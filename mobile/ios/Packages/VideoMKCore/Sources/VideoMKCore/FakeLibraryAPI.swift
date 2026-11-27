import Foundation

/// An in-memory library for unit tests, previews and screenshots. Behaves like the contract (quota, duplicates, search chips, collections).
public actor FakeLibraryAPI: LibraryAPI {
    public private(set) var photos: [LibraryPhoto]
    public private(set) var collectionList: [LibraryCollection]
    public var limitBytes: Int
    public var canUpgrade = false
    public var failNext: LibraryAPIError?
    public private(set) var uploadRequests: [[UploadRequestItem]] = []
    public private(set) var searches: [(query: String, drop: [String], cursor: String?)] = []
    public var semanticMode = false
    public private(set) var lastCursorSeen: String?
    private var hashes: [String: String] = [:]
    // Smart collections: a scripted preview, applied in chunks like the server does (about 300 photos per call).
    public private(set) var pref: OrganizePref = .ask
    public private(set) var organizeCalls: [(mode: String, since: String?, name: String?, collectionID: String?)] = []
    private var script: OrganizePreview?
    private var scriptRemaining = 0
    private var scriptChunk = 300
    private var scriptStarted = false
    private var singleID: String?
    private var organizeDelay: Duration = .zero
    private var fixedCounts: [String: Int] = [:]
    /// Uploaded photos only appear in summary() and items() after this many list calls (the server needs seconds to prepare them).
    public var readyAfter = 0
    private var listCalls = 0
    private var visibleAt: [String: Int] = [:]
    private var serial = 0

    public init(photos: [LibraryPhoto] = [], collections: [LibraryCollection] = [], limitBytes: Int = 2_000_000_000, fixedCounts: [String: Int] = [:]) {
        self.photos = photos; self.collectionList = collections; self.limitBytes = limitBytes; self.fixedCounts = fixedCounts
    }

    /// Pretend this content is already in the library (the real server learns a hash only once the file has arrived).
    public func registerExisting(sha256: String, id: String = "existing") { hashes[sha256] = id }
    public func setReadyAfter(_ n: Int) { readyAfter = n }
    public var summaryCalls: Int { listCalls }
    public func setOrganizeScript(_ p: OrganizePreview?, chunk: Int = 300) { script = p; scriptRemaining = p?.organized ?? 0; scriptChunk = chunk; scriptStarted = false; singleID = nil }
    public func setOrganizeDelay(_ d: Duration) { organizeDelay = d }
    public func setPref(_ p: OrganizePref) { pref = p }
    public func setFailNext(_ e: LibraryAPIError?) { failNext = e }
    public func setLimit(_ n: Int) { limitBytes = n }
    public func setSemantic(_ b: Bool) { semanticMode = b }
    public func setCanUpgrade(_ b: Bool) { canUpgrade = b }

    /// A believable library: `count` photos over 2023 to 2025 in a few places, 1.4 MB each.
    public static func demo(count: Int = 150) -> FakeLibraryAPI {
        let places = ["Phuket, Thailand", "Palma, Spain", "Lisbon, Portugal", "Kyoto, Japan", nil]
        let photos = (0..<count).map { n -> LibraryPhoto in
            let year = 2025 - (n * 3 / max(count, 1)), month = 1 + (n * 7) % 12, day = 1 + (n * 5) % 27
            return LibraryPhoto(id: String(format: "p%05d", n), taken: n % 9 == 8 ? nil : String(format: "%04d-%02d-%02dT1%d:%02d:00", year, month, day, n % 10, n % 60),
                                added: String(format: "%04d-%02d-%02dT09:00:00Z", year, month, day), place: places[n % places.count], w: 1536, h: 2048, bytes: 1_400_000,
                                thumbURL: URL(string: "fake://thumb/p\(String(format: "%05d", n))"), collections: [])
        }
        let autos = [("London · May 2026", 71, "p00003"), ("London · Apr 2026", 214, "p00005"), ("Lisbon · 3-6 Oct 2025", 96, "p00007"), ("Jun 2025", 52, "p00011"), ("Phuket · 14-21 Jul 2024", 188, "p00013")]
        var collections = autos.enumerated().map { LibraryCollection(id: "a\($0.offset + 1)", name: $0.element.0, count: $0.element.1, coverID: $0.element.2, auto: true) }
        collections += [LibraryCollection(id: "c1", name: "Family", emoji: "👨‍👩‍👧", count: 40, coverID: "p00017"), LibraryCollection(id: "c2", name: "Thailand", emoji: "🏝", count: 25, coverID: "p00019")]
        return FakeLibraryAPI(photos: photos, collections: collections, fixedCounts: Dictionary(uniqueKeysWithValues: collections.map { ($0.id, $0.count) }))
    }

    private func check() throws { if let e = failNext { failNext = nil; throw e } }
    private var used: Int { photos.reduce(0) { $0 + $1.bytes } }
    private func listed() -> [LibraryPhoto] { photos.filter { (visibleAt[$0.id] ?? 0) <= listCalls } }
    private func sorted() -> [LibraryPhoto] { listed().sorted { ($0.taken ?? $0.added) > ($1.taken ?? $1.added) } }
    private func refreshCollections() { for n in collectionList.indices { let id = collectionList[n].id; let m = photos.filter { $0.collections.contains(id) }; collectionList[n].count = fixedCounts[id] ?? m.count; if fixedCounts[id] == nil { collectionList[n].coverID = m.first?.id; collectionList[n].coverThumbURL = m.first?.thumbURL } } }

    public func summary() async throws -> LibrarySummary {
        try check(); listCalls += 1; refreshCollections()
        let years = Dictionary(grouping: photos.compactMap { ($0.taken ?? $0.added).prefix(4) }.compactMap { Int($0) }, by: { $0 }).map { LibrarySummary.Year(year: $0.key, count: $0.value.count) }.sorted { $0.year > $1.year }
        let places = Dictionary(grouping: photos.compactMap(\.place), by: { $0 }).map { LibrarySummary.Place(name: String($0.key.split(separator: ",").first ?? ""), country: $0.key.split(separator: ",").last.map { $0.trimmingCharacters(in: .whitespaces) }, count: $0.value.count) }
        return LibrarySummary(plan: "free", limitBytes: limitBytes, usedBytes: used, count: listed().count, canUpgrade: canUpgrade, readOnly: used > limitBytes, prefs: LibraryPrefs(organize: pref), years: years, places: places, collections: collectionList)
    }

    public func requestUploads(_ items: [UploadRequestItem]) async throws -> UploadsResponse {
        try check(); uploadRequests.append(items)
        var reserved = used
        if reserved >= limitBytes && !items.isEmpty { throw LibraryAPIError.storageFull(usedBytes: reserved, limitBytes: limitBytes) }
        var out: [UploadSlotResult] = []
        for (n, item) in items.enumerated() {
            if let dup = hashes[item.sha256] { out.append(UploadSlotResult(index: n, status: .duplicate, duplicateOf: dup)); continue }
            if reserved + item.size > limitBytes { out.append(UploadSlotResult(index: n, status: .noSpace)); continue }
            serial += 1
            let id = "u\(serial)"
            reserved += item.size
            visibleAt[id] = listCalls + readyAfter
            photos.append(LibraryPhoto(id: id, taken: item.taken, added: "2026-11-25T10:00:00Z", w: 0, h: 0, bytes: item.size, thumbURL: URL(string: "fake://thumb/\(id)")))
            out.append(UploadSlotResult(index: n, status: .upload, id: id, url: URL(string: "https://media.example/upload")!, fields: ["key": "u/me/o/\(id).jpg", "policy": "P"]))
        }
        return UploadsResponse(uploads: out, usedBytes: reserved, limitBytes: limitBytes)
    }

    public func items(limit: Int, cursor: String?, filter: ItemsFilter) async throws -> ItemsPage {
        try check(); listCalls += 1; lastCursorSeen = cursor
        var all = sorted()
        if let c = filter.collection { all = all.filter { $0.collections.contains(c) } }
        if let p = filter.place { all = all.filter { ($0.place ?? "").localizedCaseInsensitiveContains(p) } }
        if let f = filter.from { all = all.filter { ($0.taken ?? $0.added) >= f } }
        if let t = filter.to { all = all.filter { String(($0.taken ?? $0.added).prefix(10)) <= t } }
        let start = cursor.flatMap { Int($0.replacingOccurrences(of: "pos:", with: "")) } ?? 0
        let page = Array(all.dropFirst(start).prefix(limit))
        return ItemsPage(items: page, cursor: start + page.count < all.count ? "pos:\(start + page.count)" : nil)
    }

    public func item(id: String) async throws -> LibraryPhoto {
        try check()
        guard var p = photos.first(where: { $0.id == id }) else { throw LibraryAPIError.notFound }
        p.url = URL(string: "fake://full/\(id)"); return p
    }

    public func delete(ids: [String]) async throws -> DeleteResult {
        try check()
        let before = photos.count
        photos.removeAll { ids.contains($0.id) }
        hashes = hashes.filter { !ids.contains($0.value) }
        return DeleteResult(deleted: before - photos.count, usedBytes: used)
    }

    public func search(query: String, limit: Int?, drop: [String], cursor: String?) async throws -> SearchResponse {
        try check(); searches.append((query, drop, cursor))
        var chips: [SearchChip] = []
        var matched = sorted()
        let words = query.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        for place in Set(photos.compactMap { $0.place?.split(separator: ",").first.map(String.init) }) where words.contains(place.lowercased()) {
            let chip = SearchChip(kind: "place", label: place)
            if !drop.contains(chip.label) { chips.append(chip); matched = matched.filter { ($0.place ?? "").hasPrefix(place) } }
        }
        for w in words where w.count == 4 && Int(w) != nil {
            let chip = SearchChip(kind: "date", label: w)
            if !drop.contains(chip.label) { chips.append(chip); matched = matched.filter { ($0.taken ?? $0.added).hasPrefix(w) } }
        }
        let understood = SearchUnderstood(places: chips.filter { $0.kind == "place" }.map(\.label), chips: chips)
        if semanticMode { return SearchResponse(understood: understood, items: Array(matched.reversed().prefix(min(limit ?? 60, 100))), mode: "semantic") }   // relevance order (here: oldest first), no cursor
        let start = cursor.flatMap { Int($0.replacingOccurrences(of: "pos:", with: "")) } ?? 0
        let page = Array(matched.dropFirst(start).prefix(limit ?? 60))
        return SearchResponse(understood: understood, items: page, mode: "timeline", cursor: start + page.count < matched.count ? "pos:\(start + page.count)" : nil)
    }

    public func collections() async throws -> [LibraryCollection] { try check(); refreshCollections(); return collectionList }

    public func createCollection(name: String, emoji: String?) async throws -> LibraryCollection {
        try check()
        guard (1...40).contains(name.count) else { throw LibraryAPIError.invalid("Choose a name of 1 to 40 characters.") }
        serial += 1
        let c = LibraryCollection(id: "c\(100 + serial)", name: name, emoji: emoji, count: 0)
        collectionList.append(c); return c
    }

    public func updateCollection(id: String, name: String?, emoji: String?) async throws -> LibraryCollection {
        try check()
        guard let n = collectionList.firstIndex(where: { $0.id == id }) else { throw LibraryAPIError.notFound }
        if let name { collectionList[n].name = name }
        if let emoji { collectionList[n].emoji = emoji }
        return collectionList[n]
    }

    public func deleteCollection(id: String) async throws {
        try check()
        collectionList.removeAll { $0.id == id }
        for n in photos.indices { photos[n].collections.removeAll { $0 == id } }
    }

    public func organizePreview(since: String?) async throws -> OrganizePreview {
        try check(); organizeCalls.append(("preview", since, nil, nil))
        return script ?? OrganizePreview(total: 0, organized: 0, skipped: 0, groups: [])
    }

    public func organizeApply(mode: String, since: String?, name: String?, collectionID: String?) async throws -> OrganizeApplyResult {
        try check(); organizeCalls.append((mode, since, name, collectionID))
        if organizeDelay != .zero { try? await Task.sleep(for: organizeDelay) }
        guard let script else { return OrganizeApplyResult(applied: 0, remaining: 0) }
        let n = min(scriptChunk, scriptRemaining)
        scriptRemaining -= n
        var created = 0
        if mode == "single" {
            if singleID == nil && collectionID == nil {
                serial += 1; singleID = "c\(500 + serial)"; created = 1
                collectionList.append(LibraryCollection(id: singleID!, name: name ?? "Collection", count: script.organized))
                fixedCounts[singleID!] = script.organized
            }
            return OrganizeApplyResult(applied: n, remaining: scriptRemaining, created: created, collectionID: collectionID ?? singleID)
        }
        if !scriptStarted {
            scriptStarted = true
            for g in script.groups where !g.existing {
                serial += 1; created += 1
                let id = "a\(serial)"
                collectionList.append(LibraryCollection(id: id, name: g.name, count: g.count, auto: true)); fixedCounts[id] = g.count
            }
        }
        return OrganizeApplyResult(applied: n, remaining: scriptRemaining, created: created, updated: script.groups.filter(\.existing).count, skipped: script.skipped)
    }

    public func setOrganizePref(_ p: OrganizePref) async throws { try check(); pref = p }

    public func editCollection(id: String, add: [String], remove: [String]) async throws {
        try check()
        guard collectionList.contains(where: { $0.id == id }) else { throw LibraryAPIError.notFound }
        for n in photos.indices {
            if add.contains(photos[n].id), !photos[n].collections.contains(id) { photos[n].collections.append(id) }
            if remove.contains(photos[n].id) { photos[n].collections.removeAll { $0 == id } }
        }
    }
}

