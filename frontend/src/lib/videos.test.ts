import { describe, expect, it } from "vitest";
import { dayGroupOf, formatDuration, groupByDay, makingInfo, minutesLeft, normalizeItem, placeholderTone } from "./videos";

const now = new Date(2026, 10, 26, 15, 0, 0);
const at = (d: number, h = 9) => new Date(2026, 10, d, h).toISOString();

describe("day groups", () => {
  it("sorts into today, yesterday, earlier; no date is earlier", () => {
    expect(dayGroupOf(at(26), now)).toBe("today");
    expect(dayGroupOf(at(25, 23), now)).toBe("yesterday");
    expect(dayGroupOf(at(24), now)).toBe("earlier");
    expect(dayGroupOf(null, now)).toBe("earlier");
    expect(dayGroupOf("not a date", now)).toBe("earlier");
  });
  it("keeps order inside a group and drops empty groups", () => {
    const g = groupByDay([{ id: "a", created_at: at(26, 12) }, { id: "b", created_at: at(20) }, { id: "c", created_at: at(26, 8) }], now);
    expect(g.map((x) => x.group)).toEqual(["today", "earlier"]);
    expect(g[0].items.map((x) => x.id)).toEqual(["a", "c"]);
  });
  it("yesterday works across a month boundary", () => {
    expect(dayGroupOf(new Date(2026, 9, 31, 10).toISOString(), new Date(2026, 10, 1, 8))).toBe("yesterday");
  });
});

describe("normalizeItem", () => {
  it("maps the stages and the terminal states", () => {
    expect(normalizeItem({ video_id: "1", status: "PLOT_CREATION" })).toMatchObject({ status: "running", stage: "writing" });
    expect(normalizeItem({ video_id: "1", status: "RENDERING" })).toMatchObject({ status: "running", stage: "rendering" });
    expect(normalizeItem({ video_id: "1", status: "COMPLETE" })).toMatchObject({ status: "complete", stage: undefined });
    expect(normalizeItem({ video_id: "1", status: "FAILED" })?.status).toBe("error");
    expect(normalizeItem({ video_id: "1", status: "weird" })).toMatchObject({ status: "queued", stage: "starting" });
    expect(normalizeItem({ status: "COMPLETE" })).toBeNull();
  });
  it("turns s3 uris into https and keeps the thumbnail", () => {
    const t = normalizeItem({ id: "x", status: "COMPLETE", video_uri: "s3://videomk.com/v/a.mp4", preview_gif_url: "https://x/p.gif", duration_s: 75 })!;
    expect(t.download_url).toBe("https://videomk.com/v/a.mp4");
    expect(t.preview_gif_url).toBe("https://x/p.gif");
    expect(formatDuration(t.duration_s)).toBe("1:15");
    expect(formatDuration(0)).toBeNull();
  });
});

describe("making progress", () => {
  it("fills the four steps in order", () => {
    expect(makingInfo("writing").current).toBe(0);
    const mid = makingInfo("storyboard");
    expect(mid.segments.slice(0, 2)).toEqual([1, 1]);
    expect(mid.segments[3]).toBe(0);
    const late = makingInfo("rendering");
    expect(late.current).toBe(3);
    expect(late.segments.slice(0, 3)).toEqual([1, 1, 1]);
    expect(makingInfo(undefined).line).toBe("starting");
  });
  it("minutes left rounds up; no estimate is null", () => {
    expect(minutesLeft(null)).toBeNull();
    expect(minutesLeft(0)).toBe(0);
    expect(minutesLeft(61)).toBe(2);
    expect(minutesLeft(120)).toBe(2);
  });
  it("placeholder tone is stable and in range", () => {
    expect(placeholderTone("abc")).toBe(placeholderTone("abc"));
    for (const id of ["a", "b", "zzz", "123"]) expect([0, 1, 2, 3]).toContain(placeholderTone(id));
  });
});
