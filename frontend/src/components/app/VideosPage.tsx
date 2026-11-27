// Videos: a grid of real thumbnails (the making card first), a search pill, a New video button. No per-card buttons: the card opens the video, the ... menu holds the rest.
import "../../styles/app-b.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, MakingCard, Thumb, useToast } from "../ui";
import { AIcon as Icon } from "./icons";
import { Menu } from "./Menu";
import Shortcuts from "./Shortcuts";
import { useVideos } from "./useVideos";
import { APP_PATHS, appUrl } from "../../lib/links";
import { filterVideos, formatDuration, isMaking } from "../../lib/videos";
import type { TaskItem } from "../../lib/videos";
import { useLocale } from "../../lib/useLocale";

function ago(iso: string | null | undefined, tr: (k: string, p?: Record<string, number>) => string): string | null {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  const min = Math.floor(Math.max(0, Date.now() - then) / 60000);
  if (min < 1) return tr("time.just_now");
  if (min < 60) return tr("time.minutes", { n: min });
  const hr = Math.floor(min / 60);
  if (hr < 24) return tr("time.hours", { n: hr });
  const day = Math.floor(hr / 24);
  if (day < 30) return tr("time.days", { n: day });
  const mon = Math.floor(day / 30);
  return mon < 12 ? tr("time.months", { n: mon }) : tr("time.years", { n: Math.floor(mon / 12) });
}

function Card({ v, thumb, onCopied }: { v: TaskItem; thumb?: string; onCopied: () => void }) {
  const { t } = useLocale();
  const title = v.title || t("gen.untitled");
  const dur = formatDuration(v.duration_s);
  const failed = v.status === "error" || v.status === "rejected";
  const remember = () => { const u = v.video_url || v.download_url; if (u?.startsWith("http")) { try { sessionStorage.setItem(`vmk_play_url_${v.id}`, u); } catch { /* full */ } } };
  const watch = `${APP_PATHS.watch}?id=${encodeURIComponent(v.id)}`;
  const items = [
    ...(v.editable && v.status === "complete" ? [{ id: "edit", label: t("gen.edit"), href: `${APP_PATHS.edit}?id=${encodeURIComponent(v.id)}` }] : []),
    ...(v.status === "complete" ? [{ id: "copy", label: t("gen.copy_link") }] : []),
    ...(v.status === "complete" && v.download_url ? [{ id: "download", label: t("gen.download"), href: v.download_url }] : []),
  ];
  const copy = async () => { try { await navigator.clipboard.writeText(appUrl(APP_PATHS.watch, { id: v.id })); onCopied(); } catch { /* clipboard blocked */ } };
  return (
    <article className={`vtile ${failed ? "is-failed" : ""}`}>
      {failed ? (
        <div className="vtile-fail"><p className="vtile-title">{title}</p><p className="muted">{v.status === "rejected" ? (v.reject_reason || t("gen.rejected_default")) : t("gen.error_detail")}</p></div>
      ) : (
        <a href={watch} onClick={remember} className="vtile-link" aria-label={dur ? t("gen.watch_duration", { title, duration: dur }) : t("gen.watch", { title })}>
          <Thumb id={v.id} src={thumb} duration={dur} />
          <p className="vtile-title">{title}</p>
          <p className="vtile-meta">{ago(v.created_at, t)}</p>
        </a>
      )}
      {items.length > 0 && <Menu className="vtile-menu" triggerClass="icon-btn vtile-more" label={t("gen.more")} trigger={<Icon name="dots" size={20} />} items={items} align="end" onPick={(id) => { if (id === "copy") void copy(); }} />}
    </article>
  );
}

export default function VideosPage() {
  const { t } = useLocale();
  const { items, thumbs, state, reload } = useVideos();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const toast = useToast();

  useEffect(() => {   // right after creating a video the composer sends us here with ?started=1: one calm line, then the address is cleaned
    const u = new URL(location.href);
    if (u.searchParams.get("new") === "1") { u.pathname = "/new"; u.searchParams.delete("new"); location.replace(u.pathname + u.search); return; }   // old links: /generations?new=1&prompt=...
    if (u.searchParams.get("started") === "1") { toast.show(t("gen.started")); u.searchParams.delete("started"); history.replaceState(null, "", u.pathname + (u.search || "")); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {   // "/" focuses the search (Shortcuts asks the page; answering with preventDefault means "handled")
    const on = (e: Event) => { e.preventDefault(); setOpen(true); setTimeout(() => input.current?.focus(), 0); };
    window.addEventListener("vmk:search", on);
    return () => window.removeEventListener("vmk:search", on);
  }, []);

  const making = useMemo(() => items.filter(isMaking), [items]);
  const rest = useMemo(() => filterVideos(items.filter((i) => !isMaking(i)), q), [items, q]);
  const showMaking = !q.trim();

  let body: React.ReactNode;
  if (state === "loading") {
    body = <div className="vgrid" role="status" aria-label={t("gen.loading")}>{[0, 1, 2, 3].map((i) => <div key={i} className="vtile"><div className="skeleton vskel" /><div className="skeleton vskel-line" /></div>)}</div>;
  } else if (state === "error" && items.length === 0) {
    body = <EmptyState title={t("gen.load_error")} action={<button type="button" className="btn btn-primary" onClick={reload}>{t("gen.retry")}</button>} />;
  } else if (items.length === 0) {
    body = <EmptyState title={t("gen.empty_title")} body={t("gen.empty_body")} action={<a href="/new" className="btn btn-primary">{t("gen.empty_cta")}</a>} />;
  } else {
    body = (
      <>
        <div className="vgrid">
          {showMaking && making.map((m) => <MakingCard key={m.id} title={m.title} stage={m.stage} etaSeconds={m.eta_seconds} />)}
          {rest.map((v) => <Card key={v.id} v={v} thumb={thumbs[v.id]} onCopied={() => toast.show(t("gen.link_copied"))} />)}
        </div>
        {q.trim() && rest.length === 0 && <p className="muted vempty" role="status">{t("gen.search_none", { q: q.trim() })}</p>}
      </>
    );
  }

  return (
    <section className="page vpage">
      <header className="page-head">
        <h1 className="h1">{t("gen.nav_label")}</h1>
        <div className="page-tools">
          {items.length > 0 && (open
            ? <div className="search-pill is-open" role="search"><Icon name="search" size={18} /><input ref={input} type="search" value={q} placeholder={t("gen.search_ph")} aria-label={t("gen.search_ph")} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") { setQ(""); setOpen(false); } }} onBlur={() => { if (!q) setOpen(false); }} /></div>
            : <button type="button" className="search-pill" onClick={() => { setOpen(true); setTimeout(() => input.current?.focus(), 0); }}><Icon name="search" size={18} /><span>{t("gen.search")}</span></button>)}
          {!(state === "ready" && items.length === 0) && <a href="/new" className="btn btn-primary"><Icon name="plus" size={18} />{t("gen.new_video")}</a>}
        </div>
      </header>
      {body}
      {toast.node}
      <Shortcuts />
    </section>
  );
}
