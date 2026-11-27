// Locale logic for the web app (docs/I18N.md). English is the default; any es-* is Spanish; anything else is English.
// Selection order: the person's saved choice > the browser's languages > English. Pure functions first (tested), browser glue below.
import { EN as en, ES as es } from "../i18n/catalog";

export type Locale = "en" | "es";
export const LOCALES: readonly Locale[] = ["en", "es"];
export const DEFAULT_LOCALE: Locale = "en";
export const STORAGE_KEY = "vmk_locale";
export const LOCALE_EVENT = "vmk-locale";

const CATALOG: Record<Locale, Record<string, string>> = { en, es };

/** 'es', 'es-MX', 'es_419', 'ES' -> 'es'; 'en-GB' -> 'en'; anything else -> null. */
export function normalizeLocale(tag: unknown): Locale | null {
  const primary = String(tag ?? "").trim().toLowerCase().replace(/_/g, "-").split("-")[0];
  return primary === "en" || primary === "es" ? primary : null;
}

/** saved choice > first supported browser language > English. Unknown saved values are ignored. */
export function pickLocale(saved?: string | null, languages?: readonly string[] | null): Locale {
  const s = normalizeLocale(saved);
  if (s) return s;
  for (const l of languages ?? []) {
    const n = normalizeLocale(l);
    if (n) return n;
  }
  return DEFAULT_LOCALE;
}

const PLURAL = /\{(\w+),\s*plural,\s*one\s*\{([^{}]*)\}\s*other\s*\{([^{}]*)\}\s*\}/g;

/** `{name}` placeholders and `{n, plural, one {# x} other {# xs}}` (one/other only; `#` is the number). Missing params stay visible as `{name}`. */
export function format(text: string, locale: Locale, params: Record<string, string | number> = {}): string {
  const rules = new Intl.PluralRules(locale);
  const out = text.replace(PLURAL, (_m, name: string, one: string, other: string) => {
    const n = Number(params[name] ?? 0);
    return (rules.select(n) === "one" ? one : other).replace(/#/g, String(n));
  });
  return out.replace(/\{(\w+)\}/g, (m, name: string) => (name in params ? String(params[name]) : m));
}

/** The text for `key`; English when Spanish lacks it; the key itself when neither has it. */
export function translate(key: string, locale: Locale, params?: Record<string, string | number>): string {
  const text = CATALOG[locale]?.[key] ?? CATALOG.en[key] ?? key;
  return format(text, locale, params);
}

// ---------------------------------------------------------------- routing: /es/... for Spanish pages, / for English

/** The same page in another locale: '/privacy/' <-> '/es/privacy/', '/' <-> '/es/', '/es' -> '/'. Query and hash are kept. */
export function pathForLocale(path: string, locale: Locale): string {
  const m = /^([^?#]*)([?#].*)?$/.exec(path) as RegExpExecArray;
  let p = m[1] || "/";
  const rest = m[2] ?? "";
  if (p === "/es" || p.startsWith("/es/")) p = p.slice(3) || "/";
  if (!p.startsWith("/")) p = "/" + p;
  if (locale === "es") p = p === "/" ? "/es/" : "/es" + p;
  return p + rest;
}

/** The locale a path is written in (the /es/ prefix), else null (the app pages have no prefix: they follow the saved choice). */
export function localeOfPath(path: string): Locale | null {
  return path === "/es" || path.startsWith("/es/") ? "es" : path === "/" || /^\/(privacy|terms|support|delete-account)(\/|$)/.test(path) ? "en" : null;
}

/** The headers every API call carries so the server answers in the person's language (docs/CREATE_API.md). */
export const localeHeaders = (locale: Locale): Record<string, string> => ({ "X-Locale": locale });

// ---------------------------------------------------------------- browser glue (never throws; works without storage)
export function savedLocale(): Locale | null {
  try {
    return normalizeLocale(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

/** The locale of this browser: saved choice, else the browser languages, else English. */
export function getLocale(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  return pickLocale(savedLocale(), typeof navigator !== "undefined" ? (navigator.languages?.length ? navigator.languages : [navigator.language]) : []);
}

/** Remember the choice and tell every listener (React components, the footer) to redraw. */
export function setLocale(locale: Locale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* private mode: the choice lasts until reload */
  }
  if (typeof window !== "undefined") {
    document.documentElement.lang = locale;
    window.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: locale }));
  }
}

/** t() for code outside React: reads the browser's locale at call time. */
export const t = (key: string, params?: Record<string, string | number>): string => translate(key, getLocale(), params);

/** Headers for a fetch made now. */
export const currentLocaleHeaders = (): Record<string, string> => localeHeaders(getLocale());
