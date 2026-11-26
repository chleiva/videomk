import { describe, expect, it } from "vitest";
import en from "../i18n/en.json";
import es from "../i18n/es.json";
import { FALLBACK_CAPS, parseDeckCaps } from "./create";
import type { Capabilities } from "./create";
import { acceptAttr, checkFile, deckCredits, deckGenerateExtras, deckAspectWarning, deckMinutes, deckReducer, isExpectedS3Url, parseDeckStatus, pollDelayMs, pollExpired, POLL_GIVE_UP_MS, problemFor } from "./deck";
import type { DeckState } from "./deck";
import { makingInfo, normalizeItem } from "./videos";

const caps = { max_mb: 50, max_slides: 60, formats: ["pptx", "pdf"] };
const MB = 1024 * 1024;
const PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation";

describe("capabilities.deck", () => {
  it("is parsed only when well formed; absent hides the feature", () => {
    expect(parseDeckCaps(caps)).toEqual(caps);
    expect(parseDeckCaps(undefined)).toBeUndefined();
    expect(parseDeckCaps({ max_mb: 50, max_slides: 60, formats: [] })).toBeUndefined();
    expect(parseDeckCaps({ max_mb: 0, max_slides: 60, formats: ["pdf"] })).toBeUndefined();
    expect(parseDeckCaps({ max_mb: 50, max_slides: 60, formats: ["pdf", "exe"] })?.formats).toEqual(["pdf"]);
    expect(FALLBACK_CAPS.deck).toBeUndefined();
  });
  it("accept lists extensions and MIME types of the offered formats only", () => {
    expect(acceptAttr(caps)).toBe(`.pptx,${PPTX},.pdf,application/pdf`);
    expect(acceptAttr({ ...caps, formats: ["pdf"] })).toBe(".pdf,application/pdf");
  });
});

describe("local file checks", () => {
  it("accepts pptx and pdf by extension, with the right, empty or generic MIME", () => {
    expect(checkFile({ name: "Q3.PPTX", size: 5 * MB, type: PPTX }, caps)).toEqual({ ok: true, format: "pptx" });
    expect(checkFile({ name: "deck.pdf", size: 5 * MB, type: "" }, caps)).toEqual({ ok: true, format: "pdf" });
    expect(checkFile({ name: "deck.pdf", size: 5 * MB, type: "application/octet-stream" }, caps)).toEqual({ ok: true, format: "pdf" });
  });
  it("refuses the wrong size, extension, empty file and a MIME that disagrees", () => {
    expect(checkFile({ name: "a.pptx", size: 51 * MB, type: PPTX }, caps)).toEqual({ ok: false, problem: "too_large" });
    expect(checkFile({ name: "a.pptx", size: 50 * MB, type: PPTX }, caps).ok).toBe(true);
    expect(checkFile({ name: "a.pptx", size: 0, type: PPTX }, caps)).toEqual({ ok: false, problem: "empty" });
    expect(checkFile({ name: "a.docx", size: 10, type: "" }, caps)).toEqual({ ok: false, problem: "unsupported" });
    expect(checkFile({ name: "noext", size: 10 }, caps)).toEqual({ ok: false, problem: "unsupported" });
    expect(checkFile({ name: "a.pdf", size: 10, type: PPTX }, caps)).toEqual({ ok: false, problem: "unsupported" });
    expect(checkFile({ name: "a.pdf", size: 10, type: "" }, { ...caps, formats: ["pptx"] })).toEqual({ ok: false, problem: "unsupported" });
  });
  it("legacy and macro formats get the 'export it' advice, not a bare refusal", () => {
    for (const n of ["a.ppt", "a.pptm", "a.key", "a.odp"]) expect(checkFile({ name: n, size: 10 }, caps)).toEqual({ ok: false, problem: "export_first" });
  });
});

