// Video clips in Create: caps, local checks, request and answer parsing, and the whole upload state machine with a fake server (no network, no browser, no real clock).
import { describe, expect, it } from "vitest";
import {
  ClipUploader, POLL_GIVE_UP_MS, POLL_NOTICE_MS, buildSlotRequest, clipAnnouncementKey, clipUrl, contentTypeOf, failureKey, longerThanUsed, looksLikeVideo, needsTrim,
  parseClip, parseRefusal, parseVideoUploadCaps, pollDelay, precheck, videoAssetsExtra, videoGate,
} from "./videoClips";
import type { AnalyseResult, Clip, ClipDeps, ClipInput, GetResult, SlotRequest, SlotResult } from "./videoClips";
import { parseCapabilities } from "./create";
import { BY_AREA } from "../i18n/catalog";

const MB = 1024 * 1024;
const RAW = { enabled: true, available: true, paused: false, clips_per_day: 3, clips_left_today: 2, clips_per_video: 2, max_bytes: 25 * MB, used_seconds: 5, formats: ["video/mp4", "video/quicktime", "video/webm"], api_url: "https://vid.example.com/prod/", requires_plan: null };
const caps = parseVideoUploadCaps(RAW)!;

describe("capabilities.video_upload", () => {
  it("is read leniently: off, malformed or without an https address means no button", () => {
    expect(parseVideoUploadCaps(undefined)).toBeUndefined();
    expect(parseVideoUploadCaps({ ...RAW, enabled: false })).toBeUndefined();
    expect(parseVideoUploadCaps({ ...RAW, api_url: "http://vid.example.com" })).toBeUndefined();
    expect(parseVideoUploadCaps({ ...RAW, api_url: "not a url" })).toBeUndefined();
    expect(parseVideoUploadCaps({ ...RAW, api_url: "https://user:pw@vid.example.com" })).toBeUndefined();
  });
  it("keeps the numbers, the formats and the address without a trailing slash", () => {
    expect(caps).toMatchObject({ clipsPerVideo: 2, clipsLeftToday: 2, maxBytes: 25 * MB, usedSeconds: 5, apiUrl: "https://vid.example.com/prod", requiresPlan: null });
    expect(parseVideoUploadCaps({ ...RAW, formats: ["video/avi"] })!.formats).toEqual(["video/mp4", "video/quicktime", "video/webm"]);
  });
  it("is part of the Create capabilities", () => {
    const body = { aspects: [{ id: "16:9", label: "L", ready: true }], resolutions: [{ id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ["16:9"] }], lengths: { presets: [1], min_minutes: 1, max_minutes: 2 }, video_upload: RAW };
    expect(parseCapabilities(body)!.video_upload?.apiUrl).toBe("https://vid.example.com/prod");
    expect(parseCapabilities({ ...body, video_upload: undefined })!.video_upload).toBeUndefined();
  });
  it("the gate: open, or the one reason (plan before paused before no clips left)", () => {
    expect(videoGate(caps)).toEqual({ open: true });
    expect(videoGate({ ...caps, available: false, paused: true })).toMatchObject({ open: false, reason: "paused" });
    expect(videoGate({ ...caps, available: false, clipsLeftToday: 0 })).toMatchObject({ open: false, reason: "quota" });
    expect(videoGate({ ...caps, available: false, requiresPlan: "pro", paused: true })).toEqual({ open: false, reason: "plan", plan: "pro" });
  });
});

