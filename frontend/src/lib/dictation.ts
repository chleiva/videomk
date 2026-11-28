// Voice prompt through the Web Speech API where the browser has it (Chrome, Edge, Safari); the mic button is not shown elsewhere. Nothing is recorded by us: the browser's own
// speech service turns speech into text that lands in the prompt box, which the person can edit. Feature-detected, so server rendering and Firefox never touch it.
//
// What this module guarantees (docs/DICTATION_FIXES_2026-11-28.md): it keeps listening through pauses (the browser ends a session by itself after silence or about a minute;
// we start a new one until the person stops, 5 minutes pass, 90 seconds go by with nothing said, or it keeps failing at once), every phrase is APPENDED to the text that was
// in the box when dictation started, and text changed by hand meanwhile is never overwritten (the box becomes the new base).
type Ctor = new () => any;
export function speechCtor(win: any = typeof window !== "undefined" ? window : undefined): Ctor | null {
  return win?.SpeechRecognition ?? win?.webkitSpeechRecognition ?? null;
}
export const dictationSupported = (win?: any): boolean => speechCtor(win) !== null;

/** `base + one space + segment`: no space when the base is empty or ends with a new line, trailing spaces of the base are not doubled, a blank segment changes nothing. */
export function appendDictation(current: string, heard: string): string {
  const h = heard.trim();
  if (!h) return current;
  const b = current.replace(/[ \t]+$/, "");
  return !b || b.endsWith("\n") ? b + h : `${b} ${h}`;
}

/** The text rules, pure: the field is always `base + running transcript`; a finished session is folded into the base; a field changed by hand rebases. */
export class DictationText {
  base: string;
  private expected: string;
  constructor(startingWith: string, private maxLength = Infinity) { this.base = startingWith; this.expected = startingWith; }
  /** `{ write }` = set the field to this text; `{ rebased }` = the person edited the box: it is the new base, restart the recognizer and write nothing now. */
  hear(segment: string, field: string): { write: string } | { rebased: true } {
    if (field !== this.expected) { this.base = field; this.expected = field; return { rebased: true }; }
    const text = appendDictation(this.base, segment).slice(0, this.maxLength);
    this.expected = text;
    return { write: text };
  }
  fold(segment: string, field: string): { write: string } | { rebased: true } {
    const step = this.hear(segment, field);
    if ("write" in step) this.base = step.write;
    return step;
  }
}

/** When to start another recognition session and when to stop. Pure; the caller passes milliseconds. */
export class DictationRestartPolicy {
  private sessionStart = 0; private lastText = 0; private started = 0; private rapid = 0;
  constructor(private maxMs = 5 * 60_000, private idleMs = 90_000, private maxRapid = 4) {}
  sessionStarted(now: number) { this.sessionStart = now; this.lastText = now; this.started = now; this.rapid = 0; }
  recognizerStarted(now: number) { this.started = now; }
  textArrived(now: number) { this.lastText = now; this.rapid = 0; }
  ended(hadText: boolean, now: number): "restart" | "limit" | "idle" | "failing" {
    if (now - this.sessionStart >= this.maxMs) return "limit";
    if (hadText) { this.rapid = 0; return "restart"; }
    if (now - this.started < 1000) { this.rapid++; if (this.rapid >= this.maxRapid) return "failing"; } else this.rapid = 0;
    if (now - this.lastText >= this.idleMs) return "idle";
    return "restart";
  }
}

export interface Dictation { stop(): void }
export type DictationEnd = "done" | "denied" | "error" | "language";
export interface DictationOptions {
  /** BCP-47 tag of the language to listen in (en-US, es-MX): see `speechLang`. */
  lang: string;
  /** What the text box holds right now (read on every update, so hand edits are noticed). */
  getText: () => string;
  /** Put this text in the box. */
  setText: (text: string) => void;
  /** Fires once, when listening stops for any reason. */
  onEnd: (reason: DictationEnd) => void;
  maxLength?: number;
  win?: any;
  /** Wait before a new session starts after one ended by itself. */
  restartDelayMs?: number;
}