describe("error mapping", () => {
  const codes = ["deck_too_large", "deck_too_many_slides", "deck_unsupported", "deck_corrupt", "deck_encrypted", "deck_macro", "deck_empty", "deck_unsafe", "deck_convert_timeout", "deck_convert_failed",
    "too_large", "unsupported", "empty", "export_first", "too_many_decks", "poll_timeout", "upload_failed", "unavailable", "deck_missing", "network", "auth"];
  it("every code has a specific message in both languages with the right placeholders", () => {
    for (const code of codes) {
      const p = problemFor(code, caps);
      expect(Object.keys(en), code).toContain(p.key);
      expect(Object.keys(es), code).toContain(p.key);
      for (const need of (en as any)[p.key].match(/\{(\w+)\}/g) ?? []) expect(p.params?.[need.slice(1, -1)], `${code} ${need}`).toBeDefined();
    }
  });
  it("picks the action that helps", () => {
    expect(problemFor("deck_encrypted").action).toBe("choose_other");
    expect(problemFor("deck_macro").action).toBe("choose_other");
    expect(problemFor("deck_convert_timeout").action).toBe("retry");
    expect(problemFor("poll_timeout").action).toBe("keep_waiting");
    expect(problemFor("upload_failed").action).toBe("retry");
    expect(problemFor("too_large", { max_mb: 20, max_slides: 30, formats: ["pdf"] }).params).toEqual({ mb: 20, slides: 30 });
    expect(problemFor("something_new").key).toBe("deck.err.network");
  });
  it("the messages promise nothing the app cannot keep and say what to do", () => {
    for (const k of Object.keys(en).filter((x) => x.startsWith("deck.err.") && x !== "deck.err.title")) expect((en as any)[k].length, k).toBeGreaterThan(30);
    expect(en["deck.err.encrypted"]).toMatch(/password/i);
    expect(es["deck.err.encrypted"]).toMatch(/contraseña/i);
    expect(en["deck.err.macro"]).toMatch(/macro/i);
  });
});

describe("journey state machine", () => {
  const idle: DeckState = { k: "idle" };
  it("goes idle, uploading, processing, ready", () => {
    let s = deckReducer(idle, { t: "pick", name: "a.pptx", format: "pptx" });
    expect(s).toEqual({ k: "uploading", name: "a.pptx", format: "pptx", pct: 0 });
    s = deckReducer(s, { t: "progress", pct: 41.6 });
    expect(s).toMatchObject({ pct: 42 });
    s = deckReducer(s, { t: "progress", pct: 400 });
    expect(s).toMatchObject({ pct: 100 });
    s = deckReducer(s, { t: "uploaded", id: "d1", now: 5 });
    expect(s).toEqual({ k: "processing", name: "a.pptx", id: "d1", since: 5 });
    s = deckReducer(s, { t: "ready", info: { slides: 12, suggested_minutes: 4, suggested_credits: 4 } });
    expect(s).toEqual({ k: "ready", name: "a.pptx", id: "d1", slides: 12, suggested_minutes: 4, suggested_credits: 4 });
  });
  it("a failure keeps the deck id only after upload, and a wait that is too long can resume", () => {
    const up = deckReducer(idle, { t: "pick", name: "a.pdf", format: "pdf" });
    expect(deckReducer(up, { t: "failed", code: "upload_failed" })).toMatchObject({ k: "error", code: "upload_failed", id: undefined });
    const pr = deckReducer(up, { t: "uploaded", id: "d9", now: 1 });
    const slow = deckReducer(pr, { t: "waited_too_long" });
    expect(slow).toMatchObject({ k: "error", code: "poll_timeout", id: "d9" });
    expect(deckReducer(slow, { t: "resume", now: 99 })).toEqual({ k: "processing", name: "a.pdf", id: "d9", since: 99 });
    expect(deckReducer(pr, { t: "failed", code: "deck_encrypted", message: "m" })).toMatchObject({ k: "error", code: "deck_encrypted", id: "d9", serverMessage: "m" });
  });
  it("late or out-of-order events are ignored, cancel and reset always go home", () => {
    expect(deckReducer(idle, { t: "progress", pct: 50 })).toBe(idle);
    expect(deckReducer(idle, { t: "ready", info: { slides: 1, suggested_minutes: 1, suggested_credits: 1 } })).toBe(idle);
    const up = deckReducer(idle, { t: "pick", name: "a.pdf", format: "pdf" });
    expect(deckReducer(up, { t: "ready", info: { slides: 1, suggested_minutes: 1, suggested_credits: 1 } })).toBe(up);
    expect(deckReducer(up, { t: "cancel" })).toEqual(idle);
    expect(deckReducer(deckReducer(up, { t: "failed", code: "x" }), { t: "reset" })).toEqual(idle);
    expect(deckReducer(idle, { t: "rejected", code: "too_large", name: "b.pptx" })).toEqual({ k: "error", code: "too_large", name: "b.pptx" });
    expect(deckReducer(idle, { t: "resume", now: 1 })).toBe(idle);
  });
});

