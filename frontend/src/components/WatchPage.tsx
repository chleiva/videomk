// The watch page (docs/WEB_REDESIGN_2026.md, docs/UX_2026_REDESIGN.md 4.1): the video, one caption line, ONE row of icons (Share, Save, Edit, Info, More).
// "Make another" lives on the end card and in More. No labels around the player. Logic in lib/player.ts.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Player from "./Player";
import type { PlayerMeta } from "./Player";
import { PIcon } from "./PlayerIcons";
import { AIcon } from "./app/icons";
import FilmStrip from "./app/FilmStrip";
import { Sheet, Spinner, useToast } from "./ui";
import { IconButton } from "./ui/IconButton";
import { Button } from "./ui/Button";
import { getAuthorizationHeader } from "../lib/auth";
import { apiGateway } from "../lib/config";
import { currentLocaleHeaders } from "../lib/i18n";
import { aspectLabel, metaLine, safeFileName } from "../lib/player";
import { pickPrompt, promptFor } from "../lib/prompts";
import { parseMaking, sceneCounter, stableSceneThumbs, stripTiles } from "../lib/videos";
import type { Making } from "../lib/videos";
import { useLocale } from "../lib/useLocale";

const POLL_MS = 5000;   // while the video is being made this page follows it (same call, same pace as the list)

interface Known { title?: string; editable?: boolean; duration_s?: number | null; preview_gif_url?: string | null }
type View = { state: "loading" } | { state: "error" } | { state: "making"; making: Making | null } | { state: "failed" } | { state: "ready"; url: string };

/** What the list already told us about this video (title, editable, duration), from the session cache the list writes. */
function known(id: string): Known {
  try { const items = JSON.parse(sessionStorage.getItem("vmk_tasks") || "[]"); return (Array.isArray(items) ? items : []).find((x: any) => x?.id === id) || {}; } catch { return {}; }
}

