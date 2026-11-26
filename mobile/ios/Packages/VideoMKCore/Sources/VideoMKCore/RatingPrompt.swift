import Foundation

// The "Enjoying videomk?" rating prompt. Everything here is pure: the clock and the storage are injected, nothing touches UIKit.
// The long explanation and the state machine are in docs/FEEDBACK.md, section "Rating prompt".

/// The App Store page of the app.
public enum AppStoreInfo {
    /// TODO(owner): put the real numeric App Store id here once the app has an App Store Connect record ("id1234567890" -> "1234567890").
    /// While it is the placeholder the prompt NEVER appears (a "Rate" button to a page that does not exist is worse than no prompt).
    public static let appID = "0000000000"
    public static var isConfigured: Bool { appID != "0000000000" && !appID.isEmpty }
    public static func writeReviewURL(appID: String = appID) -> URL { URL(string: "https://apps.apple.com/app/id\(appID)?action=write-review")! }
}

/// Decides, from playback samples, whether a video was REALLY watched to the end once.
///
/// Rule: `observe(position:duration:)` is fed about every 0.5 s while the player moves. A step counts as watched time only if the position
/// moved FORWARD by no more than `maxStep` seconds (normal play, even at 2x). A seek (any jump bigger than `maxStep`, or backwards) adds nothing.
/// The video is complete when the watched time covers at least 90% of the duration AND the position is within 1 s of the end.
/// Scrubbing to the end therefore never counts (almost nothing was watched), neither does skipping around: only watching it through does.
/// Replaying can add watched time again (the sum is capped at the duration), which is fine: one video counts once anyway.
public struct PlaybackCompletion: Sendable, Equatable {
    public static let coverage = 0.9
    public static let endTolerance = 1.0
    public static let maxStep = 3.0
    public private(set) var watched = 0.0
    public private(set) var isComplete = false
    private var last: Double?

    public init() {}

    @discardableResult
    public mutating func observe(position: Double, duration: Double) -> Bool {
        guard position.isFinite, duration.isFinite, duration >= 1, position >= 0 else { return isComplete }
        if let last, position > last, position - last <= Self.maxStep { watched = min(duration, watched + (position - last)) }
        last = position
        if watched >= Self.coverage * duration, position >= duration - Self.endTolerance { isComplete = true }
        return isComplete
    }
}

/// Persisted rating state (one JSON blob in UserDefaults).
public struct RatingState: Codable, Equatable, Sendable {
    public var completedCount = 0
    /// Ids of fully watched videos, oldest first, capped at `RatingPrompt.idCap` (the count is kept separately, so trimming never lowers it).
    public var completedIDs: [String] = []
    public var asked = 0
    public var askedAtCount = 0
    public var lastAskedAt: Date?
    public var lastAskedVersion: String?
    public var done = false
    public init() {}
}

public enum RatingOutcome: Sendable { case rate, alreadyRated, maybeLater, notReally }

/// Where the app is right now; every flag is "something is in the way".
public struct RatingContext: Sendable {
    public var isPlaying = false, isCreating = false, sheetOpen = false, suppressed = false
    public init(isPlaying: Bool = false, isCreating: Bool = false, sheetOpen: Bool = false, suppressed: Bool = false) {
        self.isPlaying = isPlaying; self.isCreating = isCreating; self.sheetOpen = sheetOpen; self.suppressed = suppressed
    }
}

/// STATE MACHINE
/// * `recordCompleted(id)`: a video counts once per distinct id (`completedCount`).
/// * Eligible when `completedCount >= threshold`, where threshold = 11 for the first ask, then `askedAtCount + 10` (21, 31 when asked on time).
/// * Never when: `done`, 3 asks already, app version equal to the one of the last ask, app launched less than 2 minutes ago, a video is playing,
///   Create or another sheet is open, the app id is still the placeholder, or UI-test / screenshot mode.
/// * Showing it counts as an ask (`didShow`): swipe-down, tap outside, "Maybe later" and "Not really" all just wait for the next threshold.
/// * "Rate videomk" and "I already rated it" end it for good (`done`): we cannot know whether the review was written, and asking a person who
///   went to the store again would be nagging.
/// Next ask after a close is therefore at completed video 21, then 31, at most 3 asks in total.
public final class RatingPrompt: @unchecked Sendable {
    public static let firstThreshold = 11, step = 10, maxAsks = 3, idCap = 500
    public static let minimumUptime: TimeInterval = 120
    public static let key = "vmk.rating.state"

    private let defaults: UserDefaults
    private let now: @Sendable () -> Date
    private let launchedAt: Date
    private let version: String
    private let configured: Bool
    private let lock = NSLock()
    private var cached: RatingState?

    public init(defaults: UserDefaults = .standard, now: @escaping @Sendable () -> Date = { Date() }, version: String,
                configured: Bool = AppStoreInfo.isConfigured) {
        self.defaults = defaults; self.now = now; self.version = version; self.configured = configured; launchedAt = now()
    }

    public var state: RatingState {
        lock.lock(); defer { lock.unlock() }
        return load()
    }
    private func load() -> RatingState {
        if let cached { return cached }
        let s = defaults.data(forKey: Self.key).flatMap { try? JSONDecoder().decode(RatingState.self, from: $0) } ?? RatingState()
        cached = s; return s
    }
    private func mutate(_ f: (inout RatingState) -> Void) {
        lock.lock(); defer { lock.unlock() }
        var s = load(); f(&s); cached = s
        if let d = try? JSONEncoder().encode(s) { defaults.set(d, forKey: Self.key) }
    }

    public var threshold: Int { state.asked == 0 ? Self.firstThreshold : state.askedAtCount + Self.step }

    /// Returns true when this video was new.
    @discardableResult
    public func recordCompleted(_ id: String) -> Bool {
        guard !id.isEmpty, !state.completedIDs.contains(id) else { return false }
        mutate { s in
            s.completedCount += 1
            s.completedIDs.append(id)
            if s.completedIDs.count > Self.idCap { s.completedIDs.removeFirst(s.completedIDs.count - Self.idCap) }
        }
        return true
    }

    public func shouldPrompt(_ c: RatingContext = RatingContext()) -> Bool {
        let s = state
        guard configured, !c.suppressed, !c.isPlaying, !c.isCreating, !c.sheetOpen else { return false }
        guard !s.done, s.asked < Self.maxAsks, s.lastAskedVersion != version else { return false }
        guard now().timeIntervalSince(launchedAt) >= Self.minimumUptime else { return false }
        return s.completedCount >= threshold
    }

    /// Call when the pre-prompt is actually shown.
    public func didShow() {
        mutate { s in s.asked += 1; s.askedAtCount = s.completedCount; s.lastAskedAt = now(); s.lastAskedVersion = version }
    }

    public func resolve(_ outcome: RatingOutcome) {
        switch outcome {
        case .rate, .alreadyRated: mutate { $0.done = true }
        case .maybeLater, .notReally: break
        }
    }

    /// UI tests, screenshots and fake-library runs never see the prompt.
    public static func isSuppressed(environment: [String: String]) -> Bool {
        environment["XCTestConfigurationFilePath"] != nil || environment["VMK_DEBUG_FAKE_LIBRARY"] == "1" || environment["VMK_DEBUG_RESET"] == "1"
            || environment["VMK_SHOTS_DIR"] != nil || environment["VMK_DEBUG_SHEET"] != nil
    }
}
