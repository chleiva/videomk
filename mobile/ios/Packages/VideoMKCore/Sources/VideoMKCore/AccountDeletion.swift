import Foundation

// In-app account deletion (App Store guideline 5.1.1(v)). The contract is docs/ACCOUNT_DELETION.md; section numbers below refer to it.

/// What the server says about the person's Sign in with Apple grant (section 4). Anything unrecognised is `.unknown`.
public enum AppleLink: String, Sendable, Equatable {
    case notLinked = "not_linked", revokeAvailable = "revoke_available", revokeOff = "revoke_off", unknown
    init(server: String?) { self = server.flatMap(AppleLink.init(rawValue:)) ?? .unknown }
}

public enum AccountError: Error, Equatable, Sendable {
    case signedOut                  // no usable session (nothing was sent)
    case reauthRequired             // 401 reauth_required: the sign-in is older than 10 minutes (handled inside the flow)
    case sessionExpired             // the server refused the token itself
    case reauthCancelled            // the person closed the sign-in page (nothing was sent)
    case reauthFailed               // the sign-in page or the token exchange failed (nothing was sent)
    case wrongAccount               // they signed in as somebody else (nothing was sent, this session is untouched)
    case reauthNotAccepted          // signed in again, but the server still calls the sign-in too old
    case forbidden                  // 403
    case requestRejected            // 400
    case server                     // 5xx: nothing was started
    case network                    // the request never left or no answer came back before it was sent
    case uncertain                  // the request was sent and no answer came back: it may have been accepted
    case revokeUnavailable          // the Apple step could not be started

    /// Plain words for the person. Never server text.
    public var message: String {
        switch self {
        case .signedOut: tr("del.err.signed_out")
        case .reauthRequired: tr("del.err.reauth_required")
        case .sessionExpired: tr("del.err.session_expired")
        case .reauthCancelled: tr("del.err.reauth_cancelled")
        case .reauthFailed: tr("del.err.reauth_failed")
        case .wrongAccount: tr("del.err.wrong_account")
        case .reauthNotAccepted: tr("del.err.reauth_not_accepted")
        case .forbidden: tr("del.err.forbidden")
        case .requestRejected: tr("del.err.request_rejected")
        case .server: tr("del.err.server")
        case .network: tr("del.err.network")
        case .uncertain: tr("del.err.uncertain")
        case .revokeUnavailable: tr("del.err.revoke_unavailable")
        }
    }

    /// Cases where emailing support is a useful next step, so the screen offers the address.
    public var offersEmail: Bool { self == .reauthNotAccepted || self == .requestRejected }
}

/// The app's whole account API. Only the signed-in person's own `sub` (read from the token that is sent) ever goes in the path.
public protocol AccountAPI: Sendable {
    func deleteAccount(idToken: String) async throws -> AppleLink
    func appleRevokeURL(idToken: String) async throws -> URL
}

public struct AccountClient: AccountAPI {
    private let config: AppConfig
    private let session: URLSession
    private let appVersion: String

    public init(config: AppConfig, session: URLSession = .shared, appVersion: String = "0") {
        self.config = config; self.session = session; self.appVersion = appVersion
    }

    public func deleteAccount(idToken: String) async throws -> AppleLink {
        let (data, http) = try await post(idToken, "delete", ["confirm": "DELETE"])
        switch http.statusCode {
        case 200..<300:
            // Accepted. A body we cannot read still means accepted: the Apple step is then unknown.
            let apple = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["apple"] as? String
            return AppleLink(server: apple)
        case 401:
            let code = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["code"] as? String
            throw code == "reauth_required" ? AccountError.reauthRequired : AccountError.sessionExpired
        case 403: throw AccountError.forbidden
        case 400: throw AccountError.requestRejected
        default: throw AccountError.server
        }
    }

    public func appleRevokeURL(idToken: String) async throws -> URL {
        let (data, http) = try await post(idToken, "apple-revoke", ["return": "app"])
        guard http.statusCode == 200,
              let s = (try? JSONSerialization.jsonObject(with: data) as? [String: Any])?["authorize_url"] as? String,
              let url = AppleRevoke.safeAuthorizeURL(s) else { throw AccountError.revokeUnavailable }
        return url
    }

    private func post(_ token: String, _ action: String, _ body: [String: String]) async throws -> (Data, HTTPURLResponse) {
        guard let sub = JWT.subject(token), !sub.isEmpty else { throw AccountError.signedOut }
        let url = config.apiBase.appendingPathComponent("users").appendingPathComponent(sub).appendingPathComponent("account").appendingPathComponent(action)
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.httpMethod = "POST"
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("ios", forHTTPHeaderField: "X-Platform")
        req.setValue(appVersion, forHTTPHeaderField: "X-App-Version")
        req.setValue(Localization.shared.headerValue, forHTTPHeaderField: "X-Locale")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        do {
            let (data, resp) = try await session.data(for: req)
            guard let http = resp as? HTTPURLResponse else { throw AccountError.server }
            return (data, http)
        } catch let e as AccountError { throw e }
        catch is CancellationError { throw CancellationError() }
        catch { throw action == "delete" ? AccountError.uncertain : AccountError.network }
    }
}

// MARK: - Apple revocation (section 4)

