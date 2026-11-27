import { describe, expect, it } from "vitest";
import { dayGroupOf, formatDuration, groupByDay, makingInfo, minutesLeft, normalizeItem, parseMaking, placeholderTone, sceneCounter, sceneKey, stableSceneThumbs, stripTiles, withoutSceneLinks } from "./videos";

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

import { filterVideos, nextPollMs, reuseUnchanged, stableThumbs } from "./videos";
import type { TaskItem } from "./videos";
describe("redesigned list helpers", () => {
  it("search needs every word, ignores case and accents", () => {
    const items = [{ title: "How a forest breathes" }, { title: "Cómo respira un bosque" }, { title: "Mortgage rates" }];
    expect(filterVideos(items, "FOREST breathes")).toHaveLength(1);
    expect(filterVideos(items, "como bosque")).toHaveLength(1);
    expect(filterVideos(items, "  ")).toHaveLength(3);
    expect(filterVideos(items, "zzz")).toHaveLength(0);
  });
  it("the first thumbnail link of an id is kept even when the next poll brings a new signature", () => {
    const a = stableThumbs({}, [{ id: "1", preview_gif_url: "https://x/1.gif?sig=a" }, { id: "2", preview_gif_url: null }]);
    const b = stableThumbs(a, [{ id: "1", preview_gif_url: "https://x/1.gif?sig=b" }, { id: "2", preview_gif_url: "https://x/2.gif?sig=a" }]);
    expect(b).toEqual({ "1": "https://x/1.gif?sig=a", "2": "https://x/2.gif?sig=a" });
  });
  it("an unchanged item keeps its object so it is not redrawn", () => {
    const a: TaskItem = { id: "1", status: "complete", title: "A", preview_gif_url: "https://x/1?s=a" };
    const same = reuseUnchanged([a], [{ ...a, preview_gif_url: "https://x/1?s=b" }]);
    expect(same[0]).toBe(a);
    const changed = reuseUnchanged([a], [{ ...a, title: "B" }]);
    expect(changed[0]).not.toBe(a);
  });
  it("polling backs off to 30 s, stops when nothing is being made or the tab is hidden", () => {
    expect([0, 1, 2, 20].map((n) => nextPollMs(n, true, false))).toEqual([5000, 8000, 11000, 30000]);
    expect(nextPollMs(0, false, false)).toBeNull();
    expect(nextPollMs(0, true, true)).toBeNull();
  });
});

import { markRetrying, retryOutcome } from "./videos";
describe("try again reuses the same video", () => {
  it("a cancelled or failed video is a failed card that can offer Try again", () => {
    expect(normalizeItem({ video_id: "a", status: "CANCELLED", can_retry: true })).toMatchObject({ status: "error", can_retry: true });
    expect(normalizeItem({ video_id: "b", status: "FAILED" })).toMatchObject({ status: "error", can_retry: false });
  });
  it("maps the retry route's answers; an older server never leads to a resend", () => {
    expect(retryOutcome(202, { status: "STARTED_PROCESSING" })).toEqual({ ok: true });
    expect(retryOutcome(200, { message: "already running" })).toEqual({ ok: true });
    expect(retryOutcome(409, { code: "attachments_unavailable", message: "m" })).toEqual({ ok: false, kind: "attachments", message: "m" });
    expect(retryOutcome(409, { code: "retry_limit" })).toMatchObject({ ok: false, kind: "limit" });
    expect(retryOutcome(409, { code: "rejected" })).toMatchObject({ ok: false, kind: "rejected" });
    expect(retryOutcome(402, { code: "insufficient_credits" })).toMatchObject({ ok: false, kind: "credits" });
    expect(retryOutcome(404, { code: "not_found" })).toMatchObject({ ok: false, kind: "gone" });
    expect(retryOutcome(404, { message: "Missing Authentication Token" })).toEqual({ ok: false, kind: "unsupported" });
    expect(retryOutcome(403, null)).toEqual({ ok: false, kind: "unsupported" });
    expect(retryOutcome(500, null)).toMatchObject({ ok: false, kind: "error" });
  });
  it("the retried item stays the same item: same id, same place, now being made", () => {
    const list = [{ id: "x", status: "complete" as const }, { id: "f", status: "error" as const, can_retry: true, title: "T" }];
    const next = markRetrying(list, "f");
    expect(next).toHaveLength(2);
    expect(next[1]).toMatchObject({ id: "f", title: "T", status: "running", stage: "starting", can_retry: false });
    expect(next[0]).toBe(list[0]);
  });
});

