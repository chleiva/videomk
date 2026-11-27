import { describe, expect, it } from "vitest";
import {
  AUTO, castGroups, chooseLook, isConversation, lookHints, lookRequest, normalizeChoice, optionOf, parseLookAnswer, parseLooks, parseSavedLook, parseVideoLook, pillOf, presetFor,
  safeImage, tiles, toggleCast, toggleExtra, withNote,
} from "./looks";
import type { LookChoice } from "./looks";
import { LOOKS_FIXTURE, looksWith } from "./looks.fixture";

const caps = parseLooks(LOOKS_FIXTURE)!;
const none = { photos: false, deck: false };
const cartoon = (cast: LookChoice["cast"] = "auto", extras: string[] = []): LookChoice => ({ look: "cartoon", cast, extras });

describe("capabilities.looks is decoded leniently", () => {
  it("reads the four tiles in the server's order, with the cast", () => {
    expect(caps.options.map((o) => o.id)).toEqual(["auto", "real", "whiteboard", "cartoon"]);
    expect(optionOf(caps, "cartoon")).toMatchObject({ cast: true, with_photos: false, with_deck: false, min_seconds: 15, best_aspects: ["16:9", "1:1", "4:5"] });
    expect(optionOf(caps, "cartoon")!.extras).toEqual([{ id: "board", label: "Hand-drawn board", note: "The characters explain on a board that is drawn as they speak.", available: true }]);
    expect(caps.cast).toMatchObject({ max: 3, conversation: { from: 2, min_seconds: 20 } });
    expect(caps.cast!.members).toHaveLength(10);
    expect(castGroups(caps.cast).map((g) => g.length)).toEqual([4, 6]);   // people, then animals
  });
  it("a server without the picker (no looks, the older looks.style only, garbage) means: no picker, today's behaviour", () => {
    for (const raw of [undefined, null, {}, "x", { style: { options: [{ id: "auto" }] } }, { look: {} }, { look: { options: "no" } }, { look: { options: [{ id: "auto", label: "Auto" }] } }, { look: { options: [{ id: "real", label: "Real" }, { id: "cartoon", label: "Cartoon" }] } }])
      expect(parseLooks(raw)).toBeUndefined();
  });
  it("missing fields get the permissive default, malformed entries are dropped, never thrown", () => {
    const c = parseLooks({ look: { options: [{ id: "auto", label: "Auto" }, { id: "real", label: "Real", preview: "javascript:alert(1)" }, { label: "no id" }, null, { id: "real", label: "Twice" }, { id: "cartoon", label: "Cartoon", cast: true, extras: [{ id: "board" }, "x"] }] }, cast: { members: [{ id: "fox", name: "Fox", thumbnail: "http://x/y.png" }, { id: "fox", name: "Again" }, { name: "nobody" }, { id: "auto", name: "Auto" }] } })!;
    expect(c.options.map((o) => o.id)).toEqual(["auto", "real", "cartoon"]);
    expect(optionOf(c, "real")).toMatchObject({ available: true, allowed: true, requires_plan: null, with_photos: true, with_deck: true, min_seconds: 0, aspects: null, best_aspects: null, cast: false, extras: [] });
    expect(optionOf(c, "real")!.preview).toBeUndefined();   // only image data URIs and https links are ever drawn
    expect(optionOf(c, "cartoon")!.extras).toEqual([]);
    expect(c.cast).toMatchObject({ max: 1, conversation: null, members: [{ id: "fox", name: "Fox" }] });
    expect(c.cast!.members[0].thumbnail).toBeUndefined();
  });
  it("a cast that is switched off, or empty, is no cast", () => {
    expect(parseLooks({ ...LOOKS_FIXTURE, cast: { ...LOOKS_FIXTURE.cast, available: false } })!.cast).toBeNull();
    expect(parseLooks({ ...LOOKS_FIXTURE, cast: { members: [] } })!.cast).toBeNull();
    expect(parseLooks({ look: LOOKS_FIXTURE.look })!.cast).toBeNull();
  });
  it("never more than four tiles", () => {
    const many = { look: { options: [...LOOKS_FIXTURE.look.options, { id: "clay", label: "Clay" }, { id: "anime", label: "Anime" }] } };
    expect(parseLooks(many)!.options).toHaveLength(4);
  });
  it("pictures: data URIs of images and https only", () => {
    expect(safeImage("data:image/jpeg;base64,AAAA")).toBeTruthy();
    expect(safeImage("https://cdn.example/x.png")).toBeTruthy();
    for (const bad of ["data:text/html;base64,AAAA", "data:image/svg+xml;base64,AAAA", "javascript:alert(1)", "http://x/y.png", 'https://x/"onerror="x', "", null, 7]) expect(safeImage(bad)).toBeUndefined();
  });
});

