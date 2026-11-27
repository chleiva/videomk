// ONE place for links between the marketing site (videomk.com) and the web app (app.videomk.com). Set PUBLIC_SITE_URL / PUBLIC_APP_URL at build time
// (local dev: http://localhost:4321 for both). Paths are written without `index.html`; CloudFront adds it (docs/WEB_REDESIGN_2026.md WP0).
import { APP_URL, SITE_URL } from "./config";
import type { Locale } from "./i18n";

/** Paths that exist in the app (app.videomk.com). */
export const APP_PATHS = { videos: "/generations", create: "/generations?new=1", watch: "/watch", edit: "/edit", credits: "/wallet", feedback: "/feedback", signin: "/signin", media: "/media", settings: "/settings" } as const;
/** Paths that exist on the marketing site (videomk.com), English; Spanish lives under /es. */
export const SITE_PATHS = { home: "/", privacy: "/privacy", terms: "/terms", support: "/support", deleteAccount: "/delete-account" } as const;

function join(base: string, path: string): string {
  if (!path || path === "/") return base + "/";
  return base + (path.startsWith("/") ? path : "/" + path);
}

/** Absolute URL of an app page, optionally with query parameters (values are encoded). */
export function appUrl(path: string = "/", query?: Record<string, string | number | undefined>): string {
  const q = Object.entries(query ?? {}).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
  const url = join(APP_URL, path);
  return q ? url + (url.includes("?") ? "&" : "?") + q : url;
}

/** Absolute URL of a marketing page in the person's language ("/es/privacy" for Spanish). */
export function siteUrl(path: string = "/", locale: Locale = "en"): string {
  const p = path.startsWith("/") ? path : "/" + path;
  const localized = locale === "es" ? (p === "/" ? "/es/" : "/es" + p) : p;
  return join(SITE_URL, localized);
}

/** "Try this prompt" CTA: opens the app's Create with the prompt filled in (the app reads `prompt`; signed-out people go through sign-in first and come back). */
export function tryPromptUrl(prompt: string): string {
  return appUrl(APP_PATHS.videos, { new: 1, prompt: prompt.slice(0, 500) });
}
