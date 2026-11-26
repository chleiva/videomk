// The video list: item shape, normalisation of the API payload, day groups (Today / Yesterday / Earlier, as in the apps' DayGroup) and the making progress.
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
}

const STATUS: Record<string, [Status, Stage?]> = {
  STARTED_PROCESSING: ["running", "starting"],
  PLOT_CREATION: ["running", "writing"],
  ASSETS_CREATION: ["running", "assets"],
  STORYBOARD_CREATION: ["running", "storyboard"],
  RENDERING: ["running", "rendering"],
  COMPLETE: ["complete"],
  ERROR: ["error"],
  FAILED: ["error"],
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
