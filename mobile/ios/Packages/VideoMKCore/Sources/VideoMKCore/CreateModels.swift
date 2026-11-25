import Foundation

/// What the apps may offer when creating a video (GET /capabilities, docs/CREATE_API.md). Until the server has it, `fallback` offers 16:9 and 1080p only.
public struct CreateCapabilities: Codable, Sendable, Equatable {
    public struct Aspect: Codable, Sendable, Equatable { public let id: String, label: String; public let ready: Bool, beta: Bool
        public init(id: String, label: String, ready: Bool = true, beta: Bool = false) { self.id = id; self.label = label; self.ready = ready; self.beta = beta }
        public init(from d: Decoder) throws { let c = try d.container(keyedBy: CodingKeys.self); id = try c.decode(String.self, forKey: .id); label = (try? c.decode(String.self, forKey: .label)) ?? id; ready = (try? c.decode(Bool.self, forKey: .ready)) ?? false; beta = (try? c.decode(Bool.self, forKey: .beta)) ?? false } }
    public struct Resolution: Codable, Sendable, Equatable {
        public let id: String, label: String
        public let creditsMultiplier: Int      // the price relative to 1080p: 2 for 4K (1 when an older server does not say)
        public let aspects: [String]           // the shapes it can be made in; empty = every ready shape (older servers)
        public let note: String?               // a line to show when it is selected ("4K costs twice the credits…")
        enum CodingKeys: String, CodingKey { case id, label, creditsMultiplier = "credits_multiplier", aspects, note }
        public init(id: String, label: String? = nil, creditsMultiplier: Int = 1, aspects: [String] = [], note: String? = nil) { self.id = id; self.label = label ?? id; self.creditsMultiplier = max(1, creditsMultiplier); self.aspects = aspects; self.note = note }
        public init(from d: Decoder) throws {
            let c = try d.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id); label = (try? c.decode(String.self, forKey: .label)) ?? id
            creditsMultiplier = max(1, (try? c.decode(Int.self, forKey: .creditsMultiplier)) ?? (try? c.decode(Double.self, forKey: .creditsMultiplier)).map { Int($0.rounded(.up)) } ?? 1)
            aspects = (try? c.decode([String].self, forKey: .aspects)) ?? []; note = try? c.decode(String.self, forKey: .note)
        }
        public func supports(aspect: String) -> Bool { aspects.isEmpty || aspects.contains(aspect) }
    }
    public struct Platform: Codable, Sendable, Equatable {
        public let id: String, label: String, aspect: String, resolution: String
        public let note: String?
        public let recommendedMinutes: Double?     // what the platform wants (preselected, unless the person chose a length)
        public let maxMinutes: Double?             // a soft limit; nil when there is none
        public let otherAspects: [String]          // formats that also work, shown as small secondary choices
        public let supports4K: Bool                // false: the platform does not deliver 4K, the app recommends against it
        public let note4K: String?                 // the server's sentence for that recommendation
        enum CodingKeys: String, CodingKey { case id, label, aspect, resolution, note, recommendedMinutes = "recommended_minutes", maxMinutes = "max_minutes", otherAspects = "other_aspects", supports4K = "supports_4k", note4K = "note_4k" }
        public init(id: String, label: String, aspect: String, resolution: String, note: String? = nil, recommendedMinutes: Double? = nil, maxMinutes: Double? = nil, otherAspects: [String] = [], supports4K: Bool = false, note4K: String? = nil) {
            self.supports4K = supports4K; self.note4K = note4K
            self.id = id; self.label = label; self.aspect = aspect; self.resolution = resolution; self.note = note; self.recommendedMinutes = recommendedMinutes; self.maxMinutes = maxMinutes; self.otherAspects = otherAspects
        }
        public init(from d: Decoder) throws {
            let c = try d.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id); label = (try? c.decode(String.self, forKey: .label)) ?? id
            aspect = (try? c.decode(String.self, forKey: .aspect)) ?? "16:9"; resolution = (try? c.decode(String.self, forKey: .resolution)) ?? "1080p"
            note = try? c.decode(String.self, forKey: .note)
            recommendedMinutes = try? c.decode(Double.self, forKey: .recommendedMinutes); maxMinutes = try? c.decode(Double.self, forKey: .maxMinutes)
            otherAspects = (try? c.decode([String].self, forKey: .otherAspects)) ?? []
            supports4K = (try? c.decode(Bool.self, forKey: .supports4K)) ?? false; note4K = try? c.decode(String.self, forKey: .note4K)
        }
    }
    public struct Lengths: Codable, Sendable, Equatable {
        public let minMinutes: Double, maxMinutes: Double
        public let presets: [Double]
        enum CodingKeys: String, CodingKey { case minMinutes = "min_minutes", maxMinutes = "max_minutes", presets }
        public init(minMinutes: Double = 1, maxMinutes: Double = 12, presets: [Double] = CreateOptions.lengths) { self.minMinutes = minMinutes; self.maxMinutes = maxMinutes; self.presets = presets }
        public init(from d: Decoder) throws {
            let c = try d.container(keyedBy: CodingKeys.self)
            minMinutes = (try? c.decode(Double.self, forKey: .minMinutes)) ?? 1; maxMinutes = (try? c.decode(Double.self, forKey: .maxMinutes)) ?? 12
            let top = (try? c.decode(Double.self, forKey: .maxMinutes)) ?? 12
            let p = ((try? c.decode([Double].self, forKey: .presets)) ?? []).filter { $0 > 0 && $0 <= top }.sorted()
            presets = p.isEmpty ? CreateOptions.lengths : p
        }
    }
    public struct Language: Codable, Sendable, Equatable { public let id: String, label: String
        public init(id: String, label: String) { self.id = id; self.label = label } }

    public var aspects: [Aspect]
    public var resolutions: [Resolution]
    public var platforms: [Platform]
    public var languages: [Language]
    public var maxPhotos: Int
    public var intake: Bool
    public var lengths: Lengths

    enum CodingKeys: String, CodingKey { case aspects, resolutions, platforms, languages, lengths, maxPhotos = "max_photos", intake }

    public init(aspects: [Aspect], resolutions: [Resolution], platforms: [Platform], languages: [Language] = [], maxPhotos: Int = 100, intake: Bool = true, lengths: Lengths = Lengths()) {
        self.lengths = lengths; self.aspects = aspects; self.resolutions = resolutions; self.platforms = platforms; self.languages = languages; self.maxPhotos = maxPhotos; self.intake = intake
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        aspects = (try? c.decode([Aspect].self, forKey: .aspects)) ?? []; resolutions = (try? c.decode([Resolution].self, forKey: .resolutions)) ?? []
        platforms = (try? c.decode([Platform].self, forKey: .platforms)) ?? []; languages = (try? c.decode([Language].self, forKey: .languages)) ?? []
        maxPhotos = (try? c.decode(Int.self, forKey: .maxPhotos)) ?? 100; intake = (try? c.decode(Bool.self, forKey: .intake)) ?? false
        lengths = (try? c.decode(Lengths.self, forKey: .lengths)) ?? Lengths()
    }

    /// The length chips: the server's presets from 15 seconds up, or 1, 2, 3, 5, 8, 12 when it does not say.
    public var lengthPresets: [Double] { lengths.presets }

    public static let platformDefaults: [Platform] = [
        Platform(id: "youtube", label: "YouTube", aspect: "16:9", resolution: "1080p"), Platform(id: "linkedin", label: "LinkedIn", aspect: "16:9", resolution: "1080p"),
        Platform(id: "x", label: "X", aspect: "16:9", resolution: "1080p"), Platform(id: "other", label: "Just a video", aspect: "16:9", resolution: "1080p"),
        Platform(id: "shorts", label: "Shorts", aspect: "9:16", resolution: "1080p"), Platform(id: "reels", label: "Reels", aspect: "9:16", resolution: "1080p"),
        Platform(id: "tiktok", label: "TikTok", aspect: "9:16", resolution: "1080p"), Platform(id: "instagram_feed", label: "Instagram", aspect: "4:5", resolution: "1080p"),
    ]

    /// 16:9 and 1080p only, no intake (the check is skipped): what the app offers while the server cannot say more.
    public static let fallback = CreateCapabilities(
        aspects: [Aspect(id: "16:9", label: "Landscape"), Aspect(id: "9:16", label: "Vertical", ready: false), Aspect(id: "1:1", label: "Square", ready: false), Aspect(id: "4:5", label: "Portrait", ready: false)],
        resolutions: [Resolution(id: "1080p")], platforms: platformDefaults, intake: false)

    public var readyAspects: [Aspect] { aspects.filter(\.ready) }
    public func aspect(_ id: String) -> Aspect? { aspects.first { $0.id == id } }
    public func isSupported(aspect: String, resolution: String) -> Bool { aspects.contains { $0.id == aspect && $0.ready } && resolutions.contains { $0.id == resolution && $0.supports(aspect: aspect) } }
    public func resolution(_ id: String) -> Resolution? { resolutions.first { $0.id == id } }
    /// "4K" for 2160p; the id itself when the server does not list it.
    public func resolutionLabel(_ id: String) -> String { resolution(id)?.label ?? id }
    /// What the chosen resolution costs relative to 1080p (1 when unknown).
    public func multiplier(_ id: String) -> Int { resolution(id)?.creditsMultiplier ?? 1 }
    /// "Landscape 16:9"
    public func aspectName(_ id: String) -> String { "\(aspect(id)?.label ?? id) \(id)" }
}

