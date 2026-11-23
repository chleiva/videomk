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

public enum Brief {
    public static let minLength = 10
    public static let maxLength = 2000
    /// Mirrors the server's whitespace collapse so the counter matches what is sent.
    public static func normalized(_ text: String) -> String { text.split(whereSeparator: \.isWhitespace).joined(separator: " ") }
    public static func isValid(_ text: String) -> Bool { (minLength...maxLength).contains(normalized(text).count) }
}
