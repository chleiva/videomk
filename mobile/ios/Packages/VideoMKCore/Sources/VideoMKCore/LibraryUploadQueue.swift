import CryptoKit
import Foundation

/// A photo ready to go into the library: already upright, at most 2048 px, no metadata (the `PhotoPrep` output), plus the optional capture time and
/// approximate place that the Settings switches allowed (`PhotoMetaReader`). Nothing else is ever sent.
public struct PreparedUpload: Sendable {
    public var data: Data
    public var taken: String?
    public var lat: Double?
    public var lon: Double?
    public init(data: Data, taken: String? = nil, lat: Double? = nil, lon: Double? = nil) { self.data = data; self.taken = taken; self.lat = lat; self.lon = lon }
    public init(data: Data, meta: PhotoMeta?) { self.init(data: data, taken: meta?.taken, lat: meta?.lat, lon: meta?.lon) }
}

public struct QueueItem: Codable, Sendable, Equatable, Identifiable {
    public enum State: String, Codable, Sendable { case queued, uploading, done, duplicate, noSpace = "no_space", failed }
    public let id: String
    public let file: String            // file name inside the queue directory
    public let size: Int
    public let sha256: String          // of the exact bytes that are uploaded
    public var taken: String?
    public var lat: Double?
    public var lon: Double?
    public var state: State
    public var libraryID: String?
    public var reason: String?

    public init(id: String, file: String, size: Int, sha256: String, taken: String? = nil, lat: Double? = nil, lon: Double? = nil, state: State, libraryID: String? = nil, reason: String? = nil) {
        self.id = id; self.file = file; self.size = size; self.sha256 = sha256; self.taken = taken; self.lat = lat; self.lon = lon; self.state = state; self.libraryID = libraryID; self.reason = reason
    }
}

public struct QueueProgress: Sendable, Equatable {
    public var total = 0, queued = 0, uploading = 0, done = 0, duplicates = 0, noSpace = 0, failed = 0
    public var totalBytes = 0, doneBytes = 0, noSpaceBytes = 0
    public var paused = false, running = false
    public var lastError: String?
    public init() {}
    /// Items that reached an end state (the "37" of "Uploading 37 of 120").
    public var processed: Int { done + duplicates + noSpace + failed }
    public var isEmpty: Bool { total == 0 }
    public var isFinished: Bool { total > 0 && queued == 0 && uploading == 0 }
    public var needsAttention: Bool { noSpace > 0 || failed > 0 || lastError != nil }
}

