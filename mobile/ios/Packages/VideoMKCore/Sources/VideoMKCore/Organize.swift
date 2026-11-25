import Foundation

/// Smart collections ("Organize"): when to offer them, the chunked apply loop with real progress, names, and the messages.
public enum OrganizePolicy {
    public static let minPhotos = 30          // under this a batch never prompts
    public static let silentBelow = 300       // one apply call: no progress bar

    public enum Action: Sendable, Equatable { case nothing, showSheet, runSilently, runWithProgress }

    /// What to do after a batch, from the preference and the number of photos READY in the batch.
    public static func decide(pref: OrganizePref, ready: Int) -> Action {
        switch pref {
        case .never: return .nothing
        case .ask: return ready >= minPhotos ? .showSheet : .nothing
        case .always: return ready >= silentBelow ? .runWithProgress : .runSilently
        }
    }
}

public enum OrganizeSince {
    /// UTC "YYYY-MM-DDTHH:MM:SS": when the batch started, minus 60 seconds (so a slow clock never misses the first photo).
    public static func stamp(batchStart: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone(identifier: "UTC"); f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f.string(from: batchStart.addingTimeInterval(-60))
    }
}

public enum SuggestedNames {
    static let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    public static func isValid(_ name: String) -> Bool { let n = name.trimmingCharacters(in: .whitespacesAndNewlines); return !n.isEmpty && n.count <= 60 }

    /// Month points (year * 12 + month index) mentioned by a group name such as "Phuket · 14-21 Jul 2024" or "Jun 2025".
    static func points(_ date: String) -> [Int] {
        guard let year = date.split(whereSeparator: { !$0.isNumber }).compactMap({ $0.count == 4 ? Int($0) : nil }).last else { return [] }
        let words = date.split(whereSeparator: { !$0.isLetter }).map(String.init)
        return words.compactMap { w in months.firstIndex(of: w).map { year * 12 + $0 } }
    }

    static func label(_ point: Int) -> String { "\(months[point % 12]) \(point / 12)" }

    /// Name ideas for "Put all in one collection": the main place with a date, then the date range. The first one is pre-filled.
    public static func suggest(groups: [OrganizeGroup]) -> [String] {
        var byPlace: [String: Int] = [:]
        var all: [Int] = []
        var total = 0
        for g in groups {
            let parts = g.name.components(separatedBy: " · ")
            let date = parts.last ?? g.name
            all += points(date); total += g.count
            if parts.count == 2 { byPlace[parts[0], default: 0] += g.count }
        }
        guard let lo = all.min(), let hi = all.max() else { return groups.first.map { [$0.name] } ?? [] }
        let range = lo == hi ? label(lo) : "\(label(lo)) - \(label(hi))"
        var out: [String] = []
        if let (place, n) = byPlace.max(by: { $0.value < $1.value }), total > 0, Double(n) / Double(total) > 0.6 {
            out.append("\(place) \(hi - lo <= 2 ? label(hi) : String(hi / 12))")
        }
        out.append(range)
        return out
    }
}

public struct OrganizeJob: Codable, Sendable, Equatable {
    public enum Mode: String, Codable, Sendable { case auto, single }
    public enum State: String, Codable, Sendable { case running, waiting, failed, finished, cancelled }
    public var mode: Mode
    public var since: String?
    public var name: String?
    public var collectionID: String?
    public var total: Int
    public var remaining: Int
    public var created = 0, updated = 0, skipped = 0
    public var state: State = .running
    public var resumed = false          // continued after a relaunch until the first answer
    public var done: Int { max(0, total - remaining) }
    public var isActive: Bool { state == .running || state == .waiting || state == .failed }
    public var fraction: Double { total > 0 ? min(1, Double(done) / Double(total)) : 0 }
    public init(mode: Mode, since: String?, name: String? = nil, total: Int) { self.mode = mode; self.since = since; self.name = name; self.total = total; self.remaining = total }
}

