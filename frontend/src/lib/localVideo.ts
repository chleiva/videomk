// Browser-side work on the picked video, before anything is uploaded: read its length and shape, draw a poster frame from a <video> canvas, and (only for a file over the size limit)
// cut its first seconds with MediaRecorder on captureStream. Everything that can fail fails soft: no poster, no length, or no trim never blocks the upload by itself (the server decodes and
// decides); a trim that cannot be done says so with one clear sentence. Pure helpers are tested in videoClips.test.ts / localVideo.test.ts; the rest is checked in a real browser.

export interface Probe { duration: number | null; width: number | null; height: number | null; hasAudio: boolean | null; poster: string | null; posterBlob: Blob | null; aspect: number | null }
export const POSTER_MAX = 480;

/** Where to take the poster: early enough to be the opening of the clip, late enough not to be a black first frame. */
export function posterTime(duration: number | null): number { return duration && duration > 0 ? Math.min(1, Math.max(0.1, duration * 0.1)) : 0.1; }
/** Fits width x height inside `max` on the long side, never enlarging. */
export function fitSize(w: number, h: number, max = POSTER_MAX): { w: number; h: number } {
  if (!(w > 0) || !(h > 0)) return { w: max, h: Math.round(max * 9 / 16) };
  const s = Math.min(1, max / Math.max(w, h));
  return { w: Math.max(1, Math.round(w * s)), h: Math.max(1, Math.round(h * s)) };
}
/** The recorder format to cut with: WebM where it exists (Chrome, Firefox, Edge), MP4 where that is all there is (Safari). The content type sent is the plain one, without codecs. */
export function pickRecorderType(isSupported: (t: string) => boolean): { mime: string; contentType: "video/webm" | "video/mp4" } | null {
  const webm = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
  const mp4 = ["video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4;codecs=avc1", "video/mp4"];
  for (const m of webm) if (isSupported(m)) return { mime: m, contentType: "video/webm" };
  for (const m of mp4) if (isSupported(m)) return { mime: m, contentType: "video/mp4" };
  return null;
}
export function canTrimInBrowser(): boolean {
  try {
    return typeof MediaRecorder !== "undefined" && typeof HTMLVideoElement !== "undefined" && "captureStream" in HTMLVideoElement.prototype && !!pickRecorderType((t) => MediaRecorder.isTypeSupported(t));
  } catch { return false; }
}

function videoEl(url: string): HTMLVideoElement {
  const v = document.createElement("video");
  v.muted = true; v.playsInline = true; v.preload = "auto"; v.setAttribute("playsinline", ""); v.crossOrigin = "anonymous";
  v.src = url;
  return v;
}
const once = (el: EventTarget, ok: string[], bad: string[], ms: number) => new Promise<boolean>((resolve) => {
  const done = (r: boolean) => { clearTimeout(timer); [...ok, ...bad].forEach((n) => el.removeEventListener(n, h)); resolve(r); };
  const h = (e: Event) => done(ok.includes(e.type));
  const timer = setTimeout(() => done(false), ms);
  [...ok, ...bad].forEach((n) => el.addEventListener(n, h));
});

