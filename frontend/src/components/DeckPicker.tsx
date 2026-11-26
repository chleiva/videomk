// "Add a presentation" inside the Create sheet (docs/DECK_TO_VIDEO.md section 8): drop zone and button, upload with progress and cancel, processing, ready card, calm errors.
// The journey lives in useDeck (state machine in lib/deck.ts). The File is held in memory for a retry and dropped on reset or close: nothing about it is logged or stored.
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { Icon, Spinner, CostLine } from "./ui";
import { acceptAttr, checkFile, deckReducer, getDeck, pollDelayMs, pollExpired, problemFor, processDeck, requestSlot, uploadToSlot } from "../lib/deck";
import type { DeckCaps, DeckState } from "../lib/deck";
import { lengthLabel } from "../lib/create";
import { useLocale } from "../lib/useLocale";

export function useDeck(caps: DeckCaps | undefined) {
  const [state, dispatch] = useReducer(deckReducer, { k: "idle" } as DeckState);
  const file = useRef<File | null>(null);
  const run = useRef(0);                       // a new run (or a cancel) invalidates the older one's late answers
  const ctl = useRef<AbortController | null>(null);

  const stop = useCallback(() => { run.current++; ctl.current?.abort(); ctl.current = null; }, []);
  useEffect(() => () => { stop(); file.current = null; }, [stop]);

  const poll = useCallback(async (id: string, my: number, since: number) => {
    for (let attempt = 0; ; attempt++) {
      await new Promise((r) => setTimeout(r, pollDelayMs(attempt)));
      if (run.current !== my) return;
      if (pollExpired(since, Date.now())) { dispatch({ t: "waited_too_long" }); return; }
      const r = await getDeck(id);
      if (run.current !== my) return;
      if (!r.ok) { dispatch({ t: "failed", code: r.code, message: r.message }); return; }
      if (r.value.status === "ready") { dispatch({ t: "ready", info: { slides: r.value.slides, suggested_minutes: r.value.suggested_minutes, suggested_credits: r.value.suggested_credits } }); return; }
      if (r.value.status === "failed") { dispatch({ t: "failed", code: r.value.code, message: r.value.message }); return; }
    }
  }, []);

  const begin = useCallback(async (f: File) => {
    if (!caps) return;
    stop();
    const my = run.current;
    const c = checkFile(f, caps);
    if (!c.ok) { file.current = null; dispatch({ t: "rejected", code: c.problem, name: f.name }); return; }
    file.current = f;
    dispatch({ t: "pick", name: f.name, format: c.format });
    const slot = await requestSlot(c.format, f.size);
    if (run.current !== my) return;
    if (!slot.ok) { dispatch({ t: "failed", code: slot.code, message: slot.message }); return; }
    const abort = new AbortController(); ctl.current = abort;
    const up = await uploadToSlot(slot.value, f, (pct) => { if (run.current === my) dispatch({ t: "progress", pct }); }, abort.signal);
    if (run.current !== my) return;
    if (!up.ok) { dispatch({ t: "failed", code: up.code }); return; }
    const pr = await processDeck(slot.value.id);
    if (run.current !== my) return;
    if (!pr.ok) { dispatch({ t: "failed", code: pr.code, message: pr.message }); return; }
    dispatch({ t: "uploaded", id: slot.value.id, now: Date.now() });
    poll(slot.value.id, my, Date.now());
  }, [caps, poll, stop]);

  const cancel = useCallback(() => { stop(); file.current = null; dispatch({ t: "cancel" }); }, [stop]);
  const keepWaiting = useCallback((id: string) => { const my = ++run.current; const now = Date.now(); dispatch({ t: "resume", now }); poll(id, my, now); }, [poll]);
  /** Try again: with the file still in memory the whole journey restarts; without it, the person chooses again. */
  const retry = useCallback(() => { const f = file.current; if (f) begin(f); else dispatch({ t: "reset" }); }, [begin]);
  const reportError = useCallback((code: string, name?: string) => { stop(); file.current = null; dispatch({ t: "rejected", code, name }); }, [stop]);
  return { state, begin, cancel, keepWaiting, retry, reportError };
}

