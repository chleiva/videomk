// The video list's data: first load from the session cache (instant), then the API; polling only while something is being made, backing off, paused when the tab is hidden,
// and gentle on the screen: unchanged cards keep their object and their first thumbnail link, so a poll never makes the list flash (the owner saw that on Android).
import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthorizationHeader } from "../../lib/auth";
import { apiGateway } from "../../lib/config";
import { currentLocaleHeaders } from "../../lib/i18n";
import { isMaking, nextPollMs, normalizeItem, reuseUnchanged, stableThumbs } from "../../lib/videos";
import type { TaskItem } from "../../lib/videos";

const CACHE = "vmk_tasks";
const newestFirst = (a: TaskItem, b: TaskItem) => (b.created_at ? Date.parse(b.created_at) : 0) - (a.created_at ? Date.parse(a.created_at) : 0);

export function useVideos() {
  const [items, setItems] = useState<TaskItem[]>(() => { try { const c = JSON.parse(sessionStorage.getItem(CACHE) || "null"); return Array.isArray(c) ? c : []; } catch { return []; } });
  const [state, setState] = useState<"loading" | "ready" | "error">(items.length ? "ready" : "loading");
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const timer = useRef<number | undefined>(undefined);
  const attempt = useRef(0);
  const alive = useRef(true);

  const load = useCallback(async (): Promise<void> => {
    window.clearTimeout(timer.current);
    let making = false;
    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      if (!userId) throw new Error("no session");
      const res = await fetch(apiGateway.listVideos(userId), { headers: { Authorization, ...currentLocaleHeaders() } });
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as { items?: unknown[] };
      const next = (Array.isArray(data.items) ? data.items : []).map(normalizeItem).filter(Boolean) as TaskItem[];
      next.sort(newestFirst);
      making = next.some(isMaking);
      if (!alive.current) return;
      setItems((prev) => { const merged = reuseUnchanged(prev, next); try { sessionStorage.setItem(CACHE, JSON.stringify(merged)); } catch { /* full */ } return merged; });
      setThumbs((p) => stableThumbs(p, next));
      setState("ready");
    } catch {
      if (alive.current) setState((s) => (s === "ready" ? "ready" : "error"));   // keep showing what we have; only a first load that fails is an error
      making = true;                                                            // and try again soon
    }
    if (!alive.current) return;
    const ms = nextPollMs(attempt.current++, making, document.hidden);
    if (ms !== null) timer.current = window.setTimeout(() => void load(), ms);
  }, []);

  useEffect(() => {
    alive.current = true;
    void load();
    const vis = () => { if (!document.hidden) { attempt.current = 0; void load(); } };
    document.addEventListener("visibilitychange", vis);
    return () => { alive.current = false; window.clearTimeout(timer.current); document.removeEventListener("visibilitychange", vis); };
  }, [load]);

  const reload = useCallback(() => { attempt.current = 0; setState((s) => (s === "ready" ? s : "loading")); void load(); }, [load]);
  return { items, thumbs, state, reload };
}
