// Small accessible menus and popovers for the app (package B). Menu: a button that opens a list of choices (checkmark on the selected, arrow keys, Escape, click outside).
// Popover: a non-modal panel anchored to its trigger (the composer's Options); on a phone it becomes a bottom sheet. Tokens only (styles in styles/app.css, section B).
import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { ReactNode } from "react";
import { AIcon as Icon } from "./icons";

export interface MenuItem { id: string; label: ReactNode; detail?: ReactNode; checked?: boolean; disabled?: boolean; href?: string }

function useDismiss(open: boolean, close: () => void, root: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent | TouchEvent) => { if (root.current && !root.current.contains(e.target as Node)) close(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("mousedown", down); document.addEventListener("touchstart", down); document.addEventListener("keydown", key, true);
    return () => { document.removeEventListener("mousedown", down); document.removeEventListener("touchstart", down); document.removeEventListener("keydown", key, true); };
  }, [open, close, root]);
}

export function Menu({ label, trigger, items, onPick, align = "start", className = "", triggerClass = "" }: { label: string; trigger: ReactNode; items: MenuItem[]; onPick: (id: string) => void; align?: "start" | "end"; className?: string; triggerClass?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = useCallback(() => { setOpen(false); btn.current?.focus(); }, []);
  useDismiss(open, close, root);
  useEffect(() => { if (open) (list.current?.querySelector<HTMLElement>('[aria-checked="true"]:not([disabled]),[role^="menuitem"]:not([disabled])'))?.focus(); }, [open]);
  const move = (e: React.KeyboardEvent) => {
    const els = Array.from(list.current?.querySelectorAll<HTMLElement>('[role^="menuitem"]:not([disabled])') ?? []);
    const i = els.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") { e.preventDefault(); els[(i + 1) % els.length]?.focus(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); els[(i - 1 + els.length) % els.length]?.focus(); }
    else if (e.key === "Home") { e.preventDefault(); els[0]?.focus(); }
    else if (e.key === "End") { e.preventDefault(); els[els.length - 1]?.focus(); }
    else if (e.key === "Tab") setOpen(false);
  };
  const radio = items.some((i) => i.checked !== undefined);
  return (
    <div className={`vm-menu ${className}`} ref={root}>
      <button ref={btn} type="button" className={triggerClass} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} aria-label={label} onClick={() => setOpen((v) => !v)}>{trigger}</button>
      {open && (
        <div id={id} ref={list} role="menu" aria-label={label} className={`vm-menu-list vm-menu-${align}`} onKeyDown={move}>
          {items.map((it) => {
            const body = <>{radio && <span className="vm-menu-check" aria-hidden="true">{it.checked ? <Icon name="check" size={16} /> : null}</span>}<span className="vm-menu-label">{it.label}</span>{it.detail != null && <span className="vm-menu-detail">{it.detail}</span>}</>;
            const cls = `vm-menu-item ${it.disabled ? "is-dim" : ""}`;
            return it.href && !it.disabled
              ? <a key={it.id} role="menuitem" href={it.href} className={cls} onClick={() => setOpen(false)}>{body}</a>
              : <button key={it.id} type="button" role={radio ? "menuitemradio" : "menuitem"} aria-checked={radio ? !!it.checked : undefined} className={cls} aria-disabled={it.disabled || undefined} disabled={false}
                  onClick={() => { if (it.disabled) return; setOpen(false); btn.current?.focus(); onPick(it.id); }}>{body}</button>;
          })}
        </div>
      )}
    </div>
  );
}

export function Popover({ label, trigger, children, className = "", triggerClass = "", onOpenChange }: { label: string; trigger: ReactNode; children: (close: () => void) => ReactNode; className?: string; triggerClass?: string; onOpenChange?: (o: boolean) => void }) {
  const [open, setOpenRaw] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const id = useId();
  const setOpen = useCallback((o: boolean) => { setOpenRaw(o); onOpenChange?.(o); }, [onOpenChange]);
  const close = useCallback(() => { setOpen(false); btn.current?.focus(); }, [setOpen]);
  useDismiss(open, close, root);
  useEffect(() => { if (open) panel.current?.querySelector<HTMLElement>("button, [href], input, select")?.focus(); }, [open]);
  return (
    <div className={`vm-pop-root ${className}`} ref={root}>
      <button ref={btn} type="button" className={triggerClass} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} aria-label={label} onClick={() => setOpen(!open)}>{trigger}</button>
      {open && <div className="vm-pop-scrim" aria-hidden="true" />}
      {open && <div id={id} ref={panel} role="dialog" aria-label={label} className="vm-pop">{children(close)}</div>}
    </div>
  );
}

/** A segmented row of 2-4 choices (radio semantics). */
export function Segmented<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { id: T; label: string; disabled?: boolean; hint?: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="vm-seg" role="radiogroup" aria-label={label}>
      {options.map((o) => <button key={o.id} type="button" role="radio" aria-checked={value === o.id} aria-disabled={o.disabled || undefined} disabled={o.disabled} className="vm-seg-item" onClick={() => onChange(o.id)}>{o.label}{o.hint && <small>{o.hint}</small>}</button>)}
    </div>
  );
}