/// Records posts; can be told to fail some of them. For tests.
public actor FakeFilePoster: FilePosting {
    public private(set) var posts: [(url: URL, fields: [String: String], bytes: Int)] = []
    public private(set) var inFlight = 0, peak = 0
    private var failures: [Int: Int] = [:]    // first byte of the file -> how many times it must fail
    private var delay: Duration = .zero
    public init(delay: Duration = .zero) { self.delay = delay }
    public func failing(firstByte: UInt8, times: Int) { failures[Int(firstByte)] = times }
    public func post(_ file: Data, to url: URL, fields: [String: String]) async throws {
        inFlight += 1; peak = max(peak, inFlight)
        if delay != .zero { try? await Task.sleep(for: delay) }
        inFlight -= 1
        if let b = file.first, let left = failures[Int(b)], left > 0 { failures[Int(b)] = left - 1; throw LibraryAPIError.server }
        posts.append((url, fields, file.count))
    }
}

/// Capabilities and the request check for tests and previews. Responses are served in order; the last one repeats.
public actor FakeCreateAPI: CreateServing {
    public private(set) var requests: [BriefRequest] = []
    private var caps: Result<CreateCapabilities, Error>
    private var responses: [BriefResponse]
    private var delay: Duration
    private var fails = false
    private let deckScript: FakeDeckScript
    private var deckPolls: [String: Int] = [:]
    public private(set) var deckCalls: [String] = []          // "slot", "process", "status": what the app asked (never any file content)

    public init(capabilities: Result<CreateCapabilities, Error> = .success(FakeCreateAPI.richCapabilities),
                responses: [BriefResponse] = [.ok(brief: [:])], delay: Duration = .zero, deck: FakeDeckScript = FakeDeckScript()) {
        self.caps = capabilities; self.responses = responses; self.delay = delay; self.deckScript = deck
    }
    public func setFails(_ b: Bool) { fails = b }
    public func capabilities() async throws -> CreateCapabilities { try caps.get() }
    public func checkRequest(_ request: BriefRequest) async throws -> BriefResponse {
        requests.append(request)
        if delay != .zero { try await Task.sleep(for: delay) }
        if fails { throw APIError.network }
        let i = min(requests.count - 1, responses.count - 1)
        return responses[i]
    }
}

