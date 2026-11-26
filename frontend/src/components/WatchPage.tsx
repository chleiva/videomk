// The watch page: the video edge to edge, then Share (primary), Save and Edit. Replaces the old plain-JS public/watch.js.
import { useEffect, useMemo, useState } from "react";
import { getAuthorizationHeader } from "../lib/auth";
import { apiGateway } from "../lib/config";
import { currentLocaleHeaders } from "../lib/i18n";
import { Icon, Spinner, useToast } from "./ui";
import { formatDuration } from "../lib/videos";
import { useLocale } from "../lib/useLocale";

interface Known { title?: string; editable?: boolean; duration_s?: number | null; status?: string }

/** What the list already told us about this video (title, editable, duration), from the session cache the list writes. */
function known(id: string): Known {
  try { const items = JSON.parse(sessionStorage.getItem("vmk_tasks") || "[]"); return (Array.isArray(items) ? items : []).find((x: any) => x?.id === id) || {}; } catch { return {}; }
}

export default function WatchPage() {
  const { t } = useLocale();
  const id = useMemo(() => new URLSearchParams(location.search).get("id") || "", []);
  const info = useMemo(() => known(id), [id]);
  const [url, setUrl] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const toast = useToast();

  useEffect(() => {
    if (!id) { setState("error"); return; }
    let alive = true;
    (async () => {
      let playUrl: string | null = null;
      try { playUrl = sessionStorage.getItem(`vmk_play_url_${id}`); } catch {}
      try {
        if (!playUrl) {
          const { Authorization, userId } = await getAuthorizationHeader();
          if (!userId) throw new Error("auth");
          const r = await fetch(apiGateway.getVideo(userId, id), { headers: { Authorization, ...currentLocaleHeaders() } });
          if (!r.ok) throw new Error(String(r.status));
          const j = await r.json();
          playUrl = typeof j?.url === "string" ? j.url : null;
        }
        if (!alive) return;
        if (playUrl) { setUrl(playUrl); setState("ready"); } else setState("error");
      } catch { if (alive) setState("error"); }
    })();
    return () => { alive = false; };
  }, [id]);

  const title = info.title || t("gen.untitled");
  const duration = formatDuration(info.duration_s);
  const fileName = `${title.replace(/[\\/:*?"<>|]+/g, " ").trim().slice(0, 80) || "video"}.mp4`;

  async function share() {
    if (!url) return;
    try {
      if (navigator.share) { await navigator.share({ title, url }); return; }
      await navigator.clipboard.writeText(url);
      toast.show(t("watch.link_copied"));
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") toast.show(t("watch.share_failed"));
    }
  }

  return (
    <div>
      <div className="watch-stage">
        {state === "ready" && url ? (
          <video src={url} controls playsInline preload="auto" aria-label={title} />
        ) : (
          <div className="flex min-h-[40vh] items-center justify-center p-6 text-center" style={{ color: "var(--on-making)" }} role={state === "error" ? "alert" : "status"}>
            {state === "loading" ? <span className="flex items-center gap-3"><Spinner />{t("gen.loading")}</span> : <span>{t("watch.load_error")}</span>}
          </div>
        )}
      </div>
      <section className="page page-narrow">
        <a href="/generations/index.html" className="inline-flex min-h-11 items-center gap-1 font-semibold no-underline"><Icon name="back" size={18} />{t("watch.back")}</a>
        <h1 className="h1 mt-2" style={{ fontSize: "var(--fs-title)" }}>{title}</h1>
        {duration && <p className="caption mt-1">{duration}</p>}
        <div className="mt-5 flex flex-wrap gap-3">
          <button type="button" className="btn btn-primary" onClick={share} disabled={!url}><Icon name="share" size={18} />{t("watch.share")}</button>
          {url ? <a href={url} download={fileName} target="_blank" rel="noopener" className="btn btn-tonal"><Icon name="download" size={18} />{t("watch.save")}</a> : <span className="btn btn-tonal" aria-disabled="true"><Icon name="download" size={18} />{t("watch.save")}</span>}
          {info.editable && <a href={`/edit/index.html?id=${encodeURIComponent(id)}`} className="btn btn-tonal"><Icon name="edit" size={18} />{t("gen.edit")}</a>}
        </div>
        <div className="card mt-8 flex flex-wrap items-center justify-between gap-3 p-5">
          <div><p className="font-semibold">{t("watch.make_another")}</p><p className="caption">{t("watch.make_another_sub")}</p></div>
          <a href="/generations/index.html" className="btn btn-line btn-sm">{t("gen.create")}</a>
        </div>
      </section>
      {toast.node}
    </div>
  );
}
