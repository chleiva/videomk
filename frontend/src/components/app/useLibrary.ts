// My media's data: the summary (storage, years, places, collections), the timeline (paged), a meaning search with removable chips, and a filter (year, place, collection).
import { useCallback, useEffect, useRef, useState } from "react";
import { getSummary, listItems, searchPhotos } from "../../lib/library";
import type { Chip, Photo, Summary } from "../../lib/library";

export type Filter = { kind: "all" } | { kind: "year"; value: number } | { kind: "place"; value: string } | { kind: "collection"; value: string };
export interface LibState {
  summary: Summary | null; items: Photo[]; more: boolean; loading: boolean; error: "none" | "load" | "search";
  query: string; chips: Chip[]; filter: Filter; searching: boolean;
}

export function useLibrary(opts: { enabled?: boolean } = {}) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [items, setItems] = useState<Photo[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<LibState["error"]>("none");
  const [query, setQueryRaw] = useState("");
  const [chips, setChips] = useState<Chip[]>([]);
  const [dropped, setDropped] = useState<string[]>([]);
  const [filter, setFilterRaw] = useState<Filter>({ kind: "all" });
  const [searching, setSearching] = useState(false);
  const run = useRef(0);   // a newer request makes older answers irrelevant

  const loadSummary = useCallback(async () => { const s = await getSummary(); if (s) setSummary(s); return s; }, []);

  const loadPage = useCallback(async (f: Filter, after?: string) => {
    const my = ++run.current;
    if (!after) setLoading(true);
    const q = { cursor: after, ...(f.kind === "collection" ? { collection: f.value } : f.kind === "place" ? { place: f.value } : f.kind === "year" ? { from: `${f.value}-01-01`, to: `${f.value}-12-31` } : {}) };
    const r = await listItems(q);
    if (run.current !== my) return;
    if (!r.ok) { setError("load"); setLoading(false); return; }
    setError("none"); setItems((prev) => (after ? [...prev, ...r.items.filter((p) => !prev.some((x) => x.id === p.id))] : r.items)); setCursor(r.cursor); setLoading(false);
  }, []);

  const runSearch = useCallback(async (text: string, drop: string[]) => {
    const my = ++run.current;
    setSearching(true); setLoading(true);
    const r = await searchPhotos(text, drop);
    if (run.current !== my) return;
    setSearching(false); setLoading(false);
    if (!r) { setError("search"); return; }
    setError("none"); setItems(r.items); setChips(r.chips); setCursor(undefined);
  }, []);

  const refresh = useCallback(async () => { await loadSummary(); if (query.trim()) await runSearch(query.trim(), dropped); else await loadPage(filter); }, [loadSummary, loadPage, runSearch, query, dropped, filter]);

  useEffect(() => { if (opts.enabled === false) return; void loadSummary(); void loadPage({ kind: "all" }); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // typing runs a search after a short pause; emptying the box returns to the timeline
  useEffect(() => {
    if (opts.enabled === false) return;
    if (!query.trim()) { setChips([]); setDropped([]); return; }
    const t = setTimeout(() => { setDropped([]); void runSearch(query.trim(), []); }, 350);
    return () => clearTimeout(t);
  }, [query]); // eslint-disable-line react-hooks/exhaustive-deps

  const setQuery = useCallback((q: string) => {
    setQueryRaw(q);
    if (!q.trim()) { setChips([]); setDropped([]); void loadPage(filter); }
  }, [loadPage, filter]);
  const setFilter = useCallback((f: Filter) => { setFilterRaw(f); setQueryRaw(""); setChips([]); setDropped([]); void loadPage(f); }, [loadPage]);
  const dropChip = useCallback((label: string) => { const d = [...dropped, label]; setDropped(d); void runSearch(query.trim(), d); }, [dropped, query, runSearch]);
  const loadMore = useCallback(() => { if (cursor && !loading) void loadPage(filter, cursor); }, [cursor, loading, loadPage, filter]);

  return { summary, items, more: !!cursor, loading, error, query, chips, filter, searching, setQuery, setFilter, dropChip, loadMore, refresh, loadSummary };
}
