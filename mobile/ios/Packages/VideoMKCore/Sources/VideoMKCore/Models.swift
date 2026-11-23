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
            case .starting: "Starting"
            case .writing: "Writing the story"
            case .voiceAndVisuals: "Voice and visuals"
            case .rendering: "Rendering"
            }
        }

        public var title: String {
            switch self {
            case .starting: "Getting started"
            case .writing: "Writing the story"
            case .voiceAndVisuals: "Recording the voice and finding visuals"
            case .rendering: "Rendering"
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

    enum CodingKeys: String, CodingKey {
        case videoID = "video_id", status, title, durationS = "duration_s", createdAt = "created_at"
        case videoURL = "video_url", previewGifURL = "preview_gif_url", rejectReason = "reject_reason", editable
    }

    public init(id: String, status: VideoStatus, title: String? = nil, durationSeconds: Double? = nil, createdAt: Date? = nil,
                videoURL: URL? = nil, previewGifURL: URL? = nil, rejectReason: String? = nil, editable: Bool = false) {
        self.id = id; self.status = status; self.title = title; self.durationSeconds = durationSeconds; self.createdAt = createdAt
        self.videoURL = videoURL; self.previewGifURL = previewGifURL; self.rejectReason = rejectReason; self.editable = editable
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
    }

    static func parseDate(_ s: String) -> Date? {
        let f = ISO8601DateFormatter()
        return f.date(from: s)
    }

    public var displayTitle: String { (title?.isEmpty == false ? title! : nil) ?? "Untitled video" }
}

struct VideoListResponse: Decodable { let items: [VideoItem] }
struct StartResponse: Decodable { let videoID: String; enum CodingKeys: String, CodingKey { case videoID = "video_id" } }
struct PlaybackResponse: Decodable { let url: String; let description: String? }

public struct PlaybackInfo: Sendable, Equatable {
    public let url: URL
    /// Title-less description with chapters, linked image credits and sources.
    public let description: String?
}
struct MessageResponse: Decodable { let message: String? ; let status: String? }

/// The three looks the video engine offers (docs/mobile/DESIGN_BRIEF.md).
public enum VideoLook: String, CaseIterable, Sendable, Identifiable {
    case midnight, paper, sunrise
    public var id: String { rawValue }
    public var title: String { rawValue.capitalized }
}

public struct CreateOptions: Sendable, Equatable {
    public static let lengths: [Double] = [1, 2, 3, 5, 8, 12]
    public static let defaultMinutes: Double = 3
    public var minutes: Double
    public var look: VideoLook?  // nil = let the Producer choose

    public init(minutes: Double = CreateOptions.defaultMinutes, look: VideoLook? = nil) { self.minutes = minutes; self.look = look }
}

public extension CreateOptions {
    /// 1 credit per started minute, at least 1 (matches the server; the server's number is the one that is charged).
    var credits: Int { max(1, min(12, Int(minutes.rounded(.up)))) }
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
