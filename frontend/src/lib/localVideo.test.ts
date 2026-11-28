import { describe, expect, it } from "vitest";
import { fitSize, pickRecorderType, posterTime } from "./localVideo";

describe("local video helpers", () => {
  it("the poster comes from early in the clip, never the black first frame, never late", () => {
    expect(posterTime(null)).toBe(0.1); expect(posterTime(0.5)).toBe(0.1); expect(posterTime(5)).toBe(0.5); expect(posterTime(120)).toBe(1);
  });
  it("the poster is fitted inside 480 px on the long side, keeps its shape, never enlarges", () => {
    expect(fitSize(1920, 1080)).toEqual({ w: 480, h: 270 }); expect(fitSize(1080, 1920)).toEqual({ w: 270, h: 480 }); expect(fitSize(200, 100)).toEqual({ w: 200, h: 100 }); expect(fitSize(0, 0).w).toBe(480);
  });
  it("trimming records WebM where possible, MP4 where that is all there is, and nothing where neither works", () => {
    expect(pickRecorderType((t) => t.startsWith("video/webm"))).toMatchObject({ contentType: "video/webm" });
    expect(pickRecorderType((t) => t.startsWith("video/mp4"))).toMatchObject({ contentType: "video/mp4" });
    expect(pickRecorderType(() => false)).toBeNull();
    expect(pickRecorderType((t) => t === "video/webm;codecs=vp8")!.mime).toBe("video/webm;codecs=vp8");
  });
});
