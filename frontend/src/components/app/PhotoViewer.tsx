// Full-size viewer: arrows or left/right keys move between photos, the full picture loads on top of the thumbnail, one row of actions (make a video, delete).
import { useEffect, useState } from "react";
import { Sheet, Spinner } from "../ui";
import { AIcon as Icon } from "./icons";
import { photoLabel } from "./MediaGrid";
import { getPhoto } from "../../lib/library";
import type { Photo } from "../../lib/library";
import { useLocale } from "../../lib/useLocale";

export default function PhotoViewer({ items, index, onIndex, onClose, onMakeVideo, onDelete }: { items: Photo[]; index: number; onIndex: (i: number) => void; onClose: () => void; onMakeVideo: (p: Photo) => void; onDelete: (p: Photo) => void }) {
  const { t, locale } = useLocale();
  const p = items[index];
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(null);
    if (!p) return;
    let alive = true;
    void getPhoto(p.id).then((r) => { if (alive && r) setUrl(r.url); });
    return () => { alive = false; };
  }, [p?.id]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft" && index > 0) { e.preventDefault(); onIndex(index - 1); }
      if (e.key === "ArrowRight" && index < items.length - 1) { e.preventDefault(); onIndex(index + 1); }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [index, items.length, onIndex]);
  if (!p) return null;
  return (
    <Sheet title={photoLabel(p, locale)} onClose={onClose}>
      <div className="viewer">
        <div className="viewer-stage">
          <img src={p.thumb_url} alt="" className="viewer-thumb" />
          {url ? <img src={url} alt={photoLabel(p, locale)} className="viewer-full" /> : <span className="viewer-busy" role="status" aria-label={t("gen.loading")}><Spinner /></span>}
          {index > 0 && <button type="button" className="viewer-nav is-prev icon-btn" aria-label={t("media.previous")} onClick={() => onIndex(index - 1)}><Icon name="left" size={22} /></button>}
          {index < items.length - 1 && <button type="button" className="viewer-nav is-next icon-btn" aria-label={t("media.next")} onClick={() => onIndex(index + 1)}><Icon name="right" size={22} /></button>}
        </div>
        <div className="viewer-actions">
          <button type="button" className="btn btn-primary btn-sm" onClick={() => onMakeVideo(p)}>{t("media.make_video")}</button>
          <button type="button" className="btn btn-line btn-sm" onClick={() => onDelete(p)}><Icon name="trash" size={16} />{t("media.delete")}</button>
        </div>
      </div>
    </Sheet>
  );
}