describe("the optional making object (docs/CREATE_API.md Making status)", () => {
  const full = { scene_total: 9, scene_done: 4, live_line: "Adding footage of sunlit canopies", narration_line: "Sunlight pours through the canopy.",
    scenes: [{ index: 1, done: true, thumb_url: "https://x/1.jpg?sig=a" }, { index: 2, done: true }, { index: 3, done: false }, { index: 4, done: true, thumb_url: "https://x/4.jpg?sig=a" }, { index: 5, done: true }, { index: 6, done: false }, { index: 7, done: false }, { index: 8, done: false }, { index: 9, done: false }] };
  it("reads the documented shape", () => {
    const m = parseMaking(full)!;
    expect(m.scene_total).toBe(9);
    expect(m.scene_done).toBe(4);
    expect(m.live_line).toBe("Adding footage of sunlit canopies");
    expect(m.scenes).toHaveLength(9);
    expect(sceneCounter(m)).toEqual({ index: 5, total: 9 });
  });
  it("is absent, empty or malformed without breaking anything", () => {
    for (const bad of [undefined, null, "x", 3, [], {}, { scene_total: "nine" }, { scenes: "no" }, { scenes: [null, 4, {}] }, { live_line: "   " }]) expect(parseMaking(bad)).toBeNull();
    expect(normalizeItem({ video_id: "1", status: "RENDERING" })?.making).toBeNull();
    expect(sceneCounter(null)).toBeNull();
    expect(stripTiles(null)).toEqual([]);
  });
  it("draws what is there: every field is optional", () => {
    expect(parseMaking({ live_line: "Recording the narration" })).toEqual({ live_line: "Recording the narration" });
    expect(parseMaking({ scene_total: 3 })).toEqual({ scene_total: 3 });
    expect(stripTiles(parseMaking({ scene_total: 3, scene_done: 1 })).map((t) => t.state)).toEqual(["done", "now", "todo"]);
    const fromScenes = parseMaking({ scenes: [{ index: 2, done: false }, { index: 1, done: true }] })!;   // counts derived, story order restored
    expect(fromScenes).toMatchObject({ scene_total: 2, scene_done: 1 });
    expect(fromScenes.scenes!.map((x) => x.index)).toEqual([1, 2]);
  });
  it("never trusts odd values", () => {
    const m = parseMaking({ scene_total: 4, scene_done: 99, scenes: [{ index: 1, done: true, thumb_url: "javascript:alert(1)" }, { index: 1, done: false }, { index: 2, done: false, thumb_url: "https://x/2.jpg" }, { index: -3, done: true }] })!;
    expect(m.scene_done).toBe(4);                                    // never past the total
    expect(m.scenes).toEqual([{ index: 1, done: true }, { index: 2, done: false }]);   // only https pictures, only for done scenes, no duplicate or negative index
    expect(sceneCounter(m)).toBeNull();                              // every scene done: the render has no scene in work
    expect(sceneCounter(parseMaking({ scene_total: 4, scene_done: 3 }))).toEqual({ index: 4, total: 4 });
  });
  it("only a video being made carries it", () => {
    expect(normalizeItem({ video_id: "1", status: "ASSETS_CREATION", making: full })?.making?.scene_total).toBe(9);
    expect(normalizeItem({ video_id: "1", status: "COMPLETE", making: full })?.making).toBeNull();
    expect(normalizeItem({ video_id: "1", status: "FAILED", making: full })?.making).toBeNull();
  });
  it("the strip follows scenes[].done (they finish out of order); the first one not done is in work", () => {
    const tiles = stripTiles(parseMaking(full), {}, "v");
    expect(tiles.map((t) => t.state)).toEqual(["done", "done", "now", "done", "done", "todo", "todo", "todo", "todo"]);
    expect(tiles[0].thumb).toBe("https://x/1.jpg?sig=a");
    expect(tiles[1].thumb).toBeUndefined();
  });
  it("keeps the first picture link per video and scene, so a poll with new signatures reloads nothing", () => {
    const a = normalizeItem({ video_id: "v", status: "ASSETS_CREATION", making: full })!;
    const first = stableSceneThumbs({}, [a]);
    expect(first[sceneKey("v", 1)]).toBe("https://x/1.jpg?sig=a");
    const b = normalizeItem({ video_id: "v", status: "ASSETS_CREATION", making: { ...full, scenes: full.scenes.map((x) => (x.thumb_url ? { ...x, thumb_url: x.thumb_url.replace("sig=a", "sig=b") } : x)) } })!;
    expect(stableSceneThumbs(first, [b])).toBe(first);               // same object: nothing to redraw
    expect(stripTiles(b.making, first, "v")[0].thumb).toBe("https://x/1.jpg?sig=a");
    expect(reuseUnchanged([a], [b])[0]).toBe(a);                     // new signatures alone do not redraw the banner
    const c = normalizeItem({ video_id: "v", status: "ASSETS_CREATION", making: { ...full, scene_done: 5 } })!;
    expect(reuseUnchanged([a], [c])[0]).toBe(c);                     // progress does
  });
  it("never stores the private picture links in the session cache", () => {
    const a = normalizeItem({ video_id: "v", status: "ASSETS_CREATION", making: full })!;
    const cached = JSON.stringify(withoutSceneLinks([a]));
    expect(cached).not.toContain("https://x/");
    expect(cached).toContain("Adding footage");
  });
});