export default function DeckPicker({ caps, deck }: { caps: DeckCaps; deck: ReturnType<typeof useDeck> }) {
  const { t } = useLocale();
  const { state, begin, cancel, keepWaiting, retry } = deck;
  const input = useRef<HTMLInputElement>(null);
  const status = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const first = useRef(true);

  // The button that was pressed disappears with each step: move focus to the new state so a keyboard or screen reader user is never lost.
  useEffect(() => { if (first.current) { first.current = false; return; } if (state.k !== "uploading") status.current?.focus(); }, [state.k]);

  const choose = () => input.current?.click();
  const take = (files: FileList | null | undefined) => { const f = files?.[0]; if (f) begin(f); };
  const limits = caps.formats.length === 1 ? t(caps.formats[0] === "pdf" ? "deck.limits_pdf_only" : "deck.limits_pptx_only", { mb: caps.max_mb, slides: caps.max_slides }) : t("deck.limits", { mb: caps.max_mb, slides: caps.max_slides });
  const hidden = <input ref={input} type="file" hidden tabIndex={-1} accept={acceptAttr(caps)} onChange={(e) => { take(e.target.files); e.target.value = ""; }} />;

  const dropProps = {
    onDragEnter: (e: React.DragEvent) => { e.preventDefault(); depth.current++; setOver(true); },
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; },
    onDragLeave: () => { depth.current = Math.max(0, depth.current - 1); if (depth.current === 0) setOver(false); },
    onDrop: (e: React.DragEvent) => { e.preventDefault(); depth.current = 0; setOver(false); take(e.dataTransfer.files); },
  };

  if (state.k === "uploading") {
    return (
      <section className="deck" aria-label={t("deck.add_title")}>
        <div className="deck-card" ref={status} tabIndex={-1}>
          <div className="deck-file"><span className="deck-icon"><Icon name="slides" size={22} /></span><strong>{t("deck.uploading", { name: state.name })}</strong></div>
          <div className="deck-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={state.pct} aria-label={t("deck.progress", { pct: state.pct })} style={{ ["--p" as any]: `${state.pct}%` }}><i /></div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="muted" aria-live="off">{t("deck.progress", { pct: state.pct })}</span>
            <button type="button" className="btn btn-line btn-sm" onClick={cancel}>{t("deck.cancel")}</button>
          </div>
        </div>
      </section>
    );
  }
  if (state.k === "processing") {
    return (
      <section className="deck" aria-label={t("deck.add_title")}>
        <div className="deck-card" ref={status} tabIndex={-1} role="status">
          <div className="deck-file"><Spinner /><strong>{t("deck.processing_title")}</strong></div>
          <div className="deck-bar is-wait" aria-hidden="true"><i /></div>
          <p className="muted">{t("deck.processing_body")}</p>
          <div className="deck-actions"><button type="button" className="btn btn-line btn-sm" onClick={cancel}>{t("deck.cancel")}</button></div>
        </div>
      </section>
    );
  }
  if (state.k === "ready") {
    const len = lengthLabel(state.suggested_minutes);
    return (
      <section className="deck" aria-label={t("deck.add_title")}>
        <div className="deck-card" ref={status} tabIndex={-1} role="status">
          <div className="deck-file"><span className="deck-icon" style={{ color: "var(--success)", background: "var(--success-container)" }}><Icon name="check" size={22} /></span>
            <div className="min-w-0"><p className="eyebrow">{t("deck.ready_title")}</p><strong>{state.name}</strong></div></div>
          <p className="font-semibold">{t("deck.summary", { slides: t("deck.slides", { n: state.slides }), length: len })}</p>
          <CostLine credits={state.suggested_credits} />
          <p className="muted">{t("deck.promise")}</p>
          <div className="deck-actions">
            <button type="button" className="btn btn-line btn-sm" onClick={choose}>{t("deck.change_file")}</button>
            <button type="button" className="btn btn-line btn-sm" onClick={cancel}>{t("deck.remove")}</button>
          </div>
        </div>
        {hidden}
      </section>
    );
  }
  if (state.k === "error") {
    const p = problemFor(state.code, caps);
    // A code this version does not know: the server's own localized sentence is better than a generic one.
    const msg = p.key === "deck.err.network" && state.code !== "network" && state.serverMessage ? state.serverMessage : t(p.key, p.params);
    return (
      <section className="deck" aria-label={t("deck.add_title")}>
        <div className="deck-card" ref={status} tabIndex={-1}>
          <p className="notice notice-warn" role="alert"><span>{p.action === "choose_other" && <strong className="block">{t("deck.err.title")}</strong>}{msg}</span></p>
          <p className="caption">{t("create.nothing_charged")}</p>
          <div className="deck-actions">
            {p.action === "keep_waiting" && state.id && <button type="button" className="btn btn-primary btn-sm" onClick={() => keepWaiting(state.id!)}>{t("deck.act.keep_waiting")}</button>}
            {p.action === "retry" && <button type="button" className="btn btn-primary btn-sm" onClick={retry}>{t("deck.act.retry")}</button>}
            <button type="button" className={`btn btn-sm ${p.action === "choose_other" ? "btn-primary" : "btn-line"}`} onClick={choose}>{t("deck.act.choose_other")}</button>
          </div>
        </div>
        {hidden}
      </section>
    );
  }
  return (
    <section className="deck" aria-label={t("deck.add_title")}>
      <div className={`deck-drop ${over ? "is-over" : ""}`} {...dropProps} ref={status as any} tabIndex={-1} role="group" aria-label={t("deck.drop_label")} aria-describedby="deck-limits">
        <span className="deck-icon"><Icon name="slides" size={24} /></span>
        <p className="deck-title">{over ? t("deck.drop_release") : t("deck.add_title")}</p>
        <p className="muted">{t("deck.add_sub")}</p>
        <button type="button" className="btn btn-tonal btn-sm" onClick={choose}>{t("deck.choose")}</button>
        <p id="deck-limits" className="caption">{limits}</p>
      </div>
      {hidden}
    </section>
  );
}
