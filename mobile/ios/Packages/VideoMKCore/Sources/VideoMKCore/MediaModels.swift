import Foundation

// Models for "My media" (docs/MEDIA_LIBRARY.md, section API). Field names follow the contract exactly.

public struct LibraryPhoto: Codable, Sendable, Equatable, Identifiable, Hashable {
    public let id: String
    public var taken: String?            // "YYYY-MM-DDTHH:MM:SS", local wall-clock time
    public var added: String             // ISO 8601
    public var place: String?
    public var w: Int, h: Int, bytes: Int
    public var thumbURL: URL?
    public var collections: [String]
    public var url: URL?                 // only on GET items/{id}, valid 10 minutes

    enum CodingKeys: String, CodingKey { case id, taken, added, place, w, h, bytes, thumbURL = "thumb_url", collections, url }

    public init(id: String, taken: String? = nil, added: String = "1970-01-01T00:00:00Z", place: String? = nil, w: Int = 0, h: Int = 0, bytes: Int = 0, thumbURL: URL? = nil, collections: [String] = [], url: URL? = nil) {
        self.id = id; self.taken = taken; self.added = added; self.place = place; self.w = w; self.h = h; self.bytes = bytes; self.thumbURL = thumbURL; self.collections = collections; self.url = url
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        taken = try c.decodeIfPresent(String.self, forKey: .taken)
        added = try c.decodeIfPresent(String.self, forKey: .added) ?? ""
        place = try c.decodeIfPresent(String.self, forKey: .place)
        w = try c.decodeIfPresent(Int.self, forKey: .w) ?? 0
        h = try c.decodeIfPresent(Int.self, forKey: .h) ?? 0
        bytes = try c.decodeIfPresent(Int.self, forKey: .bytes) ?? 0
        thumbURL = try c.decodeIfPresent(URL.self, forKey: .thumbURL)
        collections = try c.decodeIfPresent([String].self, forKey: .collections) ?? []
        url = try c.decodeIfPresent(URL.self, forKey: .url)
    }
}

public struct LibraryCollection: Codable, Sendable, Equatable, Identifiable, Hashable {
    public let id: String
    public var name: String
    public var emoji: String?
    public var count: Int
    public var coverID: String?
    public var coverThumbURL: URL?
    enum CodingKeys: String, CodingKey { case id, name, emoji, count, coverID = "cover_id", coverThumbURL = "cover_thumb_url" }
    public init(id: String, name: String, emoji: String? = nil, count: Int = 0, coverID: String? = nil, coverThumbURL: URL? = nil) { self.id = id; self.name = name; self.emoji = emoji; self.count = count; self.coverID = coverID; self.coverThumbURL = coverThumbURL }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id); name = try c.decode(String.self, forKey: .name)
        emoji = try c.decodeIfPresent(String.self, forKey: .emoji); count = try c.decodeIfPresent(Int.self, forKey: .count) ?? 0
        coverID = try c.decodeIfPresent(String.self, forKey: .coverID)
        coverThumbURL = try c.decodeIfPresent(URL.self, forKey: .coverThumbURL)
    }
}

public struct LibrarySummary: Codable, Sendable, Equatable {
    public struct Year: Codable, Sendable, Equatable { public let year: Int; public let count: Int; public init(year: Int, count: Int) { self.year = year; self.count = count } }
    public struct Place: Codable, Sendable, Equatable { public let name: String; public let country: String?; public let count: Int
        public init(name: String, country: String?, count: Int) { self.name = name; self.country = country; self.count = count } }
    public var plan: String
    public var limitBytes: Int, usedBytes: Int, count: Int
    public var canUpgrade: Bool
    /// True when used > limit (a lapsed plan): uploads are refused, everything else works.
    public var readOnly: Bool
    public var years: [Year], places: [Place], collections: [LibraryCollection]
    enum CodingKeys: String, CodingKey { case plan, limitBytes = "limit_bytes", usedBytes = "used_bytes", count, canUpgrade = "can_upgrade", readOnly = "read_only", years, places, collections }
    public init(plan: String = "free", limitBytes: Int, usedBytes: Int, count: Int, canUpgrade: Bool = false, readOnly: Bool = false, years: [Year] = [], places: [Place] = [], collections: [LibraryCollection] = []) {
        self.plan = plan; self.limitBytes = limitBytes; self.usedBytes = usedBytes; self.count = count; self.canUpgrade = canUpgrade; self.readOnly = readOnly; self.years = years; self.places = places; self.collections = collections
    }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        plan = try c.decodeIfPresent(String.self, forKey: .plan) ?? "free"
        limitBytes = try c.decode(Int.self, forKey: .limitBytes); usedBytes = try c.decode(Int.self, forKey: .usedBytes)
        count = try c.decodeIfPresent(Int.self, forKey: .count) ?? 0
        canUpgrade = try c.decodeIfPresent(Bool.self, forKey: .canUpgrade) ?? false
        readOnly = try c.decodeIfPresent(Bool.self, forKey: .readOnly) ?? false
        years = try c.decodeIfPresent([Year].self, forKey: .years) ?? []
        places = try c.decodeIfPresent([Place].self, forKey: .places) ?? []
        collections = try c.decodeIfPresent([LibraryCollection].self, forKey: .collections) ?? []
    }
}

