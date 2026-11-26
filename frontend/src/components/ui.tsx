// Shared building blocks (styles live in src/styles/global.css, values in tokens.css): icons, sheet, toast, empty state, thumbnail, the making card.
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { makingInfo, minutesLeft, placeholderTone } from "../lib/videos";
import type { Stage } from "../lib/videos";
import { useLocale } from "../lib/useLocale";

const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" } as const;
const ICONS: Record<string, ReactNode> = {
  bolt: <path d="M13.5 2 5 13.5h5.5L9.5 22 19 9.5h-5.7z" fill="currentColor" stroke="none" />,
  plus: <path {...P} d="M12 5v14M5 12h14" />,
  close: <path {...P} d="m6 6 12 12M18 6 6 18" />,
  play: <path d="M8 5v14l11-7z" fill="currentColor" stroke="none" />,
  share: <path {...P} d="M12 15V3m0 0L7.5 7.5M12 3l4.5 4.5M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7" />,
  download: <path {...P} d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14" />,
  edit: <path {...P} d="M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4" />,
  check: <path {...P} d="m5 12.5 4.5 4.5L19 7.5" />,
  film: <path {...P} d="M4 5h16v14H4zM8 5v14M16 5v14M4 9.5h4M16 9.5h4M4 14.5h4M16 14.5h4" />,
  info: <path {...P} d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 8h.01" />,
  chevron: <path {...P} d="m9 6 6 6-6 6" />,
  dots: <path {...P} d="M5 12h.01M12 12h.01M19 12h.01" />,
  back: <path {...P} d="M15 6l-6 6 6 6" />,
  mic: <path {...P} d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zM6 11a6 6 0 0 0 12 0M12 17v4" />,
};
export function Icon({ name, size = 20, className }: { name: keyof typeof ICONS | string; size?: number; className?: string }) {
  return <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width={size} height={size} className={className}>{ICONS[name]}</svg>;
}

export function Spinner() { return <span aria-hidden="true" className="spinner" />; }

// ---------------------------------------------------------------- sheet (dialog): focus moves in, Tab stays inside, Escape and the scrim close it, the page stops scrolling
export function Sheet({ title, onClose, children, labelledBy = "sheet-title" }: { title: string; onClose: () => void; children: ReactNode; labelledBy?: string }) {
  const { t } = useLocale();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    const root = ref.current;
    const focusables = () => Array.from(root?.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),textarea,input,select,[tabindex]:not([tabindex="-1"])') ?? []).filter((e) => !e.hasAttribute("hidden"));
    (root?.querySelector<HTMLElement>("[data-autofocus]") ?? focusables()[0])?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
      if (e.key !== "Tab") return;
      const f = focusables(); if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", key);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = overflow; prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="sheet-root">
      <div className="sheet-scrim" onClick={onClose} />
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={labelledBy} className="sheet">
        <div className="sheet-head">
          <h2 id={labelledBy} className="h2" style={{ fontSize: "var(--fs-title2)" }}>{title}</h2>
          <button type="button" onClick={onClose} className="icon-btn" aria-label={t("gen.close")} style={{ marginTop: "-0.5rem", marginRight: "-0.5rem" }}><Icon name="close" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- toast
export function useToast() {
  const [msg, setMsg] = useState<ReactNode>(null);
  const timer = useRef<number | undefined>(undefined);
  const show = useCallback((m: ReactNode, ms = 5000) => { setMsg(m); window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setMsg(null), ms); }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const node = msg ? <div className="toast-host"><div className="toast" role="status" aria-live="polite">{msg}</div></div> : null;
  return { show, node };
}

// ---------------------------------------------------------------- empty state: art, headline, one sentence, one action
export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-art"><Icon name="film" size={36} /></div>
      <h2>{title}</h2>
      {body && <p>{body}</p>}
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- thumbnail: the preview when there is one, else a calm gradient with a play glyph (never a grey box)
export function Thumb({ id, src, duration, alt }: { id: string; src?: string | null; duration?: string | null; alt?: string }) {
  const [broken, setBroken] = useState(false);
  return (
    <div className="thumb">
      <div className={`thumb-ph h${placeholderTone(id)}`}><Icon name="play" size={28} /></div>
      {src && !broken && <img src={src} alt={alt ?? ""} loading="lazy" onError={() => setBroken(true)} />}
      {duration && <span className="duration">{duration}</span>}
    </div>
  );
}

// ---------------------------------------------------------------- the making card: ONE component for the list (compact) and the video screen (detail)
const STEPS = ["making.step.script", "making.step.voice", "making.step.pictures", "making.step.final_cut"];
export function MakingCard({ title, stage, etaSeconds, layout = "list", scene }: { title?: string; stage?: Stage; etaSeconds?: number | null; layout?: "list" | "detail"; scene?: { index: number; total: number } | null }) {
  const { t } = useLocale();
  const info = makingInfo(stage);
  const mins = minutesLeft(etaSeconds);
  const eta = mins === null ? null : mins <= 0 ? t("making.eta_under_minute") : t("making.eta_short", { n: mins });
  const stageLine = t(`making.line.${info.line}`);
  const detail = layout === "detail";
  return (
    <div className={`making ${detail ? "making-detail" : ""}`} role="group" aria-label={t("making.a11y", { title: title || t("gen.untitled"), stage: stageLine })}>
      <div className="making-top">
        <span className="glass-chip"><span className="live-dot" aria-hidden="true" />{t("making.chip")}</span>
        {eta && <span className="making-eta">{eta}</span>}
      </div>
      {!detail && <p className="making-title">{title || t("gen.untitled")}</p>}
      <p className="making-stage" role="status">{stageLine}</p>
      {scene && <p className="making-eta">{t("making.scene_counter", { index: scene.index, total: scene.total })}</p>}
      <p className="making-leave">{t("making.leave_promise")}</p>
      <div className="making-bar" aria-hidden="true">
        {STEPS.map((k, i) => (
          <div key={k}><i style={{ ["--p" as any]: `${Math.round(info.segments[i] * 100)}%` }} /><span style={{ fontWeight: i === info.current ? 700 : 400 }}>{t(k)}</span></div>
        ))}
      </div>
    </div>
  );
}
