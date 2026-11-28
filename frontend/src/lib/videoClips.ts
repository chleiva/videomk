// The person's own video clips in Create (docs/VIDEO_UPLOAD_2026-11-28.md API, docs/VIDEO_UPLOAD_CLIENTS_2026-11-28.md client rules, docs/VIDEO_UPLOAD_WEB_2026-11-28.md this build).
// Pure parts first (caps, local pre-checks, request and answer parsing, poll schedule, wording keys), then the ClipUploader state machine whose network, hashing and clock are INJECTED
// (ClipDeps), so the whole flow is tested without a browser or a server (videoClips.test.ts). The real network is in videoClipDeps.ts, the browser media work in localVideo.ts.

// ---------------------------------------------------------------- capabilities
/** `capabilities.video_upload`: present only where the stack has the feature on. */
export interface VideoUploadCaps {
  enabled: boolean; available: boolean; paused: boolean; clipsPerDay: number; clipsLeftToday: number; clipsPerVideo: number;
  maxBytes: number; usedSeconds: number; formats: string[]; apiUrl: string; requiresPlan: string | null;
}
export const CLIP_TYPES = ["video/mp4", "video/quicktime", "video/webm"] as const;
export const MAX_SOURCE_SECONDS = 600;   // the server refuses longer files; a file this long is not a clip

const int = (v: unknown, d: number) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.floor(v) : d);

/** Reads `video_upload` leniently: missing, disabled, or without a usable https address means "not offered" (the button is not shown at all). */
export function parseVideoUploadCaps(raw: any): VideoUploadCaps | undefined {
  if (!raw || typeof raw !== "object" || raw.enabled !== true) return undefined;
  let apiUrl = "";
  try { const u = new URL(String(raw.api_url ?? "")); if (u.protocol === "https:" && !u.username && !u.password) apiUrl = u.origin + u.pathname.replace(/\/+$/, ""); } catch { /* no address */ }
  if (!apiUrl) return undefined;
  const formats = Array.isArray(raw.formats) ? raw.formats.filter((f: unknown): f is string => typeof f === "string" && (CLIP_TYPES as readonly string[]).includes(f)) : [];
  return {
    enabled: true, available: raw.available === true, paused: raw.paused === true, clipsPerDay: int(raw.clips_per_day, 0), clipsLeftToday: int(raw.clips_left_today, 0),
    clipsPerVideo: int(raw.clips_per_video, 2) || 2, maxBytes: int(raw.max_bytes, 25 * 1024 * 1024) || 25 * 1024 * 1024, usedSeconds: int(raw.used_seconds, 5) || 5,
    formats: formats.length ? formats : [...CLIP_TYPES], apiUrl, requiresPlan: typeof raw.requires_plan === "string" && raw.requires_plan ? raw.requires_plan : null,
  };
}

export type VideoGate = { open: true } | { open: false; reason: "paused" | "quota" | "plan"; plan: string | null };
/** Whether "Add a video" works now, and if not the one reason to show (docs/VIDEO_UPLOAD_CLIENTS section 1). */
export function videoGate(c: VideoUploadCaps): VideoGate {
  if (c.available) return { open: true };
  if (c.requiresPlan) return { open: false, reason: "plan", plan: c.requiresPlan };
  if (c.paused) return { open: false, reason: "paused", plan: null };
  if (c.clipsLeftToday <= 0) return { open: false, reason: "quota", plan: null };
  return { open: false, reason: "paused", plan: null };
}

// ---------------------------------------------------------------- local checks before anything is uploaded
export interface LocalInfo { size: number; type: string; name?: string; duration?: number | null }
export type PreKind = "type" | "too_big" | "too_long" | "empty";
const EXT_TYPE: Record<string, string> = { mp4: "video/mp4", m4v: "video/mp4", mov: "video/quicktime", webm: "video/webm" };

/** The content type the server wants for this file: the browser's own when it is one of ours, else from the extension (some systems give .mov no type). */
export function contentTypeOf(f: { type: string; name?: string }, formats: readonly string[] = CLIP_TYPES): string | null {
  const t = (f.type || "").toLowerCase().split(";")[0].trim();
  if (formats.includes(t)) return t;
  const ext = /\.([a-z0-9]+)$/i.exec(f.name ?? "")?.[1]?.toLowerCase();
  const byExt = ext ? EXT_TYPE[ext] : undefined;
  return byExt && formats.includes(byExt) && (!t || t === "application/octet-stream" || t.startsWith("video/")) ? byExt : null;
}
export const looksLikeVideo = (f: { type: string; name?: string }): boolean => (f.type || "").toLowerCase().startsWith("video/") || /\.(mp4|m4v|mov|webm|mkv|avi|3gp)$/i.test(f.name ?? "");

