import { describe, expect, it } from "vitest";
import { emptySelection, formatBytes, groupByMonth, idsBetween, monthLabel, parsePhoto, parseSearch, parseSlots, parseSummary, selectAll, selectClick, storageTone } from "./library";
import type { Photo } from "./library";

const photo = (id: string, taken?: string, added = "2026-03-01T10:00:00Z"): Photo => ({ id, taken, added, w: 1, h: 1, bytes: 1, thumb_url: "", collections: [] });

describe("parsers", () => {
  it("a photo needs an id; unknown fields are dropped; missing numbers become 0", () => {
    expect(parsePhoto({})).toBeNull();
    const p = parsePhoto({ id: "a", taken: "2024-07-14T10:00:00", place: "Phuket, Thailand", thumb_url: "https://x/y.jpg", collections: ["c1", 5], junk: 1 })!;
    expect(p).toMatchObject({ id: "a", place: "Phuket, Thailand", w: 0, bytes: 0, collections: ["c1"] });
  });
  it("summary: needs limit_bytes; organise preference defaults to ask", () => {
    expect(parseSummary({})).toBeNull();
    const s = parseSummary({ plan: "pro", limit_bytes: 1e11, used_bytes: 5, count: 3, years: [{ year: 2026, count: 3 }, { nope: 1 }], places: [{ name: "Paris", country: "France", count: 2 }], collections: [{ id: "c", name: "Family", count: 4 }, { id: "x" }], prefs: { organize: "always" } })!;
    expect(s.plan).toBe("pro"); expect(s.organize).toBe("always"); expect(s.years).toHaveLength(1); expect(s.collections).toHaveLength(1);
    expect(parseSummary({ limit_bytes: 1 })!.organize).toBe("ask");
  });
  it("search chips keep their kind; unknown kinds are topics", () => {
    const r = parseSearch({ items: [{ id: "a" }, { nope: 1 }], understood: { chips: [{ kind: "place", label: "Thailand" }, { kind: "weird", label: "beach" }, { kind: "date" }] }, mode: "semantic" });
    expect(r.items).toHaveLength(1); expect(r.chips).toEqual([{ kind: "place", label: "Thailand" }, { kind: "topic", label: "beach" }]); expect(r.mode).toBe("semantic");
  });
  it("upload slots: statuses the server may send, anything else counts as upload", () => {
    const s = parseSlots({ uploads: [{ index: 0, status: "upload", id: "p1", url: "https://s3", fields: { a: "b" } }, { index: 1, status: "duplicate", duplicate_of: "p0" }, { index: 2, status: "no_space" }, { index: 3, status: "???" }, { status: "upload" }] });
    expect(s.map((x) => x.status)).toEqual(["upload", "duplicate", "no_space", "upload"]);
    expect(s[1].duplicate_of).toBe("p0");
  });
});

describe("timeline grouping", () => {
  it("groups by the month taken (else added), newest first, undated last", () => {
    const g = groupByMonth([photo("a", "2026-03-05T10:00:00"), photo("b", undefined, "2026-01-02T00:00:00Z"), photo("c", "2026-03-01T09:00:00"), photo("d", undefined, ""), photo("e", "2025-12-31T23:00:00")]);
    expect(g.map((x) => x.key)).toEqual(["2026-03", "2026-01", "2025-12", "0000-00"]);
    expect(g[0].items.map((p) => p.id)).toEqual(["a", "c"]);
  });
  it("month labels follow the language", () => {
    const g = groupByMonth([photo("a", "2026-07-02T00:00:00")])[0];
    expect(monthLabel(g, "en")).toBe("July 2026");
    expect(monthLabel(g, "es")?.toLowerCase()).toBe("julio de 2026");
    expect(monthLabel(groupByMonth([photo("d", undefined, "")])[0], "en")).toBeNull();
  });
});

describe("storage", () => {
  it("formats sizes", () => { expect(formatBytes(1_200_000_000)).toBe("1.2 GB"); expect(formatBytes(900)).toBe("900 B"); expect(formatBytes(2_000_000_000, "es")).toBe("2 GB"); });
  it("tone: amber at 85 %, red when full", () => {
    expect(storageTone({ used_bytes: 10, limit_bytes: 100 })).toBe("ok");
    expect(storageTone({ used_bytes: 85, limit_bytes: 100 })).toBe("warn");
    expect(storageTone({ used_bytes: 100, limit_bytes: 100 })).toBe("full");
  });
});

describe("selection", () => {
  const order = ["a", "b", "c", "d", "e", "f"];
  it("click toggles and sets the anchor", () => {
    let s = selectClick(emptySelection, order, "b", false);
    expect(s).toEqual({ ids: ["b"], anchor: "b" });
    s = selectClick(s, order, "b", false);
    expect(s.ids).toEqual([]);
  });
  it("shift-click selects the range from the anchor in either direction", () => {
    let s = selectClick(emptySelection, order, "b", false);
    s = selectClick(s, order, "e", true);
    expect(s.ids.sort()).toEqual(["b", "c", "d", "e"]);
    s = selectClick({ ids: ["e"], anchor: "e" }, order, "c", true);
    expect(s.ids.sort()).toEqual(["c", "d", "e"]);
  });
  it("never exceeds the cap and select all respects it", () => {
    const many = Array.from({ length: 150 }, (_, i) => `p${i}`);
    expect(selectAll(many).ids).toHaveLength(100);
    const full = selectAll(many);
    expect(selectClick(full, many, "p120", false)).toEqual(full);
    expect(selectClick({ ids: ["p0"], anchor: "p0" }, many, "p149", true).ids).toHaveLength(100);
  });
  it("drag selection covers the photos between two positions, in grid order", () => {
    expect(idsBetween(order, "d", "b")).toEqual(["b", "c", "d"]);
    expect(idsBetween(order, "x", "b")).toEqual([]);
  });
});

import { SETTLE_DELAYS_MS, pendingIds } from "./library";
describe("after an upload", () => {
  it("knows which new photos the list does not show yet", () => {
    expect(pendingIds(["a", "b", "c"], [])).toEqual(["a", "b", "c"]);
    expect(pendingIds(["a", "b", "c"], [{ id: "b" }, { id: "z" }])).toEqual(["a", "c"]);
    expect(pendingIds(["a"], [{ id: "a" }])).toEqual([]);
    expect(pendingIds([], [{ id: "a" }])).toEqual([]);
  });
  it("looks again for about a minute, straight away first", () => {
    expect(SETTLE_DELAYS_MS[0]).toBe(0);
    const total = SETTLE_DELAYS_MS.reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThanOrEqual(45000);
    expect(total).toBeLessThanOrEqual(90000);
  });
});
