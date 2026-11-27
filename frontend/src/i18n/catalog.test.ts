import { describe, expect, it } from "vitest";
import { AREA_PREFIXES, BY_AREA, EN, ES } from "./catalog";
import type { Area } from "./catalog";

const areas = Object.keys(BY_AREA) as Area[];
const ph = (s: string) => [...s.matchAll(/\{(\w+)/g)].map((m) => m[1]).sort().join(",");

describe("per-area catalogue", () => {
  it.each(areas)("%s: English and Spanish have the same keys, placeholders and no empty text", (a) => {
    const { en, es } = BY_AREA[a];
    expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort());
    for (const k of Object.keys(en)) {
      expect(ph(es[k]), k).toBe(ph(en[k]));
      expect(es[k].trim(), k).not.toBe("");
    }
  });
  it.each(areas)("%s: every key starts with a segment the area owns", (a) => {
    for (const k of Object.keys(BY_AREA[a].en)) expect(AREA_PREFIXES[a], `${k} in ${a}`).toContain(k.split(".")[0]);
  });
  it("a segment belongs to one area only, and no key is defined twice", () => {
    const seen = new Map<string, Area>();
    for (const a of areas) for (const p of AREA_PREFIXES[a]) { expect(seen.has(p), `${p} owned twice`).toBe(false); seen.set(p, a); }
    expect(Object.keys(EN).length).toBe(areas.reduce((n, a) => n + Object.keys(BY_AREA[a].en).length, 0));
    expect(Object.keys(ES).length).toBe(Object.keys(EN).length);
  });
});
