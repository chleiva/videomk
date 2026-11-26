import Foundation

/// What the user needs to know about a video's state. The server has finer statuses; we only distinguish what changes the UI.
public enum VideoStatus: Sendable, Equatable {
    case running(Stage)
    case complete
    case failed
    case rejected

    public enum Stage: Int, Sendable, CaseIterable, Comparable {
        case starting, writing, voiceAndVisuals, rendering
        public static func < (a: Stage, b: Stage) -> Bool { a.rawValue < b.rawValue }

        /// Fits on one line in a list row.
        public var shortTitle: String {
            switch self {
            case .starting: tr("stage.short.starting")
            case .writing: tr("stage.short.writing")
            case .voiceAndVisuals: tr("stage.short.voice_visuals")
            case .rendering: tr("stage.short.rendering")
            }
        }

        public var title: String {
            switch self {
            case .starting: tr("stage.long.starting")
            case .writing: tr("stage.long.writing")
            case .voiceAndVisuals: tr("stage.long.voice_visuals")
            case .rendering: tr("stage.long.rendering")
            }
        }
    }

    public init(serverStatus raw: String) {
        switch raw.uppercased() {
        case "COMPLETE", "PREVIEW_READY": self = .complete
        case "FAILED", "EDIT_FAILED", "CANCELLED": self = .failed
        case "REJECTED": self = .rejected
        case "PLOT_CREATION": self = .running(.writing)
        case "ASSETS_CREATION", "STORYBOARD_CREATION": self = .running(.voiceAndVisuals)
        case "RENDERING": self = .running(.rendering)
        default: self = .running(.starting)
        }
    }

    public var isRunning: Bool { if case .running = self { true } else { false } }
}

public struct VideoItem: Sendable, Equatable, Identifiable, Decodable {
    public let id: String
    public let status: VideoStatus
    public let title: String?
    public let durationSeconds: Double?
    public let createdAt: Date?
    public let videoURL: URL?
    public let previewGifURL: URL?
    public let rejectReason: String?
    public let editable: Bool
    /// The frame shape the video was made in ("16:9", "9:16", "1:1", "4:5") and its resolution; nil for videos from before formats existed.
    public let aspect: String?
    public let resolution: String?
    /// While a video made from a presentation is being planned (`PLOT_CREATION`): reading the slides, then writing the narration. nil for every other video.
    public let deckStage: DeckStage?

    public enum DeckStage: String, Sendable, Equatable { case reading = "deck_reading", writing = "deck_writing" }

    enum CodingKeys: String, CodingKey {
        case videoID = "video_id", status, title, durationS = "duration_s", createdAt = "created_at"
        case videoURL = "video_url", previewGifURL = "preview_gif_url", rejectReason = "reject_reason", editable, aspect, resolution, stage
    }

    public init(id: String, status: VideoStatus, title: String? = nil, durationSeconds: Double? = nil, createdAt: Date? = nil,
                videoURL: URL? = nil, previewGifURL: URL? = nil, rejectReason: String? = nil, editable: Bool = false, aspect: String? = nil, resolution: String? = nil, deckStage: DeckStage? = nil) {
        self.deckStage = deckStage
        self.id = id; self.status = status; self.title = title; self.durationSeconds = durationSeconds; self.createdAt = createdAt
        self.videoURL = videoURL; self.previewGifURL = previewGifURL; self.rejectReason = rejectReason; self.editable = editable; self.aspect = aspect; self.resolution = resolution
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .videoID)
        status = VideoStatus(serverStatus: (try? c.decode(String.self, forKey: .status)) ?? "")
        title = try? c.decode(String.self, forKey: .title)
        durationSeconds = try? c.decode(Double.self, forKey: .durationS)
        createdAt = (try? c.decode(String.self, forKey: .createdAt)).flatMap(Self.parseDate)
        videoURL = (try? c.decode(String.self, forKey: .videoURL)).flatMap(URL.init(string:))
        previewGifURL = (try? c.decode(String.self, forKey: .previewGifURL)).flatMap(URL.init(string:))
        rejectReason = try? c.decode(String.self, forKey: .rejectReason)
        editable = (try? c.decode(Bool.self, forKey: .editable)) ?? false
        aspect = try? c.decode(String.self, forKey: .aspect)
        resolution = try? c.decode(String.self, forKey: .resolution)
        deckStage = (try? c.decode(String.self, forKey: .stage)).flatMap(DeckStage.init(rawValue:))
    }

    static func parseDate(_ s: String) -> Date? {
        let f = ISO8601DateFormatter()
        return f.date(from: s)
    }

    /// Width over height of the picture (16:9 when unknown or unreadable), so cards and the player never distort a vertical or square video.
    public var aspectRatio: Double { Self.ratio(aspect) }
    public var isPortrait: Bool { aspectRatio < 1 }

    public static func ratio(_ aspect: String?) -> Double {
        let p = (aspect ?? "").split(separator: ":").compactMap { Double($0) }
        return p.count == 2 && p[0] > 0 && p[1] > 0 ? p[0] / p[1] : 16.0 / 9.0
    }

    public var displayTitle: String { (title?.isEmpty == false ? title! : nil) ?? tr("video.untitled") }
}

struct VideoListResponse: Decodable { let items: [VideoItem] }
struct StartResponse: Decodable { let videoID: String; enum CodingKeys: String, CodingKey { case videoID = "video_id" } }
struct PlaybackResponse: Decodable { let url: String; let description: String? }

