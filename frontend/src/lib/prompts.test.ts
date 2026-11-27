import { beforeEach, describe, expect, it } from "vitest";
import { pickPrompt, promptFor, rememberPrompt, withPrompt } from "./prompts";

describe("the prompt beside a video", () => {
  it("keeps the newest first, one per video, at most 60", () => {
    let l = withPrompt([], "a", " How bees make honey ");
    l = withPrompt(l, "b", "Why forests matter");
    l = withPrompt(l, "a", "How bees make honey, short");
    expect(l).toEqual([["a", "How bees make honey, short"], ["b", "Why forests matter"]]);
    for (let i = 0; i < 80; i++) l = withPrompt(l, `v${i}`, "x");
    expect(l).toHaveLength(60);
    expect(l[0][0]).toBe("v79");
  });
  it("ignores an empty id or prompt", () => {
    expect(withPrompt([], "", "x")).toEqual([]);
    expect(withPrompt([], "a", "   ")).toEqual([]);
  });
  it("the server's prompt wins; nothing known shows nothing", () => {
    expect(pickPrompt("From the server", "local")).toBe("From the server");
    expect(pickPrompt(undefined, "local")).toBe("local");
    expect(pickPrompt(42, null)).toBeNull();
    expect(pickPrompt("  ", "  ")).toBeNull();
  });
  describe("storage", () => {
    beforeEach(() => {
      const m = new Map<string, string>();
      (globalThis as any).localStorage = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
    });
    it("remembers and finds by video id; survives broken storage", () => {
      rememberPrompt("v1", "A calm explainer about forests");
      expect(promptFor("v1")).toBe("A calm explainer about forests");
      expect(promptFor("v2")).toBeNull();
      localStorage.setItem("vmk_prompts", "{not json");
      expect(promptFor("v1")).toBeNull();
      (globalThis as any).localStorage = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
      expect(() => rememberPrompt("v1", "x")).not.toThrow();
      expect(promptFor("v1")).toBeNull();
    });
  });
});
