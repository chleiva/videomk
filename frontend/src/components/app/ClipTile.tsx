// A clip in the composer's media strip (same row as the photos: docs/VIDEO_UPLOAD_CLIENTS_2026-11-28.md section 6), the calm notes under the strip, and the Recent clips list.
// The tile has the clip's own shape (landscape, portrait, square: never stretched), a play badge, a "5 s" chip and a speaker badge with a text label; every state has words for a screen reader.
import "../../styles/clips.css";
import { useEffect, useState } from "react";
import { Sheet, Spinner } from "../ui";
import { AIcon as Icon } from "./icons";
import { listClips } from "../../lib/videoClipDeps";
import { failureKey } from "../../lib/videoClips";
import type { Clip, ClipItem, VideoUploadCaps } from "../../lib/videoClips";

type T = (k: string, v?: Record<string, string | number>) => string;
const lenOf = (i: ClipItem, used: number) => Math.max(1, Math.round(i.clip?.duration ?? used));

/** The words for the tile's state: what a screen reader says for it. */
export function tileState(i: ClipItem, t: T, used = 5): string {
  if (i.state === "ready") return `${t("create.clip_ready")}, ${lenOf(i, used)} s${i.clip?.audioUsed ? `, ${t("create.clip_sound_on")}` : ""}`;
  if (i.state === "uploading") return t("create.clip_uploading", { pct: i.pct });
  if (i.state === "analysing") return t("create.clip_checking");
  if (i.state === "hashing") return t("create.clip_a11y_up");
  return t("create.clip_a11y_bad");
}

export function ClipTile({ item, t, used = 5, onRemove }: { item: ClipItem; t: T; used?: number; onRemove: () => void }) {
  const bad = item.state === "failed" || item.state === "rejected";
  const busy = item.state === "hashing" || item.state === "uploading" || item.state === "analysing";
  const a = Math.min(2, Math.max(0.6, item.aspect ?? item.clip?.aspect ?? 1));
  return (
    <div role="listitem" className={`attach clip is-${item.state}`} style={{ "--clip-a": String(a) } as React.CSSProperties}>
      {item.poster ? <img src={item.poster} alt="" /> : <span className="clip-ph" aria-hidden="true"><Icon name="film" size={22} /></span>}
      {item.state === "ready" && <span className="clip-play" aria-hidden="true"><Icon name="play" size={14} /></span>}
      {item.state === "ready" && <span className="clip-chip" aria-hidden="true">{lenOf(item, used)} s</span>}
      {item.state === "ready" && item.clip?.audioUsed && <span className="clip-snd" aria-hidden="true" title={t("create.clip_sound_on")}><Icon name="volume" size={12} /></span>}
      {busy && (
        <span className="attach-busy clip-busy" aria-hidden="true">
          {item.state === "uploading" ? <><span className="clip-pct">{item.pct}%</span><i className="clip-bar"><b style={{ transform: `scaleX(${item.pct / 100})` }} /></i></> : <Spinner />}
        </span>
      )}
      {bad && <span className="attach-bad" aria-hidden="true">!</span>}
      <span className="sr-only-vmk">{t("create.clip_tile_a11y", { state: tileState(item, t, used) })}</span>
      <button type="button" className="attach-x" aria-label={t("create.clip_remove")} onClick={onRemove}><Icon name="close" size={14} /></button>
    </div>
  );
}

