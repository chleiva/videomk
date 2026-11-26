// The Create experience (same flow as the apps, docs/CREATE_API.md): describe it, pick what it is for and how long, see the price, then the request check
// (questions one at a time, or a kind "we can't make this"), then generate. Prompt first; every option has a default; the price is always visible.
import { useEffect, useMemo, useRef, useState } from "react";
import { Sheet, Icon, Spinner, CostLine } from "./ui";
import DeckPicker, { useDeck } from "./DeckPicker";
import { newRequestId, startGeneration, getWallet } from "../lib/api";
import type { Wallet } from "../lib/api";
import { FALLBACK_CAPS, buildOptions, checkRequest, creditsFor, defaultForm, fourKAdvice, getCapabilities, lengthLabel, loadSaved, normalize, overPlatformLimit, platformOf, resolutionOf, resolutionsFor, saveChoices, selectPlatform } from "../lib/create";
import type { Answer, Capabilities, Form, Question } from "../lib/create";
import { DECK_ASPECT, deckAspectWarning, deckCredits, deckGenerateExtras, deckMinutes } from "../lib/deck";
import { useLocale } from "../lib/useLocale";

const EXAMPLES = ["create.example1", "create.example2", "create.example3"];
type Stage =
  | { k: "form" }
  | { k: "checking" }
  | { k: "questions"; questions: Question[]; i: number; answers: Answer[] }
  | { k: "stop"; kind: "not_supported" | "blocked" | "paused"; message?: string; suggestion?: string };

