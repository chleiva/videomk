import Foundation

/// Any JSON value. Used to read optional, still-moving parts of a server answer without ever failing the answer they arrive in.
public enum AnyJSON: Decodable, Sendable, Equatable {
    case null, bool(Bool), number(Double), string(String), array([AnyJSON]), object([String: AnyJSON])

    public init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let b = try? c.decode(Bool.self) { self = .bool(b) }
        else if let n = try? c.decode(Double.self) { self = .number(n) }
        else if let s = try? c.decode(String.self) { self = .string(s) }
        else if let a = try? c.decode([AnyJSON].self) { self = .array(a) }
        else if let o = try? c.decode([String: AnyJSON].self) { self = .object(o) }
        else { self = .null }
    }

    /// A whole number of zero or more, from a number or from digits in a string. Anything else is nil.
    var count: Int? {
        switch self {
        case .number(let n) where n.isFinite && n >= 0 && n < 100_000: Int(n.rounded(.down))
        case .string(let s): Double(s.trimmingCharacters(in: .whitespaces)).flatMap { $0.isFinite && $0 >= 0 && $0 < 100_000 ? Int($0.rounded(.down)) : nil }
        default: nil
        }
    }
    var flag: Bool? {
        switch self {
        case .bool(let b): b
        case .number(let n): n != 0
        case .string(let s): ["true", "yes", "1", "done"].contains(s.lowercased()) ? true : ["false", "no", "0", ""].contains(s.lowercased()) ? false : nil
        default: nil
        }
    }
    /// One line of words: trimmed, line breaks folded to spaces, nil when empty.
    var line: String? {
        guard case .string(let s) = self else { return nil }
        let t = s.split(whereSeparator: \.isNewline).joined(separator: " ").trimmingCharacters(in: .whitespaces)
        return t.isEmpty ? nil : String(t.prefix(MakingInfo.maxLine))
    }
}

/// What the server says about a video while it is being made (`"making"` in the status and list answers): how many scenes, how many are done,
/// one plain line about what is happening now, the sentence being narrated, and a small picture per scene. Every field is optional and is read
/// leniently: a missing, null or malformed part is simply absent, and the screen falls back (tiles without pictures, or a calm indeterminate state).
public struct MakingInfo: Sendable, Equatable {
    public struct Scene: Sendable, Equatable, Identifiable {
        public let index: Int          // 1-based
        public let thumbURL: URL?
        public let done: Bool
        public var id: Int { index }
        public init(index: Int, thumbURL: URL? = nil, done: Bool = false) { self.index = index; self.thumbURL = thumbURL; self.done = done }
    }

    public static let maxScenes = 60
    public static let maxLine = 240

    public let sceneTotal: Int?
    public let sceneDone: Int?
    public let liveLine: String?
    public let narrationLine: String?
    public let scenes: [Scene]

    public init(sceneTotal: Int? = nil, sceneDone: Int? = nil, liveLine: String? = nil, narrationLine: String? = nil, scenes: [Scene] = []) {
        self.sceneTotal = sceneTotal; self.sceneDone = sceneDone; self.liveLine = liveLine; self.narrationLine = narrationLine; self.scenes = scenes
    }

