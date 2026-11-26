import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SceneForm from "./SceneForm";
import { ApiError, SCENE_TYPES, diffOps, emptyScene, getPlan, postEdits, validateBeat, wordCount } from "../lib/editor";
import type { Beat, Meta, PlanView, SceneType } from "../lib/editor";
import { useLocale } from "../lib/useLocale";

const btn = "rounded-xl px-4 py-2 text-sm font-semibold shadow-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 disabled:cursor-not-allowed disabled:opacity-50";
const compact = "rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-pink-500";
const input = "w-full rounded-xl border border-neutral-200 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:ring-2 focus:ring-pink-500";

const metaOf = (p: PlanView): Meta => ({ title: p.title || "", theme: p.theme || "midnight", mood: p.mood || "calm", voice: p.voice || "" });
let refCounter = 0;

export default function Editor() {
  const { t, locale } = useLocale();
  const typeLabel = (type: SceneType) => t(`editor.scene_type.${type}`);
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
      setError(e instanceof ApiError ? e.message : t("editor.load_error"));
    } finally {
      setLoading(false);
    }
  }, [applyServer, videoId]);

  useEffect(() => { if (videoId) refresh(true); else { setLoading(false); setError(t("editor.no_video")); } }, [refresh, videoId]);

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
    if (plan) for (const b of beats) { const e = validateBeat(b, plan.limits, locale); if (e.length) out[b.id] = e; }
    return out;
  }, [beats, plan, locale]);
  const blocked = Object.keys(errors).length > 0;
  const narrationIssue = (b: Beat) => !!plan && (wordCount(b.narration) < plan.limits.min_words || wordCount(b.narration) > plan.limits.max_words);

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
      else setError(e instanceof ApiError ? e.message : t("editor.generic_error"));
      if (e instanceof ApiError && e.status === 409) await refresh(false);
    } finally { setSubmitting(false); }
  };

  if (loading) return <div className="mx-auto max-w-6xl px-6 py-16 text-neutral-500">{t("editor.loading")}</div>;
  if (!plan || !meta) return (
    <div className="mx-auto max-w-xl px-6 py-16 text-center">
      <p className="text-neutral-800" role="alert">{error || t("editor.nothing")}</p>
      <a href="/generations/index.html" className="mt-4 inline-block text-sm underline">{t("editor.back_link")}</a>
    </div>
  );

  const current = beats.find((b) => b.id === sel) || null;
  const previewFresh = !!plan.preview.url && plan.preview.rev === plan.rev;
  const showUrl = tab === "preview" && plan.preview.url ? plan.preview.url : plan.final.url;
  const canPublish = !hasChanges && !rendering && plan.final.rev !== plan.rev;
  const stateLabel = rendering ? t("editor.state.rendering") : plan.edit_state === "FAILED" ? t("editor.state.failed") : t("editor.state.ok");

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 md:px-6">
      <div className="flex flex-wrap items-center gap-3">
        <a href="/generations/index.html" className="text-sm text-neutral-600 hover:text-neutral-900">{t("editor.back")}</a>
        <input aria-label={t("editor.title_aria")} className={`${input} max-w-md font-semibold`} value={meta.title} maxLength={60} disabled={rendering} onChange={(e) => setMeta({ ...meta, title: e.target.value })} />
        <select aria-label={t("editor.look")} className={compact} value={meta.theme} disabled={rendering} onChange={(e) => setMeta({ ...meta, theme: e.target.value })}>
          <option value="midnight">{t("editor.theme.midnight")}</option><option value="paper">{t("editor.theme.paper")}</option><option value="sunrise">{t("editor.theme.sunrise")}</option>
        </select>
        <select aria-label={t("editor.mood")} className={compact} value={meta.mood} disabled={rendering} onChange={(e) => setMeta({ ...meta, mood: e.target.value })}>
          <option value="calm">{t("editor.mood.calm")}</option><option value="bright">{t("editor.mood.bright")}</option><option value="tense">{t("editor.mood.tense")}</option>
        </select>
        <span className="ml-auto text-xs text-neutral-500" aria-live="polite">{t("editor.revision", { rev: plan.rev, state: stateLabel })}</span>
      </div>

      {error && <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">{error}</p>}
      {plan.edit_state === "FAILED" && !error && <p role="alert" className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-800">{t("editor.render_failed", { reason: plan.edit_error || t("editor.reason_default") })}</p>}

      <div className="mt-5 grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)_380px]">
        {/* ---- beats */}
        <section aria-label={t("editor.scenes")} className="space-y-2 lg:max-h-[80vh] lg:overflow-y-auto lg:pr-1">
          <ol className="space-y-2">
            {beats.map((b, i) => {
              const changed = !!b.ref || (plan.beats.find((s) => s.id === b.id) && ops.some((o) => o.id === b.id));
              return (
                <li key={b.id}>
                  <div className={`rounded-2xl border bg-white p-3 shadow-sm ${sel === b.id ? "border-pink-500 ring-2 ring-pink-500/40" : "border-neutral-200"}`}>
                    <button type="button" className="block w-full text-left focus:outline-none" onClick={() => setSel(b.id)} aria-current={sel === b.id}>
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-semibold text-neutral-500">{i + 1}</span>
                        <span className="rounded-full bg-neutral-100 px-2 py-0.5 font-medium text-neutral-700">{typeLabel(b.scene.type)}</span>
                        {b.duration ? <span className="text-neutral-500">{b.duration.toFixed(0)}s</span> : null}
                        {changed && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">{t("editor.edited")}</span>}
                        {errors[b.id] && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-rose-800">{t("editor.needs_attention")}</span>}
                      </div>
                      <p className="mt-1 line-clamp-2 text-sm text-neutral-800">{b.narration || <em className="text-neutral-400">{t("editor.write_narration")}</em>}</p>
                    </button>
                    {sel === b.id && !rendering && (
                      <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
                        <button type="button" aria-label={t("editor.move_up")} className="rounded-lg border border-neutral-200 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40" disabled={i === 0} onClick={() => move(b.id, -1)}>↑</button>
                        <button type="button" aria-label={t("editor.move_down")} className="rounded-lg border border-neutral-200 px-2 py-1 hover:bg-neutral-50 disabled:opacity-40" disabled={i === beats.length - 1} onClick={() => move(b.id, 1)}>↓</button>
                        <button type="button" className="rounded-lg border border-neutral-200 px-2 py-1 hover:bg-neutral-50" onClick={() => addAfter(b.id)}>{t("editor.add_after")}</button>
                        <button type="button" className="ml-auto rounded-lg border border-rose-200 px-2 py-1 text-rose-700 hover:bg-rose-50 disabled:opacity-40" disabled={beats.length <= 1} onClick={() => remove(b.id)}>{t("editor.delete")}</button>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {!rendering && <button type="button" className="w-full rounded-2xl border border-dashed border-neutral-300 py-3 text-sm text-neutral-600 hover:bg-white" onClick={() => addAfter(beats[beats.length - 1]?.id ?? null)}>{t("editor.add_end")}</button>}
        </section>

        {/* ---- preview + actions */}
        <section aria-label={t("editor.preview_section")} className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-sm" role="tablist">
            <button role="tab" aria-selected={tab === "preview"} disabled={!plan.preview.url} className={`rounded-full px-3 py-1 ${tab === "preview" ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-700"} disabled:opacity-40`} onClick={() => setTab("preview")}>{plan.preview.rev ? t("editor.tab_preview_rev", { rev: plan.preview.rev }) : t("editor.tab_preview")}</button>
            <button role="tab" aria-selected={tab === "final"} className={`rounded-full px-3 py-1 ${tab === "final" ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-700"}`} onClick={() => setTab("final")}>{plan.final.rev ? t("editor.tab_published_rev", { rev: plan.final.rev }) : t("editor.tab_published")}</button>
            {tab === "preview" && plan.preview.url && !previewFresh && <span className="text-xs text-amber-700">{t("editor.older")}</span>}
          </div>
          <div className="relative overflow-hidden rounded-2xl border border-neutral-200 bg-black" style={{ aspectRatio: "16 / 9" }}>
            {showUrl ? <video key={showUrl} src={showUrl} controls playsInline className="h-full w-full object-contain" /> : <div className="flex h-full items-center justify-center text-sm text-neutral-400">{t("editor.no_video_yet")}</div>}
            {rendering && <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-white" role="status"><span className="animate-pulse">{plan.edit_mode === "final" ? t("editor.rendering_final") : t("editor.rendering_preview")}</span></div>}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={`${btn} bg-neutral-900 text-white hover:brightness-110`} disabled={!hasChanges || blocked || rendering || submitting} onClick={() => submit("preview", true)}>
              {submitting ? t("editor.starting") : hasChanges ? t("editor.preview_changes", { count: ops.length }) : t("editor.preview_none")}
            </button>
            <button type="button" className={`${btn} bg-gradient-to-r from-blue-500 to-pink-500 text-white hover:brightness-110`} disabled={!canPublish || submitting} onClick={() => submit("final", false)} title={hasChanges ? t("editor.publish_hint") : undefined}>
              {t("editor.publish")}
            </button>
            <button type="button" className={`${btn} border border-neutral-200 bg-white text-neutral-800 hover:bg-neutral-50`} disabled={!hasChanges || rendering} onClick={() => { setBeats(plan.beats); setMeta(metaOf(plan)); }}>{t("editor.discard")}</button>
          </div>
          <p className="text-xs text-neutral-500">{t("editor.preview_note")}</p>
          {blocked && <p className="text-xs text-rose-700" role="status">{t("editor.fix_scenes")}</p>}
        </section>

        {/* ---- inspector */}
        <section aria-label={t("editor.scene_settings")} className="space-y-4 rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm lg:max-h-[80vh] lg:overflow-y-auto">
          {!current ? <p className="text-sm text-neutral-500">{t("editor.select_scene")}</p> : (
            <fieldset disabled={rendering} className="space-y-4">
              <div>
                <label htmlFor="narr" className="mb-1 block text-xs font-medium text-neutral-600">{t("editor.narration")}</label>
                <textarea id="narr" rows={5} className={input} value={current.narration} onChange={(e) => update(current.id, { narration: e.target.value })} />
                <p className={`mt-1 text-xs ${narrationIssue(current) ? "text-rose-700" : "text-neutral-500"}`}>
                  {t("editor.words", { words: wordCount(current.narration), seconds: Math.max(1, Math.round(wordCount(current.narration) / 2.5)), min: plan.limits.min_words, max: plan.limits.max_words })}
                </p>
              </div>
              <div>
                <label htmlFor="stype" className="mb-1 block text-xs font-medium text-neutral-600">{t("editor.visual")}</label>
                <select id="stype" className={input} value={current.scene.type} onChange={(e) => changeType(current, e.target.value as SceneType)}>
                  {SCENE_TYPES.map((st) => <option key={st} value={st}>{typeLabel(st)}</option>)}
                </select>
              </div>
              <SceneForm beat={current} onChange={(props) => update(current.id, { scene: { ...current.scene, props } })} onPick={(key) => update(current.id, { pick: key })} />
              <div>
                <label htmlFor="chap" className="mb-1 block text-xs font-medium text-neutral-600">{t("editor.chapter")}</label>
                <input id="chap" className={input} maxLength={60} value={current.chapter || ""} placeholder={t("editor.chapter_hint")} onChange={(e) => update(current.id, { chapter: e.target.value })} />
              </div>
              {errors[current.id] && <ul className="space-y-1 text-xs text-rose-700" role="alert">{errors[current.id].map((m) => <li key={m}>{m}</li>)}</ul>}
            </fieldset>
          )}
        </section>
      </div>
    </div>
  );
}
