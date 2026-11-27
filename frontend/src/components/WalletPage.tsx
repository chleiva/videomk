// Credits (docs/UX_2026_REDESIGN.md 4.4): the balance, one line about the next free credit, a small "how credits work" table, what you have (history by bucket).
// No paragraphs. Buying is not open yet: "Get more" is shown, disabled, with "Coming soon".
import { useEffect, useRef, useState } from "react";
import { getWallet } from "../lib/api";
import type { Wallet } from "../lib/api";
import { PIcon } from "./PlayerIcons";
import { Skeleton } from "./ui/Skeleton";
import { useLocale } from "../lib/useLocale";

const KINDS = ["daily", "signup", "paid", "refund"];

export default function WalletPage() {
  const { t, locale } = useLocale();
  const [wallet, setWallet] = useState<Wallet | null | undefined>(undefined);
  const [how, setHow] = useState(false);
  const pop = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => { getWallet().then(setWallet); }, []);
  useEffect(() => {
    if (!how) return;
    const away = (e: MouseEvent) => { if (!pop.current?.contains(e.target as Node) && !trigger.current?.contains(e.target as Node)) setHow(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setHow(false); trigger.current?.focus(); } };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key); };
  }, [how]);

  const day = (secs: number) => new Intl.DateTimeFormat(locale, { day: "numeric", month: "long" }).format(new Date(secs * 1000));
  const expiry = (at: number | null) => {
    if (at === null) return t("wallet.never_expire");
    const left = at * 1000 - Date.now();
    return left < 24 * 3600 * 1000 && new Date(at * 1000).toDateString() === new Date().toDateString() ? t("wallet.expire_tonight") : t("wallet.expire_on", { date: day(at) });
  };

  return (
    <section className="page page-narrow credits">
      <h1 className="h1">{t("wallet.title")}</h1>

      {wallet === undefined && <div className="credits-hero" role="status" aria-label={t("gen.loading")}><Skeleton width="6rem" height="4rem" /></div>}
      {wallet === null && <p className="notice notice-bad mt-6" role="alert">{t("wallet.load_error")}</p>}
      {wallet && (
        <>
          <div className="credits-hero" role="group" aria-label={wallet.unlimited ? t("credits.unlimited") : t("wallet.balance_a11y", { n: wallet.balance })}>
            <p className="credits-num">{wallet.unlimited ? "∞" : wallet.balance}</p>
            <p className="credits-word">{wallet.unlimited ? t("credits.unlimited") : wallet.balance === 0 ? t("credits.word_none") : t("credits.word")}</p>
          </div>
          {wallet.next_daily_at && !wallet.unlimited && <p className="credits-line">{t("credits.next_free", { date: day(wallet.next_daily_at) })}</p>}

          <div className="credits-actions">
            <a className="btn btn-primary" href="/generations?create=1"><PIcon name="plus" size={18} />{t("credits.new_video")}</a>
            <button type="button" className="btn btn-tonal" disabled aria-disabled="true" title={t("credits.soon")}>{t("credits.get_more")}<span className="soon">{t("credits.soon")}</span></button>
          </div>

          <div className="credits-how">
            <button ref={trigger} type="button" className="credits-how-btn" onClick={() => setHow((v) => !v)} aria-expanded={how} aria-controls="credits-table"><PIcon name="info" size={18} />{t("credits.how")}</button>
            {how && (
              <div ref={pop} id="credits-table" className="credits-table" role="group" aria-label={t("credits.how")}>
                <p>{t("credits.row_minute")}</p><p>{t("credits.row_4k")}</p><p>{t("credits.row_free")}</p><p>{t("credits.row_paid")}</p>
              </div>
            )}
          </div>

          {wallet.buckets.length > 0 && !wallet.unlimited && (
            <ul className="credits-list">
              {wallet.buckets.map((b, i) => (
                <li key={i}>
                  <div><p className="credits-kind">{t(`wallet.bucket.${KINDS.includes(b.kind) ? b.kind : "other"}`)}</p><p className="caption">{expiry(b.expires_at)}</p></div>
                  <p className="credits-n">{b.remaining}</p>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
