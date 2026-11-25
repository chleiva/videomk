import Foundation

/// How one tile of the upload batch looks. The queue item is the truth; `listed` says whether the server already lists the photo.
public enum UploadTileState: Equatable, Sendable {
    case queued, uploading, processing, done, failed, alreadyThere, waiting
}

public enum UploadTiles {
    public static func state(of item: QueueItem, paused: Bool, offline: Bool, listed: Bool) -> UploadTileState {
        switch item.state {
        case .queued: paused || offline ? .waiting : .queued
        case .uploading: .uploading
        case .done: listed ? .done : .processing
        case .duplicate: .alreadyThere
        case .noSpace: .waiting
        case .failed: .failed
        }
    }

    /// Whether the batch is over for the grid: everything is terminal and every uploaded photo is listed. Then the "Adding N photos"
    /// section folds into the normal timeline.
    public static func isSettled(_ items: [QueueItem], listedIDs: Set<String>) -> Bool {
        !items.isEmpty && items.allSatisfy { i in
            switch i.state {
            case .queued, .uploading: false
            case .done: i.libraryID.map(listedIDs.contains) ?? false
            case .duplicate, .failed, .noSpace: true
            }
        }
    }

    /// Few processing tiles: show the "Getting it ready" label too; many: only the shimmer.
    public static func showsProcessingLabel(processingCount: Int) -> Bool { processingCount <= 12 }
}

/// The one persistent upload bar (collapsed row and expanded panel).
public struct UploadBarState: Equatable, Sendable {
    public enum Kind: Sendable, Equatable { case uploading, paused, offline, storageFull, needsAttention, finished }
    public let kind: Kind
    public let title: String
    public let subtitle: String
    public let fraction: Double
    public let added: Int, gettingReady: Int, waiting: Int, needYou: Int

    public static func make(_ p: QueueProgress, gettingReady: Int = 0, elapsed: TimeInterval? = nil) -> UploadBarState? {
        guard !p.isEmpty else { return nil }
        let uploaded = p.done + p.duplicates
        let fraction = Double(p.processed) / Double(max(p.total, 1))
        let waitingCount = p.queued + p.uploading + p.noSpace
        func make(_ kind: Kind, _ title: String, _ sub: String) -> UploadBarState {
            UploadBarState(kind: kind, title: title, subtitle: sub, fraction: fraction, added: uploaded, gettingReady: gettingReady, waiting: waitingCount, needYou: p.failed)
        }
        let storageFull = p.noSpace > 0 && p.queued == 0 && p.uploading == 0
        if storageFull {
            return make(.storageFull, "Your storage is full", "\(ComposerPlan.plural(p.noSpace, "photo")) \(p.noSpace == 1 ? "is" : "are") waiting. Free up space and they will carry on by themselves.")
        }
        if p.isFinished { return make(p.failed > 0 ? .needsAttention : .finished, p.failed > 0 ? "\(p.failed) need you" : "Done", p.failed > 0 ? "\(ComposerPlan.plural(uploaded, "photo")) added" : "") }
        if p.paused && p.lastError != nil || p.lastError != nil {
            return make(.offline, "Waiting for a connection", "\(ComposerPlan.plural(p.queued + p.uploading, "photo")) will upload automatically")
        }
        if p.paused {
            return make(.paused, "Paused · \(uploaded) of \(p.total)", p.uploading > 0 ? "Pausing after the current photos" : "Resume when you're ready")
        }
        return make(.uploading, "Uploading \(uploaded) of \(p.total)", leftText(p, elapsed: elapsed))
    }

    static func leftText(_ p: QueueProgress, elapsed: TimeInterval?) -> String {
        let left = max(0, p.totalBytes - p.doneBytes)
        var text = "\(StorageMeter.format(left)) left"
        if let elapsed, elapsed > 5, p.doneBytes > 0 {
            let seconds = Double(left) / (Double(p.doneBytes) / elapsed)
            text += " · " + (seconds < 60 ? "less than a minute" : "about \(Int((seconds / 60).rounded(.up))) min")
        }
        return text
    }
}

