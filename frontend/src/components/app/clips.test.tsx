// The clip tile, the notes under the strip and the "Add a video" dialog, drawn for each state (static markup; the browser run is in docs/VIDEO_UPLOAD_WEB_2026-11-28.md).
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup as html } from "react-dom/server";
import ClipSheet from "./ClipSheet";
import { ClipNotes, ClipTile, tileState } from "./ClipTile";
import { parseVideoUploadCaps } from "../../lib/videoClips";
import type { ClipItem } from "../../lib/videoClips";
import { translate } from "../../lib/i18n";

const en = (k: string, p?: Record<string, string | number>) => translate(k, "en", p);
const es = (k: string, p?: Record<string, string | number>) => translate(k, "es", p);
const caps = parseVideoUploadCaps({ enabled: true, available: true, clips_per_video: 2, max_bytes: 25 * 1024 * 1024, used_seconds: 5, formats: ["video/mp4", "video/quicktime", "video/webm"], api_url: "https://v.test/prod" })!;
const base: ClipItem = { key: "c1", name: "a.mp4", state: "ready", pct: 100, useAudio: true, bytes: 1, slow: false, poster: "blob:x", aspect: 16 / 9, clip: { id: "c1", status: "ready", ready: true, useAudio: true, duration: 5, audioUsed: true, aspect: 16 / 9 } };
const tile = (o: Partial<ClipItem>, t = en) => html(<ClipTile item={{ ...base, ...o }} t={t} onRemove={() => {}} />);
const notes = (items: Partial<ClipItem>[], t = en) => html(<ClipNotes items={items.map((o) => ({ ...base, ...o }))} t={t} onRetry={() => {}} onRemove={() => {}} />);

describe("clip tile", () => {
  it("ready: poster, play badge, the 5 s chip and the sound badge, with words for a screen reader and a remove button", () => {
    const m = tile({});
    expect(m).toContain("clip-play"); expect(m).toContain(">5 s<"); expect(m).toContain("clip-snd"); expect(m).toContain('aria-label="Remove video"'); expect(m).toContain("Video, Ready, 5 s, Sound on");
    expect(m).toContain("--clip-a:1.777"); expect(m).toContain('<img src="blob:x" alt=""');
  });
  it("a portrait clip is narrower than a landscape one (its own shape), the shape is clamped", () => {
    expect(tile({ aspect: 9 / 16 })).toContain("--clip-a:0.6"); expect(tile({ aspect: 5 })).toContain("--clip-a:2");
  });
  it("uploading shows the real percentage and a bar; checking shows a spinner; neither has the play badge", () => {
    const up = tile({ state: "uploading", pct: 42, clip: undefined });
    expect(up).toContain("42%"); expect(up).toContain("clip-bar"); expect(up).not.toContain("clip-play"); expect(up).toContain("Uploading 42%");
    const ck = tile({ state: "analysing", clip: undefined });
    expect(ck).toContain("spinner"); expect(ck).toContain("Checking your video…");
  });
  it("a failed clip is marked and spoken; no sound badge when the sound was not used", () => {
    expect(tile({ state: "failed", failure: { kind: "network", retry: true }, clip: undefined })).toContain("attach-bad");
    expect(tile({ clip: { ...base.clip!, audioUsed: false } })).not.toContain("clip-snd");
    expect(tileState({ ...base, state: "rejected" }, en)).toBe("A video could not be added");
  });
  it("Spanish words", () => { expect(tile({}, es)).toContain("Quitar video"); expect(tile({ state: "analysing" }, es)).toContain("Revisando tu video…"); });
});

describe("notes under the strip", () => {
  it("nothing to say, nothing shown", () => expect(notes([{}])).toBe(""));
  it("while checking: one calm line; when slow: the longer-than-usual line and no spinner", () => {
    expect(notes([{ state: "analysing" }])).toContain("Checking your video…");
    const slow = notes([{ state: "analysing", slow: true }]);
    expect(slow).toContain("taking longer than usual"); expect(slow).not.toContain("spinner");
  });
  it("network failure: our sentence, Try again and Remove; the server's sentence is used when it sends one", () => {
    const m = notes([{ state: "failed", failure: { kind: "network", retry: true }, clip: undefined }]);
    expect(m).toContain("The upload stopped. Check your connection and try again."); expect(m).toContain("Try again"); expect(m).toContain("Remove video");
    expect(notes([{ state: "failed", failure: { kind: "plan", retry: false, message: "Video clips are part of Pro." }, clip: undefined }])).toContain("Video clips are part of Pro.");
  });
  it("rejected: generic wording, no Try again, a Help link, never a reason", () => {
    const m = notes([{ state: "rejected", failure: { kind: "rejected", retry: false }, clip: undefined }]);
    expect(m).toContain("We could not use this clip. Please choose a different one."); expect(m).not.toContain("Try again"); expect(m).toContain("/support/");
  });
  it("ready clip facts: first 5 seconds used; sound could not be used", () => {
    const m = notes([{ clip: { ...base.clip!, trimmed: true, audioUsed: false, audioState: "unscreened" } }]);
    expect(m).toContain("First 5 seconds used"); expect(m).toContain("We used your video without its sound.");
  });
});

const file = (name: string, type: string, size = 5_000_000) => new File([new Uint8Array(8)], name, { type, lastModified: 0 }) as File & { size: number };
const sheet = (f: File, t = en) => html(<ClipSheet file={f} caps={caps} t={t} onCancel={() => {}} onChooseAnother={() => {}} onAdd={() => {}} />);

describe("Add a video dialog", () => {
  it("asks the sound question with no default, explains transcription, shows the notice and the privacy line; Add is not ready yet", () => {
    const m = sheet(file("a.mp4", "video/mp4"));
    expect(m).toContain("Only the first 5 seconds of a video are used."); expect(m).toContain("Use this video&#x27;s own sound?");
    expect(m).toContain("Yes, use its sound"); expect(m).toContain("No, silent"); expect(m).not.toContain("checked");
    expect(m).toContain("We check your video for safety."); expect(m).toContain('aria-disabled="true"'); expect(m).toContain(">Add video<");
    expect(m).not.toContain("turn the words into text");   // the helper appears once Yes is chosen
  });
  it("a file that is not a video we can use is blocked with one clear line and a way out", () => {
    const m = sheet(file("a.png", "image/png"));
    expect(m).toContain("That file is not a video we can use."); expect(m).toContain("Choose another video"); expect(m).not.toContain("clip-q");
  });
  it("Spanish", () => { const m = sheet(file("a.mp4", "video/mp4"), es); expect(m).toContain("Solo se usan los primeros 5 segundos"); expect(m).toContain("Sí, usar su sonido"); expect(m).toContain("No, en silencio"); });
});