extension FakeCreateAPI {
    /// The capabilities the server now sends: every aspect ready (three of them beta), short lengths, and a recommendation per platform.
    public static var richCapabilities: CreateCapabilities { capabilities(fourK: false) }
    /// The same with 4K switched on: a third resolution at twice the credits, which only YouTube and "Just a video" deliver.
    public static var fourKCapabilities: CreateCapabilities { capabilities(fourK: true) }

    static func capabilities(fourK: Bool) -> CreateCapabilities {
        typealias P0 = CreateCapabilities.Platform
        func P(id: String, label: String, aspect: String, resolution: String, note: String, recommendedMinutes: Double, maxMinutes: Double?, otherAspects: [String]) -> P0 {
            let ok = id == "youtube" || id == "other"
            return P0(id: id, label: label, aspect: aspect, resolution: resolution, note: note, recommendedMinutes: recommendedMinutes, maxMinutes: maxMinutes, otherAspects: otherAspects,
                      supports4K: ok, note4K: ok ? nil : "\(label) publishes at 1080p or lower; 4K would cost twice the credits for no visible gain.")
        }
        return CreateCapabilities(
            aspects: [.init(id: "16:9", label: "Landscape"), .init(id: "9:16", label: "Vertical", ready: true, beta: true), .init(id: "1:1", label: "Square", ready: true, beta: true), .init(id: "4:5", label: "Portrait", ready: true, beta: true)],
            resolutions: [.init(id: "720p"), .init(id: "1080p")] + (fourK ? [.init(id: "2160p", label: "4K", creditsMultiplier: 2, aspects: ["16:9", "9:16", "1:1", "4:5"], note: "4K (2160p) costs twice the credits. Best for YouTube and large screens.")] : []),
            platforms: [
                P(id: "youtube", label: "YouTube", aspect: "16:9", resolution: "1080p", note: "Landscape 16:9 · 1080p · about 3 min", recommendedMinutes: 3, maxMinutes: nil, otherAspects: []),
                P(id: "shorts", label: "YouTube Shorts", aspect: "9:16", resolution: "1080p", note: "Vertical 9:16 · 1080p · about 45 s", recommendedMinutes: 0.75, maxMinutes: 3, otherAspects: []),
                P(id: "tiktok", label: "TikTok", aspect: "9:16", resolution: "1080p", note: "Vertical 9:16 · 1080p · about 45 s", recommendedMinutes: 0.75, maxMinutes: 10, otherAspects: []),
                P(id: "reels", label: "Reels", aspect: "9:16", resolution: "1080p", note: "Vertical 9:16 · 1080p · about 30 s", recommendedMinutes: 0.5, maxMinutes: 3, otherAspects: []),
                P(id: "instagram_feed", label: "Instagram", aspect: "4:5", resolution: "1080p", note: "Portrait 4:5 · 1080p · about 30 s", recommendedMinutes: 0.5, maxMinutes: 1, otherAspects: ["1:1"]),
                P(id: "linkedin", label: "LinkedIn", aspect: "4:5", resolution: "1080p", note: "Portrait 4:5 · 1080p · about 1 min", recommendedMinutes: 1, maxMinutes: 10, otherAspects: ["1:1", "16:9"]),
                P(id: "x", label: "X", aspect: "16:9", resolution: "1080p", note: "Landscape 16:9 · 1080p · about 45 s", recommendedMinutes: 0.75, maxMinutes: 2.3333, otherAspects: ["1:1"]),
                P(id: "other", label: "Just a video", aspect: "16:9", resolution: "1080p", note: "Landscape 16:9 · 1080p · about 3 min", recommendedMinutes: 3, maxMinutes: nil, otherAspects: ["9:16", "1:1", "4:5"]),
            ],
            languages: [.init(id: "en", label: "English"), .init(id: "es", label: "Español")], intake: true,
            lengths: .init(minMinutes: 0.25, maxMinutes: 12, presets: [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12]))
    }
}

