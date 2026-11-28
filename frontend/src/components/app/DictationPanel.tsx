// The dictation panel (docs/DICTATION_FEEDBACK_2026-11-28.md): replaces the pills and tool row while the mic is working, so it can never be mistaken for idle.
// Recording = live bars from the real mic level + timer + red dot + big Stop + Cancel. Transcribing = calm sweeping bars in the brand colour. Failed = Retry or keep the device's words.
import { useEffect, useRef } from "react";
import { AIcon as Icon } from "./icons";
import { BAR_COUNT, formatTimer } from "../../lib/dictationFeedback";
import type { LevelMeter, Warning } from "../../lib/dictationFeedback";

export interface PanelProps {
  phase: "recording" | "transcribing" | "failed";
  engine: "better" | "native";          // native = the browser's own recognizer: no level, so a pulsing mic
  meter: LevelMeter;
  elapsedS: number; remainingS: number; warning: Warning; slow: boolean;
  t: (k: string, v?: Record<string, string | number>) => string;
  onStop: () => void; onCancel: () => void; onRetry: () => void; onDevice: () => void;
}
const BARS = Array.from({ length: BAR_COUNT }, (_, i) => i);

export default function DictationPanel(p: PanelProps) {
  const bars = useRef<(HTMLSpanElement | null)[]>([]);
  // draw at 25 fps straight into the DOM (no React render per frame); CSS eases the 40 ms steps
  useEffect(() => {
    if (p.phase !== "recording" || p.engine !== "better") return;
    const draw = () => { const h = p.meter.heights(); bars.current.forEach((el, i) => { if (el) el.style.transform = `scaleY(${h[i] ?? 0.1})`; }); };
    draw(); const id = setInterval(draw, 40); return () => clearInterval(id);
  }, [p.phase, p.engine, p.meter]);
  const { t } = p;
  const label = p.phase === "recording" ? (p.warning === "none" ? t("create.voice_listening") : t("create.voice_left", { s: p.remainingS })) : p.phase === "transcribing" ? (p.slow ? t("create.voice_slow") : t("create.voice_transcribing")) : t("create.voice_failed");
  return (
    <div className="voice-panel" data-phase={p.phase} data-warn={p.warning} role="group" aria-label={p.phase === "recording" ? t("create.voice_rec_a11y", { time: formatTimer(p.elapsedS) }) : label}>
      {p.phase === "failed" ? (
        <>
          <div className="voice-mid">
            <div className="voice-meta"><Icon name="warning" size={18} className="voice-warn-ic" /><span className="voice-label">{label}</span></div>
            <div className="voice-actions">
              <button type="button" className="btn btn-tonal btn-sm" onClick={p.onRetry}>{t("create.voice_retry")}</button>
              <button type="button" className="btn btn-quiet btn-sm" onClick={p.onDevice}>{t("create.voice_device")}</button>
            </div>
          </div>
        </>
      ) : (
        <>
          <button type="button" className="voice-cancel" onClick={p.onCancel} aria-label={t("create.voice_cancel")}><span className="voice-cancel-t">{t("create.voice_cancel")}</span><Icon name="close" size={20} className="voice-cancel-x" /></button>
          <div className="voice-mid">
            {p.engine === "better" || p.phase === "transcribing" ? (
              <div className={`voice-wave ${p.phase === "transcribing" ? "is-wait" : ""}`} aria-hidden="true">
                {BARS.map((i) => <span key={i} ref={(el) => { bars.current[i] = el; }} style={{ "--i": i } as React.CSSProperties} />)}
              </div>
            ) : (
              <div className="voice-pulse" aria-hidden="true"><Icon name="mic" size={22} /></div>
            )}
            <div className="voice-meta">
              <span className="voice-dot" aria-hidden="true" />
              <span className="voice-label">{label}</span>
              {p.phase === "recording" && <span className="voice-time" aria-hidden="true">{formatTimer(p.elapsedS)}</span>}
            </div>
          </div>
          {p.phase === "recording"
            ? <button type="button" className="voice-stop" onClick={p.onStop} aria-label={p.engine === "better" ? t("create.voice_stop") : t("create.voice_stop_native")} title={p.engine === "better" ? t("create.voice_stop") : t("create.voice_stop_native")}><Icon name="stop" size={22} /></button>
            : <span className="voice-busy" aria-hidden="true"><i /></span>}
        </>
      )}
    </div>
  );
}
