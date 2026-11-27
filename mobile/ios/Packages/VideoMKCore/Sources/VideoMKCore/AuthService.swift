import Foundation

public enum AuthError: Error, Equatable, Sendable {
    case signedOut
    case cancelled
    case failed
    case accountLinkRetry   // Cognito's one-off "Already found an entry for username" after an account link
    case wrongAccount       // a re-authentication ended in a different account than the one signed in
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

    /// `language` ("en", "es") is passed to the hosted pages as `lang`, so the email sign-in page speaks the app's language (the providers' own pages follow the phone).
    public func beginSignIn(provider: SocialProvider? = nil, language: String? = nil) -> URL {
        let pkce = PKCE.generate()
        let state = PKCE.generate().verifier
        pending = (pkce, state)
        var c = URLComponents(url: config.authDomain.appendingPathComponent("oauth2/authorize"), resolvingAgainstBaseURL: false)!
        c.queryItems = [
            .init(name: "response_type", value: "code"), .init(name: "client_id", value: config.clientID),
            .init(name: "redirect_uri", value: config.redirectURI), .init(name: "scope", value: "openid email profile"),
            .init(name: "state", value: state), .init(name: "code_challenge_method", value: "S256"), .init(name: "code_challenge", value: pkce.challenge),
        ]
        if let provider { c.queryItems?.append(.init(name: "identity_provider", value: provider.rawValue)) }
        if let language, !language.isEmpty { c.queryItems?.append(.init(name: "lang", value: language)) }
        return c.url!
    }

    // MARK: re-authentication (account deletion)

    /// Hosted-UI sign-out (ends the browser session only: the tokens held by the app are untouched). `docs/ACCOUNT_DELETION.md` section 2, step 1.
    public func logoutURL() -> URL {
        var c = URLComponents(url: config.authDomain.appendingPathComponent("logout"), resolvingAgainstBaseURL: false)!
        c.queryItems = [.init(name: "client_id", value: config.clientID), .init(name: "logout_uri", value: config.signOutURI)]
        return c.url!
    }

    /// A normal authorize request plus `prompt=login&max_age=0` (ignored by the classic hosted UI, correct under managed login). Section 2, step 3.
    public func beginReauth() -> URL {
        var c = URLComponents(url: beginSignIn(), resolvingAgainstBaseURL: false)!
        c.queryItems = (c.queryItems ?? []) + [.init(name: "prompt", value: "login"), .init(name: "max_age", value: "0")]
        return c.url!
    }

    /// Exchanges the code like a sign-in, but saves the new tokens ONLY when they belong to `expectedSub`: signing in as somebody else must not replace this session.
    public func completeReauth(callback: URL, expectedSub: String) async throws {
        let t = try await exchange(callback: callback)
        guard JWT.subject(t.idToken) == expectedSub else { throw AuthError.wrongAccount }
        store.save(t)
    }

    public func completeSignIn(callback: URL) async throws {
        store.save(try await exchange(callback: callback))
    }

    private func exchange(callback: URL) async throws -> Tokens {
        guard let pending else { throw AuthError.failed }
        self.pending = nil
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        func item(_ n: String) -> String? { items.first { $0.name == n }?.value }
        guard item("state") == pending.state else { throw AuthError.failed }   // every callback needs our state, errors included
        if let error = item("error") {
            let description = item("error_description") ?? ""
            if description.contains(SignInFlow.linkQuirk) { throw AuthError.accountLinkRetry }
            if error == "access_denied" || description.lowercased().contains("cancel") { throw AuthError.cancelled }
            throw AuthError.failed
        }
        guard let code = item("code") else { throw AuthError.failed }
        return try await tokenRequest(["grant_type": "authorization_code", "client_id": config.clientID, "code": code,
                                       "redirect_uri": config.redirectURI, "code_verifier": pending.pkce.verifier], previous: nil)
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
