// The Look picker (docs/CREATE_API.md "Video look (chosen and enforced)"): the Look pill opens ONE surface (a popover under the card on wide screens, a bottom sheet
// on a phone) with at most four picture tiles: Auto, Real, Whiteboard, Cartoon. Cartoon reveals its cast in the same surface: Auto, or up to three faces (two or
// three talk it through), and the hand-drawn board switch when the server lists it. Everything drawn comes from capabilities; the rules live in lib/looks.ts.
// Keyboard: arrow keys move between tiles (and between faces), Space or Enter chooses, Escape closes and gives the focus back to the pill.
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { AIcon as Icon } from "./icons";
import { castFull, castGroups, chooseLook, isConversation, narrowed, optionOf, pillOf, tiles, toggleCast, toggleExtra } from "../../lib/looks";
import type { CastMember, LookChoice, LookContext, LooksCaps } from "../../lib/looks";
import { useLocale } from "../../lib/useLocale";

type T = (key: string, params?: Record<string, string | number>) => string;
export interface LookPickerProps { caps: LooksCaps; choice: LookChoice; ctx: LookContext; planName: (id: string | null) => string | null; onChange: (c: LookChoice) => void }

/** Arrow keys walk the `[data-rove]` items of the group; Home and End jump. Choosing stays with Space / Enter (the items are buttons). */
function rove(e: React.KeyboardEvent<HTMLElement>) {
  const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
  if (!step && e.key !== "Home" && e.key !== "End") return;
  const els = Array.from(e.currentTarget.querySelectorAll<HTMLElement>("[data-rove]"));
  if (!els.length) return;
  e.preventDefault();
  const i = els.indexOf(document.activeElement as HTMLElement);
  (e.key === "Home" ? els[0] : e.key === "End" ? els[els.length - 1] : els[(i + step + els.length) % els.length])?.focus();
}

function Face({ m, size }: { m: CastMember; size: number }) {
  const [broken, setBroken] = useState(false);
  return m.thumbnail && !broken
    ? <img className="face-img" src={m.thumbnail} alt="" width={size} height={size} decoding="async" onError={() => setBroken(true)} />
    : <span className="face-img face-ph" aria-hidden="true">{m.name.slice(0, 1)}</span>;
}

