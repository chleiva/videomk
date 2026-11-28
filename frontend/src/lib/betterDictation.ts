// "Better dictation" (Pro and Max): the mic records a clip, the server turns it into text (docs/SPEECH_TO_TEXT_2026-11-28.md sections 9 and 10, docs/BETTER_DICTATION_CLIENTS_2026-11-28.md).
// The browser's own speech recognition keeps running as a live preview and as the fallback: every error here leaves the text the native engine already wrote in the box.
// Audio is never logged or stored: it lives in memory until the upload ends.
import { getAuthorizationHeader } from "./auth";
import { apiGateway } from "./config";
import { currentLocaleHeaders } from "./i18n";
import { appendDictation, startDictation } from "./dictation";
import type { Dictation, DictationOptions } from "./dictation";
import { METER_FPS, rmsOfBytes } from "./dictationFeedback";

export const MAX_DICTATION_IDS = 20;
export const HARD_MAX_SECONDS = 360;
export const HARD_MAX_BYTES = 3 * 1024 * 1024;

/** `capabilities.dictation` as the app uses it. */
export interface DictationCaps { premium: boolean; available: boolean; paused: boolean; secondsLeft: number | null; maxClipSeconds: number; maxClipBytes: number; requiresPlan: string | null }
export function parseDictationCaps(raw: any): DictationCaps | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const num = (v: unknown, d: number) => (typeof v === "number" && Number.isFinite(v) && v > 0 ? v : d);
  return {
    premium: raw.premium === true, available: raw.available === true, paused: raw.paused === true,
    secondsLeft: typeof raw.seconds_left_today === "number" ? raw.seconds_left_today : null,
    maxClipSeconds: Math.min(num(raw.max_clip_seconds, HARD_MAX_SECONDS), HARD_MAX_SECONDS), maxClipBytes: Math.min(num(raw.max_clip_bytes, HARD_MAX_BYTES), HARD_MAX_BYTES),
    requiresPlan: typeof raw.requires_plan === "string" ? raw.requires_plan : null,
  };
}
/** Better dictation can be used now: the plan has it, it is not paused, seconds are left. */
export const betterAvailable = (d: DictationCaps | undefined): boolean => !!d && d.available && !d.paused;
/** The Options sheet shows the small upgrade hint: the plan lacks it and says which plan has it. */
export const showUpgradeHint = (d: DictationCaps | undefined): boolean => !!d && !d.premium && !!d.requiresPlan;

const PREF = "vmk.better_dictation";
/** The person's choice (default on). Only an explicit "off" turns it off. */
export function betterPreferred(storage: Pick<Storage, "getItem"> | undefined = safeStorage()): boolean { try { return storage?.getItem(PREF) !== "off"; } catch { return true; } }
export function setBetterPreferred(on: boolean, storage: Pick<Storage, "setItem"> | undefined = safeStorage()): void { try { storage?.setItem(PREF, on ? "on" : "off"); } catch { /* private mode */ } }
function safeStorage(): Storage | undefined { try { return typeof localStorage !== "undefined" ? localStorage : undefined; } catch { return undefined; } }

/** Every id that produced text, sent as `dictation_ids` on the next create. At most 20 (the newest are kept), no repeats. */
export class DictationIds {
  private ids: string[] = [];
  add(id: string): void { if (!/^[0-9a-f]{32}$/i.test(id) || this.ids.includes(id)) return; this.ids.push(id); if (this.ids.length > MAX_DICTATION_IDS) this.ids.shift(); }
  list(): string[] { return [...this.ids]; }
  /** What goes in the create request: nothing when empty. */
  extra(): { dictation_ids?: string[] } { return this.ids.length ? { dictation_ids: this.list() } : {}; }
  clear(): void { this.ids = []; }
}

export type BetterError = "plan" | "quota" | "too_long" | "failed" | "paused" | "bad_audio" | "auth" | "network";
export type BetterResult = { ok: true; id: string; text: string; seconds: number; secondsLeft: number | null } | { ok: false; kind: BetterError; message?: string };

/** What the server answered, pure. */
export function dictationOutcome(status: number, body: any): BetterResult {
  body = body && typeof body === "object" ? body : {};
  if (status >= 200 && status < 300 && typeof body.id === "string" && typeof body.text === "string") return { ok: true, id: body.id, text: body.text, seconds: Number(body.seconds) || 0, secondsLeft: typeof body.seconds_left_today === "number" ? body.seconds_left_today : null };
  const message = typeof body.message === "string" ? body.message : undefined;
  const code = body.code;
  if (code === "dictation_plan") return { ok: false, kind: "plan", message };
  if (code === "dictation_quota" || status === 429) return { ok: false, kind: "quota", message };
  if (code === "dictation_too_long" || status === 413) return { ok: false, kind: "too_long", message };
  if (code === "dictation_paused" || status === 503) return { ok: false, kind: "paused", message };
  if (code === "bad_audio") return { ok: false, kind: "bad_audio", message };
  if (status === 401 || status === 403) return { ok: false, kind: "auth", message };
  return { ok: false, kind: "failed", message };
}

