import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// Reads the real tokens.css, so the test cannot drift from what ships. Contrast is WCAG 2.2 (same maths as DesignTokens.swift).
const css = readFileSync(join(__dirname, "tokens.css"), "utf8");

function block(selector: string): string {
  const i = css.indexOf(selector + " {");
  if (i < 0) throw new Error("missing block " + selector);
  return css.slice(i, css.indexOf("\n}", i));
}
function vars(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of text.matchAll(/(--[a-z0-9-]+):\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}
const light = vars(block(":root"));
const darkManual = vars(block(':root[data-theme="dark"]'));
const darkSystem = vars(block(':root:not([data-theme="light"])'));
const dark = { ...light, ...darkManual };

const lin = (v: number) => { const c = v / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
function lum(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255);
}
export function contrast(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

// every foreground / background pair the web draws, with the WCAG minimum (4.5 text, 3 for focus ring and graphics)
const PAIRS: [string, string, number][] = [
  ["--text", "--background", 4.5], ["--text", "--surface", 4.5], ["--text", "--surface-2", 4.5],
  ["--text-secondary", "--background", 4.5], ["--text-secondary", "--surface", 4.5], ["--text-secondary", "--surface-2", 4.5],
  ["--text-tertiary", "--background", 4.5], ["--text-tertiary", "--surface", 4.5], ["--text-tertiary", "--surface-2", 4.5],
  ["--primary", "--background", 4.5], ["--primary", "--surface", 4.5], ["--primary", "--primary-container", 4.5],
  ["--success", "--success-container", 4.5], ["--warning", "--warning-container", 4.5], ["--danger", "--danger-container", 4.5],
  ["--danger", "--surface", 4.5], ["--danger", "--background", 4.5],
  ["--on-primary", "--gradient-start", 4.5], ["--on-primary", "--gradient-end", 4.5],
  ["--on-making", "--making-start", 4.5], ["--on-making", "--making-end", 4.5],
  ["--on-scrim", "--making-start", 4.5],
  ["--primary", "--surface-3", 3], ["--outline", "--background", 1], // focus ring is --primary: 3:1 against the surfaces it sits on
];

describe("tokens.css", () => {
  it("has the same colour roles as the apps (DesignTokens.swift)", () => {
    expect(light["--background"]).toBe("#f6f7fc");
    expect(light["--primary"]).toBe("#4f52e0");
    expect(light["--text-tertiary"]).toBe("#5f6585"); // v2 fix
    expect(dark["--text-tertiary"]).toBe("#8a92b0");
    expect(dark["--on-primary"]).toBe("#0a0d1f");
    expect(light["--gradient-start"]).toBe("#5b5ef0");
    expect(light["--gradient-end"]).toBe("#8452f4");
    expect(light["--live"]).toBe("#22d3ee");
  });
  it("dark mode is defined once for the system and once for the manual switch, identically", () => {
    const names = Object.keys(darkManual).filter((k) => !k.startsWith("--elev") && k !== "color-scheme");
    for (const k of names) expect(darkSystem[k], k).toBe(darkManual[k]);
    expect(Object.keys(darkSystem).sort()).toEqual(Object.keys(darkManual).sort());
  });
  for (const [mode, set] of [["light", light], ["dark", dark]] as const) {
    describe(mode, () => {
      for (const [fg, bg, min] of PAIRS) {
        it(`${fg} on ${bg} is at least ${min}:1`, () => {
          const a = set[fg], b = set[bg];
          expect(a, fg).toMatch(/^#[0-9a-f]{6}$/); expect(b, bg).toMatch(/^#[0-9a-f]{6}$/);
          if (fg === "--outline") return; // informational: hairlines are decoration
          expect(contrast(a, b)).toBeGreaterThanOrEqual(min);
        });
      }
    });
  }
  it("the old blue to pink gradient on white (the failing pair the review found) would not pass: the new one does", () => {
    expect(contrast("#ffffff", "#ec4899")).toBeLessThan(4.5);
    expect(contrast(light["--on-primary"], light["--gradient-start"])).toBeGreaterThanOrEqual(4.5);
  });
  it("type scale never goes below 14 px and spacing is a 4 px grid", () => {
    for (const [k, v] of Object.entries(light)) {
      if (k.startsWith("--fs-")) expect(parseFloat(v.replace(/^clamp\(/, "")) * 16, k).toBeGreaterThanOrEqual(14);
      if (/^--space-\d+$/.test(k)) expect((parseFloat(v) * 16) % 4, k).toBe(0);
    }
  });
});

// The same rule for the source: no text under 14 px and no raw colours outside the token file.
function walk(dir: string, out: string[] = []): string[] {
  for (const f of readdirSync(dir)) { const p = join(dir, f); if (statSync(p).isDirectory()) walk(p, out); else out.push(p); }
  return out;
}
const SRC = join(__dirname, "..");
const sources = walk(SRC).filter((p) => /\.(tsx|astro|css)$/.test(p) && !p.endsWith("tokens.css") && !p.includes("/data/legal"));
describe("source rules", () => {
  it("no text smaller than 14 px (text-xs, text-[11px], 12px font sizes)", () => {
    const bad: string[] = [];
    for (const p of sources) {
      const s = readFileSync(p, "utf8");
      if (/\btext-xs\b|text-\[(\d|1[0-3])(\.\d+)?px\]|font-size:\s*(\d|1[0-3])(\.\d+)?px|font-size:\s*0?\.[0-7]\d*r?em/.test(s)) bad.push(p.replace(SRC, "src"));
    }
    expect(bad).toEqual([]);
  });
  it("no raw hex colours in components (the signin provider buttons keep the brand colours Google and Apple require)", () => {
    const bad: string[] = [];
    for (const p of sources) {
      if (p.endsWith("signin.astro") || p.endsWith("Head.astro")) continue;   // Head.astro: <meta name="theme-color"> cannot read CSS variables; the next test pins its values to the tokens
      const s = readFileSync(p, "utf8");
      if (/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b(?![0-9a-fA-F])/.test(s.replace(/href="#[\w-]+"/g, "").replace(/&#\d+;/g, ""))) bad.push(p.replace(SRC, "src"));
    }
    expect(bad).toEqual([]);
  });
  it("the browser theme-color meta values in Head.astro equal the --background tokens", () => {
    const head = readFileSync(join(SRC, "layouts", "Head.astro"), "utf8");
    expect(head).toContain(`content="${light["--background"]}" media="(prefers-color-scheme: light)"`);
    expect(head).toContain(`content="${darkManual["--background"]}" media="(prefers-color-scheme: dark)"`);
  });
});
