import { describe, expect, it } from "vitest";
import { APP_URL, SITE_URL } from "./config";
import { appUrl, siteUrl, tryPromptUrl } from "./links";

describe("links between the two sites", () => {
  it("defaults point at the production hosts", () => {
    expect(APP_URL).toBe("https://app.videomk.com");
    expect(SITE_URL).toBe("https://videomk.com");
  });
  it("app links are absolute, without index.html, with encoded query values", () => {
    expect(appUrl()).toBe("https://app.videomk.com/");
    expect(appUrl("/signin")).toBe("https://app.videomk.com/signin");
    expect(appUrl("/watch", { id: "a b&c" })).toBe("https://app.videomk.com/watch?id=a%20b%26c");
    expect(appUrl("/generations?new=1", { prompt: "x" })).toBe("https://app.videomk.com/generations?new=1&prompt=x");
    expect(appUrl("/watch", { id: undefined })).toBe("https://app.videomk.com/watch");
  });
  it("site links follow the language", () => {
    expect(siteUrl("/privacy")).toBe("https://videomk.com/privacy");
    expect(siteUrl("/privacy", "es")).toBe("https://videomk.com/es/privacy");
    expect(siteUrl("/", "es")).toBe("https://videomk.com/es/");
    expect(siteUrl("/")).toBe("https://videomk.com/");
  });
  it("the try-this-prompt link carries the prompt, capped", () => {
    expect(tryPromptUrl("a 1 minute video about bees")).toContain("prompt=a%201%20minute%20video%20about%20bees");
    expect(decodeURIComponent(tryPromptUrl("x".repeat(900))).length).toBeLessThan(600);
  });
});