/** The line to show for a failure, as a string-table key; null = fall back silently (the person did not do anything wrong and nothing useful can be said). */
export function betterErrorKey(kind: BetterError): string | null {
  switch (kind) {
    case "quota": return "create.better_quota";
    case "too_long": return "create.better_too_long";
    case "failed": case "network": case "bad_audio": return "create.better_failed";
    default: return null;   // plan, paused, auth
  }
}

/** Base64 of a blob, in chunks (a 3 MB string built in one go would overflow the argument limit). */
export async function blobToBase64(b: Blob): Promise<string> {
  const bytes = new Uint8Array(await b.arrayBuffer());
  let s = ""; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

export interface ClipRequest { blob: Blob; mime: string; seconds: number; languages: string[]; prompt?: string }
/** POST /users/{id}/dictation. Any failure is a typed result, never a throw. */
export async function sendDictation(c: ClipRequest, fetchImpl: typeof fetch = fetch): Promise<BetterResult> {
  try {
    const { Authorization, userId } = await getAuthorizationHeader();
    if (!userId) return { ok: false, kind: "auth" };
    const body = JSON.stringify({ audio: await blobToBase64(c.blob), mime: c.mime, seconds: Math.round(c.seconds * 10) / 10, languages: c.languages.slice(0, 4), ...(c.prompt ? { prompt: c.prompt.slice(-400) } : {}) });
    const res = await fetchImpl(apiGateway.dictation(userId), { method: "POST", headers: { "Content-Type": "application/json", Authorization, ...currentLocaleHeaders() }, body });
    let json: any = null; try { json = await res.json(); } catch { /* not json */ }
    return dictationOutcome(res.status, json);
  } catch { return { ok: false, kind: "network" }; }
}

/**
 * Where the better text goes. `base` is the field when recording started, `native` what the native preview wrote (the field then held exactly that).
 * Field unchanged since the preview: the dictated span is replaced by the better text (base + better), so words are not doubled. Field edited by hand:
 * the person's text wins and is returned untouched (null = do not write); the id is still kept because the clip was paid. No preview: plain append.
 */
export function placeBetterText(base: string, native: string, field: string, better: string): string | null {
  if (!better.trim()) return null;
  if (field === native) return appendDictation(base, better);
  return null;
}

export interface BetterOptions {
  lang: string;            // en-US / es-MX for the preview
  languages: string[];     // ISO 639-1 sent to the server: the app language
  getText: () => string;
  setText: (t: string) => void;
  maxLength?: number;
  maxSeconds: number;
  maxBytes: number;
  onWorking: () => void;               // recording ended, the upload started (again after retry())
  onLevel?: (level: number) => void;   // real mic level 0..1, about 25 times a second while recording
  /** The upload failed in a way worth retrying (network, server): the clip is kept in memory; retry() sends it again, dismiss() gives up (onResult then fires). Without this callback a failure ends at once. */
  onRetryable?: (kind: BetterError) => void;
  sendTimeoutMs?: number;              // an upload that takes longer counts as failed (default 60 s)
  onResult: (r: { id?: string; kind?: BetterError; limit?: boolean; denied?: boolean; cancelled?: boolean }) => void;   // exactly once, after everything ended
  deps?: Partial<BetterDeps>;
}
export interface BetterDeps {
  getUserMedia: (c: MediaStreamConstraints) => Promise<MediaStream>;
  Recorder: any;
  native: (o: DictationOptions) => Dictation | null;
  send: (c: ClipRequest) => Promise<BetterResult>;
  AudioCtx: any;   // AudioContext (level meter); absent = no levels
  setTimer: (f: () => void, ms: number) => any;
  clearTimer: (h: any) => void;
  now: () => number;
}
const MIMES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];
const defaults = (): BetterDeps => ({
  getUserMedia: (c) => navigator.mediaDevices.getUserMedia(c),
  Recorder: typeof MediaRecorder !== "undefined" ? MediaRecorder : null,
  native: startDictation,
  send: (c) => sendDictation(c),
  AudioCtx: typeof AudioContext !== "undefined" ? AudioContext : (globalThis as any).webkitAudioContext ?? null,
  setTimer: (f, ms) => setTimeout(f, ms), clearTimer: (h) => clearTimeout(h), now: () => Date.now(),
});
export const recordingSupported = (): boolean => typeof MediaRecorder !== "undefined" && !!globalThis.navigator?.mediaDevices?.getUserMedia;

export interface BetterHandle extends Dictation { cancel(): void; retry(): void; dismiss(): void }
const noop = (): BetterHandle => ({ stop() {}, cancel() {}, retry() {}, dismiss() {} });

