import Foundation

// MARK: - what the server sends for the editor (GET .../plan)

public struct PhotoCandidate: Sendable, Equatable, Identifiable, Decodable {
    public let provider: String
    public let candidateID: String
    public let thumbURL: URL?
    public let creator: String
    public let license: String
    public let alt: String
    public let landingURL: URL?
    public var id: String { key }
    /// The id the server's `pick_image` operation expects.
    public var key: String { "\(provider):\(candidateID)" }

    enum CodingKeys: String, CodingKey {
        case provider, candidateID = "id", thumbURL = "thumb_url", creator, license, alt, landingURL = "landing_url"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        provider = try c.decode(String.self, forKey: .provider)
        candidateID = try c.decode(String.self, forKey: .candidateID)
        thumbURL = (try? c.decode(String.self, forKey: .thumbURL)).flatMap(URL.init(string:))
        creator = (try? c.decode(String.self, forKey: .creator)) ?? "Unknown"
        license = (try? c.decode(String.self, forKey: .license)) ?? ""
        alt = (try? c.decode(String.self, forKey: .alt)) ?? ""
        landingURL = (try? c.decode(String.self, forKey: .landingURL)).flatMap(URL.init(string:))
    }

    public init(provider: String, id: String, creator: String = "Unknown", license: String = "") {
        self.provider = provider; candidateID = id; thumbURL = nil; self.creator = creator; self.license = license; alt = ""; landingURL = nil
    }
}

public struct BeatPhoto: Sendable, Equatable, Decodable {
    public let url: URL?
    public let credit: String?
    public let chosen: String?
    public let noPhoto: Bool
    enum CodingKeys: String, CodingKey { case url, credit, chosen, noPhoto = "no_photo" }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        url = (try? c.decode(String.self, forKey: .url)).flatMap(URL.init(string:))
        credit = try? c.decode(String.self, forKey: .credit)
        chosen = try? c.decode(String.self, forKey: .chosen)
        noPhoto = (try? c.decode(Bool.self, forKey: .noPhoto)) ?? false
    }
    public init(url: URL? = nil, credit: String? = nil, chosen: String? = nil, noPhoto: Bool = false) {
        self.url = url; self.credit = credit; self.chosen = chosen; self.noPhoto = noPhoto
    }
}

public enum SceneKind: String, Sendable, CaseIterable {
    case title, bullets, diagram, chart, timeline, stat, quote, image, clip
    public var symbol: String {
        switch self {
        case .title: "textformat"
        case .bullets: "list.bullet"
        case .diagram: "point.3.connected.trianglepath.dotted"
        case .chart: "chart.bar"
        case .timeline: "calendar.day.timeline.left"
        case .stat: "number"
        case .quote: "quote.opening"
        case .image: "photo"
        case .clip: "film"
        }
    }
    public var label: String {
        switch self {
        case .title: "Title"
        case .bullets: "List"
        case .diagram: "Diagram"
        case .chart: "Chart"
        case .timeline: "Timeline"
        case .stat: "Big number"
        case .quote: "Quote"
        case .image: "Photo"
        case .clip: "Video clip"
        }
    }
}

public struct EditorBeat: Sendable, Equatable, Identifiable, Decodable {
    public let id: String
    public var narration: String
    public let kind: SceneKind?
    public let summary: String
    public let chapter: String?
    public let duration: Double?
    public let stale: Bool
    public let silent: Bool          // a pause: nothing is spoken, the picture is held for `hold` seconds while the music carries it
    public let hold: Double?
    public let photo: BeatPhoto?
    public let candidates: [PhotoCandidate]