describe("what the picker offers", () => {
  it("all four when nothing is attached", () => {
    expect(tiles(caps, none).map((t) => [t.option.id, t.state])).toEqual([["auto", "ok"], ["real", "ok"], ["whiteboard", "ok"], ["cartoon", "ok"]]);
  });
  it("a look this stage does not have is hidden", () => {
    const c = parseLooks(looksWith("whiteboard", { available: false }))!;
    expect(tiles(c, none).map((t) => t.option.id)).toEqual(["auto", "real", "cartoon"]);
  });
  it("a look the plan does not allow is shown locked, with the plan it needs", () => {
    const t = tiles(parseLooks(looksWith("cartoon", { allowed: false, requires_plan: "pro" }))!, none).find((x) => x.option.id === "cartoon")!;
    expect(t.state).toBe("locked"); expect(t.option.requires_plan).toBe("pro");
  });
  it("with the person's own photos, or a deck, the looks not made from them stay in place and say why; the grid never changes shape", () => {
    expect(tiles(caps, { photos: true, deck: false }).map((t) => [t.option.id, t.state])).toEqual([["auto", "ok"], ["real", "ok"], ["whiteboard", "photos"], ["cartoon", "photos"]]);
    expect(tiles(caps, { photos: false, deck: true }).map((t) => t.state)).toEqual(["ok", "ok", "deck", "deck"]);
    const locked = parseLooks(looksWith("cartoon", { allowed: false, requires_plan: "pro" }))!;
    expect(tiles(locked, { photos: true, deck: false })[3].state).toBe("photos");   // what is attached is the nearer reason
  });
});

describe("choosing", () => {
  it("a tile; cast and extras start again for another look", () => {
    const c = chooseLook(AUTO, "cartoon", caps);
    expect(c).toEqual({ look: "cartoon", cast: "auto", extras: [] });
    expect(chooseLook(cartoon(["fox"], ["board"]), "real", caps)).toEqual({ look: "real", cast: "auto", extras: [] });
    expect(chooseLook(c, "cartoon", caps)).toBe(c);
  });
  it("a locked, hidden or unknown tile changes nothing", () => {
    const locked = parseLooks(looksWith("cartoon", { allowed: false }))!;
    expect(chooseLook(AUTO, "cartoon", locked)).toBe(AUTO);
    expect(chooseLook(AUTO, "cartoon", caps, { photos: true, deck: false })).toBe(AUTO);
    expect(chooseLook(AUTO, "clay", caps)).toBe(AUTO);
  });
  it("faces: one to three, a fourth is ignored, unticking the last is Auto again, Auto clears", () => {
    let c = toggleCast(cartoon(), "fox", caps);
    expect(c.cast).toEqual(["fox"]); expect(isConversation(c, caps)).toBe(false);
    c = toggleCast(c, "bear", caps); expect(c.cast).toEqual(["fox", "bear"]); expect(isConversation(c, caps)).toBe(true);
    c = toggleCast(c, "ines", caps); expect(c.cast).toEqual(["fox", "bear", "ines"]);
    expect(toggleCast(c, "owl", caps)).toBe(c);
    expect(toggleCast(c, "bear", caps).cast).toEqual(["fox", "ines"]);
    expect(toggleCast(cartoon(["fox"]), "fox", caps).cast).toBe("auto");
    expect(toggleCast(c, "auto", caps).cast).toBe("auto");
    expect(toggleCast(c, "nobody", caps)).toBe(c);
    expect(toggleCast({ look: "real", cast: "auto", extras: [] }, "fox", caps).cast).toBe("auto");   // only a look with a cast
  });
  it("the board switch, only for a look that lists it", () => {
    expect(toggleExtra(cartoon(), "board", caps).extras).toEqual(["board"]);
    expect(toggleExtra(cartoon("auto", ["board"]), "board", caps).extras).toEqual([]);
    expect(toggleExtra({ look: "real", cast: "auto", extras: [] }, "board", caps).extras).toEqual([]);
    const off = parseLooks(looksWith("cartoon", { extras: [{ id: "board", label: "Hand-drawn board", available: false }] }))!;
    expect(toggleExtra(cartoon(), "board", off).extras).toEqual([]);
  });
});