/// One chip of "What is it for?". Data, not code: it is supported only when the server can make its format.
public struct PlatformChip: Equatable, Sendable, Identifiable {
    public let id: String          // the platform id sent to the server (the first one of a group)
    public let label: String
    public let aspect: String
    public let resolution: String
    public let supported: Bool
    public let members: [String]   // "Shorts · Reels · TikTok" is one chip for three ids
    public var note: String? = nil
    public var recommendedMinutes: Double? = nil
    public var maxMinutes: Double? = nil
    public var otherAspects: [String] = []
    public var supports4K = false
    public var note4K: String? = nil
}

public enum PlatformChips {
    /// Supported chips first (YouTube, LinkedIn, X, Just a video), then the ones that are "Soon".
    public static func make(_ caps: CreateCapabilities) -> [PlatformChip] {
        var byID = Dictionary(uniqueKeysWithValues: CreateCapabilities.platformDefaults.map { ($0.id, $0) })
        for p in caps.platforms { byID[p.id] = p }
        let o = byID["other"]
        byID["other"] = CreateCapabilities.Platform(id: "other", label: "Just a video", aspect: o?.aspect ?? "16:9", resolution: o?.resolution ?? "1080p", note: o?.note, recommendedMinutes: o?.recommendedMinutes,
                                                    maxMinutes: o?.maxMinutes, otherAspects: o?.otherAspects ?? [], supports4K: o?.supports4K ?? true, note4K: o?.note4K)
        func chip(_ ids: [String], _ label: String) -> PlatformChip? {
            let found = ids.compactMap { byID[$0] }
            guard let first = found.first else { return nil }
            return PlatformChip(id: first.id, label: label, aspect: first.aspect, resolution: first.resolution, supported: found.allSatisfy { caps.isSupported(aspect: $0.aspect, resolution: $0.resolution) }, members: ids,
                                note: first.note, recommendedMinutes: first.recommendedMinutes, maxMinutes: first.maxMinutes, otherAspects: first.otherAspects.filter { id in caps.readyAspects.contains { $0.id == id } },
                                supports4K: found.allSatisfy(\.supports4K), note4K: found.first { !$0.supports4K }?.note4K)
        }
        let all = [chip(["youtube"], "YouTube"), chip(["linkedin"], "LinkedIn"), chip(["x"], "X"), chip(["other"], "Just a video"),
                   chip(["shorts", "reels", "tiktok"], "Shorts · Reels · TikTok"), chip(["instagram_feed"], "Instagram")].compactMap { $0 }
        return all.filter(\.supported) + all.filter { !$0.supported }
    }
}

