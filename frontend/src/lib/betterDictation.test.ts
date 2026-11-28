import { describe, expect, it, vi } from "vitest";
import { betterAvailable, betterErrorKey, betterPreferred, DictationIds, dictationOutcome, parseDictationCaps, placeBetterText, setBetterPreferred, showUpgradeHint, startBetter } from "./betterDictation";

const hex = (n: number) => n.toString(16).padStart(32, "0");
const caps = { premium: true, available: true, paused: false, seconds_per_day: 600, seconds_left_today: 540, max_clip_seconds: 360, max_clip_bytes: 3145728, requires_plan: null, provider: "openai" };

describe("capabilities", () => {
  it("reads the block and clamps limits", () => {
    expect(parseDictationCaps(caps)).toMatchObject({ premium: true, available: true, secondsLeft: 540, maxClipSeconds: 360, maxClipBytes: 3145728 });
    expect(parseDictationCaps({ ...caps, max_clip_seconds: 9999 })!.maxClipSeconds).toBe(360);
    expect(parseDictationCaps(undefined)).toBeUndefined();
    expect(parseDictationCaps("x")).toBeUndefined();
  });
  it("available only when not paused; the hint only for a plan without it", () => {
    expect(betterAvailable(parseDictationCaps(caps))).toBe(true);
    expect(betterAvailable(parseDictationCaps({ ...caps, paused: true }))).toBe(false);
    expect(betterAvailable(parseDictationCaps({ ...caps, available: false }))).toBe(false);
    expect(betterAvailable(undefined)).toBe(false);
    expect(showUpgradeHint(parseDictationCaps({ ...caps, premium: false, available: false, requires_plan: "pro" }))).toBe(true);
    expect(showUpgradeHint(parseDictationCaps({ ...caps, available: false }))).toBe(false);   // premium, quota used: no upgrade nag
  });
  it("the preference defaults to on and remembers off", () => {
    const m = new Map<string, string>(); const st = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
    expect(betterPreferred(st)).toBe(true); setBetterPreferred(false, st); expect(betterPreferred(st)).toBe(false); setBetterPreferred(true, st); expect(betterPreferred(st)).toBe(true);
  });
});

describe("id bookkeeping", () => {
  it("keeps ids, no repeats, no junk, at most 20 (newest kept), nothing when empty", () => {
    const ids = new DictationIds();
    expect(ids.extra()).toEqual({});
    ids.add(hex(1)); ids.add(hex(1)); ids.add("nope");
    expect(ids.extra()).toEqual({ dictation_ids: [hex(1)] });
    for (let i = 2; i <= 25; i++) ids.add(hex(i));
    expect(ids.list()).toHaveLength(20); expect(ids.list()[0]).toBe(hex(6)); expect(ids.list().at(-1)).toBe(hex(25));
    ids.clear(); expect(ids.list()).toEqual([]);
  });
});

describe("server answers", () => {
  it("success", () => expect(dictationOutcome(200, { id: hex(1), text: "hola", seconds: 3, seconds_left_today: 500 })).toEqual({ ok: true, id: hex(1), text: "hola", seconds: 3, secondsLeft: 500 }));
  it.each([
    [403, { code: "dictation_plan" }, "plan"], [429, { code: "dictation_quota" }, "quota"], [413, { code: "dictation_too_long" }, "too_long"], [502, { code: "dictation_failed" }, "failed"],
    [503, { code: "dictation_paused" }, "paused"], [400, { code: "bad_audio" }, "bad_audio"], [401, { message: "x" }, "auth"], [500, null, "failed"], [200, { nothing: 1 }, "failed"],
  ])("%i %j -> %s", (status, body, kind) => expect(dictationOutcome(status, body)).toMatchObject({ ok: false, kind }));
  it("only quota, too long and failures say something; plan and paused fall back silently", () => {
    expect(betterErrorKey("quota")).toBe("create.better_quota");
    expect(betterErrorKey("failed")).toBe("create.better_failed"); expect(betterErrorKey("network")).toBe("create.better_failed");
    expect(betterErrorKey("plan")).toBeNull(); expect(betterErrorKey("paused")).toBeNull(); expect(betterErrorKey("auth")).toBeNull();
  });
});

