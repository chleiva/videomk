import Foundation

// The chosen, enforced look of a video (docs/CREATE_API.md, "Video look (chosen and enforced)"): what the server offers (`capabilities.looks.look` and
// `.cast`), what the person picked (`look`, `cast`, `extras`), the rules of the picker, and what the answers say was applied. Everything is read
// leniently: a missing or malformed part is simply absent, and without `looks.look` the app keeps the behaviour it had before the picker existed.

/// `capabilities.looks`: the tiles of the picker and the cast. Never hard-coded: labels, notes and pictures are the server's.
public struct LookCapabilities: Sendable, Equatable {
    public struct Extra: Sendable, Equatable, Identifiable {
        public var id: String, label: String
        public var note: String?
        public var available: Bool
        public init(id: String, label: String, note: String? = nil, available: Bool = true) { self.id = id; self.label = label; self.note = note; self.available = available }
    }

    public struct Option: Sendable, Equatable, Identifiable {
        public var id: String, label: String
        public var note: String?
        public var preview: String?            // a JPEG data URI (320x180)
        public var available: Bool             // this stage has the look; false: the tile is hidden
        public var allowed: Bool               // this account's plan may use it; false: shown, with the plan's name, not selectable
        public var requiresPlan: String?
        public var withPhotos: Bool, withDeck: Bool
        public var minSeconds: Double
        public var aspects: [String], bestAspects: [String]
        public var cast: Bool                  // true: the cast picker shows under the tiles
        public var extras: [Extra]
        public init(id: String, label: String, note: String? = nil, preview: String? = nil, available: Bool = true, allowed: Bool = true, requiresPlan: String? = nil, withPhotos: Bool = true, withDeck: Bool = true,
                    minSeconds: Double = 0, aspects: [String] = [], bestAspects: [String] = [], cast: Bool = false, extras: [Extra] = []) {
            self.id = id; self.label = label; self.note = note; self.preview = preview; self.available = available; self.allowed = allowed; self.requiresPlan = requiresPlan; self.withPhotos = withPhotos
            self.withDeck = withDeck; self.minSeconds = minSeconds; self.aspects = aspects; self.bestAspects = bestAspects; self.cast = cast; self.extras = extras
        }
        public var isAuto: Bool { id == LookChoice.auto }
    }

    public struct Member: Sendable, Equatable, Identifiable {
        public var id: String, name: String
        public var role: String?
        public var kind: String                // "person" | "animal"
        public var topic: String?
        public var thumbnail: String?          // a PNG data URI (112 px)
        public init(id: String, name: String, role: String? = nil, kind: String = "person", topic: String? = nil, thumbnail: String? = nil) { self.id = id; self.name = name; self.role = role; self.kind = kind; self.topic = topic; self.thumbnail = thumbnail }
    }

    public struct Cast: Sendable, Equatable {
        public var min: Int, max: Int
        public var available: Bool
        public var autoLabel: String?, autoNote: String?
        public var conversationFrom: Int
        public var conversationMinSeconds: Double
        public var conversationNote: String?
        public var members: [Member]
        public init(min: Int = 1, max: Int = 3, available: Bool = true, autoLabel: String? = nil, autoNote: String? = nil, conversationFrom: Int = 2, conversationMinSeconds: Double = 0, conversationNote: String? = nil, members: [Member] = []) {
            self.min = min; self.max = max; self.available = available; self.autoLabel = autoLabel; self.autoNote = autoNote; self.conversationFrom = conversationFrom
            self.conversationMinSeconds = conversationMinSeconds; self.conversationNote = conversationNote; self.members = members
        }
        public func member(_ id: String) -> Member? { members.first { $0.id == id } }
        /// The members in the server's order, people first, then animals, then anything else: one group per kind.
        public var groups: [(kind: String, members: [Member])] {
            var order: [String] = []
            for m in members where !order.contains(m.kind) { order.append(m.kind) }
            let rank = ["person": 0, "animal": 1]
            return order.sorted { (rank[$0] ?? 2, order.firstIndex(of: $0)!) < (rank[$1] ?? 2, order.firstIndex(of: $1)!) }.map { k in (k, members.filter { $0.kind == k }) }
        }
    }

