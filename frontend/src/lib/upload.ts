// The upload queue behind "Add photos" (My media and the Create composer): a few photos at a time, each prepared (upright, at most 2048 px, JPEG, no metadata, sha256 of the
// exact bytes), given a presigned slot, posted straight to S3, with retry and backoff, pause, cancel, an aggregate progress and honest outcomes (done, already there, no space,
// not a photo we can read, failed). The network and the image work are INJECTED (QueueDeps), so the whole machine is tested without a browser (upload.test.ts).
import type { PhotoMeta } from "./exif";

export type ItemState = "queued" | "preparing" | "uploading" | "done" | "duplicate" | "no_space" | "unsupported" | "failed" | "cancelled";
export interface UploadItem { key: string; name: string; state: ItemState; pct: number; id?: string; bytes: number; attempts: number; meta?: PhotoMeta }
export interface Prepared { blob: Blob; sha256: string; meta: PhotoMeta }
export interface Slot { status: "upload" | "duplicate" | "no_space" | "rejected"; id?: string; url?: string; fields?: Record<string, string>; duplicate_of?: string }
export type SlotAnswer = { ok: true; slot: Slot } | { ok: false; kind: "storage_full" | "rate" | "error"; retryAfter?: number };
export type PostResult = { ok: true } | { ok: false; code: "aborted" | "expired" | "failed" };

export interface QueueDeps {
  /** null = this file cannot be read as a picture here (HEIC in a browser that cannot decode it, a PDF, a corrupt file). */
  prepare(file: File): Promise<Prepared | null>;
  requestSlot(p: Prepared): Promise<SlotAnswer>;
  post(slot: { url: string; fields: Record<string, string> }, blob: Blob, onProgress: (pct: number) => void, signal: AbortSignal): Promise<PostResult>;
  sleep(ms: number): Promise<void>;
  concurrency?: number;
  maxAttempts?: number;
}

export interface QueueSummary {
  total: number; finished: number; done: number; duplicates: number; noSpace: number; unsupported: number; failed: number; cancelled: number; active: number;
  pct: number; bytes: number; bytesDone: number; paused: boolean; storageFull: boolean; running: boolean;
}

export const BACKOFF_MS = [1000, 2000, 4000];
const TERMINAL: ItemState[] = ["done", "duplicate", "no_space", "unsupported", "failed", "cancelled"];
const isTerminal = (s: ItemState) => TERMINAL.includes(s);

export class UploadQueue {
  private items: { item: UploadItem; file: File }[] = [];
  private listeners = new Set<() => void>();
  private ctl = new AbortController();
  private pumping = 0;
  private paused = false;
  private storageFull = false;
  private seq = 0;
  private cached: { items: UploadItem[]; summary: QueueSummary } | null = null;

  constructor(private deps: QueueDeps) {}