/** Starts listening. Returns null where the browser has no speech recognition or refuses to start. */
export function startDictation(o: DictationOptions): Dictation | null {
  const C = speechCtor(o.win);
  if (!C) return null;
  const text = new DictationText(o.getText(), o.maxLength ?? Infinity);
  const policy = new DictationRestartPolicy();
  policy.sessionStarted(Date.now());
  let wanting = true, ended = false, reason: DictationEnd = "done", gen = 0, segment = "", segmentHadText = false, gotText = false;
  let rec: any = null, timer: ReturnType<typeof setTimeout> | undefined;

  const finish = () => { if (ended) return; ended = true; wanting = false; if (timer) clearTimeout(timer); o.onEnd(reason); };
  const detach = () => {
    gen++;
    const r = rec; rec = null;
    if (r) { r.onresult = r.onerror = r.onend = null; try { r.abort(); } catch { /* already stopped */ } }
  };
  const apply = (final: boolean) => {
    const field = o.getText();
    const step = final ? text.fold(segment, field) : text.hear(segment, field);
    if ("write" in step) o.setText(step.write);
    else if (wanting) { detach(); begin(); }   // the box was edited: what was said so far is in it; start a fresh session from nothing
  };
  const begin = (): boolean => {
    const r = new C();
    rec = r; const mine = ++gen; segment = ""; segmentHadText = false;
    r.lang = o.lang; r.interimResults = true; r.continuous = true; r.maxAlternatives = 1;
    r.onresult = (e: any) => {
      if (mine !== gen) return;
      let t = "";
      for (let i = 0; i < e.results.length; i++) t += e.results[i][0]?.transcript ?? "";
      if (!t.trim()) return;
      segment = t; segmentHadText = true; gotText = true; policy.textArrived(Date.now());
      apply(false);
    };
    r.onerror = (e: any) => {
      if (mine !== gen) return;
      const code = e?.error;
      if (code === "not-allowed" || code === "service-not-allowed") { reason = "denied"; wanting = false; }
      else if (code === "language-not-supported") { reason = "language"; wanting = false; }
      else if (code === "audio-capture") { reason = "error"; wanting = false; }
      else if (code === "network" && !gotText) { reason = "error"; wanting = false; }
      // no-speech, aborted, a network blip after speech: the normal end of a pause; onend decides
    };
    r.onend = () => {
      if (mine !== gen) return;
      rec = null;
      if (segment) { apply(true); segment = ""; }
      if (!wanting) return finish();
      const next = policy.ended(segmentHadText, Date.now());
      if (next === "failing") reason = gotText ? "done" : "error";
      if (next !== "restart") return finish();
      timer = setTimeout(() => { timer = undefined; if (!wanting) return finish(); if (!begin()) finish(); }, o.restartDelayMs ?? 250);
    };
    try { policy.recognizerStarted(Date.now()); r.start(); return true; } catch { rec = null; if (!gotText) reason = "error"; return false; }
  };

  if (!begin()) return null;
  return {
    stop: () => {
      wanting = false;
      if (timer) { clearTimeout(timer); timer = undefined; return finish(); }
      if (!rec) return finish();
      try { rec.stop(); } catch { finish(); }   // the final text arrives, then onend
    },
  };
}

/** The language to listen in: the app's own (en or es); the browser's preferred languages only choose the variant (es-MX rather than es-ES). */
export function speechLang(locale: string, preferred: readonly string[] = typeof navigator !== "undefined" ? (navigator.languages ?? [navigator.language ?? ""]) : []): string {
  const code = locale === "es" ? "es" : "en";
  const same = preferred.find((p) => p && p.toLowerCase().split("-")[0] === code && p.includes("-"));
  return same ?? (code === "es" ? "es-ES" : "en-US");
}