/** The first thing wrong with the picked file, or null. `canTrim`: the browser can cut the first seconds itself, so a large file is not a blocker. */
export function precheck(f: LocalInfo, caps: Pick<VideoUploadCaps, "maxBytes" | "formats">, canTrim: boolean): PreKind | null {
  if (f.size <= 0) return "empty";
  if (!contentTypeOf(f, caps.formats)) return "type";
  if (f.duration != null && Number.isFinite(f.duration) && f.duration > MAX_SOURCE_SECONDS) return "too_long";
  if (f.size > caps.maxBytes && !canTrim) return "too_big";
  return null;
}
/** A file over the limit that the browser will cut to its first seconds before upload. */
export const needsTrim = (size: number, caps: Pick<VideoUploadCaps, "maxBytes">): boolean => size > caps.maxBytes;
/** "18 seconds" shows only for a clip longer than what is used. */
export const longerThanUsed = (duration: number | null | undefined, used: number): boolean => duration != null && Number.isFinite(duration) && duration > used + 0.5;
export function formatMB(bytes: number): string { return `${bytes >= 1e7 ? Math.round(bytes / 1048576) : Math.round(bytes / 104857.6) / 10} MB`; }

// ---------------------------------------------------------------- the clip as the server describes it
export type AudioState = "off" | "none" | "speech" | "no_speech" | "unscreened" | "unavailable";
export interface Clip {
  id: string; status: "pending" | "analysing" | "ready" | "rejected" | "failed" | string; ready: boolean; useAudio: boolean;
  width?: number; height?: number; aspect?: number; duration?: number; sourceDuration?: number; trimmed?: boolean; hasAudio?: boolean; audioUsed?: boolean; audioState?: AudioState;
  thumbUrl?: string; code?: string; message?: string;
}
const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : undefined);
const str = (v: unknown, max = 300) => (typeof v === "string" && v.trim() ? v.trim().slice(0, max) : undefined);

/** Accepts `{clip}` or the clip itself. Anything without an id is not a clip. */
export function parseClip(body: any): Clip | null {
  const c = body && typeof body === "object" && body.clip && typeof body.clip === "object" ? body.clip : body;
  if (!c || typeof c !== "object" || typeof c.id !== "string" || !c.id) return null;
  const aspect = num(c.aspect) && (c.aspect as number) > 0 ? (c.aspect as number) : num(c.width) && num(c.height) && c.height > 0 ? c.width / c.height : undefined;
  const thumb = typeof c.thumb_url === "string" && /^https:\/\//.test(c.thumb_url) ? c.thumb_url : undefined;
  return {
    id: c.id, status: String(c.status ?? ""), ready: c.ready === true || c.status === "ready", useAudio: c.use_audio === true, width: num(c.width), height: num(c.height), aspect,
    duration: num(c.duration), sourceDuration: num(c.source_duration), trimmed: c.trimmed === true, hasAudio: typeof c.has_audio === "boolean" ? c.has_audio : undefined, audioUsed: c.audio_used === true,
    audioState: typeof c.audio_state === "string" ? (c.audio_state as AudioState) : undefined, thumbUrl: thumb, code: str(c.code, 60), message: str(c.message),
  };
}

// ---------------------------------------------------------------- requests
export interface SlotRequest { size_bytes: number; content_type: string; use_audio: boolean; sha256: string }
/** The body of POST .../video-uploads: use_audio is always sent (true or false, never left out). */
export function buildSlotRequest(size: number, contentType: string, useAudio: boolean, sha256: string): SlotRequest {
  return { size_bytes: size, content_type: contentType, use_audio: useAudio === true, sha256 };
}
export function clipUrl(apiUrl: string, userId: string, id?: string, action?: "analyse"): string {
  return `${apiUrl.replace(/\/+$/, "")}/users/${encodeURIComponent(userId)}/video-uploads${id ? `/${encodeURIComponent(id)}` : ""}${action ? `/${action}` : ""}`;
}
/** `video_assets` for POST .../videos/generate: only ids that are ready, once each, at most the plan's number. Nothing at all when there are none. */
export function videoAssetsExtra(ids: string[], max = 99): Record<string, unknown> {
  const out = [...new Set(ids.filter((i) => typeof i === "string" && i))].slice(0, max);
  return out.length ? { video_assets: out } : {};
}

