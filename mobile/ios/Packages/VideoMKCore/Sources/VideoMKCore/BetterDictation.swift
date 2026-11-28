import Foundation

// "Better dictation" (Pro and Max): the phone records a clip, the server turns it into text. Pure rules and the request live here (tested without a microphone);
// the recorder and the screen are in the app target. docs/SPEECH_TO_TEXT_2026-11-28.md sections 9 and 10, docs/BETTER_DICTATION_CLIENTS_2026-11-28.md.
// Nothing here logs or stores audio.

/// `capabilities.dictation`.
public struct DictationCapabilities: Sendable, Equatable {
    public static let hardMaxSeconds = 360.0
    public static let hardMaxBytes = 3 * 1024 * 1024
    public var premium: Bool, available: Bool, paused: Bool
    public var secondsLeft: Int?
    public var maxClipSeconds: Double
    public var maxClipBytes: Int
    public var requiresPlan: String?

    public init(premium: Bool = false, available: Bool = false, paused: Bool = false, secondsLeft: Int? = nil, maxClipSeconds: Double = hardMaxSeconds, maxClipBytes: Int = hardMaxBytes, requiresPlan: String? = nil) {
        self.premium = premium; self.available = available; self.paused = paused; self.secondsLeft = secondsLeft
        self.maxClipSeconds = min(maxClipSeconds, Self.hardMaxSeconds); self.maxClipBytes = min(maxClipBytes, Self.hardMaxBytes); self.requiresPlan = requiresPlan
    }

    /// Lenient: anything that is not a JSON object is "not offered".
    public init?(json: AnyJSON?) {
        guard case .object(let o)? = json else { return nil }
        func num(_ k: String) -> Double? { if case .number(let n)? = o[k] { return n }; return nil }
        func flag(_ k: String) -> Bool { if case .bool(let b)? = o[k] { return b }; return false }
        var plan: String? { if case .string(let p)? = o["requires_plan"] { return p }; return nil }
        self.init(premium: flag("premium"), available: flag("available"), paused: flag("paused"), secondsLeft: num("seconds_left_today").map { Int($0) },
                  maxClipSeconds: num("max_clip_seconds").flatMap { $0 > 0 ? $0 : nil } ?? Self.hardMaxSeconds,
                  maxClipBytes: num("max_clip_bytes").flatMap { $0 > 0 ? Int($0) : nil } ?? Self.hardMaxBytes, requiresPlan: plan)
    }

    /// Better dictation can be used now: the plan has it, it is not paused, seconds are left.
    public var isUsable: Bool { available && !paused }
    /// The Options sheet shows the small "Better dictation with Pro" line: the plan lacks it and says which plan has it. Never when the plan has it.
    public var showsUpgradeHint: Bool { !premium && requiresPlan != nil }
}

/// The person's choice in Options (default on).
public enum BetterDictationPreference {
    public static let key = "vmk.better_dictation"
    public static func isOn(_ defaults: UserDefaults = .standard) -> Bool { defaults.object(forKey: key) as? Bool ?? true }
    public static func set(_ on: Bool, _ defaults: UserDefaults = .standard) { defaults.set(on, forKey: key) }
    /// The mic uses Better dictation: offered by the server, wanted by the person.
    public static func uses(_ caps: DictationCapabilities?, preferred: Bool) -> Bool { preferred && (caps?.isUsable ?? false) }
}

/// Every id that produced text, sent as `dictation_ids` on the next create: at most 20 (the newest are kept), no repeats, only 32 hex characters.
public struct DictationIDs: Sendable, Equatable {
    public static let maximum = 20
    public private(set) var list: [String] = []
    public init() {}
    public mutating func add(_ id: String) {
        guard id.count == 32, id.allSatisfy(\.isHexDigit), !list.contains(id) else { return }
        list.append(id)
        if list.count > Self.maximum { list.removeFirst(list.count - Self.maximum) }
    }
    public mutating func clear() { list = [] }
}

/// Where the better text goes: `base` is the field when recording started, `native` what the live preview last wrote (the field held exactly that).
/// Field unchanged since: the dictated span is replaced by the better text on top of the base (words are not doubled). Edited by hand meanwhile: the person's
/// text wins (nil = write nothing); the id is still kept, the clip was paid. No preview: a plain append. Blank text: nil.
public func placeBetterText(base: String, native: String, field: String, better: String) -> String? {
    guard !better.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, field == native else { return nil }
    return DictationText.compose(base, better)
}

public enum BetterDictationFailure: Error, Sendable, Equatable {
    case plan, quota, tooLong, failed, paused, badAudio, auth, network