    public var options: [Option]
    public var cast: Cast?

    public init(options: [Option], cast: Cast? = nil) { self.options = options; self.cast = cast }

    public func option(_ id: String) -> Option? { options.first { $0.id == id } }

    /// From the `looks` object of capabilities. nil when `looks.look` is absent or lists nothing usable: the app then behaves as before the picker.
    public init?(json: AnyJSON?) {
        guard case .object(let looks)? = json, case .object(let look)? = looks["look"], case .array(let raw)? = look["options"] else { return nil }
        var seen = Set<String>()
        let options: [Option] = raw.compactMap { item in
            guard case .object(let o) = item, let id = o["id"]?.word, seen.insert(id).inserted else { return nil }
            var extras: [Extra] = []
            if case .array(let ex)? = o["extras"] {
                extras = ex.compactMap { e in
                    guard case .object(let x) = e, let xid = x["id"]?.word else { return nil }
                    return Extra(id: xid, label: x["label"]?.line ?? xid, note: x["note"]?.line, available: x["available"]?.flag ?? true)
                }
            }
            return Option(id: id, label: o["label"]?.line ?? id, note: o["note"]?.line, preview: o["preview"]?.dataURI, available: o["available"]?.flag ?? true, allowed: o["allowed"]?.flag ?? true,
                          requiresPlan: o["requires_plan"]?.line, withPhotos: o["with_photos"]?.flag ?? true, withDeck: o["with_deck"]?.flag ?? true, minSeconds: o["min_seconds"]?.seconds ?? 0,
                          aspects: o["aspects"]?.words ?? [], bestAspects: o["best_aspects"]?.words ?? [], cast: o["cast"]?.flag ?? false, extras: extras)
        }
        guard !options.isEmpty else { return nil }
        var cast: Cast?
        if case .object(let c)? = looks["cast"] {
            var ids = Set<String>()
            var members: [Member] = []
            if case .array(let ms)? = c["members"] {
                members = ms.compactMap { m in
                    guard case .object(let x) = m, let id = x["id"]?.word, id != LookChoice.auto, ids.insert(id).inserted else { return nil }
                    return Member(id: id, name: x["name"]?.line ?? id, role: x["role"]?.line, kind: x["kind"]?.word ?? "person", topic: x["topic"]?.line, thumbnail: x["thumbnail"]?.dataURI)
                }
            }
            var auto: [String: AnyJSON] = [:], talk: [String: AnyJSON] = [:]
            if case .object(let a)? = c["auto"] { auto = a }
            if case .object(let t)? = c["conversation"] { talk = t }
            let top = Swift.max(1, c["max"]?.count ?? 3)
            cast = Cast(min: Swift.max(1, Swift.min(c["min"]?.count ?? 1, top)), max: top, available: c["available"]?.flag ?? true, autoLabel: auto["label"]?.line, autoNote: auto["note"]?.line,
                        conversationFrom: Swift.max(2, talk["from"]?.count ?? 2), conversationMinSeconds: talk["min_seconds"]?.seconds ?? 0, conversationNote: talk["note"]?.line, members: members)
        }
        self.init(options: options, cast: cast)
    }
}

extension AnyJSON {
    /// A short identifier ("cartoon", "16:9"): a non-empty string without spaces.
    var word: String? {
        guard case .string(let s) = self else { return nil }
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty || t.count > 64 || t.contains(" ") ? nil : t
    }
    var words: [String]? { guard case .array(let a) = self else { return nil }; return a.compactMap(\.word) }
    var seconds: Double? { if case .number(let n) = self, n.isFinite, n >= 0 { return n }; if case .string(let s) = self, let n = Double(s), n.isFinite, n >= 0 { return n }; return nil }
    /// A picture sent inline; anything that is not an image data URI is no picture.
    var dataURI: String? { guard case .string(let s) = self, s.hasPrefix("data:image/"), s.contains(";base64,") else { return nil }; return s }
}