describe("where the text goes", () => {
  it("replaces the native preview with the better text on top of the base", () => expect(placeBetterText("Make it fun.", "Make it fun. a video abot bees", "Make it fun. a video abot bees", "A video about bees")).toBe("Make it fun. A video about bees"));
  it("appends when there was no preview", () => expect(placeBetterText("Hi", "Hi", "Hi", "there")).toBe("Hi there"));
  it("never overwrites a field edited by hand", () => expect(placeBetterText("a", "a b", "a b EDITED", "better")).toBeNull());
  it("empty text changes nothing", () => expect(placeBetterText("a", "a", "a", "  ")).toBeNull());
});

/** A fake MediaRecorder and microphone: tests drive it by hand. */
function rig(over: Partial<any> = {}) {
  const stops: string[] = []; let field = "start"; const writes: string[] = [];
  const tracks = [{ stop: () => stops.push("track") }];
  class Rec {
    static isTypeSupported = (m: string) => m === "audio/webm;codecs=opus";
    state = "inactive"; mimeType = "audio/webm;codecs=opus"; ondataavailable: any; onstop: any; opts: any;
    constructor(public stream: any, opts: any) { this.opts = opts; made.push(this); }
    start() { this.state = "recording"; this.ondataavailable({ data: new Blob([new Uint8Array(2000)]) }); }
    stop() { this.state = "inactive"; queueMicrotask(() => this.onstop()); }
  }
  const made: Rec[] = [];
  let nativeOpts: any = null;
  const timers: { f: () => void; ms: number }[] = [];
  let t = 1000;
  const send = vi.fn(async () => ({ ok: true as const, id: hex(7), text: "Better words", seconds: 4, secondsLeft: 100 }));
  const results: any[] = [];
  const opts = {
    lang: "en-US", languages: ["en"], getText: () => field, setText: (x: string) => { field = x; writes.push(x); }, maxSeconds: 360, maxBytes: 3145728,
    onWorking: vi.fn(), onResult: (r: any) => results.push(r),
    deps: {
      getUserMedia: async () => ({ getTracks: () => tracks }) as any, Recorder: Rec, send,
      native: (o: any) => { nativeOpts = o; return { stop: () => { queueMicrotask(() => o.onEnd("done")); } }; },
      setTimer: (f: () => void, ms: number) => { timers.push({ f, ms }); return timers.length; }, clearTimer: () => {}, now: () => t, ...over,
    },
  };
  return { opts, made, send, results, stops, writes, timers, native: () => nativeOpts, field: () => field, advance: (s: number) => { t += s * 1000; } };
}
const settle = () => new Promise((r) => setTimeout(r, 0));

describe("recording flow (fake MediaRecorder, fake fetch)", () => {
  it("records mono-friendly opus, uploads on stop, replaces the preview, returns the id", async () => {
    const r = rig();
    const h = await startBetter(r.opts as any);
    expect(r.made[0].opts).toMatchObject({ mimeType: "audio/webm;codecs=opus", audioBitsPerSecond: 32000 });
    r.native().setText("start a vid abot bees");   // the live preview
    r.advance(12);
    h!.stop(); await settle();
    expect(r.opts.onWorking).toHaveBeenCalled();
    expect(r.send).toHaveBeenCalledTimes(1);
    const sent = (r.send.mock.calls[0] as any)[0];
    expect(sent).toMatchObject({ mime: "audio/webm;codecs=opus", seconds: 12, languages: ["en"], prompt: "start" });
    expect(r.field()).toBe("start Better words");
    expect(r.results).toEqual([{ id: hex(7), limit: false }]);
    expect(r.stops).toContain("track");
  });
  it("a server error keeps the native text and reports the kind", async () => {
    const r = rig({ send: async () => ({ ok: false, kind: "quota" }) });
    const h = await startBetter(r.opts as any);
    r.native().setText("start native words");
    h!.stop(); await settle();
    expect(r.field()).toBe("start native words");
    expect(r.results).toEqual([{ kind: "quota", limit: false }]);
  });
  it("a field edited by hand while recording is not touched, but the paid id is kept", async () => {
    const r = rig();
    const h = await startBetter(r.opts as any);
    r.native().setText("start heard");
    r.opts.setText("start heard and typed");
    h!.stop(); await settle();
    expect(r.field()).toBe("start heard and typed");
    expect(r.results[0].id).toBe(hex(7));
  });
  it("stops by itself at the limit and says so", async () => {
    const r = rig();
    await startBetter(r.opts as any);
    expect(r.timers[0].ms).toBe(360_000);
    r.advance(360); r.timers[0].f(); await settle();
    expect(r.results[0]).toMatchObject({ id: hex(7), limit: true });
  });
  it("a clip over the byte limit is not uploaded", async () => {
    const r = rig(); r.opts.maxBytes = 100;
    const h = await startBetter(r.opts as any); h!.stop(); await settle();
    expect(r.send).not.toHaveBeenCalled(); expect(r.results[0]).toMatchObject({ kind: "too_long" });
  });
  it("a blocked microphone reports denied and uploads nothing", async () => {
    const r = rig({ getUserMedia: async () => { throw new Error("no"); } });
    await startBetter(r.opts as any);
    expect(r.results).toEqual([{ denied: true }]); expect(r.send).not.toHaveBeenCalled();
  });
  it("works without a native engine (Firefox): plain append", async () => {
    const r = rig({ native: () => null });
    const h = await startBetter(r.opts as any); h!.stop(); await settle();
    expect(r.field()).toBe("start Better words");
  });
});

