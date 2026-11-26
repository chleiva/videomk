import { useEffect, useState } from "react";
import GenerationsList from "./GenerationsList";
import CreateSheet from "./CreateSheet";
import { Icon, useToast } from "./ui";
import { getWallet } from "../lib/api";
import type { Wallet } from "../lib/api";
import { useLocale } from "../lib/useLocale";

export default function GenerationsPage() {
  const { t } = useLocale();
  const [creating, setCreating] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [view, setView] = useState<"grid" | "list">("grid");
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const toast = useToast();

  useEffect(() => { getWallet().then(setWallet); }, [refreshNonce]);

  return (
    <section className="page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="h1">{t("gen.title")}</h1>
          <p className="muted mt-1">{t("gen.subtitle")}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {wallet && (
            <a href="/wallet/index.html" className="credit-pill" aria-label={wallet.unlimited ? t("wallet.unlimited_short") : t("wallet.balance_a11y", { n: wallet.balance })}>
              <Icon name="bolt" size={16} />{wallet.unlimited ? t("wallet.unlimited_short") : wallet.balance}
            </a>
          )}
          <div role="group" aria-label={t("gen.toggle_view")} className="theme-switch hidden md:inline-flex">
            <button type="button" onClick={() => setView("grid")} aria-pressed={view === "grid"}>{t("gen.grid")}</button>
            <button type="button" onClick={() => setView("list")} aria-pressed={view === "list"}>{t("gen.list")}</button>
          </div>
          <button type="button" onClick={() => setCreating(true)} className="btn btn-primary">
            <Icon name="plus" size={18} />{t("gen.create")}
          </button>
        </div>
      </div>

      <div className="mt-6">
        <GenerationsList refreshNonce={refreshNonce} view={view} onCreate={() => setCreating(true)} />
      </div>

      {creating && (
        <CreateSheet
          onClose={() => setCreating(false)}
          onCreated={() => { setCreating(false); setRefreshNonce((n) => n + 1); toast.show(t("gen.started")); }}
        />
      )}
      {toast.node}
    </section>
  );
}
