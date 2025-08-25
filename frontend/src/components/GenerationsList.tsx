import { useEffect, useMemo, useRef, useState } from "react";
import { apiGateway, DEFAULT_USER_ID } from "../lib/config";

interface TaskItem {
  id: string;
  title?: string;
  status: "queued" | "running" | "complete" | "error";
  eta_seconds?: number | null;
  download_url?: string | null;
}

export default function GenerationsList() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);

  const hasTasks = useMemo(() => tasks.length > 0, [tasks]);

  const timerRef = useRef<number | undefined>(undefined);
  const delayRef = useRef<number>(30000);

  async function fetchTasks() {
    try {
      const res = await fetch(apiGateway.listVideos());
      if (!res.ok) throw new Error("Failed to fetch tasks");
      const data = (await res.json()) as { items?: any[] };
      const raw = Array.isArray(data.items) ? data.items : [];

      function s3ToHttps(uri: string | null | undefined): string | null {
        if (!uri || typeof uri !== "string") return null;
        const m = uri.match(/^s3:\/\/([^/]+)\/(.+)$/);
        if (!m) return uri;
        const [, bucket, key] = m;
        if (bucket === "videomk.com") return `https://videomk.com/${key}`;
        return `https://${bucket}.s3.amazonaws.com/${key}`;
      }

      const normalized: TaskItem[] = raw
        .map((it) => {
          const id: string | undefined = it?.video_id || it?.id;
          if (!id) return null;
          const statusStr: string = (it?.status || "").toString().toUpperCase();
          const statusMap: Record<string, TaskItem["status"]> = {
            STARTED_PROCESSING: "running",
            PLOT_CREATION: "running",
            ASSETS_CREATION: "running",
            STORYBOARD_CREATION: "running",
            RENDERING: "running",
            COMPLETE: "complete",
            ERROR: "error",
            FAILED: "error",
          };
          const status = statusMap[statusStr] || "queued";
          const download_url: string | null = s3ToHttps(it?.video_uri) || it?.download_url || null;
          const title: string | undefined = it?.title;
          const eta_seconds = typeof it?.eta_seconds === "number" ? it.eta_seconds : null;
          return { id, status, title, download_url, eta_seconds } as TaskItem;
        })
        .filter(Boolean) as TaskItem[];

      setTasks(normalized);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      const currentDelay = delayRef.current;
      timerRef.current = window.setTimeout(() => {
        delayRef.current = currentDelay + 30000;
        fetchTasks();
      }, currentDelay);
    }
  }

  useEffect(() => {
    fetchTasks();
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  function handleManualRefresh() {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    delayRef.current = 30000;
    setLoading(true);
    fetchTasks();
  }

  if (loading) {
    return <div className="text-neutral-500">Loading…</div>;
  }

  if (!hasTasks) {
    return (
      <div className="flex flex-col items-center justify-center rounded-3xl border border-dashed border-neutral-300 bg-white/60 p-12 text-center shadow-sm">
        <div className="mb-3 h-10 w-10 rounded-full border border-neutral-300" />
        <p className="text-neutral-600">No generations yet</p>
        <button
          onClick={handleManualRefresh}
          className="mt-4 inline-flex items-center justify-center rounded-xl border border-neutral-200 bg-white px-4 py-2 text-sm font-medium text-neutral-900 shadow-sm hover:border-neutral-300"
        >
          Refresh now
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <button
          onClick={handleManualRefresh}
          className="inline-flex items-center justify-center rounded-xl border border-neutral-200 bg-white px-4 py-2 text-sm font-medium text-neutral-900 shadow-sm hover:border-neutral-300"
        >
          Refresh now
        </button>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {tasks.map((t) => (
        <article key={t.id} className="rounded-3xl border border-neutral-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-medium text-neutral-900">{t.title || `Task ${t.id.slice(0, 6)}`}</h3>
            <StatusBadge status={t.status} />
          </div>
          <div className="mt-3 text-sm text-neutral-600">
            {t.status === "running" && (
              <span>Processing{typeof t.eta_seconds === "number" ? ` · ETA ${Math.max(0, t.eta_seconds)}s` : ""}</span>
            )}
            {t.status === "queued" && <span>Queued</span>}
            {t.status === "complete" && <span>Complete</span>}
            {t.status === "error" && <span>Error</span>}
          </div>
          <div className="mt-4 flex gap-3">
            {t.status === "complete" && (
              <>
                <a
                  href={`${apiGateway.getVideo(DEFAULT_USER_ID, t.id)}?redirect=1`}
                  title="View"
                  className="inline-flex items-center justify-center rounded-xl border border-neutral-200 bg-white px-2.5 py-1.5 text-sm text-neutral-900 shadow-sm hover:border-neutral-300"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" className="mr-1">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                  <span className="sr-only">View</span>
                </a>
                <a
                  href={`${apiGateway.getVideo(DEFAULT_USER_ID, t.id)}?download=1&redirect=1`}
                  title="Download"
                  className="inline-flex items-center justify-center rounded-xl border border-neutral-200 bg-white px-2.5 py-1.5 text-sm text-neutral-900 shadow-sm hover:border-neutral-300"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24" width="16" height="16" fill="currentColor" className="mr-1">
                    <path d="M12 3v10l4-4h-3V3h-2v6H7l5 4V3z" />
                    <path d="M5 19h14v2H5z" />
                  </svg>
                  <span className="sr-only">Download</span>
                </a>
              </>
            )}
          </div>
        </article>
      ))}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: TaskItem["status"] }) {
  const styles = {
    queued: "bg-neutral-100 text-neutral-700",
    running: "bg-amber-100 text-amber-800",
    complete: "bg-emerald-100 text-emerald-800",
    error: "bg-rose-100 text-rose-800",
  }[status];
  const label = {
    queued: "Queued",
    running: "Running",
    complete: "Complete",
    error: "Error",
  }[status];
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${styles}`}>{label}</span>;
}
