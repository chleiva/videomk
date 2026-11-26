import { useCallback, useEffect, useState } from "react";
import { LOCALE_EVENT, getLocale, setLocale, translate } from "./i18n";
import type { Locale } from "./i18n";

/**
 * The locale for a React component. Pages that are written in one language (the landing page at / and /es/) pass `fixed`, which makes server
 * and browser render the same text. App screens (client-only) follow the saved choice or the browser and redraw when the switcher changes it.
 */
export function useLocale(fixed?: Locale) {
  const [locale, set] = useState<Locale>(() => fixed ?? getLocale());
  useEffect(() => {
    if (fixed) return;
    const on = () => set(getLocale());
    window.addEventListener(LOCALE_EVENT, on);
    return () => window.removeEventListener(LOCALE_EVENT, on);
  }, [fixed]);
  const t = useCallback((key: string, params?: Record<string, string | number>) => translate(key, locale, params), [locale]);
  return { locale, t, setLocale };
}
