import Observation
import PhotosUI
import SwiftUI
import VideoMKCore

/// State of "My media": the summary (storage, collections), the upload queue, and the caches. One per signed-in session.
@MainActor @Observable
final class MediaModel {
    let api: any LibraryAPI
    let store: PhotoLibraryStore
    let queue: LibraryUploadQueue
    let organizer: OrganizeRunner
    let isFake: Bool
    private(set) var summary: LibrarySummary?
    private(set) var collections: [LibraryCollection] = []
    private(set) var upload = QueueProgress()
    private(set) var preparing = 0
    private(set) var preparingTotal = 0
    private(set) var unreadable = 0
    private(set) var version = 0              // bumps when photos were added or removed: lists reload
    private(set) var summaryError: String?
    var notice: String?
    // The upload journey (docs/UI_DESIGN.md m)
    private(set) var queueItems: [QueueItem] = []
    private(set) var toast: ToastMessage?
    var barExpanded = false
    private(set) var uploadStartedAt: Date?
    private(set) var hiddenTiles: Set<String> = []        // "Already there" tiles after their 4 seconds
    @ObservationIgnored private var announcer = UploadAnnouncer()
    @ObservationIgnored private let localImages = NSCache<NSString, UIImage>()
    @ObservationIgnored private var toastedBatch = false
    #if DEBUG
    @ObservationIgnored var debugLocalImages: [String: UIImage] = [:]
    @ObservationIgnored var debugFrozen = false          // a screenshot scene: the real queue must not overwrite it
    #endif

    // Smart collections (Organize)
    private(set) var organizeJob: OrganizeJob?
    var pendingOrganize: OrganizeRequest?                 // the sheet waits here until the Media tab is visible
    var showCollectionsList = false
    @ObservationIgnored private var organizeAnnouncer = OrganizeAnnouncer()
    @ObservationIgnored private var organizeEvaluated = false
    @ObservationIgnored private var organizeToasted = false
    @ObservationIgnored private var organizeSilent = false      // Always with a small batch: no bar, no toast
    var organizePref: OrganizePref { summary?.prefs.organize ?? .ask }
    var organizeBar: OrganizeBarState? { organizeSilent ? nil : OrganizeBarState.make(organizeJob, uploadActive: bar.map { $0.kind != .finished } ?? false) }

    struct OrganizeRequest: Identifiable, Equatable {
        let id = UUID()
        var since: String?            // nil: the whole library
        var preview: OrganizePreview?
        var fromBatch: Bool
    }

    struct ToastMessage: Identifiable, Equatable { let id = UUID(); let text: String; let action: String? }
    var bar: UploadBarState? { UploadBarState.make(upload, gettingReady: gettingReady, elapsed: uploadStartedAt.map { Date().timeIntervalSince($0) }) }
    @ObservationIgnored private let images = NSCache<NSString, UIImage>()
    @ObservationIgnored private var started = false
    // Waiting for the server to list photos it is still preparing (thumbnail, search index: 2 to 10 s after the file arrives).
    private(set) var readyTarget: Int?        // how many photos the server should list once this batch is ready
    private(set) var waiting = false
    @ObservationIgnored private var baseline: Int?
    @ObservationIgnored private let watcher = ReadyWatcher()
    @ObservationIgnored private var watching: Set<String> = []     // who is looking (the Media tab, the composer picker)
    /// Photos uploaded but not listed by the server yet.
    var gettingReady: Int { waiting ? max(0, (readyTarget ?? 0) - (summary?.count ?? 0)) : 0 }

    var meter: StorageMeter? { summary.map { StorageMeter(used: $0.usedBytes, limit: $0.limitBytes) } }

