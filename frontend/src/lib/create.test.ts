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

// ---------------------------------------------------------------- the web redesign: pills, quality, look, scenes, watermark, photos
import { lengthMenu, mediaExtras, minutesForPhotos, parseWatermarkCaps, photoCapacity, pillValues, qualityChoices } from "./create";

describe("pills and menus", () => {
  it("For shows the platform (the neutral one reads as the 'other' label), Length shows the chosen length", () => {
    const f = defaultForm(caps);
    expect(pillValues(f, caps, "Video")).toEqual({ for: "Video", length: "1 min", look: "auto" });
    expect(pillValues(selectPlatform(f, caps, "youtube"), caps, "Video")).toMatchObject({ for: "YouTube", length: "3 min" });
  });
  it("the Length menu prices every preset and greys the ones over the platform's soft limit", () => {
    const f = selectPlatform(defaultForm(caps), caps, "tiktok");
    const rows = lengthMenu(caps, f);
    expect(rows.find((r) => r.minutes === 0.5)).toEqual({ minutes: 0.5, credits: 1, over: false });
    expect(rows.find((r) => r.minutes === 5)).toEqual({ minutes: 5, credits: 5, over: true });
    expect(lengthMenu(caps, { platform: "youtube", resolution: "2160p" }).find((r) => r.minutes === 3)).toMatchObject({ credits: 6, over: false });
  });
});

describe("quality", () => {
  it("4K is offered on YouTube and the neutral platform, not where the platform does not show it", () => {
    expect(qualityChoices(caps, { aspect: "16:9", platform: "youtube" }).map((r) => r.id)).toEqual(["720p", "1080p", "2160p"]);
    expect(qualityChoices(caps, { aspect: "16:9", platform: "tiktok" }).map((r) => r.id)).toEqual(["720p", "1080p"]);
    expect(qualityChoices(caps, { aspect: "9:16", platform: "other" }).map((r) => r.id)).toEqual(["720p", "1080p"]);   // the aspect decides too
  });
  it("switching to a platform without 4K drops a 4K choice to the platform's resolution", () => {
    const yt = { ...selectPlatform(defaultForm(caps), caps, "youtube"), resolution: "2160p" };
    expect(selectPlatform(yt, caps, "tiktok").resolution).toBe("1080p");
    expect(normalize({ ...yt, platform: "other" }, caps).resolution).toBe("2160p");
  });
});

describe("look, scenes and watermark in the request", () => {
  const wcaps = { ...caps, watermark: { modes: [{ id: "none" as const, label: "None", available: true }, { id: "videomk" as const, label: "videomk", available: true }, { id: "custom" as const, label: "Your logo (Pro)", available: false, requires: "premium" }], forced: false, premium: false } };
  it("nothing extra is sent for the defaults (auto look, auto scenes, saved watermark)", () => {
    expect(buildOptions(defaultForm(wcaps), wcaps, true)).toEqual({ platform: "other", aspect: "16:9", resolution: "1080p", captions: true, language: "auto", target_minutes: 1 });
  });
  it("look sends theme; Illustrated sends style cartoon, Real sends style real; a changed watermark sends its mode", () => {
    const f = { ...defaultForm(wcaps), look: "paper" as const, scenes: "cartoon" as const, watermark: "videomk" as const };
    expect(buildOptions(f, wcaps, true)).toMatchObject({ theme: "paper", style: "cartoon", watermark: { mode: "videomk" } });
    expect(buildOptions({ ...f, scenes: "real" }, wcaps, true)).toMatchObject({ style: "real" });
  });
  it("a watermark mode the account cannot use (locked) or the server does not list is dropped", () => {
    expect(normalize({ ...defaultForm(wcaps), watermark: "custom" }, wcaps).watermark).toBeNull();
    expect(normalize({ ...defaultForm(caps), watermark: "videomk" }, caps).watermark).toBeNull();
    expect(buildOptions({ ...defaultForm(caps), watermark: "videomk" }, caps, true)).not.toHaveProperty("watermark");
  });
  it("capabilities.watermark is parsed defensively", () => {
    expect(parseWatermarkCaps(undefined)).toBeUndefined();
    expect(parseWatermarkCaps({ modes: [{ id: "bogus", label: "x" }] })).toBeUndefined();
    expect(parseWatermarkCaps({ modes: [{ id: "videomk", label: "videomk" }], forced: true })).toEqual({ modes: [{ id: "videomk", label: "videomk", available: true, requires: undefined }], forced: true, premium: false });
  });
});

describe("photos in a video", () => {
  it("about 51 photos fit per minute; the hint finds the shortest preset that holds them", () => {
    expect(photoCapacity(1)).toBe(51); expect(photoCapacity(2)).toBe(102);
    expect(minutesForPhotos(100, caps)).toBe(2); expect(minutesForPhotos(40, caps)).toBe(1); expect(minutesForPhotos(900, caps)).toBeNull();
  });
  it("the body carries direct ids as media, My media ids as library_media, at most 100 together, dates only for direct ones", () => {
    const direct = Array.from({ length: 60 }, (_, i) => `d${i}`), lib = Array.from({ length: 60 }, (_, i) => `l${i}`);
    const e = mediaExtras(direct, lib, { d0: { taken: "2024-07-14T10:00:00", lat: 7.88, lon: 98.39 }, l0: { taken: "x" } }) as any;
    expect(e.media).toHaveLength(60); expect(e.library_media).toHaveLength(40);
    expect(e.media_meta).toEqual({ d0: { taken: "2024-07-14T10:00:00", lat: 7.88, lon: 98.39 } });
    expect(mediaExtras([], [])).toEqual({});
    expect((mediaExtras(["a"], ["a", "b"]) as any).library_media).toEqual(["b"]);   // a photo is never sent twice
  });
});
