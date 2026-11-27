// Capture time and GPS from a JPEG's Exif block, read from the ORIGINAL bytes before the picture is re-encoded (the uploaded JPEG never carries metadata).
// Pure: takes bytes, returns what was found. Used only when the person's switches "photo dates" / "photo locations" are on (lib/mediaPrefs.ts); GPS is rounded to
// 2 decimals (about 1 km) HERE, so a precise position never leaves the browser. docs/MEDIA_LIBRARY.md, docs/PHOTOS.md.
export interface PhotoMeta { taken?: string; lat?: number; lon?: number }

const MAX_SCAN = 256 * 1024;   // Exif lives in the first segments; never scan a whole file

/** "2024:07:14 18:03:09" -> "2024-07-14T18:03:09" (wall-clock time at the place, no zone), or undefined when it is not a plausible date. */
export function parseExifDate(raw: string | undefined | null): string | undefined {
  const m = /^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec((raw ?? "").trim());
  if (!m) return undefined;
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number);
  if (y < 1990 || y > 2100 || mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return undefined;
  const p = (n: number) => String(n).padStart(2, "0");
  return `${y}-${p(mo)}-${p(d)}T${p(h)}:${p(mi)}:${p(s)}`;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

export function readExif(bytes: ArrayBuffer | Uint8Array, opts: { dates: boolean; locations: boolean }): PhotoMeta {
  if (!opts.dates && !opts.locations) return {};
  const u8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  const end = Math.min(u8.length, MAX_SCAN);
  if (end < 12 || u8[0] !== 0xff || u8[1] !== 0xd8) return {};
  const dv = new DataView(u8.buffer, u8.byteOffset, end);
  // find the APP1 "Exif\0\0" segment
  let p = 2, tiff = -1;
  while (p + 4 <= end) {
    if (u8[p] !== 0xff) break;
    const marker = u8[p + 1];
    if (marker === 0xda || marker === 0xd9) break;   // image data starts: no Exif after it
    const len = dv.getUint16(p + 2);
    if (len < 2) break;
    if (marker === 0xe1 && p + 10 <= end && u8[p + 4] === 0x45 && u8[p + 5] === 0x78 && u8[p + 6] === 0x69 && u8[p + 7] === 0x66 && u8[p + 8] === 0 && u8[p + 9] === 0) { tiff = p + 10; break; }
    p += 2 + len;
  }
  if (tiff < 0 || tiff + 8 > end) return {};
  const little = u8[tiff] === 0x49 && u8[tiff + 1] === 0x49;
  if (!little && !(u8[tiff] === 0x4d && u8[tiff + 1] === 0x4d)) return {};
  const u16 = (o: number) => (o + 2 <= end ? dv.getUint16(o, little) : 0);
  const u32 = (o: number) => (o + 4 <= end ? dv.getUint32(o, little) : 0);
  if (u16(tiff + 2) !== 42) return {};

  const TYPE_SIZE: Record<number, number> = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8 };
  /** Entries of the IFD at `off` (relative to the TIFF header): tag -> {type, count, valueOffset(absolute)}. */
  const ifd = (off: number) => {
    const out = new Map<number, { type: number; count: number; at: number }>();
    const base = tiff + off;
    if (base + 2 > end) return out;
    const n = Math.min(u16(base), 200);
    for (let i = 0; i < n; i++) {
      const e = base + 2 + i * 12;
      if (e + 12 > end) break;
      const type = u16(e + 2), count = u32(e + 4);
      const size = (TYPE_SIZE[type] ?? 0) * count;
      const at = size <= 4 ? e + 8 : tiff + u32(e + 8);
      if (size > 0 && at + size <= end) out.set(u16(e), { type, count, at });
    }
    return out;
  };
  const ascii = (e?: { count: number; at: number }) => (e ? String.fromCharCode(...u8.subarray(e.at, e.at + Math.max(0, e.count - 1))) : undefined);
  const rationals = (e: { count: number; at: number } | undefined, n: number) => {
    if (!e || e.count < n) return null;
    const v: number[] = [];
    for (let i = 0; i < n; i++) { const num = u32(e.at + i * 8), den = u32(e.at + i * 8 + 4); if (!den) return null; v.push(num / den); }
    return v;
  };

  const ifd0 = ifd(u32(tiff + 4));
  const out: PhotoMeta = {};
  if (opts.dates) {
    const exifPtr = ifd0.get(0x8769);
    const sub = exifPtr ? ifd(u32(exifPtr.at)) : new Map();
    const raw = ascii(sub.get(0x9003)) ?? ascii(sub.get(0x9004)) ?? ascii(ifd0.get(0x0132));   // DateTimeOriginal, then Digitized, then the file's DateTime
    const taken = parseExifDate(raw);
    if (taken) out.taken = taken;
  }
  if (opts.locations) {
    const gpsPtr = ifd0.get(0x8825);
    if (gpsPtr) {
      const g = ifd(u32(gpsPtr.at));
      const lat = rationals(g.get(2), 3), lon = rationals(g.get(4), 3);
      const latRef = ascii(g.get(1)), lonRef = ascii(g.get(3));
      if (lat && lon && latRef && lonRef) {
        let la = lat[0] + lat[1] / 60 + lat[2] / 3600, lo = lon[0] + lon[1] / 60 + lon[2] / 3600;
        if (latRef.toUpperCase().startsWith("S")) la = -la;
        if (lonRef.toUpperCase().startsWith("W")) lo = -lo;
        if (Math.abs(la) <= 90 && Math.abs(lo) <= 180 && !(la === 0 && lo === 0)) { out.lat = round2(la); out.lon = round2(lo); }
      }
    }
  }
  return out;
}
