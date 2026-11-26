import { describe, expect, it } from "vitest";
import { buildOptions, creditsFor, defaultForm, fourKAdvice, lengthLabel, normalize, overPlatformLimit, parseBrief, selectPlatform, FALLBACK_CAPS } from "./create";
import type { Capabilities } from "./create";

const caps: Capabilities = {
  aspects: [{ id: "16:9", label: "Landscape", ready: true }, { id: "9:16", label: "Vertical", ready: true, beta: true }, { id: "1:1", label: "Square", ready: false }],
  resolutions: [
    { id: "720p", label: "720p", credits_multiplier: 1, aspects: ["16:9", "9:16"] },
    { id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ["16:9", "9:16"] },
    { id: "2160p", label: "4K", credits_multiplier: 2, aspects: ["16:9"], note: "4K costs twice the credits." },
  ],
  platforms: [
    { id: "youtube", label: "YouTube", aspect: "16:9", resolution: "1080p", recommended_minutes: 3, max_minutes: null, supports_4k: true, note_4k: null },
    { id: "tiktok", label: "TikTok", aspect: "9:16", resolution: "1080p", recommended_minutes: 0.5, max_minutes: 3, supports_4k: false, note_4k: "TikTok publishes at 1080p; 4K would cost twice for no visible gain." },
    { id: "other", label: "Just a video", aspect: "16:9", resolution: "1080p", recommended_minutes: 1, max_minutes: null, supports_4k: true, note_4k: null },
  ],
  languages: [{ id: "en", label: "English" }, { id: "es", label: "Español" }],
  lengths: { min_minutes: 0.25, max_minutes: 12, presets: [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12] },
};

describe("price", () => {
  it("is started minutes, at least 1, times the multiplier (docs/CREATE_API.md)", () => {
    expect(creditsFor(0.25, "1080p", caps)).toBe(1);
    expect(creditsFor(1, "1080p", caps)).toBe(1);
    expect(creditsFor(1.01, "1080p", caps)).toBe(2);
    expect(creditsFor(3, "1080p", caps)).toBe(3);
    expect(creditsFor(3, "2160p", caps)).toBe(6);
    expect(creditsFor(0.5, "2160p", caps)).toBe(2);
    expect(creditsFor(12, "2160p", caps)).toBe(24);
  });
});

describe("form", () => {
  it("starts on the neutral platform with its recommendation", () => {
    const f = defaultForm(caps);
    expect(f).toMatchObject({ platform: "other", aspect: "16:9", resolution: "1080p", minutes: 1, captions: true, language: "auto" });
  });
  it("a platform preselects format, resolution and length", () => {
    const f = selectPlatform(defaultForm(caps), caps, "tiktok");
    expect(f).toMatchObject({ platform: "tiktok", aspect: "9:16", resolution: "1080p", minutes: 0.5 });
  });
  it("never keeps a pair the server does not offer: 4K is only 16:9 here", () => {
    const f = normalize({ ...defaultForm(caps), aspect: "9:16", resolution: "2160p" }, caps);
    expect(f.resolution).toBe("1080p");
    expect(normalize({ ...defaultForm(caps), aspect: "1:1" }, caps).aspect).toBe("16:9"); // not ready
    expect(normalize({ ...defaultForm(caps), minutes: 99 }, caps).minutes).toBe(12);
    expect(normalize({ ...defaultForm(caps), language: "fr" }, caps).language).toBe("auto");
  });
  it("saved choices apply but are normalised", () => {
    expect(defaultForm(caps, { platform: "tiktok", resolution: "2160p", aspect: "9:16" }).resolution).toBe("1080p");
  });
  it("4K on a platform that does not show 4K gets the server's recommendation, never a block", () => {
    const f = { ...selectPlatform(defaultForm(caps), caps, "tiktok") };
    expect(fourKAdvice(f, caps)).toBeNull();
    const four = { ...f, aspect: "16:9", resolution: "2160p" };
    expect(fourKAdvice(four, caps)).toMatch(/no visible gain/);
    expect(fourKAdvice({ ...four, platform: "youtube" }, caps)).toBeNull();
  });
  it("soft platform limit", () => {
    expect(overPlatformLimit({ ...defaultForm(caps), platform: "tiktok", minutes: 5 }, caps)).toBe(3);
    expect(overPlatformLimit({ ...defaultForm(caps), platform: "youtube", minutes: 12 }, caps)).toBeNull();
  });
  it("length labels use the same abbreviations in both languages", () => {
    expect([0.25, 0.5, 0.75, 1, 2, 12].map(lengthLabel)).toEqual(["15 s", "30 s", "45 s", "1 min", "2 min", "12 min"]);
  });
  it("options: everything when the server answered, only the length when it did not", () => {
    expect(buildOptions(defaultForm(caps), caps, true)).toEqual({ platform: "other", aspect: "16:9", resolution: "1080p", captions: true, language: "auto", target_minutes: 1 });
    expect(buildOptions(defaultForm(FALLBACK_CAPS), FALLBACK_CAPS, false)).toEqual({ target_minutes: 1 });
  });
});

describe("request check", () => {
  it("parses the five outcomes; unexpected means ok", () => {
    expect(parseBrief(200, { status: "ok", brief: { tone: "calm" } })).toEqual({ status: "ok", brief: { tone: "calm" } });
    expect(parseBrief(200, { status: "questions", questions: [{ id: "audience", text: "Who?", options: [{ id: "kids", label: "Kids" }], allow_other: true }] })).toMatchObject({ status: "questions" });
    expect(parseBrief(200, { status: "not_supported", message: "m", suggestion: "s" })).toEqual({ status: "not_supported", message: "m", suggestion: "s" });
    expect(parseBrief(200, { status: "blocked", message: "no" })).toEqual({ status: "blocked", message: "no" });
    expect(parseBrief(429, { status: "paused", message: "later", retry_after: 3600 })).toEqual({ status: "paused", message: "later", retryAfter: 3600 });
    expect(parseBrief(200, {})).toEqual({ status: "ok" });
    expect(parseBrief(200, { status: "questions", questions: [] })).toEqual({ status: "ok" });
    expect(parseBrief(200, { status: "questions", questions: [{ nope: 1 }] })).toEqual({ status: "ok" });
  });
});
