// Voice prompt through the Web Speech API where the browser has it (Chrome, Edge, Safari); the mic button is not shown elsewhere. Nothing is recorded by us: the browser's own
// speech service turns speech into text that lands in the prompt box, which the person can edit. Feature-detected, so server rendering and Firefox never touch it.
type Ctor = new () => any;
export function speechCtor(win: any = typeof window !== "undefined" ? window : undefined): Ctor | null {
  return win?.SpeechRecognition ?? win?.webkitSpeechRecognition ?? null;
}
export const dictationSupported = (win?: any): boolean => speechCtor(win) !== null;

/** Appends dictated text to what is already in the box (one space between, trimmed). */
export function appendDictation(current: string, heard: string): string {
  const h = heard.trim();
  if (!h) return current;
  return current.trim() ? `${current.replace(/\s+$/, "")} ${h}` : h;
}

export interface Dictation { stop(): void }
/** Starts listening in `lang` (a BCP-47 tag: en-US, es-ES). `onText` gets the running transcript of this session; `onEnd` fires when listening stops for any reason. */
export function startDictation(lang: string, onText: (t: string, final: boolean) => void, onEnd: (reason: "done" | "denied" | "error") => void, win?: any): Dictation | null {
  const C = speechCtor(win);
  if (!C) return null;
  const rec = new C();
  rec.lang = lang; rec.interimResults = true; rec.continuous = true; rec.maxAlternatives = 1;
  let reason: "done" | "denied" | "error" = "done";
  rec.onresult = (e: any) => {
    let text = "", final = true;
    for (let i = 0; i < e.results.length; i++) { text += e.results[i][0]?.transcript ?? ""; if (!e.results[i].isFinal) final = false; }
    onText(text, final);
  };
  rec.onerror = (e: any) => { reason = e?.error === "not-allowed" || e?.error === "service-not-allowed" ? "denied" : e?.error === "no-speech" || e?.error === "aborted" ? "done" : "error"; };
  rec.onend = () => onEnd(reason);
  try { rec.start(); } catch { return null; }
  return { stop: () => { try { rec.stop(); } catch { /* already stopped */ } } };
}

export const speechLang = (locale: string): string => (locale === "es" ? "es-ES" : "en-US");