    init(api: any LibraryAPI, fake: Bool = false) {
        self.api = api; isFake = fake
        let fm = FileManager.default
        let caches = fm.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("VideoMKMedia", isDirectory: true)
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0].appendingPathComponent("VideoMKUploadQueue", isDirectory: true)
        try? fm.createDirectory(at: support, withIntermediateDirectories: true)
        var noBackup = URLResourceValues(); noBackup.isExcludedFromBackup = true      // private photos are not copied into device backups
        var dir = support; try? dir.setResourceValues(noBackup)
        images.countLimit = 500
        store = PhotoLibraryStore(directory: caches, api: api, fetch: fake ? MediaModel.fakeFetch : MediaModel.fetch)
        queue = LibraryUploadQueue(directory: support, api: api, poster: fake ? FakePoster() : S3FilePoster())
        organizer = OrganizeRunner(api: api, file: fake ? nil : support.appendingPathComponent("organize-job.json"))
    }

    func start() async {
        if !started {
            started = true
            await queue.setObserver { [weak self] p in Task { @MainActor in self?.apply(p) } }
            await organizer.setObserver { [weak self] j in Task { @MainActor in self?.applyOrganize(j) } }
            await organizer.resumeIfNeeded()           // a job that was running when the app closed carries on
        }
        await queue.start()          // continues what a previous launch left in the queue
        await loadSummary()
    }

    func loadSummary() async {
        do {
            let s = try await api.summary()
            summary = s; collections = s.collections; summaryError = nil
        } catch is CancellationError {
        } catch { summaryError = (error as? LibraryAPIError)?.message ?? tr("media.err.storage") }
    }

    private var lastProcessed = 0
    private func apply(_ p: QueueProgress) {
        #if DEBUG
        if debugFrozen { return }
        #endif
        let wasEmpty = upload.isEmpty, wasFinished = upload.isFinished
        upload = p
        Task { queueItems = await queue.snapshot() }
        if wasEmpty, !p.isEmpty { baseline = summary?.count ?? 0; uploadStartedAt = .now; toastedBatch = false; announcer.reset(); hiddenTiles = []; organizeEvaluated = false }
        if p.isEmpty { lastProcessed = 0; readyTarget = nil; baseline = nil; waiting = false; watcher.stop(); uploadStartedAt = nil; barExpanded = false; return }
        announce(p)
        if p.noSpace > 0, !p.paused { Task { await self.resumeIfSpaceWasFreed() } }
        if p.isFinished, !p.running, !wasFinished || p.processed != lastProcessed {
            lastProcessed = p.processed
            if !toastedBatch, p.noSpace == 0, let msg = UploadSummary.message(p) {
                toastedBatch = true
                toast = ToastMessage(text: msg.text, action: msg.action)
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                UIAccessibility.post(notification: .announcement, argument: msg.text)
                let shown = toast
                Task { try? await Task.sleep(for: .seconds(8)); if toast == shown { toast = nil } }
            }
            if let target = ReadyWait.target(baseline: baseline ?? summary?.count ?? 0, progress: p) {
                readyTarget = target
                beginWaiting()                                          // the server lists the photos only after preparing them
            } else {
                Task { await self.loadSummary(); self.version += 1 }   // only duplicates, did-not-fit or failures: nothing to wait for
            }
        }
    }

    private func announce(_ p: QueueProgress) {
        let msg = announcer.stateMessage(bar) ?? announcer.progressMessage(p)
        if let msg { UIAccessibility.post(notification: .announcement, argument: msg) }
    }

    /// Storage was freed (photos deleted, or a bigger plan): the photos that did not fit carry on by themselves.
    private func resumeIfSpaceWasFreed() async {
        guard let m = meter, upload.noSpace > 0 else { return }
        let average = upload.noSpaceBytes / max(1, upload.noSpace)
        if m.remaining >= average, !(summary?.readOnly ?? false) { await queue.retryNoSpace() }
    }

    func dismissToast() { toast = nil }
    func retryItem(_ id: String) { Task { await queue.retry(id) } }
    func hideTile(_ id: String) { hiddenTiles.insert(id) }

    /// The local picture of a queued photo (decoded small, off the main thread), from memory or the queue's own file.
    func localImage(for item: QueueItem) async -> UIImage? {
        if let hit = localImages.object(forKey: item.id as NSString) { return hit }
        #if DEBUG
        if let fake = debugLocalImages[item.id] { return fake }
        #endif
        let url = await queue.fileURL(item)
        let img: UIImage? = await Task.detached(priority: .utility) {
            guard let data = try? Data(contentsOf: url) else { return nil }
            return PhotoAttachments.thumbnail(of: data, maxPixel: 320)
        }.value
        if let img { localImages.setObject(img, forKey: item.id as NSString) }
        return img
    }

    // MARK: waiting for uploaded photos to be listed

    /// Who is looking decides whether the single polling task runs: the Media tab and the composer picker register here.
    func setWatching(_ who: String, _ on: Bool) {
        if on { watching.insert(who) } else { watching.remove(who) }
        if watching.isEmpty { watcher.stop() }
        else if let t = readyTarget, (summary?.count ?? 0) < t, !watcher.isRunning { beginWaiting() }
    }

    private func beginWaiting() {
        guard let target = readyTarget, !watching.isEmpty else {
            if readyTarget != nil { waiting = true }      // not visible: the banner says so, polling starts when someone looks
            return
        }
        waiting = true
        watcher.start(target: target, poll: { [weak self] in await self?.pollOnce() }, finished: { [weak self] _ in
            Task { @MainActor in self?.finishWaiting() }
        })
    }

    /// One poll: the summary (its count is what is listed) and, when it changed, a merge of the first page into the open lists.
    private func pollOnce() async -> Int? {
        let before = summary?.count
        await loadSummary()
        if summary?.count != before { version += 1 }
        return summary?.count
    }

    private func finishWaiting() {
        waiting = false
        version += 1                                   // final look at the first page
        if let t = readyTarget, (summary?.count ?? 0) >= t { readyTarget = nil }
        Task { await evaluateOrganizeAfterBatch() }
    }

    // MARK: smart collections

    /// Once per batch, after its photos are ready: ask, organise by itself, or do nothing (see `OrganizePolicy`).
    private func evaluateOrganizeAfterBatch() async {
        guard !organizeEvaluated, upload.done > 0, organizePref != .never, organizeJob?.isActive != true else { return }
        organizeEvaluated = true
        let since = OrganizeSince.stamp(batchStart: uploadStartedAt ?? Date())
        guard let preview = try? await api.organizePreview(since: since) else { return }
        switch OrganizePolicy.decide(pref: organizePref, ready: preview.total) {
        case .nothing: break
        case .showSheet: if !preview.groups.isEmpty { pendingOrganize = OrganizeRequest(since: since, preview: preview, fromBatch: true) }
        case .runSilently, .runWithProgress:
            if preview.organized > 0 { organizeToasted = false; organizeSilent = OrganizePolicy.decide(pref: organizePref, ready: preview.total) == .runSilently; await organizer.start(mode: .auto, since: since, total: preview.organized) }
        }
    }

    func organizeLibrary() { pendingOrganize = OrganizeRequest(since: nil, preview: nil, fromBatch: false) }

    func startOrganize(mode: OrganizeJob.Mode, since: String?, name: String? = nil, total: Int) {
        organizeToasted = false; organizeSilent = false
        Task { await organizer.start(mode: mode, since: since, name: name, total: total) }
    }
    func cancelOrganize() { Task { await organizer.cancel(); await organizer.dismiss() } }
    func retryOrganize() { Task { await organizer.retry() } }

    func setOrganizePref(_ pref: OrganizePref) {
        guard var s = summary else { return }
        let old = s.prefs.organize
        s.prefs.organize = pref; summary = s
        Haptics.play(.selection)
        Task { do { try await api.setOrganizePref(pref) } catch { if var s2 = summary { s2.prefs.organize = old; summary = s2 }; notice = (error as? LibraryAPIError)?.message ?? tr("media.err.save") } }
    }

    private func applyOrganize(_ job: OrganizeJob?) {
        #if DEBUG
        if debugFrozen { return }
        #endif
        organizeJob = job
        if let msg = organizeAnnouncer.message(job) { UIAccessibility.post(notification: .announcement, argument: msg) }
        guard let job, job.state == .finished, !organizeToasted else { return }
        organizeToasted = true
        Task { await loadSummary(); version += 1; await organizer.dismiss() }
        if !organizeSilent, let msg = OrganizeSummary.message(job) {
            toast = ToastMessage(text: msg.text, action: msg.action)
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            UIAccessibility.post(notification: .announcement, argument: msg.text)
            let shown = toast
            Task { try? await Task.sleep(for: .seconds(8)); if toast == shown { toast = nil } }
        }
    }

    /// Tab shown again, app active again, pull to refresh: look at the server now.
    func refreshNow() async {
        await loadSummary()
        version += 1
    }

    // MARK: adding photos (system picker: no permission prompt)

    /// Prepares the picked photos a few at a time (upright, at most 2048 px, no metadata) and puts them in the upload queue.
    /// Date and place are read from the original only when the Settings switches allow it.
    func add(_ picked: [PhotosPickerItem]) async {
        guard !picked.isEmpty else { return }
        let dates = PhotoMetaSettings.dates(), locations = PhotoMetaSettings.locations()
        preparing = 0; preparingTotal += picked.count
        let queue = self.queue
        for start in stride(from: 0, to: picked.count, by: 12) {
            let group = Array(picked[start..<min(start + 12, picked.count)])
            let prepared: [PreparedUpload?] = await boundedMap(group, concurrency: PhotoLimits.prepareParallelism, onEach: { [self] _, _ in preparing += 1 }) { (_, item) async -> PreparedUpload? in
                guard let raw = try? await item.loadTransferable(type: Data.self) else { return nil }
                return await Self.prepare(raw, dates: dates, locations: locations)
            }
            unreadable += prepared.filter { $0 == nil }.count
            await queue.enqueue(prepared.compactMap { $0 })
        }
        preparing = 0; preparingTotal = 0
        if unreadable > 0 { notice = tr("attach.unreadable", unreadable); unreadable = 0 }
    }

    nonisolated static func prepare(_ raw: Data, dates: Bool, locations: Bool) async -> PreparedUpload? {
        await Task.detached(priority: .userInitiated) {
            let meta = PhotoMetaReader.read(from: raw, dates: dates, locations: locations)   // before the metadata is stripped
            guard let jpeg = PhotoPrep.jpeg(from: raw) else { return nil }
            return PreparedUpload(data: jpeg, meta: meta)
        }.value
    }

    // MARK: queue controls

    func pauseUploads() { Task { await queue.pause() } }
    func resumeUploads() { Task { await queue.resume() } }
    func cancelUploads() { Task { await queue.cancel() } }
    func retryUploads() { Task { await queue.retryFailed() } }
    func dismissUploads() { Task { await queue.dismissFinished() } }

    // MARK: deleting and collections

    func delete(_ ids: [String]) async -> Bool {
        do {
            for chunk in stride(from: 0, to: ids.count, by: 100).map({ Array(ids[$0..<min($0 + 100, ids.count)]) }) {
                let r = try await api.delete(ids: chunk)
                if var s = summary { s.usedBytes = r.usedBytes; summary = s }
            }
            await store.forget(ids)
            for id in ids { images.removeObject(forKey: id as NSString) }
            version += 1
            await loadSummary()
            return true
        } catch { notice = (error as? LibraryAPIError)?.message ?? tr("media.err.delete"); return false }
    }

    func createCollection(name: String, emoji: String? = nil) async -> LibraryCollection? {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return nil }
        do { let c = try await api.createCollection(name: String(n.prefix(40)), emoji: emoji); collections.append(c); return c }
        catch { notice = (error as? LibraryAPIError)?.message ?? tr("media.err.collection_create"); return nil }
    }

    func rename(_ c: LibraryCollection, to name: String) async {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return }
        do { let u = try await api.updateCollection(id: c.id, name: String(n.prefix(40)), emoji: nil); if let i = collections.firstIndex(where: { $0.id == c.id }) { collections[i] = u } }
        catch { notice = (error as? LibraryAPIError)?.message ?? tr("media.err.collection_rename") }
    }

    func deleteCollection(_ c: LibraryCollection) async {
        do { try await api.deleteCollection(id: c.id); collections.removeAll { $0.id == c.id }; version += 1 }
        catch { notice = (error as? LibraryAPIError)?.message ?? tr("media.err.collection_delete") }
    }

    func edit(_ c: LibraryCollection, add: [String] = [], remove: [String] = []) async -> Bool {
        do {
            for chunk in stride(from: 0, to: max(add.count, remove.count), by: 100) {
                try await api.editCollection(id: c.id, add: Array(add.dropFirst(chunk).prefix(100)), remove: Array(remove.dropFirst(chunk).prefix(100)))
            }
            await loadSummary(); version += 1
            return true
        } catch { notice = (error as? LibraryAPIError)?.message ?? tr("media.err.collection_update"); return false }
    }

    // MARK: images

    func thumbnail(for photo: LibraryPhoto) async -> UIImage? {
        if let hit = images.object(forKey: photo.id as NSString) { return hit }
        guard let data = await store.thumbnail(for: photo), let img = UIImage(data: data) else { return nil }
        images.setObject(img, forKey: photo.id as NSString)
        return img
    }

    /// The full photo for the viewer: a fresh link from `GET items/{id}` (valid 10 minutes, never stored).
    func fullImage(for photo: LibraryPhoto) async -> UIImage? {
        guard let fresh = try? await api.item(id: photo.id), let url = fresh.url else { return await thumbnail(for: photo) }
        let fetch: @Sendable (URL) async throws -> Data = isFake ? MediaModel.fakeFetch : MediaModel.fetch
        guard let data = try? await fetch(url), let img = UIImage(data: data) else { return await thumbnail(for: photo) }
        return img
    }

    func wipe() async {
        await queue.cancel()
        await store.removeAll()
        images.removeAllObjects()
        watcher.stop(); waiting = false; readyTarget = nil; baseline = nil; watching = []; queueItems = []; toast = nil; localImages.removeAllObjects()
        summary = nil; collections = []; upload = QueueProgress(); started = false
    }

    // MARK: network

    nonisolated static func fetch(_ url: URL) async throws -> Data {
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.cachePolicy = .reloadIgnoringLocalCacheData      // the id-keyed cache is ours; links are short-lived
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let code = (resp as? HTTPURLResponse)?.statusCode, (200..<300).contains(code) else { throw LibraryAPIError.unauthorized }
        return data
    }

    /// Debug builds with `VMK_DEBUG_FAKE_LIBRARY=1`: pictures are drawn locally.
    nonisolated static func fakeFetch(_ url: URL) async throws -> Data {
        fakeImage(seed: url.lastPathComponent, size: url.host == "full" ? CGSize(width: 900, height: 1200) : CGSize(width: 240, height: 240)).jpegData(compressionQuality: 0.8) ?? Data()
    }

    nonisolated static func fakeImage(seed: String, size: CGSize) -> UIImage {
        var h: UInt64 = 1469598103934665603
        for b in seed.utf8 { h = (h ^ UInt64(b)) &* 1099511628211 }         // stable across launches, unlike hashValue
        let hue = Double(h % 360) / 360
        return UIGraphicsImageRenderer(size: size).image { ctx in
            let colors = [UIColor(hue: hue, saturation: 0.5, brightness: 0.95, alpha: 1).cgColor, UIColor(hue: (hue + 0.12).truncatingRemainder(dividingBy: 1), saturation: 0.65, brightness: 0.6, alpha: 1).cgColor]
            let g = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0, 1])!
            ctx.cgContext.drawLinearGradient(g, start: .zero, end: CGPoint(x: size.width, y: size.height), options: [])
            UIColor.white.withAlphaComponent(0.55).setFill()
            ctx.cgContext.fillEllipse(in: CGRect(x: size.width * 0.55, y: size.height * 0.18, width: size.width * 0.16, height: size.width * 0.16))
            UIColor(hue: hue, saturation: 0.6, brightness: 0.35, alpha: 0.8).setFill()
            let path = UIBezierPath(); path.move(to: CGPoint(x: 0, y: size.height)); path.addLine(to: CGPoint(x: 0, y: size.height * 0.78))
            path.addQuadCurve(to: CGPoint(x: size.width, y: size.height * 0.72), controlPoint: CGPoint(x: size.width * 0.5, y: size.height * 0.55)); path.addLine(to: CGPoint(x: size.width, y: size.height)); path.fill()
        }
    }

    #if DEBUG
    /// Screenshots: `VMK_DEBUG_ORGANIZE=sheet|single|progress|done|collections`.
    func loadDebugOrganize(_ name: String) {
        debugFrozen = true
        let groups = [OrganizeGroup(name: "London · Apr 2026", count: 214, existing: true, sampleIDs: ["p00000", "p00001", "p00002"]),
                      OrganizeGroup(name: "Phuket · 14-21 Jul 2024", count: 188, sampleIDs: ["p00003", "p00004", "p00005"]),
                      OrganizeGroup(name: "Lisbon · 3-6 Oct 2025", count: 96, sampleIDs: ["p00006", "p00007", "p00008"]),
                      OrganizeGroup(name: "London · May 2026", count: 71, existing: true, sampleIDs: ["p00009", "p00010", "p00011"]),
                      OrganizeGroup(name: "Jun 2025", count: 52, sampleIDs: ["p00012", "p00013", "p00014"])]
            + (0..<9).map { OrganizeGroup(name: "Place \($0) · \($0 + 1)-\($0 + 4) Mar 2025", count: 20, sampleIDs: ["p0001\($0 % 10)"]) }
        let preview = OrganizePreview(total: 842, organized: 805, skipped: 37, home: "London", groups: groups)
        switch name {
        case "sheet", "single": pendingOrganize = OrganizeRequest(since: "2026-11-25T08:00:00", preview: preview, fromBatch: true)
        case "progress":
            var j = OrganizeJob(mode: .auto, since: nil, total: 9800); j.remaining = 8600
            organizeJob = j
        case "done": toast = ToastMessage(text: "Organized into 14 collections", action: "View")
        case "collections": showCollectionsList = true
        default: break
        }
    }
    #endif

    #if DEBUG
    /// Screenshots: `VMK_DEBUG_UPLOAD_SCENE=uploading|queue|done|error` shows that moment of the upload journey without any network.
    func loadDebugScene(_ name: String) {
        debugFrozen = true
        func item(_ n: Int, _ state: QueueItem.State, listed: String? = nil, reason: String? = nil, file: String? = nil) -> QueueItem {
            let id = "dbg\(n)"
            debugLocalImages[id] = Self.fakeImage(seed: "local\(n)", size: CGSize(width: 240, height: 240))
            return QueueItem(id: id, file: file ?? "IMG_\(2000 + n).jpg", size: 1_400_000, sha256: "x\(n)", state: state, libraryID: listed, reason: reason)
        }
        var p = QueueProgress()
        switch name {
        case "uploading", "queue":
            var items: [QueueItem] = [item(0, .done, listed: "p00000"), item(1, .done), item(2, .uploading), item(3, .uploading), item(4, .duplicate), item(5, .failed, reason: "Connection dropped. Tap to try again.", file: "IMG_2047.jpg")]
            items.append(item(6, .failed, reason: "Too large. Photos can be up to 25 MB.", file: "IMG_2042.jpg"))
            for n in 7..<18 { items.append(item(n, .queued)) }
            queueItems = items.reversed()          // the queue keeps pick order and the grid shows newest first: the list below is the grid's order, top first
            p.total = 120; p.done = 38; p.duplicates = 0; p.queued = 71; p.uploading = 6; p.failed = 5
            p.totalBytes = 1_200_000_000; p.doneBytes = 560_000_000
            upload = p; uploadStartedAt = Date().addingTimeInterval(-60); readyTarget = 156; waiting = true
            barExpanded = name == "queue"
        case "error":
            var items: [QueueItem] = (0..<4).map { item($0, .done, listed: "p0000\($0)") }
            items += (4..<16).map { item($0, .noSpace) }
            queueItems = items
            p.total = 100; p.done = 38; p.noSpace = 62; p.totalBytes = 1_000_000_000; p.doneBytes = 380_000_000
            upload = p
        case "done":
            upload = QueueProgress(); queueItems = []
            toast = ToastMessage(text: "120 photos added. 12 were already there.", action: "Got it")
        default: break
        }
    }
    #endif
}