/// The upload queue of the Media tab: persisted to disk (the prepared files too) so it survives a relaunch, batches of at most 100 slot requests,
/// presigned POST uploads three at a time, three tries per photo, pause and cancel. Nothing is dropped silently: a photo ends as done, already in
/// the library, did-not-fit, or failed (and failed ones can be retried).
public actor LibraryUploadQueue {
    public static let batchSize = 100
    private let directory: URL
    private let api: any LibraryAPI
    private let poster: any FilePosting
    private let concurrency: Int, attempts: Int, batchSize: Int
    private let backoff: [Duration]
    private var items: [QueueItem] = []
    private var paused = false
    private var cancelRequested = false
    private var runner: Task<Void, Never>?
    private var lastError: String?
    private var observer: (@Sendable (QueueProgress) -> Void)?

    public init(directory: URL, api: any LibraryAPI, poster: any FilePosting = S3FilePoster(), concurrency: Int = 3, attempts: Int = 3,
                batchSize: Int = LibraryUploadQueue.batchSize, backoff: [Duration] = [.milliseconds(600), .seconds(2)]) {
        self.directory = directory; self.api = api; self.poster = poster
        self.concurrency = concurrency; self.attempts = attempts; self.batchSize = min(batchSize, Self.batchSize); self.backoff = backoff
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        if let data = try? Data(contentsOf: directory.appendingPathComponent("queue.json")), let saved = try? JSONDecoder().decode([QueueItem].self, from: data) {
            // Whatever was in flight when the app closed goes back in line; files that vanished are failed, never silently dropped.
            items = saved.map { item in
                var i = item
                if i.state == .uploading { i.state = .queued }
                if i.state == .queued || i.state == .failed || i.state == .noSpace, !FileManager.default.fileExists(atPath: directory.appendingPathComponent(i.file).path) { i.state = .failed; i.reason = "The photo file is gone." }
                return i
            }
        }
    }

    public func setObserver(_ f: (@Sendable (QueueProgress) -> Void)?) { observer = f; f?(progress()) }

    public func progress() -> QueueProgress {
        var p = QueueProgress()
        p.total = items.count
        for i in items {
            p.totalBytes += i.size
            switch i.state {
            case .queued: p.queued += 1
            case .uploading: p.uploading += 1
            case .done: p.done += 1; p.doneBytes += i.size
            case .duplicate: p.duplicates += 1; p.doneBytes += i.size
            case .noSpace: p.noSpace += 1; p.noSpaceBytes += i.size
            case .failed: p.failed += 1
            }
        }
        p.paused = paused; p.running = runner != nil; p.lastError = lastError
        return p
    }

    public func snapshot() -> [QueueItem] { items }

    // MARK: control

    /// Stores the prepared photos on disk and queues them. Starts uploading unless paused.
    @discardableResult public func enqueue(_ photos: [PreparedUpload]) -> [String] {
        var ids: [String] = []
        for photo in photos {
            let id = UUID().uuidString
            let name = id + ".jpg"
            guard (try? photo.data.write(to: directory.appendingPathComponent(name), options: .atomic)) != nil else { continue }
            items.append(QueueItem(id: id, file: name, size: photo.data.count, sha256: Self.sha256(photo.data), taken: photo.taken, lat: photo.lat, lon: photo.lon, state: .queued))
            ids.append(id)
        }
        cancelRequested = false
        changed()
        start()
        return ids
    }

    /// Resumes after a relaunch (or after a pause).
    public func start() {
        guard runner == nil, !paused, items.contains(where: { $0.state == .queued }) else { notify(); return }
        lastError = nil
        runner = Task { await self.process() }
        notify()
    }

    public func pause() { paused = true; notify() }
    public func resume() { paused = false; start() }

    /// Stops and forgets everything that is not uploaded yet. Photos already in the library stay there.
    public func cancel() {
        cancelRequested = true; paused = false
        runner?.cancel()
        for i in items { removeFile(i) }
        items = []; lastError = nil
        changed()
    }

    /// Once storage has been freed the photos that did not fit carry on by themselves.
    public func retryNoSpace() {
        var any = false
        for n in items.indices where items[n].state == .noSpace { items[n].state = .queued; any = true }
        if any { changed(); start() }
    }

    public var directoryURL: URL { directory }
    public func fileURL(_ item: QueueItem) -> URL { directory.appendingPathComponent(item.file) }

    public func retry(_ id: String) {
        guard let n = items.firstIndex(where: { $0.id == id }), items[n].state == .failed else { return }
        items[n].state = .queued; items[n].reason = nil
        changed(); start()
    }

    public func retryFailed() {
        for n in items.indices where items[n].state == .failed { items[n].state = .queued; items[n].reason = nil }
        changed(); start()
    }

    /// Clears the finished entries (and their files) once the person has seen the result.
    public func dismissFinished() {
        for i in items where i.state != .queued && i.state != .uploading { removeFile(i) }
        items.removeAll { $0.state != .queued && $0.state != .uploading }
        lastError = nil
        changed()
    }

    // MARK: the work

    private func process() async {
        defer { runner = nil; notify() }
        while !paused, !cancelRequested, !Task.isCancelled {
            let batch = Array(items.filter { $0.state == .queued }.reversed().prefix(batchSize))     // newest first, like the grid shows them
            if batch.isEmpty { break }
            for b in batch { set(b.id) { $0.state = .uploading } }
            changed()
            let response: UploadsResponse
            do {
                response = try await api.requestUploads(batch.map { UploadRequestItem(size: $0.size, sha256: $0.sha256, taken: $0.taken, lat: $0.lat, lon: $0.lon) })
            } catch let e as LibraryAPIError {
                if cancelRequested { return }
                switch e {
                case .storageFull:   // nothing at all fits: everything still waiting is named in the did-not-fit message
                    for i in items where i.state == .uploading || i.state == .queued { finish(i.id, .noSpace) }
                    changed(); return
                case .invalid(let m): for b in batch { finish(b.id, .failed, reason: m) }; changed(); continue
                case .tooLarge: for b in batch { finish(b.id, .failed, reason: e.message) }; changed(); continue
                default:   // offline, rate limit, server trouble: keep everything and wait for the person (or the next launch)
                    for b in batch { set(b.id) { $0.state = .queued } }
                    paused = true; lastError = e.message; changed(); return
                }
            } catch { for b in batch { set(b.id) { $0.state = .queued } }; paused = true; changed(); return }
            if cancelRequested { return }

            struct Job: Sendable { let id: String; let file: URL; let url: URL; let fields: [String: String]; let libraryID: String? }
            var jobs: [Job] = []
            var seen = Set<Int>()
            for r in response.uploads where batch.indices.contains(r.index) && !seen.contains(r.index) {
                seen.insert(r.index)
                let item = batch[r.index]
                switch r.status {
                case .duplicate: finish(item.id, .duplicate, libraryID: r.duplicateOf)
                case .noSpace: finish(item.id, .noSpace)
                case .upload:
                    if let url = r.url, let fields = r.fields { jobs.append(Job(id: item.id, file: directory.appendingPathComponent(item.file), url: url, fields: fields, libraryID: r.id)) }
                    else { finish(item.id, .failed, reason: "The server gave no upload address.") }
                case .rejected, .unknown: finish(item.id, .failed, reason: r.reason ?? "This photo can't be added.")
                }
            }
            for (n, item) in batch.enumerated() where !seen.contains(n) { finish(item.id, .failed, reason: "The server did not answer for this photo.") }
            changed()

            enum Outcome: Sendable { case done, failed(String), stopped }
            let poster = self.poster, tries = attempts, waits = backoff
            let outcomes: [Outcome] = await boundedMap(jobs, concurrency: concurrency, onEach: { n, outcome in
                let job = jobs[n]
                switch outcome {
                case .done: self.finish(job.id, .done, libraryID: job.libraryID)
                case .failed(let m): self.finish(job.id, .failed, reason: m)
                case .stopped: self.set(job.id) { $0.state = .queued }
                }
                self.changed()
            }) { _, job in
                guard let data = try? Data(contentsOf: job.file) else { return .failed("The photo file is gone.") }
                var last = "The upload failed."
                for attempt in 0..<tries {
                    if await self.shouldStop() { return .stopped }
                    if attempt > 0 { try? await Task.sleep(for: waits.isEmpty ? .zero : waits[min(attempt - 1, waits.count - 1)]) }
                    do { try await poster.post(data, to: job.url, fields: job.fields); return .done }
                    catch is CancellationError { return .stopped }
                    catch let e as LibraryAPIError { last = e.message }
                    catch { last = "The upload failed." }
                }
                return .failed(last)
            }
            _ = outcomes
            if cancelRequested { return }
        }
    }

    func shouldStop() -> Bool { paused || cancelRequested }

    private func set(_ id: String, _ f: (inout QueueItem) -> Void) { if let n = items.firstIndex(where: { $0.id == id }) { f(&items[n]) } }

    private func finish(_ id: String, _ state: QueueItem.State, libraryID: String? = nil, reason: String? = nil) {
        guard let n = items.firstIndex(where: { $0.id == id }) else { return }
        items[n].state = state; items[n].libraryID = libraryID; items[n].reason = reason
        if state != .failed && state != .noSpace { removeFile(items[n]) }     // failed and did-not-fit photos keep their file: they can carry on later
    }

    private func removeFile(_ i: QueueItem) { try? FileManager.default.removeItem(at: directory.appendingPathComponent(i.file)) }

    private func changed() {
        if let data = try? JSONEncoder().encode(items) { try? data.write(to: directory.appendingPathComponent("queue.json"), options: .atomic) }
        notify()
    }

    private func notify() { observer?(progress()) }

    public static func sha256(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
}