  subscribe(fn: () => void): () => void { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  private emit() { this.cached = null; for (const l of this.listeners) l(); }

  snapshot(): { items: UploadItem[]; summary: QueueSummary } {
    if (this.cached) return this.cached;
    const items = this.items.map((x) => ({ ...x.item }));
    const count = (s: ItemState) => items.filter((i) => i.state === s).length;
    const total = items.length;
    const finished = items.filter((i) => isTerminal(i.state)).length;
    const progress = items.reduce((n, i) => n + (isTerminal(i.state) ? 100 : i.state === "uploading" ? i.pct : 0), 0);
    const bytes = items.reduce((n, i) => n + i.bytes, 0);
    const bytesDone = items.reduce((n, i) => n + (isTerminal(i.state) ? i.bytes : (i.bytes * (i.state === "uploading" ? i.pct : 0)) / 100), 0);
    const summary: QueueSummary = {
      total, finished, done: count("done"), duplicates: count("duplicate"), noSpace: count("no_space"), unsupported: count("unsupported"), failed: count("failed"), cancelled: count("cancelled"),
      active: items.filter((i) => i.state === "preparing" || i.state === "uploading").length, pct: total ? Math.round(progress / total) : 0, bytes, bytesDone: Math.round(bytesDone),
      paused: this.paused, storageFull: this.storageFull, running: finished < total && !this.paused,
    };
    return (this.cached = { items, summary });
  }

  /** Photos that reached the library (or were already there), in the order added: what a video may use. */
  readyIds(): string[] { return this.items.filter((x) => (x.item.state === "done" || x.item.state === "duplicate") && x.item.id).map((x) => x.item.id as string); }
  metaById(): Record<string, PhotoMeta> { const m: Record<string, PhotoMeta> = {}; for (const x of this.items) if (x.item.id && x.item.meta && (x.item.state === "done" || x.item.state === "duplicate") && Object.keys(x.item.meta).length) m[x.item.id] = x.item.meta; return m; }

  /** Adds pictures to the queue; returns their keys (same order) so a screen can show a preview per photo. */
  add(files: File[]): string[] {
    if (this.ctl.signal.aborted) this.ctl = new AbortController();
    const keys: string[] = [];
    for (const file of files) { const key = `u${++this.seq}`; keys.push(key); this.items.push({ file, item: { key, name: file.name, state: "queued", pct: 0, bytes: file.size, attempts: 0 } }); }
    this.emit();
    this.pump();
    return keys;
  }

  pause(): void { this.paused = true; this.emit(); }
  resume(): void { if (!this.paused) return; this.paused = false; this.emit(); this.pump(); }

  /** Stops what is running and marks everything not finished as cancelled. Finished photos stay in the library. */
  cancel(): void {
    this.ctl.abort();
    for (const x of this.items) if (!isTerminal(x.item.state)) x.item.state = "cancelled";
    this.paused = false;
    this.emit();
  }

  /** Tries the failed ones again (one more full round of attempts). */
  retryFailed(): void {
    if (this.ctl.signal.aborted) this.ctl = new AbortController();
    for (const x of this.items) if (x.item.state === "failed") { x.item.state = "queued"; x.item.attempts = 0; x.item.pct = 0; }
    this.emit();
    this.pump();
  }

  /** Takes one photo out (the person removed it from the composer): a finished one is forgotten, one in flight is ignored from now on (its result is dropped). */
  remove(key: string): void {
    const x = this.items.find((i) => i.item.key === key);
    if (!x) return;
    if (isTerminal(x.item.state)) this.items = this.items.filter((i) => i !== x);
    else x.item.state = "cancelled";
    this.emit();
  }

  /** Forgets finished items (the banner after the person dismissed it). */
  clearFinished(): void { this.items = this.items.filter((x) => !isTerminal(x.item.state)); this.storageFull = false; this.emit(); }

  private set(x: { item: UploadItem }, patch: Partial<UploadItem>) { Object.assign(x.item, patch); this.emit(); }

  private pump(): void {
    const limit = this.deps.concurrency ?? 4;
    while (!this.paused && this.pumping < limit) {
      const next = this.items.find((x) => x.item.state === "queued");
      if (!next) return;
      next.item.state = "preparing";
      this.pumping++;
      this.emit();
      this.run(next).catch(() => this.set(next, { state: "failed" })).finally(() => { this.pumping--; this.pump(); });
    }
  }

  private async run(x: { item: UploadItem; file: File }): Promise<void> {
    const signal = this.ctl.signal;
    const max = this.deps.maxAttempts ?? 3;
    const prepared = await this.deps.prepare(x.file);
    if (signal.aborted) return;
    if (!prepared) return this.set(x, { state: "unsupported" });
    x.item.meta = prepared.meta;
    x.item.bytes = prepared.blob.size;
    for (;;) {
      if (signal.aborted) return;
      if (this.storageFull) return this.set(x, { state: "no_space" });
      x.item.attempts++;
      const ans = await this.deps.requestSlot(prepared);
      if (signal.aborted) return;
      if (!ans.ok) {
        if (ans.kind === "storage_full") { this.storageFull = true; return this.set(x, { state: "no_space" }); }
        if (x.item.attempts >= max) return this.set(x, { state: "failed" });
        await this.deps.sleep(ans.kind === "rate" && ans.retryAfter ? Math.min(ans.retryAfter, 60) * 1000 : BACKOFF_MS[Math.min(x.item.attempts - 1, BACKOFF_MS.length - 1)]);
        continue;
      }
      const slot = ans.slot;
      if (slot.status === "duplicate") return this.set(x, { state: "duplicate", id: slot.duplicate_of ?? slot.id, pct: 100 });
      if (slot.status === "no_space") return this.set(x, { state: "no_space" });
      if (slot.status === "rejected") return this.set(x, { state: "failed" });   // the server read the file and refused it: trying again cannot help
      if (slot.status !== "upload" || !slot.url || !slot.fields || !slot.id) { if (x.item.attempts >= max) return this.set(x, { state: "failed" }); continue; }
      this.set(x, { state: "uploading", id: slot.id, pct: 0 });
      const res = await this.deps.post({ url: slot.url, fields: slot.fields }, prepared.blob, (pct) => { x.item.pct = Math.max(x.item.pct, Math.min(99, pct)); this.emit(); }, signal);
      if (signal.aborted || (!res.ok && res.code === "aborted")) return;
      if (res.ok) return this.set(x, { state: "done", pct: 100 });
      if (x.item.attempts >= max) return this.set(x, { state: "failed" });
      this.set(x, { state: "preparing", pct: 0 });   // back to the slot request: an expired link needs a fresh one (same photo id), a network error simply tries again
      await this.deps.sleep(BACKOFF_MS[Math.min(x.item.attempts - 1, BACKOFF_MS.length - 1)]);
    }
  }
}

// ---------------------------------------------------------------- small pure helpers the UI shares
export const IMAGE_EXT = /\.(jpe?g|png|webp|gif|bmp|avif|heic|heif|tiff?)$/i;

/** Keeps what looks like a picture (by type or extension); everything else is dropped quietly (a folder drop brings .DS_Store and sidecar files). */
export function pictureFiles(files: Iterable<File>): File[] {
  return [...files].filter((f) => f.type.startsWith("image/") || (!f.type && IMAGE_EXT.test(f.name)) || IMAGE_EXT.test(f.name));
}

/** The one calm line of the banner: "Uploading 37 of 120", or the outcome. Returns the i18n key and its parameters. */
export function bannerLine(s: QueueSummary): { key: string; params: Record<string, number> } {
  if (s.total === 0) return { key: "upload.none", params: {} };
  if (s.finished < s.total && s.paused) return { key: "upload.paused", params: { done: s.finished, total: s.total } };
  if (s.finished < s.total) return { key: "upload.progress", params: { done: Math.min(s.finished + 1, s.total), total: s.total } };
  if (s.cancelled > 0) return { key: "upload.cancelled", params: { n: s.done + s.duplicates } };
  return { key: "upload.finished", params: { n: s.done } };
}