private struct FakePoster: FilePosting { func post(_ file: Data, to url: URL, fields: [String: String]) async throws { try await Task.sleep(for: .milliseconds(120)) } }

/// One list of photos: the timeline, one collection, or search results. Pages in with an opaque cursor; keeps the first page for offline.
@MainActor @Observable
final class PhotoFeed {
    enum Kind: Equatable { case timeline, collection(String) }
    enum State: Equatable { case loading, loaded, failed(String) }

    let kind: Kind
    private let media: MediaModel
    private(set) var photos: [LibraryPhoto] = []
    private(set) var sections: [MediaGrouping.Section] = []
    private(set) var state: State = .loading
    private(set) var offline = false
    private(set) var searching = false
    private(set) var chips: [SearchChip] = []
    private(set) var semantic = false
    private var cursor: String?
    private var loadingMore = false
    private var loadedVersion = -1
    private var searchQuery = ""
    private var searchCursor: String?
    private var dropped: [String] = []
    @ObservationIgnored private let debouncer = SearchDebouncer()
    var text = "" { didSet { if text != oldValue { textChanged() } } }

    init(kind: Kind, media: MediaModel) { self.kind = kind; self.media = media }

    var isSearching: Bool { SearchPlan.decide(text) != .timeline }
    var canLoadMore: Bool { isSearching ? searchCursor != nil : cursor != nil }
    var filter: ItemsFilter { if case .collection(let id) = kind { ItemsFilter(collection: id) } else { ItemsFilter() } }