// MARK: presentation decks (fake)

/// How the fake server treats a deck. `VMK_DEBUG_DECK=ok|slow|uploading|processing|offline|fail:<code>` (see mobile/ios/README.md).
public struct FakeDeckScript: Sendable, Equatable {
    public enum Outcome: Sendable, Equatable { case ready(slides: Int, minutes: Double, credits: Int), failed(code: String) }
    public enum Stall: Sendable, Equatable { case uploading, processing }
    public var outcome: Outcome = .ready(slides: 12, minutes: 4, credits: 4)
    /// How many status calls answer "processing" before the outcome.
    public var processingPolls = 2
    /// The upload fails this many times (a lost connection) and then works.
    public var uploadFailures = 0
    public var stall: Stall?
    public init() {}

    public static func parse(_ spec: String) -> FakeDeckScript {
        var s = FakeDeckScript()
        switch spec {
        case "slow": s.processingPolls = 8
        case "uploading": s.stall = .uploading
        case "processing": s.stall = .processing
        case "offline": s.uploadFailures = 1
        case "ok", "": break
        case "short": s.outcome = .ready(slides: 3, minutes: 1, credits: 1)
        case "long": s.outcome = .ready(slides: 48, minutes: 12, credits: 12)
        default:
            if spec.hasPrefix("fail:") { s.outcome = .failed(code: String(spec.dropFirst(5))) }
        }
        return s
    }
}

