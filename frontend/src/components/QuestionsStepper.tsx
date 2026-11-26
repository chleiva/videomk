import { useEffect, useMemo, useState } from "react";
import { endpoints } from "../lib/config";
import { getTaskId } from "../lib/storage";
import { useLocale } from "../lib/useLocale";

type QuestionOption = { id: string; label: string };
interface Question {
  id: string;
  question_text: string;
  options: QuestionOption[];
}

export default function QuestionsStepper() {
  const { t } = useLocale();
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  const current = questions[currentIndex];
  const progress = useMemo(() => {
    if (questions.length === 0) return "";
    return t("questions.step", { current: currentIndex + 1, total: questions.length });
  }, [currentIndex, questions.length, t]);

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
      alert(t("questions.submit_error"));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="text-fg2">{t("questions.loading")}</div>;
  }

  if (!current) {
    return <div className="text-fg2">{t("questions.none")}</div>;
  }

  return (
    <div className="mx-auto w-full max-w-2xl">
      <div className="mb-3 text-right text-sm text-fg2">{progress}</div>
      <div className="card p-6 ">
        <h2 className="text-lg font-medium text-fg">{current.question_text}</h2>
        <div className="mt-5 grid grid-cols-1 gap-3">
          {current.options.map((opt) => {
            const selected = answers[current.id] === opt.id;
            return (
              <button
                key={opt.id}
                type="button"
                onClick={() => choose(opt.id)}
                className={`chip w-full !rounded-2xl !py-4 ${
                  selected
                    ? "is-on"
                    : "hover:bg-surface2"
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
            className="btn btn-primary"
          >
            {currentIndex < questions.length - 1 ? t("questions.next") : submitting ? t("questions.submitting") : t("questions.finish")}
          </button>
        </div>
      </div>
    </div>
  );
}