    /// Loads (or reloads) when the library changed since the last load.
    func refreshIfNeeded() async {
        if loadedVersion == media.version, state == .loaded { return }
        if isSearching { return }          // results are refreshed when the text changes; no re-search while the person types or reads them
        await reload()
    }

    func reload() async {
        loadedVersion = media.version
        if case .search(let q) = SearchPlan.decide(text) { await runSearch(q, drop: dropped); return }
        if photos.isEmpty, let cached = await media.store.cachedPage(key: filter.cacheKey) { set(cached.items); cursor = cached.cursor; state = .loaded }
        else if photos.isEmpty { state = .loading }
        do {
            let page = try await media.api.items(limit: 60, cursor: nil, filter: filter)
            await media.store.savePage(page, key: filter.cacheKey)
            merge(page); state = .loaded; offline = false; chips = []; semantic = false
        } catch is CancellationError {
        } catch {
            if photos.isEmpty { state = .failed((error as? LibraryAPIError)?.message ?? tr("media.err.photos")) } else { state = .loaded; offline = (error as? LibraryAPIError) == .network }
        }
    }

    func loadMore() async {
        if isSearching { await loadMoreSearch(); return }
        guard let c = cursor, !loadingMore else { return }
        loadingMore = true; defer { loadingMore = false }
        do {
            let page = try await media.api.items(limit: 60, cursor: c, filter: filter)      // the cursor goes back exactly as received
            await media.store.remember(page.items)
            let known = Set(photos.map(\.id))
            set(photos + page.items.filter { !known.contains($0.id) }); cursor = page.cursor
        } catch is CancellationError {
        } catch { offline = (error as? LibraryAPIError) == .network }
    }