    enum CodingKeys: String, CodingKey { case id, narration, scene, chapter, duration, stale, silent, hold, photo, candidates }
    private struct Scene: Decodable { let type: String; let props: [String: JSONValue]? }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        narration = try c.decode(String.self, forKey: .narration)
        let scene = try? c.decode(Scene.self, forKey: .scene)
        kind = scene.flatMap { SceneKind(rawValue: $0.type) }
        summary = Self.summary(type: scene?.type ?? "", props: scene?.props ?? [:])
        chapter = (try? c.decode(String.self, forKey: .chapter)).flatMap { $0.isEmpty ? nil : $0 }
        duration = try? c.decode(Double.self, forKey: .duration)
        stale = (try? c.decode(Bool.self, forKey: .stale)) ?? false
        silent = (try? c.decode(Bool.self, forKey: .silent)) ?? false
        hold = try? c.decode(Double.self, forKey: .hold)
        photo = try? c.decode(BeatPhoto.self, forKey: .photo)
        candidates = (try? c.decode([PhotoCandidate].self, forKey: .candidates)) ?? []
    }

    public init(id: String, narration: String, kind: SceneKind? = .title, summary: String = "", chapter: String? = nil, duration: Double? = nil,
                stale: Bool = false, silent: Bool = false, hold: Double? = nil, photo: BeatPhoto? = nil, candidates: [PhotoCandidate] = []) {
        self.id = id; self.narration = narration; self.kind = kind; self.summary = summary; self.chapter = chapter; self.duration = duration
        self.stale = stale; self.silent = silent; self.hold = hold; self.photo = photo; self.candidates = candidates
    }

    /// One line describing what the scene shows, for the list.
    static func summary(type: String, props p: [String: JSONValue]) -> String {
        func s(_ k: String) -> String? { p[k]?.string }
        switch type {
        case "title", "diagram", "chart", "timeline": return s("title") ?? ""
        case "bullets": return s("heading") ?? ""
        case "stat": return [s("value"), s("label")].compactMap { $0 }.joined(separator: " ")
        case "quote": return s("text") ?? ""
        case "image": return s("alt") ?? s("image_query") ?? ""
        case "clip": return s("alt") ?? s("clip_query") ?? ""
        default: return ""
        }
    }
}

public struct EditorLimits: Sendable, Equatable {
    public var minWords = 6, maxWords = 70, maxBeats = 90
    public init(minWords: Int = 6, maxWords: Int = 70, maxBeats: Int = 90) { self.minWords = minWords; self.maxWords = maxWords; self.maxBeats = maxBeats }
}

public enum EditState: Sendable, Equatable {
    case ready, rendering, failed
    init(_ raw: String?) { switch raw { case "RENDERING": self = .rendering; case "FAILED": self = .failed; default: self = .ready } }
}

public struct EditorSnapshot: Sendable, Equatable, Decodable {
    public let videoID: String
    public let rev: Int
    public let editState: EditState
    public let editMode: String?
    public let title: String
    public let captions: Bool        // subtitles on the video (the creator's choice)
    public let beats: [EditorBeat]
    public let limits: EditorLimits
    public let finalURL: URL?, finalRev: Int?
    public let previewURL: URL?, previewRev: Int?

    enum CodingKeys: String, CodingKey {
        case videoID = "video_id", rev, editState = "edit_state", editMode = "edit_mode", title, captions, beats, limits, final, preview
    }
    private struct Rendered: Decodable { let url: String?; let rev: Int? }
    private struct Limits: Decodable { let max_beats: Int?; let min_words: Int?; let max_words: Int? }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        videoID = try c.decode(String.self, forKey: .videoID)
        rev = try c.decode(Int.self, forKey: .rev)
        editState = EditState(try? c.decode(String.self, forKey: .editState))
        editMode = try? c.decode(String.self, forKey: .editMode)
        title = (try? c.decode(String.self, forKey: .title)) ?? ""
        captions = (try? c.decode(Bool.self, forKey: .captions)) ?? true
        beats = try c.decode([EditorBeat].self, forKey: .beats)
        let l = try? c.decode(Limits.self, forKey: .limits)
        limits = EditorLimits(minWords: l?.min_words ?? 6, maxWords: l?.max_words ?? 70, maxBeats: l?.max_beats ?? 90)
        let f = try? c.decode(Rendered.self, forKey: .final), p = try? c.decode(Rendered.self, forKey: .preview)
        finalURL = f?.url.flatMap(URL.init(string:)); finalRev = f?.rev
        previewURL = p?.url.flatMap(URL.init(string:)); previewRev = p?.rev
    }
}

