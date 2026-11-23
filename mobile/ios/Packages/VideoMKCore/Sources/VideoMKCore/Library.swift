import Foundation

/// A video the user just asked for. It shows up in the list immediately (before the server has answered) and hands over to the
/// server's own row once that exists, so the user can keep browsing and queue more videos while they wait.
public struct PendingVideo: Sendable, Equatable, Identifiable {
    public enum State: Sendable, Equatable {
        case sending
        case accepted(videoID: String)
        case failed(String)
    }

    /// Doubles as the request's idempotency key: retrying the same placeholder can never create a second video.
    public let id: String
    public let brief: String
    public let options: CreateOptions
    public var state: State
    public let createdAt: Date

    public init(id: String = UUID().uuidString, brief: String, options: CreateOptions, state: State = .sending, createdAt: Date = .now) {
        self.id = id; self.brief = brief; self.options = options; self.state = state; self.createdAt = createdAt
    }

    public var acceptedVideoID: String? { if case .accepted(let v) = state { v } else { nil } }
}

public enum LibraryEntry: Sendable, Equatable, Identifiable {
    case pending(PendingVideo)
    case video(VideoItem)

    public var id: String {
        switch self {
        case .pending(let p): "pending-\(p.id)"
        case .video(let v): v.id
        }
    }
}

public enum LibraryMerge {
    /// Placeholders first (newest first), then the server's list in its own order (newest first).
    /// A placeholder disappears the moment the server lists its video, so the row is replaced in place, never duplicated.
    public static func entries(pending: [PendingVideo], server: [VideoItem]) -> [LibraryEntry] {
        let known = Set(server.map(\.id))
        let live = pending.filter { p in p.acceptedVideoID.map { !known.contains($0) } ?? true }
        return live.sorted { $0.createdAt > $1.createdAt }.map(LibraryEntry.pending) + server.map(LibraryEntry.video)
    }

    /// Placeholders still needed after a refresh (the ones the server has taken over can be forgotten).
    public static func stillPending(_ pending: [PendingVideo], server: [VideoItem]) -> [PendingVideo] {
        let known = Set(server.map(\.id))
        return pending.filter { p in p.acceptedVideoID.map { !known.contains($0) } ?? true }
    }
}

/// The server reports coarse stages, not percentages, so the bar is an honest estimate: each stage owns a slice of the bar and
/// eases toward the end of its slice the longer it takes, but never reaches the next slice until the server says so.
public enum ProgressEstimator {
    /// Bar range of each stage (start, end).
    static func slice(_ stage: VideoStatus.Stage) -> (Double, Double) {
        switch stage {
        case .starting: (0.00, 0.06)
        case .writing: (0.06, 0.22)
        case .voiceAndVisuals: (0.22, 0.62)
        case .rendering: (0.62, 0.97)
        }
    }

    /// Typical seconds a stage takes for a video of `minutes` (from QA timings: planning is about fixed, the rest grows with length).
    public static func expectedSeconds(_ stage: VideoStatus.Stage, minutes: Double) -> Double {
        switch stage {
        case .starting: 6
        case .writing: 18
        case .voiceAndVisuals: 25 + 18 * minutes
        case .rendering: 30 + 35 * minutes
        }
    }

    public static func fraction(stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double = CreateOptions.defaultMinutes) -> Double {
        let (lo, hi) = slice(stage)
        let t = max(0, secondsInStage) / expectedSeconds(stage, minutes: minutes)
        let eased = 1 - exp(-1.6 * t)            // fast at first, slows down, never completes the slice
        return lo + (hi - lo) * min(eased, 0.96)
    }
}
