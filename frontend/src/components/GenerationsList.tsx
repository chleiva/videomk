import { useEffect, useMemo, useRef, useState } from "react";
import { apiGateway } from "../lib/config";
import { getAuthorizationHeader, handleAuthCodeIfPresent } from "../lib/auth";
import { currentLocaleHeaders } from "../lib/i18n";
import { useLocale } from "../lib/useLocale";
import { formatDuration, groupByDay, isMaking, normalizeItem } from "../lib/videos";
import type { TaskItem } from "../lib/videos";
import { EmptyState, MakingCard, Thumb } from "./ui";


export default function GenerationsList({ refreshNonce = 0, view = "grid", onCreate }: { refreshNonce?: number; view?: "grid" | "list"; onCreate?: () => void }) {
  const { t: tr } = useLocale();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [userId, setUserId] = useState<string | null>(null);

  const hasTasks = useMemo(() => tasks.length > 0, [tasks]);

  const timerRef = useRef<number | undefined>(undefined);
  const delayRef = useRef<number>(15000);
  const hasActiveRef = useRef<boolean>(true);

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
      const res = await fetch(endpoint, { headers: { Authorization, ...currentLocaleHeaders() } });
      if (!res.ok) throw new Error("Failed to fetch tasks");
      const data = (await res.json()) as { items?: any[] };
      const raw = Array.isArray(data.items) ? data.items : [];

      const normalized: TaskItem[] = raw.map(normalizeItem).filter(Boolean) as TaskItem[];

      // The list endpoint returns every video for the user, so this is the source of truth for polling.
      hasActiveRef.current = normalized.some((t) => t.status === "running" || t.status === "queued");
      setTasks((prev) => {
        const merged = mergeTasks(prev, normalized);
        saveCache(merged);
        return merged;
      });
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
      // Poll only while something is still processing; back off but never beyond 2 minutes.
      if (hasActiveRef.current) {
        const currentDelay = delayRef.current;
        timerRef.current = window.setTimeout(() => {
          delayRef.current = Math.min(currentDelay + 15000, 120000);
          fetchTasks();
        }, currentDelay);
      }
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
    delayRef.current = 15000;
    hasActiveRef.current = true;
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
    return (
      <div className="vgrid" role="status" aria-label={tr("gen.loading")}>
        {[0, 1, 2].map((i) => <div key={i} className="card animate-pulse p-3"><div className="thumb" /><div className="mt-3 h-4 w-3/4 rounded-full bg-surface3" /><div className="mt-2 h-3 w-1/3 rounded-full bg-surface3" /></div>)}
      </div>
    );
  }

  if (!hasTasks) {
    return (
      <EmptyState
        title={tr("gen.empty_title")}
        body={tr("gen.empty_body")}
        action={onCreate && <button type="button" onClick={onCreate} className="btn btn-primary mt-2">{tr("gen.empty_cta")}</button>}
      />
    );
  }

  function timeAgo(iso: string | null | undefined): string | null {
    if (!iso) return null;
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return null;
    const sec = Math.floor(Math.max(0, Date.now() - then) / 1000);
    if (sec < 45) return tr("time.just_now");
    const min = Math.floor(sec / 60);
    if (min < 60) return tr("time.minutes", { n: min });
    const hr = Math.floor(min / 60);
    if (hr < 24) return tr("time.hours", { n: hr });
    const day = Math.floor(hr / 24);
    if (day < 30) return tr("time.days", { n: day });
    const mon = Math.floor(day / 30);
    if (mon < 12) return tr("time.months", { n: mon });
    return tr("time.years", { n: Math.floor(mon / 12) });
  }

  const making = tasks.filter(isMaking);
  const rest = tasks.filter((t) => !isMaking(t));
  const groups = groupByDay(rest);
  const card = (t: TaskItem) => <VideoCard key={t.id} t={t} view={view} ago={timeAgo(t.created_at)} />;

  return (
    <div>
      {making.length > 0 && (
        <section aria-label={tr("gen.group_making")}>
          <div className="vgrid">
            {making.map((t) => <MakingCard key={t.id} title={t.title} stage={t.stage} etaSeconds={t.eta_seconds} />)}
          </div>
        </section>
      )}
      {groups.map((g) => (
        <section key={g.group} aria-labelledby={`day-${g.group}`}>
          <h2 id={`day-${g.group}`} className="eyebrow day-head">{tr(`gen.group_${g.group}`)}</h2>
          {view === "grid" ? <div className="vgrid">{g.items.map(card)}</div> : <div role="list" className="space-y-3">{g.items.map(card)}</div>}
        </section>
      ))}
    </div>
  );
}

function VideoCard({ t, view, ago }: { t: TaskItem; view: "grid" | "list"; ago: string | null }) {
  const { t: tr } = useLocale();
  const title = t.title || tr("gen.untitled");
  const durationLabel = formatDuration(t.duration_s);
  const failed = t.status === "error" || t.status === "rejected";
  const href = `/watch/index.html?id=${encodeURIComponent(t.id)}`;
  const remember = () => {
    const playUrl = t.video_url || t.download_url;
    if (playUrl && playUrl.startsWith("http")) { try { sessionStorage.setItem(`vmk_play_url_${t.id}`, playUrl); } catch {} }
  };
  const row = view === "list";
  const body = (
    <>
      {!failed && <Thumb id={t.id} src={t.preview_gif_url} duration={durationLabel} />}
      <div className={row ? "min-w-0 flex-1" : failed ? "" : "mt-3"}>
        <h3 className="vcard-title">{title}</h3>
        <p className="vcard-meta mt-1">{[ago, durationLabel].filter(Boolean).join(" · ")}</p>
        {failed && <p className="mt-2 text-[length:var(--fs-subhead)]">{t.status === "rejected" ? (t.reject_reason || tr("gen.rejected_default")) : tr("gen.error_detail")}</p>}
      </div>
    </>
  );
  return (
    <article role={row ? "listitem" : undefined} className={`vcard ${failed ? "failed-card" : ""}`}>
      {failed ? (
        <div className={row ? "vrow" : ""}>
          {body}
          <div className="mt-3"><StatusBadge status={t.status} /></div>
        </div>
      ) : (
        <a href={href} onClick={remember} aria-label={durationLabel ? tr("gen.watch_duration", { title, duration: durationLabel }) : tr("gen.watch", { title })} className={`vlink block text-inherit no-underline ${row ? "vrow" : ""}`} style={{ color: "inherit" }}>
          {body}
        </a>
      )}
      <EditLink t={t} />
    </article>
  );
}

function EditLink({ t }: { t: TaskItem }) {
  const { t: tr } = useLocale();
  if (t.status !== "complete" || !t.editable) return null;
  return (
    <div className="mt-3">
      <a href={`/edit/index.html?id=${encodeURIComponent(t.id)}`} className="btn btn-tonal btn-sm">{tr("gen.edit")}</a>
    </div>
  );
}

export function StatusBadge({ status }: { status: TaskItem["status"] }) {
  const { t: tr } = useLocale();
  const cls = { queued: "badge-neutral", running: "badge-primary", complete: "badge-ok", error: "badge-bad", rejected: "badge-warn" }[status];
  return <span className={`badge ${cls}`}>{tr(`status.${status}`)}</span>;
}