describe("checks before anything is uploaded", () => {
  const f = (o: Partial<{ size: number; type: string; name: string; duration: number | null }> = {}) => ({ size: 5 * MB, type: "video/mp4", name: "a.mp4", duration: 4, ...o });
  it("accepts a normal clip", () => expect(precheck(f(), caps, false)).toBeNull());
  it("type: by the browser's type, else by the extension (a .mov with no type); anything else is refused", () => {
    expect(contentTypeOf({ type: "", name: "IMG_1.MOV" })).toBe("video/quicktime");
    expect(contentTypeOf({ type: "video/mp4;codecs=avc1", name: "x" })).toBe("video/mp4");
    expect(contentTypeOf({ type: "video/x-matroska", name: "a.mkv" })).toBeNull();
    expect(precheck(f({ type: "image/png", name: "a.png" }), caps, false)).toBe("type");
    expect(precheck(f({ type: "video/x-msvideo", name: "a.avi" }), caps, true)).toBe("type");
  });
  it("size: over 25 MB is refused unless this browser can cut it", () => {
    expect(precheck(f({ size: 25 * MB }), caps, false)).toBeNull();
    expect(precheck(f({ size: 25 * MB + 1 }), caps, false)).toBe("too_big");
    expect(precheck(f({ size: 90 * MB }), caps, true)).toBeNull();
    expect(needsTrim(25 * MB + 1, caps)).toBe(true); expect(needsTrim(25 * MB, caps)).toBe(false);
  });
  it("an absurd length (over 10 minutes) and an empty file are refused; an unknown length is not a reason to refuse", () => {
    expect(precheck(f({ duration: 601 }), caps, true)).toBe("too_long");
    expect(precheck(f({ duration: 600 }), caps, true)).toBeNull();
    expect(precheck(f({ duration: null }), caps, false)).toBeNull();
    expect(precheck(f({ size: 0 }), caps, false)).toBe("empty");
  });
  it("the notice names the length only when the clip is longer than what is used", () => {
    expect(longerThanUsed(18, 5)).toBe(true); expect(longerThanUsed(5.2, 5)).toBe(false); expect(longerThanUsed(null, 5)).toBe(false);
  });
  it("looks like a video by type or extension (a drop brings other files too)", () => {
    expect(looksLikeVideo({ type: "video/quicktime", name: "a" })).toBe(true); expect(looksLikeVideo({ type: "", name: "a.WEBM" })).toBe(true); expect(looksLikeVideo({ type: "image/jpeg", name: "a.jpg" })).toBe(false);
  });
});

describe("requests", () => {
  it("the slot request always carries use_audio (true or false), the size, the type and the hash", () => {
    expect(buildSlotRequest(10, "video/mp4", false, "ab")).toEqual({ size_bytes: 10, content_type: "video/mp4", use_audio: false, sha256: "ab" });
    expect(buildSlotRequest(10, "video/webm", true, "ab").use_audio).toBe(true);
  });
  it("urls go to the clip API, per user, encoded", () => {
    expect(clipUrl("https://v.test/prod/", "u 1")).toBe("https://v.test/prod/users/u%201/video-uploads");
    expect(clipUrl("https://v.test", "u", "c1", "analyse")).toBe("https://v.test/users/u/video-uploads/c1/analyse");
    expect(clipUrl("https://v.test", "u", "c1")).toBe("https://v.test/users/u/video-uploads/c1");
  });
  it("video_assets: ready ids only, once each, at most the plan's number, and nothing when empty", () => {
    expect(videoAssetsExtra([])).toEqual({});
    expect(videoAssetsExtra(["a", "b", "a", ""], 4)).toEqual({ video_assets: ["a", "b"] });
    expect(videoAssetsExtra(["a", "b", "c"], 2)).toEqual({ video_assets: ["a", "b"] });
  });
});