/// The one summary per batch.
public enum UploadSummary {
    public struct Message: Equatable, Sendable { public let text: String; public let action: String? }

    public static func message(_ p: QueueProgress) -> Message? {
        guard p.isFinished else { return nil }
        var text: String
        if p.done > 0 { text = "\(ComposerPlan.plural(p.done, "photo")) added." }
        else if p.duplicates > 0 { text = "" }
        else { return p.failed > 0 ? Message(text: "\(ComposerPlan.plural(p.failed, "photo")) need your attention.", action: "Review") : nil }
        if p.failed > 0 { text += " \(p.failed) \(p.failed == 1 ? "needs" : "need") your attention." }
        else if p.duplicates > 0 { text += (text.isEmpty ? "" : " ") + "\(p.duplicates) \(p.duplicates == 1 ? "was" : "were") already there." }
        return Message(text: text, action: p.failed > 0 ? "Review" : "Got it")
    }
}

/// The honest "Making" card: four named steps, a line that says what is happening, and a time left. The server reports stages, not scenes.
public enum MakingProgress {
    public static let steps = ["Script", "Voice", "Pictures", "Final cut"]
    // Where each step ends on the overall 0...1 estimate (matches ProgressEstimator's slices).
    static let edges: [Double] = [0.22, 0.42, 0.62, 1.0]

    public struct Info: Equatable, Sendable {
        public let segments: [Double]      // fill of each step, 0...1
        public let current: Int
        public let line: String
    }

    public static func info(stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double) -> Info {
        let f = ProgressEstimator.fraction(stage: stage, secondsInStage: secondsInStage, minutes: minutes)
        var lo = 0.0
        var segs: [Double] = []
        for e in edges { segs.append(min(1, max(0, (f - lo) / (e - lo)))); lo = e }
        let current = min(edges.count - 1, edges.firstIndex { f < $0 } ?? edges.count - 1)
        let what: String
        switch stage {
        case .starting: what = "Getting started."
        case .writing: what = "Writing the script."
        case .voiceAndVisuals: what = "Recording the voice and drawing the pictures."
        case .rendering: what = "Putting it all together."
        }
        return Info(segments: segs, current: current, line: "\(what) \(timeLeft(stage: stage, secondsInStage: secondsInStage, minutes: minutes))")
    }

    /// Remaining of the typical stage times; rounded up to whole minutes, never "0 min".
    public static func timeLeft(stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double) -> String {
        var left = max(0, ProgressEstimator.expectedSeconds(stage, minutes: minutes) - secondsInStage)
        for s in VideoStatus.Stage.allCases where s > stage { left += ProgressEstimator.expectedSeconds(s, minutes: minutes) }
        if left < 60 { return "Less than a minute left." }
        return "About \(Int((left / 60).rounded(.up))) min left."
    }
}

/// Screen-reader progress for uploads: one polite message, at most every 10 % of the batch AND not more often than every 15 seconds,
/// never per photo. State changes are announced right away, once.
public struct UploadAnnouncer: Sendable {
    private var lastProcessed = 0
    private var lastTime: Date?
    private var lastKind: UploadBarState.Kind?
    public init() {}

    public mutating func progressMessage(_ p: QueueProgress, now: Date = .now) -> String? {
        let uploaded = p.done + p.duplicates
        let step = max(1, Int((Double(p.total) * 0.1).rounded(.up)))
        guard !p.isEmpty, !p.isFinished, p.processed - lastProcessed >= step else { return nil }
        if let t = lastTime, now.timeIntervalSince(t) < 15 { return nil }
        lastProcessed = p.processed; lastTime = now
        return "Uploaded \(uploaded) of \(p.total) photos."
    }

    /// "Upload paused", "Waiting for connection", "Storage is full": said once when the state is entered.
    public mutating func stateMessage(_ bar: UploadBarState?) -> String? {
        let kind = bar?.kind
        defer { lastKind = kind }
        guard kind != lastKind else { return nil }
        switch kind {
        case .paused?: return "Upload paused"
        case .offline?: return "Waiting for connection"
        case .storageFull?: return "Storage is full"
        default: return nil
        }
    }

    public mutating func reset() { self = UploadAnnouncer() }
}
