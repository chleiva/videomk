import Foundation

public enum AuthError: Error, Equatable, Sendable {
    case signedOut
    case cancelled
    case failed
}

/// Cognito hosted UI with authorization code + PKCE. The system browser sheet is driven by the app (it needs a window);
/// this type builds the URL, exchanges the code, stores and refreshes tokens.
public actor AuthService: AuthorizationProviding {
    private let config: AppConfig
    private let store: any TokenStore
    private let session: URLSession
    private var refreshTask: Task<Tokens, Error>?
    private var pending: (pkce: PKCE, state: String)?

    public init(config: AppConfig, store: any TokenStore, session: URLSession = .shared) {
        self.config = config; self.store = store; self.session = session
    }

    public var isSignedIn: Bool { store.load() != nil }
    public var email: String? { store.load().flatMap { JWT.email($0.idToken) } }

    // MARK: sign in

    public func beginSignIn() -> URL {
        let pkce = PKCE.generate()
        let state = PKCE.generate().verifier
        pending = (pkce, state)
        var c = URLComponents(url: config.authDomain.appendingPathComponent("oauth2/authorize"), resolvingAgainstBaseURL: false)!
        c.queryItems = [
            .init(name: "response_type", value: "code"), .init(name: "client_id", value: config.clientID),
            .init(name: "redirect_uri", value: config.redirectURI), .init(name: "scope", value: "openid email profile"),
            .init(name: "state", value: state), .init(name: "code_challenge_method", value: "S256"), .init(name: "code_challenge", value: pkce.challenge),
        ]
        return c.url!
    }

    public func completeSignIn(callback: URL) async throws {
        guard let pending else { throw AuthError.failed }
        self.pending = nil
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func item(_ n: String) -> String? { items.first { $0.name == n }?.value }
        if item("error") != nil { throw AuthError.cancelled }
        guard let code = item("code"), item("state") == pending.state else { throw AuthError.failed }
        let t = try await tokenRequest(["grant_type": "authorization_code", "client_id": config.clientID, "code": code,
                                        "redirect_uri": config.redirectURI, "code_verifier": pending.pkce.verifier], previous: nil)
        store.save(t)
    }

    public func signOut() { pending = nil; store.clear() }

    /// For automated tests and QA builds only: seed a session from tokens obtained out of band.
    public func seed(_ tokens: Tokens) { store.save(tokens) }

    // MARK: AuthorizationProviding

    public func authorization() async throws -> (idToken: String, userID: String) {
        guard var t = store.load() else { throw AuthError.signedOut }
        if t.expiresAt.timeIntervalSinceNow < 120 { t = try await refreshed(t) }
        guard let sub = JWT.subject(t.idToken) else { throw AuthError.failed }
        return (t.idToken, sub)
    }

    private func refreshed(_ old: Tokens) async throws -> Tokens {
        if let refreshTask { return try await refreshTask.value }  // one refresh in flight at a time
        guard let rt = old.refreshToken else { signOut(); throw AuthError.signedOut }
        let task = Task { try await tokenRequest(["grant_type": "refresh_token", "client_id": config.clientID, "refresh_token": rt], previous: old) }
        refreshTask = task
        defer { refreshTask = nil }
        do {
            let t = try await task.value
            store.save(t)
            return t
        } catch AuthError.signedOut {  // refresh token revoked or expired
            signOut(); throw AuthError.signedOut
        }
    }

    private func tokenRequest(_ params: [String: String], previous: Tokens?) async throws -> Tokens {
        var req = URLRequest(url: config.authDomain.appendingPathComponent("oauth2/token"), timeoutInterval: 30)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        var form = URLComponents()
        form.queryItems = params.map { URLQueryItem(name: $0.key, value: $0.value) }
        req.httpBody = form.percentEncodedQuery?.data(using: .utf8)
        let data: Data, resp: URLResponse
        do { (data, resp) = try await session.data(for: req) } catch { throw AuthError.failed }
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if status == 400, previous != nil { throw AuthError.signedOut }
        guard status == 200, let j = try? JSONDecoder().decode(TokenResponse.self, from: data) else { throw AuthError.failed }
        return Tokens(idToken: j.idToken, accessToken: j.accessToken, refreshToken: j.refreshToken ?? previous?.refreshToken,
                      expiresAt: Date().addingTimeInterval(TimeInterval(j.expiresIn)))
    }

    private struct TokenResponse: Decodable {
        let idToken: String, accessToken: String, refreshToken: String?, expiresIn: Int
        enum CodingKeys: String, CodingKey { case idToken = "id_token", accessToken = "access_token", refreshToken = "refresh_token", expiresIn = "expires_in" }
    }
}
