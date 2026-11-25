import Foundation

/// After an upload the server needs a few seconds (thumbnail, search index) before it lists a photo. This is the waiting plan: poll about
/// every 2 s, then every 4 s, and give up after about 90 s (a later visit to the tab or a pull to refresh still shows the photos).
public struct ReadyWait: Sendable {
    public enum Outcome: Sendable, Equatable { case ready, gaveUp, cancelled }
    public var fast: Duration, slow: Duration
    public var fastPolls: Int
    public var giveUp: Duration

    public init(fast: Duration = .seconds(2), slow: Duration = .seconds(4), fastPolls: Int = 5, giveUp: Duration = .seconds(90)) {
        self.fast = fast; self.slow = slow; self.fastPolls = fastPolls; self.giveUp = giveUp
    }

    /// The pauses between polls: `fast` for the first `fastPolls`, then `slow`, until the total reaches `giveUp`.
    public func delays() -> [Duration] {
        var out: [Duration] = [], total = Duration.zero
        while total < giveUp {
            let d = out.count < fastPolls ? fast : slow
            out.append(d); total += d
        }
        return out
    }

    /// Polls `count` (the number of photos the server lists) until it reaches `target`. The first poll is immediate.
    public func run(target: Int, poll count: @Sendable () async -> Int?) async -> Outcome {
        if let c = await count(), c >= target { return .ready }
        for d in delays() {
            do { try await Task.sleep(for: d) } catch { return .cancelled }
            if Task.isCancelled { return .cancelled }
            if let c = await count(), c >= target { return .ready }
        }
        return .gaveUp
    }

    /// How many photos the server should list once this batch is ready: what was listed before plus what was uploaded now
    /// (photos that were already in the library are not counted). Nil when nothing new was uploaded: no waiting.
    public static func target(baseline: Int, progress: QueueProgress) -> Int? { progress.done > 0 ? baseline + progress.done : nil }
}

/// Runs at most one waiting task at a time: starting a new one (more uploads finished) cancels the old one.
public final class ReadyWatcher: @unchecked Sendable {
    private let lock = NSLock()
    private var task: Task<Void, Never>?
    private var generation = 0
    private var active = 0
    public private(set) var peakActive = 0
    public private(set) var started = 0

    public init() {}
    public var isRunning: Bool { lock.lock(); defer { lock.unlock() }; return task != nil }

    public func start(_ wait: ReadyWait = ReadyWait(), target: Int, poll: @escaping @Sendable () async -> Int?, finished: @escaping @Sendable (ReadyWait.Outcome) -> Void = { _ in }) {
        lock.lock()
        let previous = task
        previous?.cancel()
        generation += 1; started += 1
        let mine = generation
        task = Task { [weak self] in
            await previous?.value                      // the old wait has fully stopped before the new one polls
            if Task.isCancelled { return }
            self?.enter()
            let outcome = await wait.run(target: target, poll: poll)
            self?.leave(mine)
            if outcome != .cancelled { finished(outcome) }
        }
        lock.unlock()
    }

    public func stop() { lock.lock(); task?.cancel(); task = nil; lock.unlock() }

    private func enter() { lock.lock(); active += 1; peakActive = max(peakActive, active); lock.unlock() }
    private func leave(_ gen: Int) { lock.lock(); active -= 1; if gen == generation { task = nil }; lock.unlock() }
}
