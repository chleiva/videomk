// My media (docs/MEDIA_LIBRARY.md): the private photo library. Types and parsers (pure, tested in library.test.ts) first, the network calls below.
// The API is the one the apps use. Thumbnails come from the API (presigned, cached by photo id: the picture behind an id never changes).
import { getAuthorizationHeader } from "./auth";
import { API_BASE } from "./config";
import { currentLocaleHeaders } from "./i18n";

export interface Photo { id: string; taken?: string; added: string; place?: string; w: number; h: number; bytes: number; thumb_url: string; collections: string[] }
export interface Collection { id: string; name: string; emoji?: string; count: number; cover_id?: string; cover_thumb_url?: string; auto?: boolean }
export interface Summary {
  plan: "free" | "pro"; limit_bytes: number; used_bytes: number; read_only: boolean; count: number; can_upgrade: boolean;
  years: { year: number; count: number }[]; places: { name: string; country?: string; count: number }[]; collections: Collection[]; organize: "ask" | "always" | "never";
}
export interface Chip { kind: "place" | "date" | "topic"; label: string }
export interface SearchResult { items: Photo[]; chips: Chip[]; mode: "timeline" | "semantic" }
export type SlotStatus = "upload" | "duplicate" | "no_space" | "rejected";
export interface UploadSlot { index: number; status: SlotStatus; id?: string; url?: string; fields?: Record<string, string>; duplicate_of?: string; reason?: string }
export interface OrganizePreview { total: number; organized: number; skipped: number; home?: string | null; groups: { name: string; count: number; existing?: boolean; sample_ids?: string[] }[] }

export const MAX_SELECT = 100;       // a video takes at most 100 photos in total
export const MAX_BATCH = 100;        // upload slots per request

// ---------------------------------------------------------------- pure parsers (anything unexpected is dropped, never thrown)
const str = (v: unknown): string | undefined => (typeof v === "string" && v ? v : undefined);
const num = (v: unknown, d = 0): number => (typeof v === "number" && Number.isFinite(v) ? v : d);

export function parsePhoto(p: any): Photo | null {
  const id = str(p?.id);
  if (!id) return null;
  return { id, taken: str(p.taken), added: str(p.added) ?? "", place: str(p.place), w: num(p.w), h: num(p.h), bytes: num(p.bytes), thumb_url: str(p.thumb_url) ?? "", collections: Array.isArray(p.collections) ? p.collections.filter((c: unknown) => typeof c === "string") : [] };
}
export const parsePhotos = (a: unknown): Photo[] => (Array.isArray(a) ? (a.map(parsePhoto).filter(Boolean) as Photo[]) : []);

export function parseCollection(c: any): Collection | null {
  const id = str(c?.id), name = str(c?.name);
  if (!id || !name) return null;
  return { id, name, emoji: str(c.emoji), count: num(c.count), cover_id: str(c.cover_id), cover_thumb_url: str(c.cover_thumb_url), auto: c.auto === true };
}

export function parseSummary(b: any): Summary | null {
  if (!b || typeof b !== "object" || typeof b.limit_bytes !== "number") return null;
  const org = b.prefs?.organize;
  return {
    plan: b.plan === "pro" ? "pro" : "free", limit_bytes: b.limit_bytes, used_bytes: num(b.used_bytes), read_only: b.read_only === true, count: num(b.count), can_upgrade: b.can_upgrade === true,
    years: Array.isArray(b.years) ? b.years.filter((y: any) => typeof y?.year === "number").map((y: any) => ({ year: y.year, count: num(y.count) })) : [],
    places: Array.isArray(b.places) ? b.places.filter((p: any) => str(p?.name)).map((p: any) => ({ name: p.name, country: str(p.country), count: num(p.count) })) : [],
    collections: Array.isArray(b.collections) ? (b.collections.map(parseCollection).filter(Boolean) as Collection[]) : [],
    organize: org === "always" || org === "never" ? org : "ask",
  };
}

export function parseSearch(b: any): SearchResult {
  const chips: Chip[] = Array.isArray(b?.understood?.chips) ? b.understood.chips.filter((c: any) => str(c?.label)).map((c: any) => ({ kind: c.kind === "place" || c.kind === "date" ? c.kind : "topic", label: c.label })) : [];
  return { items: parsePhotos(b?.items), chips, mode: b?.mode === "semantic" ? "semantic" : "timeline" };
}

export function parseSlots(b: any): UploadSlot[] {
  if (!Array.isArray(b?.uploads)) return [];
  return b.uploads.filter((u: any) => typeof u?.index === "number").map((u: any): UploadSlot => ({
    index: u.index, status: u.status === "duplicate" || u.status === "no_space" || u.status === "rejected" ? u.status : "upload",
    id: str(u.id), url: str(u.url), fields: u.fields && typeof u.fields === "object" ? u.fields : undefined, duplicate_of: str(u.duplicate_of), reason: str(u.reason),
  }));
}

