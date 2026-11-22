import { useState } from "react";
import { bulletsToText, chartToText, diagramToText, textToBullets, textToChart, textToDiagram, textToTimeline, timelineToText } from "../lib/editor";
import type { Beat } from "../lib/editor";

const input = "w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-pink-500";
const label = "mb-1 block text-xs font-medium text-neutral-600";

function Field({ id, title, hint, children }: { id: string; title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className={label}>{title}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-neutral-500">{hint}</p>}
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
  const p = beat.scene.props;
  const set = (patch: Record<string, any>) => onChange({ ...p, ...patch });
  const k = `${beat.id}-${beat.scene.type}`; // remounts text areas when a different beat/scene is selected
  switch (beat.scene.type) {
    case "title":
      return (<div className="space-y-3"><Text id="f-title" title="Title" value={p.title || ""} max={70} onChange={(v) => set({ title: v })} /><Text id="f-sub" title="Subtitle (optional)" value={p.subtitle || ""} max={110} onChange={(v) => set({ subtitle: v })} /></div>);
    case "bullets":
      return (<div className="space-y-3"><Text id="f-head" title="Heading (optional)" value={p.heading || ""} max={50} onChange={(v) => set({ heading: v })} /><Lines key={k} id="f-items" title="Bullet points" hint="One per line, 2 to 5." initial={bulletsToText(p.items)} onText={(t) => set({ items: textToBullets(t) })} /></div>);
    case "diagram":
      return (<div className="space-y-3"><Text id="f-dt" title="Title (optional)" value={p.title || ""} max={50} onChange={(v) => set({ title: v })} /><Lines key={k} id="f-flow" title="Steps and arrows" hint={"One per line: “A -> B”, optionally “A -> B : label”. Chain with A -> B -> C. 2 to 8 steps."} initial={diagramToText(p)} onText={(t) => set(textToDiagram(t))} /></div>);
    case "chart":
      return (
        <div className="space-y-3">
          <Text id="f-ct" title="Title (optional)" value={p.title || ""} max={50} onChange={(v) => set({ title: v })} />
          <div className="grid grid-cols-2 gap-3">
            <Field id="f-kind" title="Type"><select id="f-kind" className={input} value={p.kind || "bar"} onChange={(e) => set({ kind: e.target.value })}><option value="bar">Bars</option><option value="line">Line</option></select></Field>
            <Text id="f-unit" title="Unit (optional)" value={p.unit || ""} max={6} hint="e.g. % or $" onChange={(v) => set({ unit: v })} />
          </div>
          <Lines key={k} id="f-data" title="Data" hint="One per line: “Label: number”. 2 to 8 points. Use only figures you can source." initial={chartToText(p)} onText={(t) => set(textToChart(t))} />
        </div>
      );
    case "timeline":
      return (<div className="space-y-3"><Text id="f-tt" title="Title (optional)" value={p.title || ""} max={50} onChange={(v) => set({ title: v })} /><Lines key={k} id="f-events" title="Events" hint="One per line: “date | what happened”. 2 to 6 events." initial={timelineToText(p.events)} onText={(t) => set({ events: textToTimeline(t) })} /></div>);
    case "stat":
      return (<div className="space-y-3"><Text id="f-val" title="Number" value={p.value || ""} max={12} hint="e.g. 73%, $4.2B, 1,200" onChange={(v) => set({ value: v })} /><Text id="f-lab" title="What it means" value={p.label || ""} max={70} onChange={(v) => set({ label: v })} /></div>);
    case "quote":
      return (<div className="space-y-3"><Field id="f-q" title="Quote"><textarea id="f-q" rows={3} maxLength={180} className={input} value={p.text || ""} onChange={(e) => set({ text: e.target.value })} /></Field><Text id="f-by" title="Who said it" value={p.attribution || ""} max={50} onChange={(v) => set({ attribution: v })} /></div>);
    case "image": {
      const cands = beat.candidates || [];
      return (
        <div className="space-y-3">
          <Text id="f-iq" title="Photo to search for" value={p.image_query || ""} max={80} hint="2 to 6 words, like a stock-photo search. Changing it finds new photos on the next preview." onChange={(v) => set({ image_query: v })} />
          {cands.length > 0 && (
            <fieldset>
              <legend className={label}>Choose a different photo</legend>
              <div className="grid grid-cols-2 gap-2">
                {cands.map((c) => {
                  const key = `${c.provider}:${c.id}`;
                  const active = (beat.pick || beat.photo?.chosen) === key;
                  return (
                    <button key={key} type="button" onClick={() => onPick(key)} aria-pressed={active} title={`${c.alt || "Photo"} by ${c.creator}`}
                      className={`group relative overflow-hidden rounded-xl border bg-neutral-100 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 ${active ? "border-pink-500 ring-2 ring-pink-500" : "border-neutral-200 hover:border-neutral-400"}`}>
                      <img src={c.thumb_url} alt={c.alt || "Candidate photo"} loading="lazy" className="aspect-video w-full object-cover" referrerPolicy="no-referrer" />
                      <span className="block truncate px-2 py-1 text-[11px] text-neutral-600">{c.creator} · {c.provider === "unsplash" ? "Unsplash" : c.license}</span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
          )}
          {cands.length === 0 && <p className="text-xs text-neutral-500">No alternatives yet. They appear after the next preview.</p>}
        </div>
      );
    }
  }
}