/// The current choices and what they are called in plain words.
public struct CreateForm: Equatable, Sendable {
    public var text = ""
    public var platform = "other"
    public var aspect = "16:9"
    public var resolution = "1080p"
    public var minutes = CreateOptions.defaultMinutes
    public var look: VideoLook?
    public var captions = true
    public var language = "auto"
    /// The person changed the length by hand since the screen opened: a platform pick then keeps it (and only shows its recommendation).
    public private(set) var lengthTouched = false
    /// Any explicit pick (platform or length): remembered defaults arriving late never override it.
    public private(set) var userTouched = false

    public init() {}

    /// The person picked the resolution by hand: a platform pick then keeps it (4K is never chosen for them).
    public private(set) var resolutionTouched = false
    /// What each listed resolution costs relative to 1080p, from the capabilities (`normalize`).
    public private(set) var multipliers: [String: Int] = [:]

    public mutating func setMinutes(_ m: Double) { minutes = m; lengthTouched = true; userTouched = true }
    public mutating func setResolution(_ id: String) { resolution = id; resolutionTouched = true; userTouched = true }
    public mutating func resetTouches() { lengthTouched = false; userTouched = false; resolutionTouched = false }

    public var creditsMultiplier: Int { multipliers[resolution] ?? 1 }
    public var options: CreateOptions { CreateOptions(minutes: minutes, look: look, captions: captions, platform: platform, aspect: aspect, resolution: resolution, language: language, creditsMultiplier: creditsMultiplier) }

