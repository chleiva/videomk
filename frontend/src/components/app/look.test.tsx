// The Look picker, the locked Create and the look in a video's details, drawn against the documented contract (docs/CREATE_API.md "Video look", "Plans").
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup as html } from "react-dom/server";
import { LookPanel } from "./LookPicker";
import { LockedView } from "./CreateLocked";
import { lookSummary } from "../WatchPage";
import { AUTO, parseLooks } from "../../lib/looks";
import type { LookChoice, LookContext, LooksCaps } from "../../lib/looks";
import { LOOKS_FIXTURE, looksWith } from "../../lib/looks.fixture";
import { translate } from "../../lib/i18n";

const caps = parseLooks(LOOKS_FIXTURE)!;
const en = (k: string, p?: Record<string, string | number>) => translate(k, "en", p);
const es = (k: string, p?: Record<string, string | number>) => translate(k, "es", p);
const names: Record<string, string> = { pro: "Pro", max: "Max" };
const panel = (choice: LookChoice = AUTO, c: LooksCaps = caps, ctx: LookContext = { photos: false, deck: false }, t = en) =>
  html(<LookPanel caps={c} choice={choice} ctx={ctx} planName={(id) => (id ? names[id] ?? id : null)} onChange={() => {}} onDone={() => {}} t={t} />);
const count = (m: string, re: RegExp) => (m.match(re) ?? []).length;