// ---------------------------------------------------------------- refusals and failures
export type FailKind = "network" | "check_failed" | "too_big" | "bad_request" | "quota" | "paused" | "plan" | "safety" | "rejected" | "error";
export interface Failure { kind: FailKind; message?: string; canUpgrade?: boolean; plan?: string | null; retry: boolean }
const RETRY: Record<FailKind, boolean> = { network: true, check_failed: true, too_big: false, bad_request: false, quota: false, paused: false, plan: false, safety: false, rejected: false, error: true };
const fail = (kind: FailKind, message?: string, extra: Partial<Failure> = {}): Failure => ({ kind, message, retry: RETRY[kind], ...extra });

/** What the video-uploads API answered when it said no (docs section 3: Refusals). The server's `message` is localized and is shown as it is. */
export function parseRefusal(status: number, body: any): Failure {
  body = body && typeof body === "object" ? body : {};
  const code = typeof body.code === "string" ? body.code : typeof body.error === "string" ? body.error : "";
  const message = str(body.message);
  if (status === 429 && (body.status === "paused" || code === "paused")) return fail("safety", message);
  if (code === "video_upload_paused" || (status === 503 && !code)) return fail("paused", message);
  if (code === "video_upload_quota" || status === 429) return fail("quota", message, { canUpgrade: body.can_upgrade === true, plan: str(body.requires_plan, 40) ?? null });
  if (code === "video_upload_plan" || status === 403) return fail("plan", message, { plan: str(body.requires_plan, 40) ?? null, canUpgrade: body.can_upgrade === true });
  if (code === "too_big" || status === 413) return fail("too_big", message);
  if (code === "rejected") return fail("rejected", message);
  if (status === 400 || code === "bad_request" || code === "unfinished") return fail("bad_request", message);
  if (status === 401) return fail("error", message);
  return fail("error", message);
}
/** The i18n key of a failure when the server sent no sentence of its own. */
export function failureKey(f: Pick<Failure, "kind" | "canUpgrade">): string {
  switch (f.kind) {
    case "network": return "create.clip_err_network";
    case "check_failed": return "create.clip_err_check_failed";
    case "too_big": return "create.clip_err_too_big";
    case "bad_request": return "create.clip_err_bad";
    case "quota": return f.canUpgrade ? "create.clip_err_quota_plan" : "create.clip_err_quota";
    case "paused": return "create.clip_err_paused";
    case "plan": return "create.clip_err_plan";
    case "safety": return "create.paused_fallback";
    case "rejected": return "create.clip_err_rejected";
    default: return "create.clip_err_generic";
  }
}

// ---------------------------------------------------------------- poll schedule (docs section 4: 1.5 s, 3 s after 20 s, "taking longer" at 90 s, we keep checking)
export const POLL_FAST_MS = 1500, POLL_SLOW_MS = 3000, POLL_AFTER_MS = 20_000, POLL_NOTICE_MS = 90_000, POLL_LATE_MS = 5000, POLL_GIVE_UP_MS = 600_000;
export function pollDelay(elapsedMs: number): number { return elapsedMs < POLL_AFTER_MS ? POLL_FAST_MS : elapsedMs < POLL_NOTICE_MS ? POLL_SLOW_MS : POLL_LATE_MS; }

// ---------------------------------------------------------------- the state machine
export type ClipState = "hashing" | "uploading" | "analysing" | "ready" | "rejected" | "failed" | "cancelled";
export interface ClipItem {
  key: string; name: string; state: ClipState; pct: number; id?: string; useAudio: boolean; bytes: number; clip?: Clip; failure?: Failure;
  slow: boolean;            // the check takes longer than usual: shown as one calm line, we keep checking
  poster?: string; aspect?: number; trimmed?: boolean;
}
export interface ClipInput { blob: Blob; name: string; contentType: string; useAudio: boolean; poster?: string; aspect?: number; trimmedLocally?: boolean }

