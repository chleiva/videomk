import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import SceneForm from "./SceneForm";
import Player from "./Player";
import { PIcon } from "./PlayerIcons";
import { Spinner } from "./ui";
import { IconButton } from "./ui/IconButton";
import { ApiError, SCENE_TYPES, diffOps, emptyScene, getPlan, postEdits, validateBeat, wordCount } from "../lib/editor";
import type { Beat, Meta, PlanView, SceneType } from "../lib/editor";
import { useLocale } from "../lib/useLocale";

const btn = "btn btn-sm";
const compact = "field editor-select";
const input = "field";

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
  const past = useRef<{ beats: Beat[]; meta: Meta }[]>([]);
  const lastSnap = useRef<{ beats: Beat[]; meta: Meta } | null>(null);
  const [canUndo, setCanUndo] = useState(false);

  const applyServer = useCallback((p: PlanView, resetLocal: boolean) => {
    setPlan(p);
    if (resetLocal) {
      past.current = []; lastSnap.current = null; setCanUndo(false);
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

  useEffect(() => {   // one undo step per pause in editing (500 ms), so a sentence typed is one step, not one per letter
    if (!meta || !plan) return;
    const timer = setTimeout(() => {
      const prev = lastSnap.current;
      if (prev && (prev.beats !== beats || prev.meta !== meta)) { past.current.push(prev); if (past.current.length > 50) past.current.shift(); setCanUndo(true); }
      lastSnap.current = { beats, meta };
    }, 500);
    return () => clearTimeout(timer);
  }, [beats, meta, plan]);
  const undo = useCallback(() => {
    const prev = past.current.pop();
    if (!prev) return;
    lastSnap.current = prev; setBeats(prev.beats); setMeta(prev.meta); setCanUndo(past.current.length > 0);
  }, []);
  useEffect(() => {   // Cmd/Ctrl+Z outside a text field (inside one the browser undoes the typing)
    const key = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === "z" && !/^(input|textarea|select)$/i.test(el.tagName) && !el.isContentEditable) { e.preventDefault(); undo(); }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [undo]);

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

  if (loading) return <div className="editor-state" role="status"><Spinner />{t("editor.loading")}</div>;
  if (!plan || !meta) return (
    <div className="editor-state" role="alert">
      <p>{error || t("editor.nothing")}</p>
      <a href="/generations" className="btn btn-tonal">{t("editor.back_link")}</a>
    </div>
  );

  const current = beats.find((b) => b.id === sel) || null;
  const previewFresh = !!plan.preview.url && plan.preview.rev === plan.rev;
  const showUrl = tab === "preview" && plan.preview.url ? plan.preview.url : plan.final.url;
  const canPublish = !hasChanges && !rendering && plan.final.rev !== plan.rev;
  const stateLabel = rendering ? t("editor.state.rendering") : plan.edit_state === "FAILED" ? t("editor.state.failed") : t("editor.state.ok");

  return (
    <div className="editor">
      <header className="editor-top">
        <a href="/generations" className="icon-btn glass-btn" aria-label={t("editor.back_link")} title={t("editor.back_link")}><PIcon name="back" size={22} /></a>
        <input aria-label={t("editor.title_aria")} className="field editor-title" value={meta.title} maxLength={60} disabled={rendering} onChange={(e) => setMeta({ ...meta, title: e.target.value })} />
        <select aria-label={t("editor.look")} className={compact} value={meta.theme} disabled={rendering} onChange={(e) => setMeta({ ...meta, theme: e.target.value })}>
          <option value="midnight">{t("editor.theme.midnight")}</option><option value="paper">{t("editor.theme.paper")}</option><option value="sunrise">{t("editor.theme.sunrise")}</option>
        </select>
        <select aria-label={t("editor.mood")} className={compact} value={meta.mood} disabled={rendering} onChange={(e) => setMeta({ ...meta, mood: e.target.value })}>
          <option value="calm">{t("editor.mood.calm")}</option><option value="bright">{t("editor.mood.bright")}</option><option value="tense">{t("editor.mood.tense")}</option>
        </select>
        <IconButton label={t("editor.undo")} onClick={undo} disabled={!canUndo || rendering}><PIcon name="replay" size={20} /></IconButton>
        <span className={`badge ${rendering ? "badge-primary" : plan.edit_state === "FAILED" ? "badge-bad" : "badge-neutral"}`} aria-live="polite" title={t("editor.revision", { rev: plan.rev, state: stateLabel })}>{rendering && <Spinner />}{stateLabel}</span>
      </header>

      {error && <p role="alert" className="notice notice-bad mt-3">{error}</p>}
      {plan.edit_state === "FAILED" && !error && <p role="alert" className="notice notice-bad mt-3">{t("editor.render_failed", { reason: plan.edit_error || t("editor.reason_default") })}</p>}

      <div className="editor-grid">
        {/* ---- scenes */}
        <section aria-label={t("editor.scenes")} className="editor-scenes">
          <ol>
            {beats.map((b, i) => {
              const changed = !!b.ref || (plan.beats.find((s) => s.id === b.id) && ops.some((o) => o.id === b.id));
              return (
                <li key={b.id}>
                  <div className={`scene-card${sel === b.id ? " is-on" : ""}`}>
                    <button type="button" className="scene-main" onClick={() => setSel(b.id)} aria-current={sel === b.id}>
                      <span className="scene-top">
                        <span className="scene-n">{i + 1}</span>
                        <span className="badge badge-neutral">{typeLabel(b.scene.type)}</span>
                        {b.duration ? <span className="caption">{b.duration.toFixed(0)}s</span> : null}
                        {changed && <span className="badge badge-warn">{t("editor.edited")}</span>}
                        {errors[b.id] && <span className="badge badge-bad">{t("editor.needs_attention")}</span>}
                      </span>
                      <span className="scene-text">{b.narration || <em>{t("editor.write_narration")}</em>}</span>
                    </button>
                    {sel === b.id && !rendering && (
                      <div className="scene-tools">
                        <IconButton label={t("editor.move_up")} disabled={i === 0} onClick={() => move(b.id, -1)}><span aria-hidden="true">↑</span></IconButton>
                        <IconButton label={t("editor.move_down")} disabled={i === beats.length - 1} onClick={() => move(b.id, 1)}><span aria-hidden="true">↓</span></IconButton>
                        <IconButton label={t("editor.add_after")} onClick={() => addAfter(b.id)}><PIcon name="plus" size={20} /></IconButton>
                        <IconButton label={t("editor.delete")} className="tool-danger" disabled={beats.length <= 1} onClick={() => remove(b.id)}><PIcon name="close" size={20} /></IconButton>
                      </div>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
          {!rendering && <button type="button" className="btn btn-line btn-block add-end" onClick={() => addAfter(beats[beats.length - 1]?.id ?? null)}><PIcon name="plus" size={18} />{t("editor.add_end")}</button>}
        </section>

        {/* ---- preview and actions */}
        <section aria-label={t("editor.preview_section")} className="editor-preview">
          <div className="tabs" role="tablist">
            <button role="tab" className="tab" aria-selected={tab === "preview"} disabled={!plan.preview.url} onClick={() => setTab("preview")}>{plan.preview.rev ? t("editor.tab_preview_rev", { rev: plan.preview.rev }) : t("editor.tab_preview")}</button>
            <button role="tab" className="tab" aria-selected={tab === "final"} onClick={() => setTab("final")}>{plan.final.rev ? t("editor.tab_published_rev", { rev: plan.final.rev }) : t("editor.tab_published")}</button>
          </div>
          {tab === "preview" && plan.preview.url && !previewFresh && <p className="caption">{t("editor.older")}</p>}
          <div className="editor-video">
            {showUrl ? <Player key={showUrl} src={showUrl} title={meta.title || t("gen.untitled")} newVideoHref="/generations?create=1" /> : <div className="watch-state">{t("editor.no_video_yet")}</div>}
            {rendering && <div className="editor-rendering" role="status"><Spinner />{plan.edit_mode === "final" ? t("editor.rendering_final") : t("editor.rendering_preview")}</div>}
          </div>
          <div className="editor-actions">
            <button type="button" className={`${btn} btn-tonal`} disabled={!hasChanges || blocked || rendering || submitting} onClick={() => submit("preview", true)} title={t("editor.preview_note")}>
              {submitting ? t("editor.starting") : hasChanges ? t("editor.preview_changes", { count: ops.length }) : t("editor.preview_none")}
            </button>
            <button type="button" className={`${btn} btn-primary`} disabled={!canPublish || submitting} onClick={() => submit("final", false)} title={hasChanges ? t("editor.publish_hint") : undefined}>
              {t("editor.publish")}
            </button>
            <button type="button" className={`${btn} btn-line`} disabled={!hasChanges || rendering} onClick={() => { setBeats(plan.beats); setMeta(metaOf(plan)); }}>{t("editor.discard")}</button>
          </div>
          {blocked && <p className="hint-bad" role="status">{t("editor.fix_scenes")}</p>}
        </section>

        {/* ---- the selected scene */}
        <section aria-label={t("editor.scene_settings")} className="editor-inspector card">
          {!current ? <p className="muted">{t("editor.select_scene")}</p> : (
            <fieldset disabled={rendering} className="editor-fields">
              <div>
                <label htmlFor="narr" className="label">{t("editor.narration")}</label>
                <textarea id="narr" rows={5} className={input} value={current.narration} onChange={(e) => update(current.id, { narration: e.target.value })} />
                <p className={`hint ${narrationIssue(current) ? "hint-bad" : ""}`}>
                  {t("editor.words", { words: wordCount(current.narration), seconds: Math.max(1, Math.round(wordCount(current.narration) / 2.5)), min: plan.limits.min_words, max: plan.limits.max_words })}
                </p>
              </div>
              <div>
                <label htmlFor="stype" className="label">{t("editor.visual")}</label>
                <select id="stype" className={input} value={current.scene.type} onChange={(e) => changeType(current, e.target.value as SceneType)}>
                  {SCENE_TYPES.map((st) => <option key={st} value={st}>{typeLabel(st)}</option>)}
                </select>
              </div>
              <SceneForm beat={current} onChange={(props) => update(current.id, { scene: { ...current.scene, props } })} onPick={(key) => update(current.id, { pick: key })} />
              <div>
                <label htmlFor="chap" className="label">{t("editor.chapter")}</label>
                <input id="chap" className={input} maxLength={60} value={current.chapter || ""} placeholder={t("editor.chapter_hint")} onChange={(e) => update(current.id, { chapter: e.target.value })} />
              </div>
              {errors[current.id] && <ul className="hint-bad" role="alert">{errors[current.id].map((m) => <li key={m}>{m}</li>)}</ul>}
            </fieldset>
          )}
        </section>
      </div>
    </div>
  );
}