/** The surface itself (no trigger): used by the pill below and drawn on its own in the tests. */
export function LookPanel({ caps, choice, ctx, planName, onChange, onDone, t }: LookPickerProps & { onDone: () => void; t: T }) {
  const list = tiles(caps, ctx);
  const chosen = optionOf(caps, choice.look) ?? list[0].option;
  const [tileFocus, setTileFocus] = useState(chosen.id);
  const [faceFocus, setFaceFocus] = useState<string>(Array.isArray(choice.cast) ? choice.cast[0] : "auto");
  const cast = chosen.cast ? caps.cast : null;
  const full = castFull(choice, caps);
  const picked = Array.isArray(choice.cast) ? choice.cast : [];
  const one = picked.length === 1 ? cast?.members.find((m) => m.id === picked[0]) : undefined;
  const castLine = !cast ? null : isConversation(choice, caps) ? cast.conversation?.note : one ? [one.role, one.topic].filter(Boolean).join(" · ") : cast.auto.note;
  const extras = chosen.extras.filter((x) => x.available);
  const pick = (id: string) => {
    const next = chooseLook(choice, id, caps, ctx);
    if (next !== choice) onChange(next);
    const o = optionOf(caps, next.look);
    if (next.look === id && o && !o.cast && !o.extras.some((x) => x.available)) onDone();   // nothing more to decide for this look: pick and go
  };
  return (
    <div className="look-panel">
      <div className="opts-head"><h2 className="h2" id="look-title">{t("create.pill_look")}</h2><button type="button" className="btn btn-tonal btn-sm" onClick={onDone}>{t("create.done")}</button></div>
      <div className="look-tiles" role="radiogroup" aria-labelledby="look-title" data-count={list.length} onKeyDown={rove}>
        {list.map(({ option: o, state }) => {
          const on = o.id === chosen.id, locked = state === "locked", plan = locked ? planName(o.requires_plan) : null;
          return (
            <button key={o.id} type="button" role="radio" data-rove data-look={o.id} aria-checked={on} aria-disabled={locked || undefined} tabIndex={o.id === tileFocus ? 0 : -1}
              className={`look-tile ${on ? "is-on" : ""} ${locked ? "is-locked" : ""}`} aria-describedby={o.note ? `look-note-${o.id}` : undefined}
              onFocus={() => setTileFocus(o.id)} onClick={() => { if (!locked) pick(o.id); }}>
              <span className="look-pic">
                {o.preview ? <img src={o.preview} alt="" decoding="async" /> : <span className={`look-ph look-ph-${o.id}`} aria-hidden="true" />}
                {on && <span className="look-check" aria-hidden="true"><Icon name="check" size={14} /></span>}
                {locked && <span className="look-lock"><Icon name="lock" size={14} />{plan && <span aria-hidden="true">{plan}</span>}<span className="sr-only-vmk">{plan ? t("create.plan_needs", { plan }) : t("create.plan_locked")}</span></span>}
              </span>
              <span className="look-name">{o.label}</span>
              {o.note && <span className="look-note" id={`look-note-${o.id}`}>{o.note}</span>}
            </button>
          );
        })}
      </div>
      {narrowed(caps, ctx) && <p className="look-line">{t(ctx.deck ? "create.pick_from_deck" : "create.pick_from_photos")}</p>}

      {cast && (
        <div className="look-cast" role="group" aria-label={t("create.pick_cast")} onKeyDown={rove}>
          <p className="label" aria-hidden="true">{t("create.pick_cast")}</p>
          <div className="cast-row">
            <button type="button" data-rove aria-pressed={picked.length === 0} tabIndex={faceFocus === "auto" ? 0 : -1} className={`face face-auto ${picked.length === 0 ? "is-on" : ""} ${(cast.auto.label || t("create.look_auto")).length > 7 ? "is-wide" : ""}`}
              onFocus={() => setFaceFocus("auto")} onClick={() => onChange(toggleCast(choice, "auto", caps))}>
              <span className="face-img face-ph"><Icon name="sparkle" size={22} /></span><span className="face-name">{cast.auto.label || t("create.look_auto")}</span>
            </button>
            {castGroups(cast).map((group, gi) => (
              <div key={gi} className="cast-group" role="presentation">
                {gi > 0 && <span className="cast-sep" aria-hidden="true" />}
                {group.map((m) => {
                  const on = picked.includes(m.id), dim = !on && full;
                  return (
                    <button key={m.id} type="button" data-rove data-face={m.id} aria-pressed={on} aria-disabled={dim || undefined} tabIndex={faceFocus === m.id ? 0 : -1} title={[m.role, m.topic].filter(Boolean).join(" · ") || undefined}
                      aria-label={[m.name, m.role].filter(Boolean).join(", ")} className={`face ${on ? "is-on" : ""} ${dim ? "is-dim" : ""}`}
                      onFocus={() => setFaceFocus(m.id)} onClick={() => { if (!dim) onChange(toggleCast(choice, m.id, caps)); }}>
                      <span className="face-wrap"><Face m={m} size={56} />{on && <span className="face-n" aria-hidden="true">{picked.indexOf(m.id) + 1}</span>}</span>
                      <span className="face-name">{m.name}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
          <p className="look-line" role="status">{castLine || " "}</p>
        </div>
      )}
      {extras.map((x) => (
        <label key={x.id} className="opt-row look-extra" htmlFor={`look-extra-${x.id}`}>
          <span><span className="look-extra-name">{x.label}</span>{x.note && <span className="look-extra-note" id={`look-extra-note-${x.id}`}>{x.note}</span>}</span>
          <input id={`look-extra-${x.id}`} type="checkbox" role="switch" className="vm-switch" aria-describedby={x.note ? `look-extra-note-${x.id}` : undefined} checked={choice.extras.includes(x.id)} onChange={() => onChange(toggleExtra(choice, x.id, caps))} />
        </label>
      ))}
    </div>
  );
}

/** The pill and its surface. The pill says the choice compactly: the look's name and the faces picked. */
export default function LookPicker(props: LookPickerProps) {
  const { caps, choice } = props;
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => { setOpen(false); btn.current?.focus(); }, []);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent | TouchEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("mousedown", down); document.addEventListener("touchstart", down); document.addEventListener("keydown", key, true);
    panel.current?.querySelector<HTMLElement>('[role="radio"][aria-checked="true"]')?.focus();
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("touchstart", down); document.removeEventListener("keydown", key, true); };
  }, [open, close]);
  // on a wide screen the surface opens under the card and may reach past the window, more so when Cartoon reveals its cast: bring it into view (a phone's sheet is fixed)
  useEffect(() => {
    if (!open) return;
    const still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    panel.current?.scrollIntoView?.({ block: "nearest", behavior: still ? "auto" : "smooth" });
  }, [open, choice.look]);
  const pill = pillOf(choice, caps);
  const thumb = optionOf(caps, choice.look)?.preview;
  const said = [pill.label, pill.names, ...choice.extras.flatMap((x) => optionOf(caps, choice.look)?.extras.find((e) => e.id === x)?.label ?? [])].filter(Boolean).join(", ");
  return (
    <div className="look-root" ref={root}>
      <button ref={btn} type="button" className="pill look-pill" aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} aria-label={t("create.pick_a11y", { look: said })} onClick={() => setOpen((v) => !v)}>
        {choice.look === "auto" && <span className="pill-k">{t("create.pill_look_k")}</span>}{/* a named look says what it is; "Auto" alone would not */}
        {thumb && <img className="look-pill-thumb" src={thumb} alt="" />}
        <span className="look-pill-v">{pill.label}</span>
        {pill.faces.length > 0 && <span className="look-pill-faces" aria-hidden="true">{pill.faces.map((m) => <Face key={m.id} m={m} size={22} />)}</span>}
        <Icon name="chevdown" size={16} />
      </button>
      {open && <div className="vm-pop-scrim" aria-hidden="true" onClick={close} />}
      {open && <div id={id} ref={panel} role="dialog" aria-label={t("create.pill_look")} className="vm-pop look-pop"><LookPanel {...props} onDone={close} t={t} /></div>}
    </div>
  );
}
