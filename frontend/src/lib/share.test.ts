import { describe, expect, it } from "vitest";
import { isShareUrl, mapShareAnswer, shareAvailable, shareUrlFor } from "./share";

const TOKEN = "AbCdEfGhIjKlMnOpQrSt_-";
describe("share links", () => {
  it("is hidden until the share API address is set, and only https counts", () => {
    expect(shareAvailable("")).toBe(false);
    expect(shareAvailable("http://x.example")).toBe(false);
    expect(shareAvailable("https://x.execute-api.eu-west-1.amazonaws.com")).toBe(true);
  });
  it("builds the per-video address with the ids encoded", () => {
    expect(shareUrlFor("u 1", "v/2", "https://api.example")).toBe("https://api.example/users/u%201/videos/v%2F2/share");
  });
  it("accepts only a real share address", () => {
    expect(isShareUrl(`https://share.example.com/${TOKEN}`)).toBe(true);
    for (const bad of ["http://share.example.com/" + TOKEN, "https://share.example.com/short", `https://share.example.com/${TOKEN}/x`, "javascript:alert(1)", null, 5]) expect(isShareUrl(bad)).toBe(false);
  });
  it("maps the answers", () => {
    expect(mapShareAnswer(200, { shared: true, token: TOKEN, url: `https://d1.cloudfront.net/${TOKEN}` })).toEqual({ ok: true, state: { shared: true, url: `https://d1.cloudfront.net/${TOKEN}` } });
    expect(mapShareAnswer(200, { shared: true, url: "https://evil.example/x" })).toEqual({ ok: false, kind: "error" });
    expect(mapShareAnswer(200, { shared: false })).toEqual({ ok: true, state: { shared: false } });
    expect(mapShareAnswer(409, { code: "not_ready" })).toEqual({ ok: false, kind: "not_ready" });
    expect(mapShareAnswer(403, {})).toEqual({ ok: false, kind: "auth" });
    expect(mapShareAnswer(500, {})).toEqual({ ok: false, kind: "error" });
  });
});