    /// The resolutions to show for the chosen shape, in the server's order (one that cannot be made in this shape is left out).
    public func resolutionChoices(_ caps: CreateCapabilities) -> [CreateCapabilities.Resolution] { caps.resolutions.filter { $0.supports(aspect: aspect) } }

    /// The line under the resolution chips when the chosen one has a note ("4K (2160p) costs twice the credits…").
    public func resolutionNote(_ caps: CreateCapabilities) -> String? { caps.resolution(resolution)?.note }

    /// 4K is chosen for a platform that does not deliver it: the server's sentence recommending against it, and the resolution to go back to.
    /// A recommendation only: the person may still go ahead.
    public func fourKAdvice(_ caps: CreateCapabilities) -> (text: String, useResolution: String)? {
        guard caps.multiplier(resolution) > 1, let c = chip(caps), !c.supports4K else { return nil }
        let back = resolutionChoices(caps).last { $0.creditsMultiplier == 1 }?.id ?? c.resolution
        guard back != resolution else { return nil }
        let text = (c.note4K?.isEmpty == false ? c.note4K : nil) ?? "\(c.label) does not show \(caps.resolutionLabel(resolution)); it would cost \(caps.multiplier(resolution)) times the credits for no visible gain."
        return (text, back)
    }
    public var hasContent: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    public func chip(_ caps: CreateCapabilities) -> PlatformChip? { PlatformChips.make(caps).first { $0.members.contains(platform) } }

    /// The person changed the format away from what the platform recommends (its own "also works" formats do not count as custom).
    public func isCustom(_ caps: CreateCapabilities) -> Bool { guard let c = chip(caps) else { return true }; return !(c.aspect == aspect || c.otherAspects.contains(aspect)) || (c.resolution != resolution && caps.multiplier(resolution) == 1) }      // 4K on top of a platform is still that platform

    /// "LinkedIn · Portrait 4:5 · 1080p · about 1 min": the server's own note for the platform's recommendation, else built from the choices
    /// ("YouTube · Landscape 16:9 · 1080p", or "Custom · Vertical 9:16 · 1080p").
    public func recommendation(_ caps: CreateCapabilities) -> String {
        let c = chip(caps)
        let name = isCustom(caps) ? "Custom" : (c?.label ?? "Just a video")
        if !isCustom(caps), let c, c.aspect == aspect, c.resolution == resolution, let note = c.note, !note.isEmpty { return "\(name) · \(note)" }
        return "\(name) · \(caps.aspectName(aspect)) · \(caps.resolutionLabel(resolution))"
    }

    /// "Also works: Square, Landscape": the platform's other formats, as small secondary choices that switch only the format.
    public func alsoWorks(_ caps: CreateCapabilities) -> [(id: String, name: String)] {
        guard let c = chip(caps), c.supported else { return [] }
        return ([c.aspect] + c.otherAspects).filter { $0 != aspect }.compactMap { id in caps.aspect(id).map { (id, $0.label) } }
    }

