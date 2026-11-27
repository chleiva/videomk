import { useRef } from "react";

export interface TabItem { id: string; label: string }
export interface TabsProps { items: readonly TabItem[]; value: string; onChange: (id: string) => void; /** Accessible name of the tab list. */ label: string }

/** Arrow keys, Home and End move between tabs (roving tabindex), like a native tablist. Pure, tested. */
export function nextTab(ids: readonly string[], current: string, key: string): string | null {
  const i = ids.indexOf(current);
  if (i < 0 || ids.length === 0) return null;
  if (key === "ArrowRight" || key === "ArrowDown") return ids[(i + 1) % ids.length];
  if (key === "ArrowLeft" || key === "ArrowUp") return ids[(i - 1 + ids.length) % ids.length];
  if (key === "Home") return ids[0];
  if (key === "End") return ids[ids.length - 1];
  return null;
}

/** Segmented tabs. The panel is the caller's: give it `role="tabpanel"` and `aria-labelledby={`tab-${id}`}`. */
export function Tabs({ items, value, onChange, label }: TabsProps) {
  const ref = useRef<HTMLDivElement>(null);
  const onKey = (e: React.KeyboardEvent) => {
    const next = nextTab(items.map((t) => t.id), value, e.key);
    if (!next) return;
    e.preventDefault();
    onChange(next);
    ref.current?.querySelector<HTMLElement>(`[data-tab="${next}"]`)?.focus();
  };
  return (
    <div ref={ref} className="tabs" role="tablist" aria-label={label} onKeyDown={onKey}>
      {items.map((t) => (
        <button key={t.id} id={`tab-${t.id}`} data-tab={t.id} type="button" role="tab" className="tab" aria-selected={t.id === value} tabIndex={t.id === value ? 0 : -1} onClick={() => onChange(t.id)}>{t.label}</button>
      ))}
    </div>
  );
}