extension FakeCreateAPI: DeckServing {
    public func requestSlot(format: String, size: Int) async throws -> DeckSlot {
        deckCalls.append("slot")
        return DeckSlot(id: "fakedeck1", format: format, url: URL(string: "https://upload.invalid/deck")!, fields: ["key": "fake"])
    }
    public func process(deckID: String) async throws { deckCalls.append("process") }
    public func status(deckID: String) async throws -> DeckStatus {
        deckCalls.append("status")
        let n = (deckPolls[deckID] ?? 0) + 1
        deckPolls[deckID] = n
        if deckScript.stall == .processing || n <= deckScript.processingPolls { return .processing }
        switch deckScript.outcome {
        case .ready(let slides, let minutes, let credits): return .ready(DeckReady(slides: slides, suggestedMinutes: minutes, suggestedCredits: credits))
        case .failed(let code): return .failed(code: code, message: "Server message for \(code)")
        }
    }
}

/// An upload that never touches the network: progress in steps, optional stalls and failures.
public final class FakeDeckUploader: DeckUploading, @unchecked Sendable {
    private let lock = NSLock()
    private let script: FakeDeckScript
    private let stepDelay: Double
    private var failuresLeft: Int
    private var _uploads = 0
    public init(_ script: FakeDeckScript = FakeDeckScript(), stepDelay: Double = 0.15) { self.script = script; self.stepDelay = stepDelay; failuresLeft = script.uploadFailures }
    public var uploads: Int { lock.withLock { _uploads } }

