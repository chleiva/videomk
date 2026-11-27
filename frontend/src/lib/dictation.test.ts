import { describe, expect, it } from "vitest";
import { appendDictation, dictationSupported, speechLang, startDictation } from "./dictation";

describe("dictation", () => {
  it("is only offered where the browser has speech recognition (prefixed or not)", () => {
    expect(dictationSupported({})).toBe(false);
    expect(dictationSupported({ webkitSpeechRecognition: function () {} })).toBe(true);
    expect(dictationSupported({ SpeechRecognition: function () {} })).toBe(true);
    expect(startDictation("en-US", () => {}, () => {}, {})).toBeNull();
  });
  it("appends what was heard with one space and never adds an empty string", () => {
    expect(appendDictation("", " a video about bees ")).toBe("a video about bees");
    expect(appendDictation("How a forest breathes  ", "for teenagers")).toBe("How a forest breathes for teenagers");
    expect(appendDictation("keep", "  ")).toBe("keep");
  });
  it("maps the app language to a speech language", () => { expect(speechLang("es")).toBe("es-ES"); expect(speechLang("en")).toBe("en-US"); });
  it("reports the transcript and why it stopped (denied permission is its own reason)", () => {
    let inst: any;
    function Fake(this: any) { inst = this; this.start = () => {}; this.stop = () => this.onend(); }
    const texts: string[] = [], ends: string[] = [];
    const d = startDictation("en-US", (t) => texts.push(t), (r) => ends.push(r), { SpeechRecognition: Fake });
    inst.onresult({ results: [Object.assign([{ transcript: "hello " }], { isFinal: false }), Object.assign([{ transcript: "world" }], { isFinal: true })] });
    expect(texts).toEqual(["hello world"]);
    inst.onerror({ error: "not-allowed" }); d!.stop();
    expect(ends).toEqual(["denied"]);
  });
});
