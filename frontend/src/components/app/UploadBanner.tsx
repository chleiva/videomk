// The one calm banner for uploads (the apps' upload journey): one line, one progress bar, Pause / Resume / Cancel, then the outcome with what needs attention.
import { AIcon as Icon } from "./icons";
import { bannerLine } from "../../lib/upload";
import type { QueueSummary, UploadQueue } from "../../lib/upload";
import { useLocale } from "../../lib/useLocale";
import { formatBytes } from "../../lib/library";

export default function UploadBanner({ queue, summary, onDismiss }: { queue: UploadQueue; summary: QueueSummary; onDismiss: () => void }) {
  const { t, locale } = useLocale();
  if (summary.total === 0) return null;
  const finished = summary.finished >= summary.total;
  const line = bannerLine(summary);
  const notes: string[] = [];
  if (summary.duplicates) notes.push(t("upload.duplicates", { n: summary.duplicates }));
  if (summary.noSpace) notes.push(t("upload.no_space", { n: summary.noSpace }));
  if (summary.unsupported) notes.push(t("upload.unsupported", { n: summary.unsupported }));
  if (summary.failed) notes.push(t("upload.failed", { n: summary.failed }));
  return (
    <section className={`upload-banner ${finished && (summary.failed || summary.noSpace || summary.unsupported) ? "has-issue" : ""}`} aria-label={t("upload.a11y")}>
      <div className="upload-row">
        <p className="upload-line" role="status" aria-live="polite">
          {finished ? <Icon name="check" size={18} /> : <span className="spinner" aria-hidden="true" />}
          <span>{t(line.key, line.params)}</span>
          {!finished && summary.bytes > 0 && <span className="muted"> · {formatBytes(summary.bytesDone, locale)} / {formatBytes(summary.bytes, locale)}</span>}
        </p>
        <div className="upload-actions">
          {!finished && (summary.paused
            ? <button type="button" className="btn btn-tonal btn-sm" onClick={() => queue.resume()}>{t("upload.resume")}</button>
            : <button type="button" className="btn btn-line btn-sm" onClick={() => queue.pause()}>{t("upload.pause")}</button>)}
          {!finished && <button type="button" className="btn btn-line btn-sm" onClick={() => queue.cancel()}>{t("upload.cancel")}</button>}
          {finished && summary.failed > 0 && <button type="button" className="btn btn-tonal btn-sm" onClick={() => queue.retryFailed()}>{t("upload.retry")}</button>}
          {finished && <button type="button" className="btn btn-line btn-sm" onClick={onDismiss}>{t("upload.dismiss")}</button>}
        </div>
      </div>
      {!finished && <div className="upload-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={summary.pct} aria-label={t("upload.a11y")} style={{ ["--p" as any]: `${summary.pct}%` }}><i /></div>}
      {!finished && <p className="caption">{t("upload.leave")}</p>}
      {notes.length > 0 && <ul className="upload-notes">{notes.map((n) => <li key={n}>{n}</li>)}</ul>}
    </section>
  );
}