/** Records and, on stop, uploads. Resolves to a handle (stop uploads, cancel discards, retry/dismiss after a retryable failure); returns null when the microphone cannot be opened (the caller then uses the native engine alone). */
export async function startBetter(o: BetterOptions): Promise<BetterHandle | null> {
  const d = { ...defaults(), ...o.deps };
  if (!d.Recorder) return null;
  let stream: MediaStream;
  try { stream = await d.getUserMedia({ audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true } }); }
  catch { o.onResult({ denied: true }); return noop(); }
  const base = o.getText();
  let nativeWrote = base;   // what the preview last put in the box
  const nativeEnded = { done: false }; let nativeResolve: () => void = () => {}; const nativeP = new Promise<void>((r) => { nativeResolve = r; });
  const native = d.native({
    lang: o.lang, maxLength: o.maxLength,
    getText: o.getText, setText: (t) => { nativeWrote = t; o.setText(t); },
    onEnd: () => { nativeEnded.done = true; nativeResolve(); },
  });
  if (!native) { nativeEnded.done = true; nativeResolve(); }

  const mime = (d.Recorder.isTypeSupported ? MIMES.find((m) => d.Recorder.isTypeSupported(m)) : undefined) ?? "";
  let rec: any;
  const chunks: Blob[] = [];
  try { rec = new d.Recorder(stream, { ...(mime ? { mimeType: mime } : {}), audioBitsPerSecond: 32000 }); }
  catch { stream.getTracks().forEach((t) => t.stop()); native?.stop(); o.onResult({ denied: true }); return noop(); }
  const t0 = d.now(); let stopped = false, limit = false, timer: any, cancelled = false, finished = false, token = 0, sendTimer: any, meterTimer: any, ctx: any;
  const recordingDone = new Promise<void>((resolve) => { rec.onstop = () => resolve(); });
  rec.ondataavailable = (e: any) => { if (e?.data?.size) chunks.push(e.data); };
  rec.start(1000);
  const finish = (r: Parameters<BetterOptions["onResult"]>[0]) => { if (finished) return; finished = true; d.clearTimer(sendTimer); o.onResult(r); };
  // the level meter: an AnalyserNode on the same stream, sampled at METER_FPS (cheap: 256 samples, one RMS)
  const stopMeter = () => { if (meterTimer) { clearInterval(meterTimer); meterTimer = null; } try { ctx?.close?.(); } catch { /* closed */ } ctx = null; };
  if (o.onLevel && d.AudioCtx) {
    try {
      ctx = new d.AudioCtx(); const an = ctx.createAnalyser(); an.fftSize = 256; an.smoothingTimeConstant = 0; ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize);
      meterTimer = setInterval(() => { an.getByteTimeDomainData(buf); o.onLevel?.(rmsOfBytes(buf)); }, Math.round(1000 / METER_FPS));
    } catch { stopMeter(); }
  }
  let clip: { blob: Blob; seconds: number } | null = null;
  const upload = async (again = false) => {
    if (!clip) return;
    const my = ++token; if (again) o.onWorking();
    const fail = (kind: BetterError) => { if (o.onRetryable && (kind === "failed" || kind === "network")) { d.clearTimer(sendTimer); o.onRetryable(kind); } else finish({ kind, limit }); };
    sendTimer = d.setTimer(() => { if (my !== token || cancelled || finished) return; token++; fail("network"); }, o.sendTimeoutMs ?? 60000);
    const r = await d.send({ blob: clip.blob, mime: clip.blob.type || "audio/webm", seconds: Math.min(clip.seconds, o.maxSeconds), languages: o.languages, prompt: base.trim() || undefined });
    if (my !== token || cancelled || finished) return;
    d.clearTimer(sendTimer);
    if (!r.ok) return fail(r.kind);
    const next = placeBetterText(base, nativeWrote, o.getText(), r.text);
    if (next !== null) o.setText(o.maxLength ? next.slice(0, o.maxLength) : next);
    clip = null; finish({ id: r.id, limit });
  };
  const halt = () => {
    if (stopped) return; stopped = true; d.clearTimer(timer); stopMeter();
    if (!cancelled) o.onWorking();
    try { rec.state !== "inactive" && rec.stop(); } catch { /* already stopped */ }
    native?.stop();
    void (async () => {
      await Promise.all([recordingDone, nativeP]);
      stream.getTracks().forEach((t) => t.stop());
      if (cancelled) { chunks.length = 0; return; }
      const seconds = (d.now() - t0) / 1000;
      const blob = new Blob(chunks, { type: rec.mimeType || mime || "audio/webm" }); chunks.length = 0;
      if (blob.size === 0) return finish({ limit });
      if (blob.size > o.maxBytes || seconds > o.maxSeconds + 2) return finish({ kind: "too_long", limit });
      clip = { blob, seconds };
      await upload();
    })();
  };
  timer = d.setTimer(() => { limit = true; halt(); }, o.maxSeconds * 1000);
  return {
    stop: halt,
    /** Recording: throw the clip away and put the box back as it was. Transcribing: stop waiting (the words the phone heard stay). */
    cancel() {
      if (finished || cancelled) return; cancelled = true; token++; clip = null;
      if (!stopped) { o.setText(base); halt(); }
      finish({ cancelled: true });
    },
    retry() { if (!finished && !cancelled && clip) void upload(true); },
    dismiss() { if (finished) return; clip = null; finish({ kind: "failed", limit }); },
  };
}
