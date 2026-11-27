// The photo grid: square tiles, month headers on the timeline, lazy images, selection by checkbox, shift-click range, Ctrl/Cmd-click toggle, and drag across tiles in selection mode.
// A tile opens the viewer unless the person is selecting. content-visibility keeps a very long timeline cheap to draw; the page loads more as the end scrolls into view.
import { useEffect, useMemo, useRef } from "react";
import { AIcon as Icon } from "./icons";
import { groupByMonth, idsBetween, monthLabel, selectClick } from "../../lib/library";
import type { Photo, Selection } from "../../lib/library";
import { useLocale } from "../../lib/useLocale";

export function photoLabel(p: Photo, locale: string): string {
  const d = new Date(p.taken || p.added || "");
  let when = "";
  if (!Number.isNaN(d.getTime())) { try { when = new Intl.DateTimeFormat(locale, { dateStyle: "long", timeZone: p.taken ? "UTC" : undefined }).format(d); } catch { when = ""; } }
  return [when, p.place].filter(Boolean).join(", ") || "·";
}

export default function MediaGrid({ items, grouped, selection, onSelection, onOpen, selectOnly = false, max, onMore, hasMore }: {
  items: Photo[]; grouped: boolean; selection: Selection; onSelection: (s: Selection) => void; onOpen?: (id: string) => void; selectOnly?: boolean; max: number; onMore?: () => void; hasMore?: boolean;
}) {
  const { t, locale } = useLocale();
  const order = useMemo(() => items.map((p) => p.id), [items]);
  const groups = useMemo(() => (grouped ? groupByMonth(items) : [{ key: "all", year: 0, month: 0, items }]), [items, grouped]);
  const selecting = selection.ids.length > 0;
  const drag = useRef<{ start: string; base: string[] } | null>(null);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const end = () => { drag.current = null; };
    window.addEventListener("pointerup", end); window.addEventListener("pointercancel", end);
    return () => { window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", end); };
  }, []);
  useEffect(() => {
    if (!hasMore || !onMore || !sentinel.current || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((e) => { if (e[0]?.isIntersecting) onMore(); }, { rootMargin: "600px" });
    io.observe(sentinel.current);
    return () => io.disconnect();
  }, [hasMore, onMore, items.length]);

  const toggle = (id: string, range: boolean) => onSelection(selectClick(selection, order, id, range, max));
  const click = (e: React.MouseEvent, id: string) => {
    if (selectOnly || selecting || e.shiftKey || e.metaKey || e.ctrlKey) { e.preventDefault(); toggle(id, e.shiftKey); return; }
    onOpen?.(id);
  };
  const onDown = (e: React.PointerEvent, id: string) => { if (e.pointerType === "mouse" && e.button === 0 && (selecting || selectOnly) && !(e.target as HTMLElement).closest(".mtile-check")) drag.current = { start: id, base: selection.ids }; };
  const onEnter = (id: string) => {
    const d = drag.current; if (!d || d.start === id) return;
    const merged = [...new Set([...d.base, ...idsBetween(order, d.start, id)])].slice(0, max);
    onSelection({ ids: merged, anchor: d.start });
  };

  return (
    <div className="mgrid-wrap">
      {groups.map((g) => {
        const label = grouped ? monthLabel(g, locale) ?? t("media.undated") : null;
        return (
          <section key={g.key} aria-label={label ?? undefined}>
            {label && <h2 className="mhead"><span>{label}</span><span className="mhead-n">{t("media.photos_n", { n: g.items.length })}</span></h2>}
            <div className="mgrid" role="list">
              {g.items.map((p) => {
                const on = selection.ids.includes(p.id);
                const lbl = photoLabel(p, locale);
                return (
                  <div key={p.id} role="listitem" className={`mtile ${on ? "is-on" : ""}`} onPointerDown={(e) => onDown(e, p.id)} onPointerEnter={() => onEnter(p.id)}>
                    <button type="button" className="mtile-btn" aria-label={on ? `${lbl}, ${t("media.photo_selected")}` : lbl} aria-pressed={selectOnly || selecting ? on : undefined} onClick={(e) => click(e, p.id)}>
                      {p.thumb_url ? <img src={p.thumb_url} alt="" loading="lazy" decoding="async" draggable={false} /> : <span className="mtile-ph" />}
                    </button>
                    {!selectOnly && <button type="button" className="mtile-check" aria-label={`${t("media.selected_n", { n: 1 })}: ${lbl}`} aria-pressed={on} onClick={(e) => { e.stopPropagation(); toggle(p.id, e.shiftKey); }}><Icon name="check" size={16} /></button>}
                    {selectOnly && on && <span className="mtile-tick" aria-hidden="true"><Icon name="check" size={16} /></span>}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
      {hasMore && <div ref={sentinel} className="mgrid-more" aria-hidden="true" />}
    </div>
  );
}
