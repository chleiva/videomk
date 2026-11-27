// My media (docs/MEDIA_LIBRARY.md, docs/WEB_REDESIGN_2026.md 6.3): search by meaning, filters, collections, a square grid, drop-anywhere upload with one calm banner, a floating selection bar
// (Make a video, Add to collection, Delete), the viewer, smart organise after a big upload, a one-time privacy note, the storage meter.
import "../../styles/app-b.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EmptyState, Spinner, useToast } from "../ui";
import { Dialog } from "../ui/Dialog";
import { AIcon as Icon } from "./icons";
import { Menu } from "./Menu";
import MediaGrid from "./MediaGrid";
import OrganizeSheet from "./OrganizeSheet";
import PhotoViewer from "./PhotoViewer";
import Shortcuts from "./Shortcuts";
import UploadBanner from "./UploadBanner";
import { useLibrary } from "./useLibrary";
import { useUploadQueue } from "./useUploadQueue";
import { addToCollection, createCollection, deleteCollection, deletePhotos, emptySelection, formatBytes, MAX_SELECT, storageTone } from "../../lib/library";
import type { Selection } from "../../lib/library";
import { filesFromDrop } from "../../lib/droppedFiles";
import { pictureFiles } from "../../lib/upload";
import { libraryDeps } from "../../lib/uploadDeps";
import { useLocale } from "../../lib/useLocale";

const HANDOFF = "vmk_compose_library";
const PRIVACY_KEY = "vmk_media_privacy_seen";
const ORGANIZE_FROM = 30;   // batches under 30 photos never prompt