public struct UploadRequestItem: Codable, Sendable, Equatable {
    public var size: Int
    public var sha256: String
    public var taken: String?
    public var lat: Double?
    public var lon: Double?
    public init(size: Int, sha256: String, taken: String? = nil, lat: Double? = nil, lon: Double? = nil) { self.size = size; self.sha256 = sha256; self.taken = taken; self.lat = lat; self.lon = lon }
}

public struct UploadSlotResult: Codable, Sendable, Equatable {
    public enum Status: String, Codable, Sendable { case upload, duplicate, noSpace = "no_space", rejected, unknown
        public init(from d: Decoder) throws { self = Status(rawValue: (try? d.singleValueContainer().decode(String.self)) ?? "") ?? .unknown } }
    public let index: Int
    public let status: Status
    public let id: String?
    public let url: URL?
    public let fields: [String: String]?
    public let duplicateOf: String?
    public let reason: String?
    enum CodingKeys: String, CodingKey { case index, status, id, url, fields, duplicateOf = "duplicate_of", reason }
    public init(index: Int, status: Status, id: String? = nil, url: URL? = nil, fields: [String: String]? = nil, duplicateOf: String? = nil, reason: String? = nil) {
        self.index = index; self.status = status; self.id = id; self.url = url; self.fields = fields; self.duplicateOf = duplicateOf; self.reason = reason
    }
}

public struct UploadsResponse: Codable, Sendable, Equatable {
    public let uploads: [UploadSlotResult]
    public let usedBytes: Int, limitBytes: Int
    enum CodingKeys: String, CodingKey { case uploads, usedBytes = "used_bytes", limitBytes = "limit_bytes" }
    public init(uploads: [UploadSlotResult], usedBytes: Int, limitBytes: Int) { self.uploads = uploads; self.usedBytes = usedBytes; self.limitBytes = limitBytes }
}

/// `cursor` is opaque: it is stored and sent back exactly as received.
public struct ItemsPage: Codable, Sendable, Equatable {
    public let items: [LibraryPhoto]
    public let cursor: String?
    public init(items: [LibraryPhoto], cursor: String? = nil) { self.items = items; self.cursor = cursor }
}

public struct ItemsFilter: Sendable, Equatable {
    public var from: String?, to: String?, collection: String?, place: String?
    public init(from: String? = nil, to: String? = nil, collection: String? = nil, place: String? = nil) { self.from = from; self.to = to; self.collection = collection; self.place = place }
    /// A stable key for caching a first page.
    public var cacheKey: String { ["t", from, to, collection.map { "c-" + $0 }, place].compactMap { $0 }.joined(separator: "|") }
}

public struct DeleteResult: Codable, Sendable, Equatable {
    public let deleted: Int, usedBytes: Int
    enum CodingKeys: String, CodingKey { case deleted, usedBytes = "used_bytes" }
    public init(deleted: Int, usedBytes: Int) { self.deleted = deleted; self.usedBytes = usedBytes }
}

public struct SearchChip: Codable, Sendable, Equatable, Hashable {
    public let kind: String   // place | date | topic
    public let label: String
    public init(kind: String, label: String) { self.kind = kind; self.label = label }
}

public struct SearchUnderstood: Codable, Sendable, Equatable {
    public var text: String?, from: String?, to: String?
    public var places: [String]
    public var chips: [SearchChip]
    public init(text: String? = nil, from: String? = nil, to: String? = nil, places: [String] = [], chips: [SearchChip] = []) { self.text = text; self.from = from; self.to = to; self.places = places; self.chips = chips }
    public init(from d: Decoder) throws {
        let c = try d.container(keyedBy: CodingKeys.self)
        text = try c.decodeIfPresent(String.self, forKey: .text); from = try c.decodeIfPresent(String.self, forKey: .from); to = try c.decodeIfPresent(String.self, forKey: .to)
        places = try c.decodeIfPresent([String].self, forKey: .places) ?? []; chips = try c.decodeIfPresent([SearchChip].self, forKey: .chips) ?? []
    }
}

public struct SearchResponse: Codable, Sendable, Equatable {
    public let understood: SearchUnderstood
    public let items: [LibraryPhoto]
    public let mode: String   // timeline | semantic
    /// Timeline mode pages with this opaque cursor; semantic mode (by relevance, at most 100) has none.
    public let cursor: String?
    public init(understood: SearchUnderstood, items: [LibraryPhoto], mode: String = "timeline", cursor: String? = nil) { self.understood = understood; self.items = items; self.mode = mode; self.cursor = cursor }
}

/// Everything the library calls can fail with. `storageFull` is the 402 "nothing at all fits".
public enum LibraryAPIError: Error, Equatable, Sendable {
    case unauthorized, notFound, conflict, tooLarge, network, server
    case invalid(String)
    case rateLimited(retryAfter: Int?)
    case storageFull(usedBytes: Int, limitBytes: Int)

    public var message: String {
        switch self {
        case .unauthorized: "Your session expired. Please sign in again."
        case .notFound: "That photo is no longer in your library."
        case .conflict: "That changed in the meantime. Pull down to refresh and try again."
        case .tooLarge: "That photo is too large to upload."
        case .network: "No connection. Your photos are kept, and this continues when you are back online."
        case .server: "Something went wrong on our side. Please try again."
        case .invalid(let m): m
        case .rateLimited: "Too many requests right now. Please wait a moment and try again."
        case .storageFull: "Your storage is full. Free some space or choose a larger plan."
        }
    }
}
