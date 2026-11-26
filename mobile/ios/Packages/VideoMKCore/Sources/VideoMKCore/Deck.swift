import Foundation
import Observation

// Presentation decks (PowerPoint or PDF) to video. Contract: docs/CREATE_API.md "Making a video from a presentation deck", design: docs/DECK_TO_VIDEO.md.
// The feature exists only where the server says so (`capabilities.deck`). Nothing here ever logs a file name or content.

/// `capabilities.deck`: present only when the server has the feature on.
public struct DeckCapabilities: Codable, Sendable, Equatable {
    public let maxMB: Int
    public let maxSlides: Int
    public let formats: [String]
    enum CodingKeys: String, CodingKey { case maxMB = "max_mb", maxSlides = "max_slides", formats }
    public init(maxMB: Int = 50, maxSlides: Int = 60, formats: [String] = ["pptx", "pdf"]) { self.maxMB = maxMB; self.maxSlides = maxSlides; self.formats = formats }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        maxMB = (try? c.decode(Int.self, forKey: .maxMB)) ?? 50
        maxSlides = (try? c.decode(Int.self, forKey: .maxSlides)) ?? 60
        let f = ((try? c.decode([String].self, forKey: .formats)) ?? []).map { $0.lowercased() }
        formats = f.isEmpty ? ["pptx", "pdf"] : f
    }
    public var maxBytes: Int { maxMB * 1024 * 1024 }
    /// The file types the Files picker offers (uniform type identifiers are chosen by the app from these extensions).
    public func accepts(_ ext: String) -> Bool { formats.contains(ext.lowercased()) }
}

/// What the person can do about a problem.
public enum DeckAction: Sendable, Equatable {
    case pickAnother      // choose a different file
    case chooseAgain      // the same file again (the server's copy is gone: it has to be sent again)
    case retry            // send the same file again (it is still on the phone)
    case checkAgain       // the upload is done and the server is still working: look again
}

/// Every way a deck can fail, with a calm localized message of its own. The server's `code` picks the case; its own `message` is only the fallback for a code this app does not know.
public enum DeckProblem: Sendable, Equatable {
    case tooLarge(maxMB: Int)
    case tooManySlides(max: Int)
    case unsupported
    case exportFirst(ext: String)      // .ppt, .pptm, .key, .odp: export as .pptx or PDF
    case corrupt, encrypted, macro, empty, unsafe
    case convertTimeout, convertFailed
    case stillWorking                  // the app stopped waiting; the server may still finish
    case network, tooManyDecks, server
    case other(String)

    public static func from(code: String, message: String? = nil, caps: DeckCapabilities = DeckCapabilities()) -> DeckProblem {
        switch code {
        case "deck_too_large": .tooLarge(maxMB: caps.maxMB)
        case "deck_too_many_slides": .tooManySlides(max: caps.maxSlides)
        case "deck_unsupported": .unsupported
        case "deck_corrupt": .corrupt
        case "deck_encrypted": .encrypted
        case "deck_macro": .macro
        case "deck_empty": .empty
        case "deck_unsafe": .unsafe
        case "deck_convert_timeout": .convertTimeout
        case "deck_convert_failed": .convertFailed
        case "too_many_decks": .tooManyDecks
        default: message.flatMap { $0.isEmpty ? nil : $0 }.map(DeckProblem.other) ?? .server
        }
    }

    public var title: String {
        switch self {
        case .tooLarge: tr("deck.err.too_large.title")
        case .tooManySlides: tr("deck.err.too_many_slides.title")
        case .unsupported, .exportFirst: tr("deck.err.unsupported.title")
        case .corrupt: tr("deck.err.corrupt.title")
        case .encrypted: tr("deck.err.encrypted.title")
        case .macro: tr("deck.err.macro.title")
        case .empty: tr("deck.err.empty.title")
        case .unsafe: tr("deck.err.unsafe.title")
        case .convertTimeout, .convertFailed: tr("deck.err.convert.title")
        case .stillWorking: tr("deck.err.slow.title")
        case .network: tr("deck.err.network.title")
        case .tooManyDecks: tr("deck.err.too_many_decks.title")
        case .server, .other: tr("deck.err.server.title")
        }
    }