    /// nil when there is nothing usable in it (not an object, or an object with none of the fields).
    public init?(json: AnyJSON?) {
        guard case .object(let o)? = json else { return nil }
        var scenes: [Scene] = []
        if case .array(let raw)? = o["scenes"] {
            var seen = Set<Int>()
            for (position, item) in raw.enumerated() {
                guard case .object(let s) = item else { continue }
                let index = s["index"]?.count.flatMap { $0 >= 1 ? $0 : nil } ?? position + 1
                guard index <= Self.maxScenes, seen.insert(index).inserted else { continue }
                var url: URL?
                if case .string(let u)? = s["thumb_url"], let parsed = URL(string: u.trimmingCharacters(in: .whitespaces)), ["https", "http", "fake"].contains(parsed.scheme?.lowercased() ?? "") { url = parsed }
                scenes.append(Scene(index: index, thumbURL: url, done: s["done"]?.flag ?? false))
            }
            scenes.sort { $0.index < $1.index }
        }
        var total = o["scene_total"]?.count.flatMap { $0 >= 1 ? min($0, Self.maxScenes) : nil }
        if total == nil, let last = scenes.last { total = last.index }                      // the list itself says how many
        if let t = total, let last = scenes.last, last.index > t { total = last.index }     // never fewer tiles than scenes listed
        var done = o["scene_done"]?.count
        if done == nil, !scenes.isEmpty { done = scenes.filter(\.done).count }
        if let t = total, let d = done { done = min(d, t) }
        if total == nil { done = nil }                                                       // "4 done" of an unknown number says nothing
        let live = o["live_line"]?.line, narration = o["narration_line"]?.line
        if total == nil && live == nil && narration == nil && scenes.isEmpty { return nil }
        self.init(sceneTotal: total, sceneDone: done, liveLine: live, narrationLine: narration, scenes: scenes)
    }

    /// From a status answer's body: `{"status": "...", "making": {...}}`. Anything else is nil.
    public static func fromStatusBody(_ data: Data) -> MakingInfo? {
        guard case .object(let o)? = try? JSONDecoder().decode(AnyJSON.self, from: data) else { return nil }
        return MakingInfo(json: o["making"])
    }

    // MARK: what the film strip shows

    public enum TileState: Sendable, Equatable { case done, current, upcoming }
    public struct Tile: Sendable, Equatable, Identifiable {
        public let index: Int
        public let state: TileState
        public let thumbURL: URL?
        public var id: Int { index }
    }

    /// One tile per scene: done ones first (with their picture when the server sent one), the one being made now, then the rest. Empty when the number of scenes is unknown.
    public var tiles: [Tile] {
        guard let total = sceneTotal, total > 0 else { return [] }
        let byIndex = Dictionary(scenes.map { ($0.index, $0) }, uniquingKeysWith: { a, _ in a })
        let doneCount = sceneDone ?? 0
        func isDone(_ i: Int) -> Bool { i <= doneCount || byIndex[i]?.done == true }
        let current = (1...total).first { !isDone($0) }
        return (1...total).map { i in Tile(index: i, state: isDone(i) ? .done : i == current ? .current : .upcoming, thumbURL: byIndex[i]?.thumbURL) }
    }

    /// The scene being made now (1-based); nil when every scene is done or the count is unknown.
    public var currentScene: Int? { tiles.first { $0.state == .current }?.index }
    /// How many scenes are finished (never more than the total).
    public var doneScenes: Int { tiles.filter { $0.state == .done }.count }
    public var hasThumbnails: Bool { scenes.contains { $0.thumbURL != nil } }
    /// The picture for the large view: the scene being made if it already has one, else the last finished scene that has one.
    public var heroThumb: URL? {
        let t = tiles
        if let c = t.first(where: { $0.state == .current }), let u = c.thumbURL { return u }
        return t.last { $0.state == .done && $0.thumbURL != nil }?.thumbURL
    }

    /// At most `count` tiles around the scene being made (the list card has room for seven): the window slides so the current tile stays in view.
    public func window(_ count: Int) -> [Tile] {
        let all = tiles
        guard count > 0, all.count > count else { return all }
        let focus = (currentScene ?? all.count) - 1
        let start = max(0, min(all.count - count, focus - (count - 3)))
        return Array(all[start..<start + count])
    }

    /// Same to the eye: picture links count by where they live, never by their signature (the server signs them anew on every answer).
    public func visiblyEqual(_ o: MakingInfo) -> Bool {
        sceneTotal == o.sceneTotal && sceneDone == o.sceneDone && liveLine == o.liveLine && narrationLine == o.narrationLine && scenes.count == o.scenes.count
            && zip(scenes, o.scenes).allSatisfy { $0.index == $1.index && $0.done == $1.done && ImageKey.stable($0.thumbURL) == ImageKey.stable($1.thumbURL) }
    }
}