describe("Look picker: the tiles", () => {
  it("four picture tiles in the server's order, a radio group, Auto chosen, each with its picture, label and one-line note", () => {
    const m = panel();
    expect(count(m, /role="radio"/g)).toBe(4);
    expect(m).toContain('role="radiogroup"');
    expect(m.indexOf("Auto")).toBeLessThan(m.indexOf("Real")); expect(m.indexOf("Real")).toBeLessThan(m.indexOf("Whiteboard")); expect(m.indexOf("Whiteboard")).toBeLessThan(m.indexOf("Cartoon"));
    expect(m).toMatch(/data-look="auto" aria-checked="true"/);
    expect(count(m, /aria-checked="true"/g)).toBe(1);
    expect(count(m, /<img src="data:image\/jpeg/g)).toBe(4);
    for (const note of ["We pick one look that suits your topic.", "Photos and video footage.", "Drawn by hand as it is explained.", "Cartoon characters explain it."]) expect(m).toContain(note);
    expect(m).toContain('aria-describedby="look-note-whiteboard"');
  });
  it("one tab stop in the group (arrow keys move inside it): the chosen tile", () => {
    const m = panel({ look: "whiteboard", cast: "auto", extras: [] });
    expect(count(m, /data-look="[a-z]+"[^>]*tabindex="0"/g)).toBe(1);
    expect(m).toMatch(/data-look="whiteboard" aria-checked="true" tabindex="0"/);
  });
  it("a look this stage does not have is not drawn", () => {
    const m = panel(AUTO, parseLooks(looksWith("whiteboard", { available: false }))!);
    expect(count(m, /role="radio"/g)).toBe(3); expect(m).not.toContain("Whiteboard"); expect(m).toContain('data-count="3"');
  });
  it("a look the plan does not allow is shown locked, quietly, with the plan's name, and cannot be chosen", () => {
    const m = panel(AUTO, parseLooks(looksWith("cartoon", { allowed: false, requires_plan: "pro" }))!);
    expect(m).toMatch(/data-look="cartoon" aria-checked="false" aria-disabled="true"/);
    expect(m).toContain("is-locked"); expect(m).toContain("Needs Pro"); expect(m).toContain(">Pro<");
    expect(m).not.toMatch(/upgrade|buy/i);   // nothing can be bought yet: no button
    expect(panel(AUTO, parseLooks(looksWith("cartoon", { allowed: false }))!)).toContain("Not on your plan");
  });
  it("with the person's photos (or a deck) the looks that are not made from them are not offered, and one line says why", () => {
    const m = panel(AUTO, caps, { photos: true, deck: false });
    expect(count(m, /role="radio"/g)).toBe(2); expect(m).not.toContain("Cartoon"); expect(m).not.toContain("Whiteboard");
    expect(m).toContain("Made from your photos, so only these looks apply.");
    expect(panel(AUTO, caps, { photos: false, deck: true })).toContain("Made from your slides, so only these looks apply.");
    expect(panel()).not.toContain("only these looks apply");
  });
});

describe("Look picker: the cast, in the same surface", () => {
  const cartoon = (cast: LookChoice["cast"] = "auto", extras: string[] = []): LookChoice => ({ look: "cartoon", cast, extras });
  it("is not there for Auto, Real or Whiteboard", () => {
    for (const look of ["auto", "real", "whiteboard"]) { const m = panel({ look, cast: "auto", extras: [] }); expect(m).not.toContain("look-cast"); expect(m).not.toContain('role="switch"'); }
  });
  it("Cartoon reveals Auto (chosen) and ten round faces with their names, people then animals", () => {
    const m = panel(cartoon());
    expect(m).toContain('role="group" aria-label="Cast"');
    expect(count(m, /data-face="/g)).toBe(10);
    expect(m).toMatch(/aria-pressed="true"[^>]*class="face face-auto is-on/);
    expect(count(m, /<img class="face-img" src="data:image\/png/g)).toBe(10);
    expect(m).toContain('aria-label="Fox, Guide for children"'); expect(m).toContain(">Inés<");
    expect(m.indexOf('data-face="mateo"')).toBeLessThan(m.indexOf("cast-sep")); expect(m.indexOf("cast-sep")).toBeLessThan(m.indexOf('data-face="fox"'));
    expect(m).toContain("We pick characters that suit the topic.");
  });
  it("one face: who it is; two or three: the server's conversation note, numbered in the order picked", () => {
    expect(panel(cartoon(["fox"]))).toContain("Guide for children · For children");
    const two = panel(cartoon(["bear", "fox"]));
    expect(two).toContain("Pick 2 or 3 and they talk it through together.");
    expect(count(two, /data-face="[a-z]+" aria-pressed="true"/g)).toBe(2);
    expect(two).toMatch(/data-face="bear"[\s\S]*?class="face-n"[^>]*>1</); expect(two).toMatch(/data-face="fox"[\s\S]*?class="face-n"[^>]*>2</);
    expect(two).not.toContain("is-dim");
  });
  it("at three the others are dimmed: no fourth", () => {
    const m = panel(cartoon(["fox", "bear", "ines"]));
    expect(count(m, /data-face="[a-z]+" aria-pressed="true"/g)).toBe(3);
    expect(count(m, /aria-pressed="false" aria-disabled="true"/g)).toBe(7);
  });
  it("the Hand-drawn board switch only when the look lists it as available", () => {
    const m = panel(cartoon("auto", ["board"]));
    expect(m).toContain("Hand-drawn board"); expect(m).toMatch(/role="switch"[^>]*checked=""/);
    expect(panel(cartoon())).toMatch(/role="switch"/); expect(panel(cartoon())).not.toMatch(/role="switch"[^>]*checked=""/);
    expect(panel(cartoon(), parseLooks(looksWith("cartoon", { extras: [] }))!)).not.toContain('role="switch"');
    expect(panel(cartoon(), parseLooks(looksWith("cartoon", { extras: [{ id: "board", label: "Hand-drawn board", available: false }] }))!)).not.toContain('role="switch"');
  });
  it("a server without a cast still offers Cartoon, with nothing to pick", () => {
    const m = panel(cartoon(), parseLooks({ look: LOOKS_FIXTURE.look })!);
    expect(m).toMatch(/data-look="cartoon" aria-checked="true"/); expect(m).not.toContain("look-cast");
  });
});

describe("words: few, and in both languages", () => {
  const words = (s: string) => s.trim().split(/\s+/).filter(Boolean).length;
  const KEYS = ["create.pick_a11y", "create.pick_cast", "create.pick_from_photos", "create.pick_from_deck", "create.pick_reset_photos", "create.pick_reset_deck", "create.pick_min", "create.pick_use", "create.pick_talk_min", "create.pick_best",
    "create.plan_needs", "create.plan_locked", "create.colors", "create.locked_fallback", "create.locked_plan", "create.locked_soon", "create.showcase", "making.cancel", "making.cancel_title", "making.cancel_body", "making.cancel_keep", "making.cancel_stop",
    "making.cancelled", "making.cancel_done", "making.cancel_error", "making.cancel_unsupported", "gen.cancelled_detail", "gen.delete", "gen.deleted", "gen.undo", "gen.delete_error", "watch.look", "watch.look_auto", "watch.delete", "wallet.plan", "wallet.plan_length", "wallet.bucket.plan"];
  it("every new line exists in English and in Spanish", () => {
    for (const k of KEYS) { expect(en(k), k).not.toBe(k); expect(es(k), k).not.toBe(k); }
    expect(es("create.pick_cast")).toBe("Personajes");
    expect(en("making.cancelled_refund", { n: 1 })).toBe("Cancelled. 1 credit is back."); expect(en("making.cancelled_refund", { n: 2 })).toBe("Cancelled. 2 credits are back.");
    expect(es("making.cancelled_refund", { n: 2 })).toBe("Cancelado. 2 créditos recuperados.");
  });
  it("the picker itself adds at most 3 fixed words (the title, Done, Cast): the rest is the server's", () => {
    for (const t of [en, es]) expect(words(t("create.pill_look")) + words(t("create.done")) + words(t("create.pick_cast"))).toBeLessThanOrEqual(3);
  });
  it("draws in Spanish with the server's Spanish labels", () => {
    const c = parseLooks({ ...LOOKS_FIXTURE, look: { ...LOOKS_FIXTURE.look, options: LOOKS_FIXTURE.look.options.map((o) => (o.id === "cartoon" ? { ...o, label: "Dibujos animados", note: "Personajes de dibujos lo explican." } : o)) } })!;
    const m = panel({ look: "cartoon", cast: "auto", extras: [] }, c, { photos: false, deck: false }, es);
    expect(m).toContain("Dibujos animados"); expect(m).toContain('aria-label="Personajes"'); expect(m).toContain(">Listo<");
  });
});

describe("Create when the account cannot make a video right now", () => {
  const videos = [{ id: "forest", title: "How a forest breathes", video_url: "https://cdn/x.mp4", poster_url: "https://cdn/x.jpg", aspect: "16:9", seconds: 28 }, { id: "short", title: "Three focus tips", video_url: "https://cdn/y.mp4", poster_url: null, aspect: "9:16", seconds: 15 }];
  it("the server's sentence, the plan's name, the showcase, and no buy button", () => {
    const m = html(<LockedView lock={{ message: "Free videos are made in the VideoMK app.", reason: "app_only" }} plan="Free" videos={videos} t={en} />);
    expect(m).toContain("Free videos are made in the VideoMK app."); expect(m).toContain("Free plan · Paid plans are coming soon.");
    expect(m).toContain("Made with VideoMK"); expect(count(m, /class="show-tile"/g)).toBe(2);
    expect(m).toContain('aria-label="Watch How a forest breathes"'); expect(m).toContain("0:28");
    expect(m).not.toContain("<form"); expect(m).not.toContain("<textarea"); expect(m).not.toMatch(/upgrade|buy|subscribe/i);
  });
  it("without a message or a showcase it still says something true", () => {
    const m = html(<LockedView lock={{}} plan={null} videos={[]} t={es} />);
    expect(m).toContain("Crear videos no está disponible en esta cuenta por ahora."); expect(m).toContain("Los planes de pago llegarán pronto."); expect(m).not.toContain("showcase");
  });
});

describe("the look in a video's details", () => {
  it("the server's names when capabilities has them, the ids with a capital otherwise", () => {
    expect(lookSummary({ applied: "whiteboard", cast: [], extras: [] }, caps)).toBe("Whiteboard");
    expect(lookSummary({ applied: "cartoon", cast: ["fox", "ines"], extras: ["board"] }, caps)).toBe("Cartoon · Fox, Inés · Hand-drawn board");
    expect(lookSummary({ applied: "cartoon", cast: ["fox"], extras: ["board"] }, null)).toBe("Cartoon · Fox");
  });
});
