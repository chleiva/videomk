import { describe, expect, it } from "vitest";
import { renderToStaticMarkup as html } from "react-dom/server";
import Player from "./Player";
import { PIcon } from "./PlayerIcons";
import { PATHS } from "./PlayerIcons";
import { EN, ES } from "../i18n/catalog";

describe("player markup", () => {
  const m = html(<Player src="https://example.com/v.mp4" title="Forest" newVideoHref="/new" />);
  it("is a labelled group the keyboard can reach", () => {
    expect(m).toContain('role="group"');
    expect(m).toContain('aria-label="Video player: Forest"');
    expect(m).toContain('tabindex="0"');
  });
  it("has no text button: every control is named, the speed shows its value", () => {
    const buttons = [...m.matchAll(/<button[^>]*>/g)].map((x) => x[0]);
    expect(buttons.length).toBeGreaterThanOrEqual(5);
    for (const b of buttons) expect(b, b).toContain("aria-label=");
    expect(m).toContain("Playback speed: 1x");
  });
  it("the scrubber is a named range with a spoken value", () => {
    expect(m).toMatch(/<input[^>]*type="range"[^>]*aria-label="Position"/);
    expect(m).toContain("aria-valuetext=");
  });
  it("starts with the big play button and without the end card", () => {
    expect(m).toContain("player-big");
    expect(m).not.toContain("player-end");
  });
  it("never uses the browser's own controls", () => {
    expect(m).not.toMatch(/<video[^>]*\scontrols/);
  });
});

describe("icons and strings", () => {
  it("draws every icon the pages ask for and hides it from screen readers", () => {
    for (const n of ["play", "pause", "share", "download", "sliders", "info", "more", "back", "fullscreen", "pip", "volume", "mute", "replay", "flag", "chat", "copy"]) {
      expect(PATHS[n], n).toBeTruthy();
      expect(html(<PIcon name={n} />)).toContain('aria-hidden="true"');
    }
  });
  it("has the player, watch, credits and settings text in both languages", () => {
    const keys = Object.keys(EN).filter((k) => /^(player|watch|credits|settings)\./.test(k));
    expect(keys.length).toBeGreaterThan(60);
    for (const k of keys) { expect((ES as any)[k], k).toBeTruthy(); }
  });
  it("keeps the player's labels short (they are icon names, not sentences)", () => {
    for (const k of Object.keys(EN).filter((x) => x.startsWith("player.") && !x.includes("region") && !x.includes("seek_value"))) expect(EN[k].split(/\s+/).length, k).toBeLessThanOrEqual(4);
  });
});
