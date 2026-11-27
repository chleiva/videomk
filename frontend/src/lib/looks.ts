// The video look: one chosen, enforced look per video (docs/CREATE_API.md "Video look (chosen and enforced)"). Auto, Real, Whiteboard, Cartoon; Cartoon has a cast
// of 1 to 3 characters (2 or 3 = a conversation) and may have the hand-drawn board. Everything shown comes from `capabilities.looks`: the tiles, the previews, the cast.
// Pure functions (tested in looks.test.ts). Decoding is lenient: a server that sends less, or nothing, leaves the app exactly as it was before the picker.

export interface LookExtra { id: string; label: string; note?: string; available: boolean }
export interface LookOption {
  id: string; label: string; note?: string; preview?: string;
  available: boolean; allowed: boolean; requires_plan: string | null;
  with_photos: boolean; with_deck: boolean; min_seconds: number;
  aspects: string[] | null; best_aspects: string[] | null;   // null: the server did not say (then every shape is fine)
  cast: boolean; extras: LookExtra[];
}
export interface CastMember { id: string; name: string; role?: string; kind?: "person" | "animal"; topic?: string; thumbnail?: string }
export interface CastCaps {
  min: number; max: number;
  auto: { label?: string; note?: string };
  conversation: { from: number; min_seconds: number; note?: string } | null;
  members: CastMember[];
}
export interface LooksCaps { default: string; options: LookOption[]; cast: CastCaps | null }

/** What the person chose. `cast` and `extras` only mean something for a look that lists them. */
export interface LookChoice { look: string; cast: "auto" | string[]; extras: string[] }
export const AUTO: LookChoice = { look: "auto", cast: "auto", extras: [] };

