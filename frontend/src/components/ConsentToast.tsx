// src/react/ConsentToast.tsx
import React, { useEffect, useState } from "react";
import { pathForLocale } from "../lib/i18n";
import type { Locale } from "../lib/i18n";
import { useLocale } from "../lib/useLocale";

type Choice = "accepted_all" | "necessary_only";

const STORAGE_KEY = "consent.choice";
const STORAGE_TS = "consent.timestamp";

export default function ConsentToast({ locale: fixedLocale }: { locale?: Locale }) {
  const { t, locale } = useLocale(fixedLocale);
  const [open, setOpen] = useState(false);
  const [animOK, setAnimOK] = useState(true);

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY)) return; // already chosen
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setAnimOK(!mq.matches);
    // slight delay so it doesn't clash with first paint
    const t = setTimeout(() => setOpen(true), 400);
    return () => clearTimeout(t);
  }, []);

  const decide = (choice: Choice) => {
    localStorage.setItem(STORAGE_KEY, choice);
    localStorage.setItem(STORAGE_TS, String(Date.now()));
    setOpen(false);
  };

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label={t("consent.label")}
      aria-live="polite"
      className={[
        "fixed z-50 bottom-4 right-4 w-[min(92vw,360px)]",
        "rounded-2xl border border-neutral-200 bg-white/95 backdrop-blur",
        "shadow-[0_8px_24px_rgba(0,0,0,0.08)] p-3 md:p-4",
        animOK ? "animate-in fade-in slide-in-from-bottom-2 duration-200" : ""
      ].join(" ")}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 h-2.5 w-2.5 rounded-full bg-neutral-900 shrink-0" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-medium text-neutral-900">
            {t("consent.title")}
          </p>
          <p className="mt-1 text-xs text-neutral-600">
            {t("consent.body")}{" "}
            <a href={pathForLocale("/privacy", locale)} className="underline underline-offset-2">{t("consent.privacy")}</a>
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              onClick={() => decide("necessary_only")}
              className="rounded-xl bg-black px-3 py-1.5 text-sm font-medium text-white"
            >
              {t("consent.ok")}
            </button>
          </div>
        </div>
        <button
          onClick={() => decide("necessary_only")}
          aria-label={t("consent.close")}
          className="ml-auto rounded-lg p-1.5 text-neutral-500 hover:bg-neutral-100"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
