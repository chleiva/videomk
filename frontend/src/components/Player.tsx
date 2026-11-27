// The video player of the watch page: our own controls (icons only, no text) over a plain <video>. Keyboard shortcuts, scrubber, volume, speed, picture in picture,
// full screen, captions when the file has a track, an end card, and controls that rest after 3 s of playback. Logic in lib/player.ts (tested).
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { PIcon } from "./PlayerIcons";
import { Spinner } from "./ui";
import { actionForKey, clampTime, formatClock, nextSpeed, speedLabel } from "../lib/player";
import type { PlayerAction } from "../lib/player";
import { useLocale } from "../lib/useLocale";

export interface PlayerMeta { width: number; height: number; duration: number }
interface Props {
  src: string;
  title: string;
  poster?: string | null;
  onMeta?: (m: PlayerMeta) => void;
  /** The end card's "new video" action (a link target); the replay button is built in. */
  newVideoHref: string;
}

const HIDE_AFTER_MS = 3000;

export default function Player({ src, title, poster, onMeta, newVideoHref }: Props) {
  const { t } = useLocale();
  const box = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const hideTimer = useRef<number | undefined>(undefined);
  const [playing, setPlaying] = useState(false);
  const [started, setStarted] = useState(false);
  const [ended, setEnded] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [full, setFull] = useState(false);
  const [showBar, setShowBar] = useState(true);
  const [hasCaptions, setHasCaptions] = useState(false);
  const [captionsOn, setCaptionsOn] = useState(false);
  const pipOk = useMemo(() => typeof document !== "undefined" && !!(document as any).pictureInPictureEnabled, []);
  const [pipOn, setPipOn] = useState(false);

  const wake = useCallback(() => {
    setShowBar(true);
    window.clearTimeout(hideTimer.current);
    const v = video.current;
    if (v && !v.paused && !v.ended) hideTimer.current = window.setTimeout(() => { if (!box.current?.contains(document.activeElement) || !(document.activeElement as HTMLElement)?.matches?.(":focus-visible")) setShowBar(false); }, HIDE_AFTER_MS);
  }, []);
  useEffect(() => () => window.clearTimeout(hideTimer.current), []);

  const toggle = useCallback(() => {
    const v = video.current; if (!v) return;
    if (v.ended) v.currentTime = 0;
    if (v.paused) v.play().catch(() => {}); else v.pause();
  }, []);
  const seekBy = (by: number) => { const v = video.current; if (v) v.currentTime = clampTime(v.currentTime + by, v.duration); };
  const setVol = (n: number) => { const v = video.current; if (!v) return; const x = Math.min(1, Math.max(0, n)); v.volume = x; v.muted = x === 0; };
  const toggleMute = () => { const v = video.current; if (v) v.muted = !v.muted; };
  const cycleSpeed = (dir: 1 | -1 = 1) => {
    const v = video.current; if (!v) return;
    const next = dir === 1 ? nextSpeed(v.playbackRate) : (() => { let r = v.playbackRate; for (let i = 0; i < 4; i++) r = nextSpeed(r); return r; })();   // four forward steps in a cycle of five = one back
    v.playbackRate = next; setRate(next);
  };
  const toggleFull = () => {
    const el = box.current as any, v = video.current as any;
    const d = document as any;
    if (d.fullscreenElement || d.webkitFullscreenElement) { (d.exitFullscreen || d.webkitExitFullscreen)?.call(d); return; }
    if (el?.requestFullscreen) el.requestFullscreen().catch(() => {});
    else if (el?.webkitRequestFullscreen) el.webkitRequestFullscreen();
    else v?.webkitEnterFullscreen?.();   // iPhone Safari: only the video itself can go full screen
  };
  const togglePip = async () => {
    const v = video.current as any, d = document as any;
    try { if (d.pictureInPictureElement) await d.exitPictureInPicture(); else await v?.requestPictureInPicture?.(); } catch { /* not allowed right now */ }
  };
  const toggleCaptions = () => {
    const v = video.current; if (!v) return;
    const on = !captionsOn;
    for (const tr of Array.from(v.textTracks)) tr.mode = on ? "showing" : "hidden";
    setCaptionsOn(on);
  };

  const run = (a: PlayerAction) => {
    const v = video.current; if (!v) return;
    switch (a.type) {
      case "toggle": toggle(); break;
      case "seek": seekBy(a.by); break;
      case "seekTo": if (Number.isFinite(v.duration)) v.currentTime = v.duration * a.fraction; break;
      case "volume": setVol(v.volume + a.by); break;
      case "mute": toggleMute(); break;
      case "fullscreen": toggleFull(); break;
      case "pip": if (pipOk) void togglePip(); break;
      case "captions": if (hasCaptions) toggleCaptions(); break;
      case "speed": cycleSpeed(a.direction); break;
    }
  };

  const onKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const el = e.target as HTMLElement;
    const a = actionForKey({ key: e.key, shiftKey: e.shiftKey, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, targetTag: el.tagName, targetEditable: el.isContentEditable });
    if (!a) { wake(); return; }
    e.preventDefault(); wake(); run(a);
  };

  useEffect(() => {
    const onFs = () => setFull(!!((document as any).fullscreenElement || (document as any).webkitFullscreenElement));
    document.addEventListener("fullscreenchange", onFs); document.addEventListener("webkitfullscreenchange", onFs);
    return () => { document.removeEventListener("fullscreenchange", onFs); document.removeEventListener("webkitfullscreenchange", onFs); };
  }, []);

  const buffered = () => { const v = video.current; if (!v || !v.buffered.length) return 0; return v.buffered.end(v.buffered.length - 1); };
  const [bufEnd, setBufEnd] = useState(0);
  const pct = duration > 0 ? Math.min(100, (current / duration) * 100) : 0;
  const bufPct = duration > 0 ? Math.min(100, (bufEnd / duration) * 100) : 0;
  const barVisible = showBar || !playing || ended;

  return (
    <div ref={box} className={`player${barVisible ? "" : " player-rest"}${full ? " player-full" : ""}${ended ? " player-ended" : ""}`} role="group" aria-label={t("player.region", { title })}
      tabIndex={0} onKeyDown={onKey} onMouseMove={wake} onTouchStart={wake} onFocus={wake}>
      <video
        ref={video} src={src} poster={poster || undefined} playsInline preload="metadata" aria-label={title}
        onClick={() => { wake(); toggle(); }} onDoubleClick={toggleFull}
        onLoadedMetadata={(e) => {
          const v = e.currentTarget;
          setDuration(Number.isFinite(v.duration) ? v.duration : 0);
          setHasCaptions(v.textTracks.length > 0);
          onMeta?.({ width: v.videoWidth, height: v.videoHeight, duration: Number.isFinite(v.duration) ? v.duration : 0 });
        }}
        onDurationChange={(e) => setDuration(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : 0)}
        onTimeUpdate={(e) => { setCurrent(e.currentTarget.currentTime); setBufEnd(buffered()); }}
        onProgress={() => setBufEnd(buffered())}
        onPlay={() => { setPlaying(true); setStarted(true); setEnded(false); wake(); }}
        onPause={() => { setPlaying(false); setShowBar(true); window.clearTimeout(hideTimer.current); }}
        onEnded={() => { setEnded(true); setPlaying(false); setShowBar(true); }}
        onWaiting={() => setWaiting(true)} onPlaying={() => setWaiting(false)} onCanPlay={() => setWaiting(false)}
        onVolumeChange={(e) => { setVolume(e.currentTarget.volume); setMuted(e.currentTarget.muted); }}
        onRateChange={(e) => setRate(e.currentTarget.playbackRate)}
        onEnterPictureInPicture={() => setPipOn(true)} onLeavePictureInPicture={() => setPipOn(false)}
      />

      {!started && !ended && (
        <button type="button" className="player-big" onClick={() => { toggle(); wake(); }} aria-label={t("player.play")}><PIcon name="play" size={34} /></button>
      )}
      {waiting && playing && <span className="player-wait" role="status" aria-label={t("player.loading")}><Spinner /></span>}

      {ended && (
        <div className="player-end">
          <button type="button" className="player-circle" onClick={toggle} aria-label={t("watch.replay")} title={t("watch.replay")}><PIcon name="replay" size={26} /></button>
          <a className="btn btn-primary" href={newVideoHref}><PIcon name="plus" size={18} />{t("watch.new_video")}</a>
        </div>
      )}

      <div className="player-bar" aria-hidden={!barVisible ? true : undefined}>
        <input
          type="range" className="player-seek" min={0} max={duration || 0} step={0.1} value={Math.min(current, duration || 0)} disabled={!duration}
          aria-label={t("player.seek")} aria-valuetext={t("player.seek_value", { current: formatClock(current), total: formatClock(duration) })}
          style={{ ["--p" as any]: `${pct}%`, ["--b" as any]: `${bufPct}%` }}
          onChange={(e) => { const v = video.current; if (v) v.currentTime = Number(e.target.value); setCurrent(Number(e.target.value)); }}
          tabIndex={barVisible ? 0 : -1}
        />
        <div className="player-row">
          <button type="button" className="player-btn" onClick={toggle} aria-label={playing ? t("player.pause") : t("player.play")} tabIndex={barVisible ? 0 : -1}><PIcon name={playing ? "pause" : "play"} /></button>
          <span className="player-time" aria-hidden="true">{formatClock(current)} / {formatClock(duration)}</span>
          <span className="player-spacer" />
          <span className="player-volume">
            <button type="button" className="player-btn" onClick={toggleMute} aria-label={muted || volume === 0 ? t("player.unmute") : t("player.mute")} tabIndex={barVisible ? 0 : -1}><PIcon name={muted || volume === 0 ? "mute" : "volume"} /></button>
            <input type="range" className="player-vol" min={0} max={1} step={0.05} value={muted ? 0 : volume} aria-label={t("player.volume")} onChange={(e) => setVol(Number(e.target.value))} style={{ ["--p" as any]: `${(muted ? 0 : volume) * 100}%` }} tabIndex={barVisible ? 0 : -1} />
          </span>
          <button type="button" className="player-btn player-rate" onClick={() => cycleSpeed(1)} aria-label={`${t("player.speed")}: ${speedLabel(rate)}`} tabIndex={barVisible ? 0 : -1}>{speedLabel(rate)}</button>
          {hasCaptions && <button type="button" className="player-btn" onClick={toggleCaptions} aria-pressed={captionsOn} aria-label={t("player.captions")} tabIndex={barVisible ? 0 : -1}><PIcon name="captions" /></button>}
          {pipOk && <button type="button" className="player-btn" onClick={togglePip} aria-pressed={pipOn} aria-label={t("player.pip")} tabIndex={barVisible ? 0 : -1}><PIcon name="pip" /></button>}
          <button type="button" className="player-btn" onClick={toggleFull} aria-label={full ? t("player.exit_fullscreen") : t("player.fullscreen")} tabIndex={barVisible ? 0 : -1}><PIcon name={full ? "exitFullscreen" : "fullscreen"} /></button>
        </div>
      </div>
    </div>
  );
}