export default function MediaPage() {
  const { t, locale } = useLocale();
  const lib = useLibrary();
  const up = useUploadQueue(libraryDeps);
  const toast = useToast();
  const [sel, setSel] = useState<Selection>(emptySelection);
  const [viewer, setViewer] = useState<number | null>(null);
  const [confirm, setConfirm] = useState<string[] | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [organize, setOrganize] = useState<string | null | false>(false);
  const [newName, setNewName] = useState<string | null>(null);
  const [pendingAdd, setPendingAdd] = useState<string[] | null>(null);   // a new collection is being created for these photos
  const [privacy, setPrivacy] = useState(() => { try { return localStorage.getItem(PRIVACY_KEY) !== "1"; } catch { return false; } });
  const input = useRef<HTMLInputElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const batchStart = useRef<string | null>(null);
  const depth = useRef(0);
  const doneRef = useRef(0);

  // ---- the "/" shortcut focuses the search
  useEffect(() => {
    const on = (e: Event) => { e.preventDefault(); search.current?.focus(); };
    window.addEventListener("vmk:search", on);
    return () => window.removeEventListener("vmk:search", on);
  }, []);

  // ---- adding photos: button, drop anywhere (folders too), paste
  const add = useCallback((files: File[]) => {
    const pics = pictureFiles(files);
    if (!pics.length) return;
    if (up.summary.finished >= up.summary.total) { up.queue.clearFinished(); batchStart.current = new Date(Date.now() - 60000).toISOString().slice(0, 19); }
    else if (!batchStart.current) batchStart.current = new Date(Date.now() - 60000).toISOString().slice(0, 19);
    up.queue.add(pics);
  }, [up.queue, up.summary.finished, up.summary.total]);

  useEffect(() => {
    const over = (e: DragEvent) => { if (e.dataTransfer?.types.includes("Files")) { e.preventDefault(); } };
    const enter = (e: DragEvent) => { if (e.dataTransfer?.types.includes("Files")) { depth.current++; setDragging(true); } };
    const leave = () => { depth.current = Math.max(0, depth.current - 1); if (depth.current === 0) setDragging(false); };
    const drop = (e: DragEvent) => { if (!e.dataTransfer?.types.includes("Files")) return; e.preventDefault(); depth.current = 0; setDragging(false); void filesFromDrop(e.dataTransfer).then(add); };
    const paste = (e: ClipboardEvent) => { const f = Array.from(e.clipboardData?.files ?? []); if (f.length && !(e.target as HTMLElement | null)?.closest("input,textarea")) { e.preventDefault(); add(f); } };
    window.addEventListener("dragover", over); window.addEventListener("dragenter", enter); window.addEventListener("dragleave", leave); window.addEventListener("drop", drop); window.addEventListener("paste", paste);
    return () => { window.removeEventListener("dragover", over); window.removeEventListener("dragenter", enter); window.removeEventListener("dragleave", leave); window.removeEventListener("drop", drop); window.removeEventListener("paste", paste); };
  }, [add]);

  // ---- when the queue finishes: refresh, and offer to organise a big batch
  useEffect(() => {
    const s = up.summary;
    if (s.total === 0 || s.finished < s.total || s.active > 0) return;
    if (doneRef.current === s.done + s.duplicates + s.failed + s.total) return;
    doneRef.current = s.done + s.duplicates + s.failed + s.total;
    void lib.refresh();
    if (s.done >= ORGANIZE_FROM && lib.summary?.organize === "ask") setOrganize(batchStart.current);
    else if (s.done >= ORGANIZE_FROM && lib.summary?.organize === "always") setOrganize(batchStart.current);
  }, [up.summary]); // eslint-disable-line react-hooks/exhaustive-deps

  const order = useMemo(() => lib.items.map((p) => p.id), [lib.items]);
  const selecting = sel.ids.length > 0;
  const filterOn = lib.filter.kind !== "all";
  const sum = lib.summary;
  const tone = sum ? storageTone(sum) : "ok";
  const years = sum?.years.slice(0, 3) ?? [];
  const places = sum?.places.slice(0, 3) ?? [];
  const inCollection = lib.filter.kind === "collection" ? sum?.collections.find((c) => c.id === (lib.filter as any).value) : undefined;

  function makeVideo(ids: string[]) {
    const byId = new Map(lib.items.map((p) => [p.id, p] as const));
    const picks = ids.map((id) => byId.get(id)).filter(Boolean).map((p) => ({ id: p!.id, thumb_url: p!.thumb_url }));
    try { sessionStorage.setItem(HANDOFF, JSON.stringify(picks.slice(0, MAX_SELECT))); } catch { /* full: the composer opens without them */ }
    location.assign("/new");
  }
  async function doDelete(ids: string[]) {
    setDeleting(true);
    const ok = await deletePhotos(ids);
    setDeleting(false); setConfirm(null);
    if (ok) { setSel(emptySelection); setViewer(null); await lib.refresh(); } else toast.show(t("media.delete_error"));
  }
  async function addTo(cid: string, ids: string[], name: string) {
    const ok = await addToCollection(cid, ids);
    if (ok) { toast.show(t("media.collection_added", { name })); setSel(emptySelection); void lib.loadSummary(); } else toast.show(t("media.collection_error"));
  }
  async function createAndAdd() {
    const name = newName?.trim(); const ids = pendingAdd ?? [];
    setNewName(null); setPendingAdd(null);
    if (!name) return;
    const c = await createCollection(name);
    if (!c) { toast.show(t("media.collection_error")); return; }
    if (ids.length) await addTo(c.id, ids, c.name); else void lib.loadSummary();
  }

  let body: React.ReactNode;
  if (lib.error === "load" && lib.items.length === 0) body = <EmptyState title={t("media.load_error")} action={<button type="button" className="btn btn-primary" onClick={() => void lib.refresh()}>{t("gen.retry")}</button>} />;
  else if (lib.loading && lib.items.length === 0) body = <div className="mgrid" role="status" aria-label={t("gen.loading")}>{Array.from({ length: 12 }, (_, i) => <div key={i} className="mtile skeleton" />)}</div>;
  else if (!lib.query && !filterOn && lib.items.length === 0) body = <EmptyState title={t("media.empty_title")} body={t("media.empty_body")} action={<button type="button" className="btn btn-primary" onClick={() => input.current?.click()}>{t("media.add")}</button>} />;
  else if (lib.items.length === 0) body = <EmptyState title={t("media.no_match")} body={t("media.no_match_body")} />;
  else body = <MediaGrid items={lib.items} grouped={!lib.query.trim() && lib.filter.kind !== "collection"} selection={sel} onSelection={setSel} onOpen={(id) => setViewer(order.indexOf(id))} max={MAX_SELECT} hasMore={lib.more} onMore={lib.loadMore} />;

  return (
    <section className="page mpage">
      <header className="page-head">
        <h1 className="h1">{t("media.title")}</h1>
        <div className="page-tools">
          {sum && sum.limit_bytes > 0 && <p className={`storage tone-${tone}`} aria-label={t("media.storage_a11y", { used: formatBytes(sum.used_bytes, locale), limit: formatBytes(sum.limit_bytes, locale) })}><span className="storage-bar" aria-hidden="true"><i style={{ width: `${Math.min(100, Math.round((sum.used_bytes / sum.limit_bytes) * 100))}%` }} /></span><span>{t("media.storage", { used: formatBytes(sum.used_bytes, locale), limit: formatBytes(sum.limit_bytes, locale) })}</span></p>}
          <button type="button" className="btn btn-primary" onClick={() => input.current?.click()} disabled={sum?.read_only}><Icon name="plus" size={18} />{t("media.add")}</button>
        </div>
        <input ref={input} type="file" hidden tabIndex={-1} accept="image/*" multiple onChange={(e) => { add(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
      </header>

      {privacy && <p className="privacy-note"><span>{t("media.privacy")}</span><button type="button" className="btn btn-line btn-sm" onClick={() => { setPrivacy(false); try { localStorage.setItem(PRIVACY_KEY, "1"); } catch { /* private mode */ } }}>{t("media.privacy_dismiss")}</button></p>}
      {sum?.read_only && <p className="notice notice-warn" role="status">{t("media.read_only")}</p>}
      {(up.summary.storageFull || (sum && tone === "full" && !sum.read_only)) && <p className="notice notice-warn" role="status"><span><strong>{t("media.storage_full")}</strong> {t("media.storage_full_body")}</span></p>}
      <UploadBanner queue={up.queue} summary={up.summary} onDismiss={() => up.queue.clearFinished()} />

      <div className="search-pill is-open wide" role="search"><Icon name="search" size={18} /><input ref={search} type="search" value={lib.query} placeholder={t("media.search_ph")} aria-label={t("media.search_label")} onChange={(e) => lib.setQuery(e.target.value)} />{lib.searching && <Spinner />}</div>
      {lib.chips.length > 0 && <div className="chips mchips" aria-live="polite">{lib.chips.map((c) => <button key={c.label} type="button" className="chip is-on" aria-label={t("media.chip_remove", { label: c.label })} onClick={() => lib.dropChip(c.label)}>{c.label}<Icon name="close" size={14} /></button>)}</div>}

      {!lib.query && sum && (years.length > 0 || places.length > 0 || sum.collections.length > 0) && (
        <div className="chips mfilters" role="group" aria-label={t("media.filter_collections")}>
          <button type="button" className="chip" aria-pressed={!filterOn} onClick={() => lib.setFilter({ kind: "all" })}>{t("media.filter_all")}</button>
          {years.map((y) => <button key={y.year} type="button" className="chip" aria-pressed={lib.filter.kind === "year" && (lib.filter as any).value === y.year} onClick={() => lib.setFilter({ kind: "year", value: y.year })}>{y.year}</button>)}
          {places.map((p) => <button key={p.name} type="button" className="chip" aria-pressed={lib.filter.kind === "place" && (lib.filter as any).value === p.name} onClick={() => lib.setFilter({ kind: "place", value: p.name })}>{p.name.split(",")[0]}</button>)}
          {sum.collections.map((c) => <button key={c.id} type="button" className="chip" aria-pressed={lib.filter.kind === "collection" && (lib.filter as any).value === c.id} onClick={() => lib.setFilter({ kind: "collection", value: c.id })}>{c.emoji ? `${c.emoji} ` : ""}{c.name}<span className="chip-count">{c.count}</span></button>)}
          <button type="button" className="chip chip-add" aria-label={t("media.new_collection")} onClick={() => { setPendingAdd([]); setNewName(""); }}><Icon name="plus" size={16} /></button>
        </div>
      )}
      {inCollection && <p className="coll-bar"><span>{inCollection.name}</span><button type="button" className="btn btn-line btn-sm" onClick={async () => { if (await deleteCollection(inCollection.id)) { lib.setFilter({ kind: "all" }); void lib.loadSummary(); } else toast.show(t("media.collection_error")); }}>{t("media.collection_delete")}</button></p>}

      {body}

      {selecting && (
        <div className="selbar" role="toolbar" aria-label={t("media.selected_n", { n: sel.ids.length })}>
          <span className="selbar-n" role="status">{t("media.selected_n", { n: sel.ids.length })}</span>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => makeVideo(sel.ids)}>{t("media.make_video")}</button>
          <Menu label={t("media.add_to_collection")} triggerClass="btn btn-line btn-sm" trigger={<span>{t("media.add_to_collection")}</span>} align="end"
            items={[...(sum?.collections ?? []).filter((c) => !c.auto || true).map((c) => ({ id: c.id, label: `${c.emoji ? c.emoji + " " : ""}${c.name}` })), { id: "__new", label: t("media.new_collection") }]}
            onPick={(id) => { if (id === "__new") { setPendingAdd(sel.ids); setNewName(""); } else void addTo(id, sel.ids, sum?.collections.find((c) => c.id === id)?.name ?? ""); }} />
          <button type="button" className="icon-btn" aria-label={t("media.delete")} onClick={() => setConfirm(sel.ids)}><Icon name="trash" size={20} /></button>
          <button type="button" className="icon-btn" aria-label={t("media.clear_selection")} onClick={() => setSel(emptySelection)}><Icon name="close" size={20} /></button>
          <button type="button" className="btn btn-line btn-sm selbar-all" onClick={() => setSel({ ids: order.slice(0, MAX_SELECT), anchor: order[0] ?? null })}>{t("media.select_all")}</button>
        </div>
      )}

      {viewer !== null && lib.items[viewer] && <PhotoViewer items={lib.items} index={viewer} onIndex={setViewer} onClose={() => setViewer(null)} onMakeVideo={(p) => makeVideo([p.id])} onDelete={(p) => setConfirm([p.id])} />}
      {confirm && <Dialog title={t("media.delete_title", { n: confirm.length })} danger busy={deleting} confirmLabel={t("media.delete")} cancelLabel={t("media.cancel")} onCancel={() => setConfirm(null)} onConfirm={() => void doDelete(confirm)}>{t("media.delete_body")}</Dialog>}
      {newName !== null && (
        <Dialog title={t("media.new_collection")} confirmLabel={t("media.create")} cancelLabel={t("media.cancel")} onCancel={() => { setNewName(null); setPendingAdd(null); }} onConfirm={() => void createAndAdd()}>
          <input className="field" data-autofocus autoFocus maxLength={40} aria-label={t("media.collection_name")} placeholder={t("media.collection_name")} value={newName} onChange={(e) => setNewName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void createAndAdd(); } }} />
        </Dialog>
      )}
      {organize !== false && <OrganizeSheet since={organize ?? undefined} onClose={() => setOrganize(false)} onDone={() => { setOrganize(false); toast.show(t("library.organize_done")); void lib.refresh(); }} />}
      {dragging && <div className="drop-veil" aria-hidden="true"><div className="drop-card"><Icon name="upload" size={32} /><p>{t("media.drop_here")}</p></div></div>}
      {toast.node}
      <Shortcuts />
    </section>
  );
}
