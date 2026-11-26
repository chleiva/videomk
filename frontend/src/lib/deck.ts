// "Add a presentation" (docs/CREATE_API.md "Making a video from a presentation deck", docs/DECK_TO_VIDEO.md section 8): checks before upload, the journey's state machine,
// error mapping, the price, and the network calls. Pure functions first (tested in deck.test.ts). Nothing about the file (name, size, bytes) is logged or stored beyond the session.
import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";
import { currentLocaleHeaders } from "./i18n";
import { creditsFor, resolutionOf } from "./create";
import type { Capabilities, DeckCaps } from "./create";

export type { DeckCaps } from "./create";
export { parseDeckCaps } from "./create";
export type DeckFormat = "pptx" | "pdf";

const MIME: Record<DeckFormat, string> = { pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation", pdf: "application/pdf" };
const LEGACY = ["ppt", "pptm", "pps", "ppsx", "key", "odp", "pot", "potx"];

/** The `accept` attribute of the hidden input: extensions and MIME types of the formats the server lists. */
export function acceptAttr(caps: DeckCaps): string {
  return caps.formats.flatMap((f) => [`.${f}`, MIME[f as DeckFormat]]).filter(Boolean).join(",");
}

export const extensionOf = (name: string): string => { const m = /\.([A-Za-z0-9]+)$/.exec(name.trim()); return m ? m[1].toLowerCase() : ""; };

export type PickProblem = "empty" | "too_large" | "unsupported" | "export_first";
export type PickResult = { ok: true; format: DeckFormat } | { ok: false; problem: PickProblem };

/** Local checks before anything is uploaded: size and extension/MIME. The server checks again (the content is what counts there). */
export function checkFile(file: { name: string; size: number; type?: string }, caps: DeckCaps): PickResult {
  const ext = extensionOf(file.name);
  if (LEGACY.includes(ext)) return { ok: false, problem: "export_first" };
  const byExt = (caps.formats as string[]).includes(ext) ? (ext as DeckFormat) : null;
  const mime = (file.type || "").toLowerCase();
  const byMime = (caps.formats as DeckFormat[]).find((f) => MIME[f] === mime) ?? null;
  // The extension decides; a missing or unknown MIME (browsers often send "") is fine, a known MIME that disagrees with the extension is not.
  if (!byExt || (mime && byMime && byMime !== byExt)) return { ok: false, problem: "unsupported" };
  if (file.size <= 0) return { ok: false, problem: "empty" };
  if (file.size > caps.max_mb * 1024 * 1024) return { ok: false, problem: "too_large" };
  return { ok: true, format: byExt };
}

// ---------------------------------------------------------------- errors: the server's code to a localized, specific message and the right action
export type DeckAction = "choose_other" | "retry" | "keep_waiting" | "export";
export interface DeckProblem { key: string; action: DeckAction; params?: Record<string, number> }

/** Codes of GET .../decks/{id} (failed), of POST .../decks, plus the client's own (`poll_timeout`, `network`, `upload_failed`, and the local pick problems). */
export function problemFor(code: string, caps?: DeckCaps): DeckProblem {
  const p = { mb: caps?.max_mb ?? 50, slides: caps?.max_slides ?? 60 };
  switch (code) {
    case "too_large": case "deck_too_large": return { key: "deck.err.too_large", action: "choose_other", params: p };
    case "deck_too_many_slides": return { key: "deck.err.too_many_slides", action: "choose_other", params: p };
    case "deck_encrypted": return { key: "deck.err.encrypted", action: "choose_other" };
    case "deck_macro": return { key: "deck.err.macro", action: "choose_other" };
    case "deck_corrupt": return { key: "deck.err.corrupt", action: "choose_other" };
    case "deck_empty": case "empty": return { key: "deck.err.empty", action: "choose_other" };
    case "deck_unsafe": return { key: "deck.err.unsafe", action: "choose_other" };
    case "deck_convert_timeout": case "deck_convert_failed": return { key: "deck.err.convert", action: "retry" };
    case "deck_missing": return { key: "deck.err.expired", action: "choose_other" };
    case "deck_unsupported": case "unsupported": return { key: "deck.err.unsupported", action: "choose_other" };
    case "export_first": return { key: "deck.err.export_first", action: "choose_other" };
    case "too_many_decks": return { key: "deck.err.too_many_decks", action: "choose_other" };
    case "poll_timeout": return { key: "deck.err.slow", action: "keep_waiting" };
    case "upload_failed": return { key: "deck.err.upload_failed", action: "retry" };
    case "unavailable": return { key: "deck.err.unavailable", action: "choose_other" };
    case "auth": return { key: "api.session_expired", action: "choose_other" };
    default: return { key: "deck.err.network", action: "retry" };
  }
}

// ---------------------------------------------------------------- the journey (state machine)
export interface DeckReady { slides: number; suggested_minutes: number; suggested_credits: number }
export type DeckState =
  | { k: "idle" }
  | { k: "uploading"; name: string; format: DeckFormat; pct: number }
  | { k: "processing"; name: string; id: string; since: number }
  | { k: "ready"; name: string; id: string } & DeckReady
  | { k: "error"; code: string; name?: string; id?: string; serverMessage?: string };
export type DeckEvent =
  | { t: "pick"; name: string; format: DeckFormat }
  | { t: "progress"; pct: number }
  | { t: "uploaded"; id: string; now: number }
  | { t: "ready"; info: DeckReady }
  | { t: "failed"; code: string; message?: string }
  | { t: "waited_too_long" }
  | { t: "resume"; now: number }
  | { t: "rejected"; code: string; name?: string }
  | { t: "cancel" }
  | { t: "reset" };

/** Every transition in one place; an event that makes no sense in the current state is ignored (a late progress tick after a cancel, for example). */
export function deckReducer(s: DeckState, e: DeckEvent): DeckState {
  switch (e.t) {
    case "pick": return { k: "uploading", name: e.name, format: e.format, pct: 0 };
    case "progress": return s.k === "uploading" ? { ...s, pct: Math.max(0, Math.min(100, Math.round(e.pct))) } : s;
    case "uploaded": return s.k === "uploading" ? { k: "processing", name: s.name, id: e.id, since: e.now } : s;
    case "ready": return s.k === "processing" ? { k: "ready", name: s.name, id: s.id, ...e.info } : s;
    case "failed": return s.k === "uploading" || s.k === "processing" ? { k: "error", code: e.code, name: s.name, id: s.k === "processing" ? s.id : undefined, serverMessage: e.message } : s;
    case "waited_too_long": return s.k === "processing" ? { k: "error", code: "poll_timeout", name: s.name, id: s.id } : s;
    case "resume": return s.k === "error" && s.id ? { k: "processing", name: s.name ?? "", id: s.id, since: e.now } : s;
    case "rejected": return { k: "error", code: e.code, name: e.name };
    case "cancel": case "reset": return { k: "idle" };
  }
}

/** Seconds to wait before poll number `attempt` (0 based): 2 s at first (processing takes 5 to 30 s), easing to 6 s. */
export function pollDelayMs(attempt: number): number { return Math.min(6000, 2000 + Math.max(0, attempt) * 500); }
/** The client stops after 3 minutes and offers "keep waiting" (the server itself gives up at 10 minutes). */
export const POLL_GIVE_UP_MS = 3 * 60 * 1000;
export const pollExpired = (since: number, now: number) => now - since >= POLL_GIVE_UP_MS;

// ---------------------------------------------------------------- price and options
export const DECK_ASPECT = "16:9";
/** The length the video will get: what the person picked, else the deck's suggestion. */
export const deckMinutes = (ready: DeckReady, picked: number | null) => picked ?? ready.suggested_minutes;

/** Credits for a deck video: the server's suggestion while nothing is changed and the resolution is the default, otherwise the usual rule on the effective length. */
export function deckCredits(ready: DeckReady, picked: number | null, resolution: string, c: Capabilities): number {
  const mult = resolutionOf(c, resolution)?.credits_multiplier ?? 1;
  if (picked === null && mult === 1 && ready.suggested_credits > 0) return ready.suggested_credits;
  return creditsFor(deckMinutes(ready, picked), resolution, c);
}

/** Vertical or square pages crop a slide's frame: say so gently (never a block). */
export const deckAspectWarning = (aspect: string) => aspect !== DECK_ASPECT;

/** Extra fields for generate: the deck id; `target_minutes` only when the person chose a length (absent means the deck's suggestion, charged exactly that). */
export function deckGenerateExtras(id: string, picked: number | null): Record<string, unknown> {
  return { deck: id, ...(picked !== null ? { target_minutes: picked } : {}) };
}

// ---------------------------------------------------------------- the upload target must be S3 (a presigned POST to anywhere else is refused)
/** https, no credentials or port, host is an S3 endpoint (virtual-hosted or path style, any region, dualstack included). */
export function isExpectedS3Url(raw: string): boolean {
  let u: URL;
  try { u = new URL(raw); } catch { return false; }
  if (u.protocol !== "https:" || u.username || u.password || u.port) return false;
  const h = u.hostname.toLowerCase();
  return /^(?:[a-z0-9][a-z0-9.-]*\.)?s3(?:[.-](?:dualstack\.)?[a-z0-9-]+)?\.amazonaws\.com(?:\.cn)?$/.test(h) && !h.includes("..");
}

// ---------------------------------------------------------------- network
export interface Slot { id: string; url: string; fields: Record<string, string> }
export type CallResult<T> = { ok: true; value: T } | { ok: false; code: string; message?: string };

async function authed(): Promise<{ Authorization: string; userId: string } | null> {
  const { Authorization, userId } = await getAuthorizationHeader();
  return userId ? { Authorization, userId } : null;
}
const headers = (Authorization: string, json = false) => ({ Authorization, ...(json ? { "Content-Type": "application/json" } : {}), ...currentLocaleHeaders() });
async function jsonOf(res: Response): Promise<any> { try { return await res.json(); } catch { return {}; } }
const failure = (status: number, body: any): { ok: false; code: string; message?: string } => ({
  ok: false, code: status === 401 || status === 403 ? "auth" : status === 404 ? "unavailable" : typeof body?.code === "string" ? body.code : typeof body?.error === "string" ? body.error : status === 429 ? "too_many_decks" : "network",
  message: typeof body?.message === "string" ? body.message : undefined,
});

/** Step 1: ask for the upload slot (presigned POST). The target host is checked before it is returned. */
export async function requestSlot(format: DeckFormat, size: number): Promise<CallResult<Slot>> {
  try {
    const a = await authed(); if (!a) return { ok: false, code: "auth" };
    const res = await fetch(apiGateway.decks(a.userId), { method: "POST", headers: headers(a.Authorization, true), body: JSON.stringify({ format, size }) });
    const b = await jsonOf(res);
    if (!res.ok) return failure(res.status, b);
    const d = b?.deck;
    if (!d || typeof d.id !== "string" || typeof d.url !== "string" || typeof d.fields !== "object" || !d.fields) return { ok: false, code: "network" };
    if (!isExpectedS3Url(d.url)) return { ok: false, code: "upload_failed" };
    return { ok: true, value: { id: d.id, url: d.url, fields: d.fields } };
  } catch { return { ok: false, code: "network" }; }
}

/** Step 2: multipart POST straight to S3 (the slot's fields first, `file` last) with progress and an abort signal. Nothing here carries our token. */
export function uploadToSlot(slot: Slot, file: Blob, onProgress: (pct: number) => void, signal: AbortSignal): Promise<CallResult<true>> {
  return new Promise((resolve) => {
    if (!isExpectedS3Url(slot.url)) return resolve({ ok: false, code: "upload_failed" });
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    for (const [k, v] of Object.entries(slot.fields)) form.append(k, String(v));
    form.append("file", file);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && e.total > 0) onProgress((e.loaded / e.total) * 100); };
    xhr.onload = () => resolve(xhr.status >= 200 && xhr.status < 300 ? { ok: true, value: true } : { ok: false, code: "upload_failed" });
    xhr.onerror = () => resolve({ ok: false, code: "upload_failed" });
    xhr.ontimeout = () => resolve({ ok: false, code: "upload_failed" });
    xhr.onabort = () => resolve({ ok: false, code: "aborted" });
    signal.addEventListener("abort", () => xhr.abort(), { once: true });
    if (signal.aborted) return resolve({ ok: false, code: "aborted" });
    xhr.open("POST", slot.url);
    xhr.send(form);
  });
}

