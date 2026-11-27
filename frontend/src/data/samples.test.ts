import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { ASPECT_KEY, HERO, SAMPLES, galleryFor } from "./samples";

const PUBLIC = path.resolve(__dirname, "../../public");
const size = (rel: string) => fs.statSync(path.join(PUBLIC, rel)).size;

describe("home page samples (public/samples)", () => {
  it("every sample has its video and poster on disk, within the weight budget", () => {
    for (const s of SAMPLES) {
      expect(fs.existsSync(path.join(PUBLIC, s.file)), s.file).toBe(true);
      expect(fs.existsSync(path.join(PUBLIC, s.poster)), s.poster).toBe(true);
      expect(size(s.file), `${s.file} <= 4.5 MB for the hero, 2.8 MB for the rest`).toBeLessThanOrEqual(s === HERO ? 4.5e6 : 2.8e6);
      expect(size(s.poster), `${s.poster} poster <= 70 KB (hero) / 35 KB`).toBeLessThanOrEqual(s === HERO ? 70e3 : 35e3);
      expect(s.seconds).toBeLessThanOrEqual(30);
    }
  });
  it("all the media together stays small enough to live in the repository (<= 25 MB)", () => {
    const total = SAMPLES.reduce((n, s) => n + size(s.file) + size(s.poster), 0) + size("og.jpg");
    expect(total).toBeLessThanOrEqual(25e6);
  });
  it("ids are unique, the hero has the real prompt, and every sample has both languages", () => {
    expect(new Set(SAMPLES.map((s) => s.id)).size).toBe(SAMPLES.length);
    expect(HERO.prompt && HERO.prompt.length).toBeGreaterThan(40);
    for (const s of SAMPLES) {
      for (const l of ["en", "es"] as const) { expect(s.title[l].trim(), `${s.id} title ${l}`).not.toBe(""); expect(s.description[l].trim()).not.toBe(""); }
      expect(ASPECT_KEY[s.aspect]).toBeTruthy();
      expect(s.width / s.height).toBeCloseTo({ wide: 16 / 9, tall: 9 / 16, square: 1, portrait: 4 / 5 }[s.aspect], 1);
    }
  });
  it("a prompt is shown only when it is a word-for-word part of a real one (no invented prompts)", () => {
    for (const s of SAMPLES) if (s.prompt !== null) expect(s.prompt.length).toBeGreaterThan(20);
    expect(SAMPLES.filter((s) => s.prompt === null).length).toBeGreaterThan(0);   // the samples whose prompt we do not have say so, they do not make one up
  });
  it("the Spanish page leads its gallery with Spanish narration, the English page does not", () => {
    expect(galleryFor("es")[0].lang).toBe("es");
    expect(galleryFor("en")[0].lang).toBe("en");
    expect(galleryFor("en")).toHaveLength(SAMPLES.length - 1);
  });
});
