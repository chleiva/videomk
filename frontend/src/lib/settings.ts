// The settings page's logic: this browser's preferences (the same ones the apps have) and the saved watermark default (docs/WATERMARK.md section 4).
// Pure helpers are tested in settings.test.ts. Other pages read the preferences through `readPref` (the Create sheet: subtitles; the media pages: photo dates and locations).
import { getAuthorizationHeader } from "./auth";
import { API_BASE } from "./config";
import { currentLocaleHeaders } from "./i18n";

// ---------------------------------------------------------------- preferences of this browser
export type PrefId = "subtitles" | "photoDates" | "photoLocations";
const PREF: Record<PrefId, { key: string; fallback: boolean }> = {
  subtitles: { key: "vmk_pref_subtitles", fallback: true },          // subtitles on by default (the creator can turn them off per video)
  photoDates: { key: "vmk_pref_photo_dates", fallback: true },        // the date a photo was taken helps the story
  photoLocations: { key: "vmk_pref_photo_locations", fallback: false }, // a place is shared only when the person chose to
};

/** The saved switch, or its default when nothing is saved (or storage is unavailable). Only "1" and "0" are read back. */
export function readPref(id: PrefId, storage: Pick<Storage, "getItem"> | null = safeStorage()): boolean {
  try {
    const v = storage?.getItem(PREF[id].key);
    return v === "1" ? true : v === "0" ? false : PREF[id].fallback;
  } catch {
    return PREF[id].fallback;
  }
}

export function writePref(id: PrefId, on: boolean, storage: Pick<Storage, "setItem"> | null = safeStorage()): void {
  try { storage?.setItem(PREF[id].key, on ? "1" : "0"); } catch { /* private mode: the choice lasts until reload (the page keeps it in state) */ }
}

function safeStorage(): Storage | null {
  try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; }
}

// ---------------------------------------------------------------- watermark default
export type WmMode = "none" | "videomk" | "custom";
export type WmPosition = "auto" | "tl" | "tr" | "bl" | "br";
export interface WmSettings { mode: WmMode; position: WmPosition; has_logo: boolean }
export interface WmMode_ { id: WmMode; available: boolean }
export interface WmView { settings: WmSettings; modes: WmMode_[]; forced: boolean; premium: boolean; logo: { max_bytes: number; types: string[] } }

const MODES: WmMode[] = ["none", "videomk", "custom"];
const POSITIONS: WmPosition[] = ["auto", "tl", "tr", "bl", "br"];
export const WM_POSITIONS = POSITIONS;

/** What the settings page shows from GET .../watermark; null when the server does not have the feature (the section is then hidden). */
export function parseWatermark(raw: any): WmView | null {
  const w = raw?.watermark, c = raw?.capabilities;
  if (!w || typeof w !== "object" || !c || typeof c !== "object" || !Array.isArray(c.modes)) return null;
  const modes: WmMode_[] = c.modes.filter((m: any) => MODES.includes(m?.id)).map((m: any) => ({ id: m.id as WmMode, available: m.available !== false }));
  if (!modes.length) return null;
  const mode: WmMode = MODES.includes(w.mode) ? w.mode : "none";
  const position: WmPosition = POSITIONS.includes(w.position) ? w.position : "auto";
  const maxBytes = Number(c.logo?.max_bytes);
  return {
    settings: { mode, position, has_logo: w.has_logo === true },
    modes, forced: c.forced === true, premium: c.premium === true,
    logo: { max_bytes: Number.isFinite(maxBytes) && maxBytes > 0 ? maxBytes : 2 * 1024 * 1024, types: Array.isArray(c.logo?.types) ? c.logo.types.map(String) : ["image/png", "image/jpeg", "image/svg+xml"] },
  };
}

/** The base64 part of a data URL ("data:image/png;base64,AAAA" -> "AAAA"), or null for anything else. */
export function base64Of(dataUrl: string): string | null {
  const m = /^data:[^;,]*;base64,([A-Za-z0-9+/=]+)$/.exec(dataUrl);
  return m ? m[1] : null;
}

/** Why a chosen file cannot be a logo, or null (the server checks again from the bytes). */
export function logoProblem(file: { size: number; type: string }, maxBytes: number, types: readonly string[]): "big" | "type" | "empty" | null {
  if (!(file.size > 0)) return "empty";
  if (file.size > maxBytes) return "big";
  return types.includes(file.type) ? null : "type";
}

const wmUrl = (userId: string, tail = "") => `${API_BASE}/users/${encodeURIComponent(userId)}/watermark${tail}`;

async function call(method: string, tail: string, body?: unknown): Promise<{ status: number; body: any }> {
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) return { status: 401, body: {} };
  try {
    const res = await fetch(wmUrl(userId, tail), { method, headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() }, body: body === undefined ? undefined : JSON.stringify(body) });
    let b: any = {};
    try { b = await res.json(); } catch { /* no body */ }
    return { status: res.status, body: b };
  } catch {
    return { status: 0, body: {} };
  }
}

export async function loadWatermark(): Promise<WmView | null> {
  const r = await call("GET", "");
  return r.status === 200 ? parseWatermark(r.body) : null;
}

export type SaveResult = { ok: true } | { ok: false; message: string };
const fail = (r: { status: number; body: any }): SaveResult => ({ ok: false, message: typeof r.body?.message === "string" ? r.body.message : "" });

export async function saveWatermark(s: { mode: WmMode; position: WmPosition }): Promise<SaveResult> {
  const r = await call("PUT", "", { mode: s.mode, position: s.position });
  return r.status === 200 || r.status === 204 ? { ok: true } : fail(r);
}

export async function uploadLogo(base64: string): Promise<SaveResult> {
  const r = await call("PUT", "/logo", { data: base64 });
  return r.status === 200 || r.status === 204 ? { ok: true } : fail(r);
}

export async function removeLogo(): Promise<SaveResult> {
  const r = await call("DELETE", "/logo");
  return r.status === 200 || r.status === 204 ? { ok: true } : fail(r);
}
