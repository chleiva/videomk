import { useEffect, useMemo, useRef, useState } from "react";
import { apiGateway } from "../lib/config";
import { getAuthorizationHeader, handleAuthCodeIfPresent } from "../lib/auth";

interface TaskItem {
  id: string;
  title?: string;
  status: "queued" | "running" | "complete" | "error";
  eta_seconds?: number | null;
  created_at?: string | null;
  download_url?: string | null;
  preview_gif_url?: string | null;
  duration_s?: number | null;
  video_url?: string | null;
}

export default function GenerationsList({ refreshNonce = 0, view = "grid" }: { refreshNonce?: number; view?: "grid" | "list" }) {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);

  const hasTasks = useMemo(() => tasks.length > 0, [tasks]);

  const timerRef = useRef<number | undefined>(undefined);
  const delayRef = useRef<number>(30000);

  function saveCache(items: TaskItem[]) {
    try {
      sessionStorage.setItem("vmk_tasks", JSON.stringify(items));
    } catch {}
  }

  function loadCache(): TaskItem[] | null {
    try {
      const raw = sessionStorage.getItem("vmk_tasks");
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? (parsed as TaskItem[]) : null;
    } catch {
      return null;
    }
  }

  function mergeTasks(current: TaskItem[], incoming: TaskItem[]): TaskItem[] {
    const byId = new Map(current.map((t) => [t.id, t] as const));
    for (const it of incoming) {
      const existing = byId.get(it.id);
      if (existing) {
        byId.set(it.id, { ...existing, ...it });
      } else {
        byId.set(it.id, it);
      }
    }
    const merged = Array.from(byId.values());
    merged.sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return tb - ta;
    });
    return merged;
  }

  async function fetchTasks() {
    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      setUserId(userId);
      const endpoint = apiGateway.listVideos(userId || "");
      const res = await fetch(endpoint, { headers: { Authorization } });
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
          const preview_gif_url: string | null = (it?.preview_gif_url as string | null) || s3ToHttps(it?.preview_gif_uri) || null;
          const title: string | undefined = it?.title;
          const created_at: string | null = typeof it?.created_at === "string" ? it.created_at : null;
          const eta_seconds = typeof it?.eta_seconds === "number" ? it.eta_seconds : null;
          const duration_s: number | null = typeof it?.duration_s === "number" ? it.duration_s : null;
          const video_url: string | null = typeof it?.video_url === "string" ? it.video_url : null;
          return { id, status, title, download_url, eta_seconds, preview_gif_url, created_at, duration_s, video_url } as TaskItem;
        })
        .filter(Boolean) as TaskItem[];

      setTasks((prev) => {
        const merged = mergeTasks(prev, normalized);
        saveCache(merged);
        return merged;
      });
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
    (async () => {
      const hasCode = typeof window !== "undefined" && new URL(window.location.href).searchParams.has("code");
      if (hasCode) {
        try {
          await handleAuthCodeIfPresent();
        } catch (e) {
          // Swallow; if exchange fails, guard will re-initiate login later
        }
      }
      // Prime UI with cached items while fetching new ones
      const cached = loadCache();
      if (cached && cached.length > 0) {
        setTasks(cached);
        setLoading(false);
      }
      fetchTasks();
    })();
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

  // Parent-triggered refresh (e.g., right after starting a new generation)
  useEffect(() => {
    if (refreshNonce > 0) {
      handleManualRefresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshNonce]);

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

  function timeAgo(iso: string | null | undefined): string | null {
    if (!iso) return null;
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return null;
    const now = Date.now();
    const diffMs = Math.max(0, now - then);
    const sec = Math.floor(diffMs / 1000);
    if (sec < 45) return "just now";
    const min = Math.floor(sec / 60);
    if (min < 60) return min === 1 ? "1 min ago" : `${min} mins ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return hr === 1 ? "1 h ago" : `${hr} h ago`;
    const day = Math.floor(hr / 24);
    if (day < 30) return day === 1 ? "1 day ago" : `${day} days ago`;
    const mon = Math.floor(day / 30);
    if (mon < 12) return mon === 1 ? "1 month ago" : `${mon} months ago`;
    const yr = Math.floor(mon / 12);
    return yr === 1 ? "1 year ago" : `${yr} years ago`;
  }

  function formatDuration(s?: number | null): string | null {
    if (!s || s <= 0) return null;
    const minutes = Math.floor(s / 60);
    const seconds = Math.floor(s % 60);
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  }

  return (
    <div>
      {/* Removed manual refresh button to reduce UI clutter */}

      {view === "grid" ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {tasks.map((t) => {
            const durationLabel = formatDuration(t.duration_s);
            return (
              <article key={t.id} className="rounded-3xl border border-neutral-200 bg-white p-4 shadow-sm">
                <a
                  href={`/watch/index.html?id=${encodeURIComponent(t.id)}`}
                  onClick={() => {
                    const playUrl = t.video_url || t.download_url;
                    if (playUrl && playUrl.startsWith("http")) {
                      try { sessionStorage.setItem(`vmk_play_url_${t.id}`, playUrl); } catch {}
                    }
                  }}
                  aria-label={`Watch ${t.title || "Untitled"}${durationLabel ? `, duration ${durationLabel}` : ""}`}
                  className="group block focus:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 rounded-2xl"
                >
                  <div className="ratio-16x9 relative overflow-hidden rounded-xl border border-neutral-200 bg-neutral-50">
                    <div className="absolute inset-0 bg-gradient-to-br from-neutral-100 to-neutral-200" />
                    {t.preview_gif_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={t.preview_gif_url}
                        alt="Preview"
                        className="ratio-media h-full w-full object-cover opacity-100 transition-opacity duration-200 ease-out"
                        loading="lazy"
                        onError={(e) => {
                          const el = e.currentTarget as HTMLImageElement;
                          el.style.display = "none";
                        }}
                      />
                    )}
                    {durationLabel && (
                      <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs font-medium text-white">
                        {durationLabel}
                      </span>
                    )}
                  </div>
                  <div className="mt-3 flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-base font-medium text-neutral-900 line-clamp-2">{t.title || "Untitled"}</h3>
                      <p className="mt-0.5 text-xs text-neutral-500">{timeAgo(t.created_at)}</p>
                    </div>
                    <StatusBadge status={t.status} />
                  </div>
                </a>
              </article>
            );
          })}
        </div>
      ) : (
        <div role="list" className="space-y-4">
          {tasks.map((t) => {
            const durationLabel = formatDuration(t.duration_s);
            return (
              <article key={t.id} role="listitem" className="rounded-3xl border border-neutral-200 bg-white p-4 shadow-sm">
                <a
                  href={`/watch/index.html?id=${encodeURIComponent(t.id)}`}
                  onClick={() => {
                    const playUrl = t.video_url || t.download_url;
                    if (playUrl && playUrl.startsWith("http")) {
                      try { sessionStorage.setItem(`vmk_play_url_${t.id}`, playUrl); } catch {}
                    }
                  }}
                  aria-label={`Watch ${t.title || "Untitled"}${durationLabel ? `, duration ${durationLabel}` : ""}`}
                  className="group flex gap-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-pink-500 rounded-2xl"
                >
                  <div className="ratio-16x9 relative w-48 shrink-0 overflow-hidden rounded-xl border border-neutral-200 bg-neutral-50">
                    <div className="absolute inset-0 bg-gradient-to-br from-neutral-100 to-neutral-200" />
                    {t.preview_gif_url && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={t.preview_gif_url}
                        alt="Preview"
                        className="ratio-media h-full w-full object-cover opacity-100 transition-opacity duration-200 ease-out"
                        loading="lazy"
                        onError={(e) => {
                          const el = e.currentTarget as HTMLImageElement;
                          el.style.display = "none";
                        }}
                      />
                    )}
                    {durationLabel && (
                      <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs font-medium text-white">
                        {durationLabel}
                      </span>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="truncate text-base font-medium text-neutral-900">{t.title || "Untitled"}</h3>
                        <p className="mt-0.5 text-xs text-neutral-500">{timeAgo(t.created_at)}</p>
                      </div>
                      <StatusBadge status={t.status} />
                    </div>
                    <div className="mt-2 text-sm text-neutral-700">
                      {t.status === "running" && (
                        <span>
                          Processing{typeof t.eta_seconds === "number" ? ` · ETA ${Math.max(0, t.eta_seconds)}s` : ""}
                        </span>
                      )}
                      {t.status === "queued" && <span>Queued</span>}
                      {t.status === "complete" && <span>Complete</span>}
                      {t.status === "error" && <span>Error</span>}
                    </div>
                  </div>
                </a>
              </article>
            );
          })}
        </div>
      )}
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
