// The Create form's logic (docs/CREATE_API.md): what the server offers (capabilities), the choices, the price, the request check (brief) and the options sent to generate.
// Pure functions first (tested in create.test.ts); the network calls below. The web works with only what capabilities lists; with none it falls back to 16:9 and 1080p.
import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";
import { currentLocaleHeaders } from "./i18n";
import { AUTO, lookRequest, normalizeChoice, parseLooks } from "./looks";
import type { LookChoice, LookContext, LooksCaps } from "./looks";
import { lengthLock, parseLengthLimits, parsePlanState } from "./plan";
import type { LengthLimits, PlanState } from "./plan";

export interface Aspect { id: string; label: string; ready: boolean; beta?: boolean }
export interface Resolution { id: string; label: string; credits_multiplier: number; aspects: string[]; note?: string; available?: boolean; requires_plan?: string | null }   // available false: the plan does not make it (shown locked with the plan's name)
export interface Platform { id: string; label: string; aspect: string; resolution: string; recommended_minutes: number; max_minutes: number | null; other_aspects?: string[]; note?: string; supports_4k?: boolean; note_4k?: string | null }
export interface Capabilities {
  aspects: Aspect[]; resolutions: Resolution[]; platforms: Platform[]; languages: { id: string; label: string }[];
  lengths: { min_minutes: number; max_minutes: number; presets: number[] }; max_photos?: number; intake?: boolean; deck?: DeckCaps; watermark?: WatermarkCaps;
  looks?: LooksCaps;        // the chosen, enforced look (docs/CREATE_API.md "Video look"); absent on a server without it: the Look pill is then the colour theme, as before
  limits?: LengthLimits;    // the plan's longest video and the lengths over it (docs/PLANS.md); absent: no plan limit
  plans?: PlanState;        // plan, free, can_upgrade
}

/** `capabilities.watermark` (docs/WATERMARK.md): present only where the stack has the feature on. Modes carry `available` (false: locked or hidden) and `requires`. */
export interface WatermarkMode { id: "none" | "videomk" | "custom"; label: string; available: boolean; requires?: string }
export interface WatermarkCaps { modes: WatermarkMode[]; forced: boolean; premium: boolean }
export function parseWatermarkCaps(raw: any): WatermarkCaps | undefined {
  if (!raw || !Array.isArray(raw.modes)) return undefined;
  const modes: WatermarkMode[] = raw.modes.filter((m: any) => m && (m.id === "none" || m.id === "videomk" || m.id === "custom") && typeof m.label === "string")
    .map((m: any) => ({ id: m.id, label: m.label, available: m.available !== false, requires: typeof m.requires === "string" ? m.requires : undefined }));
  return modes.length ? { modes, forced: raw.forced === true, premium: raw.premium === true } : undefined;
}
/** The scene style the person can pick for this video (docs/VECTOR_SCENE_POLICY.md section 7): auto sends nothing. */
export type SceneStyle = "auto" | "cartoon" | "real";
export const LOOKS = ["auto", "midnight", "paper", "sunrise"] as const;
export type Look = (typeof LOOKS)[number];
export type WatermarkChoice = "none" | "videomk" | "custom";

/** `capabilities.deck`: present only when the server enables decks (docs/CREATE_API.md). */
export interface DeckCaps { max_mb: number; max_slides: number; formats: string[] }
export function parseDeckCaps(raw: any): DeckCaps | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const formats = Array.isArray(raw.formats) ? raw.formats.filter((f: unknown) => f === "pptx" || f === "pdf") : [];
  const max_mb = Number(raw.max_mb), max_slides = Number(raw.max_slides);
  if (!formats.length || !Number.isFinite(max_mb) || max_mb <= 0 || !Number.isFinite(max_slides) || max_slides <= 0) return undefined;
  return { max_mb, max_slides, formats };
}

/** What the form offers when the server cannot say (not deployed yet, offline): 16:9, 1080p, a few lengths, no request check. */
export const FALLBACK_CAPS: Capabilities = {
  aspects: [{ id: "16:9", label: "Landscape", ready: true }],
  resolutions: [{ id: "1080p", label: "1080p", credits_multiplier: 1, aspects: ["16:9"] }],
  platforms: [], languages: [],
  lengths: { min_minutes: 0.25, max_minutes: 12, presets: [0.5, 1, 2, 3, 5] }, intake: false,
};

export interface Form {
  text: string; platform: string; aspect: string; resolution: string; minutes: number; captions: boolean; language: string;
  look: Look; scenes: SceneStyle; watermark: WatermarkChoice | null;   // look (the colour theme) auto and scenes auto send nothing; watermark null = the saved default applies (nothing is sent)
  pick: LookChoice;   // the video look chosen in the picker: Auto sends nothing
}