public enum DataURI {
    /// The bytes of `data:image/...;base64,...`; nil for anything else.
    public static func data(_ uri: String?) -> Data? {
        guard let uri, uri.hasPrefix("data:"), let comma = uri.firstIndex(of: ",") else { return nil }
        return Data(base64Encoded: String(uri[uri.index(after: comma)...]), options: .ignoreUnknownCharacters)
    }
}

/// What the person picked. `auto` with no cast and no extras sends nothing at all, so a server from before the contract is unaffected.
public struct LookChoice: Sendable, Equatable, Codable {
    public static let auto = "auto"
    public var look: String
    public var cast: [String]       // empty = "auto"
    public var extras: [String]
    public init(look: String = LookChoice.auto, cast: [String] = [], extras: [String] = []) { self.look = look; self.cast = cast; self.extras = extras }
    public var isAuto: Bool { look == Self.auto && cast.isEmpty && extras.isEmpty }

    /// The request fields, exactly as the contract writes them (the body of `generate`, and `options` of `brief`).
    public var requestLook: String? { look == Self.auto ? nil : look }
    public var requestCast: [String]? { look == Self.auto || cast.isEmpty ? nil : cast }
    public var requestExtras: [String]? { look == Self.auto || extras.isEmpty ? nil : extras }
    public var fields: [String: Any] {
        var f: [String: Any] = [:]
        if let l = requestLook { f["look"] = l }
        if let c = requestCast { f["cast"] = c }
        if let e = requestExtras { f["extras"] = e }
        return f
    }
}

/// The rules of the picker. Pure, so every one of them is unit-tested.
public enum LookRules {
    public struct Attached: Sendable, Equatable {
        public var photos: Bool, deck: Bool
        public init(photos: Bool = false, deck: Bool = false) { self.photos = photos; self.deck = deck }
        public static let nothing = Attached()
        public var any: Bool { photos || deck }
    }

    public struct Tile: Sendable, Equatable, Identifiable {
        public let option: LookCapabilities.Option
        public let locked: Bool
        public var id: String { option.id }
    }

    public enum Reset: Sendable, Equatable { case photos, deck, plan, gone }

    /// A look made from these attachments? (The person's own photos or slides are the pictures of the video: the drawn looks are not offered then.)
    static func fits(_ o: LookCapabilities.Option, _ a: Attached) -> Bool { (!a.photos || o.withPhotos) && (!a.deck || o.withDeck) }

    /// At most four tiles in the server's order. Hidden: a look this stage does not have, and a look that is not made from what is attached.
    /// A look the plan does not include is shown, locked.
    public static func tiles(_ caps: LookCapabilities, attached: Attached = .nothing) -> [Tile] {
        Array(caps.options.filter { $0.available && fits($0, attached) }.prefix(4)).map { Tile(option: $0, locked: !$0.allowed) }
    }

    /// The looks that were left out because of the attachments (their labels, for the one line that says so).
    public static func hidden(_ caps: LookCapabilities, attached: Attached) -> [LookCapabilities.Option] { caps.options.filter { $0.available && !fits($0, attached) } }

    /// Keeps a choice inside what can be made now. Returns the reason when the look itself had to go back to Auto.
    public static func normalized(_ choice: LookChoice, caps: LookCapabilities?, attached: Attached = .nothing) -> (choice: LookChoice, reset: Reset?) {
        guard let caps else { return (LookChoice(), nil) }                 // an older server: nothing is sent
        guard choice.look != LookChoice.auto else { return (LookChoice(), nil) }
        guard let o = caps.option(choice.look), o.available else { return (LookChoice(), .gone) }
        if attached.photos, !o.withPhotos { return (LookChoice(), .photos) }
        if attached.deck, !o.withDeck { return (LookChoice(), .deck) }
        if !o.allowed { return (LookChoice(), .plan) }
        var c = choice
        if o.cast, let cast = caps.cast, cast.available {
            var seen = Set<String>()
            c.cast = Array(c.cast.filter { cast.member($0) != nil && seen.insert($0).inserted }.prefix(cast.max))
        } else { c.cast = [] }
        let usable = Set(o.extras.filter(\.available).map(\.id))
        c.extras = c.extras.filter { usable.contains($0) }
        return (c, nil)
    }