// ---------------------------------------------------------------- timeline grouping (newest first, by the day taken, else the day added)
export interface MonthGroup { key: string; year: number; month: number; items: Photo[] }
const stamp = (p: Photo) => p.taken || p.added || "";

/** Groups photos by month and year in the order given (the API returns newest first). A photo with no usable date goes to the last group (key "0000-00"). */
export function groupByMonth(items: Photo[]): MonthGroup[] {
  const groups: MonthGroup[] = [];
  const index = new Map<string, MonthGroup>();
  for (const p of items) {
    const m = /^(\d{4})-(\d{2})/.exec(stamp(p));
    const key = m ? `${m[1]}-${m[2]}` : "0000-00";
    let g = index.get(key);
    if (!g) { g = { key, year: m ? Number(m[1]) : 0, month: m ? Number(m[2]) : 0, items: [] }; index.set(key, g); groups.push(g); }
    g.items.push(p);
  }
  return groups.sort((a, b) => (a.key === "0000-00" ? 1 : b.key === "0000-00" ? -1 : b.key.localeCompare(a.key)));
}

/** "July 2026" in the person's language (no date: null, the caller shows the "Undated" header). */
export function monthLabel(g: MonthGroup, locale: string): string | null {
  if (!g.year) return null;
  try { return new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(g.year, g.month - 1, 1))); } catch { return `${g.year}-${String(g.month).padStart(2, "0")}`; }
}

