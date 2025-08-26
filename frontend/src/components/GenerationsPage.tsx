import { useMemo, useRef, useState } from "react";
import GenerationsList from "./GenerationsList";
import { apiGateway } from "../lib/config";
import { getAuthorizationHeader } from "../lib/auth";

export default function GenerationsPage() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [hint, setHint] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const inputRef = useRef<HTMLInputElement>(null);

  const canSubmit = useMemo(() => !submitting, [submitting]);

  function openModal() {
    setHint("");
    setIsModalOpen(true);
    setTimeout(() => inputRef.current?.focus(), 20);
  }
  function closeModal() {
    setIsModalOpen(false);
    setSubmitting(false);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    const trimmed = prompt.trim();
    if (trimmed.length === 0) {
      setPrompt("Just inspire me…");
      inputRef.current?.focus();
      return;
    }
    if (trimmed.length > 0 && trimmed.length < 15) {
      setHint("Add a bit more detail so we can create something great.");
      inputRef.current?.focus();
      return;
    }
    setHint("");
    setSubmitting(true);
    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      if (!userId) {
        setSubmitting(false);
        alert("You must be signed in to create a video.");
        return;
      }
      const url = apiGateway.generateVideo(userId);
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization },
        body: JSON.stringify({ prompt: trimmed }),
      });
      if (!res.ok) {
        throw new Error(`Request failed with ${res.status}`);
      }
      closeModal();
      setRefreshNonce((n) => n + 1);
    } catch (err) {
      console.error(err);
      setSubmitting(false);
      alert("There was a problem starting your generation. Please try again.");
    }
  }

  return (
    <section className="mx-auto max-w-6xl px-6 py-10 md:py-16">
      <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
        <div>
          <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">Generations</h1>
          <p className="mt-2 text-neutral-600">Monitor your renders and pick up where you left off.</p>
        </div>
        <div className="flex items-center gap-3">
          <div role="group" aria-label="Toggle view" className="hidden md:inline-flex rounded-xl border border-neutral-200 bg-white p-1 shadow-sm">
            <button
              type="button"
              onClick={() => setView("grid")}
              aria-pressed={view === "grid"}
              className={`rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 ${
                view === "grid" ? "bg-neutral-900 text-white" : "text-neutral-800 hover:bg-neutral-100"
              }`}
            >
              Grid
            </button>
            <button
              type="button"
              onClick={() => setView("list")}
              aria-pressed={view === "list"}
              className={`rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 ${
                view === "list" ? "bg-neutral-900 text-white" : "text-neutral-800 hover:bg-neutral-100"
              }`}
            >
              List
            </button>
          </div>
          <button
            onClick={openModal}
            className="group btn-shimmer relative overflow-hidden rounded-full bg-gradient-to-r from-blue-500 to-pink-500 px-5 py-3 text-white font-semibold shadow-md transition-all hover:brightness-110 hover:shadow-lg active:scale-95"
          >
            <span className="relative z-10 flex items-center gap-2">
              <svg aria-hidden viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                <path d="M12 5v14m-7-7h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Create video
            </span>
          </button>
        </div>
      </div>

      <div className="mt-8">
        <GenerationsList refreshNonce={refreshNonce} view={view} />
      </div>

      {isModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-end md:items-center justify-center p-0 md:p-6"
        >
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={closeModal} />
          <div className="relative w-full md:max-w-lg rounded-t-3xl md:rounded-2xl bg-white shadow-xl">
            <form onSubmit={handleCreate} className="p-6">
              <div className="flex items-start justify-between gap-4">
                <h2 className="text-lg font-semibold">Describe your video</h2>
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-full p-2 text-neutral-500 hover:text-neutral-800 hover:bg-neutral-100"
                  aria-label="Close"
                >
                  <svg aria-hidden viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                    <path d="M6.225 4.811 4.811 6.225 10.586 12l-5.775 5.775 1.414 1.414L12 13.414l5.775 5.775 1.414-1.414L13.414 12l5.775-5.775-1.414-1.414L12 10.586 6.225 4.811z"/>
                  </svg>
                </button>
              </div>
              <div className="mt-4">
                <input
                  ref={inputRef}
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  className="w-full rounded-xl border border-neutral-200 bg-white px-4 py-3 shadow-sm outline-none focus:ring-2 focus:ring-pink-500"
                  placeholder="A cinematic explainer about quantum computing for beginners"
                />
                {hint && <p className="mt-2 text-sm text-neutral-600" aria-live="polite">{hint}</p>}
              </div>
              <div className="mt-6 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-xl border border-neutral-200 bg-white px-4 py-2 text-sm font-medium text-neutral-900 shadow-sm hover:border-neutral-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  aria-busy={submitting}
                  className="group btn-shimmer relative overflow-hidden rounded-xl bg-neutral-900 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:brightness-110 hover:shadow-md disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  <span className="relative z-10 flex items-center gap-2">
                    {submitting ? (
                      <>
                        <span aria-hidden className="inline-block h-4 w-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                        <span>Starting…</span>
                      </>
                    ) : (
                      <>
                        <svg aria-hidden viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                          <path d="M8 5v14l11-7z" />
                        </svg>
                        <span>Create</span>
                      </>
                    )}
                  </span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </section>
  );
}


