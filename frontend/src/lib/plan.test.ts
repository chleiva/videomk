import { describe, expect, it } from "vitest";
import { NO_PLAN, createLock, lengthLock, parseGallery, parseLengthLimits, parsePlanState, planName, planRefusal } from "./plan";

const FREE = { plan: { id: "free", name: "Free", limits: { max_seconds: 30, resolutions: ["720p", "1080p"] }, plans: [{ id: "free", name: "Free" }, { id: "pro", name: "Pro" }, { id: "max", name: "Max" }] }, free_creation: "welcome", free: { available: true, credits_left: 2 }, can_upgrade: false };

describe("the plan in capabilities and the wallet", () => {
  it("a server without plans sends nothing: no plan, no limits, nothing locked", () => {
    for (const b of [undefined, null, {}, "x", { balance: 3 }]) expect(parsePlanState(b)).toEqual(NO_PLAN);
    expect(parseLengthLimits({ min_minutes: 0.25, max_minutes: 12, presets: [1] })).toEqual({ planMaxSeconds: null, locked: [] });
    expect(lengthLock(12, undefined)).toBe(false);
  });
  it("reads the name, the longest video, the plans' names and can_upgrade", () => {
    const s = parsePlanState(FREE);
    expect(s.plan).toMatchObject({ id: "free", name: "Free", maxSeconds: 30, resolutions: ["720p", "1080p"] });
    expect(s.free).toMatchObject({ available: true }); expect(s.freeCreation).toBe("welcome"); expect(s.canUpgrade).toBe(false);
    expect(planName(s, "pro")).toBe("Pro"); expect(planName(s, "max")).toBe("Max");
    expect(planName(NO_PLAN, "studio")).toBe("Studio");   // a plan the server did not name: its id with a capital
    expect(planName(s, null)).toBeNull();
    expect(parsePlanState({ plan: { id: "pro" } }).plan!.name).toBe("Pro");
  });
  it("lengths over the plan's longest video are locked, with the cheapest plan that makes them", () => {
    const lim = parseLengthLimits({ plan_max_seconds: 30, locked: [{ over_seconds: 300, max_seconds: 720, requires_plan: "max" }, { over_seconds: 30, max_seconds: 300, requires_plan: "pro" }] });
    expect(lengthLock(0.25, lim)).toBe(false); expect(lengthLock(0.5, lim)).toBe(false);
    expect(lengthLock(0.75, lim)).toEqual({ requires: "pro" }); expect(lengthLock(5, lim)).toEqual({ requires: "pro" });
    expect(lengthLock(8, lim)).toEqual({ requires: "max" }); expect(lengthLock(12, lim)).toEqual({ requires: "max" });
    expect(lengthLock(2, parseLengthLimits({ plan_max_minutes: 1 }))).toEqual({ requires: null });   // only the limit is known: locked, no plan named
    expect(lengthLock(2, parseLengthLimits({ locked: [{ over_seconds: 60, requires_plan: "pro" }] }))).toEqual({ requires: "pro" });
    expect(parseLengthLimits({ locked: [null, { over_seconds: "x" }, "y"] }).locked).toEqual([]);
  });
});

