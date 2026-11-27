// The watch page's logic, kept free of the DOM so it is tested directly (player.test.ts): clock text, playback speeds, keyboard shortcuts, seeking, file names.

export const SPEEDS = [0.75, 1, 1.25, 1.5, 2] as const;
export const DEFAULT_SPEED = 1;

/** m:ss, or h:mm:ss from one hour. Anything that is not a finite, positive number reads 0:00. */
export function formatClock(seconds: number | null | undefined): string {
  const s = typeof seconds === "number" && Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  const two = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${two(m)}:${two(r)}` : `${m}:${two(r)}`;
}

/** The next speed in the cycle (1x -> 1.25x -> ... -> 2x -> 0.75x -> 1x). An unknown speed goes back to 1x. */
export function nextSpeed(current: number): number {
  const i = SPEEDS.indexOf(current as (typeof SPEEDS)[number]);
  return i < 0 ? DEFAULT_SPEED : SPEEDS[(i + 1) % SPEEDS.length];
}

/** "1x", "1.25x", "0.75x". */
export const speedLabel = (s: number): string => `${Number.isInteger(s) ? s : String(s)}x`;

/** A position inside [0, duration]; an unknown duration allows only forward from 0. */
export function clampTime(t: number, duration: number): number {
  if (!Number.isFinite(t)) return 0;
  const max = Number.isFinite(duration) && duration > 0 ? duration : Number.POSITIVE_INFINITY;
  return Math.min(Math.max(0, t), max);
}

export type PlayerAction =
  | { type: "toggle" } | { type: "seek"; by: number } | { type: "seekTo"; fraction: number } | { type: "volume"; by: number }
  | { type: "mute" } | { type: "fullscreen" } | { type: "pip" } | { type: "captions" } | { type: "speed"; direction: 1 | -1 };

export interface KeyInfo { key: string; shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; targetTag?: string; targetEditable?: boolean }

/**
 * What a key press means for the player, or null to leave it alone. YouTube-style shortcuts people already know:
 * space/k play, left/right 5 s, j/l 10 s, up/down volume, m mute, f full screen, p picture in picture, c captions, 0-9 jump, < > speed.
 * Never when a modifier is held (browser shortcuts), when typing in a field, or for Space/Enter on a focused button or link (they activate it).
 */
export function actionForKey(k: KeyInfo): PlayerAction | null {
  if (k.ctrlKey || k.metaKey || k.altKey) return null;
  const tag = (k.targetTag || "").toLowerCase();
  // The scrubber and volume sliders are inputs of type range: arrows move them natively, so leave every input alone.
  if (k.targetEditable === true || tag === "input" || tag === "textarea" || tag === "select") return null;
  if ((k.key === " " || k.key === "Enter") && (tag === "button" || tag === "a" || tag === "summary")) return null;
  switch (k.key) {
    case " ": case "k": case "K": return { type: "toggle" };
    case "ArrowLeft": return { type: "seek", by: -5 };
    case "ArrowRight": return { type: "seek", by: 5 };
    case "j": case "J": return { type: "seek", by: -10 };
    case "l": case "L": return { type: "seek", by: 10 };
    case "ArrowUp": return { type: "volume", by: 0.1 };
    case "ArrowDown": return { type: "volume", by: -0.1 };
    case "m": case "M": return { type: "mute" };
    case "f": case "F": return { type: "fullscreen" };
    case "p": case "P": return { type: "pip" };
    case "c": case "C": return { type: "captions" };
    case ">": return { type: "speed", direction: 1 };
    case "<": return { type: "speed", direction: -1 };
    default:
      if (/^[0-9]$/.test(k.key)) return { type: "seekTo", fraction: Number(k.key) / 10 };
      return null;
  }
}

/** A safe download name: no path or reserved characters, at most 80 characters, ".mp4". */
export function safeFileName(title: string | null | undefined, fallback = "video"): string {
  const base = String(title ?? "").replace(/[\\/:*?"<>|\u0000-\u001f]+/g, " ").replace(/\s+/g, " ").trim().slice(0, 80).trim();
  return `${base || fallback}.mp4`;
}

/** The shape of a video from its pixels: 16:9, 9:16, 1:1, 4:5 (nearest), used to size the player. */
export function aspectLabel(width: number, height: number): "16:9" | "9:16" | "1:1" | "4:5" | null {
  if (!(width > 0) || !(height > 0)) return null;
  const r = width / height;
  const options: [number, "16:9" | "9:16" | "1:1" | "4:5"][] = [[16 / 9, "16:9"], [9 / 16, "9:16"], [1, "1:1"], [4 / 5, "4:5"]];
  return options.reduce((best, o) => (Math.abs(o[0] - r) < Math.abs(best[0] - r) ? o : best))[1];
}

/** The height label of a video ("1080p") from its short side, as the apps show it. */
export function qualityLabel(width: number, height: number): string | null {
  const short = Math.min(width, height);
  if (!(short > 0)) return null;
  const steps = [2160, 1440, 1080, 720, 480];
  const hit = steps.find((s) => short >= s * 0.95);
  return hit ? `${hit}p` : `${Math.round(short)}p`;
}

/** The caption under the video: "1:20 · 1080p" (the only metadata we show). */
export function metaLine(duration: number | null | undefined, width: number, height: number): string {
  const parts = [duration && duration > 0 ? formatClock(duration) : null, qualityLabel(width, height)].filter(Boolean);
  return parts.join(" · ");
}