export default function WatchPage() {
  const { t, locale } = useLocale();
  const id = useMemo(() => new URLSearchParams(location.search).get("id") || "", []);
  const info = useMemo(() => known(id), [id]);
  const [view, setView] = useState<View>({ state: "loading" });
  const [title, setTitle] = useState(info.title || "");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState<string | null>(() => promptFor(id));
  const [sceneThumbs, setSceneThumbs] = useState<Record<string, string>>({});
  const [meta, setMeta] = useState<PlayerMeta | null>(null);
  const [sheet, setSheet] = useState(false);
  const [menu, setMenu] = useState(false);
  const [tries, setTries] = useState(0);
  const toast = useToast();
  const menuRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!id) { setView({ state: "error" }); return; }
    let alive = true, timer: number | undefined;
    setView({ state: "loading" });
    const load = async (first: boolean) => {
      try {
        const { Authorization, userId } = await getAuthorizationHeader();
        if (!userId) throw new Error("auth");
        const r = await fetch(apiGateway.getVideo(userId, id), { headers: { Authorization, ...currentLocaleHeaders() } });
        if (!alive) return;
        if (r.status === 409) {
          let b: any = null; try { b = await r.json(); } catch { /* no body */ }
          if (!alive) return;
          const st = String(b?.status || "").toUpperCase();
          if (st === "ERROR" || st === "FAILED" || st === "REJECTED" || st === "CANCELLED") { setView({ state: "failed" }); return; }
          const making = parseMaking(b?.making);   // optional (docs/CREATE_API.md "Making status"): without it the page says "Still being made" as before
          setSceneThumbs((p) => stableSceneThumbs(p, [{ id, making }]));
          setView({ state: "making", making });
          timer = window.setTimeout(() => void load(false), POLL_MS);   // follow it until it is ready: the player then appears by itself
          return;
        }
        if (!r.ok) throw new Error(String(r.status));
        const j = await r.json();
        if (!alive) return;
        if (typeof j?.title === "string" && j.title.trim()) setTitle(j.title);
        if (typeof j?.description === "string") setDescription(j.description);
        setPrompt((p) => pickPrompt(j?.prompt, p));
        if (typeof j?.url === "string") setView({ state: "ready", url: j.url });
        else setView({ state: "error" });
      } catch {
        if (!alive) return;
        if (first) setView({ state: "error" }); else timer = window.setTimeout(() => void load(false), POLL_MS * 2);   // one missed poll is not an error screen
      }
    };
    void load(true);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [id, tries]);

  // the More menu: closes with Escape or a click outside, focus goes back to its button
  useEffect(() => {
    if (!menu) return;
    const away = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node) && !moreRef.current?.contains(e.target as Node)) setMenu(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setMenu(false); moreRef.current?.focus(); } };
    document.addEventListener("mousedown", away); document.addEventListener("keydown", key);
    menuRef.current?.querySelector<HTMLElement>("a,button")?.focus();
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", key); };
  }, [menu]);

  const shown = title || t("gen.untitled");
  const url = view.state === "ready" ? view.url : null;
  const ratio = meta ? aspectLabel(meta.width, meta.height) : null;
  const ar = meta && meta.width > 0 && meta.height > 0 ? meta.width / meta.height : 16 / 9;
  const caption = metaLine(meta?.duration || info.duration_s || null, meta?.width || 0, meta?.height || 0);

  const share = useCallback(async () => {
    if (!url) return;
    try {
      if (navigator.share) { await navigator.share({ title: shown, url }); return; }
      await navigator.clipboard.writeText(url);
      toast.show(t("watch.link_copied"));
    } catch (e) {
      if ((e as Error)?.name !== "AbortError") toast.show(t("watch.share_failed"));
    }
  }, [url, shown, t, toast]);

  // Save: ask for the attachment link (the server names the file) and let the browser download it; the page stays.
  const [saving, setSaving] = useState(false);
  const save = useCallback(async () => {
    if (saving) return;
    setSaving(true);
    try {
      const { Authorization, userId } = await getAuthorizationHeader();
      if (!userId) return;
      const r = await fetch(`${apiGateway.getVideo(userId, id)}?download=1`, { headers: { Authorization, ...currentLocaleHeaders() } });
      const j = r.ok ? await r.json() : null;
      if (typeof j?.url !== "string") throw new Error("no url");
      const a = document.createElement("a");
      a.href = j.url; a.download = safeFileName(shown); a.rel = "noopener"; document.body.appendChild(a); a.click(); a.remove();
    } catch { toast.show(t("watch.load_error")); }
    finally { setSaving(false); }
  }, [id, saving, shown, t, toast]);

  const copyInfo = async () => {
    try { await navigator.clipboard.writeText(description); toast.show(t("watch.copied")); } catch { toast.show(t("watch.share_failed")); }
  };

  const newHref = "/new";
  // "Make another": the same subject, pre-filled in Create with one thing changed (the person still presses Create; nothing is made from here)
  const otherLang = locale === "es" ? "en" : "es";
  const subject = (prompt || shown).slice(0, 500);
  const againHref = (o: { aspect?: string; minutes?: number; language?: string }) => `/new?${new URLSearchParams({ prompt: subject, ...(o.aspect ? { aspect: o.aspect } : {}), ...(o.minutes ? { minutes: String(o.minutes) } : {}), ...(o.language ? { language: o.language } : {}) }).toString()}`;
  const feedbackHref = `/feedback?from=after_video&video=${encodeURIComponent(id)}`;
  const reportHref = `/feedback?from=report&kind=problem&video=${encodeURIComponent(id)}`;

  return (
    <section className="watch">
      <a className="watch-back" href="/generations" onClick={(e) => { if (document.referrer.startsWith(location.origin) && history.length > 1) { e.preventDefault(); history.back(); } }}><PIcon name="back" size={20} /><span>{t("watch.back_short")}</span></a>
      <div className="watch-grid">
        <div className="watch-main">
          <div className="watch-stage" style={{ ["--ar" as any]: String(ar) }} data-aspect={ratio ?? undefined}>
            {view.state === "ready" && url ? (
              <Player src={url} title={shown} poster={info.preview_gif_url} onMeta={setMeta} newVideoHref={newHref} />
            ) : (
              <div className="watch-state" role={view.state === "loading" || view.state === "making" ? "status" : "alert"}>
                {view.state === "loading" && <Spinner />}
                {view.state === "making" && (() => {
                  const scene = sceneCounter(view.making);
                  return (
                    <div className="watch-making">
                      <p className="watch-making-line"><AIcon name="sparkle" size={18} /><span>{view.making?.live_line || t("watch.making")}</span></p>
                      <FilmStrip tiles={stripTiles(view.making, sceneThumbs, id)} className="watch-strip" />
                      {scene && <p className="watch-making-count">{t("making.scene_counter", scene)}</p>}
                      {view.making?.narration_line && <p className="watch-making-says">“{view.making.narration_line}”</p>}
                      <p className="watch-making-leave">{t("making.leave_promise")}</p>
                    </div>
                  );
                })()}
                {view.state === "error" && <><p>{t("watch.load_error")}</p><Button variant="tonal" onClick={() => setTries((n) => n + 1)}>{t("watch.retry")}</Button></>}
                {view.state === "failed" && <><p>{t("watch.failed")}</p><a className="btn btn-tonal" href="/generations">{t("watch.back")}</a></>}
              </div>
            )}
          </div>
          <div className="watch-under">
            <div className="watch-head">
              <h1 className="watch-title" title={shown}>{shown}</h1>
              {caption && <p className="watch-meta">{caption}</p>}
            </div>
            <div className="watch-actions" role="toolbar" aria-label={shown}>
              <button type="button" className="btn btn-primary watch-share" onClick={share} disabled={!url}><PIcon name="share" size={20} />{t("watch.share")}</button>
              <IconButton label={t("watch.save")} className="action" onClick={save} disabled={!url || saving}>{saving ? <Spinner /> : <PIcon name="download" />}</IconButton>
              {info.editable && <a className="icon-btn action" href={`/edit?id=${encodeURIComponent(id)}`} aria-label={t("watch.edit")} title={t("watch.edit")}><PIcon name="edit" /></a>}
              <span className="menu-anchor">
                <button ref={moreRef} type="button" className="icon-btn action" onClick={() => setMenu((m) => !m)} aria-label={t("watch.more")} title={t("watch.more")} aria-haspopup="menu" aria-expanded={menu}><PIcon name="more" /></button>
                {menu && (
                  <div ref={menuRef} className="menu" role="menu" aria-label={t("watch.more")}>
                    <button role="menuitem" type="button" onClick={() => { setMenu(false); setSheet(true); }} disabled={!url}><PIcon name="info" size={20} />{t("watch.info")}</button>
                    <a role="menuitem" href={feedbackHref}><PIcon name="chat" size={20} />{t("watch.feedback")}</a>
                    <a role="menuitem" href={reportHref}><PIcon name="flag" size={20} />{t("watch.report")}</a>
                  </div>
                )}
              </span>
            </div>
          </div>
        </div>
        <aside className="watch-side">
          {prompt && (
            <div className="watch-prompt">
              <p className="eyebrow">{t("watch.prompt")}</p>
              <p className="watch-prompt-text">{prompt}</p>
              <a className="watch-prompt-again" href={`/new?${new URLSearchParams({ prompt: prompt.slice(0, 500) }).toString()}`}>{t("watch.prompt_again")}</a>
            </div>
          )}
          <p className="eyebrow">{t("watch.another")}</p>
          <div className="watch-chips">
            <a className="chip" href={againHref({ aspect: "9:16", minutes: 0.5 })}><AIcon name="sparkle" size={15} />{t("watch.another_short")}</a>
            <a className="chip" href={againHref({ language: otherLang })}><AIcon name="sparkle" size={15} />{t(otherLang === "es" ? "watch.another_es" : "watch.another_en")}</a>
            <a className="chip" href={againHref({})}><AIcon name="sparkle" size={15} />{t("watch.another_again")}</a>
          </div>
        </aside>
      </div>

      {sheet && (
        <Sheet title={t("watch.info_title")} onClose={() => setSheet(false)}>
          <div className="info-body">
            {description ? (
              <>
                <pre className="info-text">{description}</pre>
                <Button variant="tonal" small icon={<PIcon name="copy" size={18} />} onClick={copyInfo}>{t("watch.copy")}</Button>
              </>
            ) : <p className="muted">{t("watch.info_empty")}</p>}
          </div>
        </Sheet>
      )}
      {toast.node}
    </section>
  );
}
