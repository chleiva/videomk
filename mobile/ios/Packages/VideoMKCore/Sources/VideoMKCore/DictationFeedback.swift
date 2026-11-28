import Foundation

/// Visible feedback for dictation (docs/DICTATION_FEEDBACK_2026-11-28.md): the pure rules, the same cases as web `dictationFeedback.ts` and Android `DictationFeedback.kt`.
/// No clock and no UI here: the screen feeds in mic levels (0...1) and time.
public enum DictationFeedback {
    public static let barCount = 24            // phones; web uses 28 on a wide card
    public static let meterFPS = 25            // 20 to 30 is the budget
    public static let minBar = 0.1             // silence is a row of dots, never a gap
    public static let attack = 0.6             // fast up
    public static let release = 0.12           // slow down: calm
    public static let slowAfter = 8            // "taking longer than usual"
    public static let timeoutAfter = 60        // then Retry / device dictation
    public static let warnSoon = 30
    public static let warnFinal = 10

    /// Loudness (RMS 0...1) to bar height (minBar...1): speech sits at 0.02 to 0.3, so the curve is steep at the bottom.
    public static func barHeight(_ level: Double) -> Double {
        let v = min(1, max(0, level) * 3.2)
        return minBar + (1 - minBar) * v.squareRoot()
    }
    /// AVAudioRecorder gives average power in dB (-160...0): to linear RMS, with a floor at -50 dB (room noise).
    public static func level(fromDecibels db: Float) -> Double {
        guard db.isFinite else { return 0 }
        if db <= -50 { return 0 }
        return min(1, Double(pow(10, db / 20)))
    }
    /// m:ss
    public static func timer(_ seconds: Double) -> String {
        let t = max(0, Int(seconds.rounded(.down))); return String(format: "%d:%02d", t / 60, t % 60)
    }
    /// The nearer of the clip limit and what is left of today's allowance.
    public static func effectiveLimit(maxClip: Int, secondsLeft: Int?) -> Int { max(0, secondsLeft.map { min(maxClip, $0) } ?? maxClip) }

    public enum Warning: Equatable, Sendable { case none, soon, final }
    public static func warning(elapsed: Int, limit: Int, recording: Bool = true) -> (level: Warning, remaining: Int) {
        let remaining = max(0, limit - max(0, elapsed))
        guard recording else { return (.none, remaining) }
        return (remaining <= warnFinal ? .final : remaining <= warnSoon ? .soon : .none, remaining)
    }
    public enum Wait: Equatable, Sendable { case normal, slow, timeout }
    public static func wait(waited: Int) -> Wait { waited >= timeoutAfter ? .timeout : waited >= slowAfter ? .slow : .normal }
}

/// A scrolling level history: newest bar on the right. `push` takes the raw level once per frame.
public struct LevelMeter: Equatable, Sendable {
    public let count: Int
    private var smooth = 0.0
    public private(set) var bars: [Double]
    public init(count: Int = DictationFeedback.barCount) { self.count = count; bars = Array(repeating: DictationFeedback.minBar, count: count) }
    @discardableResult public mutating func push(_ raw: Double) -> [Double] {
        let x = raw.isFinite ? min(1, max(0, raw)) : 0
        smooth += (x - smooth) * (x > smooth ? DictationFeedback.attack : DictationFeedback.release)
        bars.removeFirst(); bars.append(DictationFeedback.barHeight(smooth)); return bars
    }
    public mutating func reset() { smooth = 0; bars = Array(repeating: DictationFeedback.minBar, count: count) }
}

public enum VoicePhase: Equatable, Sendable { case idle, requesting, recording, transcribing, failed, inserted }

/// The phase machine. Times are milliseconds. Impossible events change nothing.
public struct VoiceFeedback: Equatable, Sendable {
    public private(set) var phase: VoicePhase = .idle
    public private(set) var startedAt: Double?
    public private(set) var waitStartedAt: Double?
    public private(set) var now: Double = 0
    public private(set) var limit: Int = 360
    public private(set) var failure: String?
    public init() {}

    public enum Event: Equatable, Sendable {
        case request, granted(now: Double, limit: Int), denied, stop(now: Double), ok, fail(String), cancel, retry(now: Double), dismiss, tick(now: Double)
    }
    public mutating func apply(_ e: Event) {
        switch (e, phase) {
        case (.request, .idle), (.request, .inserted), (.request, .failed): self = VoiceFeedback(); phase = .requesting
        case (.granted(let n, let l), .requesting): phase = .recording; startedAt = n; now = n; limit = l
        case (.denied, .requesting), (.denied, .recording): self = VoiceFeedback()
        case (.stop(let n), .recording): phase = .transcribing; waitStartedAt = n; now = max(now, n)
        case (.ok, .transcribing): phase = .inserted
        case (.fail(let k), .transcribing): phase = .failed; failure = k
        case (.cancel, .recording), (.cancel, .transcribing), (.cancel, .requesting): self = VoiceFeedback()
        case (.retry(let n), .failed): phase = .transcribing; waitStartedAt = n; now = max(now, n); failure = nil
        case (.dismiss, .failed), (.dismiss, .inserted): self = VoiceFeedback()
        case (.tick(let n), _): now = max(now, n)
        default: break
        }
    }
    public var elapsed: Int { startedAt.map { max(0, Int(((now - $0) / 1000).rounded(.down))) } ?? 0 }
    public var waited: Int { waitStartedAt.map { max(0, Int(((now - $0) / 1000).rounded(.down))) } ?? 0 }
    public var warning: (level: DictationFeedback.Warning, remaining: Int) { DictationFeedback.warning(elapsed: elapsed, limit: limit, recording: phase == .recording) }
    public var wait: DictationFeedback.Wait { phase == .transcribing ? DictationFeedback.wait(waited: waited) : .normal }
    /// What the screen reader says: changes only at thresholds, never per tick (nil = nothing).
    public var announcement: String? {
        switch phase {
        case .recording: let w = warning.level; return w == .final ? "warn_final" : w == .soon ? "warn_soon" : "listening"
        case .transcribing: return wait == .slow ? "slow" : "transcribing"
        case .failed: return "failed"
        case .inserted: return "inserted"
        default: return nil
        }
    }
}