describe("a choice stays inside what the server lists", () => {
  it("unknown, unavailable or locked looks become Auto; unknown faces and extras are dropped", () => {
    expect(normalizeChoice({ look: "clay", cast: "auto", extras: [] }, caps).choice).toEqual(AUTO);
    expect(normalizeChoice(cartoon(), parseLooks(looksWith("cartoon", { available: false }))).choice).toEqual(AUTO);
    expect(normalizeChoice(cartoon(), parseLooks(looksWith("cartoon", { allowed: false }))).choice).toEqual(AUTO);
    expect(normalizeChoice(cartoon(["fox", "ghost", "fox", "bear", "owl", "cat"], ["board", "smoke"]), caps).choice).toEqual({ look: "cartoon", cast: ["fox", "bear", "owl"], extras: ["board"] });
    expect(normalizeChoice({ look: "real", cast: ["fox"], extras: ["board"] }, caps).choice).toEqual({ look: "real", cast: "auto", extras: [] });
    expect(normalizeChoice(cartoon(), undefined).choice).toEqual(AUTO);
    expect(normalizeChoice(null, caps).choice).toEqual(AUTO);
    expect(normalizeChoice("junk" as any, caps).choice).toEqual(AUTO);
  });
  it("photos or a deck attached after choosing: back to Auto, and it says why", () => {
    expect(normalizeChoice(cartoon(["fox"]), caps, { photos: true, deck: false })).toEqual({ choice: AUTO, reset: "photos" });
    expect(normalizeChoice({ look: "whiteboard", cast: "auto", extras: [] }, caps, { photos: false, deck: true })).toEqual({ choice: AUTO, reset: "deck" });
    expect(normalizeChoice({ look: "real", cast: "auto", extras: [] }, caps, { photos: true, deck: false })).toEqual({ choice: { look: "real", cast: "auto", extras: [] }, reset: null });
    expect(normalizeChoice(AUTO, caps, { photos: true, deck: false }).reset).toBeNull();
  });
});

describe("what is sent (docs/CREATE_API.md): look, cast, extras, and nothing on Auto", () => {
  it("Auto sends nothing at all", () => {
    expect(lookRequest(AUTO, caps)).toEqual({});
    expect(lookRequest(null, caps)).toEqual({});
    expect(lookRequest(cartoon(["fox"]), undefined)).toEqual({});   // a server without the picker never gets the keys
  });
  it("a look alone; cast only as a list of ids; extras only when on", () => {
    expect(lookRequest({ look: "real", cast: "auto", extras: [] }, caps)).toEqual({ look: "real" });
    expect(lookRequest({ look: "whiteboard", cast: "auto", extras: [] }, caps)).toEqual({ look: "whiteboard" });
    expect(lookRequest(cartoon(), caps)).toEqual({ look: "cartoon" });
    expect(lookRequest(cartoon(["fox"]), caps)).toEqual({ look: "cartoon", cast: ["fox"] });
    expect(lookRequest(cartoon(["fox", "bear"], ["board"]), caps)).toEqual({ look: "cartoon", cast: ["fox", "bear"], extras: ["board"] });
    expect(lookRequest(cartoon("auto", ["board"]), caps)).toEqual({ look: "cartoon", extras: ["board"] });
  });
  it("never a cast with real or whiteboard, never a look that cannot go with the photos", () => {
    expect(lookRequest({ look: "real", cast: ["fox"], extras: ["board"] }, caps)).toEqual({ look: "real" });
    expect(lookRequest(cartoon(["fox"]), caps, { photos: true, deck: false })).toEqual({});
  });
});

