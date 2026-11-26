import Foundation
import Observation

// "Send feedback" (docs/FEEDBACK.md). Contract: POST /users/{userId}/feedback with
// {"text","kind":"idea|problem|other" (optional),"app":"ios","version","locale":"en|es","context":"settings|after_video|rating_prompt"}
// -> 202 {"ok":true}, 400 invalid, 429 rate limited.

public enum FeedbackKind: String, CaseIterable, Sendable { case idea, problem, other }

public enum FeedbackContext: String, Sendable { case settings, afterVideo = "after_video", ratingPrompt = "rating_prompt" }

public enum FeedbackRules {
    public static let minLength = 3
    public static let maxLength = 2000
    public static func trimmed(_ s: String) -> String { s.trimmingCharacters(in: .whitespacesAndNewlines) }
    /// 3...2000 characters after trimming. The server checks the same range.
    public static func isValid(_ s: String) -> Bool { (minLength...maxLength).contains(trimmed(s).count) }
    /// What the field keeps: never more than the maximum (a long paste is cut, not refused).
    public static func clamp(_ s: String) -> String { s.count > maxLength ? String(s.prefix(maxLength)) : s }
}

public struct FeedbackRequest: Equatable, Sendable {
    public let text: String
    public let kind: FeedbackKind?
    public let version: String
    public let locale: String
    public let context: FeedbackContext
    public init(text: String, kind: FeedbackKind?, version: String, locale: String, context: FeedbackContext) {
        self.text = text; self.kind = kind; self.version = version; self.locale = locale; self.context = context
    }
    public var json: [String: Any] {
        var f: [String: Any] = ["text": text, "app": "ios", "version": version, "locale": locale, "context": context.rawValue]
        if let kind { f["kind"] = kind.rawValue }
        return f
    }
}

public enum FeedbackError: Error, Equatable, Sendable {
    case network, rateLimited, invalid, unauthorized, server

    /// Plain words. Every one says the message is still on the phone (the text is never cleared by a failure).
    public var message: String {
        switch self {
        case .network: tr("feedback.err.network")
        case .rateLimited: tr("feedback.err.rate_limited")
        case .invalid: tr("feedback.err.invalid")
        case .unauthorized: tr("feedback.err.unauthorized")
        case .server: tr("feedback.err.server")
        }
    }
}

public protocol FeedbackAPI: Sendable { func sendFeedback(_ request: FeedbackRequest) async throws }

extension APIClient: FeedbackAPI {
    public func sendFeedback(_ request: FeedbackRequest) async throws {
        let body = try JSONSerialization.data(withJSONObject: request.json)
        let http: HTTPURLResponse
        do { (_, http) = try await perform("POST", ["feedback"], body: body) }
        catch is CancellationError { throw CancellationError() }
        catch let e as APIError { throw e == .unauthorized ? FeedbackError.unauthorized : FeedbackError.network }
        catch { throw FeedbackError.network }
        switch http.statusCode {
        case 200..<300: return
        case 400: throw FeedbackError.invalid
        case 401, 403: throw FeedbackError.unauthorized
        case 429: throw FeedbackError.rateLimited
        default: throw FeedbackError.server
        }
    }
}

/// The unsent message, kept on the phone so a failure, a dismissed sheet or a restart never loses what the person typed. Cleared on success.
public struct FeedbackDraftStore: Sendable {
    public static let key = "vmk.feedback.draft"
    nonisolated(unsafe) private let defaults: UserDefaults
    public init(defaults: UserDefaults = .standard) { self.defaults = defaults }
    public var text: String { get { defaults.string(forKey: Self.key) ?? "" } nonmutating set { newValue.isEmpty ? defaults.removeObject(forKey: Self.key) : defaults.set(newValue, forKey: Self.key) } }
}

/// The sheet's logic: field, kind chips, sending and the three end states. UI-free, tested with a fake API.
@MainActor @Observable public final class FeedbackComposer {
    public enum Phase: Equatable { case editing, sending, sent, failed(FeedbackError) }

    public var text: String { didSet { if text != oldValue { text = FeedbackRules.clamp(text); drafts.text = text } } }
    public var kind: FeedbackKind?
    public private(set) var phase: Phase = .editing
    public let context: FeedbackContext
    private let api: (any FeedbackAPI)?
    private let drafts: FeedbackDraftStore
    private let version: String
    private let locale: @Sendable () -> String

    public init(context: FeedbackContext, api: (any FeedbackAPI)?, version: String, drafts: FeedbackDraftStore = FeedbackDraftStore(),
                locale: @escaping @Sendable () -> String = { Localization.shared.headerValue }) {
        self.context = context; self.api = api; self.version = version; self.drafts = drafts; self.locale = locale
        text = drafts.text
    }

    public var count: Int { text.count }
    public var canSend: Bool { FeedbackRules.isValid(text) && phase != .sending && phase != .sent }
    public var isSending: Bool { phase == .sending }
    /// Chips toggle: tapping the chosen one clears it (the kind is optional).
    public func choose(_ k: FeedbackKind) { kind = kind == k ? nil : k }

    public func send() async {
        guard canSend else { return }
        guard let api else { phase = .failed(.server); return }
        phase = .sending
        let r = FeedbackRequest(text: FeedbackRules.trimmed(text), kind: kind, version: version, locale: locale(), context: context)
        do {
            try await api.sendFeedback(r)
            drafts.text = ""; phase = .sent
        } catch let e as FeedbackError { phase = .failed(e) }
        catch { phase = .failed(.network) }
    }
}
