// The video list's data: first load from the session cache (instant), then the API; polling only while something is being made, backing off, paused when the tab is hidden,
// and gentle on the screen: unchanged cards keep their object and their first thumbnail link, so a poll never makes the list flash (the owner saw that on Android).
import { useCallback, useEffect, useRef, useState } from "react";
import { getAuthorizationHeader } from "../../lib/auth";
import { apiGateway } from "../../lib/config";
import { currentLocaleHeaders } from "../../lib/i18n";
import { cancelVideo } from "../../lib/api";
import { deleteOutcome, isMaking, markCancelled, markRetrying, nextPollMs, normalizeItem, retryOutcome, reuseUnchanged, stableSceneThumbs, stableThumbs, withoutSceneLinks } from "../../lib/videos";
import type { CancelOutcome, DeleteOutcome, RetryOutcome, TaskItem } from "../../lib/videos";

const CACHE = "vmk_tasks";
const newestFirst = (a: TaskItem, b: TaskItem) => (b.created_at ? Date.parse(b.created_at) : 0) - (a.created_at ? Date.parse(a.created_at) : 0);

export function useVideos() {
  const [items, setItems] = useState<TaskItem[]>(() => { try { const c = JSON.parse(sessionStorage.getItem(CACHE) || "null"); return Array.isArray(c) ? c : []; } catch { return []; } });
  const [state, setState] = useState<"loading" | "ready" | "error">(items.length ? "ready" : "loading");
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const [sceneThumbs, setSceneThumbs] = useState<Record<string, string>>({});   // the film strip's pictures, by video and scene (never by link: the link changes on every poll)
  const timer = useRef<number | undefined>(undefined);
  const attempt = useRef(0);
  const alive = useRef(true);
  const auth = useRef<{ Authorization: string; userId: string } | null>(null);   // the last good sign-in header: a delete sent while the page is being left cannot wait for one
  const hidden = useRef(new Set<string>());   // videos the person deleted and may still bring back (Undo): gone from the screen, not yet from the server

  const load = useCallback(async (): Promise<void> => {
    window.clearTimeout(timer.current);
    let making = false;
    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      if (!userId) throw new Error("no session");
      auth.current = { Authorization, userId };
      const res = await fetch(apiGateway.listVideos(userId), { headers: { Authorization, ...currentLocaleHeaders() } });
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as { items?: unknown[] };
      const next = ((Array.isArray(data.items) ? data.items : []).map(normalizeItem).filter(Boolean) as TaskItem[]).filter((i) => !hidden.current.has(i.id));
      next.sort(newestFirst);
      making = next.some(isMaking);
      if (!alive.current) return;
      setItems((prev) => { const merged = reuseUnchanged(prev, next); try { sessionStorage.setItem(CACHE, JSON.stringify(withoutSceneLinks(merged))); } catch { /* full */ } return merged; });
      setThumbs((p) => stableThumbs(p, next));
      setSceneThumbs((p) => stableSceneThumbs(p, next));
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

  /** "Try again": the SAME video runs again (same id, same card). Nothing is created here and nothing is resent from the browser, so the photos cannot be lost. */
  const retry = useCallback(async (id: string): Promise<RetryOutcome> => {
    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      if (!userId) return { ok: false, kind: "error" };
      const res = await fetch(apiGateway.retryVideo(userId, id), { method: "POST", headers: { Authorization, ...currentLocaleHeaders() } });
      const out = retryOutcome(res.status, await res.json().catch(() => null));
      if (out.ok && alive.current) {
        setItems((prev) => { const next = markRetrying(prev, id); try { sessionStorage.setItem(CACHE, JSON.stringify(next)); } catch { /* full */ } return next; });
        attempt.current = 0; void load();
      }
      return out;
    } catch { return { ok: false, kind: "error" }; }
  }, [load]);

  /** Remove a video that did not finish (DELETE .../videos/{id}); a made video is never deleted here. */
  const remove = useCallback(async (id: string): Promise<boolean> => {
    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      if (!userId) return false;
      const res = await fetch(apiGateway.getVideo(userId, id), { method: "DELETE", headers: { Authorization, ...currentLocaleHeaders() } });
      if (!res.ok && res.status !== 404) return false;
      if (alive.current) setItems((prev) => { const next = prev.filter((i) => i.id !== id); try { sessionStorage.setItem(CACHE, JSON.stringify(next)); } catch { /* full */ } return next; });
      return true;
    } catch { return false; }
  }, []);

  /** Cancel a video that is being made (POST .../cancel): the workflow stops and the credits of this attempt come back. A step change between the server's read and
   *  write answers `try_again`: the same call is sent once more. */
  const cancel = useCallback(async (id: string): Promise<CancelOutcome> => {
    const out = await cancelVideo(id);
    if (alive.current && out.ok) setItems((prev) => { const next = markCancelled(prev, id); try { sessionStorage.setItem(CACHE, JSON.stringify(withoutSceneLinks(next))); } catch { /* full */ } return next; });
    if (alive.current && (out.ok || out.kind === "done" || out.kind === "gone")) { attempt.current = 0; void load(); }   // the server's view: stopped, finished meanwhile, or gone
    return out;
  }, [load]);

  /** Delete with Undo. The server has no bin (docs/CREATE_API.md: "There is no undo"), so the card leaves the screen at once and the DELETE is sent only when the
   *  Undo time is over (`commit`), or when the page is left before that. `undo` simply brings the card back: nothing was sent. */
  const hide = useCallback((id: string): void => {
    hidden.current.add(id);
    setItems((prev) => { const next = prev.filter((i) => i.id !== id); try { sessionStorage.setItem(CACHE, JSON.stringify(withoutSceneLinks(next))); } catch { /* full */ } return next; });
  }, []);
  const unhide = useCallback((id: string) => { hidden.current.delete(id); attempt.current = 0; void load(); }, [load]);
  const destroy = useCallback(async (id: string, keepalive = false): Promise<DeleteOutcome> => {
    try {
      const { Authorization, userId } = keepalive && auth.current ? auth.current : await getAuthorizationHeader();   // leaving the page: sent at once, with a request that outlives it
      if (!userId) return { ok: false, kind: "error" };
      const res = await fetch(apiGateway.getVideo(userId, id), { method: "DELETE", keepalive, headers: { Authorization, ...currentLocaleHeaders() } });
      const out = deleteOutcome(res.status, await res.json().catch(() => null));
      if (!out.ok && alive.current) unhide(id);   // it could not be deleted (an edit is rendering, the network): the card comes back
      else hidden.current.delete(id);
      return out;
    } catch { if (alive.current) unhide(id); return { ok: false, kind: "error" }; }
  }, [unhide]);

  return { items, thumbs, sceneThumbs, state, reload, retry, remove, cancel, hide, unhide, destroy };
}
