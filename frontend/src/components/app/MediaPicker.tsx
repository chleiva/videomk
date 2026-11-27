// "From My media" in the composer: the same grid with search, select up to what still fits in the video, Use N. Photos from the person's prompt: a prompt like
// "my holidays in Thailand 2024" can be searched first (the search box starts with it when the composer passes one).
import { useState } from "react";
import { Sheet, Spinner } from "../ui";
import { AIcon as Icon } from "./icons";
import MediaGrid from "./MediaGrid";
import { useLibrary } from "./useLibrary";
import { emptySelection } from "../../lib/library";
import type { Photo, Selection } from "../../lib/library";
import { useLocale } from "../../lib/useLocale";

export default function MediaPicker({ max, onClose, onUse, initialQuery = "" }: { max: number; onClose: () => void; onUse: (p: Photo[]) => void; initialQuery?: string }) {
  const { t } = useLocale();
  const lib = useLibrary();
  const [sel, setSel] = useState<Selection>(emptySelection);
  const picked = lib.items.filter((p) => sel.ids.includes(p.id));
  const empty = !lib.loading && lib.items.length === 0 && !lib.query;
  return (
    <Sheet title={t("media.picker_title")} onClose={onClose}>
      <div className="picker">
        <div className="search-pill is-open picker-search" role="search"><Icon name="search" size={18} /><input type="search" value={lib.query} placeholder={t("media.search_ph")} aria-label={t("media.search_label")} onChange={(e) => lib.setQuery(e.target.value)} /></div>
        {initialQuery.trim().length >= 8 && !lib.query && <div className="chips"><button type="button" className="chip" onClick={() => lib.setQuery(initialQuery.trim())}><Icon name="sparkle" size={16} />{t("media.from_prompt")}</button></div>}
        {lib.chips.length > 0 && <div className="chips">{lib.chips.map((c) => <button key={c.label} type="button" className="chip is-on" aria-label={t("media.chip_remove", { label: c.label })} onClick={() => lib.dropChip(c.label)}>{c.label}<Icon name="close" size={14} /></button>)}</div>}
        <div className="picker-body">
          {lib.loading && lib.items.length === 0 ? <p className="muted" role="status"><Spinner /> {t("gen.loading")}</p>
            : empty ? <p className="muted">{t("media.empty_body")} <a href="/media">{t("media.title")}</a></p>
            : lib.items.length === 0 ? <p className="muted">{t("media.no_match")}</p>
            : <MediaGrid items={lib.items} grouped={!lib.query.trim()} selection={sel} onSelection={setSel} selectOnly max={max} hasMore={lib.more} onMore={lib.loadMore} />}
        </div>
        <div className="dialog-actions">
          {sel.ids.length >= max && <p className="hint">{t("media.max_select", { n: max })}</p>}
          <button type="button" className="btn btn-line btn-sm" onClick={() => setSel(lib.items.length ? { ids: lib.items.map((p) => p.id).slice(0, max), anchor: lib.items[0].id } : emptySelection)} disabled={lib.items.length === 0}>{t("media.select_all")}</button>
          <button type="button" className="btn btn-primary btn-sm" disabled={picked.length === 0} onClick={() => onUse(picked)}>{t("media.picker_use", { n: picked.length })}</button>
        </div>
      </div>
    </Sheet>
  );
}