describe("the pill and the gentle advice", () => {
  it("the pill: the look's own label and the faces picked", () => {
    expect(pillOf(AUTO, caps)).toMatchObject({ label: "Auto", faces: [], names: "" });
    const p = pillOf(cartoon(["fox", "ines"]), caps);
    expect(p.label).toBe("Cartoon"); expect(p.names).toBe("Fox, Inés"); expect(p.faces).toHaveLength(2);
  });
  it("minimum length, a conversation that needs a longer video, the best shapes: advice, never a block", () => {
    const c = parseLooks(looksWith("whiteboard", { min_seconds: 30 }))!;
    expect(lookHints({ look: "whiteboard", cast: "auto", extras: [] }, c, 15, "9:16")).toEqual({ minSeconds: 30, conversationSeconds: null, bestAspects: ["16:9", "1:1"] });
    expect(lookHints({ look: "whiteboard", cast: "auto", extras: [] }, c, 30, "16:9")).toEqual({ minSeconds: null, conversationSeconds: null, bestAspects: null });
    expect(lookHints(cartoon(["fox", "bear"]), caps, 15, "16:9").conversationSeconds).toBe(20);
    expect(lookHints(cartoon(["fox"]), caps, 15, "16:9").conversationSeconds).toBeNull();
    expect(lookHints(cartoon(["fox", "bear"]), caps, 30, "16:9").conversationSeconds).toBeNull();
    expect(lookHints(AUTO, caps, 1, "9:16")).toEqual({ minSeconds: null, conversationSeconds: null, bestAspects: null });
  });
  it("the shortest preset that is long enough, inside the plan", () => {
    const presets = [0.25, 0.5, 0.75, 1, 2];
    expect(presetFor(20, presets)).toBe(0.5);
    expect(presetFor(60, presets)).toBe(1);
    expect(presetFor(40, presets, 30)).toBeNull();   // the plan's longest video is too short: no offer
    expect(presetFor(999, presets)).toBeNull();
  });
});

describe("remembered on this device, and what the answers say", () => {
  it("a saved choice is read back safely", () => {
    expect(parseSavedLook(JSON.stringify(cartoon(["fox"], ["board"])))).toEqual(cartoon(["fox"], ["board"]));
    expect(parseSavedLook(JSON.stringify({ look: "real" }))).toEqual({ look: "real", cast: "auto", extras: [] });
    for (const bad of [null, "", "{", "[]", "7", JSON.stringify({ cast: ["fox"] })]) expect(parseSavedLook(bad)).toBeNull();
  });
  it("note and look are optional on every answer", () => {
    expect(parseLookAnswer({ message: "workflow started", video_id: "v" })).toBeNull();
    expect(parseLookAnswer(null)).toBeNull();
    expect(parseLookAnswer({ note: "Made from your photos: the Cartoon look is not used with your own photos.", look: { chosen: "cartoon", applied: "real", enforced: false, reason: "own_photos" } }))
      .toEqual({ note: "Made from your photos: the Cartoon look is not used with your own photos.", chosen: "cartoon", applied: "real", enforced: false, reason: "own_photos" });
    expect(parseLookAnswer({ look: { style: "auto", asked: ["cartoon"], adapted: [] } })).toBeNull();   // the older shape: nothing to show
  });
  it("the note of a video being made is kept by video, newest first, at most 20", () => {
    let list = withNote([], "a", " one ");
    list = withNote(list, "b", "two"); list = withNote(list, "a", "three");
    expect(list).toEqual([["a", "three"], ["b", "two"]]);
    expect(withNote(list, "", "x")).toBe(list); expect(withNote(list, "c", "  ")).toBe(list);
    for (let i = 0; i < 30; i++) list = withNote(list, `v${i}`, "n");
    expect(list).toHaveLength(20);
  });
  it("the video record's look", () => {
    expect(parseVideoLook({ chosen: "auto", applied: "whiteboard", recipe: "whiteboard", cast: [], extras: [], why: "A step-by-step process is clearest drawn.", by: "auto", share: 0.94, repaired: 1, reason: null }))
      .toEqual({ chosen: "auto", applied: "whiteboard", recipe: "whiteboard", cast: [], extras: [], why: "A step-by-step process is clearest drawn.", by: "auto" });
    expect(parseVideoLook({ applied: "cartoon", cast: ["fox", 7, "bear"], extras: ["board"] })).toEqual({ applied: "cartoon", cast: ["fox", "bear"], extras: ["board"] });
    for (const bad of [null, undefined, {}, "x", { chosen: "auto" }]) expect(parseVideoLook(bad)).toBeNull();
  });
});
