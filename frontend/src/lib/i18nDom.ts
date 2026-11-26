// Fills the static (build-time English) markup of the app screens in the person's language, and wires the language switcher.
// Elements: data-i18n="key" (text), data-i18n-html="key" (trusted catalog text with placeholders already inserted as markup by the caller),
// data-i18n-aria="key", data-i18n-title="key" (document title, on <html>), data-path="/privacy" (a link whose /es/ prefix follows the locale).
import { LOCALE_EVENT, getLocale, pathForLocale, savedLocale, setLocale, translate } from "./i18n";
import type { Locale } from "./i18n";

export function applyDom(locale: Locale, root: ParentNode = document): void {
  document.documentElement.lang = locale;
  root.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => (el.textContent = translate(el.dataset.i18n!, locale)));
  root.querySelectorAll<HTMLElement>("[data-i18n-aria]").forEach((el) => el.setAttribute("aria-label", translate(el.dataset.i18nAria!, locale)));
  root.querySelectorAll<HTMLAnchorElement>("a[data-path]").forEach((a) => (a.href = pathForLocale(a.dataset.path!, locale)));
  root.querySelectorAll<HTMLElement>("[data-lang-option]").forEach((el) => el.setAttribute("aria-current", el.dataset.langOption === locale ? "true" : "false"));
  const titleKey = document.documentElement.dataset.i18nTitle;
  if (titleKey) document.title = translate(titleKey, locale);
}

/** Wire the footer switcher. Static pages (written in one language) navigate to the other language's page and remember the choice;
 *  app screens switch in place. Returns the locale in use. */
export function initLocale(staticLocale?: Locale): Locale {
  const dynamic = !staticLocale;
  const locale = staticLocale ?? getLocale();
  if (dynamic) applyDom(locale);
  document.querySelectorAll<HTMLElement>("[data-lang-option]").forEach((el) => {
    el.addEventListener("click", (ev) => {
      const next = el.dataset.langOption as Locale;
      setLocale(next);
      if (dynamic) {
        ev.preventDefault();
        applyDom(next);
      }
    });
  });
  window.addEventListener(LOCALE_EVENT, (e) => dynamic && applyDom((e as CustomEvent<Locale>).detail));
  return locale;
}

export { savedLocale };
