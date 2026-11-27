// The message catalogue, split by AREA so parallel work never edits the same JSON file (docs/WEB_REDESIGN_2026.md, WP0).
//   common       shell, footer, theme, nav, time, status, validation, consent        (owner: shell / WP0)
//   marketing    landing page and the public legal pages                              (owner: package A)
//   auth         sign-in and the OAuth callback                                       (owner: package C)
//   app-create   Create, questions, decks (presentation to video)                     (owner: package B)
//   app-library  Videos list, Making card, media library, collections, upload        (owner: package B)
//   app-player   player, editor, credits/wallet, settings, feedback                   (owner: package C)
// A key's first segment (`gen.title` -> `gen`) must belong to exactly one area (areas.json lists the segments); catalog.test.ts enforces it, the
// EN/ES key parity and the placeholder parity of every area. Add new keys to your own area's `<area>.en.json` AND `<area>.es.json`.
import areas from "./areas.json";
import commonEn from "./common.en.json";
import commonEs from "./common.es.json";
import marketingEn from "./marketing.en.json";
import marketingEs from "./marketing.es.json";
import authEn from "./auth.en.json";
import authEs from "./auth.es.json";
import createEn from "./app-create.en.json";
import createEs from "./app-create.es.json";
import libraryEn from "./app-library.en.json";
import libraryEs from "./app-library.es.json";
import playerEn from "./app-player.en.json";
import playerEs from "./app-player.es.json";

export type Area = "common" | "marketing" | "auth" | "app-create" | "app-library" | "app-player";
export const AREA_PREFIXES: Record<Area, string[]> = areas as Record<Area, string[]>;
export const BY_AREA: Record<Area, { en: Record<string, string>; es: Record<string, string> }> = {
  common: { en: commonEn, es: commonEs },
  marketing: { en: marketingEn, es: marketingEs },
  auth: { en: authEn, es: authEs },
  "app-create": { en: createEn, es: createEs },
  "app-library": { en: libraryEn, es: libraryEs },
  "app-player": { en: playerEn, es: playerEs },
};
export const EN: Record<string, string> = Object.assign({}, ...Object.values(BY_AREA).map((a) => a.en));
export const ES: Record<string, string> = Object.assign({}, ...Object.values(BY_AREA).map((a) => a.es));
