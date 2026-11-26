import Foundation

/// Clearing the device after an accepted deletion (docs/ACCOUNT_DELETION.md section 3).
public enum LocalWipe {
    /// Removes everything inside each directory but keeps the directory itself (stores expect their folder to exist). Missing folders are fine.
    public static func clearContents(of directories: [URL], fileManager fm: FileManager = .default) {
        for dir in directories {
            guard let items = try? fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil) else { continue }
            for item in items { try? fm.removeItem(at: item) }
        }
    }

    /// Empties the app's whole preferences domain (drafts, remembered choices, per-person settings, every flag), then sets `keep`.
    /// The app has no setting that should outlive an account, so nothing else is spared.
    public static func resetDefaults(_ defaults: UserDefaults, domain: String, then keep: [String: Bool] = [:]) {
        defaults.removePersistentDomain(forName: domain)
        for (k, v) in keep { defaults.set(v, forKey: k) }
        defaults.synchronize()
    }
}

// MARK: - Fakes: debug builds (screenshots, UI tests) and unit tests. They never touch the network.

public enum FakeToken {
    /// An unsigned token with the claims the app reads. `authAge` is how long ago the person signed in.
    public static func make(sub: String = "demo-user", email: String = "demo@example.com", authAge: TimeInterval, now: Date = Date()) -> String {
        func b64(_ o: [String: Any]) -> String { ((try? JSONSerialization.data(withJSONObject: o)) ?? Data()).base64URLEncoded }
        let t = Int(now.timeIntervalSince1970)
        return "\(b64(["alg": "none"])).\(b64(["sub": sub, "email": email, "exp": t + 3000, "auth_time": t - Int(authAge)])).sig"
    }
}

/// Scripted answers, one per call; the last one repeats. Records the token of every call.
public final class FakeAccountAPI: AccountAPI, @unchecked Sendable {
    private let lock = NSLock()
    private var script: [Result<AppleLink, AccountError>]
    private var revoke: Result<URL, AccountError>
    private var _deleteTokens: [String] = []
    private var _revokeTokens: [String] = []
    private let delay: Duration?

    public init(_ script: [Result<AppleLink, AccountError>] = [.success(.notLinked)],
                revoke: Result<URL, AccountError> = .success(URL(string: "https://appleid.apple.com/auth/authorize?fake=1")!), delay: Duration? = nil) {
        self.script = script; self.revoke = revoke; self.delay = delay
    }
    public var deleteTokens: [String] { lock.withLock { _deleteTokens } }
    public var revokeTokens: [String] { lock.withLock { _revokeTokens } }

    public func deleteAccount(idToken: String) async throws -> AppleLink {
        if let delay { try await Task.sleep(for: delay) }
        let next: Result<AppleLink, AccountError> = lock.withLock {
            _deleteTokens.append(idToken)
            return script.count > 1 ? script.removeFirst() : (script.first ?? .failure(.server))
        }
        return try next.get()
    }

    public func appleRevokeURL(idToken: String) async throws -> URL {
        lock.withLock { _revokeTokens.append(idToken) }
        return try revoke.get()
    }
}

/// A session with a chosen sign-in age. `reauthenticate` mints a fresh token (or throws `reauthError`).
public final class FakeDeletionAuth: DeletionAuth, @unchecked Sendable {
    private let lock = NSLock()
    private var token: String
    private let sub: String
    private let reauthError: Error?
    private var _reauths = 0
    private var _signedOut = false
    private let delay: Duration?

    public init(sub: String = "demo-user", authAge: TimeInterval, reauthError: Error? = nil, delay: Duration? = nil) {
        self.sub = sub; self.reauthError = reauthError; self.delay = delay
        token = FakeToken.make(sub: sub, authAge: authAge)
    }
    public var reauthCount: Int { lock.withLock { _reauths } }
    /// Simulates the server having revoked the session (what an accepted deletion does).
    public func revokeSession() { lock.withLock { _signedOut = true } }
    public var currentToken: String { lock.withLock { token } }

    public func authorization() async throws -> (idToken: String, userID: String) {
        try lock.withLock { if _signedOut { throw AuthError.signedOut }; return (token, sub) }
    }

    public func reauthenticate(expectedSub: String) async throws {
        if let delay { try await Task.sleep(for: delay) }
        lock.withLock { _reauths += 1 }
        if let reauthError { throw reauthError }
        lock.withLock { token = FakeToken.make(sub: sub, authAge: 1) }
    }
}
