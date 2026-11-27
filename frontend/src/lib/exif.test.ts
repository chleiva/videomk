import { describe, expect, it } from "vitest";
import { parseExifDate, readExif } from "./exif";

/** Builds a minimal little-endian JPEG with an Exif block: DateTimeOriginal and GPS (Phuket-ish, 7 deg 52' 30" N, 98 deg 23' 15" E by default). */
function jpegWithExif(opts: { date?: string; gps?: { latRef: string; lat: [number, number, number]; lonRef: string; lon: [number, number, number] }; big?: boolean } = {}): Uint8Array {
  const le = !opts.big;
  const buf: number[] = [];
  const w16 = (v: number) => (le ? buf.push(v & 255, v >> 8) : buf.push(v >> 8, v & 255));
  const w32 = (v: number) => (le ? buf.push(v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >>> 24) & 255) : buf.push((v >>> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255));
  const date = opts.date ?? "2024:07:14 18:03:09";
  // layout (offsets relative to the TIFF header): header 0..7, IFD0 at 8 (2 entries), ExifIFD, GPS IFD, then data
  const ifd0 = 8, ifd0Size = 2 + 2 * 12 + 4;
  const exifAt = ifd0 + ifd0Size, exifSize = 2 + 1 * 12 + 4;
  const gpsAt = exifAt + exifSize, gpsSize = 2 + 4 * 12 + 4;
  const dateAt = gpsAt + gpsSize, latAt = dateAt + 20, lonAt = latAt + 24;
  buf.push(...(le ? [0x49, 0x49] : [0x4d, 0x4d])); w16(42); w32(8);
  w16(2);
  w16(0x8769); w16(4); w32(1); w32(exifAt);
  w16(0x8825); w16(4); w32(1); w32(gpsAt);
  w32(0);
  w16(1); w16(0x9003); w16(2); w32(20); w32(dateAt); w32(0);
  const g = opts.gps;
  w16(4);
  w16(1); w16(2); w32(2); buf.push((g?.latRef ?? "N").charCodeAt(0), 0, 0, 0);
  w16(2); w16(5); w32(3); w32(latAt);
  w16(3); w16(2); w32(2); buf.push((g?.lonRef ?? "E").charCodeAt(0), 0, 0, 0);
  w16(4); w16(5); w32(3); w32(lonAt);
  w32(0);
  for (const ch of date) buf.push(ch.charCodeAt(0)); buf.push(0);
  const lat = g?.lat ?? [7, 52, 30], lon = g?.lon ?? [98, 23, 15];
  for (const v of lat) { w32(v); w32(1); }
  for (const v of lon) { w32(v); w32(1); }
  const tiff = buf.length;
  const app1Len = 2 + 6 + tiff;
  return Uint8Array.from([0xff, 0xd8, 0xff, 0xe1, app1Len >> 8, app1Len & 255, 0x45, 0x78, 0x69, 0x66, 0, 0, ...buf, 0xff, 0xda, 0, 2]);
}

describe("parseExifDate", () => {
  it("turns the Exif wall-clock text into an ISO local time", () => expect(parseExifDate("2024:07:14 18:03:09")).toBe("2024-07-14T18:03:09"));
  it("refuses nonsense and the all-zero date cameras write when the clock was never set", () => {
    expect(parseExifDate("0000:00:00 00:00:00")).toBeUndefined();
    expect(parseExifDate("2024:13:40 25:61:61")).toBeUndefined();
    expect(parseExifDate("yesterday")).toBeUndefined();
    expect(parseExifDate(undefined)).toBeUndefined();
  });
});

describe("readExif", () => {
  it("reads the capture time and the position, rounded to 2 decimals (about 1 km)", () => {
    const m = readExif(jpegWithExif(), { dates: true, locations: true });
    expect(m.taken).toBe("2024-07-14T18:03:09");
    expect(m.lat).toBeCloseTo(7.88, 2);   // 7 + 52/60 + 30/3600 = 7.875 -> 7.88
    expect(m.lon).toBeCloseTo(98.39, 2);  // 98 + 23/60 + 15/3600 = 98.3875 -> 98.39
  });
  it("reads big-endian files too", () => {
    const m = readExif(jpegWithExif({ big: true }), { dates: true, locations: true });
    expect(m.taken).toBe("2024-07-14T18:03:09");
    expect(m.lat).toBeCloseTo(7.88, 2);
  });
  it("southern and western hemispheres are negative", () => {
    const m = readExif(jpegWithExif({ gps: { latRef: "S", lat: [33, 51, 0], lonRef: "W", lon: [70, 40, 0] } }), { dates: false, locations: true });
    expect(m.lat).toBeCloseTo(-33.85, 2);
    expect(m.lon).toBeCloseTo(-70.67, 2);
    expect(m.taken).toBeUndefined();
  });
  it("honours the switches: nothing is read when both are off, no position when locations are off", () => {
    expect(readExif(jpegWithExif(), { dates: false, locations: false })).toEqual({});
    const m = readExif(jpegWithExif(), { dates: true, locations: false });
    expect(m.taken).toBe("2024-07-14T18:03:09");
    expect(m.lat).toBeUndefined();
    expect(m.lon).toBeUndefined();
  });
  it("is safe on files without Exif, truncated files and non-JPEG bytes", () => {
    expect(readExif(Uint8Array.from([0xff, 0xd8, 0xff, 0xd9]), { dates: true, locations: true })).toEqual({});
    expect(readExif(new Uint8Array(0), { dates: true, locations: true })).toEqual({});
    expect(readExif(Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]), { dates: true, locations: true })).toEqual({});
    const cut = jpegWithExif().slice(0, 40);
    expect(() => readExif(cut, { dates: true, locations: true })).not.toThrow();
  });
});
