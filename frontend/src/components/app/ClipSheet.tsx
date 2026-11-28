// "Add a video" (docs/VIDEO_UPLOAD_CLIENTS_2026-11-28.md section 3): ONE dialog before anything is uploaded, with the notice (only the first 5 seconds are used) and the sound question,
// which has no default: the person must choose. A file over the size limit is cut to its first 5 seconds on this device first (MediaRecorder) where the browser can; else it is blocked with one clear line.
import "../../styles/clips.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { Sheet, Spinner } from "../ui";
import { AIcon as Icon } from "./icons";
import { canTrimInBrowser, probeVideo, trimClip } from "../../lib/localVideo";
import type { Probe } from "../../lib/localVideo";
import { contentTypeOf, formatMB, longerThanUsed, needsTrim, precheck } from "../../lib/videoClips";
import type { PreKind, VideoUploadCaps } from "../../lib/videoClips";

export interface ClipPick { blob: Blob; name: string; contentType: string; useAudio: boolean; poster?: string; aspect?: number; trimmedLocally: boolean }
type T = (k: string, v?: Record<string, string | number>) => string;

const PRE_KEY: Record<PreKind, string> = { type: "create.clip_pre_type", too_big: "create.clip_err_too_big", too_long: "create.clip_pre_too_long", empty: "create.clip_pre_empty" };

