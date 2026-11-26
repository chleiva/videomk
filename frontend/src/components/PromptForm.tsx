import { useEffect, useMemo, useRef, useState } from "react";
import { startGeneration, newRequestId } from "../lib/api";
import { useLocale } from "../lib/useLocale";
import type { Locale } from "../lib/i18n";

const STORAGE_KEYS = {
  prompt: "videomk_prompt",
  taskId: "videomk_task_id",
};

export default function PromptForm({ locale: fixedLocale }: { locale?: Locale }) {
  const { t } = useLocale(fixedLocale);
  const [prompt, setPrompt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [firstAutofillDone, setFirstAutofillDone] = useState(false);
  const [hint, setHint] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef<{ text: string; id: string }>({ text: "", id: "" });

  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEYS.prompt);
    if (saved) setPrompt(saved);
  }, []);

  const canSubmit = useMemo(() => !isSubmitting, [isSubmitting]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    const trimmed = prompt.trim();


    if (trimmed.length > 0 && trimmed.length < 15) {
      setHint(t("prompt.more_detail"));
      inputRef.current?.focus();
      return;
    }

    setHint("");
    sessionStorage.setItem(STORAGE_KEYS.prompt, trimmed);
    setIsSubmitting(true);

    // Same prompt => same request id, so a retry after a flaky network can't start (or bill) twice.
    if (requestRef.current.text !== trimmed) requestRef.current = { text: trimmed, id: newRequestId() };
    try {
      const result = await startGeneration(trimmed, requestRef.current.id);
      if (!result.ok) {
        setIsSubmitting(false);
        setHint(result.message);
        inputRef.current?.focus();
        return;
      }
      sessionStorage.removeItem(STORAGE_KEYS.prompt);
      window.location.href = "/generations/index.html";
    } catch (err) {
      console.error(err);
      setIsSubmitting(false);
      setHint(t("prompt.start_error"));
      inputRef.current?.focus();
    }
  }

  const examples = ["create.example1", "create.example2", "create.example3"];
  return (
    <form onSubmit={handleSubmit} className="mx-auto w-full max-w-2xl text-left">
      <div className="composer">
        <label htmlFor="prompt" className="sr-only-vmk">{t("prompt.aria")}</label>
        <input
          id="prompt"
          ref={inputRef}
          type="text"
          inputMode="text"
          autoComplete="off"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={t("prompt.placeholder")}
          className="composer-input"
        />
        <button type="submit" disabled={isSubmitting} aria-busy={isSubmitting} className="btn btn-primary shrink-0">
          {isSubmitting ? (<><span aria-hidden className="spinner" /><span>{t("prompt.creating")}</span></>) : (<span>{t("prompt.create")}</span>)}
        </button>
      </div>
      <p className="hint mt-2 min-h-5 text-center" aria-live="polite">{hint}</p>
      <p className="eyebrow mt-4 text-center">{t("create.try_one")}</p>
      <div className="chips mt-3 justify-center">
        {examples.map((k) => <button key={k} type="button" className="chip" onClick={() => { setPrompt(t(k)); setHint(""); inputRef.current?.focus(); }}>{t(k)}</button>)}
      </div>
    </form>
  );
}
