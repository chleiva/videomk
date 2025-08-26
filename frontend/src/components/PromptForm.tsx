import { useEffect, useMemo, useRef, useState } from "react";
import { apiGateway } from "../lib/config";
import { getAuthorizationHeader } from "../lib/auth";

const STORAGE_KEYS = {
  prompt: "videomk_prompt",
  taskId: "videomk_task_id",
};

export default function PromptForm() {
  const [prompt, setPrompt] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [firstAutofillDone, setFirstAutofillDone] = useState(false);
  const [hint, setHint] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

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
      setHint("A bit more detail helps us create something great — add a few more words.");
      inputRef.current?.focus();
      return;
    }

    setHint("");
    sessionStorage.setItem(STORAGE_KEYS.prompt, trimmed);
    setIsSubmitting(true);

    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      if (!userId) {
        setIsSubmitting(false);
        alert("You must be signed in to create a video.");
        return;
      }
      const url = apiGateway.generateVideo(userId);
      const json = JSON.stringify({ prompt: trimmed });
      console.log("Submitting generation", { url, promptLength: trimmed.length });
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization },
        body: json,
        keepalive: true,
        mode: "cors",
        cache: "no-store",
      });
      console.log("Generation request response", res.status);
      // Navigate regardless
      window.location.href = "/generations/index.html";
    } catch (err) {
      console.error(err);
      setIsSubmitting(false);
      inputRef.current?.focus();
      alert("There was a problem starting your generation. Please try again.");
    }
  }

  return (
<form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto">


  <div className="flex items-center rounded-full border border-neutral-200 bg-white/90 px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-pink-500 focus-within:border-transparent transition">
    <input
      id="prompt"
      ref={inputRef}
      type="text"
      inputMode="text"
      aria-label="Prompt"
      value={prompt}
      onChange={(e) => setPrompt(e.target.value)}
      placeholder="Describe your idea, we’ll make the video."
      className="w-full bg-transparent px-4 py-3 text-lg md:text-xl outline-none placeholder:text-neutral-500"
    />
    <button
      type="submit"
      disabled={isSubmitting}
      aria-busy={isSubmitting}
      aria-disabled={isSubmitting}
      className="group btn-shimmer ml-2 shrink-0 relative overflow-hidden rounded-full bg-gradient-to-r from-blue-500 to-pink-500 px-6 py-3 text-white font-semibold shadow-md transition-all duration-200 ease-out hover:brightness-110 hover:shadow-lg active:scale-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 disabled:opacity-60 disabled:cursor-not-allowed disabled:shadow-none disabled:pointer-events-none"
    >
      <span className="relative z-10 flex items-center gap-2">
        {isSubmitting ? (
          <>
            <span
              aria-hidden
              className="inline-block h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin"
            />
            <span>Creating…</span>
          </>
        ) : (
          <span>Create</span>
        )}
      </span>
    </button>
  </div>

  {hint && (
    <p className="mt-2 text-sm text-neutral-600" aria-live="polite">
      {hint}
    </p>
  )}
</form>
  );
}