    /// Longer than the platform allows: a gentle line and a one-tap chip to use its longest preset within the limit.
    public func maxLengthHint(_ caps: CreateCapabilities) -> (text: String, fixMinutes: Double)? {
        guard let c = chip(caps), let max = c.maxMinutes, minutes > max + 1e-9 else { return nil }
        let presets = caps.lengthPresets.sorted()
        let fix = presets.last { $0 <= max + 1e-9 } ?? presets.first ?? max
        return ("\(c.label) allows up to \(LengthLabel.clock(max)).", fix)
    }

    /// The Change link exists only when there is a real choice to make.
    public func canChangeFormat(_ caps: CreateCapabilities) -> Bool { caps.readyAspects.count > 1 || caps.resolutions.count > 1 }

    /// Picking a platform sets its format and, unless the length was changed by hand since the screen opened, its recommended length.
    public mutating func select(_ chip: PlatformChip) {
        guard chip.supported else { return }
        platform = chip.id; aspect = chip.aspect; userTouched = true
        if !resolutionTouched { resolution = chip.resolution }                  // an explicit resolution stays; a platform never picks 4K
        if !lengthTouched, let m = chip.recommendedMinutes { minutes = m }
    }

    /// One line for the collapsed "More options" row.
    public func moreSummary(_ caps: CreateCapabilities) -> String {
        let lang = language == "auto" ? "Same language as description" : (caps.languages.first { $0.id == language }?.label ?? language)
        return "\(look?.title ?? "Auto") look · Subtitles \(captions ? "on" : "off") · \(lang)"
    }

    /// Keeps the choices inside what the server lists (a stored format that is gone falls back to the first supported one, quietly).
    public mutating func normalize(_ caps: CreateCapabilities) {
        multipliers = Dictionary(caps.resolutions.map { ($0.id, $0.creditsMultiplier) }, uniquingKeysWith: { a, _ in a })
        if let r = caps.resolution(resolution), !r.supports(aspect: aspect) { resolution = resolutionChoices(caps).last { $0.creditsMultiplier == 1 }?.id ?? resolutionChoices(caps).first?.id ?? resolution }
        if !caps.isSupported(aspect: aspect, resolution: resolution) {
            let a = caps.readyAspects.first?.id ?? "16:9"
            aspect = caps.readyAspects.contains { $0.id == aspect } ? aspect : a
            resolution = caps.resolutions.contains { $0.id == resolution } ? resolution : (caps.resolutions.first?.id ?? "1080p")
        }
        if let c = PlatformChips.make(caps).first(where: { $0.members.contains(platform) }), !c.supported { platform = "other"; aspect = caps.readyAspects.first?.id ?? "16:9" }
        if language != "auto", !caps.languages.contains(where: { $0.id == language }) { language = "auto" }
    }
}

/// What is remembered per person: the choices, never the prompt or the photos.
public struct CreateDefaults: Codable, Sendable, Equatable {
    public var platform = "other", aspect = "16:9", resolution = "1080p", language = "auto"
    public var minutes = CreateOptions.defaultMinutes
    public var look: String?
    public var captions = true
    public init() {}
    public init(_ f: CreateForm) { platform = f.platform; aspect = f.aspect; resolution = f.resolution; minutes = f.minutes; look = f.look?.rawValue; captions = f.captions; language = f.language }

    static func key(_ userID: String?) -> String { "createDefaults.\(userID ?? "anonymous")" }

    public static func load(userID: String?, defaults: UserDefaults = .standard) -> CreateDefaults {
        guard let data = defaults.data(forKey: key(userID)), let d = try? JSONDecoder().decode(CreateDefaults.self, from: data) else { return CreateDefaults() }
        return d
    }
    public func save(userID: String?, defaults: UserDefaults = .standard) { if let data = try? JSONEncoder().encode(self) { defaults.set(data, forKey: Self.key(userID)) } }

    /// A fresh form with these choices, kept inside the capabilities.
    public func form(_ caps: CreateCapabilities) -> CreateForm {
        var f = CreateForm()
        f.platform = platform; f.aspect = aspect; f.resolution = caps.multiplier(resolution) > 1 ? "1080p" : resolution       // 4K is never a remembered default: always an explicit choice
        f.minutes = caps.lengthPresets.contains(minutes) ? minutes : (caps.lengthPresets.contains(CreateOptions.defaultMinutes) ? CreateOptions.defaultMinutes : (caps.lengthPresets.first ?? CreateOptions.defaultMinutes))
        f.look = look.flatMap(VideoLook.init(rawValue:)); f.captions = captions; f.language = language
        f.normalize(caps)
        return f
    }
}

