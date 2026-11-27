import { describe, expect, it } from "vitest";
import { BACKOFF_MS, UploadQueue, bannerLine, pictureFiles } from "./upload";
import type { PostResult, Prepared, QueueDeps, Slot, SlotAnswer } from "./upload";

const file = (name: string, size = 1000, type = "image/jpeg") => new File([new Uint8Array(size)], name, { type });
const prepared = (f: File): Prepared => ({ blob: new Blob([new Uint8Array(f.size)]), sha256: `sha-${f.name}`, meta: f.name.startsWith("dated") ? { taken: "2024-07-14T10:00:00" } : {} });

interface Fake { deps: QueueDeps; slots: string[]; posts: string[]; sleeps: number[]; maxParallel: () => number }
function fake(opts: { slot?: (name: string, n: number) => SlotAnswer; post?: (name: string, n: number) => PostResult; prepare?: (f: File) => Prepared | null; gate?: Promise<void> } = {}): Fake {
  const slots: string[] = [], posts: string[] = [], sleeps: number[] = [];
  const slotCalls = new Map<string, number>(), postCalls = new Map<string, number>();
  let running = 0, peak = 0;
  const deps: QueueDeps = {
    concurrency: 3, maxAttempts: 3,
    prepare: async (f) => (opts.prepare ? opts.prepare(f) : prepared(f)),
    requestSlot: async (p) => {
      const name = p.sha256.slice(4); slots.push(name);
      const n = (slotCalls.get(name) ?? 0) + 1; slotCalls.set(name, n);
      return opts.slot ? opts.slot(name, n) : { ok: true, slot: { status: "upload", id: `id-${name}`, url: "https://bucket.s3.amazonaws.com/", fields: { k: name } } as Slot };
    },
    post: async (slot, _b, onProgress) => {
      const name = slot.fields.k; posts.push(name);
      running++; peak = Math.max(peak, running);
      if (opts.gate) await opts.gate;
      await Promise.resolve();
      onProgress(50);
      running--;
      const n = (postCalls.get(name) ?? 0) + 1; postCalls.set(name, n);
      return opts.post ? opts.post(name, n) : { ok: true };
    },
    sleep: async (ms) => { sleeps.push(ms); },
  };
  return { deps, slots, posts, sleeps, maxParallel: () => peak };
}
async function settled(q: UploadQueue): Promise<void> {
  for (let i = 0; i < 400; i++) { const s = q.snapshot().summary; if (s.finished >= s.total && s.active === 0) return; await new Promise((r) => setTimeout(r, 0)); }
  throw new Error("queue did not settle: " + JSON.stringify(q.snapshot().summary));
}