public enum AppleRevoke {
    /// Only Apple's own sign-in page is ever opened for this step.
    public static func safeAuthorizeURL(_ s: String) -> URL? {
        guard let u = URL(string: s), u.scheme == "https", u.host == "appleid.apple.com" else { return nil }
        return u
    }

    public enum Status: String, Sendable, Equatable { case ok, cancelled, mismatch, failed, invalid }

    /// `com.videomk.app://auth/apple-revoked?status=<s>`. Anything else (wrong host or path, unknown status) counts as `failed`.
    public static func status(of url: URL, scheme: String = "com.videomk.app") -> Status {
        guard url.scheme == scheme, url.host == "auth", url.path == "/apple-revoked",
              let raw = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "status" })?.value,
              let s = Status(rawValue: raw) else { return .failed }
        return s
    }

    public static var manualSteps: String { tr("del.manual_steps") }
}

// MARK: - The flow

public enum DeletionStage: Sendable, Equatable { case checking, signingIn, sending }

public struct DeletionAccepted: Sendable, Equatable {
    public let apple: AppleLink
    /// The token that was accepted, kept in memory only for the Apple step (valid about an hour). Nil when the outcome is assumed.
    public let idToken: String?
    /// True when the request was sent earlier, its answer was lost, and the session has since been switched off by the server:
    /// the only way that happens is the deletion having started.
    public let assumed: Bool
}

/// What the flow needs from the sign-in layer. `reauthenticate` runs the interactive sequence of section 2 and, on success, leaves the NEW tokens stored
/// (and only if they belong to `expectedSub`).
public protocol DeletionAuth: Sendable {
    func authorization() async throws -> (idToken: String, userID: String)
    func reauthenticate(expectedSub: String) async throws
}

public struct AccountDeletionFlow: Sendable {
    /// The server accepts a sign-in at most this old (`max_age_seconds` of the 401).
    public static let maxAge: TimeInterval = 600
    /// A token this close to the limit is treated as stale, so it cannot cross the line while the request is on the way.
    public static let margin: TimeInterval = 60

    private let auth: any DeletionAuth
    private let api: any AccountAPI
    private let now: @Sendable () -> Date

    public init(auth: any DeletionAuth, api: any AccountAPI, now: @escaping @Sendable () -> Date = { Date() }) {
        self.auth = auth; self.api = api; self.now = now
    }

    /// The typed confirmation: the word of the app language (DELETE, ELIMINAR) or the other one; case and edge spaces do not matter.
    public static func isConfirmation(_ typed: String) -> Bool {
        ["DELETE", "ELIMINAR"].contains(typed.trimmingCharacters(in: .whitespaces).uppercased())
    }

    public static func isRecent(_ idToken: String, now: Date) -> Bool {
        guard let t = JWT.authTime(idToken) else { return false }
        let age = now.timeIntervalSince(t)
        return age >= -margin && age <= maxAge - margin
    }

    /// Never changes anything local: the caller clears the device only after this returns. Whatever it throws, the person is still signed in
    /// (a re-authentication that fails or is cancelled leaves the stored tokens as they were).
    /// - Parameter outcomeUnknown: a previous attempt was sent and its answer never came. The retry goes straight to the server (a repeat
    ///   is harmless and needs no new sign-in, section 1) and only signs in again if the server asks.
    public func run(outcomeUnknown: Bool = false, stage: @MainActor (DeletionStage) -> Void) async throws -> DeletionAccepted {
        await stage(.checking)
        var token: String, sub: String
        do { (token, sub) = try await authorize() }
        catch AccountError.signedOut where outcomeUnknown {
            return DeletionAccepted(apple: .unknown, idToken: nil, assumed: true)
        }

        var signedInAgain = false
        func reauth() async throws {
            await stage(.signingIn)
            do { try await auth.reauthenticate(expectedSub: sub) }
            catch AuthError.cancelled { throw AccountError.reauthCancelled }
            catch AuthError.wrongAccount { throw AccountError.wrongAccount }
            catch is CancellationError { throw CancellationError() }
            catch { throw AccountError.reauthFailed }
            let fresh = try await authorize()
            guard fresh.sub == sub else { throw AccountError.wrongAccount }
            token = fresh.token; signedInAgain = true
        }

        if !outcomeUnknown, !Self.isRecent(token, now: now()) { try await reauth() }   // up front, so a stale token never surprises the person with a failure

        await stage(.sending)
        do { return DeletionAccepted(apple: try await api.deleteAccount(idToken: token), idToken: token, assumed: false) }
        catch AccountError.reauthRequired {
            if signedInAgain { throw AccountError.reauthNotAccepted }       // the sign-in was reused: ask the person to try again, once
            try await reauth()
            await stage(.sending)
            do { return DeletionAccepted(apple: try await api.deleteAccount(idToken: token), idToken: token, assumed: false) }
            catch AccountError.reauthRequired { throw AccountError.reauthNotAccepted }
        }
    }

    private func authorize() async throws -> (token: String, sub: String) {
        do {
            let a = try await auth.authorization()
            return (a.idToken, a.userID)
        }
        catch AuthError.signedOut { throw AccountError.signedOut }
        catch is CancellationError { throw CancellationError() }
        catch { throw AccountError.network }
    }
}