    public func upload(file: URL, to slot: DeckSlot, progress: @escaping @Sendable (Double) -> Void) async throws {
        lock.withLock { _uploads += 1 }
        for step in 1...5 {
            try await Task.sleep(for: .seconds(stepDelay))
            progress(Double(step) * 0.2 * (script.stall == .uploading ? 0.45 : 1))
            if script.stall == .uploading, step == 2 { try await Task.sleep(for: .seconds(3600)) }
            if step == 3, lock.withLock({ if failuresLeft > 0 { failuresLeft -= 1; return true } else { return false } }) { throw DeckError(.network) }
        }
    }
}

public extension DeckCapabilities { static var fake: DeckCapabilities { DeckCapabilities(maxMB: 50, maxSlides: 60, formats: ["pptx", "pdf"]) } }

public extension CreateCapabilities {
    /// The same capabilities with the deck feature on (the server sends `deck` only when it is enabled).
    func withDeck(_ deck: DeckCapabilities = .fake) -> CreateCapabilities { var c = self; c.deck = deck; return c }
}

// MARK: the chosen look (fake)

public extension LookCapabilities {
    /// The picker as docs/CREATE_API.md describes it, without pictures (tiles and faces then draw their placeholders): four looks, ten characters, the board extra.
    /// Screenshot runs load the real thing, pictures included, from a file (`from(file:)`).
    static var fake: LookCapabilities {
        let all = ["16:9", "9:16", "1:1", "4:5"]
        func m(_ id: String, _ name: String, _ role: String, _ kind: String, _ topic: String) -> Member { Member(id: id, name: name, role: role, kind: kind, topic: topic) }
        return LookCapabilities(options: [
            Option(id: "auto", label: "Auto", note: "Picked for your topic", minSeconds: 15, aspects: all, bestAspects: all),
            Option(id: "real", label: "Real", note: "Photos and footage", minSeconds: 15, aspects: all, bestAspects: all),
            Option(id: "whiteboard", label: "Whiteboard", note: "Drawn by hand", withPhotos: false, withDeck: false, minSeconds: 15, aspects: all, bestAspects: ["16:9", "1:1"]),
            Option(id: "cartoon", label: "Cartoon", note: "Characters explain it", withPhotos: false, withDeck: false, minSeconds: 15, aspects: all, bestAspects: ["16:9", "1:1", "4:5"], cast: true,
                   extras: [Extra(id: "board", label: "Characters explain at a board", note: "A board beside them is drawn by hand as they speak.")]),
        ], cast: Cast(min: 1, max: 3, autoLabel: "Auto", autoNote: "We pick for you. Or choose up to 3.", conversationFrom: 2, conversationMinSeconds: 20, conversationNote: "They talk it through.", members: [
            m("ines", "Inés", "Teacher", "person", "Learning"), m("david", "David", "Engineer", "person", "Technology"), m("priya", "Priya", "Doctor", "person", "Health"), m("mateo", "Mateo", "Chef", "person", "Food"),
            m("fox", "Fox", "Guide for children", "animal", "For children"), m("owl", "Hugo", "Owl professor", "animal", "Science and history"), m("bear", "Bruno", "Caring bear", "animal", "Feelings and bedtime"),
            m("cat", "Mika", "Curious cat", "animal", "How things work"), m("parrot", "Paco", "Travelling parrot", "animal", "Travel and languages"), m("turtle", "Tula", "Wise turtle", "animal", "Nature"),
        ]))
    }