describe("the clip as the server describes it", () => {
  it("reads a ready clip, wrapped or not, with its shape and sound", () => {
    const body = { id: "c1", status: "ready", ready: true, use_audio: true, width: 1920, height: 1080, duration: 4.9, trimmed: true, audio_used: true, audio_state: "speech", thumb_url: "https://s3.test/t.jpg?sig=1" };
    for (const b of [body, { clip: body }]) expect(parseClip(b)).toMatchObject({ id: "c1", ready: true, useAudio: true, audioUsed: true, trimmed: true, audioState: "speech", thumbUrl: "https://s3.test/t.jpg?sig=1" });
    expect(parseClip(body)!.aspect).toBeCloseTo(16 / 9, 3);
  });
  it("a body without an id is not a clip; a thumbnail that is not https is dropped", () => {
    expect(parseClip({})).toBeNull(); expect(parseClip(null)).toBeNull();
    expect(parseClip({ id: "c", status: "ready", thumb_url: "javascript:alert(1)" })!.thumbUrl).toBeUndefined();
  });
});

describe("refusals: the server's sentence is used as it is, never a code", () => {
  it("one answer per row of the spec", () => {
    expect(parseRefusal(413, { code: "too_big" }).kind).toBe("too_big");
    expect(parseRefusal(400, { code: "bad_request" }).kind).toBe("bad_request");
    expect(parseRefusal(400, { code: "rejected", message: "m" })).toMatchObject({ kind: "rejected", retry: false, message: "m" });
    expect(parseRefusal(429, { code: "video_upload_quota", can_upgrade: true })).toMatchObject({ kind: "quota", canUpgrade: true, retry: false });
    expect(parseRefusal(503, { code: "video_upload_paused" })).toMatchObject({ kind: "paused", retry: false });
    expect(parseRefusal(403, { code: "video_upload_plan", requires_plan: "pro" })).toMatchObject({ kind: "plan", plan: "pro" });
    expect(parseRefusal(429, { status: "paused", message: "Account paused" })).toMatchObject({ kind: "safety", message: "Account paused" });
    expect(parseRefusal(500, {})).toMatchObject({ kind: "error", retry: true });
  });
  it("every failure has our own sentence in both languages", () => {
    const { en, es } = BY_AREA["app-create"];
    for (const kind of ["network", "check_failed", "too_big", "bad_request", "quota", "paused", "plan", "safety", "rejected", "error"] as const) for (const canUpgrade of [false, true]) { const k = failureKey({ kind, canUpgrade }); expect(en[k], k).toBeTruthy(); expect(es[k], k).toBeTruthy(); }
    expect(en["create.clip_err_check_failed"]).toBe("We could not check that clip this time. Please try again.");
    expect(en["create.clip_err_rejected"]).toBe("We could not use this clip. Please choose a different one.");   // never says why
    expect(en["create.clip_err_paused"]).toBe("Adding video clips is paused for a while. Photos still work.");
    expect(en["create.clip_checking"]).toBe("Checking your video…");
  });
  it("the poll goes 1.5 s, 3 s after 20 s, 5 s after 90 s", () => { expect(pollDelay(0)).toBe(1500); expect(pollDelay(25_000)).toBe(3000); expect(pollDelay(100_000)).toBe(5000); });
});

// ---------------------------------------------------------------- the state machine, with a fake server and a fake clock
const readyClip = (id: string, extra: Partial<Clip> = {}): Clip => ({ id, status: "ready", ready: true, useAudio: false, duration: 5, aspect: 16 / 9, ...extra });
const pending = (id: string): Clip => ({ id, status: "analysing", ready: false, useAudio: false });

