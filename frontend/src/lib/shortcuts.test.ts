import { describe, expect, it } from "vitest";
import { G_WINDOW_MS, createShortcuts } from "./shortcuts";

function rig() {
  const log: string[] = []; let t = 1000; let searchHandled = true;
  const on = createShortcuts({ go: (d) => log.push(`go:${d}`), search: () => { log.push("search"); return searchHandled; }, help: () => log.push("help") }, () => t);
  return { log, on, tick: (ms: number) => (t += ms), noSearch: () => (searchHandled = false) };
}
const key = (k: string, extra: object = {}) => ({ key: k, ...extra });

describe("shortcuts", () => {
  it("N starts a new video, / focuses search, ? opens help", () => {
    const r = rig();
    expect(r.on(key("n"))).toBe(true); expect(r.on(key("/"))).toBe(true); expect(r.on(key("?"))).toBe(true);
    expect(r.log).toEqual(["go:new", "search", "help"]);
  });
  it("G then V/M/C goes to Videos/Media/Credits, within the window only", () => {
    const r = rig();
    r.on(key("g")); r.on(key("m"));
    r.on(key("g")); r.tick(G_WINDOW_MS + 1); r.on(key("v"));
    r.on(key("G")); r.on(key("c"));
    expect(r.log).toEqual(["go:media", "go:credits"]);
  });
  it("is silent while typing, with modifiers, or in a text box", () => {
    const r = rig();
    expect(r.on(key("n", { target: { tagName: "TEXTAREA" } }))).toBe(false);
    expect(r.on(key("n", { target: { tagName: "div", isContentEditable: true } }))).toBe(false);
    expect(r.on(key("n", { metaKey: true }))).toBe(false);
    expect(r.on(key("/", { ctrlKey: true }))).toBe(false);
    expect(r.on(key("x"))).toBe(false);
    expect(r.log).toEqual([]);
  });
  it("a page without a search box leaves / to the browser", () => {
    const r = rig(); r.noSearch();
    expect(r.on(key("/"))).toBe(false);
  });
  it("a stray G followed by another key does not leak into the next shortcut", () => {
    const r = rig();
    r.on(key("g")); r.on(key("x")); r.on(key("v"));
    expect(r.log).toEqual([]);
  });
});
