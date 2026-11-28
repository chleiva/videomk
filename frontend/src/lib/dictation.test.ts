import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { appendDictation, DictationRestartPolicy, DictationText, dictationSupported, speechLang, startDictation } from "./dictation";

/** A fake Web Speech recognizer: tests drive it by hand, no microphone. */
function fakeBrowser() {
  const made: any[] = [];
  function Fake(this: any) {
    made.push(this);
    this.started = false;
    this.start = () => { this.started = true; };
    this.stop = () => { this.onend?.(); };
    this.abort = () => { this.aborted = true; };
  }
  const say = (r: any, ...phrases: string[]) => r.onresult({ results: phrases.map((p) => Object.assign([{ transcript: p }], { isFinal: false })) });
  return { win: { SpeechRecognition: Fake }, made, say };
}

describe("dictation text", () => {
  it("is only offered where the browser has speech recognition (prefixed or not)", () => {
    expect(dictationSupported({})).toBe(false);
    expect(dictationSupported({ webkitSpeechRecognition: function () {} })).toBe(true);
    expect(dictationSupported({ SpeechRecognition: function () {} })).toBe(true);
    expect(startDictation({ lang: "en-US", getText: () => "", setText: () => {}, onEnd: () => {}, win: {} })).toBeNull();
  });
  it("appends what was heard with one space and never adds an empty string", () => {
    expect(appendDictation("", " a video about bees ")).toBe("a video about bees");
    expect(appendDictation("How a forest breathes  ", "for teenagers")).toBe("How a forest breathes for teenagers");
    expect(appendDictation("keep", "  ")).toBe("keep");
    expect(appendDictation("one\n", "two")).toBe("one\ntwo");
  });
  it("speaking again appends, partial results never reset the base", () => {
    const d = new DictationText("About bees"); let field = "About bees";
    const w = (s: { write: string } | { rebased: true }) => { if ("write" in s) field = s.write; };
    w(d.hear("and", field)); w(d.hear("and honey", field)); w(d.fold("and honey", field));
    expect(field).toBe("About bees and honey");
    w(d.hear("for", field)); w(d.fold("for kids", field));
    expect(field).toBe("About bees and honey for kids");
  });
  it("a hand edit rebases and is never overwritten", () => {
    const d = new DictationText("Bees"); let field = "Bees";
    const first = d.hear("and honey", field); if ("write" in first) field = first.write;
    field = "Bees and honey, no wasps";
    expect(d.hear("and honey and more", field)).toEqual({ rebased: true });
    expect(d.base).toBe("Bees and honey, no wasps");
    expect(d.hear("flowers", field)).toEqual({ write: "Bees and honey, no wasps flowers" });
  });
  it("respects the maximum length without mistaking the cut for a hand edit", () => {
    const d = new DictationText("", 10); let field = "";
    const a = d.hear("0123456789 and more", field); if ("write" in a) field = a.write;
    expect(field).toBe("0123456789");
    expect(d.hear("0123456789 and more and more", field)).toEqual({ write: "0123456789" });
  });
});

describe("restart policy", () => {
  it("goes on through pauses and stops on the limits", () => {
    const p = new DictationRestartPolicy(300_000, 90_000); p.sessionStarted(0); p.recognizerStarted(0); p.textArrived(10_000);
    expect(p.ended(true, 12_000)).toBe("restart");
    p.recognizerStarted(12_300); expect(p.ended(false, 20_000)).toBe("restart");
    p.recognizerStarted(20_300); expect(p.ended(false, 101_000)).toBe("idle");
    const q = new DictationRestartPolicy(); q.sessionStarted(0); expect(q.ended(true, 300_001)).toBe("limit");
  });
  it("does not loop on a recognizer that fails at once", () => {
    const p = new DictationRestartPolicy(); p.sessionStarted(0);
    const out = [0, 1, 2, 3].map((i) => { p.recognizerStarted(i * 1000); return p.ended(false, i * 1000 + 100); });
    expect(out).toEqual(["restart", "restart", "restart", "failing"]);
  });
});

describe("startDictation", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  function run(initial = "") {
    const b = fakeBrowser(); let field = initial; const ends: string[] = [];
    const d = startDictation({ lang: "es-MX", getText: () => field, setText: (t) => { field = t; }, onEnd: (r) => ends.push(r), maxLength: 1500, win: b.win })!;
    return { ...b, d, ends, get field() { return field; }, set field(v: string) { field = v; } };
  }

  it("listens in the language it is given", () => {
    const t = run(); expect(t.made[0].lang).toBe("es-MX"); expect(t.made[0].continuous).toBe(true); expect(t.made[0].interimResults).toBe(true);
  });
  it("keeps listening when the browser ends a session on a pause, and appends every phrase", () => {
    const t = run("Un video");
    t.say(t.made[0], "sobre"); t.say(t.made[0], "sobre abejas");
    expect(t.field).toBe("Un video sobre abejas");
    t.made[0].onerror({ error: "no-speech" }); t.made[0].onend();       // the browser stopped after silence
    expect(t.ends).toEqual([]);
    vi.advanceTimersByTime(300);
    expect(t.made.length).toBe(2); expect(t.made[1].lang).toBe("es-MX");
    t.say(t.made[1], "y miel");
    expect(t.field).toBe("Un video sobre abejas y miel");               // appended, not replaced
    t.d.stop();
    expect(t.ends).toEqual(["done"]);
  });
  it("never overwrites text edited meanwhile: rebases and starts a fresh session", () => {
    const t = run("A");
    t.say(t.made[0], "b");
    t.field = "A b, typed";
    t.say(t.made[0], "b c");
    expect(t.field).toBe("A b, typed");
    expect(t.made[0].aborted).toBe(true); expect(t.made.length).toBe(2);
    t.say(t.made[1], "d");
    expect(t.field).toBe("A b, typed d");
  });
  it("reports why it stopped: denied, language not supported", () => {
    const a = run(); a.made[0].onerror({ error: "not-allowed" }); a.made[0].onend();
    expect(a.ends).toEqual(["denied"]);
    const b = run(); b.made[0].onerror({ error: "language-not-supported" }); b.made[0].onend();
    expect(b.ends).toEqual(["language"]);
  });
  it("stops by itself after 90 seconds of silence", () => {
    const t = run("x");
    for (let i = 0; i < 12; i++) { const r = t.made[t.made.length - 1]; vi.advanceTimersByTime(9000); r.onerror({ error: "no-speech" }); r.onend(); vi.advanceTimersByTime(300); }
    expect(t.ends).toEqual(["done"]);
  });
});

describe("speechLang", () => {
  it("follows the app language, the browser only picks the variant", () => {
    expect(speechLang("es", ["en-US"])).toBe("es-ES");
    expect(speechLang("en", ["es-MX"])).toBe("en-US");
    expect(speechLang("es", ["en-US", "es-MX"])).toBe("es-MX");
    expect(speechLang("en", ["en-GB"])).toBe("en-GB");
  });
});
