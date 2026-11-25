import Foundation

/// What the apps may offer when creating a video (GET /capabilities, docs/CREATE_API.md). Until the server has it, `fallback` offers 16:9 and 1080p only.
public struct CreateCapabilities: Codable, Sendable, Equatable {
    public struct Aspect: Codable, Sendable, Equatable { public let id: String, label: String; public let ready: Bool, beta: Bool
        public init(id: String, label: String, ready: Bool = true, beta: Bool = false) { self.id = id; self.label = label; self.ready = ready; self.beta = beta }
        public init(from d: Decoder) throws { let c = try d.container(keyedBy: CodingKeys.self); id = try c.decode(String.self, forKey: .id); label = (try? c.decode(String.self, forKey: .label)) ?? id; ready = (try? c.decode(Bool.self, forKey: .ready)) ?? false; beta = (try? c.decode(Bool.self, forKey: .beta)) ?? false } }
    public struct Resolution: Codable, Sendable, Equatable { public let id: String, label: String
        public init(id: String, label: String? = nil) { self.id = id; self.label = label ?? id }
        public init(from d: Decoder) throws { let c = try d.container(keyedBy: CodingKeys.self); id = try c.decode(String.self, forKey: .id); label = (try? c.decode(String.self, forKey: .label)) ?? id } }
    public struct Platform: Codable, Sendable, Equatable { public let id: String, label: String, aspect: String, resolution: String; public let note: String?
        public init(id: String, label: String, aspect: String, resolution: String, note: String? = nil) { self.id = id; self.label = label; self.aspect = aspect; self.resolution = resolution; self.note = note }
        public init(from d: Decoder) throws { let c = try d.container(keyedBy: CodingKeys.self); id = try c.decode(String.self, forKey: .id); label = (try? c.decode(String.self, forKey: .label)) ?? id; aspect = (try? c.decode(String.self, forKey: .aspect)) ?? "16:9"; resolution = (try? c.decode(String.self, forKey: .resolution)) ?? "1080p"; note = try? c.decode(String.self, forKey: .note) } }
    public struct Language: Codable, Sendable, Equatable { public let id: String, label: String
        public init(id: String, label: String) { self.id = id; self.label = label } }

    public var aspects: [Aspect]
    public var resolutions: [Resolution]
    public var platforms: [Platform]
    public var languages: [Language]
    public var maxPhotos: Int
    public var intake: Bool

    enum CodingKeys: String, CodingKey { case aspects, resolutions, platforms, languages, maxPhotos = "max_photos", intake }

    public init(aspects: [Aspect], resolutions: [Resolution], platforms: [Platform], languages: [Language] = [], maxPhotos: Int = 100, intake: Bool = true) {
        self.aspects = aspects; self.resolutions = resolutions; self.platforms = platforms; self.languages = languages; self.maxPhotos = maxPhotos; self.intake = intake
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        aspects = (try? c.decode([Aspect].self, forKey: .aspects)) ?? []; resolutions = (try? c.decode([Resolution].self, forKey: .resolutions)) ?? []
        platforms = (try? c.decode([Platform].self, forKey: .platforms)) ?? []; languages = (try? c.decode([Language].self, forKey: .languages)) ?? []
        maxPhotos = (try? c.decode(Int.self, forKey: .maxPhotos)) ?? 100; intake = (try? c.decode(Bool.self, forKey: .intake)) ?? false
    }

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
    public func isSupported(aspect: String, resolution: String) -> Bool { aspects.contains { $0.id == aspect && $0.ready } && resolutions.contains { $0.id == resolution } }
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
}

public enum PlatformChips {
    /// Supported chips first (YouTube, LinkedIn, X, Just a video), then the ones that are "Soon".
    public static func make(_ caps: CreateCapabilities) -> [PlatformChip] {
        var byID = Dictionary(uniqueKeysWithValues: CreateCapabilities.platformDefaults.map { ($0.id, $0) })
        for p in caps.platforms { byID[p.id] = p }
        byID["other"] = CreateCapabilities.Platform(id: "other", label: "Just a video", aspect: byID["other"]?.aspect ?? "16:9", resolution: byID["other"]?.resolution ?? "1080p")
        func chip(_ ids: [String], _ label: String) -> PlatformChip? {
            let found = ids.compactMap { byID[$0] }
            guard let first = found.first else { return nil }
            return PlatformChip(id: first.id, label: label, aspect: first.aspect, resolution: first.resolution, supported: found.allSatisfy { caps.isSupported(aspect: $0.aspect, resolution: $0.resolution) }, members: ids)
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

    public init() {}

    public var options: CreateOptions { CreateOptions(minutes: minutes, look: look, captions: captions, platform: platform, aspect: aspect, resolution: resolution, language: language) }
    public var hasContent: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    public func chip(_ caps: CreateCapabilities) -> PlatformChip? { PlatformChips.make(caps).first { $0.members.contains(platform) } }

    /// The person changed the format away from what the platform recommends.
    public func isCustom(_ caps: CreateCapabilities) -> Bool { guard let c = chip(caps) else { return true }; return c.aspect != aspect || c.resolution != resolution }

    /// "YouTube · Landscape 16:9 · 1080p" (or "Custom · Vertical 9:16 · 1080p").
    public func recommendation(_ caps: CreateCapabilities) -> String {
        let name = isCustom(caps) ? "Custom" : (chip(caps)?.label ?? "Just a video")
        return "\(name) · \(caps.aspectName(aspect)) · \(resolution)"
    }

    /// The Change link exists only when there is a real choice to make.
    public func canChangeFormat(_ caps: CreateCapabilities) -> Bool { caps.readyAspects.count > 1 || caps.resolutions.count > 1 }

    public mutating func select(_ chip: PlatformChip) { guard chip.supported else { return }; platform = chip.id; aspect = chip.aspect; resolution = chip.resolution }

    /// One line for the collapsed "More options" row.
    public func moreSummary(_ caps: CreateCapabilities) -> String {
        let lang = language == "auto" ? "Same language as description" : (caps.languages.first { $0.id == language }?.label ?? language)
        return "\(look?.title ?? "Auto") look · Subtitles \(captions ? "on" : "off") · \(lang)"
    }

    /// Keeps the choices inside what the server lists (a stored format that is gone falls back to the first supported one, quietly).
    public mutating func normalize(_ caps: CreateCapabilities) {
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
        f.platform = platform; f.aspect = aspect; f.resolution = resolution; f.minutes = CreateOptions.lengths.contains(minutes) ? minutes : CreateOptions.defaultMinutes
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
