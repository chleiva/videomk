// The video list: item shape, normalisation of the API payload, day groups (Today / Yesterday / Earlier, as in the apps' DayGroup) and the making progress.
import { parseVideoLook } from "./looks";
import type { VideoLook } from "./looks";

export type Status = "queued" | "running" | "complete" | "error" | "rejected";
export type Stage = "starting" | "writing" | "deck_reading" | "deck_writing" | "assets" | "storyboard" | "rendering";

export interface TaskItem {
  id: string;
  title?: string;
  status: Status;
  stage?: Stage;
  editable?: boolean;
  reject_reason?: string | null;
  eta_seconds?: number | null;
  created_at?: string | null;
  download_url?: string | null;
  preview_gif_url?: string | null;
  duration_s?: number | null;
  video_url?: string | null;
  aspect?: string | null;   // "9:16", "1:1", "4:5" (absent: 16:9)
  can_retry?: boolean;   // a failed video the server will run again as the SAME item (POST .../retry)
  look?: VideoLook | null;   // the look the video got (docs/CREATE_API.md "The video record"); absent on older servers and before the plan exists
  cancelled?: boolean;   // stopped by the person (CANCELLED): credits came back, it can be tried again or removed
  making?: Making | null;   // what is known about the video being made (scenes done, one live line); absent on older servers and before the plan exists
}

// ---------------------------------------------------------------- the optional `making` object (docs/CREATE_API.md "Making status")
export interface MakingScene { index: number; done: boolean; thumb_url?: string }
export interface Making { scene_total?: number; scene_done?: number; live_line?: string; narration_line?: string; scenes?: MakingScene[] }

const count = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? Math.floor(v) : undefined);
const line = (v: unknown, max: number): string | undefined => { const s = typeof v === "string" ? v.trim() : ""; return s ? s.slice(0, max) : undefined; };