    /// A tap on a tile. Locked and hidden tiles change nothing. Choosing another look drops the cast and the extras of the one before.
    public static func select(_ id: String, in choice: LookChoice, caps: LookCapabilities, attached: Attached = .nothing) -> LookChoice {
        guard tiles(caps, attached: attached).contains(where: { $0.id == id && !$0.locked }) else { return choice }
        return id == choice.look ? choice : LookChoice(look: id)
    }

    public enum CastTap: Sendable, Equatable { case added, removed, full }

    /// A tap on a face: ticks it, or unticks it; a fourth is refused (`full`).
    public static func toggle(_ member: String, in choice: inout LookChoice, caps: LookCapabilities) -> CastTap {
        guard let cast = caps.cast, cast.member(member) != nil else { return .full }
        if let i = choice.cast.firstIndex(of: member) { choice.cast.remove(at: i); return .removed }
        guard choice.cast.count < cast.max else { return .full }
        choice.cast.append(member); return .added
    }

    public static func setExtra(_ id: String, on: Bool, in choice: inout LookChoice) {
        choice.extras.removeAll { $0 == id }
        if on { choice.extras.append(id) }
    }

    /// Two or three ticked: they talk to each other.
    public static func isConversation(_ choice: LookChoice, caps: LookCapabilities?) -> Bool {
        guard let cast = caps?.cast else { return false }
        return choice.cast.count >= cast.conversationFrom
    }

    /// The shortest video this choice works in, in seconds.
    public static func minSeconds(_ choice: LookChoice, caps: LookCapabilities?) -> Double {
        guard let caps, let o = caps.option(choice.look) else { return 0 }
        return max(o.minSeconds, isConversation(choice, caps: caps) ? (caps.cast?.conversationMinSeconds ?? 0) : 0)
    }

    public struct LengthNudge: Sendable, Equatable {
        public let minutes: Double          // the length to use: the shortest preset the choice works in
        public let needSeconds: Double
        public let conversation: Bool
    }

    /// The chosen length is shorter than the choice needs: the preset to move to. nil when the length is fine or no preset is long enough.
    public static func lengthNudge(_ choice: LookChoice, caps: LookCapabilities?, minutes: Double, presets: [Double]) -> LengthNudge? {
        let need = minSeconds(choice, caps: caps)
        guard need > 0, minutes * 60 + 1e-6 < need, let fix = presets.sorted().first(where: { $0 * 60 + 1e-6 >= need }) else { return nil }
        return LengthNudge(minutes: fix, needSeconds: need, conversation: isConversation(choice, caps: caps) && (caps?.option(choice.look)?.minSeconds ?? 0) < need)
    }

    /// The chosen shape is not one the look is at its best in: the shapes that are (their ids), for a quiet hint. Empty: nothing to say.
    public static func betterAspects(_ choice: LookChoice, caps: LookCapabilities?, aspect: String) -> [String] {
        guard let o = caps?.option(choice.look), !o.isAuto, !o.bestAspects.isEmpty, !o.bestAspects.contains(aspect) else { return [] }
        return o.bestAspects
    }

    // MARK: words

    /// The names of the ticked characters, in the order they were ticked.
    public static func castNames(_ ids: [String], caps: LookCapabilities?) -> [String] { ids.map { caps?.cast?.member($0)?.name ?? $0 } }

    /// What the pill says: "Auto", "Whiteboard", "Cartoon · Fox + Bruno" (three: "Cartoon · Fox + 2", so no name is ever cut).
    public static func pillLabel(_ choice: LookChoice, caps: LookCapabilities?) -> String {
        guard let caps, let o = caps.option(choice.look) else { return tr("look.auto") }
        if o.isAuto { return tr("look.auto") }
        let names = castNames(choice.cast, caps: caps)
        switch names.count {
        case 0: return o.label
        case 1, 2: return "\(o.label) · \(names.joined(separator: " + "))"
        default: return "\(o.label) · \(names[0]) + \(names.count - 1)"
        }
    }

