import { describe, expect, it } from "vitest";
import { base64Of, logoProblem, parseWatermark, readPref, writePref } from "./settings";
import { authTimeOf, confirmationOk, isFreshSignIn, keysToWipe, mapDeleteAnswer, readResume, RESUME_PATH } from "./account";

const mem = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }; };
const token = (claims: object) => `x.${btoa(JSON.stringify(claims)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}.y`;

describe("preferences", () => {
  it("have defaults: subtitles and dates on, locations off", () => {
    const s = mem();
    expect(readPref("subtitles", s)).toBe(true);
    expect(readPref("photoDates", s)).toBe(true);
    expect(readPref("photoLocations", s)).toBe(false);
  });
  it("round-trip and ignore garbage", () => {
    const s = mem();
    writePref("subtitles", false, s); writePref("photoLocations", true, s);
    expect(readPref("subtitles", s)).toBe(false);
    expect(readPref("photoLocations", s)).toBe(true);
    s.setItem("vmk_pref_photo_dates", "maybe");
    expect(readPref("photoDates", s)).toBe(true);
  });
  it("survive a storage that throws", () => {
    const bad = { getItem: () => { throw new Error("x"); }, setItem: () => { throw new Error("x"); } };
    expect(readPref("subtitles", bad)).toBe(true);
    expect(() => writePref("subtitles", false, bad)).not.toThrow();
  });
});

describe("watermark view", () => {
  const raw = { watermark: { mode: "videomk", position: "tr", has_logo: false }, capabilities: { modes: [{ id: "none", available: true }, { id: "videomk", available: true }, { id: "custom", available: false, requires: "premium" }, { id: "weird", available: true }], forced: false, premium: false, logo: { max_bytes: 1000, types: ["image/png"] } } };
  it("reads the settings and what is allowed", () => {
    const v = parseWatermark(raw)!;
    expect(v.settings).toEqual({ mode: "videomk", position: "tr", has_logo: false });
    expect(v.modes.map((m) => m.id)).toEqual(["none", "videomk", "custom"]);
    expect(v.modes[2].available).toBe(false);
    expect(v.logo).toEqual({ max_bytes: 1000, types: ["image/png"] });
  });
  it("is null when the server has no such feature or sends nonsense", () => {
    expect(parseWatermark(null)).toBeNull();
    expect(parseWatermark({ watermark: {}, capabilities: {} })).toBeNull();
    expect(parseWatermark({ watermark: {}, capabilities: { modes: [] } })).toBeNull();
  });
  it("falls back to safe values", () => {
    const v = parseWatermark({ ...raw, watermark: { mode: "x", position: "y" } })!;
    expect(v.settings).toEqual({ mode: "none", position: "auto", has_logo: false });
  });
  it("cuts the base64 out of a data URL", () => {
    expect(base64Of("data:image/png;base64,AAAA")).toBe("AAAA");
    expect(base64Of("data:text/html,<b>")).toBeNull();
    expect(base64Of("nope")).toBeNull();
  });
  it("checks the chosen file", () => {
    const types = ["image/png", "image/jpeg"];
    expect(logoProblem({ size: 0, type: "image/png" }, 1000, types)).toBe("empty");
    expect(logoProblem({ size: 2000, type: "image/png" }, 1000, types)).toBe("big");
    expect(logoProblem({ size: 10, type: "image/gif" }, 1000, types)).toBe("type");
    expect(logoProblem({ size: 10, type: "image/png" }, 1000, types)).toBeNull();
  });
});

describe("account deletion helpers", () => {
  it("reads auth_time and judges freshness", () => {
    const now = 1_700_000_600_000;
    expect(authTimeOf(token({ auth_time: 1_700_000_000 }))).toBe(1_700_000_000);
    expect(isFreshSignIn(token({ auth_time: 1_700_000_100 }), now)).toBe(true);
    expect(isFreshSignIn(token({ auth_time: 1_699_999_000 }), now)).toBe(false);
    expect(isFreshSignIn(token({}), now)).toBe(false);
    expect(isFreshSignIn("garbage", now)).toBe(false);
    expect(isFreshSignIn(null, now)).toBe(false);
  });
  it("accepts the typed word", () => {
    expect(confirmationOk("DELETE")).toBe(true);
    expect(confirmationOk("  delete ")).toBe(true);
    expect(confirmationOk("DELET")).toBe(false);
    expect(confirmationOk("")).toBe(false);
  });
  it("maps the server's answers", () => {
    expect(mapDeleteAnswer(202, { apple: "revoke_available" })).toEqual({ ok: true, apple: "revoke_available" });
    expect(mapDeleteAnswer(202, {})).toEqual({ ok: true, apple: "unknown" });
    expect(mapDeleteAnswer(401, { code: "reauth_required" })).toEqual({ ok: false, kind: "reauth" });
    expect(mapDeleteAnswer(401, { message: "Unauthorized" })).toEqual({ ok: false, kind: "auth" });
    expect(mapDeleteAnswer(403, {})).toEqual({ ok: false, kind: "auth" });
    expect(mapDeleteAnswer(500, {})).toEqual({ ok: false, kind: "error" });
  });
  it("resumes only our own fresh path", () => {
    const now = 1_000_000;
    expect(readResume(JSON.stringify({ path: RESUME_PATH, at: now - 1000 }), now)).toBe(RESUME_PATH);
    expect(readResume(JSON.stringify({ path: RESUME_PATH, at: now - 16 * 60 * 1000 }), now)).toBeNull();
    expect(readResume(JSON.stringify({ path: "https://evil.example/", at: now }), now)).toBeNull();
    expect(readResume(JSON.stringify({ path: "//evil.example", at: now }), now)).toBeNull();
    expect(readResume("not json", now)).toBeNull();
    expect(readResume(null, now)).toBeNull();
  });
  it("wipes the person's keys but keeps language and look", () => {
    expect(keysToWipe(["vmk_auth_tokens", "vmk_locale", "vmk_theme", "vmk_tasks", "other", "vmk-draft", "videomk.x"]).sort()).toEqual(["videomk.x", "vmk-draft", "vmk_auth_tokens", "vmk_tasks"]);
  });
});