// MARK: request check (intake)

public struct IntakeOption: Codable, Sendable, Equatable, Hashable { public let id: String, label: String
    public init(id: String, label: String) { self.id = id; self.label = label } }

public struct IntakeQuestion: Codable, Sendable, Equatable, Identifiable {
    public let id: String
    public let title: String
    public let helper: String?
    public let options: [IntakeOption]
    public let allowOther: Bool
    enum CodingKeys: String, CodingKey { case id, text, title, helper, options, allowOther = "allow_other" }
    public init(id: String, title: String, helper: String? = nil, options: [IntakeOption], allowOther: Bool = true) { self.id = id; self.title = title; self.helper = helper; self.options = options; self.allowOther = allowOther }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = (try? c.decode(String.self, forKey: .text)) ?? (try? c.decode(String.self, forKey: .title)) ?? ""
        helper = try? c.decode(String.self, forKey: .helper)
        options = (try? c.decode([IntakeOption].self, forKey: .options)) ?? []
        allowOther = (try? c.decode(Bool.self, forKey: .allowOther)) ?? true
    }
    public func encode(to e: Encoder) throws { var c = e.container(keyedBy: CodingKeys.self); try c.encode(id, forKey: .id); try c.encode(title, forKey: .text); try c.encode(options, forKey: .options); try c.encode(allowOther, forKey: .allowOther) }
}

public struct IntakeAnswer: Codable, Sendable, Equatable {
    public let id: String
    public var option: String?
    public var text: String?
    public var skip: Bool?
    public var label: String? = nil           // what the chip says (local only, never sent)
    enum CodingKeys: String, CodingKey { case id, option, text, skip }
    public static func chose(_ id: String, _ option: IntakeOption) -> IntakeAnswer { IntakeAnswer(id: id, option: option.id, label: option.label) }
    public static func other(_ id: String, _ text: String) -> IntakeAnswer { IntakeAnswer(id: id, text: text, label: text) }
    public static func skipped(_ id: String) -> IntakeAnswer { IntakeAnswer(id: id, skip: true) }
    public var isReal: Bool { skip != true }
}

public struct BriefRequest: Encodable, Sendable {
    public struct Options: Encodable, Sendable { public let platform, aspect, resolution: String; public let captions: Bool; public let language: String; public let target_minutes: Double }
    public let prompt: String
    public let options: Options
    public let media_count: Int
    public let answers: [IntakeAnswer]
    public init(prompt: String, options: CreateOptions, mediaCount: Int, answers: [IntakeAnswer] = []) {
        self.prompt = Brief.normalized(prompt); self.media_count = mediaCount; self.answers = answers
        self.options = Options(platform: options.platform, aspect: options.aspect, resolution: options.resolution, captions: options.captions, language: options.language, target_minutes: options.minutes)
    }
}

public enum BriefResponse: Sendable, Equatable {
    case ok(brief: [String: String])
    case questions([IntakeQuestion])
    case notSupported(message: String?, suggestion: String?)
    case blocked(message: String?)
    case paused(message: String?, retryAfter: Int?)

    public static func decode(_ data: Data) -> BriefResponse? {
        struct Raw: Decodable { let status: String; let brief: [String: String]?; let questions: [IntakeQuestion]?; let message: String?; let suggestion: String?; let retry_after: Int? }
        guard let r = try? JSONDecoder().decode(Raw.self, from: data) else { return nil }
        switch r.status {
        case "ok": return .ok(brief: r.brief ?? [:])
        case "questions": return .questions(Array((r.questions ?? []).filter { !$0.options.isEmpty }.prefix(3)))
        case "not_supported", "unsupported": return .notSupported(message: r.message, suggestion: r.suggestion)
        case "blocked", "unsafe": return .blocked(message: r.message)
        case "paused": return .paused(message: r.message, retryAfter: r.retry_after)
        default: return nil
        }
    }
}

public protocol CreateServing: Sendable {
    func capabilities() async throws -> CreateCapabilities
    func checkRequest(_ request: BriefRequest) async throws -> BriefResponse
}

