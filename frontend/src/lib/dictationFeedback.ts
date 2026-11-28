// Visible feedback for dictation (docs/DICTATION_FEEDBACK_2026-11-28.md): the pure rules, mirrored on iOS (DictationFeedback.swift) and Android (DictationFeedback.kt).
// Everything here is deterministic: no clock, no DOM. The UI feeds it mic levels (0..1) and time.

export const BAR_COUNT = 28;          // fixed bar count (phones use 24: same rule, narrower capsule)
export const METER_FPS = 25;          // level sampling rate, 20 to 30 is the budget
export const MIN_BAR = 0.1;           // a silent bar is a dot, never a gap: the row always reads as a waveform
export const ATTACK = 0.6;            // fast up
export const RELEASE = 0.12;          // slow down: calm, no flicker
export const SLOW_AFTER_S = 8;        // "taking longer than usual"
export const TIMEOUT_AFTER_S = 60;    // then Retry / phone dictation
export const WARN_SOON_S = 30;        // "30 seconds left"
export const WARN_FINAL_S = 10;       // countdown

/** A scrolling level history: newest bar on the right (Voice Memos, WhatsApp). push() takes the raw mic level 0..1 once per frame. */
export class LevelMeter {
  private smooth = 0;
  private bars: number[];
  constructor(readonly count = BAR_COUNT) { this.bars = new Array(count).fill(MIN_BAR); }
  push(raw: number): number[] {
    const x = Number.isFinite(raw) ? Math.min(1, Math.max(0, raw)) : 0;
    this.smooth += (x - this.smooth) * (x > this.smooth ? ATTACK : RELEASE);
    this.bars.shift(); this.bars.push(barHeight(this.smooth));
    return this.heights();
  }
  heights(): number[] { return [...this.bars]; }
  reset(): void { this.smooth = 0; this.bars.fill(MIN_BAR); }
}
/** Loudness to bar height: speech sits at RMS 0.02 to 0.3, so the curve is steep at the bottom (x^0.5 after a x3.2 gain). */
export function barHeight(level: number): number {
  const v = Math.min(1, Math.max(0, level) * 3.2);
  return MIN_BAR + (1 - MIN_BAR) * Math.sqrt(v);
}
/** RMS of 8-bit time-domain samples (128 = silence), as an AnalyserNode gives them. */
export function rmsOfBytes(data: ArrayLike<number>): number {
  if (!data.length) return 0;
  let s = 0; for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; s += v * v; }
  return Math.sqrt(s / data.length);
}

export type Phase = "idle" | "requesting" | "recording" | "transcribing" | "failed" | "inserted";
export interface FeedbackState {
  phase: Phase;
  startedMs: number | null;   // recording start
  waitStartMs: number | null; // transcribing start
  nowMs: number;
  limitS: number;             // per-clip or daily cap, whichever is nearer
  failure: string | null;
}
export type FeedbackEvent =
  | { type: "request" } | { type: "granted"; nowMs: number; limitS: number } | { type: "denied" }
  | { type: "stop"; nowMs: number } | { type: "ok" } | { type: "fail"; kind: string }
  | { type: "cancel" } | { type: "retry"; nowMs: number } | { type: "dismiss" } | { type: "tick"; nowMs: number };
export const initialFeedback = (): FeedbackState => ({ phase: "idle", startedMs: null, waitStartMs: null, nowMs: 0, limitS: 360, failure: null });

export function feedbackReduce(s: FeedbackState, e: FeedbackEvent): FeedbackState {
  switch (e.type) {
    case "request": return s.phase === "idle" || s.phase === "inserted" || s.phase === "failed" ? { ...initialFeedback(), phase: "requesting" } : s;
    case "granted": return s.phase === "requesting" ? { ...s, phase: "recording", startedMs: e.nowMs, nowMs: e.nowMs, limitS: e.limitS } : s;
    case "denied": return s.phase === "requesting" || s.phase === "recording" ? initialFeedback() : s;
    case "stop": return s.phase === "recording" ? { ...s, phase: "transcribing", waitStartMs: e.nowMs, nowMs: e.nowMs } : s;
    case "ok": return s.phase === "transcribing" ? { ...s, phase: "inserted" } : s;
    case "fail": return s.phase === "transcribing" ? { ...s, phase: "failed", failure: e.kind } : s;
    case "cancel": return s.phase === "recording" || s.phase === "transcribing" || s.phase === "requesting" ? initialFeedback() : s;
    case "retry": return s.phase === "failed" ? { ...s, phase: "transcribing", waitStartMs: e.nowMs, nowMs: e.nowMs, failure: null } : s;
    case "dismiss": return s.phase === "failed" || s.phase === "inserted" ? initialFeedback() : s;
    case "tick": return { ...s, nowMs: Math.max(s.nowMs, e.nowMs) };
  }
}
export const elapsedS = (s: FeedbackState): number => (s.startedMs == null ? 0 : Math.max(0, Math.floor((s.nowMs - s.startedMs) / 1000)));
export const waitedS = (s: FeedbackState): number => (s.waitStartMs == null ? 0 : Math.max(0, Math.floor((s.nowMs - s.waitStartMs) / 1000)));
/** The nearer of the clip limit and what is left of today's allowance (never above the clip limit, never below 0). */
export function effectiveLimitS(maxClipS: number, secondsLeftToday: number | null): number {
  return Math.max(0, secondsLeftToday == null ? maxClipS : Math.min(maxClipS, secondsLeftToday));
}
/** m:ss */
export function formatTimer(totalS: number): string {
  const t = Math.max(0, Math.floor(totalS)); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}
export type Warning = "none" | "soon" | "final";
export function warningFor(s: FeedbackState): { level: Warning; remainingS: number } {
  const remainingS = Math.max(0, s.limitS - elapsedS(s));
  if (s.phase !== "recording") return { level: "none", remainingS };
  return { level: remainingS <= WARN_FINAL_S ? "final" : remainingS <= WARN_SOON_S ? "soon" : "none", remainingS };
}
/** Transcribing too long: "slow" shows the hint, "timeout" shows Retry. */
export function waitState(s: FeedbackState): "normal" | "slow" | "timeout" {
  if (s.phase !== "transcribing") return "normal";
  const w = waitedS(s); return w >= TIMEOUT_AFTER_S ? "timeout" : w >= SLOW_AFTER_S ? "slow" : "normal";
}
/** The screen-reader announcements, polite, only on change (never per tick): at start, at the thresholds, at the end. */
export function announcementKey(s: FeedbackState): string | null {
  switch (s.phase) {
    case "recording": { const w = warningFor(s); return w.level === "final" ? "warn_final" : w.level === "soon" ? "warn_soon" : "listening"; }
    case "transcribing": return waitState(s) === "slow" ? "slow" : "transcribing";
    case "failed": return "failed";
    case "inserted": return "inserted";
    default: return null;
  }
}
