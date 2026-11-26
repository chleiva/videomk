import { useState } from "react";
import { bulletsToText, chartToText, diagramToText, textToBullets, textToChart, textToDiagram, textToTimeline, timelineToText } from "../lib/editor";
import type { Beat } from "../lib/editor";
import { useLocale } from "../lib/useLocale";

const input = "field";
const label = "label";

function Field({ id, title, hint, children }: { id: string; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className={label}>{title}</label>
      {children}
      {hint && <p className="mt-1 text-sm text-fg2">{hint}</p>}
    </div>
  );
}

function Text({ id, title, value, onChange, max, hint }: { id: string; title: string; value: string; onChange: (v: string) => void; max?: number; hint?: string }) {
  return (
    <Field id={id} title={title} hint={hint}>
      <input id={id} className={input} value={value} maxLength={max} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}

/** A textarea whose text is parsed into props on every keystroke, but is NOT re-formatted while the user types. */
function Lines({ id, title, hint, initial, rows = 5, onText }: { id: string; title: string; hint: string; initial: string; rows?: number; onText: (t: string) => void }) {
  const [text, setText] = useState(initial);
  return (
    <Field id={id} title={title} hint={hint}>
      <textarea id={id} rows={rows} className={`${input} font-mono`} value={text} onChange={(e) => { setText(e.target.value); onText(e.target.value); }} />
    </Field>
  );
}

export default function SceneForm({ beat, onChange, onPick }: { beat: Beat; onChange: (props: Record<string, any>) => void; onPick: (key: string) => void }) {
  const { t } = useLocale();
  const p = beat.scene.props;
  const set = (patch: Record<string, any>) => onChange({ ...p, ...patch });
  const k = `${beat.id}-${beat.scene.type}`; // remounts text areas when a different beat/scene is selected
  switch (beat.scene.type) {
    case "title":
      return (<div className="space-y-3"><Text id="f-title" title={t("scene.title")} value={p.title || ""} max={70} onChange={(v) => set({ title: v })} /><Text id="f-sub" title={t("scene.subtitle")} value={p.subtitle || ""} max={110} onChange={(v) => set({ subtitle: v })} /></div>);
    case "bullets":
      return (<div className="space-y-3"><Text id="f-head" title={t("scene.heading")} value={p.heading || ""} max={50} onChange={(v) => set({ heading: v })} /><Lines key={k} id="f-items" title={t("scene.bullets")} hint={t("scene.bullets_hint")} initial={bulletsToText(p.items)} onText={(t) => set({ items: textToBullets(t) })} /></div>);
    case "diagram":
      return (<div className="space-y-3"><Text id="f-dt" title={t("scene.title_optional")} value={p.title || ""} max={50} onChange={(v) => set({ title: v })} /><Lines key={k} id="f-flow" title={t("scene.steps")} hint={t("scene.steps_hint")} initial={diagramToText(p)} onText={(t) => set(textToDiagram(t))} /></div>);
    case "chart":
      return (
        <div className="space-y-3">
          <Text id="f-ct" title={t("scene.title_optional")} value={p.title || ""} max={50} onChange={(v) => set({ title: v })} />
          <div className="grid grid-cols-2 gap-3">
            <Field id="f-kind" title={t("scene.kind")}><select id="f-kind" className={input} value={p.kind || "bar"} onChange={(e) => set({ kind: e.target.value })}><option value="bar">{t("scene.kind_bar")}</option><option value="line">{t("scene.kind_line")}</option></select></Field>
            <Text id="f-unit" title={t("scene.unit")} value={p.unit || ""} max={6} hint={t("scene.unit_hint")} onChange={(v) => set({ unit: v })} />
          </div>
          <Lines key={k} id="f-data" title={t("scene.data")} hint={t("scene.data_hint")} initial={chartToText(p)} onText={(t) => set(textToChart(t))} />
        </div>
      );
    case "timeline":
      return (<div className="space-y-3"><Text id="f-tt" title={t("scene.title_optional")} value={p.title || ""} max={50} onChange={(v) => set({ title: v })} /><Lines key={k} id="f-events" title={t("scene.events")} hint={t("scene.events_hint")} initial={timelineToText(p.events)} onText={(t) => set({ events: textToTimeline(t) })} /></div>);
    case "stat":
      return (<div className="space-y-3"><Text id="f-val" title={t("scene.number")} value={p.value || ""} max={12} hint={t("scene.number_hint")} onChange={(v) => set({ value: v })} /><Text id="f-lab" title={t("scene.meaning")} value={p.label || ""} max={70} onChange={(v) => set({ label: v })} /></div>);
    case "quote":
      return (<div className="space-y-3"><Field id="f-q" title={t("scene.quote")}><textarea id="f-q" rows={3} maxLength={180} className={input} value={p.text || ""} onChange={(e) => set({ text: e.target.value })} /></Field><Text id="f-by" title={t("scene.attribution")} value={p.attribution || ""} max={50} onChange={(v) => set({ attribution: v })} /></div>);
    case "image": {
      const cands = beat.candidates || [];
      return (
        <div className="space-y-3">
          <Text id="f-iq" title={t("scene.photo_query")} value={p.image_query || ""} max={80} hint={t("scene.photo_query_hint")} onChange={(v) => set({ image_query: v })} />
          {cands.length > 0 && (
            <fieldset>
              <legend className={label}>{t("scene.choose_photo")}</legend>
              <div className="grid grid-cols-2 gap-2">
                {cands.map((c) => {
                  const key = `${c.provider}:${c.id}`;
                  const active = (beat.pick || beat.photo?.chosen) === key;
                  return (
                    <button key={key} type="button" onClick={() => onPick(key)} aria-pressed={active} title={t("scene.photo_by", { alt: c.alt || t("scene.photo_default"), creator: c.creator })}
                      className={`group relative overflow-hidden rounded-xl border bg-surface2 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${active ? "border-primary ring-2 ring-primary" : "border-line hover:border-neutral-400"}`}>
                      <img src={c.thumb_url} alt={c.alt || t("scene.candidate_alt")} loading="lazy" className="aspect-video w-full object-cover" referrerPolicy="no-referrer" />
                      <span className="block truncate px-2 py-1 text-sm text-fg2">{c.creator} · {c.provider === "unsplash" ? "Unsplash" : c.license}</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
          )}
          {cands.length === 0 && <p className="text-sm text-fg2">{t("scene.no_alternatives")}</p>}
        </div>
      );
    }
  }
}