describe("feedback controls: cancel, retry, timeout", () => {
  it("cancel while recording discards the clip, restores the box and uploads nothing", async () => {
    const r = rig();
    const h = await startBetter(r.opts as any);
    r.native().setText("start heard words");
    h!.cancel(); await settle();
    expect(r.send).not.toHaveBeenCalled(); expect(r.field()).toBe("start"); expect(r.results).toEqual([{ cancelled: true }]); expect(r.stops).toContain("track");
  });
  it("cancel while transcribing stops waiting; a late answer is ignored and the phone's words stay", async () => {
    let resolve!: (v: any) => void;
    const r = rig({ send: () => new Promise((x) => { resolve = x; }) });
    const h = await startBetter(r.opts as any);
    r.native().setText("start native"); h!.stop(); await settle();
    h!.cancel(); resolve({ ok: true, id: hex(7), text: "late", seconds: 1, secondsLeft: 1 }); await settle();
    expect(r.field()).toBe("start native"); expect(r.results).toEqual([{ cancelled: true }]);
  });
  it("a retryable failure keeps the clip; retry resends it and succeeds", async () => {
    const answers: any[] = [{ ok: false, kind: "network" }, { ok: true, id: hex(7), text: "Better words", seconds: 4, secondsLeft: 1 }];
    const sendSpy = vi.fn(async () => answers.shift()); const r = rig({ send: sendSpy });
    const failed: string[] = []; (r.opts as any).onRetryable = (k: string) => failed.push(k);
    const h = await startBetter(r.opts as any);
    h!.stop(); await settle();
    expect(failed).toEqual(["network"]); expect(r.results).toEqual([]);
    h!.retry(); await settle();
    expect(sendSpy).toHaveBeenCalledTimes(2); expect(r.opts.onWorking).toHaveBeenCalledTimes(2);
    expect(r.field()).toBe("start Better words"); expect(r.results).toEqual([{ id: hex(7), limit: false }]);
  });
  it("dismiss after a failure ends with the phone's text and the error kind", async () => {
    const r = rig({ send: async () => ({ ok: false, kind: "failed" }) });
    (r.opts as any).onRetryable = () => {};
    const h = await startBetter(r.opts as any);
    r.native().setText("start native"); h!.stop(); await settle(); h!.dismiss();
    expect(r.field()).toBe("start native"); expect(r.results).toEqual([{ kind: "failed", limit: false }]);
  });
  it("quota is never retryable, even with onRetryable", async () => {
    const r = rig({ send: async () => ({ ok: false, kind: "quota" }) });
    (r.opts as any).onRetryable = () => { throw new Error("no"); };
    const h = await startBetter(r.opts as any); h!.stop(); await settle();
    expect(r.results).toEqual([{ kind: "quota", limit: false }]);
  });
  it("an upload that never answers times out into a retryable failure", async () => {
    const r = rig({ send: () => new Promise(() => {}) });
    const failed: string[] = []; (r.opts as any).onRetryable = (k: string) => failed.push(k);
    const h = await startBetter(r.opts as any); h!.stop(); await settle();
    const t = r.timers.find((x) => x.ms === 60000)!; t.f();
    expect(failed).toEqual(["network"]);
  });
});