describe("refusals that come from the plan (nothing was charged; the server's sentence is shown, the draft stays)", () => {
  it("403 plan_* and free_not_available, 429 free_budget_spent and free_monthly_cap", () => {
    expect(planRefusal(403, { code: "plan_length", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", requires_plan: "pro", can_upgrade: false }))
      .toEqual({ code: "plan_length", message: "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", requiresPlan: "pro", canUpgrade: false });
    for (const code of ["plan_resolution", "plan_photos", "plan_watermark", "plan_something_new", "watermark_premium", "free_not_available"]) expect(planRefusal(403, { code })?.code).toBe(code);
    expect(planRefusal(429, { code: "free_budget_spent", message: "Free videos are done for today.", resumes_at: "2026-11-29T00:00:00Z" })).toMatchObject({ code: "free_budget_spent", message: "Free videos are done for today." });
    expect(planRefusal(429, { code: "free_monthly_cap" })).not.toBeNull();
  });
  it("anything else is not a plan refusal: an expired session, a safety pause, a bad request", () => {
    expect(planRefusal(403, {})).toBeNull(); expect(planRefusal(403, null)).toBeNull();
    expect(planRefusal(429, { status: "paused" })).toBeNull();
    expect(planRefusal(400, { code: "plan_length" })).toBeNull();
    expect(planRefusal(402, { code: "insufficient_credits" })).toBeNull();
  });
});

describe("Create is locked only for a Free account that cannot make a video and has nothing to spend", () => {
  const state = (free: any, extra: any = {}) => parsePlanState({ ...FREE, free, ...extra });
  const off = { available: false, reason: "app_only", message: "Free videos are made in the VideoMK app." };
  it("no plans on the server: never locked", () => {
    expect(createLock({ balance: 0, unlimited: false }, undefined)).toBeNull();
    expect(createLock(null, NO_PLAN)).toBeNull();
  });
  it("free creation not available here and no credits: locked, with the server's sentence", () => {
    expect(createLock({ balance: 0, unlimited: false, plans: state(off) }, undefined)).toEqual({ message: "Free videos are made in the VideoMK app.", reason: "app_only", resumesAt: undefined });
    expect(createLock({ balance: 0, unlimited: false }, state({ available: false, reason: "off" }, { free_creation: "none" }))).toMatchObject({ reason: "off" });
    expect(createLock({ balance: 0, unlimited: false }, parsePlanState({ plan: { id: "free" }, free_creation: "none" }))).toMatchObject({ reason: "off" });   // no `free` object: free_creation none says it
    expect(createLock({ balance: 0, unlimited: false }, state({ available: false, reason: "paused", message: "Back tomorrow.", resumes_at: "2026-11-29T00:00:00Z" }))).toEqual({ message: "Back tomorrow.", reason: "paused", resumesAt: "2026-11-29T00:00:00Z" });
  });
  it("credits to spend, a paid plan, an unlimited account or free creation available: Create works", () => {
    expect(createLock({ balance: 3, unlimited: false, plans: state(off) }, undefined)).toBeNull();
    expect(createLock({ balance: 0, unlimited: true, plans: state(off) }, undefined)).toBeNull();
    expect(createLock({ balance: 0, unlimited: false, plans: parsePlanState({ plan: { id: "pro" }, free: off }) }, undefined)).toBeNull();
    expect(createLock({ balance: 0, unlimited: false, plans: state({ available: true }) }, undefined)).toBeNull();
  });
  it("the wallet's view wins over capabilities (the wallet is what grants the welcome credits)", () => {
    expect(createLock({ balance: 0, unlimited: false, plans: state({ available: true }) }, state(off))).toBeNull();
  });
});

describe("the showcase (GET /gallery)", () => {
  it("keeps what can be played, drops the rest, and an empty list is a valid answer", () => {
    const g = parseGallery({ videos: [{ id: "forest", title: "How a forest breathes", aspect: "16:9", seconds: 28, video_url: "https://cdn/x.mp4", poster_url: "https://cdn/x.jpg" }, { id: "no-url" }, { id: "bad", video_url: "javascript:x" }, { id: "tall", title: "", aspect: "tall", video_url: "https://cdn/y.mp4", poster_url: null }], count: 4 });
    expect(g).toEqual([{ id: "forest", title: "How a forest breathes", video_url: "https://cdn/x.mp4", poster_url: "https://cdn/x.jpg", aspect: "16:9", seconds: 28 }, { id: "tall", title: "", video_url: "https://cdn/y.mp4", poster_url: null, aspect: null, seconds: null }]);
    expect(parseGallery({ videos: [] })).toEqual([]); expect(parseGallery(null)).toEqual([]); expect(parseGallery({})).toEqual([]);
  });
});