const readyAspects = (c: Capabilities) => c.aspects.filter((a) => a.ready);

export function platformOf(c: Capabilities, id: string): Platform | undefined { return c.platforms.find((p) => p.id === id); }
export function resolutionOf(c: Capabilities, id: string): Resolution | undefined { return c.resolutions.find((r) => r.id === id); }

/** The resolutions the chosen aspect can be made in (the pair must not be offered otherwise). */
export function resolutionsFor(c: Capabilities, aspect: string): Resolution[] { return c.resolutions.filter((r) => !r.aspects || r.aspects.includes(aspect)); }
/** The same, without the ones the plan locks: what may actually be chosen. */
const openResolutions = (c: Capabilities, aspect: string): Resolution[] => resolutionsFor(c, aspect).filter((r) => r.available !== false);
/** The longest preset the plan makes (null: no plan limit, or no preset fits). */
export function planMaxPreset(c: Capabilities): number | null {
  if (!c.limits) return null;
  const ok = c.lengths.presets.filter((m) => !lengthLock(m, c.limits));
  return ok.length < c.lengths.presets.length && ok.length ? Math.max(...ok) : null;
}

/** What the Options popover offers as quality: the aspect's resolutions, without the paid-up ones on a platform that does not show them (YouTube and general keep 4K). */
export function qualityChoices(c: Capabilities, f: Pick<Form, "aspect" | "platform">): Resolution[] {
  const plat = platformOf(c, f.platform);
  return resolutionsFor(c, f.aspect).filter((r) => r.credits_multiplier <= 1 || !plat || plat.supports_4k !== false);
}

/** Keeps every choice inside what the server lists; a choice that is no longer offered moves to the nearest valid one. */
export function normalize(f: Form, c: Capabilities): Form {
  const out = { ...f };
  const aspects = readyAspects(c);
  if (!aspects.some((a) => a.id === out.aspect)) out.aspect = aspects[0]?.id ?? "16:9";
  const res = openResolutions(c, out.aspect).length ? openResolutions(c, out.aspect) : resolutionsFor(c, out.aspect);   // a resolution the plan locks is never kept
  if (!res.some((r) => r.id === out.resolution)) out.resolution = res.find((r) => r.id === "1080p")?.id ?? res[res.length - 1]?.id ?? "1080p";
  if (c.platforms.length && !platformOf(c, out.platform)) out.platform = (platformOf(c, "other") ?? c.platforms[0]).id;
  out.minutes = clampMinutes(out.minutes, c);
  if (lengthLock(out.minutes, c.limits)) out.minutes = planMaxPreset(c) ?? out.minutes;   // over the plan's longest video: the longest it makes
  out.pick = normalizeChoice(out.pick, c.looks).choice;
  if (out.language !== "auto" && !c.languages.some((l) => l.id === out.language)) out.language = "auto";
  if (!LOOKS.includes(out.look)) out.look = "auto";
  if (out.scenes !== "cartoon" && out.scenes !== "real") out.scenes = "auto";
  if (out.watermark !== null && !(c.watermark?.modes.find((m) => m.id === out.watermark)?.available)) out.watermark = null;
  // 4K is offered for the platforms that show it (YouTube, general): a platform that does not (supports_4k false) never keeps a 4K choice
  const plat = platformOf(c, out.platform);
  if (plat && plat.supports_4k === false && (resolutionOf(c, out.resolution)?.credits_multiplier ?? 1) > 1) out.resolution = resolutionsFor(c, out.aspect).find((r) => r.id === plat.resolution)?.id ?? resolutionsFor(c, out.aspect).find((r) => r.credits_multiplier === 1)?.id ?? out.resolution;
  return out;
}

export function clampMinutes(m: number, c: Capabilities): number {
  const { min_minutes: lo, max_minutes: hi, presets } = c.lengths;
  if (!Number.isFinite(m)) return presets.includes(1) ? 1 : presets[0] ?? lo;
  return Math.min(hi, Math.max(lo, m));
}

export function defaultForm(c: Capabilities, saved?: Partial<Form> | null): Form {
  const p = platformOf(c, saved?.platform ?? "other") ?? platformOf(c, "other") ?? c.platforms[0];
  const base: Form = { text: "", platform: p?.id ?? "other", aspect: p?.aspect ?? "16:9", resolution: p?.resolution ?? "1080p", minutes: p?.recommended_minutes ?? 1, captions: true, language: "auto", look: "auto", scenes: "auto", watermark: null, pick: AUTO };
  return normalize({ ...base, ...(saved ?? {}), text: "" }, c);
}