/** Under the strip: one line while something is being sent or checked, the reason (with Try again) for each clip that did not work, small facts about ready clips. */
export function ClipNotes({ items, t, onRetry, onRemove }: { items: ClipItem[]; t: T; onRetry: (key: string) => void; onRemove: (key: string) => void }) {
  const up = items.filter((i) => i.state === "uploading" || i.state === "hashing");
  const checking = items.filter((i) => i.state === "analysing");
  const slow = checking.some((i) => i.slow);
  const status = up.length ? t("create.clip_uploading", { pct: Math.round(up.reduce((n, i) => n + i.pct, 0) / up.length) }) : slow ? t("create.clip_slow") : checking.length ? t("create.clip_checking") : null;
  const bad = items.filter((i) => i.state === "failed" || i.state === "rejected");
  const facts = items.filter((i) => i.state === "ready" && i.clip).flatMap((i) => [
    ...(i.clip!.trimmed ? [`${i.key}t:${t("create.clip_first5_used")}`] : []),
    ...(i.clip!.useAudio && !i.clip!.audioUsed && (i.clip!.audioState === "unscreened" || i.clip!.audioState === "unavailable") ? [`${i.key}a:${t("create.clip_no_sound_used")}`] : []),
  ]);
  if (!status && !bad.length && !facts.length) return null;
  return (
    <div className="clip-notes">
      {status && <p className="hint clip-status" data-slow={slow || undefined}>{!slow && <span className="clip-status-sp" aria-hidden="true"><Spinner /></span>}<span>{status}</span></p>}
      {bad.map((i) => (
        <div key={i.key} className="clip-bad hint-bad">
          <Icon name="warning" size={18} className="clip-bad-ic" />
          <p className="clip-bad-t">{i.failure?.message ?? t(failureKey(i.failure ?? { kind: "error" }), { limit: "25 MB" })}</p>
          <span className="clip-bad-actions">
            {i.failure?.retry && <button type="button" className="btn btn-tonal btn-sm" onClick={() => onRetry(i.key)}>{t("create.clip_try_again")}</button>}
            {i.state === "rejected" && <a className="cost-link" href="/support/">{t("create.clip_help")}</a>}
            <button type="button" className="btn btn-quiet btn-sm" onClick={() => onRemove(i.key)}>{t("create.clip_remove")}</button>
          </span>
        </div>
      ))}
      {facts.map((f) => <p key={f.split(":")[0]} className="hint">{f.slice(f.indexOf(":") + 1)}</p>)}
    </div>
  );
}

/** The last 14 days of clips (GET /video-uploads): pick a ready one to use it again. */
export function RecentClipsSheet({ caps, t, taken, room, onUse, onClose }: { caps: VideoUploadCaps; t: T; taken: string[]; room: number; onUse: (c: Clip) => void; onClose: () => void }) {
  const [clips, setClips] = useState<Clip[] | null | "error">(null);
  useEffect(() => { let on = true; void listClips(caps.apiUrl).then((r) => on && setClips(r ?? "error")); return () => { on = false; }; }, [caps.apiUrl]);
  return (
    <Sheet title={t("create.clip_recent_title")} onClose={onClose}>
      <div className="clip-recent">
        {clips === null ? <p className="muted" role="status"><Spinner /> {t("create.clip_recent_loading")}</p>
          : clips === "error" ? <p className="notice notice-bad" role="alert">{t("create.clip_recent_error")}</p>
          : clips.length === 0 ? <p className="muted">{t("create.clip_recent_empty")}</p>
          : <ul className="clip-recent-grid">{clips.map((c) => {
              const ok = c.ready && !taken.includes(c.id) && room > 0;
              return (
                <li key={c.id}>
                  <button type="button" className={`clip-recent-item ${ok ? "" : "is-dim"}`} aria-disabled={!ok || undefined} aria-label={c.ready ? t("create.clip_recent_use", { s: Math.max(1, Math.round(c.duration ?? caps.usedSeconds)) }) : t("create.clip_recent_wait")} onClick={() => ok && onUse(c)}>
                    {c.thumbUrl ? <img src={c.thumbUrl} alt="" /> : <span className="clip-ph" aria-hidden="true"><Icon name="film" size={22} /></span>}
                    {c.ready ? <span className="clip-chip" aria-hidden="true">{Math.max(1, Math.round(c.duration ?? caps.usedSeconds))} s</span> : <span className="attach-busy" aria-hidden="true"><Spinner /></span>}
                  </button>
                </li>
              );
            })}</ul>}
      </div>
    </Sheet>
  );
}