interface Fake { deps: ClipDeps; calls: string[]; slots: SlotRequest[]; clock: { t: number }; script: { slot?: SlotResult[]; post?: ("ok" | "fail")[]; analyse?: AnalyseResult[]; get?: GetResult[] } }
function fake(script: Fake["script"] = {}): Fake {
  const calls: string[] = [], slots: SlotRequest[] = [], clock = { t: 0 };
  let n = 0;
  const next = <T,>(arr: T[] | undefined, dflt: T): T => (arr && arr.length > 1 ? arr.shift()! : arr?.[0] ?? dflt);
  const deps: ClipDeps = {
    async sha256() { calls.push("sha"); return "h".repeat(64); },
    async createSlot(req) { calls.push("slot"); slots.push(req); return next(script.slot, { kind: "slot", id: `c${++n}`, url: "https://b.s3.eu-west-1.amazonaws.com/", fields: { key: "k" } } as SlotResult); },
    async post(_s, _b, onProgress, signal) { calls.push("post"); onProgress(42); if (signal.aborted) return { ok: false, code: "aborted" }; return next(script.post, "ok") === "ok" ? { ok: true } : { ok: false, code: "failed" }; },
    async analyse() { calls.push("analyse"); return next(script.analyse, { ok: true, clip: pending("x") } as AnalyseResult); },
    async getClip() { calls.push("get"); return next(script.get, { ok: true, clip: readyClip("c1") } as GetResult); },
    async remove(id) { calls.push(`remove:${id}`); },
    async sleep(ms) { clock.t += ms; await Promise.resolve(); },
    now: () => clock.t,
  };
  return { deps, calls, slots, clock, script };
}
const input = (o: Partial<ClipInput> = {}): ClipInput => ({ blob: new Blob([new Uint8Array(2000)]), name: "a.mp4", contentType: "video/mp4", useAudio: true, ...o });
const settle = async (u: ClipUploader, until: (s: ReturnType<ClipUploader["snapshot"]>["items"]) => boolean = (i) => i.every((x) => ["ready", "rejected", "failed", "cancelled"].includes(x.state))) => { for (let i = 0; i < 200 && !until(u.snapshot().items); i++) await new Promise((r) => setTimeout(r, 0)); return u.snapshot().items; };