/** Picking a platform preselects its format, resolution and recommended length (the person can still change each). */
export function selectPlatform(f: Form, c: Capabilities, id: string): Form {
  const p = platformOf(c, id);
  if (!p) return f;
  return normalize({ ...f, platform: id, aspect: p.aspect, resolution: p.resolution, minutes: p.recommended_minutes }, c);
}

/** The price before the tap: started minutes (at least 1) times the resolution's multiplier, the same number the server charges. */
export function creditsFor(minutes: number, resolution: string, c: Capabilities): number {
  const mult = resolutionOf(c, resolution)?.credits_multiplier ?? 1;
  return Math.max(1, Math.min(c.lengths.max_minutes, Math.ceil(Math.round(minutes * 1e6) / 1e6))) * mult;
}

/** 4K chosen on a platform that does not show 4K: the server's sentence (a recommendation, never a block). */
export function fourKAdvice(f: Form, c: Capabilities): string | null {
  const r = resolutionOf(c, f.resolution);
  const p = platformOf(c, f.platform);
  return r && r.credits_multiplier > 1 && p && p.supports_4k === false && p.note_4k ? p.note_4k : null;
}

/** "15 s", "45 s", "1 min", "2 min": same abbreviations in English and Spanish (docs/I18N.md rule 7). */
export function lengthLabel(minutes: number): string {
  return minutes < 1 ? `${Math.round(minutes * 60)} s` : `${Number.isInteger(minutes) ? minutes : Math.round(minutes * 10) / 10} min`;
}

/** A soft limit of the platform ("TikTok videos can be longer"): true when the chosen length is above it. */
export function overPlatformLimit(f: Form, c: Capabilities): number | null {
  const p = platformOf(c, f.platform);
  return p?.max_minutes != null && f.minutes > p.max_minutes ? p.max_minutes : null;
}

/** The fields generate and brief accept next to the prompt. With no capabilities from the server nothing but the length is sent. */
export function buildOptions(f: Form, c: Capabilities, live: boolean, ctx?: LookContext): Record<string, unknown> {
  if (!live) return { target_minutes: f.minutes };
  return {
    platform: f.platform, aspect: f.aspect, resolution: f.resolution, captions: f.captions, language: f.language, target_minutes: f.minutes,
    ...(f.look !== "auto" ? { theme: f.look } : {}),
    ...(c.looks ? lookRequest(f.pick, c.looks, ctx) : f.scenes !== "auto" ? { style: f.scenes } : {}),   // the picker replaces the older `style`: with it only look, cast, extras are sent
    ...(f.watermark && c.watermark ? { watermark: { mode: f.watermark } } : {}),   // only when the person changed it for this video: otherwise the saved default applies
  };
}

// ---------------------------------------------------------------- the composer's summary pills and the length menu
/** Text of each of the three pills: For, Length, Look. */
export function pillValues(f: Form, c: Capabilities, otherLabel: string): { for: string; length: string; look: Look } {
  const p = platformOf(c, f.platform);
  return { for: p && p.id !== "other" ? p.label : otherLabel, length: lengthLabel(f.minutes), look: f.look };
}

/** Rows of the Length menu: each preset with its credit price, greyed over the platform's soft limit. */
export function lengthMenu(c: Capabilities, f: Pick<Form, "platform" | "resolution">): { minutes: number; credits: number; over: boolean; locked: { requires: string | null } | false }[] {
  const max = platformOf(c, f.platform)?.max_minutes ?? null;
  return c.lengths.presets.map((m) => ({ minutes: m, credits: creditsFor(m, f.resolution, c), over: max != null && m > max, locked: lengthLock(m, c.limits) }));
}

// ---------------------------------------------------------------- photos in a video (docs/PHOTOS.md): the generate body carries them
export const MAX_VIDEO_PHOTOS = 100;
/** About 51 photos per minute fit (collages show several at once). Returns how many fit in `minutes`, and the shortest length that holds `n` photos in the presets. */
export const photoCapacity = (minutes: number): number => Math.floor(51 * minutes);
export function minutesForPhotos(n: number, c: Capabilities): number | null { return c.lengths.presets.find((m) => photoCapacity(m) >= n) ?? null; }

/** `media` (direct uploads of this video), `library_media` (My media ids) and `media_meta` (capture time and position per direct id), at most 100 photos in all. */
export function mediaExtras(direct: string[], library: string[], meta: Record<string, { taken?: string; lat?: number; lon?: number }> = {}): Record<string, unknown> {
  const d = direct.slice(0, MAX_VIDEO_PHOTOS), l = library.filter((id) => !d.includes(id)).slice(0, Math.max(0, MAX_VIDEO_PHOTOS - d.length));
  const m: Record<string, unknown> = {};
  for (const id of d) if (meta[id] && Object.keys(meta[id]).length) m[id] = meta[id];   // library photos already carry their date and place on the server
  return { ...(d.length ? { media: d } : {}), ...(l.length ? { library_media: l } : {}), ...(Object.keys(m).length ? { media_meta: m } : {}) };
}

