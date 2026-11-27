// The two photo switches the apps have in Settings ("Use photo dates", "Use photo locations"; both on by default, docs/PHOTOS.md): whether the browser reads the capture time
// and the position from a photo's Exif BEFORE it is re-encoded. Stored per browser; the Settings page (package C) uses the same keys through these functions.
export const KEY_DATES = "vmk_photo_dates";
export const KEY_LOCATIONS = "vmk_photo_locations";

function read(key: string): boolean {
  try { const v = localStorage.getItem(key); return v === null ? true : v === "1"; } catch { return true; }
}
function write(key: string, on: boolean): void {
  try { localStorage.setItem(key, on ? "1" : "0"); } catch { /* private mode: the choice lasts until the tab closes */ }
}
export const photoDates = (): boolean => read(KEY_DATES);
export const photoLocations = (): boolean => read(KEY_LOCATIONS);
export const setPhotoDates = (on: boolean): void => write(KEY_DATES, on);
export const setPhotoLocations = (on: boolean): void => write(KEY_LOCATIONS, on);