export default function CreateSheet({ onClose, onCreated, initialText = "" }: { onClose: () => void; onCreated: () => void; initialText?: string }) {
  const { t, locale } = useLocale();
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [live, setLive] = useState(false);
  const [form, setForm] = useState<Form | null>(null);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [stage, setStage] = useState<Stage>({ k: "form" });
  const [hint, setHint] = useState<{ text: string; credits?: boolean } | null>(null);
  const [sending, setSending] = useState(false);
  const [more, setMore] = useState(false);
  const [why, setWhy] = useState(false);
  const [other, setOther] = useState("");
  const req = useRef<{ key: string; id: string }>({ key: "", id: "" });
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    getCapabilities().then((c) => { if (!alive) return; const cc = c ?? FALLBACK_CAPS; setLive(!!c); setCaps(cc); setForm({ ...defaultForm(cc, loadSaved()), text: initialText }); });
    getWallet().then((w) => alive && setWallet(w));
    return () => { alive = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const c = caps ?? FALLBACK_CAPS;
  const f = form;
  const set = (patch: Partial<Form>) => setForm((x) => (x ? normalize({ ...x, ...patch }, c) : x));
  const deck = useDeck(c.deck);
  const [picked, setPicked] = useState<number | null>(null);   // the length the person chose for a deck video (null: the deck's suggestion)
  const ready = deck.state.k === "ready" ? deck.state : null;
  const deckId = ready?.id;
  useEffect(() => { setPicked(null); if (deckId) setForm((x) => (x ? normalize({ ...x, aspect: DECK_ASPECT }, c) : x)); }, [deckId]); // eslint-disable-line react-hooks/exhaustive-deps
  const minutes = f ? (ready ? deckMinutes(ready, picked) : f.minutes) : 1;
  const busyDeck = deck.state.k === "uploading" || deck.state.k === "processing";
  const credits = f ? (ready ? deckCredits(ready, picked, f.resolution, c) : creditsFor(f.minutes, f.resolution, c)) : 1;
  const advice = f ? fourKAdvice(f, c) : null;
  const limit = f ? overPlatformLimit({ ...f, minutes }, c) : null;
  const res = f ? resolutionOf(c, f.resolution) : undefined;
  const platform = f ? platformOf(c, f.platform) : undefined;
  const short = f ? f.text.trim().length > 0 && f.text.trim().length < 15 : false;
  const enough = wallet ? wallet.unlimited || wallet.balance >= credits : true;

  async function generate(brief?: Record<string, string>) {
    if (!f) return;
    setSending(true); setHint(null); setStage({ k: "form" });
    const text = f.text.trim();
    // A deck video: the deck id, and a length only when the person chose one (absent: the deck's suggestion, charged exactly that).
    const { target_minutes: _len, ...rest } = buildOptions(f, c, live);
    const options = ready ? { ...rest, ...deckGenerateExtras(ready.id, picked) } : buildOptions(f, c, live);
    const key = JSON.stringify([text, options, brief ?? null]);
    if (req.current.key !== key) req.current = { key, id: newRequestId() }; // same request, same id: a retry cannot bill twice
    try {
      const r = await startGeneration(text, req.current.id, { ...options, ...(brief ? { brief } : {}) });
      if (!r.ok) {
        setSending(false);
        if (ready && r.kind === "invalid" && r.code?.startsWith("deck_") && r.code !== "deck_not_ready") { deck.reportError(r.code, ready.name); return; }
        if (r.kind === "blocked" || r.kind === "paused") setStage({ k: "stop", kind: r.kind, message: r.message });
        else setHint({ text: r.message, credits: r.kind === "credits" });
        return;
      }
      if (!ready) saveChoices(f);   // a deck video forces 16:9: that must not become the default for the next video
      onCreated();
    } catch (e) {
      console.error(e);
      setSending(false); setHint({ text: t("gen.start_error") });
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!f || sending || stage.k !== "form") return;
    const text = f.text.trim();
    if (busyDeck) return;
    if (ready) {
      if (!enough) { setHint({ text: t("create.not_enough", { needed: credits, balance: wallet?.balance ?? 0 }), credits: true }); return; }
      await generate();   // the prompt is optional with a deck, and the deck is checked on the server (no request check)
      return;
    }
    if (!text) { set({ text: t("gen.inspire_text") }); area.current?.focus(); return; }
    if (text.length < 15) { setHint({ text: t("gen.more_detail") }); area.current?.focus(); return; }
    if (!enough) { setHint({ text: t("create.not_enough", { needed: credits, balance: wallet?.balance ?? 0 }), credits: true }); return; }
    if (!live || c.intake === false) { await generate(); return; }
    setHint(null); setStage({ k: "checking" });
    const out = await checkRequest(text, buildOptions(f, c, live), []);
    followBrief(out, []);
  }

  function followBrief(out: Awaited<ReturnType<typeof checkRequest>>, answers: Answer[]) {
    if (out.status === "questions") { setOther(""); setStage({ k: "questions", questions: out.questions, i: 0, answers }); }
    else if (out.status === "ok") generate(out.brief);
    else setStage({ k: "stop", kind: out.status, message: out.message, suggestion: out.status === "not_supported" ? out.suggestion : undefined });
  }

  async function answer(a: Answer) {
    if (stage.k !== "questions" || !f) return;
    const answers = [...stage.answers, a];
    if (stage.i + 1 < stage.questions.length) { setOther(""); setStage({ ...stage, i: stage.i + 1, answers }); return; }
    await finish(answers);
  }
  async function finish(answers: Answer[]) {
    if (!f) return;
    setStage({ k: "checking" });
    const out = await checkRequest(f.text.trim(), buildOptions(f, c, live), answers);
    if (out.status === "ok") generate(out.brief); else if (out.status === "questions") generate(); else followBrief(out, answers); // asked enough: make it
  }

  const title = stage.k === "questions" ? t("create.questions_title") : stage.k === "stop" ? (stage.kind === "paused" ? t("create.paused_title") : t("create.cant_make_title")) : t("create.title");

  // ---------------------------------------------------------------- screens
  let body: React.ReactNode;
  if (!f || !caps) {
    body = <p className="mt-6 flex items-center gap-3 muted" role="status"><Spinner />{t("gen.loading")}</p>;
  } else if (stage.k === "checking") {
    body = (
      <div className="mt-6 space-y-3" role="status" aria-live="polite">
        <p className="flex items-center gap-3 font-semibold"><Spinner />{t("create.checking")}</p>
        <div className="space-y-2" aria-hidden="true">{[80, 60, 70].map((w) => <div key={w} className="h-3 rounded-full bg-surface3 animate-pulse" style={{ width: `${w}%` }} />)}</div>
      </div>
    );
  } else if (stage.k === "questions") {
    const q = stage.questions[stage.i];
    body = (
      <div className="mt-4">
        <p className="eyebrow">{t("create.question_n", { n: stage.i + 1, total: stage.questions.length })}</p>
        <p className="mt-2 text-[length:var(--fs-title3)] font-semibold leading-snug">{q.text}</p>
        <div className="chips mt-4">
          {q.options.map((o) => <button key={o.id} type="button" className="chip" onClick={() => answer({ id: q.id, option: o.id })}>{o.label}</button>)}
        </div>
        {q.allow_other && (
          <div className="mt-4 flex gap-2">
            <input className="field" aria-label={t("create.type_answer")} placeholder={t("create.type_answer")} maxLength={200} value={other} onChange={(e) => setOther(e.target.value)} />
            <button type="button" className="btn btn-tonal btn-sm shrink-0" disabled={!other.trim()} onClick={() => answer({ id: q.id, text: other.trim() })}>{t("create.use_this")}</button>
          </div>
        )}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-2">
          <button type="button" className="btn btn-line btn-sm" onClick={() => answer({ id: q.id, skip: true })}>{t("create.you_decide")}</button>
          <button type="button" className="btn btn-primary btn-sm" onClick={() => finish(stage.answers)}>{t("create.make_it_now")}</button>
        </div>
      </div>
    );
  } else if (stage.k === "stop") {
    body = (
      <div className="mt-4 space-y-4">
        <p className={`notice ${stage.kind === "paused" ? "notice-warn" : "notice-info"}`} role="alert">{stage.message || (stage.kind === "paused" ? t("create.paused_fallback") : stage.kind === "blocked" ? t("create.blocked_fallback") : t("create.unsupported_fallback"))}</p>
        {stage.suggestion && <p className="muted">{stage.suggestion}</p>}
        <p className="caption">{t("create.nothing_charged")}</p>
        {stage.kind !== "paused" && <button type="button" className="btn btn-primary btn-block" onClick={() => { setStage({ k: "form" }); setTimeout(() => area.current?.focus(), 20); }}>{t("create.edit_request")}</button>}
      </div>
    );
  } else {
    body = (
      <form onSubmit={submit} className="mt-4">
        <label htmlFor="create-text" className="sr-only-vmk">{ready ? t("deck.prompt_label") : t("create.title")}</label>
        <textarea id="create-text" ref={area} data-autofocus rows={4} className="field" value={f.text} maxLength={1500} onChange={(e) => { setHint(null); set({ text: e.target.value }); }} placeholder={ready ? t("deck.placeholder") : t("create.placeholder")} aria-describedby="create-hint" />
        <p id="create-hint" className={`hint ${short ? "" : ""}`} aria-live="polite">{hint ? <>{hint.text}{hint.credits && <> <a href="/wallet/index.html">{t("create.see_credits")}</a></>}</> : short ? t("gen.more_detail") : ""}</p>

        {c.deck && live && <DeckPicker caps={c.deck} deck={deck} />}

        {deck.state.k === "idle" && (
          <>
            <p className="eyebrow mt-4">{t("create.try_one")}</p>
            <div className="chips mt-2">
              {EXAMPLES.map((k) => <button key={k} type="button" className="chip" onClick={() => { setHint(null); set({ text: t(k) }); area.current?.focus(); }}>{t(k)}</button>)}
            </div>
          </>
        )}

        {c.platforms.length > 0 && (
          <>
            <p className="eyebrow mt-6" id="create-for">{t("create.for")}</p>
            <div className="chips mt-2" role="group" aria-labelledby="create-for">
              {c.platforms.map((p) => <button key={p.id} type="button" className="chip" aria-pressed={f.platform === p.id} onClick={() => setForm(selectPlatform(f, c, p.id))}>{p.label}</button>)}
            </div>
            {platform?.note && <p className="hint">{platform.note}</p>}
          </>
        )}

        <p className="eyebrow mt-6" id="create-len">{t("create.length")}</p>
        <div className="chips mt-2" role="group" aria-labelledby="create-len">
          {ready && <button type="button" className="chip" aria-pressed={picked === null} onClick={() => setPicked(null)}>{t("deck.suggested_chip", { length: lengthLabel(ready.suggested_minutes) })}</button>}
          {c.lengths.presets.filter((m) => !ready || m !== ready.suggested_minutes).map((m) => <button key={m} type="button" className="chip" aria-pressed={ready ? picked === m : f.minutes === m} onClick={() => (ready ? setPicked(m) : set({ minutes: m }))}>{lengthLabel(m)}</button>)}
        </div>
        {ready && <p className="hint">{t("deck.length_hint")}</p>}
        {limit != null && platform && <p className="hint">{t("create.max_length", { platform: platform.label, length: lengthLabel(limit) })}</p>}

        {live && (
          <>
            <button type="button" className="cost-link mt-4" aria-expanded={more} aria-controls="create-more" onClick={() => setMore((v) => !v)}>
              {more ? t("create.less_options") : t("create.more_options")}
            </button>
            {more && (
              <div id="create-more" className="mt-2 space-y-4 rounded-2xl bg-surface2 p-4">
                <div>
                  <p className="label" id="create-fmt">{t("create.format")}</p>
                  <div className="chips" role="group" aria-labelledby="create-fmt">
                    {c.aspects.filter((a) => a.ready).map((a) => <button key={a.id} type="button" className="chip" aria-pressed={f.aspect === a.id} onClick={() => set({ aspect: a.id })}>{a.label}{a.beta ? ` · ${t("create.beta")}` : ""}</button>)}
                  </div>
                </div>
                <div>
                  <p className="label" id="create-res">{t("create.resolution")}</p>
                  <div className="chips" role="group" aria-labelledby="create-res">
                    {resolutionsFor(c, f.aspect).map((r) => <button key={r.id} type="button" className="chip" aria-pressed={f.resolution === r.id} onClick={() => set({ resolution: r.id })}>{r.label}{r.credits_multiplier > 1 ? ` · ${t("create.multiplier", { n: r.credits_multiplier })}` : ""}</button>)}
                  </div>
                  {res?.note && <p className="hint">{res.note}</p>}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <label className="flex min-h-11 items-center gap-3 font-semibold" htmlFor="create-captions">
                    <input id="create-captions" type="checkbox" className="h-5 w-5 accent-[var(--primary)]" checked={f.captions} onChange={(e) => set({ captions: e.target.checked })} />{t("create.subtitles")}
                  </label>
                  {c.languages.length > 0 && (
                    <label className="flex w-full flex-wrap items-center gap-2 font-semibold sm:w-auto" htmlFor="create-lang">{t("create.narration")}
                      <select id="create-lang" className="field !w-auto min-w-0 max-w-full flex-1" value={f.language} onChange={(e) => set({ language: e.target.value })}>
                        <option value="auto">{t("create.same_language")}</option>
                        {c.languages.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
                      </select>
                    </label>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        <div className="mt-5 border-t border-line pt-4">
          <CostLine credits={credits} noteBad={!enough}
            note={wallet ? (wallet.unlimited ? t("wallet.unlimited_short") : enough ? t("create.left", { n: wallet.balance - credits }) : t("create.you_have", { n: wallet.balance })) : undefined}>
            <button type="button" className="cost-link" aria-expanded={why} aria-controls="create-why" onClick={() => setWhy((v) => !v)}>{t("create.cost_why")}</button>
          </CostLine>
          {ready && deckAspectWarning(f.aspect) && (
            <p className="notice notice-warn mt-2" role="status">
              <span>{t("deck.vertical_warn")}{" "}<button type="button" className="cost-link" onClick={() => set({ aspect: DECK_ASPECT })}>{t("deck.use_landscape")}</button></span>
            </p>
          )}
          {res && res.credits_multiplier > 1 && <p className="hint">{t("create.cost_4k_double")} {t("create.fourk_slower")}</p>}
          {advice && (
            <p className="notice notice-warn mt-2" role="status">
              <span>{advice}{" "}
                <button type="button" className="cost-link" onClick={() => set({ resolution: (resolutionsFor(c, f.aspect).find((r) => r.id === "1080p") ?? resolutionsFor(c, f.aspect).find((r) => r.credits_multiplier === 1))?.id ?? "1080p" })}>{t("create.use_instead", { res: (resolutionsFor(c, f.aspect).find((r) => r.id === "1080p") ?? resolutionsFor(c, f.aspect).find((r) => r.credits_multiplier === 1))?.label ?? "1080p" })}</button>
              </span>
            </p>
          )}
          {why && (
            <div id="create-why" className="mt-2 space-y-1 rounded-2xl bg-surface2 p-4 text-[length:var(--fs-subhead)]">
              <p className="font-semibold">{t("wallet.cost_title")}</p>
              <p>{t("wallet.cost_minute")}</p><p>{t("wallet.cost_example")}</p><p>{t("wallet.cost_4k")}</p><p>{t("wallet.cost_expiry")}</p>
            </div>
          )}
        </div>

        <button type="submit" className="btn btn-primary btn-block mt-4" disabled={sending || busyDeck} aria-busy={sending || busyDeck}>
          {sending ? <><Spinner /><span>{t("gen.starting")}</span></> : <><Icon name="bolt" size={18} /><span>{t("create.submit", { credits: t("create.credits", { n: credits }) })}</span></>}
        </button>
      </form>
    );
  }

  return <Sheet title={title} onClose={onClose}>{body}</Sheet>;
}
