import { describe, expect, it } from "vitest";
import { actionForKey, aspectLabel, clampTime, formatClock, metaLine, nextSpeed, qualityLabel, safeFileName, speedLabel } from "./player";

describe("formatClock", () => {
  it("writes m:ss and h:mm:ss", () => {
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(13.9)).toBe("0:13");
    expect(formatClock(91)).toBe("1:31");
    expect(formatClock(3600)).toBe("1:00:00");
    expect(formatClock(3725)).toBe("1:02:05");
  });
  it("never shows NaN or a negative time", () => {
    expect(formatClock(NaN)).toBe("0:00");
    expect(formatClock(-5)).toBe("0:00");
    expect(formatClock(undefined)).toBe("0:00");
    expect(formatClock(Infinity)).toBe("0:00");
  });
});

describe("speed", () => {
  it("cycles and recovers from an unknown value", () => {
    expect(nextSpeed(1)).toBe(1.25);
    expect(nextSpeed(2)).toBe(0.75);
    expect(nextSpeed(0.75)).toBe(1);
    expect(nextSpeed(3)).toBe(1);
  });
  it("labels", () => { expect(speedLabel(1)).toBe("1x"); expect(speedLabel(1.25)).toBe("1.25x"); expect(speedLabel(0.75)).toBe("0.75x"); });
});

describe("clampTime", () => {
  it("stays inside the video", () => {
    expect(clampTime(-3, 90)).toBe(0);
    expect(clampTime(120, 90)).toBe(90);
    expect(clampTime(45, 90)).toBe(45);
    expect(clampTime(NaN, 90)).toBe(0);
    expect(clampTime(10, NaN)).toBe(10);
  });
});

describe("actionForKey", () => {
  it("maps the familiar shortcuts", () => {
    expect(actionForKey({ key: " " })).toEqual({ type: "toggle" });
    expect(actionForKey({ key: "k" })).toEqual({ type: "toggle" });
    expect(actionForKey({ key: "ArrowLeft" })).toEqual({ type: "seek", by: -5 });
    expect(actionForKey({ key: "l" })).toEqual({ type: "seek", by: 10 });
    expect(actionForKey({ key: "ArrowUp" })).toEqual({ type: "volume", by: 0.1 });
    expect(actionForKey({ key: "m" })).toEqual({ type: "mute" });
    expect(actionForKey({ key: "f" })).toEqual({ type: "fullscreen" });
    expect(actionForKey({ key: "p" })).toEqual({ type: "pip" });
    expect(actionForKey({ key: "c" })).toEqual({ type: "captions" });
    expect(actionForKey({ key: ">" })).toEqual({ type: "speed", direction: 1 });
    expect(actionForKey({ key: "5" })).toEqual({ type: "seekTo", fraction: 0.5 });
  });
  it("leaves browser shortcuts, typing and focused buttons alone", () => {
    expect(actionForKey({ key: "f", metaKey: true })).toBeNull();
    expect(actionForKey({ key: "k", ctrlKey: true })).toBeNull();
    expect(actionForKey({ key: " ", targetTag: "TEXTAREA" })).toBeNull();
    expect(actionForKey({ key: "ArrowLeft", targetTag: "INPUT" })).toBeNull();
    expect(actionForKey({ key: "k", targetEditable: true })).toBeNull();
    expect(actionForKey({ key: " ", targetTag: "BUTTON" })).toBeNull();
    expect(actionForKey({ key: "Enter", targetTag: "A" })).toBeNull();
    expect(actionForKey({ key: "k", targetTag: "BUTTON" })).toEqual({ type: "toggle" });
    expect(actionForKey({ key: "x" })).toBeNull();
  });
});

describe("safeFileName", () => {
  it("is safe and short", () => {
    expect(safeFileName("How a forest breathes")).toBe("How a forest breathes.mp4");
    expect(safeFileName('a/b\\c:d*e?"f<g>h|i')).toBe("a b c d e f g h i.mp4");
    expect(safeFileName("   ")).toBe("video.mp4");
    expect(safeFileName(null)).toBe("video.mp4");
    expect(safeFileName("x".repeat(200)).length).toBe(84);
  });
});

describe("shape and quality", () => {
  it("finds the nearest aspect", () => {
    expect(aspectLabel(1920, 1080)).toBe("16:9");
    expect(aspectLabel(1080, 1920)).toBe("9:16");
    expect(aspectLabel(1080, 1080)).toBe("1:1");
    expect(aspectLabel(1080, 1350)).toBe("4:5");
    expect(aspectLabel(0, 10)).toBeNull();
  });
  it("labels the quality from the short side, like the apps", () => {
    expect(qualityLabel(1920, 1080)).toBe("1080p");
    expect(qualityLabel(1080, 1920)).toBe("1080p");
    expect(qualityLabel(3840, 2160)).toBe("2160p");
    expect(qualityLabel(1280, 720)).toBe("720p");
    expect(qualityLabel(0, 0)).toBeNull();
  });
  it("writes the one caption line", () => {
    expect(metaLine(80, 1920, 1080)).toBe("1:20 · 1080p");
    expect(metaLine(null, 1920, 1080)).toBe("1080p");
    expect(metaLine(80, 0, 0)).toBe("1:20");
    expect(metaLine(null, 0, 0)).toBe("");
  });
});