/** Step 3: start processing (repeating it is harmless). */
export async function processDeck(id: string): Promise<CallResult<true>> {
  try {
    const a = await authed(); if (!a) return { ok: false, code: "auth" };
    const res = await fetch(apiGateway.deckProcess(a.userId, id), { method: "POST", headers: headers(a.Authorization, true), body: "{}" });
    if (res.ok || res.status === 202) return { ok: true, value: true };
    return failure(res.status, await jsonOf(res));
  } catch { return { ok: false, code: "network" }; }
}

export type DeckStatus =
  | { status: "uploading" | "processing" }
  | ({ status: "ready" } & DeckReady)
  | { status: "failed"; code: string; message?: string };

/** Pure: the GET .../decks/{id} body to a typed status (anything unexpected counts as still processing). */
export function parseDeckStatus(b: any): DeckStatus {
  if (b?.status === "ready" && Number(b.slides) > 0) return { status: "ready", slides: Number(b.slides), suggested_minutes: Number(b.suggested_minutes) || 1, suggested_credits: Number(b.suggested_credits) || 0 };
  if (b?.status === "failed") return { status: "failed", code: typeof b.code === "string" ? b.code : "deck_convert_failed", message: typeof b.message === "string" ? b.message : undefined };
  return { status: b?.status === "uploading" ? "uploading" : "processing" };
}

/** Step 4: one poll. A network blip is "still processing": the next poll tries again. */
export async function getDeck(id: string): Promise<CallResult<DeckStatus>> {
  try {
    const a = await authed(); if (!a) return { ok: false, code: "auth" };
    const res = await fetch(apiGateway.deck(a.userId, id), { headers: headers(a.Authorization) });
    const b = await jsonOf(res);
    if (!res.ok) return res.status >= 500 ? { ok: true, value: { status: "processing" } } : failure(res.status, b);
    return { ok: true, value: parseDeckStatus(b) };
  } catch { return { ok: true, value: { status: "processing" } }; }
}