public struct PlaybackInfo: Sendable, Equatable {
    public let url: URL
    /// Title-less description with chapters, linked image credits and sources.
    public let description: String?
    public init(url: URL, description: String?) { self.url = url; self.description = description }
}
struct MessageResponse: Decodable { let message: String? ; let status: String? }

/// The three looks the video engine offers (docs/mobile/DESIGN_BRIEF.md).
public enum VideoLook: String, CaseIterable, Sendable, Identifiable {
    case midnight, paper, sunrise
    public var id: String { rawValue }
    public var title: String { tr("look." + rawValue) }
}

public struct CreateOptions: Sendable, Equatable {
    /// What the app offers until the server says otherwise (capabilities carry `lengths.presets`, from 15 seconds up).
    public static let lengths: [Double] = [1, 2, 3, 5, 8, 12]
    public static let defaultMinutes: Double = 3
    public var minutes: Double
    public var look: VideoLook?  // nil = let the Producer choose
    public var captions: Bool    // subtitles on the video; the creator decides
    public var platform: String  // what the video is for (youtube, linkedin, x, other, ...)
    public var aspect: String    // 16:9, 9:16, 1:1, 4:5
    public var resolution: String // 720p or 1080p
    public var language: String  // "auto" (the description's language) or a language id

    /// What the chosen resolution costs relative to 1080p (2 for 4K), from the capabilities.
    public var creditsMultiplier: Int
    /// A presentation is attached: its price at its own length (the server's number), the usual rule for any other length.
    public var deck: DeckPrice?

    public init(minutes: Double = CreateOptions.defaultMinutes, look: VideoLook? = nil, captions: Bool = true, platform: String = "other", aspect: String = "16:9", resolution: String = "1080p", language: String = "auto", creditsMultiplier: Int = 1, deck: DeckPrice? = nil) {
        self.deck = deck; self.creditsMultiplier = max(1, creditsMultiplier); self.minutes = minutes; self.look = look; self.captions = captions; self.platform = platform; self.aspect = aspect; self.resolution = resolution; self.language = language
    }
}

public extension CreateOptions {
    /// 1 credit per started minute, at least 1 (matches the server; the server's number is the one that is charged).
    /// Times the resolution's multiplier: 3 minutes is 3 credits at 1080p and 6 at 4K.
    var credits: Int { if let deck { return deck.credits(minutes: minutes, multiplier: creditsMultiplier) }; return max(1, min(12, Int(minutes.rounded(.up)))) * creditsMultiplier }
}

public struct WalletBucket: Sendable, Equatable, Decodable {
    public enum Kind: String, Sendable { case daily, signup, paid, refund, other }
    public let kindName: String
    public let remaining: Int
    public let expiresAt: Date?
    public var kind: Kind { Kind(rawValue: kindName) ?? .other }
    enum CodingKeys: String, CodingKey { case kindName = "kind", remaining, expiresAt = "expires_at" }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kindName = try c.decode(String.self, forKey: .kindName)
        remaining = try c.decode(Int.self, forKey: .remaining)
        expiresAt = (try? c.decode(Double.self, forKey: .expiresAt)).map(Date.init(timeIntervalSince1970:))
    }
    public init(kind: String, remaining: Int, expiresAt: Date? = nil) { kindName = kind; self.remaining = remaining; self.expiresAt = expiresAt }
}

public struct WalletInfo: Sendable, Equatable, Decodable {
    public let balance: Int
    public let buckets: [WalletBucket]
    public let nextFreeAt: Date?
    public let dailyCredits: Int
    public let signupCredits: Int
    /// Test and staff accounts the server never charges.
    public let unlimited: Bool
    enum CodingKeys: String, CodingKey { case balance, buckets, nextDailyAt = "next_daily_at", rules, unlimited }
    private struct Rules: Decodable { let daily: Int?; let signup: Int? }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        balance = try c.decode(Int.self, forKey: .balance)
        buckets = (try? c.decode([WalletBucket].self, forKey: .buckets)) ?? []
        nextFreeAt = (try? c.decode(Double.self, forKey: .nextDailyAt)).map(Date.init(timeIntervalSince1970:))
        let r = try? c.decode(Rules.self, forKey: .rules)
        dailyCredits = r?.daily ?? 1; signupCredits = r?.signup ?? 5
        unlimited = (try? c.decode(Bool.self, forKey: .unlimited)) ?? false
    }
    public init(balance: Int, buckets: [WalletBucket] = [], nextFreeAt: Date? = nil, dailyCredits: Int = 1, signupCredits: Int = 5, unlimited: Bool = false) {
        self.balance = balance; self.buckets = buckets; self.nextFreeAt = nextFreeAt; self.dailyCredits = dailyCredits; self.signupCredits = signupCredits; self.unlimited = unlimited
    }

    /// Whether `credits` can be paid right now.
    public func canAfford(_ credits: Int) -> Bool { unlimited || balance >= credits }
}

public enum Brief {
    public static let minLength = 10
    public static let maxLength = 2000
    /// Mirrors the server's whitespace collapse so the counter matches what is sent.
    public static func normalized(_ text: String) -> String { text.split(whereSeparator: \.isWhitespace).joined(separator: " ") }
    public static func isValid(_ text: String) -> Bool { (minLength...maxLength).contains(normalized(text).count) }
}