describe("UploadQueue", () => {
  it("uploads every photo, reports progress and returns their ids in order", async () => {
    const f = fake(); const q = new UploadQueue(f.deps);
    q.add([file("a.jpg"), file("b.jpg"), file("c.jpg")]);
    await settled(q);
    const s = q.snapshot().summary;
    expect(s).toMatchObject({ total: 3, done: 3, failed: 0, pct: 100, finished: 3 });
    expect(q.readyIds()).toEqual(["id-a.jpg", "id-b.jpg", "id-c.jpg"]);
  });
  it("never runs more than the concurrency limit at once", async () => {
    let open!: () => void; const gate = new Promise<void>((r) => (open = r));
    const f = fake({ gate }); const q = new UploadQueue(f.deps);
    q.add(Array.from({ length: 10 }, (_, i) => file(`p${i}.jpg`)));
    await new Promise((r) => setTimeout(r, 5));
    expect(q.snapshot().summary.active).toBeLessThanOrEqual(3);
    open(); await settled(q);
    expect(f.maxParallel()).toBeLessThanOrEqual(3);
    expect(q.snapshot().summary.done).toBe(10);
  });
  it("a duplicate is counted, not uploaded, and its id is the library photo", async () => {
    const f = fake({ slot: (n) => (n === "b.jpg" ? { ok: true, slot: { status: "duplicate", duplicate_of: "old-b" } } : { ok: true, slot: { status: "upload", id: `id-${n}`, url: "https://x.s3.amazonaws.com/", fields: { k: n } } }) });
    const q = new UploadQueue(f.deps); q.add([file("a.jpg"), file("b.jpg")]); await settled(q);
    expect(q.snapshot().summary).toMatchObject({ done: 1, duplicates: 1 });
    expect(f.posts).toEqual(["a.jpg"]);
    expect(q.readyIds()).toEqual(["id-a.jpg", "old-b"]);
  });
  it("retries a failed post with backoff and succeeds on the third attempt (asking for a fresh slot each time)", async () => {
    const f = fake({ post: (_n, k) => (k < 3 ? { ok: false, code: "failed" } : { ok: true }) });
    const q = new UploadQueue(f.deps); q.add([file("a.jpg")]); await settled(q);
    expect(q.snapshot().summary.done).toBe(1);
    expect(f.slots).toEqual(["a.jpg", "a.jpg", "a.jpg"]);
    expect(f.sleeps).toEqual([BACKOFF_MS[0], BACKOFF_MS[1]]);
  });
  it("gives up after the attempts and marks the photo failed; retryFailed tries again", async () => {
    let healthy = false;
    const f = fake({ post: () => (healthy ? { ok: true } : { ok: false, code: "failed" }) });
    const q = new UploadQueue(f.deps); q.add([file("a.jpg"), file("b.jpg")]); await settled(q);
    expect(q.snapshot().summary).toMatchObject({ failed: 2, done: 0 });
    healthy = true; q.retryFailed(); await settled(q);
    expect(q.snapshot().summary).toMatchObject({ failed: 0, done: 2 });
  });
  it("rate limited: waits the Retry-After the server sent (capped) and goes on", async () => {
    const f = fake({ slot: (n, k) => (k === 1 ? { ok: false, kind: "rate", retryAfter: 7 } : { ok: true, slot: { status: "upload", id: `id-${n}`, url: "https://x.s3.amazonaws.com/", fields: { k: n } } }) });
    const q = new UploadQueue(f.deps); q.add([file("a.jpg")]); await settled(q);
    expect(f.sleeps).toEqual([7000]);
    expect(q.snapshot().summary.done).toBe(1);
  });
  it("storage full stops asking: the photo that hit it and everything after is 'no space', already uploaded ones stay", async () => {
    const f = fake({ slot: (n) => (n === "b.jpg" ? { ok: false, kind: "storage_full" } : { ok: true, slot: { status: "upload", id: `id-${n}`, url: "https://x.s3.amazonaws.com/", fields: { k: n } } }) });
    f.deps.concurrency = 1;
    const q = new UploadQueue(f.deps); q.add([file("a.jpg"), file("b.jpg"), file("c.jpg"), file("d.jpg")]); await settled(q);
    const s = q.snapshot().summary;
    expect(s).toMatchObject({ done: 1, noSpace: 3, storageFull: true });
    expect(f.slots).toEqual(["a.jpg", "b.jpg"]);
  });
  it("a slot with status no_space or rejected is final: no retry", async () => {
    const f = fake({ slot: (n) => ({ ok: true, slot: { status: n === "a.jpg" ? "no_space" : "rejected" } }) });
    const q = new UploadQueue(f.deps); q.add([file("a.jpg"), file("b.jpg")]); await settled(q);
    expect(q.snapshot().summary).toMatchObject({ noSpace: 1, failed: 1 });
    expect(f.slots.length).toBe(2);
  });
  it("a file that cannot be read is 'unsupported' and never touches the network", async () => {
    const f = fake({ prepare: (x) => (x.name.endsWith(".heic") ? null : prepared(x)) });
    const q = new UploadQueue(f.deps); q.add([file("a.heic", 10, "image/heic"), file("b.jpg")]); await settled(q);
    expect(q.snapshot().summary).toMatchObject({ unsupported: 1, done: 1 });
    expect(f.slots).toEqual(["b.jpg"]);
  });
  it("pause stops new work, resume continues", async () => {
    const f = fake(); f.deps.concurrency = 1;
    const q = new UploadQueue(f.deps); q.pause();
    q.add([file("a.jpg"), file("b.jpg")]);
    await new Promise((r) => setTimeout(r, 10));
    expect(q.snapshot().summary).toMatchObject({ done: 0, paused: true });
    q.resume(); await settled(q);
    expect(q.snapshot().summary.done).toBe(2);
  });
  it("cancel marks the unfinished as cancelled and keeps the finished", async () => {
    let open!: () => void; const gate = new Promise<void>((r) => (open = r));
    const f = fake({ gate }); f.deps.concurrency = 1;
    const q = new UploadQueue(f.deps); q.add([file("a.jpg"), file("b.jpg"), file("c.jpg")]);
    await new Promise((r) => setTimeout(r, 5));
    q.cancel(); open();
    await new Promise((r) => setTimeout(r, 10));
    const s = q.snapshot().summary;
    expect(s.cancelled).toBe(3); expect(s.done).toBe(0);
    q.add([file("d.jpg")]); await settled(q);   // the queue is usable again after a cancel
    expect(q.snapshot().summary.done).toBe(1);
  });
  it("keeps the capture date and position of each photo to send with the slot request", async () => {
    const f = fake(); const q = new UploadQueue(f.deps); q.add([file("dated.jpg"), file("plain.jpg")]); await settled(q);
    expect(q.metaById()).toEqual({ "id-dated.jpg": { taken: "2024-07-14T10:00:00" } });
  });
  it("remove takes one photo out: queued ones are never uploaded, finished ones leave the list and the ready ids", async () => {
    const f = fake(); f.deps.concurrency = 1;
    const q = new UploadQueue(f.deps); q.pause(); q.add([file("a.jpg"), file("b.jpg"), file("c.jpg")]);
    q.remove(q.snapshot().items[1].key); q.resume(); await settled(q);
    expect(f.posts).toEqual(["a.jpg", "c.jpg"]);
    expect(q.readyIds()).toEqual(["id-a.jpg", "id-c.jpg"]);
    q.remove(q.snapshot().items[0].key);
    expect(q.readyIds()).toEqual(["id-c.jpg"]);
  });
  it("clearFinished forgets finished photos only", async () => {
    const f = fake(); const q = new UploadQueue(f.deps); q.add([file("a.jpg")]); await settled(q);
    q.clearFinished(); expect(q.snapshot().summary.total).toBe(0);
  });
});

describe("helpers", () => {
  it("pictureFiles keeps pictures and drops sidecar files from a folder drop", () => {
    const names = pictureFiles([file("a.jpg"), file(".DS_Store", 1, ""), file("b.HEIC", 1, ""), file("notes.txt", 1, "text/plain"), file("c.png", 1, "image/png")]).map((x) => x.name);
    expect(names).toEqual(["a.jpg", "b.HEIC", "c.png"]);
  });
  it("the banner line", () => {
    const base = { total: 10, finished: 3, done: 3, duplicates: 0, noSpace: 0, unsupported: 0, failed: 0, cancelled: 0, active: 2, pct: 30, bytes: 1, bytesDone: 0, paused: false, storageFull: false, running: true };
    expect(bannerLine(base)).toEqual({ key: "upload.progress", params: { done: 4, total: 10 } });
    expect(bannerLine({ ...base, paused: true }).key).toBe("upload.paused");
    expect(bannerLine({ ...base, finished: 10, done: 10 })).toEqual({ key: "upload.finished", params: { n: 10 } });
    expect(bannerLine({ ...base, finished: 10, done: 4, cancelled: 6 }).key).toBe("upload.cancelled");
  });
});
