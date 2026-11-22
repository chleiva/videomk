import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SceneForm from "./SceneForm";
import { ApiError, SCENE_TYPES, diffOps, emptyScene, getPlan, postEdits, validateBeat, wordCount } from "../lib/editor";
import type { Beat, Meta, PlanView, SceneType } from "../lib/editor";

const btn = "rounded-xl px-4 py-2 text-sm font-semibold shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 disabled:cursor-not-allowed disabled:opacity-50";
const compact = "rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-pink-500";
const input = "w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-pink-500";
const TYPE_LABEL: Record<SceneType, string> = { title: "Title", bullets: "Bullets", diagram: "Diagram", chart: "Chart", timeline: "Timeline", stat: "Big number", quote: "Quote", image: "Photo" };

const metaOf = (p: PlanView): Meta => ({ title: p.title || "", theme: p.theme || "midnight", mood: p.mood || "calm", voice: p.voice || "" });
let refCounter = 0;

export default function Editor() {
  const videoId = useMemo(() => new URLSearchParams(location.search).get("id") || "", []);
  const [plan, setPlan] = useState<PlanView | null>(null);
  const [beats, setBeats] = useState<Beat[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [tab, setTab] = useState<"preview" | "final">("preview");
  const dirtyRef = useRef(false);

  const applyServer = useCallback((p: PlanView, resetLocal: boolean) => {
    setPlan(p);
    if (resetLocal) {
      setBeats(p.beats);
      setMeta(metaOf(p));
      setSel((s) => (s && p.beats.some((b) => b.id === s) ? s : p.beats[0]?.id ?? null));
    }
  }, []);

  const refresh = useCallback(async (resetLocal: boolean) => {
    try {
      applyServer(await getPlan(videoId), resetLocal);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't load the editor. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [applyServer, videoId]);

  useEffect(() => { if (videoId) refresh(true); else { setLoading(false); setError("No video selected."); } }, [refresh, videoId]);

  const rendering = plan?.edit_state === "RENDERING";
  useEffect(() => { // poll while a render runs; a finished render replaces the working copy (it now equals the saved plan)
    if (!rendering) return;
    const t = setInterval(() => refresh(false), 3000);
    return () => clearInterval(t);
  }, [rendering, refresh]);
  const wasRendering = useRef(false);
  useEffect(() => {
    if (wasRendering.current && !rendering) { refresh(true); dirtyRef.current = false; setTab(plan?.edit_mode === "final" ? "final" : "preview"); }
    wasRendering.current = rendering;
  }, [rendering]); // eslint-disable-line react-hooks/exhaustive-deps

  const ops = useMemo(() => (plan && meta ? diffOps(plan.beats, beats, metaOf(plan), meta) : []), [plan, beats, meta]);
  const hasChanges = ops.length > 0;
  useEffect(() => {
    dirtyRef.current = hasChanges;
    const warn = (e: BeforeUnloadEvent) => { if (dirtyRef.current) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasChanges]);

  const errors = useMemo(() => {
    const out: Record<string, string[]> = {};
    if (plan) for (const b of beats) { const e = validateBeat(b, plan.limits); if (e.length) out[b.id] = e; }
    return out;
  }, [beats, plan]);
  const blocked = Object.keys(errors).length > 0;

  const update = (id: string, patch: Partial<Beat>) => setBeats((bs) => bs.map((b) => (b.id === id ? { ...b, ...patch } : b)));
  const move = (id: string, d: -1 | 1) => setBeats((bs) => { const i = bs.findIndex((b) => b.id === id); const j = i + d; if (j < 0 || j >= bs.length) return bs; const c = bs.slice(); [c[i], c[j]] = [c[j], c[i]]; return c; });
  const remove = (id: string) => { if (beats.length <= 1) return; setBeats((bs) => bs.filter((b) => b.id !== id)); if (sel === id) setSel(beats.find((b) => b.id !== id)?.id ?? null); };
  const addAfter = (id: string | null) => {
    if (plan && beats.length >= plan.limits.max_beats) return;
    const ref = `n${++refCounter}`;
    const nb: Beat = { id: `new-${ref}`, ref, narration: "", scene: emptyScene("title") };
    setBeats((bs) => { const i = id === null ? -1 : bs.findIndex((b) => b.id === id); const c = bs.slice(); c.splice(i + 1, 0, nb); return c; });
    setSel(nb.id);
  };
  const changeType = (b: Beat, type: SceneType) => update(b.id, { scene: emptyScene(type, b.narration), pick: null });

  const submit = async (mode: "preview" | "final", withOps: boolean) => {
    if (!plan) return;
    setSubmitting(true); setError("");
    try {
      await postEdits(videoId, { base_rev: plan.rev, ops: withOps ? ops : [], mode });
      await refresh(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setError(`${e.message}${e.rev ? "" : ""}`);
      else setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      if (e instanceof ApiError && e.status === 409) await refresh(false);
    } finally { setSubmitting(false); }
  };

  if (loading) return <div className="mx-auto max-w-6xl px-6 py-16 text-neutral-500">Loading editor…</div>;
  if (!plan || !meta) return (
    <div className="mx-auto max-w-xl px-6 py-16 text-center">
      <p className="text-neutral-800" role="alert">{error || "Nothing to edit."}</p>
      <a href="/generations/index.html" className="mt-4 inline-block text-sm underline">Back to Generations</a>
    </div>
  );

  const current = beats.find((b) => b.id === sel) || null;
  const previewFresh = !!plan.preview.url && plan.preview.rev === plan.rev;
  const showUrl = tab === "preview" && plan.preview.url ? plan.preview.url : plan.final.url;
  const canPublish = !hasChanges && !rendering && plan.final.rev !== plan.rev;
  const stateLabel = rendering ? "Rendering…" : plan.edit_state === "FAILED" ? "Last render failed" : "Up to date";

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-center gap-3">
        <a href="/generations/index.html" className="text-sm text-neutral-600 hover:text-neutral-900">← Generations</a>
        <input aria-label="Video title" className={`${input} max-w-md font-semibold`} value={meta.title} maxLength={60} disabled={rendering} onChange={(e) => setMeta({ ...meta, title: e.target.value })} />
        <select aria-label="Look" className={compact} value={meta.theme} disabled={rendering} onChange={(e) => setMeta({ ...meta, theme: e.target.value })}>
          <option value="midnight">Midnight</option><option value="paper">Paper</option><option value="sunrise">Sunrise</option>
        </select>
        <select aria-label="Music mood" className={compact} value={meta.mood} disabled={rendering} onChange={(e) => setMeta({ ...meta, mood: e.target.value })}>
          <option value="calm">Calm music</option><option value="bright">Bright music</option><option value="tense">Tense music</option>
        </select>
        <span className="ml-auto text-xs text-neutral-500" aria-live="polite">Revision {plan.rev} · {stateLabel}</span>
      </div>

      {error && <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">{error}</p>}
      {plan.edit_state === "FAILED" && !error && <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">The last render didn't finish ({plan.edit_error || "error"}). Your published video is unchanged: adjust and try again.</p>}

      <div className="mt-5 grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)_380px]">
        {/* ---- beats */}
        <section aria-label="Scenes" className="space-y-2 lg:max-h-[80vh] lg:overflow-y-auto lg:pr-1">
          <ol className="space-y-2">
            {beats.map((b, i) => {
              const changed = !!b.ref || (plan.beats.find((s) => s.id === b.id) && ops.some((o) => o.id === b.id));
              return (
                <li key={b.id}>
                  <div className={`rounded-2xl border bg-white p-3 shadow-sm ${sel === b.id ? "border-pink-500 ring-2 ring-pink-500/40" : "border-neutral-200"}`}>
                    <button type="button" className="block w-full text-left focus:outline-none" onClick={() => setSel(b.id)} aria-current={sel === b.id}>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-semibold text-neutral-500">{i + 1}</span>
                        <span className="rounded-full bg-neutral-100 px-2 py-0.5 font-medium text-neutral-700">{TYPE_LABEL[b.scene.type]}</span>
                        {b.duration ? <span className="text-neutral-500">{b.duration.toFixed(0)}s</span> : null}
                        {changed && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">edited</span>}
                        {errors[b.id] && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-rose-800">needs attention</span>}
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm text-neutral-800">{b.narration || <em className="text-neutral-400">Write the narration…</em>}</p>
                    </button>
                    {sel === b.id && !rendering && (
                      <div className="mt-2 flex items-center gap-1 text-xs">
                        <button type="button" aria-label="Move up" className="rounded-lg border border-neutral-200 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40" disabled={i === 0} onClick={() => move(b.id, -1)}>↑</button>
                        <button type="button" aria-label="Move down" className="rounded-lg border border-neutral-200 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40" disabled={i === beats.length - 1} onClick={() => move(b.id, 1)}>↓</button>
                        <button type="button" className="rounded-lg border border-neutral-200 px-2 py-1 hover:bg-neutral-50" onClick={() => addAfter(b.id)}>+ Add scene after</button>
                        <button type="button" className="ml-auto rounded-lg border border-rose-200 px-2 py-1 text-rose-700 hover:bg-rose-50 disabled:opacity-40" disabled={beats.length <= 1} onClick={() => remove(b.id)}>Delete</button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {!rendering && <button type="button" className="w-full rounded-2xl border border-dashed border-neutral-300 py-3 text-sm text-neutral-600 hover:bg-white" onClick={() => addAfter(beats[beats.length - 1]?.id ?? null)}>+ Add a scene at the end</button>}
        </section>

        {/* ---- preview + actions */}
        <section aria-label="Preview" className="space-y-3">
          <div className="flex items-center gap-2 text-sm" role="tablist">
            <button role="tab" aria-selected={tab === "preview"} disabled={!plan.preview.url} className={`rounded-full px-3 py-1 ${tab === "preview" ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-700"} disabled:opacity-40`} onClick={() => setTab("preview")}>Preview{plan.preview.rev ? ` (r${plan.preview.rev})` : ""}</button>
            <button role="tab" aria-selected={tab === "final"} className={`rounded-full px-3 py-1 ${tab === "final" ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-700"}`} onClick={() => setTab("final")}>Published{plan.final.rev ? ` (r${plan.final.rev})` : ""}</button>
            {tab === "preview" && plan.preview.url && !previewFresh && <span className="text-xs text-amber-700">older than your latest edits</span>}
          </div>
          <div className="relative overflow-hidden rounded-2xl border border-neutral-200 bg-black" style={{ aspectRatio: "16 / 9" }}>
            {showUrl ? <video key={showUrl} src={showUrl} controls playsInline className="h-full w-full object-contain" /> : <div className="flex h-full items-center justify-center text-sm text-neutral-400">No video yet</div>}
            {rendering && <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-white" role="status"><span className="animate-pulse">Rendering your {plan.edit_mode === "final" ? "final video" : "preview"}…</span></div>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={`${btn} bg-neutral-900 text-white hover:brightness-110`} disabled={!hasChanges || blocked || rendering || submitting} onClick={() => submit("preview", true)}>
              {submitting ? "Starting…" : hasChanges ? `Preview ${ops.length} change${ops.length === 1 ? "" : "s"}` : "Preview changes"}
            </button>
            <button type="button" className={`${btn} bg-gradient-to-r from-blue-500 to-pink-500 text-white hover:brightness-110`} disabled={!canPublish || submitting} onClick={() => submit("final", false)} title={hasChanges ? "Preview your changes first" : undefined}>
              Publish this version
            </button>
            <button type="button" className={`${btn} border border-neutral-200 bg-white text-neutral-800 hover:bg-neutral-50`} disabled={!hasChanges || rendering} onClick={() => { setBeats(plan.beats); setMeta(metaOf(plan)); }}>Discard changes</button>
          </div>
          <p className="text-xs text-neutral-500">Previews are fast, lower-resolution drafts. Only scenes you changed are re-made; publishing renders the full-quality video and keeps earlier versions.</p>
          {blocked && <p className="text-xs text-rose-700" role="status">Fix the highlighted scenes to preview.</p>}
        </section>

        {/* ---- inspector */}
        <section aria-label="Scene settings" className="space-y-4 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm lg:max-h-[80vh] lg:overflow-y-auto">
          {!current ? <p className="text-sm text-neutral-500">Select a scene to edit it.</p> : (
            <fieldset disabled={rendering} className="space-y-4">
              <div>
                <label htmlFor="narr" className="mb-1 block text-xs font-medium text-neutral-600">Narration (what the voice says)</label>
                <textarea id="narr" rows={5} className={input} value={current.narration} onChange={(e) => update(current.id, { narration: e.target.value })} />
                <p className={`mt-1 text-xs ${errors[current.id]?.some((m) => m.startsWith("Narration")) ? "text-rose-700" : "text-neutral-500"}`}>
                  {wordCount(current.narration)} words · about {Math.max(1, Math.round(wordCount(current.narration) / 2.5))}s spoken ({plan.limits.min_words}–{plan.limits.max_words} words)
                </p>
              </div>
              <div>
                <label htmlFor="stype" className="mb-1 block text-xs font-medium text-neutral-600">Visual</label>
                <select id="stype" className={input} value={current.scene.type} onChange={(e) => changeType(current, e.target.value as SceneType)}>
                  {SCENE_TYPES.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
                </select>
              </div>
              <SceneForm beat={current} onChange={(props) => update(current.id, { scene: { ...current.scene, props } })} onPick={(key) => update(current.id, { pick: key })} />
              <div>
                <label htmlFor="chap" className="mb-1 block text-xs font-medium text-neutral-600">Chapter title (optional)</label>
                <input id="chap" className={input} maxLength={60} value={current.chapter || ""} placeholder="Starts a YouTube chapter at this scene" onChange={(e) => update(current.id, { chapter: e.target.value })} />
              </div>
              {errors[current.id] && <ul className="space-y-1 text-xs text-rose-700" role="alert">{errors[current.id].map((m) => <li key={m}>{m}</li>)}</ul>}
            </fieldset>
          )}
        </section>
      </div>
    </div>
  );
}