extension APIClient: CreateServing {
    public func capabilities() async throws -> CreateCapabilities {
        let (data, http) = try await perform("GET", ["capabilities"])
        guard (200..<300).contains(http.statusCode), let caps = try? JSONDecoder().decode(CreateCapabilities.self, from: data), !caps.aspects.isEmpty else { throw APIError.server }
        return caps
    }

    public func checkRequest(_ request: BriefRequest) async throws -> BriefResponse {
        let body = try JSONEncoder().encode(request)
        let (data, http) = try await perform("POST", ["videos", "brief"], body: body)
        if http.statusCode == 429, let r = BriefResponse.decode(data) { return r }
        guard http.statusCode == 200, let r = BriefResponse.decode(data) else { throw APIError.server }
        return r
    }
}

public enum CheckOutcome: Sendable, Equatable {
    case proceed(brief: [String: String]?)
    case questions([IntakeQuestion])
    case notSupported(message: String?, suggestion: String?)
    case blocked(String?)
    case paused(message: String?, retryAfter: Int?)
}

/// The request check with its budgets: anything slower than `timeout`, or any failure, means "go on without a brief". `onSlow` fires once after `slowAfter`
/// (the skeleton is only shown then).
public struct CreateChecker: Sendable {
    public let api: any CreateServing
    public var timeout: Duration
    public var slowAfter: Duration
    public init(api: any CreateServing, timeout: Duration = .seconds(8), slowAfter: Duration = .milliseconds(2500)) { self.api = api; self.timeout = timeout; self.slowAfter = slowAfter }

    public func check(_ request: BriefRequest, onSlow: @escaping @Sendable () -> Void = {}) async -> CheckOutcome {
        let api = self.api, timeout = self.timeout, slowAfter = self.slowAfter
        return await withTaskGroup(of: CheckOutcome?.self) { group in
            group.addTask {
                guard let r = try? await api.checkRequest(request) else { return .proceed(brief: nil) }
                switch r {
                case .ok(let brief): return .proceed(brief: brief.isEmpty ? nil : brief)
                case .questions(let q): return q.isEmpty ? .proceed(brief: nil) : .questions(q)
                case .notSupported(let m, let s): return .notSupported(message: m, suggestion: s)
                case .blocked(let m): return .blocked(m)
                case .paused(let m, let t): return .paused(message: m, retryAfter: t)
                }
            }
            group.addTask { try? await Task.sleep(for: timeout); return .proceed(brief: nil) }
            group.addTask { try? await Task.sleep(for: slowAfter); if !Task.isCancelled { onSlow() }; return nil }
            while let r = await group.next() { if let r { group.cancelAll(); return r } }
            return .proceed(brief: nil)
        }
    }
}

/// The one-at-a-time questions: up to 3, each answered by a tap, with Other, You decide, Skip, back and Make it now.
public struct IntakeFlow: Sendable, Equatable {
    public let questions: [IntakeQuestion]
    public private(set) var index = 0
    public private(set) var answers: [String: IntakeAnswer] = [:]
    public private(set) var madeItNow = false
    public private(set) var editing: String?
    public init(_ questions: [IntakeQuestion]) { self.questions = Array(questions.prefix(3)) }

    public var current: IntakeQuestion? { questions.indices.contains(index) ? questions[index] : nil }
    public var progressText: String { "Question \(index + 1) of \(questions.count)" }
    /// Done asking: every question has an answer (or a skip), or the person chose Make it now.
    public var isComplete: Bool { madeItNow || (editing == nil && questions.allSatisfy { answers[$0.id] != nil }) }
    public var canGoBack: Bool { index > 0 && editing == nil }

    /// The answers in question order (skips included: they are sent as `skip: true`).
    public var payload: [IntakeAnswer] { questions.compactMap { answers[$0.id] } }
    public var realAnswers: [IntakeAnswer] { payload.filter(\.isReal) }
    /// Skipped everything: nothing to confirm, the video can start.
    public var needsSummary: Bool { !realAnswers.isEmpty }