describe("ClipUploader", () => {
  it("hash, slot, upload with progress, analyse, poll until ready: the clip is ready and usable", async () => {
    const f = fake({ get: [{ ok: true, clip: pending("c1") }, { ok: true, clip: readyClip("c1", { audioUsed: true }) }] });
    const u = new ClipUploader(f.deps);
    const key = u.add(input());
    expect(u.busy()).toBe(true);
    const items = await settle(u);
    expect(f.calls).toEqual(["sha", "slot", "post", "analyse", "get", "get"]);
    expect(items[0]).toMatchObject({ key, state: "ready", id: "c1", pct: 100 });
    expect(u.readyIds()).toEqual(["c1"]); expect(u.busy()).toBe(false);
  });
  it("use_audio, size and type go in the slot request exactly as chosen (silent is false, not missing)", async () => {
    const f = fake(); const u = new ClipUploader(f.deps);
    u.add(input({ useAudio: false, contentType: "video/webm" })); await settle(u);
    expect(f.slots[0]).toMatchObject({ use_audio: false, content_type: "video/webm", size_bytes: 2000 });
    expect(f.slots[0].sha256).toHaveLength(64);
  });
  it("the progress rises to 99 while sending and is 100 only when checking", async () => {
    const f = fake({ get: [{ ok: true, clip: pending("c1") }, { ok: true, clip: readyClip("c1") }] }); const u = new ClipUploader(f.deps);
    const seen: string[] = []; u.subscribe(() => { const i = u.snapshot().items[0]; if (i) seen.push(`${i.state}:${i.pct}`); });
    u.add(input()); await settle(u);
    expect(seen).toContain("uploading:42"); expect(seen).toContain("analysing:100");
  });
  it("a duplicate answer skips the upload and the analysis: ready straight away", async () => {
    const f = fake({ slot: [{ kind: "duplicate", clip: readyClip("old") }] }); const u = new ClipUploader(f.deps);
    u.add(input()); const items = await settle(u);
    expect(f.calls).toEqual(["sha", "slot"]); expect(items[0]).toMatchObject({ state: "ready", id: "old" }); expect(u.readyIds()).toEqual(["old"]);
  });
  it.each([
    ["quota", { kind: "quota" as const, retry: false }], ["paused (503 video_upload_paused)", { kind: "paused" as const, retry: false }], ["plan", { kind: "plan" as const, retry: false }],
    ["too big", { kind: "too_big" as const, retry: false }], ["bad request", { kind: "bad_request" as const, retry: false }], ["safety pause", { kind: "safety" as const, message: "Paused", retry: false }],
  ])("a refusal at the door (%s) stops there: nothing is uploaded and there is no retry", async (_n, failure) => {
    const f = fake({ slot: [{ kind: "refused", failure }] }); const u = new ClipUploader(f.deps);
    u.add(input()); const [it] = await settle(u);
    expect(f.calls).toEqual(["sha", "slot"]); expect(it.state).toBe("failed"); expect(it.failure).toMatchObject({ kind: failure.kind, retry: false });
    u.retry(it.key); expect((await settle(u))[0].state).toBe("failed"); expect(f.calls.filter((c) => c === "slot")).toHaveLength(1);   // retry does nothing for a refusal
    expect(u.readyIds()).toEqual([]);
  });
  it("a network error while uploading fails with Try again, and Try again takes a NEW slot and finishes", async () => {
    const f = fake({ post: ["fail", "ok"], get: [{ ok: true, clip: readyClip("c2") }] }); const u = new ClipUploader(f.deps);
    u.add(input()); let [it] = await settle(u);
    expect(it.state).toBe("failed"); expect(it.failure).toMatchObject({ kind: "network", retry: true });
    u.retry(it.key); [it] = await settle(u);
    expect(it.state).toBe("ready"); expect(f.calls.filter((c) => c === "slot")).toHaveLength(2); expect(f.calls.filter((c) => c === "post")).toHaveLength(2);
  });
  it("a clip the checks refused ends as rejected: no retry, no reason", async () => {
    const f = fake({ get: [{ ok: true, clip: { id: "c1", status: "rejected", ready: false, useAudio: false, code: "rejected", message: "secret reason" } }] });
    const u = new ClipUploader(f.deps); u.add(input()); const [it] = await settle(u);
    expect(it.state).toBe("rejected"); expect(it.failure?.retry).toBe(false); expect(u.readyIds()).toEqual([]);
  });
  it("a check that could not run (failed) can be tried again with a fresh upload", async () => {
    const f = fake({ get: [{ ok: true, clip: { id: "c1", status: "failed", ready: false, useAudio: false, code: "check_failed" } }, { ok: true, clip: readyClip("c1") }] });
    const u = new ClipUploader(f.deps); u.add(input()); let [it] = await settle(u);
    expect(it).toMatchObject({ state: "failed", failure: { kind: "check_failed", retry: true } });
    u.retry(it.key); [it] = await settle(u); expect(it.state).toBe("ready");
  });
  it("analyse refused (the day's ceiling: 503 paused) is shown as paused", async () => {
    const f = fake({ analyse: [{ ok: false, failure: { kind: "paused", retry: false } }] }); const u = new ClipUploader(f.deps);
    u.add(input()); const [it] = await settle(u); expect(it.failure?.kind).toBe("paused");
  });
  it("a dropped poll is simply asked again; a 404 means the check cannot be found", async () => {
    const f = fake({ get: [{ ok: false }, { ok: false }, { ok: true, clip: readyClip("c1") }] }); const u = new ClipUploader(f.deps);
    u.add(input()); expect((await settle(u))[0].state).toBe("ready");
    const g = fake({ get: [{ ok: false, notFound: true }] }); const v = new ClipUploader(g.deps);
    v.add(input()); expect((await settle(v))[0]).toMatchObject({ state: "failed", failure: { kind: "check_failed" } });
  });
  it("after 90 s the line says it takes longer and we keep checking; after 10 minutes it gives up with Try again", async () => {
    const f = fake({ get: [{ ok: true, clip: pending("c1") }] }); const u = new ClipUploader(f.deps);
    let slow: ReturnType<ClipUploader["snapshot"]>["items"][number] | null = null, at = 0;
    u.subscribe(() => { const i = u.snapshot().items[0]; if (i?.slow && !slow) { slow = i; at = f.clock.t; } });
    u.add(input());
    const end = await settle(u);
    expect(slow).toMatchObject({ state: "analysing", slow: true }); expect(at).toBeGreaterThanOrEqual(POLL_NOTICE_MS); expect(at).toBeLessThan(POLL_NOTICE_MS + 6000);
    expect(end[0]).toMatchObject({ state: "failed", failure: { kind: "check_failed", retry: true } }); expect(f.clock.t).toBeGreaterThanOrEqual(POLL_GIVE_UP_MS);
  });
  it("removing a clip while it uploads stops it, drops its result and deletes the slot's record; nothing late can bring it back", async () => {
    const f = fake(); let release: () => void = () => {};
    const gate = new Promise<void>((r) => (release = r));
    const slowPost = f.deps.post; f.deps.post = async (...a) => { await gate; return slowPost(...a); };
    const u = new ClipUploader(f.deps); const key = u.add(input());
    await settle(u, (i) => i[0]?.state === "uploading");
    u.remove(key); release(); await new Promise((r) => setTimeout(r, 5));
    expect(u.snapshot().items).toEqual([]); expect(f.calls).toContain("remove:c1"); expect(f.calls).not.toContain("analyse"); expect(u.readyIds()).toEqual([]);
  });
  it("removing a ready clip deletes it on the server and forgets it", async () => {
    const f = fake(); const u = new ClipUploader(f.deps); const key = u.add(input()); await settle(u);
    u.remove(key); expect(u.snapshot().items).toEqual([]); expect(f.calls).toContain("remove:c1"); expect(u.readyIds()).toEqual([]);
  });
  it("only ready clips are ever offered to the video, in the order added", async () => {
    const f = fake({ slot: [{ kind: "slot", id: "c1", url: "https://b.s3.amazonaws.com/", fields: {} }, { kind: "refused", failure: { kind: "quota", retry: false } }, { kind: "slot", id: "c3", url: "https://b.s3.amazonaws.com/", fields: {} }], get: [{ ok: true, clip: readyClip("c1") }, { ok: true, clip: readyClip("c3") }] });
    const u = new ClipUploader(f.deps); u.add(input()); u.add(input()); u.add(input()); await settle(u);
    expect(u.snapshot().items.map((i) => i.state)).toEqual(["ready", "failed", "ready"]); expect(u.readyIds()).toEqual(["c1", "c3"]);
  });
  it("a recent clip is added without any upload, once", () => {
    const f = fake(); const u = new ClipUploader(f.deps);
    expect(u.addReady(readyClip("r1"))).toBeTruthy(); expect(u.addReady(readyClip("r1"))).toBeNull();
    expect(u.readyIds()).toEqual(["r1"]); expect(f.calls).toEqual([]);
  });
  it("a request that is sent twice with the same ready clips has the same key (create stays idempotent): ids are stable", () => {
    const a = JSON.stringify(videoAssetsExtra(["c1", "c2"], 4)), b = JSON.stringify(videoAssetsExtra(["c1", "c2", "c1"], 4));
    expect(a).toBe(b);
  });
  it("the screen-reader line changes with the state, not with the progress", () => {
    const base = { name: "", pct: 0, useAudio: false, bytes: 1, slow: false } as const;
    expect(clipAnnouncementKey([{ ...base, key: "a", state: "uploading" }])).toBe(clipAnnouncementKey([{ ...base, key: "a", state: "uploading", pct: 80 }]));
    expect(clipAnnouncementKey([{ ...base, key: "a", state: "analysing" }])).not.toBe(clipAnnouncementKey([{ ...base, key: "a", state: "uploading" }]));
    expect(clipAnnouncementKey([{ ...base, key: "a", state: "ready" }]).startsWith("ready")).toBe(true);
    expect(clipAnnouncementKey([])).toBe("");
  });
});
