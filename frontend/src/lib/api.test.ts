import { describe, expect, it } from "vitest";
import { parseWallet, startOutcome } from "./api";

describe("what generate answered", () => {
  it("202: the video, and the optional note when the look was adapted", () => {
    expect(startOutcome(202, { message: "workflow started", video_id: "v1" })).toEqual({ ok: true, videoId: "v1", look: null });
    const r = startOutcome(202, { video_id: "v2", note: "Made from your photos: the Cartoon look is not used with your own photos.", look: { chosen: "cartoon", applied: "real", enforced: false, reason: "own_photos" } });
    expect(r).toMatchObject({ ok: true, videoId: "v2", look: { note: "Made from your photos: the Cartoon look is not used with your own photos.", applied: "real" } });
  });
  it("a plan refusal shows the server's own sentence and is never taken for an expired session", () => {
    expect(startOutcome(403, { code: "plan_length", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", plan: "free", requires_plan: "pro", can_upgrade: false }))
      .toEqual({ ok: false, kind: "plan", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", code: "plan_length", requiresPlan: "pro", canUpgrade: false });
    expect(startOutcome(403, { code: "plan_resolution", message: "4K is part of Max." })).toMatchObject({ kind: "plan", message: "4K is part of Max." });
    expect(startOutcome(403, { code: "free_not_available", message: "Free videos are made in the app." })).toMatchObject({ kind: "plan" });
    expect(startOutcome(429, { code: "free_budget_spent", message: "Free videos are done for today. Back tomorrow." })).toMatchObject({ kind: "plan", message: "Free videos are done for today. Back tomorrow.", canUpgrade: false });
    expect(startOutcome(403, {})).toMatchObject({ kind: "auth" });
    expect(startOutcome(401, null)).toMatchObject({ kind: "auth" });
  });
  it("the answers that were already there are unchanged", () => {
    expect(startOutcome(402, { message: "This video needs 6 credits and you have 5.", balance: 5, needed: 6 })).toMatchObject({ kind: "credits", balance: 5, needed: 6 });
    expect(startOutcome(400, { status: "blocked", message: "No." })).toMatchObject({ kind: "blocked", message: "No." });
    expect(startOutcome(429, { status: "paused", message: "Paused." })).toMatchObject({ kind: "paused" });
    expect(startOutcome(429, { message: "Slow down." })).toMatchObject({ kind: "quota", message: "Slow down." });
    expect(startOutcome(400, { message: "Unknown look", code: "bad_look" })).toMatchObject({ kind: "invalid", message: "Unknown look", code: "bad_look" });
    expect(startOutcome(409, { code: "deck_not_ready" })).toMatchObject({ kind: "invalid", code: "deck_not_ready" });
    expect(startOutcome(500, "x")).toMatchObject({ kind: "error" });
  });
});

describe("the wallet", () => {
  it("as before on a server without plans", () => {
    expect(parseWallet({ balance: 3, unlimited: false, buckets: [], next_daily_at: null })).toEqual({ balance: 3, unlimited: false, buckets: [], next_daily_at: null });
    expect(parseWallet({})).toBeNull();
  });
  it("carries the plan and what a Free account may do", () => {
    const w = parseWallet({ balance: 0, plan: { id: "free", name: "Free", limits: { max_seconds: 30 } }, free_creation: "welcome", free: { available: false, reason: "app_only", message: "Free videos are made in the app." }, can_upgrade: false })!;
    expect(w.plans).toMatchObject({ plan: { name: "Free", maxSeconds: 30 }, free: { available: false, reason: "app_only" }, canUpgrade: false });
  });
});