    public mutating func choose(_ option: IntakeOption) { guard let q = current else { return }; record(.chose(q.id, option)) }
    public mutating func other(_ text: String) { guard let q = current, SuggestedNames.isValid(text) || !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }; record(.other(q.id, String(text.trimmingCharacters(in: .whitespacesAndNewlines).prefix(200)))) }
    public mutating func skip() { guard let q = current else { return }; record(.skipped(q.id)) }
    public mutating func youDecide() { skip() }
    public mutating func back() { if canGoBack { index -= 1 } }
    public mutating func makeItNow() { madeItNow = true; editing = nil }
    /// Reopens one question from the summary; answering returns to the summary.
    public mutating func edit(_ id: String) { guard let i = questions.firstIndex(where: { $0.id == id }) else { return }; index = i; editing = id; madeItNow = false }

    private mutating func record(_ a: IntakeAnswer) {
        answers[a.id] = a
        if editing != nil { editing = nil; index = questions.count; return }
        if index < questions.count - 1 { index += 1 } else { index = questions.count }
    }

    /// The summary chips: the server's own words when it sent a summary, else the answers' labels. Each knows the question it reopens.
    public func chips(briefSummary: String?) -> [(questionID: String, text: String)] {
        let real = realAnswers
        let parts = briefSummary?.components(separatedBy: " · ").filter { !$0.isEmpty } ?? []
        return real.enumerated().map { i, a in (a.id, parts.count == real.count ? parts[i] : (a.label ?? a.text ?? "")) }
    }
}

public enum RetryText {
    /// "Try again in about 1 hour." from the server's seconds.
    public static func make(_ seconds: Int?) -> String? {
        guard let s = seconds, s > 0 else { return nil }
        if s < 90 { return "Try again in about a minute." }
        if s < 3600 { return "Try again in about \(ComposerPlan.plural((s + 30) / 60, "minute"))." }
        if s < 86_400 { return "Try again in about \(ComposerPlan.plural((s + 1800) / 3600, "hour"))." }
        return "Try again in about \(ComposerPlan.plural((s + 43_200) / 86_400, "day"))."
    }
}


/// How lengths are written on chips and in hints.
public enum LengthLabel {
    /// "15 s", "30 s", "45 s", "1 min", "2 min".
    public static func chip(_ minutes: Double) -> String { minutes < 1 ? "\(Int((minutes * 60).rounded())) s" : "\(Int(minutes.rounded())) min" }
    /// "2:20" for 2 minutes 20 seconds.
    public static func clock(_ minutes: Double) -> String { let s = Int((minutes * 60).rounded()); return String(format: "%d:%02d", s / 60, s % 60) }
    /// "15 seconds", "2 minutes" for screen readers.
    public static func spoken(_ minutes: Double) -> String { minutes < 1 ? "\(Int((minutes * 60).rounded())) seconds" : ComposerPlan.plural(Int(minutes.rounded()), "minute") }
}

/// How a chip with a label of unknown length is laid out so its text is never cut: on one line when it fits the row, otherwise at the full
/// width of its container on two lines, and on as many lines as it needs when even that is not enough.
public enum ChipFit {
    public enum Mode: Equatable, Sendable { case singleLine, wrapped, fullWidth }

    /// A rough width of `label` in points: an average glyph is about 0.55 em wide, plus the chip's padding and icon.
    public static func estimatedWidth(label: String, fontSize: Double, padding: Double = 44, extra: Double = 0) -> Double {
        Double(label.count) * fontSize * 0.55 + padding + extra
    }

    /// `singleLine`: fits on one line in the available width. `wrapped`: a chip of its own width that needs two lines. `fullWidth`: needs
    /// more than half a container's width of text, so it takes the whole row (and as many lines as it needs, never fewer than the text).
    public static func mode(label: String, availableWidth: Double, fontSize: Double = 17, padding: Double = 44, extra: Double = 0) -> Mode {
        let natural = estimatedWidth(label: label, fontSize: fontSize, padding: padding, extra: extra)
        if natural <= availableWidth { return .singleLine }
        return natural <= availableWidth * 1.0 + (availableWidth - padding) ? .wrapped : .fullWidth
    }

    /// Lines the text needs at that width (at least 1); a chip never allows fewer.
    public static func lines(label: String, availableWidth: Double, fontSize: Double = 17, padding: Double = 44) -> Int {
        let textWidth = max(1, availableWidth - padding)
        return max(1, Int((Double(label.count) * fontSize * 0.55 / textWidth).rounded(.up)))
    }
}
