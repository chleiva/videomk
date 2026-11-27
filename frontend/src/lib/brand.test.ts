// The brand is written "VideoMK" wherever a person reads it (docs/BRAND.md). Lowercase "videomk" is only for identifiers:
// the domain and emails (videomk.com, hello@videomk.com), bundle ids (com.videomk.app), storage keys, bucket names, file names,
// i18n keys (create.wm_videomk) and the watermark mode id, which is the whole quoted token "videomk".
import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = join(__dirname, "..", "..");
const TEXT = /\.(astro|tsx?|jsx?|mjs|json|css|html|md|webmanifest|txt|xml)$/;
// "videomk" in any casing that is not exactly VideoMK, standing as a word: not glued to @ . / : - _ or letters on either side
const WRONG = /(?<![\w@./:\-])videomk(?![\w]|[.\-_/:]\w)/i;
const MODE_ID = /(["'`])videomk\1/g;                                   // the watermark mode id and other exact identifier tokens
const VISIBLE = /(aria-label=|content=|alt=|\bname:\s*|\btitle\s*=\s*|"name":\s*|"short_name":\s*|\blabel:\s*|"label":\s*)["']videomk["']/;

export function brandMistakes(text: string): number[] {
  const bad: number[] = [];
  text.split("\n").forEach((line, i) => {
    if (VISIBLE.test(line)) return void bad.push(i + 1);
    const rest = line.replace(/VideoMK/g, "").replace(MODE_ID, "");
    if (WRONG.test(rest)) bad.push(i + 1);
  });
  return bad;
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name.startsWith("dist") || name.startsWith(".")) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out); else if (TEXT.test(name)) out.push(p);
  }
  return out;
}

describe("brand spelling: VideoMK", () => {
  it("knows a wrong spelling from an identifier", () => {
    expect(brandMistakes("Made with videomk")).toEqual([1]);
    expect(brandMistakes("Welcome to Videomk.")).toEqual([1]);
    expect(brandMistakes('<a aria-label="videomk">')).toEqual([1]);
    expect(brandMistakes("Made with VideoMK at videomk.com, hello@videomk.com, com.videomk.app, videomk-uploads, videomk_key")).toEqual([]);
    expect(brandMistakes('mode === "videomk" ? t("create.wm_videomk") : 0')).toEqual([]);
  });

  it("no page, string or legal text writes the name another way", () => {
    const found: string[] = [];
    for (const dir of ["src", "public", "site-pages", "scripts"]) {
      for (const f of walk(join(ROOT, dir))) {
        if (f.endsWith("brand.test.ts")) continue;
        for (const n of brandMistakes(readFileSync(f, "utf8"))) found.push(`${relative(ROOT, f)}:${n}`);
      }
    }
    expect(found).toEqual([]);
  });
});