/** Every field is optional and anything malformed is dropped, never thrown: a server that sends less (or nothing) still gets a working screen. null when nothing usable is left. */
export function parseMaking(raw: unknown): Making | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const r = raw as Record<string, unknown>;
  const seen = new Set<number>();
  const scenes = (Array.isArray(r.scenes) ? r.scenes : []).flatMap((x): MakingScene[] => {
    const index = count((x as any)?.index);
    if (!index || seen.has(index)) return [];
    seen.add(index);
    const u = (x as any)?.thumb_url;
    const done = (x as any)?.done === true;
    return [{ index, done, ...(done && typeof u === "string" && /^https:\/\//.test(u) ? { thumb_url: u } : {}) }];
  }).sort((a, b) => a.index - b.index).slice(0, 200);
  let total = count(r.scene_total), done = count(r.scene_done);
  if (total === undefined && scenes.length) total = scenes.length;
  if (done === undefined && scenes.length) done = scenes.filter((x) => x.done).length;
  if (total !== undefined && done !== undefined) done = Math.min(done, total);
  const out: Making = {
    ...(total ? { scene_total: total } : {}), ...(total && done !== undefined ? { scene_done: done } : {}),
    ...(line(r.live_line, 120) ? { live_line: line(r.live_line, 120) } : {}), ...(line(r.narration_line, 240) ? { narration_line: line(r.narration_line, 240) } : {}),
    ...(scenes.length ? { scenes } : {}),
  };
  return Object.keys(out).length ? out : null;
}

/** "Scene 5 of 9": the scene in work is the one after the last finished. null when the server did not say, and once every scene is done (the render and the
 *  finishing touches have no scene in work: seen against QA, "Scene 3 of 3 · Putting the scenes together" read as if the third scene were still being made). */
export function sceneCounter(m: Making | null | undefined): { index: number; total: number } | null {
  if (!m?.scene_total) return null;
  const done = m.scene_done ?? 0;
  return done >= m.scene_total ? null : { index: done + 1, total: m.scene_total };
}

export interface StripTile { index: number; state: "done" | "now" | "todo"; thumb?: string }
/** The film strip: one tile per planned scene in story order. Scenes do not finish in order, so "now" is the first one not done. Without a scene list the counts draw plain tiles. */
export function stripTiles(m: Making | null | undefined, thumbs: Record<string, string> = {}, videoId = ""): StripTile[] {
  if (!m) return [];
  const total = m.scene_total ?? m.scenes?.length ?? 0;
  if (!total) return [];
  const by = new Map((m.scenes ?? []).map((x) => [x.index, x] as const));
  const tiles: StripTile[] = [];
  let nowSet = false;
  for (let i = 1; i <= total; i++) {
    const sc = by.get(i);
    const done = sc ? sc.done : i <= (m.scene_done ?? 0);
    const thumb = done ? thumbs[sceneKey(videoId, i)] ?? sc?.thumb_url : undefined;
    if (done) tiles.push({ index: i, state: "done", ...(thumb ? { thumb } : {}) });
    else if (!nowSet) { nowSet = true; tiles.push({ index: i, state: "now" }); }
    else tiles.push({ index: i, state: "todo" });
  }
  return tiles;
}

export const sceneKey = (videoId: string, index: number) => `${videoId}#${index}`;
/** A scene's picture link is signed for minutes and changes on every poll; the picture does not. Keep the first link per video and scene so a poll never reloads a tile. */
export function stableSceneThumbs(prev: Record<string, string>, items: { id: string; making?: Making | null }[]): Record<string, string> {
  let next = prev;
  for (const it of items) for (const sc of it.making?.scenes ?? []) {
    const k = sceneKey(it.id, sc.index);
    if (sc.thumb_url && !next[k]) { if (next === prev) next = { ...prev }; next[k] = sc.thumb_url; }
  }
  return next;
}
/** For the session cache: the private, short-lived scene links are never stored (docs/CREATE_API.md); the counts and the line are. */
export function withoutSceneLinks(items: TaskItem[]): TaskItem[] {
  return items.map((i) => (i.making?.scenes?.some((x) => x.thumb_url) ? { ...i, making: { ...i.making, scenes: i.making.scenes.map(({ thumb_url: _u, ...rest }) => rest) } } : i));
}
const sameMaking = (a: Making | null | undefined, b: Making | null | undefined): boolean => {
  if (!a || !b) return !a && !b;
  return a.scene_total === b.scene_total && a.scene_done === b.scene_done && a.live_line === b.live_line && a.narration_line === b.narration_line
    && (a.scenes?.length ?? 0) === (b.scenes?.length ?? 0) && (a.scenes ?? []).every((x, i) => x.done === b.scenes![i].done && x.index === b.scenes![i].index && !!x.thumb_url === !!b.scenes![i].thumb_url);
};

const STATUS: Record<string, [Status, Stage?]> = {
  STARTED_PROCESSING: ["running", "starting"],
  PLOT_CREATION: ["running", "writing"],
  ASSETS_CREATION: ["running", "assets"],
  STORYBOARD_CREATION: ["running", "storyboard"],
  RENDERING: ["running", "rendering"],
  COMPLETE: ["complete"],
  ERROR: ["error"],
  FAILED: ["error"],
  CANCELLED: ["error"],
  REJECTED: ["rejected"],
};

export function s3ToHttps(uri: string | null | undefined): string | null {
  if (!uri || typeof uri !== "string") return null;
  const m = uri.match(/^s3:\/\/([^/]+)\/(.+)$/);
  if (!m) return uri;
  const [, bucket, key] = m;
  return bucket === "videomk.com" ? `https://videomk.com/${key}` : `https://${bucket}.s3.amazonaws.com/${key}`;
}

/** One list item from the API (null when it has no id). Unknown statuses count as queued. */
export function normalizeItem(it: any): TaskItem | null {
  const id: string | undefined = it?.video_id || it?.id;
  if (!id) return null;
  let [status, stage] = STATUS[(it?.status || "").toString().toUpperCase()] ?? ["queued", "starting"];
  // A video made from a presentation reports `stage` while the deck is read and the story written (docs/CREATE_API.md); it is ignored afterwards.
  if (stage === "writing" && (it?.stage === "deck_reading" || it?.stage === "deck_writing")) stage = it.stage;
  return {
    id, status, stage: status === "queued" || status === "running" ? stage : undefined,
    title: it?.title,
    editable: it?.editable === true,
    reject_reason: typeof it?.reject_reason === "string" ? it.reject_reason : null,
    download_url: s3ToHttps(it?.video_uri) || it?.download_url || null,
    eta_seconds: typeof it?.eta_seconds === "number" ? it.eta_seconds : null,
    preview_gif_url: (it?.preview_gif_url as string | null) || s3ToHttps(it?.preview_gif_uri) || null,
    created_at: typeof it?.created_at === "string" ? it.created_at : null,
    duration_s: typeof it?.duration_s === "number" ? it.duration_s : null,
    video_url: typeof it?.video_url === "string" ? it.video_url : null,
    can_retry: it?.can_retry === true,
    aspect: typeof it?.aspect === "string" && /^\d+:\d+$/.test(it.aspect) ? it.aspect : null,
    making: status === "queued" || status === "running" ? parseMaking(it?.making) : null,
    ...(parseVideoLook(it?.look) ? { look: parseVideoLook(it.look) } : {}),
    ...((it?.status || "").toString().toUpperCase() === "CANCELLED" ? { cancelled: true } : {}),
  };
}

export const isMaking = (t: TaskItem) => t.status === "running" || t.status === "queued";

export function formatDuration(s?: number | null): string | null {
  if (!s || s <= 0) return null;
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, "0")}`;
}

// ---------------------------------------------------------------- day groups
export type DayGroup = "today" | "yesterday" | "earlier";
const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** A video without a (valid) date goes to Earlier. */
export function dayGroupOf(iso: string | null | undefined, now: Date = new Date()): DayGroup {
  if (!iso) return "earlier";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "earlier";
  if (sameDay(d, now)) return "today";
  const y = new Date(now); y.setDate(y.getDate() - 1);
  return sameDay(d, y) ? "yesterday" : "earlier";
}

/** Keeps the input order inside each group; empty groups are dropped. */
export function groupByDay<T extends { created_at?: string | null }>(items: T[], now: Date = new Date()): { group: DayGroup; items: T[] }[] {
  return (["today", "yesterday", "earlier"] as const)
    .map((group) => ({ group, items: items.filter((i) => dayGroupOf(i.created_at, now) === group) }))
    .filter((g) => g.items.length > 0);
}

// ---------------------------------------------------------------- making progress (four steps: script, voice, pictures, final cut)
export interface MakingInfo { segments: number[]; current: number; line: "starting" | "writing" | "deck_reading" | "deck_writing" | "voice_visuals" | "rendering" }

/** The server reports stages, not scenes (so there is no scene counter yet); the bar is an honest estimate of the four steps. */
export function makingInfo(stage: Stage | undefined): MakingInfo {
  switch (stage) {
    case "writing": return { segments: [0.6, 0, 0, 0], current: 0, line: "writing" };
    case "deck_reading": return { segments: [0.2, 0, 0, 0], current: 0, line: "deck_reading" };
    case "deck_writing": return { segments: [0.65, 0, 0, 0], current: 0, line: "deck_writing" };
    case "assets": return { segments: [1, 0.5, 0.3, 0], current: 1, line: "voice_visuals" };
    case "storyboard": return { segments: [1, 1, 0.6, 0], current: 2, line: "voice_visuals" };
    case "rendering": return { segments: [1, 1, 1, 0.5], current: 3, line: "rendering" };
    default: return { segments: [0.1, 0, 0, 0], current: 0, line: "starting" };
  }
}

/** A stable look for a thumbnail placeholder (0..3), from the id. */
export function placeholderTone(id: string): number {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h % 4;
}

/** Whole minutes left for the card ("about 2 min"), or null while there is no estimate. Under a minute is 0. */
export function minutesLeft(etaSeconds: number | null | undefined): number | null {
  return typeof etaSeconds === "number" && etaSeconds >= 0 ? Math.floor((etaSeconds + 59) / 60) : null;
}

// ---------------------------------------------------------------- the redesigned list: search and a flicker-free thumbnail
const fold = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
/** Videos whose title contains every word of the query (case and accents ignored). An empty query keeps all. */
export function filterVideos<T extends { title?: string }>(items: T[], q: string): T[] {
  const words = fold(q).split(/\s+/).filter(Boolean);
  if (!words.length) return items;
  return items.filter((i) => { const t = fold(i.title ?? ""); return words.every((w) => t.includes(w)); });
}

/** Presigned thumbnail links change on every poll (new signature); the picture behind an id does not. Keeping the first link per id stops the list from re-requesting and flashing. */
export function stableThumbs(prev: Record<string, string>, items: { id: string; preview_gif_url?: string | null }[]): Record<string, string> {
  const next = { ...prev };
  for (const i of items) if (i.preview_gif_url && !next[i.id]) next[i.id] = i.preview_gif_url;
  return next;
}

/** Keeps the previous object for items whose visible fields did not change, so React skips them: a poll that changes one card redraws one card. */
export function reuseUnchanged(prev: TaskItem[], next: TaskItem[]): TaskItem[] {
  const by = new Map(prev.map((p) => [p.id, p] as const));
  return next.map((n) => {
    const p = by.get(n.id);
    if (!p) return n;
    const same = p.status === n.status && p.stage === n.stage && p.title === n.title && p.eta_seconds === n.eta_seconds && p.duration_s === n.duration_s && p.editable === n.editable
      && p.reject_reason === n.reject_reason && (p.preview_gif_url ? true : !n.preview_gif_url) && p.created_at === n.created_at && p.can_retry === n.can_retry && sameMaking(p.making, n.making)
      && !!p.cancelled === !!n.cancelled && JSON.stringify(p.look ?? null) === JSON.stringify(n.look ?? null);
    return same ? p : n;
  });
}

/** Poll delay: quick while something is being made (5 s, 8 s, 12 s ... up to 30 s), none when everything is finished or the tab is hidden. */
export function nextPollMs(attempt: number, anyMaking: boolean, hidden: boolean): number | null {
  if (!anyMaking || hidden) return null;
  return Math.min(30000, 5000 + attempt * 3000);
}

// ---------------------------------------------------------------- try again / remove (docs/CREATE_API.md "Retry a video")
/** What the retry route answered, as the list needs it. "Try again" reuses the SAME video: it never creates a second item and never resends a request without its photos. */
export type RetryOutcome =
  | { ok: true }                                                      // 202 restarted, or 200 already running
  | { ok: false; kind: "attachments" | "limit" | "rejected" | "credits" | "gone" | "unsupported" | "paused" | "error"; message?: string };

export function retryOutcome(status: number, body: any): RetryOutcome {
  const message = typeof body?.message === "string" ? body.message : undefined;
  if (status === 200 || status === 202) return { ok: true };
  if (status === 402) return { ok: false, kind: "credits", message };
  if (status === 429) return { ok: false, kind: "paused", message };
  if (status === 409) {
    const code = String(body?.code ?? "");
    if (code === "attachments_unavailable") return { ok: false, kind: "attachments", message };
    if (code === "retry_limit") return { ok: false, kind: "limit", message };
    if (code === "rejected") return { ok: false, kind: "rejected", message };
    return { ok: false, kind: "error", message };
  }
  if (status === 404) return body?.code === "not_found" ? { ok: false, kind: "gone", message } : { ok: false, kind: "unsupported" };   // an older server has no such route: say so, never resend without the photos
  if (status === 403 || status === 405) return { ok: false, kind: "unsupported" };
  return { ok: false, kind: "error", message };
}

/** The list right after a retry was accepted: the same item, now being made (first in the list until the next poll brings the server's view). */
export function markRetrying(items: TaskItem[], id: string): TaskItem[] {
  return items.map((i) => (i.id === id ? { ...i, status: "running" as Status, stage: "starting" as Stage, can_retry: false, reject_reason: null } : i));
}

// ---------------------------------------------------------------- cancel while making / delete a finished video (docs/CREATE_API.md "Cancel", "Delete")
/** What the cancel route answered. "try_again": the video moved a step between the server's read and write: the same call is sent once more. "done": it finished (or failed)
 *  meanwhile, so there is nothing to cancel and the list is refreshed. */
export type CancelOutcome =
  | { ok: true; refunded: number }
  | { ok: false; kind: "try_again" | "done" | "gone" | "unsupported" | "error"; message?: string };

export function cancelOutcome(status: number, body: any): CancelOutcome {
  const message = typeof body?.message === "string" ? body.message : undefined;
  if (status === 200) return { ok: true, refunded: typeof body?.refunded === "number" && body.refunded > 0 ? Math.floor(body.refunded) : 0 };
  if (status === 409) return body?.code === "try_again" ? { ok: false, kind: "try_again", message } : body?.code === "not_cancellable" ? { ok: false, kind: "done", message } : { ok: false, kind: "error", message };
  if (status === 404) return body?.code === "not_found" ? { ok: false, kind: "gone", message } : { ok: false, kind: "unsupported" };   // an older server has no such route
  if (status === 403 || status === 405) return { ok: false, kind: "unsupported" };
  return { ok: false, kind: "error", message };
}
/** The list right after a cancel: the same item, now stopped (it can be tried again or removed). The next poll brings `can_retry` from the server. */
export function markCancelled(items: TaskItem[], id: string): TaskItem[] {
  return items.map((i) => (i.id === id ? { ...i, status: "error" as Status, stage: undefined, making: null, cancelled: true } : i));
}

/** What DELETE answered. A repeated delete answers 404 not_found, which is success (the card goes). "making": cancel it first. "busy": an edit is rendering. */
export type DeleteOutcome = { ok: true } | { ok: false; kind: "making" | "busy" | "error"; message?: string };
export function deleteOutcome(status: number, body: any): DeleteOutcome {
  const message = typeof body?.message === "string" ? body.message : undefined;
  if ((status >= 200 && status < 300) || status === 404) return { ok: true };
  if (status === 409) return { ok: false, kind: body?.code === "not_deletable" ? "making" : body?.code === "busy" ? "busy" : "error", message };
  return { ok: false, kind: "error", message };
}