/// Calls apply again and again (about 300 photos each) until nothing remains. Persisted, so a killed app resumes; offline it waits and
/// carries on by itself; any other failure stops with "Try again". Cancelling keeps what was made.
public actor OrganizeRunner {
    private let api: any LibraryAPI
    private let file: URL?
    private let backoff: Duration
    private var task: Task<Void, Never>?
    public private(set) var job: OrganizeJob?
    private var observer: (@Sendable (OrganizeJob?) -> Void)?

    public init(api: any LibraryAPI, file: URL? = nil, backoff: Duration = .seconds(3)) {
        self.api = api; self.file = file; self.backoff = backoff
        if let file, let data = try? Data(contentsOf: file), let saved = try? JSONDecoder().decode(OrganizeJob.self, from: data) { job = saved }
    }

    public func setObserver(_ f: (@Sendable (OrganizeJob?) -> Void)?) { observer = f; f?(job) }

    /// A job that was running when the app closed carries on (apply is safe to repeat).
    public func resumeIfNeeded() {
        guard task == nil, var j = job, j.state == .running || j.state == .waiting else { return }
        j.resumed = true; j.state = .running; job = j; changed(); launch()
    }

    public func start(mode: OrganizeJob.Mode, since: String?, name: String? = nil, total: Int) {
        task?.cancel()
        job = OrganizeJob(mode: mode, since: since, name: name, total: total)
        changed(); launch()
    }

    public func retry() {
        guard var j = job, j.state == .failed else { return }
        j.state = .running; job = j; changed(); launch()
    }

    public func cancel() {
        task?.cancel(); task = nil
        guard var j = job, j.isActive else { return }
        j.state = .cancelled; job = j; changed()
    }

    public func dismiss() { task?.cancel(); task = nil; job = nil; changed() }

    private func launch() {
        task?.cancel()
        task = Task { await self.loop() }
    }

    private func loop() async {
        var idle = 0
        while !Task.isCancelled, var j = job, j.state == .running || j.state == .waiting {
            do {
                let r = try await api.organizeApply(mode: j.mode.rawValue, since: j.since, name: j.name, collectionID: j.collectionID)
                guard var cur = job, cur.isActive else { return }
                cur.remaining = r.remaining
                cur.total = max(cur.total, cur.done + r.remaining)
                cur.created += r.created; cur.updated += r.updated; cur.skipped = max(cur.skipped, r.skipped)
                if let id = r.collectionID { cur.collectionID = id }
                cur.state = .running; cur.resumed = false
                idle = r.applied == 0 ? idle + 1 : 0
                if r.remaining <= 0 || idle >= 2 { cur.remaining = 0; cur.state = .finished }
                job = cur; changed()
                if cur.state == .finished { task = nil; return }
            } catch is CancellationError { return }
            catch let e as LibraryAPIError where e == .network {
                j.state = .waiting; job = j; changed()
                try? await Task.sleep(for: backoff)
            } catch {
                j.state = .failed; job = j; changed(); task = nil; return
            }
        }
    }

    private func changed() {
        if let file {
            if let j = job, j.isActive { if let d = try? JSONEncoder().encode(j) { try? d.write(to: file, options: .atomic) } }
            else { try? FileManager.default.removeItem(at: file) }
        }
        observer?(job)
    }
}

/// The docked bar for an organise job (same slot and anatomy as the upload bar).
public struct OrganizeBarState: Equatable, Sendable {
    public enum Kind: Sendable, Equatable { case running, waiting, failed }
    public let kind: Kind
    public let title: String
    public let subtitle: String
    public let fraction: Double

    public static func make(_ job: OrganizeJob?, uploadActive: Bool = false) -> OrganizeBarState? {
        guard let job, job.isActive else { return nil }
        let counts = "\(job.done.formatted()) of \(job.total.formatted())"
        switch job.state {
        case .waiting: return OrganizeBarState(kind: .waiting, title: "Waiting for a connection", subtitle: "\(counts) organized", fraction: job.fraction)
        case .failed: return OrganizeBarState(kind: .failed, title: "Couldn't finish organizing", subtitle: "Try again to carry on where it stopped.", fraction: job.fraction)
        default:
            return OrganizeBarState(kind: .running, title: "\(job.resumed ? "Resuming…" : "Organizing…") \(counts)", subtitle: uploadActive ? "Organizing after the upload" : "You can leave this screen.", fraction: job.fraction)
        }
    }
}

public enum OrganizeSummary {
    public struct Message: Equatable, Sendable { public let text: String; public let action: String? }
    public static func message(_ job: OrganizeJob) -> Message? {
        guard job.state == .finished else { return nil }
        let n = job.created + job.updated
        if job.mode == .single { return Message(text: "Organized into 1 collection", action: "View") }
        if n == 0 { return Message(text: "Everything is already organized", action: nil) }
        return Message(text: "Organized into \(ComposerPlan.plural(n, "collection"))", action: "View")
    }
}

/// Screen-reader progress for organising: aggregated (10 % and 15 s at most), never per call; state changes once.
public struct OrganizeAnnouncer: Sendable {
    private var lastDone = 0
    private var lastTime: Date?
    private var lastKind: OrganizeBarState.Kind?
    public init() {}

    public mutating func message(_ job: OrganizeJob?, now: Date = .now) -> String? {
        guard let job, job.isActive else { lastKind = nil; return nil }
        let bar = OrganizeBarState.make(job)
        defer { lastKind = bar?.kind }
        if bar?.kind != lastKind, let kind = bar?.kind {
            if kind == .waiting { return "Waiting for a connection" }
            if kind == .failed { return "Couldn't finish organizing" }
        }
        let step = max(1, Int((Double(job.total) * 0.1).rounded(.up)))
        guard job.state == .running, job.done - lastDone >= step else { return nil }
        if let t = lastTime, now.timeIntervalSince(t) < 15 { return nil }
        lastDone = job.done; lastTime = now
        return "Organized \(job.done.formatted()) of \(job.total.formatted()) photos"
    }
}