    public var message: String {
        switch self {
        case .tooLarge(let mb): tr("deck.err.too_large.message", mb)
        case .tooManySlides(let n): tr("deck.err.too_many_slides.message", n)
        case .unsupported: tr("deck.err.unsupported.message")
        case .exportFirst(let ext): tr("deck.err.export_first.message", ext.uppercased())
        case .corrupt: tr("deck.err.corrupt.message")
        case .encrypted: tr("deck.err.encrypted.message")
        case .macro: tr("deck.err.macro.message")
        case .empty: tr("deck.err.empty.message")
        case .unsafe: tr("deck.err.unsafe.message")
        case .convertTimeout: tr("deck.err.convert_timeout.message")
        case .convertFailed: tr("deck.err.convert_failed.message")
        case .stillWorking: tr("deck.err.slow.message")
        case .network: tr("deck.err.network.message")
        case .tooManyDecks: tr("deck.err.too_many_decks.message")
        case .server: tr("deck.err.server.message")
        case .other(let m): m
        }
    }

    /// The main thing to offer. `hasLocalFile`: the upload did not finish, so the file is still on the phone and sending it again is possible.
    public func action(hasLocalFile: Bool = false) -> DeckAction {
        switch self {
        case .convertTimeout, .convertFailed: .chooseAgain
        case .stillWorking: .checkAgain
        case .network, .server: hasLocalFile ? .retry : .checkAgain
        case .tooManyDecks: .pickAnother
        default: .pickAnother
        }
    }

    public var isTransient: Bool { switch self { case .network, .server, .stillWorking: true; default: false } }
}

/// Checks a picked file before anything is uploaded: format first, then size.
public enum DeckFileCheck {
    /// The old and unsupported kinds the app answers with "export it as .pptx or PDF".
    static let exportable: Set<String> = ["ppt", "pptm", "pps", "ppsx", "key", "odp", "pot", "potx"]

    public enum Result: Equatable, Sendable {
        case ok(format: String)
        case problem(DeckProblem)
    }

    public static func check(fileName: String, bytes: Int, caps: DeckCapabilities) -> Result {
        let ext = (fileName as NSString).pathExtension.lowercased()
        if caps.accepts(ext) {
            if bytes <= 0 { return .problem(.empty) }
            if bytes > caps.maxBytes { return .problem(.tooLarge(maxMB: caps.maxMB)) }
            return .ok(format: ext)
        }
        return .problem(exportable.contains(ext) ? .exportFirst(ext: ext) : .unsupported)
    }

    /// "report.pptx" shown on the ready card: the base name, never a path.
    public static func displayName(_ fileName: String) -> String { (fileName as NSString).lastPathComponent }
}

/// The presigned POST that `POST /decks` returns.
public struct DeckSlot: Sendable, Equatable, Decodable {
    public let id: String
    public let format: String
    public let url: URL
    public let fields: [String: String]
    public init(id: String, format: String, url: URL, fields: [String: String] = [:]) { self.id = id; self.format = format; self.url = url; self.fields = fields }

    public var contentType: String { format == "pdf" ? "application/pdf" : "application/vnd.openxmlformats-officedocument.presentationml.presentation" }
}

struct DeckSlotResponse: Decodable { let deck: DeckSlot }

/// A deck the server finished reading.
public struct DeckReady: Sendable, Equatable, Decodable {
    public let slides: Int
    public let suggestedMinutes: Double
    public let suggestedCredits: Int
    enum CodingKeys: String, CodingKey { case slides, suggestedMinutes = "suggested_minutes", suggestedCredits = "suggested_credits" }
    public init(slides: Int, suggestedMinutes: Double, suggestedCredits: Int) { self.slides = slides; self.suggestedMinutes = suggestedMinutes; self.suggestedCredits = suggestedCredits }
    public var price: DeckPrice { DeckPrice(suggestedMinutes: suggestedMinutes, suggestedCredits: suggestedCredits) }
}

public enum DeckStatus: Sendable, Equatable {
    case uploading, processing
    case ready(DeckReady)
    case failed(code: String, message: String?)

