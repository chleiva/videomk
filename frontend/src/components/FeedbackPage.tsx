// Feedback: one warm text box. Reachable from the menu ("Feedback") and, quietly, from the end of a video. No nagging: nothing ever asks for it.
import { useEffect, useRef, useState } from "react";
import { Icon, Spinner } from "./ui";
import { useLocale } from "../lib/useLocale";
import { KINDS, TEXT_MAX, TEXT_MIN, contextFrom, sendFeedback, textProblem } from "../lib/feedback";
import type { FeedbackFailure, Kind } from "../lib/feedback";

const ERROR_KEY: Record<FeedbackFailure, string> = { network: "feedback.error_network", error: "feedback.error_generic", rate: "feedback.error_rate", invalid: "feedback.error_invalid", auth: "api.session_expired" };

export default function FeedbackPage() {
  const { t } = useLocale();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<Kind | null>(null);
  const [state, setState] = useState<"edit" | "sending" | "done">("edit");
  const [failure, setFailure] = useState<FeedbackFailure | null>(null);
  const [touched, setTouched] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const thanks = useRef<HTMLDivElement>(null);
  const problem = textProblem(text);
  const chars = [...text].length;

  useEffect(() => { if (state === "done") thanks.current?.focus(); }, [state]);

  async function submit(e?: React.FormEvent) {
    e?.preventDefault();
    if (problem || state === "sending") { setTouched(true); area.current?.focus(); return; }
    setState("sending"); setFailure(null);
    const r = await sendFeedback({ text, kind, context: contextFrom(location.search) });
    if (r.ok) { setText(""); setKind(null); setTouched(false); setState("done"); return; }
    setFailure(r.failure); setState("edit");   // the typed text stays
  }

  if (state === "done") {
    return (
      <section className="page page-narrow">
        <div ref={thanks} tabIndex={-1} role="status" className="card mt-6 p-6 text-center" style={{ outline: "none" }}>
          <span className="mx-auto flex h-14 w-14 items-center justify-center" style={{ borderRadius: "var(--radius-pill)", color: "var(--success)", background: "var(--success-container)" }}><Icon name="check" size={28} /></span>
          <h1 className="h1 mt-4" style={{ fontSize: "var(--fs-title2)" }}>{t("feedback.thanks_title")}</h1>
          <p className="muted mt-2">{t("feedback.thanks_body")}</p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <a href="/generations/index.html" className="btn btn-primary">{t("feedback.back")}</a>
            <button type="button" className="btn btn-line" onClick={() => setState("edit")}>{t("feedback.another")}</button>
          </div>
        </div>
      </section>
    );
  }

  const short = touched && problem === "short";
  return (
    <section className="page page-narrow">
      <h1 className="h1">{t("feedback.title")}</h1>
      <p className="muted mt-2">{t("feedback.intro")}</p>
      <form className="mt-6" onSubmit={submit} noValidate>
        <fieldset className="border-0 p-0">
          <legend className="caption mb-2">{t("feedback.kind_label")}</legend>
          <div className="chips" role="group">
            {KINDS.map((k) => <button key={k} type="button" className="chip" aria-pressed={kind === k} onClick={() => setKind(kind === k ? null : k)}>{t(`feedback.kind.${k}`)}</button>)}
          </div>
        </fieldset>
        <label htmlFor="feedback-text" className="mt-5 block font-semibold">{t("feedback.text_label")}</label>
        <textarea
          id="feedback-text" ref={area} className="field mt-2" rows={6} maxLength={TEXT_MAX} value={text} placeholder={t("feedback.placeholder")} enterKeyHint="enter" autoComplete="off"
          aria-describedby="feedback-hint feedback-count" aria-invalid={short || undefined} disabled={state === "sending"}
          onChange={(e) => { setText(e.target.value); if (failure === "invalid") setFailure(null); }} onBlur={() => text && setTouched(true)}
        />
        <div className="mt-1 flex justify-between gap-3">
          <p id="feedback-hint" className={short ? "caption text-[color:var(--danger)]" : "caption"}>{short ? t("feedback.too_short", { min: TEXT_MIN }) : ""}</p>
          <p id="feedback-count" className="caption shrink-0" aria-live={chars >= TEXT_MAX ? "polite" : "off"}>{t("feedback.counter", { n: chars, max: TEXT_MAX })}</p>
        </div>
        {failure && (
          <div className="notice notice-bad mt-4" role="alert">
            <p>{t(ERROR_KEY[failure])}</p>
          </div>
        )}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button type="submit" className="btn btn-primary" disabled={state === "sending"} aria-disabled={!!problem || state === "sending"}>
            {state === "sending" ? <><Spinner />{t("feedback.sending")}</> : failure && failure !== "auth" ? t("feedback.retry") : t("feedback.send")}
          </button>
        </div>
        <p className="caption mt-6">{t("feedback.privacy")}</p>
      </form>
    </section>
  );
}
