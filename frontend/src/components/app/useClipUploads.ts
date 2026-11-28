// React binding for lib/videoClips.ts: one uploader per composer, a snapshot the strip renders, a warning before the page closes while a clip is still going up.
import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { ClipUploader } from "../../lib/videoClips";
import type { ClipDeps, ClipItem } from "../../lib/videoClips";

export function useClipUploads(deps: ClipDeps | null): { uploader: ClipUploader | null; items: ClipItem[] } {
  const ref = useRef<ClipUploader | null>(null);
  if (deps && !ref.current) ref.current = new ClipUploader(deps);   // made once, when the address from capabilities is known
  const u = ref.current;
  const snap = useSyncExternalStore((fn) => (u ? u.subscribe(fn) : () => {}), () => (u ? u.snapshot() : EMPTY), () => EMPTY);
  const busy = snap.items.some((i) => i.state === "hashing" || i.state === "uploading");
  useEffect(() => {
    if (!busy) return;
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [busy]);
  return useMemo(() => ({ uploader: u, items: snap.items }), [u, snap]);
}
const EMPTY = { items: [] as ClipItem[] };