    public static func decode(_ data: Data) -> DeckStatus? {
        struct Raw: Decodable { let status: String; let slides: Int?; let suggested_minutes: Double?; let suggested_credits: Int?; let code: String?; let message: String? }
        guard let r = try? JSONDecoder().decode(Raw.self, from: data) else { return nil }
        switch r.status {
        case "uploading": return .uploading
        case "processing": return .processing
        case "ready":
            guard let s = r.slides, s > 0, let m = r.suggested_minutes, m > 0, let c = r.suggested_credits, c > 0 else { return nil }
            return .ready(DeckReady(slides: s, suggestedMinutes: m, suggestedCredits: c))
        case "failed": return .failed(code: r.code ?? "deck_corrupt", message: r.message)
        default: return nil
        }
    }
}

/// What a deck costs: the server's price at its suggested length, and the usual rule (started minutes, 4K doubles) for any other length.
public struct DeckPrice: Sendable, Equatable {
    public let suggestedMinutes: Double
    public let suggestedCredits: Int
    public init(suggestedMinutes: Double, suggestedCredits: Int) { self.suggestedMinutes = suggestedMinutes; self.suggestedCredits = suggestedCredits }

    public func credits(minutes: Double, multiplier: Int = 1) -> Int {
        let base = abs(minutes - suggestedMinutes) < 1e-6 ? suggestedCredits : max(1, min(12, Int(minutes.rounded(.up))))
        return base * max(1, multiplier)
    }
}

/// A failure that already carries its message.
public struct DeckError: Error, Sendable, Equatable { public let problem: DeckProblem; public init(_ p: DeckProblem) { problem = p } }

public protocol DeckServing: Sendable {
    func requestSlot(format: String, size: Int) async throws -> DeckSlot
    func process(deckID: String) async throws
    func status(deckID: String) async throws -> DeckStatus
}

extension APIClient: DeckServing {
    private func fail(_ http: HTTPURLResponse, _ data: Data) -> DeckError {
        struct Body: Decodable { let code: String?; let message: String? }
        let b = try? JSONDecoder().decode(Body.self, from: data)
        switch http.statusCode {
        case 400, 404, 409, 429:
            if let code = b?.code { return DeckError(.from(code: code, message: b?.message)) }
            return DeckError(http.statusCode == 429 ? .tooManyDecks : .server)
        default: return DeckError(.server)
        }
    }

    private func call(_ method: String, _ path: [String], body: Data? = nil) async throws -> (Data, HTTPURLResponse) {
        do { return try await perform(method, path, body: body) }
        catch let e as APIError where e == .network { throw DeckError(.network) }
    }

    public func requestSlot(format: String, size: Int) async throws -> DeckSlot {
        let body = try JSONSerialization.data(withJSONObject: ["format": format, "size": size] as [String: Any])
        let (data, http) = try await call("POST", ["decks"], body: body)
        guard (200..<300).contains(http.statusCode) else { throw fail(http, data) }
        guard let r = try? JSONDecoder().decode(DeckSlotResponse.self, from: data) else { throw DeckError(.server) }
        return r.deck
    }

    public func process(deckID: String) async throws {
        let (data, http) = try await call("POST", ["decks", deckID, "process"])
        // 400 "missing": the upload did not finish; 404: unknown deck. Both end as a plain problem the person can retry.
        guard (200..<300).contains(http.statusCode) else { throw http.statusCode == 400 ? DeckError(.network) : fail(http, data) }
    }

    public func status(deckID: String) async throws -> DeckStatus {
        let (data, http) = try await call("GET", ["decks", deckID])
        guard (200..<300).contains(http.statusCode) else { throw fail(http, data) }
        guard let s = DeckStatus.decode(data) else { throw DeckError(.server) }
        return s
    }
}

/// A video is made from a presentation or from photos, never both: choosing one removes the other, after asking when something would be lost.
public enum AttachRule {
    public enum Step: Sendable, Equatable { case go, confirm }
    public static func deck(photos: Int) -> Step { photos > 0 ? .confirm : .go }
    public static func photos(deckActive: Bool) -> Step { deckActive ? .confirm : .go }
}

// MARK: upload

