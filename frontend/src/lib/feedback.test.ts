import { describe, expect, it } from "vitest";
import { buildFeedbackRequest, cleanText, contextFrom, failureFor, textProblem, TEXT_MAX } from "./feedback";
import en from "../i18n/en.json";
import es from "../i18n/es.json";

describe("feedback request", () => {
  it("builds the contract body for the web app", () => {
    expect(buildFeedbackRequest({ text: "  Please add dark mode  ", kind: "idea", locale: "es", context: "after_video" })).toEqual({ text: "Please add dark mode", kind: "idea", app: "web", locale: "es", context: "after_video" });
  });
  it("leaves out what is not given and never invents a kind", () => {
    expect(buildFeedbackRequest({ text: "hello there" })).toEqual({ text: "hello there", app: "web" });
    expect(buildFeedbackRequest({ text: "hello there", kind: "nope" as any, locale: "fr" as any })).toEqual({ text: "hello there", app: "web" });
  });
  it("refuses short, blank and too long text; counts after trimming and control characters", () => {
    expect(buildFeedbackRequest({ text: "ab" })).toBeNull();
    expect(buildFeedbackRequest({ text: " \n\t  " })).toBeNull();
    expect(buildFeedbackRequest({ text: "a\u0000b\u0001 " })).toBeNull();
    expect(buildFeedbackRequest({ text: "x".repeat(TEXT_MAX) })).not.toBeNull();
    expect(buildFeedbackRequest({ text: "x".repeat(TEXT_MAX + 1) })).toBeNull();
    expect(textProblem("abc")).toBeNull();
    expect(textProblem("a")).toBe("short");
    expect(textProblem("x".repeat(TEXT_MAX + 1))).toBe("long");
  });
  it("keeps newlines and strips bidi and control characters", () => {
    expect(cleanText("a\r\nb‮ c\u0007")).toBe("a\nb c");
  });
  it("only sends a known context", () => {
    expect(contextFrom("?from=after_video")).toBe("after_video");
    expect(contextFrom("?from=<script>")).toBe("settings");
    expect(contextFrom("")).toBe("settings");
  });
  it("maps the answers to what the screen says", () => {
    expect([400, 429, 401, 403, 500, 502].map(failureFor)).toEqual(["invalid", "rate", "auth", "auth", "error", "error"]);
  });
  it("has every screen string in both languages", () => {
    const keys = Object.keys(en).filter((k) => k.startsWith("feedback.") || k === "nav.feedback");
    expect(keys.length).toBeGreaterThan(15);
    for (const k of keys) expect((es as any)[k], k).toBeTruthy();
  });
});
