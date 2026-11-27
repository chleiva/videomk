// React binding for lib/upload.ts: one queue per page, a snapshot the components render, a warning before the page closes while photos are still going up.
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { UploadQueue } from "../../lib/upload";
import type { QueueDeps, QueueSummary, UploadItem } from "../../lib/upload";

export function useUploadQueue(make: () => QueueDeps): { queue: UploadQueue; items: UploadItem[]; summary: QueueSummary } {
  const ref = useRef<UploadQueue | null>(null);
  if (!ref.current) ref.current = new UploadQueue(make());
  const queue = ref.current;
  const snap = useSyncExternalStore((fn) => queue.subscribe(fn), () => queue.snapshot(), () => queue.snapshot());
  const busy = snap.summary.running && snap.summary.finished < snap.summary.total;
  useEffect(() => {
    if (!busy) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);
  return useMemo(() => ({ queue, items: snap.items, summary: snap.summary }), [queue, snap]);
}