export type SlotResult =
  | { kind: "slot"; id: string; url: string; fields: Record<string, string> }
  | { kind: "duplicate"; clip: Clip }
  | { kind: "refused"; failure: Failure };
export type AnalyseResult = { ok: true; clip?: Clip } | { ok: false; failure: Failure };
export type GetResult = { ok: true; clip: Clip } | { ok: false; notFound?: boolean };

export interface ClipDeps {
  sha256(blob: Blob): Promise<string>;
  createSlot(req: SlotRequest): Promise<SlotResult>;
  post(slot: { url: string; fields: Record<string, string> }, blob: Blob, onProgress: (pct: number) => void, signal: AbortSignal): Promise<{ ok: true } | { ok: false; code: "aborted" | "failed" }>;
  analyse(id: string): Promise<AnalyseResult>;
  getClip(id: string): Promise<GetResult>;
  remove(id: string): Promise<void>;
  sleep(ms: number): Promise<void>;
  now(): number;
}

interface Entry { item: ClipItem; input: ClipInput; ctl: AbortController; run: number }
const isDone = (s: ClipState) => s === "ready" || s === "rejected" || s === "failed" || s === "cancelled";

export class ClipUploader {
  private entries: Entry[] = [];
  private listeners = new Set<() => void>();
  private seq = 0;
  private cached: { items: ClipItem[] } | null = null;
  constructor(private deps: ClipDeps) {}

