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
            return make(.storageFull, tr("upload.storage_full_title"), tr("upload.storage_full_sub", p.noSpace))
        }
        if p.isFinished { return make(p.failed > 0 ? .needsAttention : .finished, p.failed > 0 ? tr("upload.need_you_title", p.failed) : tr("upload.done"), p.failed > 0 ? tr("upload.photos_added", uploaded) : "") }
        if p.paused && p.lastError != nil || p.lastError != nil {
            return make(.offline, tr("upload.offline_title"), tr("upload.offline_sub", p.queued + p.uploading))
        }
        if p.paused {
            return make(.paused, tr("upload.paused_title", uploaded, p.total), p.uploading > 0 ? tr("upload.pausing") : tr("upload.resume_hint"))
        }
        return make(.uploading, tr("upload.uploading_title", uploaded, p.total), leftText(p, elapsed: elapsed))
    }

    static func leftText(_ p: QueueProgress, elapsed: TimeInterval?) -> String {
        let left = max(0, p.totalBytes - p.doneBytes)
        let size = StorageMeter.format(left)
        if let elapsed, elapsed > 5, p.doneBytes > 0 {
            let seconds = Double(left) / (Double(p.doneBytes) / elapsed)
            return seconds < 60 ? tr("upload.left_less_than_minute", size) : tr("upload.left_about_minutes", size, Int((seconds / 60).rounded(.up)))
        }
        return tr("upload.left", size)
    }
}

/// The one summary per batch.
public enum UploadSummary {
    public struct Message: Equatable, Sendable { public let text: String; public let action: String? }

    public static func message(_ p: QueueProgress) -> Message? {
        guard p.isFinished else { return nil }
        var text: String
        if p.done > 0 { text = tr("upload.summary_added", p.done) }
        else if p.duplicates > 0 { text = "" }
        else { return p.failed > 0 ? Message(text: tr("upload.summary_attention", p.failed), action: tr("upload.review")) : nil }
        if p.failed > 0 { text += " " + tr("upload.summary_attention", p.failed) }
        else if p.duplicates > 0 { text += (text.isEmpty ? "" : " ") + tr("upload.summary_duplicates", p.duplicates) }
        return Message(text: text, action: p.failed > 0 ? tr("upload.review") : tr("upload.got_it"))
    }
}

/// The honest "Making" card: four named steps, a line that says what is happening, and a time left. The server reports stages, not scenes.
public enum MakingProgress {
    public static var steps: [String] { [tr("making.step.script"), tr("making.step.voice"), tr("making.step.pictures"), tr("making.step.final_cut")] }
    // Where each step ends on the overall 0...1 estimate (matches ProgressEstimator's slices).
    static let edges: [Double] = [0.22, 0.42, 0.62, 1.0]

    public struct Info: Equatable, Sendable {
        public let segments: [Double]      // fill of each step, 0...1
        public let current: Int
        public let line: String
        /// The same sentence without the time ("Recording the voice and drawing the pictures."), and the time on its own ("About 2 min left.").
        public let what: String
        public let eta: String
        public init(segments: [Double], current: Int, line: String, what: String? = nil, eta: String = "") {
            self.segments = segments; self.current = current; self.line = line; self.what = what ?? line; self.eta = eta
        }
    }

    public static func info(stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double) -> Info {
        let f = ProgressEstimator.fraction(stage: stage, secondsInStage: secondsInStage, minutes: minutes)
        var lo = 0.0
        var segs: [Double] = []
        for e in edges { segs.append(min(1, max(0, (f - lo) / (e - lo)))); lo = e }
        let current = min(edges.count - 1, edges.firstIndex { f < $0 } ?? edges.count - 1)
        let what: String
        switch stage {
        case .starting: what = tr("making.line.starting")
        case .writing: what = tr("making.line.writing")
        case .voiceAndVisuals: what = tr("making.line.voice_visuals")
        case .rendering: what = tr("making.line.rendering")
        }
        let eta = timeLeft(stage: stage, secondsInStage: secondsInStage, minutes: minutes)
        return Info(segments: segs, current: current, line: "\(what). \(eta)", what: what, eta: eta)       // the live line carries no full stop of its own
    }

    /// Whole minutes left (rounded up) from the typical stage times; nil when under a minute.
    public static func minutesLeft(stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double) -> Int? {
        var left = max(0, ProgressEstimator.expectedSeconds(stage, minutes: minutes) - secondsInStage)
        for s in VideoStatus.Stage.allCases where s > stage { left += ProgressEstimator.expectedSeconds(s, minutes: minutes) }
        return left < 60 ? nil : Int((left / 60).rounded(.up))
    }

    /// Remaining of the typical stage times; rounded up to whole minutes, never "0 min".
    public static func timeLeft(stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double) -> String {
        guard let m = minutesLeft(stage: stage, secondsInStage: secondsInStage, minutes: minutes) else { return tr("making.time_less_than_minute") }
        return tr("making.time_about_minutes", m)
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
        return tr("upload.announce_progress", uploaded, p.total)
    }

    /// "Upload paused", "Waiting for connection", "Storage is full": said once when the state is entered.
    public mutating func stateMessage(_ bar: UploadBarState?) -> String? {
        let kind = bar?.kind
        defer { lastKind = kind }
        guard kind != lastKind else { return nil }
        switch kind {
        case .paused?: return tr("upload.announce_paused")
        case .offline?: return tr("upload.announce_offline")
        case .storageFull?: return tr("upload.announce_storage_full")
        default: return nil
        }
    }

    public mutating func reset() { self = UploadAnnouncer() }
}