    /// A capabilities answer saved to a file (`{"looks": {...}}`, the server's own JSON): the fixture of UI tests and screenshots.
    static func from(file path: String) -> LookCapabilities? {
        guard let data = FileManager.default.contents(atPath: path), case .object(let o)? = try? JSONDecoder().decode(AnyJSON.self, from: data) else { return nil }
        return LookCapabilities(json: o["looks"])
    }

    /// Variants for tests and screenshots: `locked` (Cartoon needs the Pro plan), `soon` (this stage has no Whiteboard), `noboard` (the extra is not listed), `short` (Cartoon needs 30 s).
    func variant(_ name: String) -> LookCapabilities {
        var c = self
        func edit(_ id: String, _ change: (inout Option) -> Void) { if let i = c.options.firstIndex(where: { $0.id == id }) { change(&c.options[i]) } }
        for part in name.split(separator: ",") {
            switch part {
            case "locked": edit("cartoon") { $0.allowed = false; $0.requiresPlan = "Pro" }
            case "lockedplain": edit("cartoon") { $0.allowed = false; $0.requiresPlan = nil }
            case "soon": edit("whiteboard") { $0.available = false }
            case "noboard": edit("cartoon") { $0.extras = [] }
            case "short": edit("cartoon") { $0.minSeconds = 30 }
            default: break
            }
        }
        return c
    }
}

public extension CreateCapabilities {
    /// The same capabilities with the look picker (the server sends `looks.look` once the engine has it).
    func withLooks(_ looks: LookCapabilities? = .fake) -> CreateCapabilities { var c = self; c.looks = looks; return c }
}

public enum FakeLook {
    /// What the fake server answers about a chosen look: the contract's cases the app can reach (a conversation in a video that is too short; `force` for screenshots).
    public static func started(videoID: String, options: CreateOptions, photos: Bool, caps: LookCapabilities?, spanish: Bool = false) -> StartedVideo {
        let c = options.lookChoice
        guard !c.isAuto else { return StartedVideo(videoID: videoID) }
        let label = caps?.option(c.look)?.label ?? c.look
        if photos, caps?.option(c.look)?.withPhotos == false {
            return StartedVideo(videoID: videoID, look: AppliedLook(chosen: c.look, applied: "real", reason: "own_photos"),
                                note: spanish ? "Lo hacemos con tus fotos: el estilo \(label) no se usa con tus propias fotos." : "Made from your photos: the \(label) look is not used with your own photos.")
        }
        if c.cast.count >= 2, options.minutes * 60 < (caps?.cast?.conversationMinSeconds ?? 20) {
            return StartedVideo(videoID: videoID, look: AppliedLook(chosen: c.look, applied: c.look, cast: [c.cast[0]], extras: c.extras, reason: "too_short"),
                                note: spanish ? "Presenta un solo personaje. Una conversación necesita 20 s o más." : "One character presents. A conversation needs 20 s or more.")
        }
        return StartedVideo(videoID: videoID, look: AppliedLook(chosen: c.look, applied: c.look, cast: c.cast, extras: c.extras))
    }
}