    /// The same for a screen reader and for Info, in full: "Cartoon, Fox, Bruno and Mika, Hand-drawn board".
    public static func spoken(_ choice: LookChoice, caps: LookCapabilities?) -> String {
        guard let caps, let o = caps.option(choice.look) else { return tr("look.auto") }
        var parts = [o.label]
        let names = castNames(choice.cast, caps: caps)
        if !names.isEmpty { parts.append(Localization.shared.list(names)) }
        parts += choice.extras.compactMap { id in o.extras.first { $0.id == id }?.label }
        return parts.joined(separator: ", ")
    }

    /// One line saying why the look went back to Auto ("Look is Auto: Cartoon is not made from your photos.").
    public static func resetLine(_ reason: Reset, was: String) -> String {
        switch reason {
        case .photos: tr("looks.reset_photos", was)
        case .deck: tr("looks.reset_deck", was)
        case .plan, .gone: tr("looks.reset_gone", was)
        }
    }
}

/// What an answer (`brief`, the 202 of `generate`) or the video record says about the look: what was asked, what the video gets, and why.
public struct AppliedLook: Sendable, Equatable {
    public var chosen: String?
    public var applied: String?
    public var cast: [String]           // empty: none, or "auto"
    public var extras: [String]
    public var reason: String?          // not_available | own_photos | deck | too_short
    public var why: String?             // the video record: one sentence on why this look
    public var byAuto: Bool             // the video record: the director chose it

    public init(chosen: String? = nil, applied: String? = nil, cast: [String] = [], extras: [String] = [], reason: String? = nil, why: String? = nil, byAuto: Bool = false) {
        self.chosen = chosen; self.applied = applied; self.cast = cast; self.extras = extras; self.reason = reason; self.why = why; self.byAuto = byAuto
    }

    public init?(json: AnyJSON?) {
        guard case .object(let o)? = json else { return nil }
        let applied = o["applied"]?.word, chosen = o["chosen"]?.word
        guard applied != nil || chosen != nil else { return nil }
        self.init(chosen: chosen, applied: applied, cast: o["cast"]?.words ?? [], extras: o["extras"]?.words ?? [], reason: o["reason"]?.word, why: o["why"]?.line,
                  byAuto: o["by"]?.word == "auto" || (o["by"] == nil && chosen == LookChoice.auto))
    }

    /// "Whiteboard", "Cartoon · Fox + Bruno": the server's own label when the capabilities list the look, else our word for the four known looks.
    public func title(caps: LookCapabilities?) -> String? {
        guard let id = applied ?? chosen, id != LookChoice.auto else { return nil }
        let known = ["real": "looks.name_real", "whiteboard": "looks.name_whiteboard", "cartoon": "looks.name_cartoon", "presenters": "looks.name_cartoon"]
        guard let name = caps?.option(id)?.label ?? known[id].map({ tr($0) }) else { return nil }
        let names = LookRules.castNames(cast, caps: caps)
        return names.isEmpty ? name : "\(name) · \(names.joined(separator: " + "))"
    }
}

/// The 202 of `generate`: the video, and (optional) what look it gets and one sentence when the look had to be adapted.
public struct StartedVideo: Sendable, Equatable {
    public let videoID: String
    public var look: AppliedLook?
    public var note: String?
    public init(videoID: String, look: AppliedLook? = nil, note: String? = nil) { self.videoID = videoID; self.look = look; self.note = note }

    /// nil only when there is no `video_id`: a malformed `look` or `note` never fails the start.
    public static func decode(_ data: Data) -> StartedVideo? {
        guard case .object(let o)? = try? JSONDecoder().decode(AnyJSON.self, from: data), case .string(let id)? = o["video_id"], !id.isEmpty else { return nil }
        return StartedVideo(videoID: id, look: AppliedLook(json: o["look"]), note: o["note"]?.line)
    }
}
