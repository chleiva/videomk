import { describe, expect, it } from "vitest";
import { announcementKey, barHeight, BAR_COUNT, effectiveLimitS, feedbackReduce, formatTimer, initialFeedback, LevelMeter, MIN_BAR, rmsOfBytes, waitState, warningFor } from "./dictationFeedback";
import type { FeedbackEvent, FeedbackState } from "./dictationFeedback";

const run = (evs: FeedbackEvent[], from: FeedbackState = initialFeedback()) => evs.reduce(feedbackReduce, from);
const rec = (limitS = 360) => run([{ type: "request" }, { type: "granted", nowMs: 1000, limitS }]);

describe("level meter", () => {
  it("has a fixed bar count and silence is dots, not gaps", () => {
    const m = new LevelMeter(); const h = m.push(0);
    expect(h).toHaveLength(BAR_COUNT); expect(Math.min(...h)).toBeCloseTo(MIN_BAR); expect(Math.max(...h)).toBeLessThanOrEqual(1);
  });
  it("attack is fast, release is slow", () => {
    const m = new LevelMeter(); m.push(0.1); const up = m.heights().at(-1)!;
    expect(up).toBeGreaterThan(0.3);
    m.push(0.1); m.push(0.1); const loud = m.heights().at(-1)!; expect(loud).toBeGreaterThan(up);
    m.push(0); const down = m.heights().at(-1)!; expect(down).toBeLessThan(loud); expect(down).toBeGreaterThan(MIN_BAR + (loud - MIN_BAR) * 0.4);
  });
  it("nothing jitters on constant input; a loud frame raises the newest bar", () => {
    const m = new LevelMeter(); for (let i = 0; i < 60; i++) m.push(0.2);
    const h = m.heights(); expect(new Set(h.map((x) => x.toFixed(3))).size).toBe(1);
    m.push(1); expect(m.heights().at(-1)!).toBeGreaterThan(h.at(-1)!);
  });
  it("is deterministic and clamps bad input", () => {
    const a = new LevelMeter(), b = new LevelMeter(); for (const x of [0, 0.3, NaN, 5, -1, 0.1]) { a.push(x); b.push(x); }
    expect(a.heights()).toEqual(b.heights()); expect(Math.max(...a.heights())).toBeLessThanOrEqual(1);
    expect(barHeight(1)).toBe(1); expect(barHeight(0)).toBeCloseTo(MIN_BAR);
  });
  it("rms of 8-bit samples: 128 is silence", () => {
    expect(rmsOfBytes(new Uint8Array(100).fill(128))).toBe(0); expect(rmsOfBytes(new Uint8Array([0, 255, 0, 255]))).toBeGreaterThan(0.9); expect(rmsOfBytes([])).toBe(0);
  });
});

describe("phase machine", () => {
  it("happy path", () => {
    let s = rec(); expect(s.phase).toBe("recording");
    s = run([{ type: "stop", nowMs: 5000 }], s); expect(s.phase).toBe("transcribing");
    s = run([{ type: "ok" }], s); expect(s.phase).toBe("inserted");
    expect(run([{ type: "dismiss" }], s).phase).toBe("idle");
  });
  it("denied and cancel go back to idle; cancel works while transcribing", () => {
    expect(run([{ type: "request" }, { type: "denied" }]).phase).toBe("idle");
    expect(run([{ type: "cancel" }], rec()).phase).toBe("idle");
    expect(run([{ type: "stop", nowMs: 2000 }, { type: "cancel" }], rec()).phase).toBe("idle");
  });
  it("failure then retry restarts the wait clock", () => {
    let s = run([{ type: "stop", nowMs: 2000 }, { type: "fail", kind: "network" }], rec());
    expect(s.phase).toBe("failed"); expect(s.failure).toBe("network");
    s = run([{ type: "retry", nowMs: 9000 }], s); expect(s.phase).toBe("transcribing"); expect(s.waitStartMs).toBe(9000); expect(s.failure).toBeNull();
  });
  it("ignores impossible events", () => {
    expect(run([{ type: "stop", nowMs: 1 }]).phase).toBe("idle"); expect(run([{ type: "ok" }], rec()).phase).toBe("recording");
    expect(run([{ type: "request" }], rec()).phase).toBe("recording");
  });
});

describe("timer and thresholds", () => {
  it("formats m:ss", () => { expect(formatTimer(0)).toBe("0:00"); expect(formatTimer(7)).toBe("0:07"); expect(formatTimer(65)).toBe("1:05"); expect(formatTimer(359.9)).toBe("5:59"); expect(formatTimer(-3)).toBe("0:00"); });
  it("elapsed follows ticks and never goes backwards", () => {
    let s = run([{ type: "tick", nowMs: 4600 }], rec()); expect(warningFor(s).remainingS).toBe(360 - 3);
    s = run([{ type: "tick", nowMs: 2000 }], s); expect(s.nowMs).toBe(4600);
  });
  it("warns at 30 s and 10 s before the limit", () => {
    const at = (sec: number) => warningFor(run([{ type: "tick", nowMs: 1000 + sec * 1000 }], rec(360)));
    expect(at(329).level).toBe("none"); expect(at(330).level).toBe("soon"); expect(at(349).level).toBe("soon");
    expect(at(350).level).toBe("final"); expect(at(350).remainingS).toBe(10); expect(at(400).remainingS).toBe(0);
  });
  it("the daily allowance can be nearer than the clip limit", () => {
    expect(effectiveLimitS(360, 45)).toBe(45); expect(effectiveLimitS(360, 5000)).toBe(360); expect(effectiveLimitS(360, null)).toBe(360); expect(effectiveLimitS(360, -4)).toBe(0);
    expect(warningFor(rec(effectiveLimitS(360, 45))).level).toBe("none");
    expect(warningFor(run([{ type: "tick", nowMs: 21000 }], rec(effectiveLimitS(360, 45)))).level).toBe("soon");
  });
  it("transcribing: normal, slow after 8 s, timeout after 60 s", () => {
    const w = (sec: number) => waitState(run([{ type: "tick", nowMs: 2000 + sec * 1000 }], run([{ type: "stop", nowMs: 2000 }], rec())));
    expect(w(7)).toBe("normal"); expect(w(8)).toBe("slow"); expect(w(59)).toBe("slow"); expect(w(60)).toBe("timeout");
    expect(waitState(rec())).toBe("normal");
  });
  it("announcements change only at thresholds", () => {
    const key = (sec: number) => announcementKey(run([{ type: "tick", nowMs: 1000 + sec * 1000 }], rec(360)));
    expect(key(1)).toBe(key(100)); expect(key(335)).toBe("warn_soon"); expect(key(355)).toBe("warn_final"); expect(key(358)).toBe(key(355));
    expect(announcementKey(initialFeedback())).toBeNull();
  });
});
