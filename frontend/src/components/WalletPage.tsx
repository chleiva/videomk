// Credits: the balance hero, what you have (buckets with expiry), and how credits work (the same explainer the Create sheet opens). No pricing here: buying is "coming soon".
import { useEffect, useState } from "react";
import { getWallet } from "../lib/api";
import type { Wallet } from "../lib/api";
import { Icon } from "./ui";
import { useLocale } from "../lib/useLocale";

const KINDS = ["daily", "signup", "paid", "refund"];

export default function WalletPage() {
  const { t, locale } = useLocale();
  const [wallet, setWallet] = useState<Wallet | null | undefined>(undefined);
  useEffect(() => { getWallet().then(setWallet); }, []);
  const day = (secs: number) => new Intl.DateTimeFormat(locale, { day: "numeric", month: "long" }).format(new Date(secs * 1000));
  const expiry = (at: number | null) => {
    if (at === null) return t("wallet.never_expire");
    const left = at * 1000 - Date.now();
    return left < 24 * 3600 * 1000 && new Date(at * 1000).toDateString() === new Date().toDateString() ? t("wallet.expire_tonight") : t("wallet.expire_on", { date: day(at) });
  };

  return (
    <section className="page page-narrow">
      <h1 className="h1">{t("wallet.title")}</h1>

      {wallet === undefined && <div className="wallet-hero mt-6 animate-pulse" style={{ minHeight: "11rem" }} role="status" aria-label={t("gen.loading")} />}
      {wallet === null && <p className="notice notice-bad mt-6" role="alert">{t("wallet.load_error")}</p>}
      {wallet && (
        <>
          <div className="wallet-hero mt-6" role="group" aria-label={wallet.unlimited ? t("wallet.unlimited_short") : t("wallet.balance_a11y", { n: wallet.balance })}>
            <span className="glass-chip self-start"><Icon name="bolt" size={14} />{t("wallet.title")}</span>
            <p className="big mt-2">{wallet.unlimited ? "∞" : wallet.balance}</p>
            <p className="sub">{wallet.unlimited ? t("wallet.unlimited_long") : wallet.balance === 0 ? t("wallet.none") : t("wallet.credits_label")}</p>
            {wallet.next_daily_at && <p className="sub">{t("wallet.next_free", { date: day(wallet.next_daily_at) })}</p>}
          </div>

          {wallet.buckets.length > 0 && (
            <div className="card mt-6 px-5 py-2">
              <h2 className="eyebrow pt-3">{t("wallet.what_you_have")}</h2>
              <ul>
                {wallet.buckets.map((b, i) => (
                  <li key={i} className="bucket">
                    <div><p className="font-semibold">{t(`wallet.bucket.${KINDS.includes(b.kind) ? b.kind : "other"}`)}</p><p className="caption">{expiry(b.expires_at)}</p></div>
                    <p className="text-[length:var(--fs-title3)] font-bold">{b.remaining}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <div className="card mt-6 p-5">
        <h2 className="h2">{t("wallet.cost_title")}</h2>
        <ul className="mt-3 space-y-2 muted">
          <li>{t("wallet.cost_minute")}</li><li>{t("wallet.cost_example")}</li><li>{t("wallet.cost_4k")}</li><li>{t("wallet.cost_expiry")}</li>
        </ul>
      </div>
      <p className="notice notice-info mt-6">{t("wallet.coming_soon")}</p>
      <div className="mt-6"><a href="/generations" className="btn btn-primary">{t("gen.create")}</a></div>
    </section>
  );
}