    /// Timeline-mode search pages with its own opaque cursor (semantic results have none).
    private func loadMoreSearch() async {
        guard let c = searchCursor, !loadingMore, !semantic else { return }
        loadingMore = true; defer { loadingMore = false }
        do {
            let r = try await media.api.search(query: searchQuery, limit: 60, drop: dropped, cursor: c)
            guard SearchPlan.decide(text) == .search(searchQuery) else { return }
            await media.store.remember(r.items)
            let known = Set(photos.map(\.id))
            set(photos + r.items.filter { !known.contains($0.id) }); searchCursor = r.cursor
        } catch is CancellationError {
        } catch { offline = (error as? LibraryAPIError) == .network }
    }

    /// Loads further pages until `count` photos are loaded or there are no more ("select all" in a long result).
    func loadAll(upTo count: Int) async {
        while canLoadMore, photos.count < count, !Task.isCancelled {
            let before = photos.count
            await loadMore()
            if photos.count == before { break }
        }
    }

    private func textChanged() {
        dropped = []
        switch SearchPlan.decide(text) {
        case .timeline: debouncer.cancel(); searching = false; searchCursor = nil; Task { await self.reload() }
        case .search(let q): searching = true; debouncer.schedule { [weak self] in await self?.runSearch(q, drop: []) }
        }
    }

