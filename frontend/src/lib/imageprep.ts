// Browser-side photo preparation, the same rules as the apps (docs/PHOTOS.md): upright, at most 2048 px on the long side, re-encoded as JPEG with NO metadata (a canvas
// re-encode drops Exif, GPS and colour profiles), and the sha256 of the exact bytes that will be uploaded. The capture time and position are read from the original first
// (lib/exif.ts, only when the person's switches are on). Anything the browser cannot decode (HEIC in Chrome or Firefox) returns null: the queue shows it as "can't be read here".
import { readExif } from "./exif";
import { photoDates, photoLocations } from "./mediaPrefs";
import type { Prepared } from "./upload";

export const MAX_SIDE = 2048;
const MAX_BYTES = 9 * 1024 * 1024;   // the direct-upload slot allows 10 MB

export function fitWithin(w: number, h: number, max = MAX_SIDE): { w: number; h: number } {
  const k = Math.min(1, max / Math.max(w, h));
  return { w: Math.max(1, Math.round(w * k)), h: Math.max(1, Math.round(h * k)) };
}

export async function sha256Hex(blob: Blob): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return Array.from(new Uint8Array(d), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function toJpeg(bitmap: ImageBitmap, w: number, h: number, quality: number): Promise<Blob | null> {
  if (typeof OffscreenCanvas !== "undefined") {
    const c = new OffscreenCanvas(w, h), g = c.getContext("2d");
    if (!g) return null;
    g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); g.drawImage(bitmap, 0, 0, w, h);
    return c.convertToBlob({ type: "image/jpeg", quality });
  }
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  const g = c.getContext("2d");
  if (!g) return null;
  g.fillStyle = "#fff"; g.fillRect(0, 0, w, h); g.drawImage(bitmap, 0, 0, w, h);
  return new Promise((res) => c.toBlob((b) => res(b), "image/jpeg", quality));
}

export async function prepareImage(file: File): Promise<Prepared | null> {
  try {
    const head = await file.slice(0, 256 * 1024).arrayBuffer();
    const meta = readExif(head, { dates: photoDates(), locations: photoLocations() });
    let bitmap: ImageBitmap;
    try { bitmap = await createImageBitmap(file, { imageOrientation: "from-image" }); } catch { return null; }   // not a picture this browser can decode
    try {
      const { w, h } = fitWithin(bitmap.width, bitmap.height);
      if (bitmap.width < 16 || bitmap.height < 16) return null;
      let blob: Blob | null = null;
      for (const q of [0.9, 0.8, 0.7, 0.55]) { blob = await toJpeg(bitmap, w, h, q); if (blob && blob.size <= MAX_BYTES) break; }
      if (!blob || blob.size > MAX_BYTES) return null;
      return { blob, sha256: await sha256Hex(blob), meta };
    } finally { bitmap.close?.(); }
  } catch { return null; }
}
