import { describe, expect, it } from "vitest";
import { EN as en, ES as es } from "../i18n/catalog";
import { format, localeHeaders, localeOfPath, normalizeLocale, pathForLocale, pickLocale, translate } from "./i18n";

describe("normalizeLocale", () => {
  it("maps every es-* to es and en-* to en", () => {
    for (const t of ["es", "ES", "es-ES", "es-MX", "es_419", " es-AR "]) expect(normalizeLocale(t)).toBe("es");
    for (const t of ["en", "en-GB", "EN_us"]) expect(normalizeLocale(t)).toBe("en");
  });
  it("rejects everything else", () => {
    for (const t of ["fr", "fr-FR", "", null, undefined, 5, "esperanto", "zh-Hans"]) expect(normalizeLocale(t)).toBeNull();
  });
});

describe("pickLocale", () => {
  it("saved choice beats the browser", () => {
    expect(pickLocale("en", ["es-ES"])).toBe("en");
    expect(pickLocale("es", ["en-US"])).toBe("es");
  });
  it("browser languages in order; first supported wins", () => {
    expect(pickLocale(null, ["es-MX", "en"])).toBe("es");
    expect(pickLocale(null, ["fr-FR", "es", "en"])).toBe("es");
    expect(pickLocale(undefined, ["en-US", "es"])).toBe("en");
  });
  it("falls back to English; an invalid saved value is ignored", () => {
    expect(pickLocale(null, ["fr", "de"])).toBe("en");
    expect(pickLocale("klingon", ["es"])).toBe("es");
    expect(pickLocale(null, [])).toBe("en");
    expect(pickLocale()).toBe("en");
  });
});

describe("format and translate", () => {
  it("fills placeholders and plurals", () => {
    expect(format("Hi {name}", "en", { name: "Ana" })).toBe("Hi Ana");
    expect(translate("time.minutes", "en", { n: 1 })).toBe("1 min ago");
    expect(translate("time.minutes", "en", { n: 5 })).toBe("5 mins ago");
    expect(translate("time.days", "es", { n: 1 })).toBe("hace 1 día");
    expect(translate("time.days", "es", { n: 3 })).toBe("hace 3 días");
    expect(translate("editor.preview_changes", "es", { count: 2 })).toBe("Ver 2 cambios");
    expect(translate("questions.step", "es", { current: 1, total: 3 })).toBe("Paso 1 de 3");
  });
  it("keeps a missing placeholder visible and falls back to English for a missing key", () => {
    expect(format("a {x} b", "en")).toBe("a {x} b");
    expect(translate("no.such.key", "es")).toBe("no.such.key");
  });
});

describe("paths and headers", () => {
  it("maps a path to the other locale and back", () => {
    expect(pathForLocale("/privacy/", "es")).toBe("/es/privacy/");
    expect(pathForLocale("/es/privacy/", "en")).toBe("/privacy/");
    expect(pathForLocale("/", "es")).toBe("/es/");
    expect(pathForLocale("/es/", "en")).toBe("/");
    expect(pathForLocale("/es", "en")).toBe("/");
    expect(pathForLocale("/es/terms", "es")).toBe("/es/terms");
    expect(pathForLocale("/terms?x=1#a", "es")).toBe("/es/terms?x=1#a");
    expect(pathForLocale("/estimate", "es")).toBe("/es/estimate");   // not an /es/ prefix
  });
  it("knows which paths carry their own language", () => {
    expect(localeOfPath("/es/support/")).toBe("es");
    expect(localeOfPath("/support/")).toBe("en");
    expect(localeOfPath("/generations/index.html")).toBeNull();
  });
  it("sends X-Locale", () => expect(localeHeaders("es")).toEqual({ "X-Locale": "es" }));
});

describe("catalog parity", () => {
  const ph = (s: string) => [...s.matchAll(/\{(\w+)/g)].map((m) => m[1]).sort().join(",");
  it("has the same keys and placeholders in both languages", () => {
    expect(Object.keys(es).sort()).toEqual(Object.keys(en).sort());
    for (const k of Object.keys(en)) {
      expect(ph((es as any)[k]), k).toBe(ph((en as any)[k]));
      expect((es as any)[k].trim(), k).not.toBe("");
    }
  });
});
