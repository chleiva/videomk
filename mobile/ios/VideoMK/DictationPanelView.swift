import SwiftUI
import VideoMKCore

/// The voice panel (docs/DICTATION_FEEDBACK_2026-11-28.md): replaces the pills and tool row while the mic works.
/// Recording: red dot, bars from the REAL input level (`AVAudioRecorder` metering), m:ss, a 52 pt Stop and Cancel. Transcribing: the same bars settle to a slow
/// sweep in the brand colour, a spinner replaces Stop. Failed: Retry or the phone's own dictation. HIG: system haptics at the moments that matter, Reduce Motion
/// gives a still ramp, 44 pt targets, Dynamic Type capped at accessibility1 like the dock, VoiceOver gets one group and polite announcements.
struct DictationPanelView: View {
    let dictation: BetterDictation
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var scheme
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let f = dictation.feedback
        Group {
            if f.phase == .failed { failed } else { live(f) }
        }
        .padding(.horizontal, Theme.Space.m).padding(.vertical, Theme.Space.s)
        .frame(maxWidth: .infinity, minHeight: 72)
        .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: f.phase == .failed ? 28 : 36, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: f.phase == .failed ? 28 : 36, style: .continuous).strokeBorder(Theme.outline, lineWidth: 1))
        .accessibilityElement(children: .contain).accessibilityIdentifier("dictationPanel")
    }

    private func live(_ f: VoiceFeedback) -> some View {
        let recording = f.phase == .recording
        let warn = f.warning
        let cancel = Button { dictation.discard() } label: {
            Text(tr("voice.cancel")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.textSecondary).lineLimit(1).minimumScaleFactor(0.7)
                .padding(.horizontal, Theme.Space.s).frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Rectangle())
        }
        .buttonStyle(.plain).accessibilityIdentifier("voiceCancel")
        let trailing = Group {
            if recording {
                Button { dictation.stop() } label: {
                    Image(systemName: "stop.fill").font(.system(size: 20, weight: .semibold)).foregroundStyle(Theme.background).frame(width: 52, height: 52).background(Theme.danger, in: Circle())
                }
                .buttonStyle(.plain).accessibilityLabel(dictation.engineIsBetter ? tr("voice.stop") : tr("voice.stop_native")).accessibilityIdentifier("voiceStop")
            } else {
                LiveSpinner(size: 24).frame(width: 52, height: 52)
            }
        }
        let graphic = Group { if dictation.engineIsBetter || !recording { bars(recording: recording).frame(height: 28) } else { pulsingMic } }
        let status = HStack(spacing: Theme.Space.s) {
            Circle().fill(recording ? Theme.danger : Theme.primary).frame(width: 8, height: 8).accessibilityHidden(true)
            Text(statusLine(f, recording: recording, warn: warn)).font(.role(.subhead, weight: .semibold)).foregroundStyle(statusColor(recording: recording, warn: warn.level)).lineLimit(typeSize.isAccessibilitySize ? 3 : 1).minimumScaleFactor(typeSize.isAccessibilitySize ? 1 : 0.8).fixedSize(horizontal: false, vertical: typeSize.isAccessibilitySize)
            Spacer(minLength: 0)
            if recording { Text(DictationFeedback.timer(Double(f.elapsed))).font(.role(.subhead, weight: .semibold)).monospacedDigit().foregroundStyle(Theme.text).accessibilityHidden(true) }
        }
        return Group {
            if typeSize.isAccessibilitySize {      // big text: bars, then the words, then the two buttons on their own row (nothing hyphenates)
                VStack(spacing: Theme.Space.s) {
                    graphic; status
                    HStack { cancel; Spacer(minLength: 0); trailing }
                }
            } else {
                HStack(spacing: Theme.Space.m) {
                    cancel
                    VStack(alignment: .leading, spacing: 4) { graphic; status }.frame(maxWidth: .infinity)
                    trailing
                }
            }
        }
        .accessibilityElement(children: .contain)
    }

    private func statusLine(_ f: VoiceFeedback, recording: Bool, warn: (level: DictationFeedback.Warning, remaining: Int)) -> String {
        if recording { return warn.level == .none ? tr("voice.listening") : tr("voice.left", warn.remaining) }
        return f.wait == .normal ? tr("voice.transcribing") : tr("voice.slow")
    }
    private func statusColor(recording: Bool, warn: DictationFeedback.Warning) -> Color {
        guard recording else { return Theme.textSecondary }
        return warn == .final ? Theme.danger : warn == .soon ? Theme.warning : Theme.textSecondary
    }

    /// 24 bars, newest on the right. Recording: heights follow the level. Transcribing: calm sweep (a still ramp with Reduce Motion).
    private func bars(recording: Bool) -> some View {
        TimelineView(.animation(minimumInterval: 1.0 / Double(DictationFeedback.meterFPS), paused: reduceMotion && !recording)) { ctx in
            let t = ctx.date.timeIntervalSinceReferenceDate
            Canvas { gc, size in
                let n = DictationFeedback.barCount, w: CGFloat = 3, gap = (size.width - w * CGFloat(n)) / CGFloat(max(1, n - 1))
                let bars = dictation.meter.bars
                for i in 0..<n {
                    let h: Double
                    if recording { h = bars[i] }
                    else if reduceMotion { h = 0.2 + 0.25 * Double(i) / Double(n) }
                    else { let p = (t / 2.4 - Double(i) * 0.025).truncatingRemainder(dividingBy: 1); h = 0.22 + 0.38 * max(0, sin(p * .pi * 2) * 0.5 + 0.5) * (p < 0.6 ? 1 : 0.0) }
                    let bh = max(3, size.height * h)
                    let r = CGRect(x: CGFloat(i) * (w + gap), y: (size.height - bh) / 2, width: w, height: bh)
                    gc.fill(Path(roundedRect: r, cornerRadius: 1.5), with: .color(recording ? Theme.danger : Theme.primary))
                }
            }
        }
        .accessibilityHidden(true)
    }

    /// Phone dictation exposes no level: a mic with a soft ring, so it is still clearly listening.
    private var pulsingMic: some View {
        HStack {
            TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { ctx in
                let p = reduceMotion ? 0 : ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.6) / 1.6
                ZStack {
                    Circle().stroke(Theme.danger.opacity(0.5 * (1 - p)), lineWidth: 2).frame(width: 24, height: 24).scaleEffect(1 + 0.2 * p)
                    Image(systemName: "mic.fill").font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.danger)
                }
                .frame(width: 28, height: 28)
            }
            Spacer(minLength: 0)
        }
        .frame(height: 28).accessibilityHidden(true)
    }

    private var failed: some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) {
            HStack(spacing: Theme.Space.s) {
                Image(systemName: "exclamationmark.triangle").font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.warning).accessibilityHidden(true)
                Text(tr("voice.failed")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: Theme.Space.s) {
                Button { dictation.retry() } label: {
                    Text(tr("voice.retry")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.primary).multilineTextAlignment(.center).frame(maxWidth: .infinity, minHeight: Theme.minTouch).background(Theme.primaryContainer, in: Capsule())
                }
                .buttonStyle(.plain).accessibilityIdentifier("voiceRetry")
                Button { dictation.useDeviceDictation() } label: {
                    Text(tr("voice.device")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, minHeight: Theme.minTouch).background(Theme.surface, in: Capsule())
                }
                .buttonStyle(.plain).accessibilityIdentifier("voiceDevice")
            }
        }
    }
}