/** Length, shape, a poster frame and (where the browser can say) whether there is sound. Gives up after a few seconds and returns what it has. */
export async function probeVideo(file: Blob): Promise<Probe> {
  const out: Probe = { duration: null, width: null, height: null, hasAudio: null, poster: null, posterBlob: null, aspect: null };
  const url = URL.createObjectURL(file);
  const v = videoEl(url);
  try {
    if (!(await once(v, ["loadedmetadata"], ["error"], 6000))) return out;
    if (Number.isFinite(v.duration) && v.duration > 0) out.duration = v.duration;
    if (v.videoWidth > 0 && v.videoHeight > 0) { out.width = v.videoWidth; out.height = v.videoHeight; out.aspect = v.videoWidth / v.videoHeight; }
    const anyV = v as any;
    if (typeof anyV.mozHasAudio === "boolean") out.hasAudio = anyV.mozHasAudio;
    else if (anyV.audioTracks && typeof anyV.audioTracks.length === "number") out.hasAudio = anyV.audioTracks.length > 0;
    try { v.currentTime = posterTime(out.duration); } catch { return out; }
    if (!(await once(v, ["seeked"], ["error"], 5000)) || !out.width || !out.height) return out;
    const { w, h } = fitSize(out.width, out.height);
    const cv = document.createElement("canvas"); cv.width = w; cv.height = h;
    cv.getContext("2d")?.drawImage(v, 0, 0, w, h);
    const blob: Blob | null = await new Promise((r) => cv.toBlob((b) => r(b), "image/jpeg", 0.82));
    if (blob && blob.size > 0) { out.posterBlob = blob; out.poster = URL.createObjectURL(blob); }
    return out;
  } catch { return out; } finally { v.removeAttribute("src"); v.load(); URL.revokeObjectURL(url); }
}

export type TrimResult = { ok: true; blob: Blob; contentType: "video/webm" | "video/mp4" } | { ok: false; reason: "unsupported" | "failed" | "cancelled" | "still_big" };

/** Plays the first `seconds` of the file and records them (the picture, and the sound only when asked): the original is never touched. Takes about `seconds` of real time. */
export async function trimClip(file: Blob, o: { seconds: number; withAudio: boolean; maxBytes: number; onProgress?: (pct: number) => void; signal?: AbortSignal }): Promise<TrimResult> {
  if (!canTrimInBrowser()) return { ok: false, reason: "unsupported" };
  const type = pickRecorderType((t) => MediaRecorder.isTypeSupported(t))!;
  const url = URL.createObjectURL(file);
  const v = videoEl(url);
  let rec: MediaRecorder | null = null;
  try {
    if (!(await once(v, ["loadedmetadata"], ["error"], 8000))) return { ok: false, reason: "failed" };
    const src: MediaStream = (v as any).captureStream();
    const stream = o.withAudio ? src : new MediaStream(src.getVideoTracks());
    rec = new MediaRecorder(stream, { mimeType: type.mime, videoBitsPerSecond: 2_500_000, audioBitsPerSecond: 96_000 });
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    const stopped = new Promise<void>((r) => { rec!.onstop = () => r(); });
    v.currentTime = 0;
    await v.play();
    rec.start(250);
    const limit = Math.min(o.seconds, Number.isFinite(v.duration) ? v.duration : o.seconds);
    const cancelled = await new Promise<boolean>((resolve) => {
      const finish = (c: boolean) => { clearTimeout(guard); v.removeEventListener("timeupdate", tick); v.removeEventListener("ended", end); o.signal?.removeEventListener("abort", abort); resolve(c); };
      const tick = () => { o.onProgress?.(Math.min(99, Math.round((v.currentTime / limit) * 100))); if (v.currentTime >= limit) finish(false); };
      const end = () => finish(false), abort = () => finish(true);
      const guard = setTimeout(() => finish(false), (limit + 4) * 1000);
      v.addEventListener("timeupdate", tick); v.addEventListener("ended", end); o.signal?.addEventListener("abort", abort);
      if (o.signal?.aborted) finish(true);
    });
    v.pause();
    if (rec.state !== "inactive") rec.stop();
    await stopped;
    if (cancelled) return { ok: false, reason: "cancelled" };
    const blob = new Blob(chunks, { type: type.contentType });
    if (blob.size < 1000) return { ok: false, reason: "failed" };
    if (blob.size > o.maxBytes) return { ok: false, reason: "still_big" };
    o.onProgress?.(100);
    return { ok: true, blob, contentType: type.contentType };
  } catch { return { ok: false, reason: o.signal?.aborted ? "cancelled" : "failed" }; }
  finally { try { if (rec && rec.state !== "inactive") rec.stop(); } catch { /* already stopped */ } v.pause(); v.removeAttribute("src"); v.load(); URL.revokeObjectURL(url); }
}