  subscribe(fn: () => void): () => void { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  private emit() { this.cached = null; for (const l of this.listeners) l(); }
  snapshot(): { items: ClipItem[] } { return this.cached ?? (this.cached = { items: this.entries.map((e) => ({ ...e.item })) }); }

  /** Ids of clips that are ready, in the order added: what the create request carries as `video_assets`. */
  readyIds(): string[] { return this.entries.filter((e) => e.item.state === "ready" && e.item.id).map((e) => e.item.id as string); }
  /** Something is still being sent or checked (Create waits for it, as for photos). */
  busy(): boolean { return this.entries.some((e) => !isDone(e.item.state)); }

  /** Adds an already-ready clip from the person's recent clips (no upload). Returns its key, or null when it is already in the strip. */
  addReady(clip: Clip, poster?: string): string | null {
    if (this.entries.some((e) => e.item.id === clip.id && e.item.state !== "cancelled")) return null;
    const key = `c${++this.seq}`;
    const item: ClipItem = { key, name: "", state: "ready", pct: 100, id: clip.id, useAudio: clip.useAudio, bytes: 0, clip, slow: false, poster: poster ?? clip.thumbUrl, aspect: clip.aspect };
    this.entries.push({ item, input: { blob: new Blob(), name: "", contentType: "", useAudio: clip.useAudio }, ctl: new AbortController(), run: 0 });
    this.emit();
    return key;
  }

  add(input: ClipInput): string {
    const key = `c${++this.seq}`;
    const item: ClipItem = { key, name: input.name, state: "hashing", pct: 0, useAudio: input.useAudio, bytes: input.blob.size, slow: false, poster: input.poster, aspect: input.aspect, trimmed: input.trimmedLocally };
    const e: Entry = { item, input, ctl: new AbortController(), run: 0 };
    this.entries.push(e);
    this.emit();
    void this.start(e);
    return key;
  }

  /** A fresh upload of the same file (a new slot; the old pending record expires by itself). Only for failures that can be tried again. */
  retry(key: string): void {
    const e = this.entries.find((x) => x.item.key === key);
    if (!e || e.item.state !== "failed" || !e.item.failure?.retry) return;
    e.ctl = new AbortController();
    Object.assign(e.item, { state: "hashing", pct: 0, failure: undefined, slow: false, id: undefined, clip: undefined });
    this.emit();
    void this.start(e);
  }

  /** Takes the clip out: what is in flight stops, and a clip the server holds is deleted (best effort; a video already made keeps its own copy). */
  remove(key: string): void {
    const e = this.entries.find((x) => x.item.key === key);
    if (!e) return;
    const id = e.item.id, wasBusy = !isDone(e.item.state);
    e.ctl.abort(); e.run++;
    this.entries = this.entries.filter((x) => x !== e);
    this.emit();
    if (id && !(wasBusy && e.item.state === "analysing")) void this.deps.remove(id).catch(() => {});   // an analysing clip answers 409 busy: it expires by itself
  }

  private set(e: Entry, run: number, patch: Partial<ClipItem>): boolean {
    if (e.run !== run || e.ctl.signal.aborted) return false;
    Object.assign(e.item, patch);
    this.emit();
    return true;
  }
  private live(e: Entry, run: number): boolean { return e.run === run && !e.ctl.signal.aborted; }
  private finishFail(e: Entry, run: number, failure: Failure) { this.set(e, run, { state: failure.kind === "rejected" ? "rejected" : "failed", failure, slow: false }); }

  private async start(e: Entry): Promise<void> {
    const run = ++e.run, d = this.deps, signal = e.ctl.signal;
    try {
      const hash = await d.sha256(e.input.blob);
      if (!this.live(e, run)) return;
      const slot = await d.createSlot(buildSlotRequest(e.input.blob.size, e.input.contentType, e.input.useAudio, hash));
      if (!this.live(e, run)) return;
      if (slot.kind === "refused") return this.finishFail(e, run, slot.failure);
      if (slot.kind === "duplicate") return this.settle(e, run, slot.clip);   // the same file is already ready: nothing to upload
      this.set(e, run, { state: "uploading", id: slot.id, pct: 0 });
      const up = await d.post({ url: slot.url, fields: slot.fields }, e.input.blob, (pct) => { if (this.live(e, run)) { e.item.pct = Math.max(e.item.pct, Math.min(99, Math.round(pct))); this.emit(); } }, signal);
      if (!this.live(e, run)) return;
      if (!up.ok) return this.finishFail(e, run, fail("network"));
      this.set(e, run, { state: "analysing", pct: 100 });
      const an = await d.analyse(slot.id);
      if (!this.live(e, run)) return;
      if (!an.ok) return this.finishFail(e, run, an.failure);
      if (an.clip && an.clip.status !== "pending" && an.clip.status !== "analysing") return this.settle(e, run, an.clip);
      await this.poll(e, run, slot.id);
    } catch {
      if (this.live(e, run)) this.finishFail(e, run, fail("network"));
    }
  }

  private async poll(e: Entry, run: number, id: string): Promise<void> {
    const d = this.deps, t0 = d.now();
    for (;;) {
      const elapsed = d.now() - t0;
      if (elapsed >= POLL_GIVE_UP_MS) return this.finishFail(e, run, fail("check_failed"));
      await d.sleep(pollDelay(elapsed));
      if (!this.live(e, run)) return;
      const waited = d.now() - t0;
      if (waited >= POLL_NOTICE_MS && !e.item.slow) this.set(e, run, { slow: true });
      const r = await d.getClip(id);
      if (!this.live(e, run)) return;
      if (!r.ok) { if (r.notFound) return this.finishFail(e, run, fail("check_failed")); continue; }   // a dropped poll is simply asked again
      if (r.clip.status === "pending" || r.clip.status === "analysing") continue;
      return this.settle(e, run, r.clip);
    }
  }

  private settle(e: Entry, run: number, clip: Clip): void {
    if (clip.ready || clip.status === "ready") { this.set(e, run, { state: "ready", clip, id: clip.id, pct: 100, slow: false, aspect: e.item.aspect ?? clip.aspect, failure: undefined }); return; }
    if (clip.status === "rejected" || clip.code === "rejected") return this.finishFail(e, run, fail("rejected", clip.message));
    if (clip.status === "failed" || clip.code === "check_failed") return this.finishFail(e, run, fail("check_failed", clip.message));
    this.finishFail(e, run, fail("error", clip.message));
  }
}

/** One short line for the screen reader when a clip changes state (never per progress tick). */
export function clipAnnouncementKey(items: ClipItem[]): string {
  const bad = items.find((i) => i.state === "failed" || i.state === "rejected");
  if (bad) return `bad:${bad.key}:${bad.failure?.kind ?? ""}`;
  const slow = items.find((i) => i.slow && i.state === "analysing");
  if (slow) return `slow:${slow.key}`;
  const an = items.find((i) => i.state === "analysing");
  if (an) return `check:${an.key}`;
  const up = items.find((i) => i.state === "uploading" || i.state === "hashing");
  if (up) return `up:${up.key}`;
  const ready = items.filter((i) => i.state === "ready");
  return ready.length ? `ready:${ready[ready.length - 1].key}` : "";
}