export default function ClipSheet({ file, caps, t, onCancel, onChooseAnother, onAdd }: { file: File; caps: VideoUploadCaps; t: T; onCancel: () => void; onChooseAnother: () => void; onAdd: (p: ClipPick) => void }) {
  const [probe, setProbe] = useState<Probe | null>(null);
  const [sound, setSound] = useState<boolean | null>(null);
  const [askSound, setAskSound] = useState(false);   // pressed Add without choosing: the line under the question says so
  const [trim, setTrim] = useState<{ pct: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ctl = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const trimOk = useMemo(() => canTrimInBrowser(), []);
  useEffect(() => { alive.current = true; void probeVideo(file).then((p) => { if (alive.current) setProbe(p); else if (p.poster) URL.revokeObjectURL(p.poster); }); return () => { alive.current = false; ctl.current?.abort(); }; }, [file]);

  const duration = probe?.duration ?? null;
  const block = precheck({ size: file.size, type: file.type, name: file.name, duration }, caps, trimOk);
  const trimNeeded = block === null && needsTrim(file.size, caps);
  const noAudio = probe?.hasAudio === false;   // the browser can see there is no sound: the question is not asked (silent)
  const limit = formatMB(caps.maxBytes);
  const used = caps.usedSeconds;

  async function add() {
    if (block || trim) return;
    if (!noAudio && sound === null) { setAskSound(true); return; }
    const useAudio = noAudio ? false : sound === true;
    const base = { name: file.name, useAudio, poster: probe?.poster ?? undefined, aspect: probe?.aspect ?? undefined };
    setError(null);
    if (!trimNeeded) { onAdd({ ...base, blob: file, contentType: contentTypeOf(file, caps.formats) ?? "video/mp4", trimmedLocally: false }); return; }
    ctl.current = new AbortController();
    setTrim({ pct: 0 });
    const r = await trimClip(file, { seconds: used, withAudio: useAudio, maxBytes: caps.maxBytes, onProgress: (pct) => alive.current && setTrim({ pct }), signal: ctl.current.signal });
    if (!alive.current) return;
    if (r.ok) { onAdd({ ...base, blob: r.blob, contentType: r.contentType, trimmedLocally: true }); return; }
    setTrim(null);
    if (r.reason !== "cancelled") setError(t(r.reason === "still_big" ? "create.clip_err_too_big" : "create.clip_prep_failed", { limit }));
  }
  const cantTrim = needsTrim(file.size, caps) && !trimOk && block === null;
  const hard = block ? t(PRE_KEY[block], { limit }) : cantTrim ? t("create.clip_err_too_big", { limit }) : null;

  return (
    <Sheet title={t("create.clip_sheet_title")} onClose={onCancel}>
      <div className="clip-sheet">
        <div className="clip-pre">
          <span className="clip-pre-img" style={probe?.aspect ? ({ aspectRatio: String(Math.min(2, Math.max(0.5, probe.aspect))) } as React.CSSProperties) : undefined}>
            {probe?.poster ? <img src={probe.poster} alt="" /> : probe === null ? <Spinner /> : <Icon name="film" size={26} />}
          </span>
          <span className="clip-pre-meta"><span className="clip-pre-name">{file.name}</span><span className="clip-pre-sub">{duration ? `${Math.max(1, Math.round(duration))} s · ` : ""}{formatMB(file.size)}</span></span>
        </div>

        {hard ? (
          <>
            <p className="notice notice-bad" role="alert"><Icon name="warning" size={20} /><span>{hard}</span></p>
            <div className="clip-actions"><button type="button" className="btn btn-primary" data-autofocus onClick={onChooseAnother}>{t("create.clip_another")}</button><button type="button" className="btn btn-quiet" onClick={onCancel}>{t("create.cancel")}</button></div>
          </>
        ) : (
          <>
            <p className="notice notice-info clip-first5"><Icon name="info" size={20} /><span>{longerThanUsed(duration, used) ? t("create.clip_first5_long", { n: Math.round(duration!) }) : t("create.clip_first5")}</span></p>
            {trimNeeded && <p className="hint">{t("create.clip_trim_note", { size: formatMB(file.size), limit })}</p>}

            {!noAudio && (
              <fieldset className="clip-q" aria-describedby={askSound ? "clip-q-ask" : undefined} disabled={!!trim}>
                <legend className="clip-q-t">{t("create.clip_sound_q")}</legend>
                <div className="clip-choices" role="radiogroup" aria-label={t("create.clip_sound_q")}>
                  {([[true, "create.clip_sound_yes", "volume"], [false, "create.clip_sound_no", "volumeoff"]] as const).map(([v, k, ic]) => (
                    <label key={String(v)} className={`clip-choice ${sound === v ? "is-on" : ""}`}>
                      <input type="radio" name="clip-sound" className="clip-radio" checked={sound === v} onChange={() => { setSound(v); setAskSound(false); }} data-autofocus={v ? true : undefined} />
                      <span className="clip-choice-ic" aria-hidden="true"><Icon name={ic} size={20} /></span><span className="clip-choice-t">{t(k)}</span>
                    </label>
                  ))}
                </div>
                {sound === true && <p className="hint clip-help" id="clip-help">{t("create.clip_sound_help")}</p>}
                {askSound && <p className="hint hint-bad" id="clip-q-ask" role="alert">{t("create.clip_choose_first")}</p>}
              </fieldset>
            )}

            <p className="clip-privacy">{t("create.clip_privacy")}{sound === true && <> {t("create.clip_privacy_sound")} <a href="/privacy" target="_blank" rel="noopener">{t("create.clip_privacy_link")}</a></>}</p>
            {error && <p className="notice notice-bad" role="alert"><Icon name="warning" size={20} /><span>{error}</span></p>}

            {trim ? (
              <div className="clip-trim" role="status">
                <div className="clip-trim-bar" aria-hidden="true"><i style={{ width: `${trim.pct}%` }} /></div>
                <span>{t("create.clip_preparing", { pct: trim.pct })}</span>
                <button type="button" className="btn btn-line btn-sm" onClick={() => ctl.current?.abort()}>{t("create.cancel")}</button>
              </div>
            ) : (
              <div className="clip-actions">
                <button type="button" className="btn btn-primary" aria-disabled={(!noAudio && sound === null) || undefined} onClick={() => void add()}>{t("create.clip_add")}</button>
                <button type="button" className="btn btn-quiet" onClick={onCancel}>{t("create.cancel")}</button>
              </div>
            )}
          </>
        )}
      </div>
    </Sheet>
  );
}