// ---------------------------------------------------------------- saved choices (never the text)
const KEY = "vmk_create_defaults";
export function loadSaved(): Partial<Form> | null {
  try { const v = JSON.parse(localStorage.getItem(KEY) || "null"); return v && typeof v === "object" ? v : null; } catch { return null; }
}
export function saveChoices(f: Form): void {
  try { const { text: _t, ...rest } = f; localStorage.setItem(KEY, JSON.stringify(rest)); } catch { /* private mode */ }
}

// ---------------------------------------------------------------- request check (brief)
export interface Question { id: string; text: string; options: { id: string; label: string }[]; allow_other?: boolean }
export type Answer = { id: string; option?: string; text?: string; skip?: boolean };
export type BriefOutcome =
  | { status: "ok"; brief?: Record<string, string>; note?: string }   // note: a look that was adapted (optional; never a reason to stop)
  | { status: "questions"; questions: Question[] }
  | { status: "not_supported"; message?: string; suggestion?: string }
  | { status: "blocked"; message?: string }
  | { status: "paused"; message?: string; retryAfter?: number };

/** Parses the brief response; anything unexpected counts as ok with no brief (the check must never stop a request by itself failing). */
export function parseBrief(httpStatus: number, body: any): BriefOutcome {
  if (httpStatus === 429 && body?.status === "paused") return { status: "paused", message: body.message, retryAfter: typeof body.retry_after === "number" ? body.retry_after : undefined };
  if (body?.status === "questions" && Array.isArray(body.questions) && body.questions.length) {
    const questions: Question[] = body.questions.slice(0, 3).filter((q: any) => q && typeof q.id === "string" && typeof q.text === "string" && Array.isArray(q.options))
      .map((q: any) => ({ id: q.id, text: q.text, allow_other: q.allow_other === true, options: q.options.filter((o: any) => o && typeof o.id === "string" && typeof o.label === "string").slice(0, 5) }));
    if (questions.length) return { status: "questions", questions };
  }
  if (body?.status === "not_supported") return { status: "not_supported", message: body.message, suggestion: body.suggestion };
  if (body?.status === "blocked") return { status: "blocked", message: body.message };
  const note = typeof body?.note === "string" && body.note.trim() ? { note: body.note.trim().slice(0, 300) } : {};
  if (body?.status === "ok" && body.brief && typeof body.brief === "object") return { status: "ok", brief: body.brief, ...note };
  return { status: "ok", ...(body?.status === "ok" ? note : {}) };
}

/** The capabilities body as the form uses it. The newer parts (looks, plan limits) are read leniently: missing or malformed means "not offered", never an error. */
export function parseCapabilities(b: any): Capabilities | null {
  if (!Array.isArray(b?.aspects) || !Array.isArray(b?.resolutions) || !b?.lengths?.presets?.length) return null;
  const limits = parseLengthLimits(b.lengths), plans = parsePlanState(b);
  return {
    aspects: b.aspects, resolutions: b.resolutions, platforms: Array.isArray(b.platforms) ? b.platforms : [], languages: Array.isArray(b.languages) ? b.languages : [], lengths: b.lengths,
    max_photos: b.max_photos, intake: b.intake !== false, deck: parseDeckCaps(b.deck), watermark: parseWatermarkCaps(b.watermark),
    looks: parseLooks(b.looks), ...(limits.planMaxSeconds != null || limits.locked.length ? { limits } : {}), ...(plans.plan || plans.free ? { plans } : {}),
  };
}

export async function getCapabilities(): Promise<Capabilities | null> {
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return null;
    const res = await fetch(apiGateway.capabilities(userId), { headers: { Authorization, ...currentLocaleHeaders() } });
    if (!res.ok) return null;
    const b = await res.json();
    return parseCapabilities(b);
  } catch {
    return null;
  }
}

/** The request check. Called when the person taps Create, before generate. Any failure or a response slower than 8 s is "ok, no brief". */
export async function checkRequest(prompt: string, options: Record<string, unknown>, answers: Answer[]): Promise<BriefOutcome> {
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return { status: "ok" };
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 8000);
    try {
      const res = await fetch(apiGateway.brief(userId), { method: "POST", signal: ctl.signal, headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() }, body: JSON.stringify({ prompt, options, media_count: 0, answers }) });
      let body: any = {};
      try { body = await res.json(); } catch { /* not json */ }
      if (!res.ok && res.status !== 429) return body?.status === "blocked" ? parseBrief(200, body) : { status: "ok" };
      return parseBrief(res.status, body);
    } finally { clearTimeout(timer); }
  } catch {
    return { status: "ok" };
  }
}
