import CryptoKit
import Foundation

/// Caches for the Media tab: the first page of each view (so offline still shows something) and the thumbnails, in memory and on disk,
/// keyed by PHOTO ID, never by URL (links expire after an hour, the image never changes). When a link has expired it is refreshed
/// from the server (`GET items/{id}`) and the download is tried once more.
public actor PhotoLibraryStore {
    private let directory: URL
    private let api: any LibraryAPI
    private let fetch: @Sendable (URL) async throws -> Data
    private let memoryLimit: Int
    private var memory: [String: Data] = [:]
    private var order: [String] = []
    private var known: [String: LibraryPhoto] = [:]
    private var inFlight: [String: Task<Data?, Never>] = [:]

    public init(directory: URL, api: any LibraryAPI, memoryLimit: Int = 400, fetch: @escaping @Sendable (URL) async throws -> Data) {
        self.directory = directory; self.api = api; self.memoryLimit = memoryLimit; self.fetch = fetch
        for sub in ["thumbs", "pages"] { try? FileManager.default.createDirectory(at: directory.appendingPathComponent(sub), withIntermediateDirectories: true) }
    }

    // MARK: pages (opaque cursors are stored exactly as received)

    public func remember(_ photos: [LibraryPhoto]) { for p in photos { known[p.id] = p } }
    public func photo(_ id: String) -> LibraryPhoto? { known[id] }

    public func savePage(_ page: ItemsPage, key: String) {
        remember(page.items)
        if let data = try? JSONEncoder().encode(page) { try? data.write(to: file("pages", key, "json"), options: .atomic) }
    }

    public func cachedPage(key: String) -> ItemsPage? {
        guard let data = try? Data(contentsOf: file("pages", key, "json")), let page = try? JSONDecoder().decode(ItemsPage.self, from: data) else { return nil }
        remember(page.items)
        return page
    }

    // MARK: thumbnails

    public func thumbnail(for photo: LibraryPhoto) async -> Data? {
        if let d = memory[photo.id] { touch(photo.id); return d }
        if let d = try? Data(contentsOf: file("thumbs", photo.id, "jpg")) { put(photo.id, d); return d }
        if let running = inFlight[photo.id] { return await running.value }
        let task = Task<Data?, Never> { await self.download(photo) }
        inFlight[photo.id] = task
        let d = await task.value
        inFlight[photo.id] = nil
        return d
    }

    private func download(_ photo: LibraryPhoto) async -> Data? {
        let current = known[photo.id] ?? photo
        if let url = current.thumbURL, let d = try? await fetch(url), !d.isEmpty { store(photo.id, d); return d }
        // The link may have expired: ask for a fresh one once.
        guard let fresh = try? await api.item(id: photo.id), let url = fresh.thumbURL else { return nil }
        known[photo.id] = fresh
        guard let d = try? await fetch(url), !d.isEmpty else { return nil }
        store(photo.id, d)
        return d
    }

    public func forget(_ ids: [String]) {
        for id in ids {
            memory[id] = nil; order.removeAll { $0 == id }; known[id] = nil
            try? FileManager.default.removeItem(at: file("thumbs", id, "jpg"))
        }
    }

    public func removeAll() {
        memory = [:]; order = []; known = [:]
        for sub in ["thumbs", "pages"] {
            try? FileManager.default.removeItem(at: directory.appendingPathComponent(sub))
            try? FileManager.default.createDirectory(at: directory.appendingPathComponent(sub), withIntermediateDirectories: true)
        }
    }

    public func hasOnDisk(_ id: String) -> Bool { FileManager.default.fileExists(atPath: file("thumbs", id, "jpg").path) }

    private func store(_ id: String, _ data: Data) {
        try? data.write(to: file("thumbs", id, "jpg"), options: .atomic)
        put(id, data)
    }

    private func put(_ id: String, _ data: Data) {
        memory[id] = data; touch(id)
        while order.count > memoryLimit { memory[order.removeFirst()] = nil }
    }

    private func touch(_ id: String) { order.removeAll { $0 == id }; order.append(id) }

    /// File names are a hash of the key, so an id or key from the network can never become a path.
    private func file(_ sub: String, _ key: String, _ ext: String) -> URL {
        let name = SHA256.hash(data: Data(key.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appendingPathComponent(sub).appendingPathComponent(name + "." + ext)
    }
}