const str = (v: unknown, max = 160): string | undefined => { const s = typeof v === "string" ? v.trim() : ""; return s ? s.slice(0, max) : undefined; };
const ids = (v: unknown): string[] | null => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string" && !!x) : null);
/** A picture from the server is drawn only when it is an image data URI or an https link (never script, never another scheme). */
export function safeImage(v: unknown): string | undefined {
  return typeof v === "string" && (/^data:image\/(jpeg|jpg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(v) || /^https:\/\/[^\s"'<>]+$/.test(v)) ? v : undefined;
}

/** `capabilities.looks` -> the picker's data, or undefined when the server has no chosen looks yet (then today's behaviour stays). */
export function parseLooks(raw: unknown): LooksCaps | undefined {
  const look = (raw as any)?.look;
  if (!look || typeof look !== "object" || !Array.isArray(look.options)) return undefined;
  const seen = new Set<string>();
  const options: LookOption[] = look.options.flatMap((o: any): LookOption[] => {
    const id = str(o?.id, 40), label = str(o?.label, 40);
    if (!id || !label || seen.has(id)) return [];
    seen.add(id);
    const extras: LookExtra[] = (Array.isArray(o.extras) ? o.extras : []).flatMap((e: any): LookExtra[] => {
      const eid = str(e?.id, 40), el = str(e?.label, 60);
      return eid && el ? [{ id: eid, label: el, note: str(e?.note), available: e?.available !== false }] : [];
    });
    const min = Number(o.min_seconds);
    return [{
      id, label, note: str(o.note), preview: safeImage(o.preview),
      available: o.available !== false, allowed: o.allowed !== false, requires_plan: str(o.requires_plan, 40) ?? null,
      with_photos: o.with_photos !== false, with_deck: o.with_deck !== false, min_seconds: Number.isFinite(min) && min > 0 ? min : 0,
      aspects: ids(o.aspects), best_aspects: ids(o.best_aspects), cast: o.cast === true, extras,
    }];
  }).slice(0, 4);   // at most four tiles
  if (!options.some((o) => o.id === "auto") || options.length < 2) return undefined;   // nothing to choose between
  return { default: options.some((o) => o.id === look.default) ? look.default : "auto", options, cast: parseCast((raw as any)?.cast) };
}

function parseCast(raw: any): CastCaps | null {
  if (!raw || typeof raw !== "object" || raw.available === false || !Array.isArray(raw.members)) return null;
  const seen = new Set<string>();
  const members: CastMember[] = raw.members.flatMap((m: any): CastMember[] => {
    const id = str(m?.id, 40), name = str(m?.name, 40);
    if (!id || !name || id === "auto" || seen.has(id)) return [];
    seen.add(id);
    return [{ id, name, role: str(m.role, 60), kind: m.kind === "person" || m.kind === "animal" ? m.kind : undefined, topic: str(m.topic, 60), thumbnail: safeImage(m.thumbnail) }];
  });
  if (!members.length) return null;
  const max = Math.max(1, Math.min(members.length, Number.isFinite(Number(raw.max)) && Number(raw.max) >= 1 ? Math.floor(Number(raw.max)) : 3));
  const c = raw.conversation, from = Number(c?.from), cmin = Number(c?.min_seconds);
  return {
    min: 1, max,
    auto: { label: str(raw.auto?.label, 40), note: str(raw.auto?.note) },
    conversation: c && typeof c === "object" ? { from: Number.isFinite(from) && from >= 2 ? Math.floor(from) : 2, min_seconds: Number.isFinite(cmin) && cmin > 0 ? cmin : 0, note: str(c.note) } : null,
    members,
  };
}

export const optionOf = (caps: LooksCaps | undefined, id: string): LookOption | undefined => caps?.options.find((o) => o.id === id);
/** People first, then animals, each in the server's order (the picker groups them). */
export function castGroups(cast: CastCaps | null): CastMember[][] {
  if (!cast) return [];
  const people = cast.members.filter((m) => m.kind !== "animal"), animals = cast.members.filter((m) => m.kind === "animal");
  return [people, animals].filter((g) => g.length);
}

// ---------------------------------------------------------------- what the picker offers
export interface LookContext { photos: boolean; deck: boolean }
export type TileState = "ok" | "locked";
export interface Tile { option: LookOption; state: TileState }
/** The tiles to draw, in the server's order: a look this stage does not have is hidden, one that cannot go with the attached photos or deck is not offered,
 *  one the plan does not allow is shown locked (with the plan's name). Auto is always there. */
export function tiles(caps: LooksCaps, ctx: LookContext): Tile[] {
  return caps.options
    .filter((o) => o.id === "auto" || (o.available && (!ctx.photos || o.with_photos) && (!ctx.deck || o.with_deck)))
    .map((o) => ({ option: o, state: o.allowed || o.id === "auto" ? "ok" : "locked" }));
}
/** True when attached photos or a deck took some looks away (the picker then says so in one line). */
export function narrowed(caps: LooksCaps, ctx: LookContext): boolean {
  return caps.options.some((o) => o.id !== "auto" && o.available && ((ctx.photos && !o.with_photos) || (ctx.deck && !o.with_deck)));
}

/** Keeps a choice inside what the server lists right now. `reset` says why a chosen look fell back to Auto (photos or a deck were attached afterwards). */
export function normalizeChoice(choice: LookChoice | null | undefined, caps: LooksCaps | undefined, ctx: LookContext = { photos: false, deck: false }): { choice: LookChoice; reset: "photos" | "deck" | null } {
  const o = caps && choice ? optionOf(caps, choice.look) : undefined;
  if (!caps || !choice || !o || o.id === "auto") return { choice: AUTO, reset: null };
  if (!o.available || !o.allowed) return { choice: AUTO, reset: null };
  if (ctx.photos && !o.with_photos) return { choice: AUTO, reset: "photos" };
  if (ctx.deck && !o.with_deck) return { choice: AUTO, reset: "deck" };
  let cast: LookChoice["cast"] = "auto";
  if (o.cast && caps.cast && Array.isArray(choice.cast)) {
    const known = [...new Set(choice.cast)].filter((id) => caps.cast!.members.some((m) => m.id === id)).slice(0, caps.cast.max);
    if (known.length) cast = known;
  }
  const extras = [...new Set(Array.isArray(choice.extras) ? choice.extras : [])].filter((id) => o.extras.some((e) => e.id === id && e.available));
  return { choice: { look: o.id, cast, extras }, reset: null };
}

/** Choosing a tile. Returns the same choice when the tile cannot be chosen (locked, hidden). Cast and extras start again at their defaults for another look. */
export function chooseLook(choice: LookChoice, id: string, caps: LooksCaps, ctx: LookContext = { photos: false, deck: false }): LookChoice {
  if (choice.look === id) return choice;
  const t = tiles(caps, ctx).find((x) => x.option.id === id);
  return t && t.state === "ok" ? { look: id, cast: "auto", extras: [] } : choice;
}

/** Ticking a face: "auto" clears the picks; a face is added up to `max` (a fourth is ignored) or removed; none left means Auto again. */
export function toggleCast(choice: LookChoice, id: string, caps: LooksCaps): LookChoice {
  const cast = caps.cast;
  if (!cast || !optionOf(caps, choice.look)?.cast) return choice;
  if (id === "auto") return { ...choice, cast: "auto" };
  if (!cast.members.some((m) => m.id === id)) return choice;
  const now = Array.isArray(choice.cast) ? choice.cast : [];
  if (now.includes(id)) { const rest = now.filter((x) => x !== id); return { ...choice, cast: rest.length ? rest : "auto" }; }
  return now.length >= cast.max ? choice : { ...choice, cast: [...now, id] };
}
export const castCount = (c: LookChoice): number => (Array.isArray(c.cast) ? c.cast.length : 0);
export const castFull = (c: LookChoice, caps: LooksCaps): boolean => !!caps.cast && castCount(c) >= caps.cast.max;
export const isConversation = (c: LookChoice, caps: LooksCaps): boolean => !!caps.cast?.conversation && castCount(c) >= caps.cast.conversation.from;

export function toggleExtra(choice: LookChoice, id: string, caps: LooksCaps): LookChoice {
  if (!optionOf(caps, choice.look)?.extras.some((e) => e.id === id && e.available)) return choice;
  return { ...choice, extras: choice.extras.includes(id) ? choice.extras.filter((x) => x !== id) : [...choice.extras, id] };
}

// ---------------------------------------------------------------- what is sent
/** The keys for `generate` and for `options` of `brief`: nothing at all on Auto; `look`; `cast` only as a list of ids; `extras` only when one is on. */
export function lookRequest(choice: LookChoice | null | undefined, caps: LooksCaps | undefined, ctx: LookContext = { photos: false, deck: false }): { look?: string; cast?: string[]; extras?: string[] } {
  const c = normalizeChoice(choice, caps, ctx).choice;
  if (c.look === "auto") return {};
  return { look: c.look, ...(Array.isArray(c.cast) && c.cast.length ? { cast: c.cast } : {}), ...(c.extras.length ? { extras: c.extras } : {}) };
}

// ---------------------------------------------------------------- what the pill and the hints say
/** The pill: the look's own label and the faces picked (drawn as small pictures; `names` is what a screen reader hears). */
export function pillOf(choice: LookChoice, caps: LooksCaps): { label: string; faces: CastMember[]; names: string } {
  const o = optionOf(caps, choice.look) ?? optionOf(caps, "auto")!;
  const faces = o.cast && Array.isArray(choice.cast) ? choice.cast.flatMap((id) => caps.cast?.members.find((m) => m.id === id) ?? []) : [];
  return { label: o.label, faces, names: faces.map((m) => m.name).join(", ") };
}

export interface LookHints { minSeconds: number | null; conversationSeconds: number | null; bestAspects: string[] | null }
/** Gentle advice for the chosen look against the chosen length and shape: never a block (the server adapts and says so).
 *  minSeconds: the look needs a longer video; conversationSeconds: a conversation was picked for a video too short for one; bestAspects: where it looks best. */
export function lookHints(choice: LookChoice, caps: LooksCaps | undefined, seconds: number, aspect: string): LookHints {
  const o = caps ? optionOf(caps, choice.look) : undefined;
  if (!caps || !o || o.id === "auto") return { minSeconds: null, conversationSeconds: null, bestAspects: null };
  const conv = caps.cast?.conversation;
  return {
    minSeconds: o.min_seconds > seconds + 1e-6 ? o.min_seconds : null,
    conversationSeconds: conv && isConversation(choice, caps) && conv.min_seconds > seconds + 1e-6 ? conv.min_seconds : null,
    bestAspects: o.best_aspects && o.best_aspects.length && !o.best_aspects.includes(aspect) ? o.best_aspects : null,
  };
}
/** The shortest preset that is long enough for `seconds` (and inside the plan when a limit is given), or null. */
export function presetFor(seconds: number, presets: number[], planMaxSeconds?: number | null): number | null {
  return presets.find((m) => m * 60 + 1e-6 >= seconds && (planMaxSeconds == null || m * 60 <= planMaxSeconds + 1e-6)) ?? null;
}

// ---------------------------------------------------------------- remembered on this device (a convenience; never needed to work)
const KEY = "vmk_look_choice";
export function parseSavedLook(raw: string | null | undefined): LookChoice | null {
  try {
    const v = JSON.parse(String(raw));
    if (!v || typeof v.look !== "string") return null;
    return { look: v.look.slice(0, 40), cast: Array.isArray(v.cast) ? v.cast.filter((x: unknown) => typeof x === "string").slice(0, 3) : "auto", extras: Array.isArray(v.extras) ? v.extras.filter((x: unknown) => typeof x === "string").slice(0, 4) : [] };
  } catch { return null; }
}
export function loadLook(): LookChoice | null { try { return parseSavedLook(localStorage.getItem(KEY)); } catch { return null; } }
export function saveLook(c: LookChoice): void { try { localStorage.setItem(KEY, JSON.stringify(c)); } catch { /* private mode: the choice lasts for this visit */ } }

// ---------------------------------------------------------------- what the answers say (`note`, `look` on brief and on the 202 of generate; both optional)
export interface LookAnswer { note?: string; chosen?: string; applied?: string; enforced?: boolean; reason?: string }
export function parseLookAnswer(body: unknown): LookAnswer | null {
  const b = body as any, l = b?.look && typeof b.look === "object" ? b.look : null;
  const out: LookAnswer = {
    ...(str(b?.note, 300) ? { note: str(b.note, 300) } : {}),
    ...(str(l?.chosen, 40) ? { chosen: str(l.chosen, 40) } : {}), ...(str(l?.applied, 40) ? { applied: str(l.applied, 40) } : {}),
    ...(typeof l?.enforced === "boolean" ? { enforced: l.enforced } : {}), ...(str(l?.reason, 40) ? { reason: str(l.reason, 40) } : {}),
  };
  return Object.keys(out).length ? out : null;
}

// The note of a video that is being made is only in the answer of `generate`, so the browser that started it keeps the sentence until the video is done
// (this device only, newest 20; the key starts with vmk_ so it is wiped with the rest of the local data).
const NOTES = "vmk_look_notes";
type NoteEntry = [id: string, note: string];
export function withNote(list: NoteEntry[], id: string, note: string): NoteEntry[] {
  const text = note.trim().slice(0, 300);
  return id && text ? [[id, text] as NoteEntry, ...list.filter((e) => e[0] !== id)].slice(0, 20) : list;
}
function readNotes(): NoteEntry[] {
  try { const a = JSON.parse(localStorage.getItem(NOTES) || "[]"); return Array.isArray(a) ? a.filter((e): e is NoteEntry => Array.isArray(e) && typeof e[0] === "string" && typeof e[1] === "string") : []; } catch { return []; }
}
export function rememberNote(id: string, note: string | undefined): void { if (!note) return; try { localStorage.setItem(NOTES, JSON.stringify(withNote(readNotes(), id, note))); } catch { /* the line is simply not shown */ } }
export function noteFor(id: string): string | null { return readNotes().find((e) => e[0] === id)?.[1] ?? null; }

// ---------------------------------------------------------------- the video record's `look` (list items and GET video; additive, optional)
export interface VideoLook { chosen?: string; applied: string; recipe?: string; cast: string[]; extras: string[]; why?: string; by?: "you" | "auto" }
export function parseVideoLook(raw: unknown): VideoLook | null {
  const r = raw as any;
  const applied = str(r?.applied, 40);
  if (!applied) return null;
  return {
    applied, ...(str(r.chosen, 40) ? { chosen: str(r.chosen, 40) } : {}), ...(str(r.recipe, 40) ? { recipe: str(r.recipe, 40) } : {}),
    cast: (ids(r.cast) ?? []).slice(0, 3), extras: (ids(r.extras) ?? []).slice(0, 4),
    ...(str(r.why, 240) ? { why: str(r.why, 240) } : {}), ...(r.by === "you" || r.by === "auto" ? { by: r.by } : {}),
  };
}