    /// What the server answered (pure).
    public static func from(status: Int, body: Data?) -> BetterDictationFailure {
        let o = body.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
        switch o?["code"] as? String {
        case "dictation_plan": return .plan
        case "dictation_quota": return .quota
        case "dictation_too_long": return .tooLong
        case "dictation_paused": return .paused
        case "bad_audio": return .badAudio
        default: break
        }
        switch status {
        case 429: return .quota
        case 413: return .tooLong
        case 503: return .paused
        case 401, 403: return .auth
        default: return .failed
        }
    }

    /// The line to show (a string-table key); nil = fall back silently (the person did nothing wrong and nothing useful can be said).
    public var messageKey: String? {
        switch self {
        case .quota: "better.quota"
        case .tooLong: "better.limit"
        case .failed, .network, .badAudio: "better.failed"
        case .plan, .paused, .auth: nil
        }
    }
}

public struct DictationClip: Sendable, Equatable {
    public var audio: Data, mime: String, seconds: Double, languages: [String], prompt: String?
    public init(audio: Data, mime: String = "audio/mp4", seconds: Double, languages: [String], prompt: String? = nil) {
        self.audio = audio; self.mime = mime; self.seconds = seconds; self.languages = languages; self.prompt = prompt
    }
    /// The JSON body: base64 audio, `mime`, `seconds` (one decimal), `languages` (at most 4), `prompt` (the last 400 characters of the draft, when there is one).
    public func body() throws -> Data {
        var f: [String: Any] = ["audio": audio.base64EncodedString(), "mime": mime, "seconds": (seconds * 10).rounded() / 10, "languages": Array(languages.prefix(4))]
        if let p = prompt?.trimmingCharacters(in: .whitespacesAndNewlines), !p.isEmpty { f["prompt"] = String(p.suffix(400)) }
        return try JSONSerialization.data(withJSONObject: f)
    }
}

public struct DictationAnswer: Sendable, Equatable {
    public let id: String, text: String, seconds: Double, secondsLeft: Int?
    public init(id: String, text: String, seconds: Double = 0, secondsLeft: Int? = nil) { self.id = id; self.text = text; self.seconds = seconds; self.secondsLeft = secondsLeft }
    public static func decode(_ data: Data) -> DictationAnswer? {
        guard let o = try? JSONSerialization.jsonObject(with: data) as? [String: Any], let id = o["id"] as? String, let text = o["text"] as? String else { return nil }
        return DictationAnswer(id: id, text: text, seconds: (o["seconds"] as? NSNumber)?.doubleValue ?? 0, secondsLeft: (o["seconds_left_today"] as? NSNumber)?.intValue)
    }
}

public protocol DictationServing: Sendable {
    func dictate(_ clip: DictationClip) async -> Result<DictationAnswer, BetterDictationFailure>
}

extension APIClient: DictationServing {
    /// POST /users/{id}/dictation. Never throws: every failure is a typed result and the caller falls back to the native text.
    public func dictate(_ clip: DictationClip) async -> Result<DictationAnswer, BetterDictationFailure> {
        guard let body = try? clip.body() else { return .failure(BetterDictationFailure.failed) }
        do {
            let (data, http) = try await perform("POST", ["dictation"], body: body)
            if (200..<300).contains(http.statusCode), let a = DictationAnswer.decode(data) { return .success(a) }
            return .failure(BetterDictationFailure.from(status: http.statusCode, body: data))
        } catch { return .failure(BetterDictationFailure.network) }
    }
}

/// What to do when a clip's upload ends, pure: the text to write (nil = leave the field), the id to remember (only when text came back) and the line to say (a string-table key).
/// Any failure leaves the field exactly as the native engine wrote it. `limitHit`: the recording was stopped by the 6 minute limit, which the person is told either way.
public struct BetterDictationResolution: Equatable, Sendable {
    public var write: String?, id: String?, noteKey: String?
    public static func resolve(base: String, native: String, field: String, result: Result<DictationAnswer, BetterDictationFailure>, limitHit: Bool) -> BetterDictationResolution {
        switch result {
        case .success(let a):
            let hasText = !a.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            return BetterDictationResolution(write: placeBetterText(base: base, native: native, field: field, better: a.text), id: hasText ? a.id : nil, noteKey: limitHit ? "better.limit" : nil)
        case .failure(let f):
            return BetterDictationResolution(write: nil, id: nil, noteKey: f == .quota ? "better.quota" : limitHit ? "better.limit" : f.messageKey)
        }
    }
}