    func runSearch(_ query: String, drop: [String]) async {
        searching = true; searchQuery = query; dropped = drop
        defer { searching = false }
        do {
            let r = try await media.api.search(query: query, limit: 100, drop: drop, cursor: nil)
            guard SearchPlan.decide(text) == .search(query) else { return }     // the person kept typing
            await media.store.remember(r.items)
            semantic = r.mode == "semantic"
            chips = r.understood.chips; set(r.items); cursor = nil; searchCursor = semantic ? nil : r.cursor; state = .loaded; offline = false
        } catch is CancellationError {
        } catch { state = .failed((error as? LibraryAPIError)?.message ?? tr("media.err.search")); photos = []; sections = []; searchCursor = nil }
    }

    func drop(_ chip: SearchChip) async { await runSearch(searchQuery, drop: dropped + [chip.label]) }

    /// New photos go to the top; what was already loaded further down stays, so the scroll position (and any selection) is not lost.
    private func merge(_ page: ItemsPage) {
        guard !photos.isEmpty, let last = page.items.last?.id, let at = photos.firstIndex(where: { $0.id == last }) else { set(page.items); cursor = page.cursor; return }
        let ids = Set(page.items.map(\.id))
        let tail = photos[(at + 1)...].filter { !ids.contains($0.id) }
        set(page.items + tail)
        if tail.isEmpty { cursor = page.cursor }
    }

    func remove(_ ids: Set<String>) { set(photos.filter { !ids.contains($0.id) }) }

    private func set(_ list: [LibraryPhoto]) {
        photos = list
        sections = semantic ? [MediaGrouping.Section(id: "results", title: "", items: list)] : MediaGrouping.sections(list)
    }
}
