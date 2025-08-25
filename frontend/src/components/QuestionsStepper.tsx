import { useEffect, useMemo, useState } from "react";
import { endpoints } from "../lib/config";
import { getTaskId } from "../lib/storage";

type QuestionOption = { id: string; label: string };
interface Question {
  id: string;
  question_text: string;
  options: QuestionOption[];
}

export default function QuestionsStepper() {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const current = questions[currentIndex];
  const progress = useMemo(() => {
    if (questions.length === 0) return "";
    return `Step ${currentIndex + 1} of ${questions.length}`;
  }, [currentIndex, questions.length]);

  useEffect(() => {
    const taskId = getTaskId();
    const url = endpoints.questions(taskId || undefined);
    fetch(url)
      .then((r) => r.json())
      .then((data: Question[]) => setQuestions(data))
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  function choose(optionId: string) {
    if (!current) return;
    setAnswers((prev) => ({ ...prev, [current.id]: optionId }));
  }

  function canNext() {
    if (!current) return false;
    return Boolean(answers[current.id]);
  }

  async function next() {
    if (!current) return;
    if (!canNext()) return;
    if (currentIndex < questions.length - 1) {
      setCurrentIndex((i) => i + 1);
      return;
    }
    // submit answers at the end
    try {
      setSubmitting(true);
      const taskId = getTaskId();
      const res = await fetch(endpoints.questions(taskId || undefined), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answers }),
      });
      if (!res.ok) throw new Error(`Failed to submit: ${res.status}`);
      window.location.href = "/generations/index.html";
    } catch (e) {
      console.error(e);
      alert("Could not submit your answers. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="text-neutral-500">Loading questions…</div>;
  }

  if (!current) {
    return <div className="text-neutral-500">No questions available.</div>;
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="mb-3 text-right text-sm text-neutral-500">{progress}</div>
      <div className="rounded-3xl border border-neutral-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-medium text-neutral-900">{current.question_text}</h2>
        <div className="mt-5 grid grid-cols-1 gap-3">
          {current.options.map((opt) => {
            const selected = answers[current.id] === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => choose(opt.id)}
                className={`rounded-2xl border px-4 py-4 text-left transition shadow-sm focus-visible:outline-none ${
                  selected
                    ? "border-black bg-black text-white"
                    : "border-neutral-200 bg-white hover:border-neutral-300"
                }`}
              >
                <span className="text-base">{opt.label}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-6 flex justify-end">
          <button
            type="button"
            onClick={next}
            disabled={!canNext() || submitting}
            className="inline-flex items-center justify-center rounded-2xl bg-black px-6 py-3 text-sm font-semibold text-white shadow transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          >
            {currentIndex < questions.length - 1 ? "Next" : submitting ? "Submitting…" : "Finish"}
          </button>
        </div>
      </div>
    </div>
  );
}