/// Sends the file to the presigned form. Separate from `DeckServing` because it never carries the login token.
public protocol DeckUploading: Sendable {
    func upload(file: URL, to slot: DeckSlot, progress: @escaping @Sendable (Double) -> Void) async throws
}

/// Streams the file: the multipart body is written to a temporary file (the signed fields first, the file last, as S3 requires) and sent from disk, so a 50 MB deck is never held in memory.
/// Foreground only: the transfer stops if the app is closed, and the screen says so (a background session would need app-delegate plumbing for a one-off 50 MB upload at most).
public struct DeckS3Uploader: DeckUploading {
    public init() {}

    public func upload(file: URL, to slot: DeckSlot, progress: @escaping @Sendable (Double) -> Void) async throws {
        let boundary = UUID().uuidString
        let body = file.deletingLastPathComponent().appendingPathComponent("\(UUID().uuidString).body")
        defer { try? FileManager.default.removeItem(at: body) }
        try Self.writeBody(to: body, fields: slot.fields, file: file, mimeType: slot.contentType, boundary: boundary)
        var req = URLRequest(url: slot.url, timeoutInterval: 300)
        req.httpMethod = "POST"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        // deliberately no Authorization header: the presigned fields are the credential
        let watcher = ProgressWatcher(progress)
        let session = URLSession(configuration: .ephemeral)
        defer { session.finishTasksAndInvalidate() }
        do {
            let (_, resp) = try await session.upload(for: req, fromFile: body, delegate: watcher)
            guard let code = (resp as? HTTPURLResponse)?.statusCode else { throw DeckError(.network) }
            if (200..<300).contains(code) { progress(1); return }
            throw DeckError(code == 400 || code == 403 || code == 413 ? .tooLarge(maxMB: DeckCapabilities().maxMB) : .server)
        } catch let e as DeckError { throw e }
        catch is CancellationError { throw CancellationError() }
        catch let e as URLError where e.code == .cancelled { throw CancellationError() }
        catch { throw DeckError(.network) }
    }

    static func writeBody(to url: URL, fields: [String: String], file: URL, mimeType: String, boundary: String) throws {
        FileManager.default.createFile(atPath: url.path, contents: nil, attributes: [.protectionKey: FileProtectionType.complete])
        let out = try FileHandle(forWritingTo: url)
        defer { try? out.close() }
        for (name, value) in fields.sorted(by: { $0.key < $1.key }) {
            try out.write(contentsOf: Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        // the file name inside the form is generic: the real name is never sent anywhere
        try out.write(contentsOf: Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"deck\"\r\nContent-Type: \(mimeType)\r\n\r\n".utf8))
        let input = try FileHandle(forReadingFrom: file)
        defer { try? input.close() }
        while let chunk = try input.read(upToCount: 1 << 20), !chunk.isEmpty { try out.write(contentsOf: chunk) }
        try out.write(contentsOf: Data("\r\n--\(boundary)--\r\n".utf8))
    }

    private final class ProgressWatcher: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
        let report: @Sendable (Double) -> Void
        init(_ report: @escaping @Sendable (Double) -> Void) { self.report = report }
        func urlSession(_ session: URLSession, task: URLSessionTask, didSendBodyData bytesSent: Int64, totalBytesSent: Int64, totalBytesExpectedToSend: Int64) {
            guard totalBytesExpectedToSend > 0 else { return }
            report(min(1, Double(totalBytesSent) / Double(totalBytesExpectedToSend)))
        }
    }
}

// MARK: the temporary copy

/// The one place a picked deck is copied to while it is uploaded. The copy gets a random name (the person's file name is never written to disk by the app),
/// is excluded from backups and protected, and is deleted as soon as the upload finishes, on cancel, on sign-out and on account deletion.
public struct DeckTempStore: Sendable {
    public let directory: URL
    public static var defaultDirectory: URL { FileManager.default.temporaryDirectory.appendingPathComponent("VideoMKDeck", isDirectory: true) }
    public init(directory: URL = DeckTempStore.defaultDirectory) { self.directory = directory }

    public struct Imported: Sendable, Equatable { public let url: URL; public let name: String; public let bytes: Int; public let format: String }