describe("polling", () => {
  it("backs off from 2 s to 6 s and gives up after 3 minutes", () => {
    expect([0, 1, 2, 4, 8, 50].map(pollDelayMs)).toEqual([2000, 2500, 3000, 4000, 6000, 6000]);
    expect(pollExpired(1000, 1000 + POLL_GIVE_UP_MS - 1)).toBe(false);
    expect(pollExpired(1000, 1000 + POLL_GIVE_UP_MS)).toBe(true);
  });
  it("parses the status body; anything unexpected is still processing", () => {
    expect(parseDeckStatus({ status: "ready", slides: 12, suggested_minutes: 4, suggested_credits: 4 })).toEqual({ status: "ready", slides: 12, suggested_minutes: 4, suggested_credits: 4 });
    expect(parseDeckStatus({ status: "failed", code: "deck_macro", message: "m" })).toEqual({ status: "failed", code: "deck_macro", message: "m" });
    expect(parseDeckStatus({ status: "failed" })).toMatchObject({ code: "deck_convert_failed" });
    expect(parseDeckStatus({ status: "uploading" })).toEqual({ status: "uploading" });
    expect(parseDeckStatus({ status: "ready", slides: 0 })).toEqual({ status: "processing" });
    expect(parseDeckStatus(null)).toEqual({ status: "processing" });
  });
});

describe("price and options", () => {
  const c: Capabilities = { ...FALLBACK_CAPS, resolutions: [{ id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ["16:9"] }, { id: "2160p", label: "4K", credits_multiplier: 2, aspects: ["16:9"] }], lengths: { min_minutes: 0.25, max_minutes: 12, presets: [1, 2, 3, 5] } };
  const ready = { slides: 12, suggested_minutes: 4, suggested_credits: 4 };
  it("uses the suggested length and the server's credits until the person picks another", () => {
    expect(deckMinutes(ready, null)).toBe(4);
    expect(deckCredits(ready, null, "1080p", c)).toBe(4);
    expect(deckCredits(ready, 2, "1080p", c)).toBe(2);
    expect(deckCredits(ready, null, "2160p", c)).toBe(8);          // 4K doubles it (the usual rule)
    expect(deckCredits({ ...ready, suggested_minutes: 3.5, suggested_credits: 4 }, null, "2160p", c)).toBe(8);   // started minutes
    expect(deckCredits({ ...ready, suggested_credits: 0 }, null, "1080p", c)).toBe(4);
  });
  it("sends target_minutes only when chosen, and the deck id", () => {
    expect(deckGenerateExtras("d1", null)).toEqual({ deck: "d1" });
    expect(deckGenerateExtras("d1", 2)).toEqual({ deck: "d1", target_minutes: 2 });
  });
  it("warns on any aspect but 16:9", () => {
    expect(deckAspectWarning("16:9")).toBe(false);
    expect(deckAspectWarning("9:16")).toBe(true);
    expect(deckAspectWarning("1:1")).toBe(true);
  });
});

describe("upload target", () => {
  it("accepts S3 endpoints only", () => {
    for (const u of ["https://bucket.s3.amazonaws.com/", "https://videomk-uploads.s3.eu-west-1.amazonaws.com/", "https://s3.eu-west-1.amazonaws.com/bucket", "https://b.s3-eu-west-1.amazonaws.com/", "https://b.s3.dualstack.us-east-1.amazonaws.com/"])
      expect(isExpectedS3Url(u), u).toBe(true);
    for (const u of ["http://bucket.s3.amazonaws.com/", "https://evil.com/", "https://s3.amazonaws.com.evil.com/", "https://evil.com/.s3.amazonaws.com", "https://user:pw@b.s3.amazonaws.com/", "https://b.s3.amazonaws.com:8443/", "https://amazonaws.com/", "https://notamazonaws.com/", "https://xs3.amazonaws.com.attacker.io", "javascript:alert(1)", "", "not a url", "https://b.s3.amazonaws.com@evil.com/"])
      expect(isExpectedS3Url(u), u).toBe(false);
  });
});

describe("making card stages", () => {
  it("shows the deck stages only while the story is written", () => {
    expect(normalizeItem({ video_id: "1", status: "PLOT_CREATION", stage: "deck_reading" })?.stage).toBe("deck_reading");
    expect(normalizeItem({ video_id: "1", status: "PLOT_CREATION", stage: "deck_writing" })?.stage).toBe("deck_writing");
    expect(normalizeItem({ video_id: "1", status: "PLOT_CREATION" })?.stage).toBe("writing");
    expect(normalizeItem({ video_id: "1", status: "ASSETS_CREATION", stage: "deck_writing" })?.stage).toBe("assets");   // stale stage is ignored afterwards
    expect(makingInfo("deck_reading").line).toBe("deck_reading");
    expect(makingInfo("deck_writing").line).toBe("deck_writing");
    for (const l of ["deck_reading", "deck_writing"]) { expect((en as any)[`making.line.${l}`]).toBeTruthy(); expect((es as any)[`making.line.${l}`]).toBeTruthy(); }
  });
});