// ---------------------------------------------------------------- storage meter
export function formatBytes(n: number, locale = "en"): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = Math.max(0, n), i = 0;
  while (v >= 1000 && i < units.length - 1) { v /= 1000; i++; }
  const digits = i === 0 || v >= 100 ? 0 : v >= 10 ? 1 : 2;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(v)} ${units[i]}`;
}
export type StorageTone = "ok" | "warn" | "full";
export function storageTone(s: Pick<Summary, "used_bytes" | "limit_bytes">): StorageTone {
  const r = s.limit_bytes > 0 ? s.used_bytes / s.limit_bytes : 0;
  return r >= 1 ? "full" : r >= 0.85 ? "warn" : "ok";
}

// ---------------------------------------------------------------- selection (click, shift-click range, select all, cap)
export interface Selection { ids: string[]; anchor: string | null }
export const emptySelection: Selection = { ids: [], anchor: null };

/** Click toggles; with `range` it selects everything between the anchor and this photo in the visible order. Never more than `max` photos. */
export function selectClick(sel: Selection, order: string[], id: string, range: boolean, max = MAX_SELECT): Selection {
  if (range && sel.anchor && order.includes(sel.anchor)) {
    const a = order.indexOf(sel.anchor), b = order.indexOf(id);
    if (b >= 0) {
      const [lo, hi] = a < b ? [a, b] : [b, a];
      const merged = [...new Set([...sel.ids, ...order.slice(lo, hi + 1)])];
      return { ids: merged.slice(0, max), anchor: id };
    }
  }
  if (sel.ids.includes(id)) return { ids: sel.ids.filter((x) => x !== id), anchor: id };
  if (sel.ids.length >= max) return sel;
  return { ids: [...sel.ids, id], anchor: id };
}
export const selectAll = (order: string[], max = MAX_SELECT): Selection => ({ ids: order.slice(0, max), anchor: order[0] ?? null });

/** The photos between two grid positions (drag select), as ids in grid order. */
export function idsBetween(order: string[], from: string, to: string): string[] {
  const a = order.indexOf(from), b = order.indexOf(to);
  if (a < 0 || b < 0) return [];
  return order.slice(Math.min(a, b), Math.max(a, b) + 1);
}

// ---------------------------------------------------------------- network
async function call(path: string, init: { method?: string; body?: unknown } = {}): Promise<{ ok: boolean; status: number; body: any; retryAfter?: number }> {
  const { Authorization, userId } = await getAuthorizationHeader();
  if (!userId) return { ok: false, status: 401, body: {} };
  try {
    const res = await fetch(`${API_BASE}/users/${encodeURIComponent(userId)}/library${path}`, {
      method: init.method ?? (init.body !== undefined ? "POST" : "GET"),
      headers: { Authorization, ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}), ...currentLocaleHeaders() },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
    let body: any = {};
    try { body = await res.json(); } catch { /* empty */ }
    const ra = Number(res.headers.get("Retry-After"));
    return { ok: res.ok, status: res.status, body, retryAfter: Number.isFinite(ra) && ra > 0 ? ra : undefined };
  } catch {
    return { ok: false, status: 0, body: {} };
  }
}

export async function getSummary(): Promise<Summary | null> { const r = await call("/summary"); return r.ok ? parseSummary(r.body) : null; }

export async function listItems(q: { cursor?: string; limit?: number; collection?: string; place?: string; from?: string; to?: string } = {}): Promise<{ ok: boolean; items: Photo[]; cursor?: string }> {
  const p = new URLSearchParams();
  p.set("limit", String(q.limit ?? 60));
  for (const k of ["cursor", "collection", "place", "from", "to"] as const) if (q[k]) p.set(k, q[k] as string);
  const r = await call(`/items?${p}`);
  return { ok: r.ok, items: r.ok ? parsePhotos(r.body?.items) : [], cursor: str(r.body?.cursor) };
}

/** One photo with its full-size link (valid 10 minutes: never keep it). */
export async function getPhoto(id: string): Promise<(Photo & { url: string }) | null> {
  const r = await call(`/items/${encodeURIComponent(id)}`);
  const p = r.ok ? parsePhoto(r.body?.item ?? r.body) : null;
  const url = str((r.body?.item ?? r.body)?.url);
  return p && url ? { ...p, url } : null;
}

export async function searchPhotos(query: string, drop: string[] = []): Promise<SearchResult | null> {
  const r = await call("/search", { body: { query, limit: MAX_SELECT, ...(drop.length ? { drop } : {}) } });
  return r.ok ? parseSearch(r.body) : null;
}

export async function deletePhotos(ids: string[]): Promise<boolean> {
  for (let i = 0; i < ids.length; i += 100) { const r = await call("/items/delete", { body: { ids: ids.slice(i, i + 100) } }); if (!r.ok) return false; }
  return true;
}

export async function listCollections(): Promise<Collection[] | null> {
  const r = await call("/collections");
  return r.ok && Array.isArray(r.body?.collections) ? (r.body.collections.map(parseCollection).filter(Boolean) as Collection[]) : null;
}
export async function createCollection(name: string): Promise<Collection | null> { const r = await call("/collections", { body: { name: name.trim().slice(0, 40) } }); return r.ok ? parseCollection(r.body?.collection ?? r.body) : null; }
export async function addToCollection(cid: string, ids: string[]): Promise<boolean> {
  for (let i = 0; i < ids.length; i += 100) { const r = await call(`/collections/${encodeURIComponent(cid)}/items`, { body: { add: ids.slice(i, i + 100) } }); if (!r.ok) return false; }
  return true;
}
export async function deleteCollection(cid: string): Promise<boolean> { return (await call(`/collections/${encodeURIComponent(cid)}/delete`, { body: {} })).ok; }

export async function organizePreview(since?: string): Promise<OrganizePreview | null> {
  const r = await call("/organize/preview", { body: since ? { since } : {} });
  if (!r.ok || typeof r.body?.total !== "number") return null;
  return { total: r.body.total, organized: num(r.body.organized), skipped: num(r.body.skipped), home: str(r.body.home) ?? null,
    groups: Array.isArray(r.body.groups) ? r.body.groups.filter((g: any) => str(g?.name)).map((g: any) => ({ name: g.name, count: num(g.count), existing: g.existing === true, sample_ids: Array.isArray(g.sample_ids) ? g.sample_ids : [] })) : [] };
}
/** Organises about 300 photos per call; repeat until `remaining` is 0 (each call is safe to repeat). */
export async function organizeApply(mode: "auto" | "single", since?: string, name?: string): Promise<boolean> {
  let collection_id: string | undefined;
  for (let guard = 0; guard < 60; guard++) {
    const r = await call("/organize/apply", { body: { mode, ...(since ? { since } : {}), ...(mode === "single" ? { name, ...(collection_id ? { collection_id } : {}) } : {}) } });
    if (!r.ok) return false;
    if (typeof r.body?.collection_id === "string") collection_id = r.body.collection_id;
    if (!r.body?.remaining) return true;
  }
  return false;
}
export async function setOrganizePref(organize: "ask" | "always" | "never"): Promise<boolean> { return (await call("/prefs", { body: { organize } })).ok; }

/** Step 1 of an upload: slots for up to 100 photos (size and sha256 of the exact bytes that will be uploaded). */
export async function requestLibrarySlots(items: { size: number; sha256: string; taken?: string; lat?: number; lon?: number }[]): Promise<{ ok: true; slots: UploadSlot[] } | { ok: false; kind: "storage_full" | "rate" | "error"; retryAfter?: number }> {
  const r = await call("/uploads", { body: { items } });
  if (r.ok) return { ok: true, slots: parseSlots(r.body) };
  if (r.status === 402) return { ok: false, kind: "storage_full" };
  if (r.status === 429) return { ok: false, kind: "rate", retryAfter: r.retryAfter };
  return { ok: false, kind: "error" };
}

// ---------------------------------------------------------------- after an upload: the server lists a photo a little after it accepted the file (found against QA: the first list call came back empty)
/** How long to wait before each new look at the list once an upload has finished (about a minute in all); the page stops as soon as every new photo is listed. */
export const SETTLE_DELAYS_MS = [0, 1500, 2500, 4000, 6000, 9000, 14000, 22000];
/** The uploaded photos the list does not show yet. */
export function pendingIds(uploaded: readonly string[], listed: readonly { id: string }[]): string[] {
  const have = new Set(listed.map((p) => p.id));
  return uploaded.filter((id) => !have.has(id));
}