// MARK: - operations and the diff that produces them

public enum RenderMode: String, Sendable { case preview, final }

public enum EditOp: Sendable, Equatable {
    case setNarration(id: String, text: String)
    case pickImage(id: String, candidate: String)
    case delete(id: String)
    case move(id: String, to: Int)
    case setTitle(String)
    case setCaptions(Bool)

    var json: [String: Any] {
        switch self {
        case .setNarration(let id, let text): ["op": "set_narration", "id": id, "text": text]
        case .pickImage(let id, let c): ["op": "pick_image", "id": id, "candidate": c]
        case .delete(let id): ["op": "delete", "id": id]
        case .move(let id, let to): ["op": "move", "id": id, "to": to]
        case .setTitle(let t): ["op": "set_meta", "title": t]
        case .setCaptions(let on): ["op": "set_meta", "captions": on]
        }
    }
}

public enum EditorDiff {
    /// The operations that turn `server` into `local`. Order matters: content first, then deletions, then moves by target index.
    public static func ops(serverTitle: String, server: [EditorBeat], localTitle: String, local: [EditorBeat], picks: [String: String] = [:],
                           serverCaptions: Bool = true, localCaptions: Bool = true) -> [EditOp] {
        var ops: [EditOp] = []
        let serverByID = Dictionary(uniqueKeysWithValues: server.map { ($0.id, $0) })
        let localIDs = Set(local.map(\.id))

        for b in local {
            if let s = serverByID[b.id], Self.normalize(s.narration) != Self.normalize(b.narration) {
                ops.append(.setNarration(id: b.id, text: Self.normalize(b.narration)))
            }
            if let pick = picks[b.id], serverByID[b.id] != nil { ops.append(.pickImage(id: b.id, candidate: pick)) }
        }
        for s in server where !localIDs.contains(s.id) { ops.append(.delete(id: s.id)) }

        var current = server.map(\.id).filter(localIDs.contains)
        let target = local.map(\.id).filter { serverByID[$0] != nil }
        for (i, id) in target.enumerated() where current[i] != id {
            current.removeAll { $0 == id }
            current.insert(id, at: i)
            ops.append(.move(id: id, to: i))
        }
        let t = Self.normalize(localTitle)
        if !t.isEmpty, t != Self.normalize(serverTitle) { ops.append(.setTitle(t)) }
        if localCaptions != serverCaptions { ops.append(.setCaptions(localCaptions)) }
        return ops
    }

    public static func normalize(_ s: String) -> String { s.split(whereSeparator: \.isWhitespace).joined(separator: " ") }

    /// Mirrors the server's narration limits so errors show beside the field before anything is sent.
    public static func narrationError(_ text: String, limits: EditorLimits, silent: Bool = false) -> String? {
        let n = normalize(text).split(separator: " ").count
        if silent && n == 0 { return nil }          // a pause has no narration; typing words into it gives it a voice, and then the usual limits apply
        if n < limits.minWords { return "Needs at least \(limits.minWords) words (now \(n))." }
        if n > limits.maxWords { return "Limited to \(limits.maxWords) words per scene (now \(n)). Split it into two scenes." }
        return nil
    }

    public static func wordCount(_ text: String) -> Int { normalize(text).split(separator: " ").count }
    /// Spoken time at about 2.5 words per second.
    public static func spokenSeconds(_ text: String) -> Double { Double(wordCount(text)) / 2.5 }
}

// MARK: - tiny JSON value for scene props

public enum JSONValue: Decodable, Sendable, Equatable {
    case string(String), number(Double), bool(Bool), array([JSONValue]), object([String: JSONValue]), null

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Double.self) { self = .number(v) }
        else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else if let v = try? c.decode([String: JSONValue].self) { self = .object(v) }
        else { self = .null }
    }

    public var string: String? { if case .string(let s) = self { s } else { nil } }
}