    /// Reads the size and name from the picked (security-scoped) URL, checks them, and only then copies. Throws `DeckError` for a file the app will not upload.
    /// The scope is opened here and closed here, whatever happens.
    public func importFile(from source: URL, caps: DeckCapabilities) throws -> Imported {
        let scoped = source.startAccessingSecurityScopedResource()
        defer { if scoped { source.stopAccessingSecurityScopedResource() } }
        let name = DeckFileCheck.displayName(source.lastPathComponent)
        let size = (try? source.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0
        let format: String
        switch DeckFileCheck.check(fileName: name, bytes: size, caps: caps) {
        case .ok(let f): format = f
        case .problem(let p): throw DeckError(p)
        }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.protectionKey: FileProtectionType.complete])
        var dest = directory.appendingPathComponent("\(UUID().uuidString).\(format)")
        var copyError: Error?
        var coordError: NSError?
        // the coordinator makes iCloud Drive download the file first, and waits for it
        NSFileCoordinator().coordinate(readingItemAt: source, options: [.withoutChanges], error: &coordError) { readable in
            do { try FileManager.default.copyItem(at: readable, to: dest) } catch { copyError = error }
        }
        if coordError != nil || copyError != nil { try? FileManager.default.removeItem(at: dest); throw DeckError(.corrupt) }
        var values = URLResourceValues(); values.isExcludedFromBackup = true
        try? dest.setResourceValues(values)
        let copied = (try? dest.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? size
        return Imported(url: dest, name: name, bytes: copied, format: format)
    }

    public func remove(_ url: URL?) { if let url { try? FileManager.default.removeItem(at: url) } }
    /// Everything this app ever copied here.
    public func removeAll() { try? FileManager.default.removeItem(at: directory) }
    public var isEmpty: Bool { ((try? FileManager.default.contentsOfDirectory(atPath: directory.path)) ?? []).isEmpty }
}

// MARK: the journey

/// How long the app waits: every 2 seconds at first (a deck takes 5 to 30 seconds), slower after, and it stops waiting after `giveUp` seconds
/// (the server reports a deck stuck for 10 minutes as failed by itself; the person can check again).
public struct DeckTiming: Sendable {
    public var intervals: [(until: Double, every: Double)] = [(30, 2), (90, 4), (.infinity, 6)]
    public var giveUp: Double = 180
    public var maxQuietFailures = 3
    public var sleep: @Sendable (Double) async throws -> Void = { try await Task.sleep(for: .seconds($0)) }
    public init() {}
    public func interval(after elapsed: Double) -> Double { intervals.first { elapsed < $0.until }?.every ?? 6 }
}

/// Attach a presentation: pick, upload with progress, process, poll, ready (or a plain problem). One deck at a time.
@MainActor @Observable
public final class DeckJourney {
    public enum State: Equatable, Sendable {
        case idle
        case uploading(Double)
        case processing
        case ready(DeckReady)
        case failed(DeckProblem)
    }

    public private(set) var state: State = .idle
    /// For the ready card ("Q3 review.pptx"). Shown on screen only: never logged, never stored.
    public private(set) var fileName: String?
    public private(set) var deckID: String?
    public private(set) var caps = DeckCapabilities()

    private let api: (any DeckServing)?
    private let uploader: any DeckUploading
    private let store: DeckTempStore
    private let timing: DeckTiming
    private var local: DeckTempStore.Imported?
    private var task: Task<Void, Never>?
    private var generation = 0

    public init(api: (any DeckServing)?, uploader: any DeckUploading = DeckS3Uploader(), store: DeckTempStore = DeckTempStore(), timing: DeckTiming = DeckTiming()) {
        self.api = api; self.uploader = uploader; self.store = store; self.timing = timing
    }

    public var isActive: Bool { state != .idle }
    public var isWorking: Bool { switch state { case .uploading, .processing: true; default: false } }
    public var ready: DeckReady? { if case .ready(let r) = state { r } else { nil } }
    public var problem: DeckProblem? { if case .failed(let p) = state { p } else { nil } }
    /// The file is still on the phone (only while it is being uploaded or after the upload failed).
    public var hasLocalFile: Bool { local != nil }

