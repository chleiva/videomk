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
    @ObservationIgnored private let images = NSCache<NSString, UIImage>()
    @ObservationIgnored private var started = false

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
    }

    func start() async {
        if !started {
            started = true
            await queue.setObserver { [weak self] p in Task { @MainActor in self?.apply(p) } }
        }
        await queue.start()          // continues what a previous launch left in the queue
        await loadSummary()
    }

    func loadSummary() async {
        do {
            let s = try await api.summary()
            summary = s; collections = s.collections; summaryError = nil
        } catch is CancellationError {
        } catch { summaryError = (error as? LibraryAPIError)?.message ?? "Couldn't load your storage." }
    }

    private var lastProcessed = 0
    private func apply(_ p: QueueProgress) {
        let wasFinished = upload.isFinished
        upload = p
        if p.isFinished, !wasFinished || p.processed != lastProcessed, !p.running {
            lastProcessed = p.processed
            Task { await self.loadSummary(); self.version += 1 }
        }
        if p.isEmpty { lastProcessed = 0 }
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
        if unreadable > 0 { notice = "\(unreadable) \(unreadable == 1 ? "photo" : "photos") couldn't be read."; unreadable = 0 }
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
        } catch { notice = (error as? LibraryAPIError)?.message ?? "Couldn't delete. Please try again."; return false }
    }

    func createCollection(name: String, emoji: String? = nil) async -> LibraryCollection? {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return nil }
        do { let c = try await api.createCollection(name: String(n.prefix(40)), emoji: emoji); collections.append(c); return c }
        catch { notice = (error as? LibraryAPIError)?.message ?? "Couldn't create the collection."; return nil }
    }

    func rename(_ c: LibraryCollection, to name: String) async {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return }
        do { let u = try await api.updateCollection(id: c.id, name: String(n.prefix(40)), emoji: nil); if let i = collections.firstIndex(where: { $0.id == c.id }) { collections[i] = u } }
        catch { notice = (error as? LibraryAPIError)?.message ?? "Couldn't rename the collection." }
    }

    func deleteCollection(_ c: LibraryCollection) async {
        do { try await api.deleteCollection(id: c.id); collections.removeAll { $0.id == c.id }; version += 1 }
        catch { notice = (error as? LibraryAPIError)?.message ?? "Couldn't delete the collection." }
    }

    func edit(_ c: LibraryCollection, add: [String] = [], remove: [String] = []) async -> Bool {
        do {
            for chunk in stride(from: 0, to: max(add.count, remove.count), by: 100) {
                try await api.editCollection(id: c.id, add: Array(add.dropFirst(chunk).prefix(100)), remove: Array(remove.dropFirst(chunk).prefix(100)))
            }
            await loadSummary(); version += 1
            return true
        } catch { notice = (error as? LibraryAPIError)?.message ?? "Couldn't update the collection."; return false }
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
        let id = url.lastPathComponent
        let hue = Double(abs(id.hashValue) % 360) / 360
        let full = url.host == "full"
        let size = CGSize(width: full ? 900 : 240, height: full ? 1200 : 240)
        let img = UIGraphicsImageRenderer(size: size).image { ctx in
            let colors = [UIColor(hue: hue, saturation: 0.55, brightness: 0.95, alpha: 1).cgColor, UIColor(hue: (hue + 0.12).truncatingRemainder(dividingBy: 1), saturation: 0.7, brightness: 0.55, alpha: 1).cgColor]
            let g = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors as CFArray, locations: [0, 1])!
            ctx.cgContext.drawLinearGradient(g, start: .zero, end: CGPoint(x: size.width, y: size.height), options: [])
        }
        return img.jpegData(compressionQuality: 0.8) ?? Data()
    }
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
            set(page.items); cursor = page.cursor; state = .loaded; offline = false; chips = []; semantic = false
        } catch is CancellationError {
        } catch {
            if photos.isEmpty { state = .failed((error as? LibraryAPIError)?.message ?? "Couldn't load your photos.") } else { state = .loaded; offline = (error as? LibraryAPIError) == .network }
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
        } catch { state = .failed((error as? LibraryAPIError)?.message ?? "Search didn't work. Please try again."); photos = []; sections = []; searchCursor = nil }
    }

    func drop(_ chip: SearchChip) async { await runSearch(searchQuery, drop: dropped + [chip.label]) }

    func remove(_ ids: Set<String>) { set(photos.filter { !ids.contains($0.id) }) }

    private func set(_ list: [LibraryPhoto]) {
        photos = list
        sections = semantic ? [MediaGrouping.Section(id: "results", title: "", items: list)] : MediaGrouping.sections(list)
    }
}