    /// Starts the whole journey for a file the person picked in the Files app. Any earlier deck is dropped first.
    public func pick(_ source: URL, caps: DeckCapabilities) {
        discard()
        self.caps = caps
        fileName = DeckFileCheck.displayName(source.lastPathComponent)
        state = .uploading(0)
        generation += 1
        let gen = generation
        let store = self.store
        task = Task { [weak self] in
            let imported: DeckTempStore.Imported
            do { imported = try await Task.detached { try store.importFile(from: source, caps: caps) }.value }
            catch let e as DeckError { self?.fail(e.problem, gen); return }
            catch { self?.fail(.corrupt, gen); return }
            guard let self, gen == self.generation, !Task.isCancelled else { store.remove(imported.url); return }
            self.local = imported
            await self.run(imported, gen)
        }
    }

    /// The file was refused before any copy (for a test or a debug fixture that has no real file).
    public func reject(name: String, problem: DeckProblem) { discard(); fileName = DeckFileCheck.displayName(name); state = .failed(problem) }

    /// The primary button of a problem card.
    public func perform(_ action: DeckAction) {
        switch action {
        case .retry: if let local { generation += 1; let gen = generation; task = Task { [weak self] in await self?.run(local, gen) } }
        case .checkAgain: if deckID != nil { resumePolling() }
        case .pickAnother, .chooseAgain: break          // the screen opens the picker; picking starts afresh
        }
    }

    /// Cancel an upload, drop a ready deck, or dismiss a problem: back to nothing, and nothing stays on the phone.
    public func discard() {
        generation += 1
        task?.cancel(); task = nil
        store.remove(local?.url); local = nil
        state = .idle; fileName = nil; deckID = nil
    }

    /// The video was accepted: the server deletes the deck's files; the phone forgets it.
    public func consume() { discard() }

    /// Sign-out and account deletion: everything, including copies left by an earlier launch.
    public func wipe() { discard(); store.removeAll() }

    // MARK: steps

    private func run(_ file: DeckTempStore.Imported, _ gen: Int) async {
        guard let api else { fail(.server, gen); return }
        do {
            state = .uploading(0)
            let slot = try await api.requestSlot(format: file.format, size: file.bytes)
            guard gen == generation else { return }
            deckID = slot.id
            try await uploader.upload(file: file.url, to: slot) { [weak self] f in Task { @MainActor in self?.progress(f, gen) } }
            guard gen == generation else { return }
            store.remove(file.url); local = nil                  // the deck never stays on the phone once it is on the server
            state = .processing
            try await api.process(deckID: slot.id)
            try await poll(slot.id, gen)
        } catch is CancellationError {
        } catch let e as DeckError { fail(e.problem, gen)
        } catch { fail(.network, gen) }
    }

    private func progress(_ f: Double, _ gen: Int) { if gen == generation, case .uploading = state { state = .uploading(f) } }

    private func resumePolling() {
        guard let id = deckID else { return }
        generation += 1; let gen = generation
        state = .processing
        task = Task { [weak self] in
            do { try await self?.poll(id, gen) }
            catch is CancellationError {}
            catch let e as DeckError { self?.fail(e.problem, gen) }
            catch { self?.fail(.network, gen) }
        }
    }

    private func poll(_ id: String, _ gen: Int) async throws {
        guard let api else { throw DeckError(.server) }
        var elapsed = 0.0, quiet = 0
        while gen == generation {
            do {
                switch try await api.status(deckID: id) {
                case .ready(let r):
                    guard gen == generation else { return }
                    state = .ready(r); return
                case .failed(let code, let message):
                    fail(.from(code: code, message: message, caps: caps), gen); return
                case .uploading, .processing: quiet = 0
                }
            } catch let e as DeckError where e.problem.isTransient {
                quiet += 1
                if quiet >= timing.maxQuietFailures { throw e }
            }
            let wait = timing.interval(after: elapsed)
            try await timing.sleep(wait); elapsed += wait
            if elapsed >= timing.giveUp { throw DeckError(.stillWorking) }
        }
    }

    private func fail(_ p: DeckProblem, _ gen: Int) {
        guard gen == generation else { return }
        if !p.isTransient { store.remove(local?.url); local = nil }       // a transient failure during the upload keeps the file for "Try again"
        state = .failed(p)
    }
}
