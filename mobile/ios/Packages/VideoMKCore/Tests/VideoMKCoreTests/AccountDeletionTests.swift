import Foundation
import Testing
@testable import VideoMKCore

/// Own stub (the shared one belongs to CoreTests' serial suite).
final class AccountStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: (@Sendable (URLRequest) throws -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let (code, data) = try Self.handler?(request) ?? (500, Data())
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}
private func accountSession() -> URLSession {
    let c = URLSessionConfiguration.ephemeral
    c.protocolClasses = [AccountStub.self]
    return URLSession(configuration: c)
}
private func bodyData(_ r: URLRequest) -> Data {
    if let b = r.httpBody { return b }
    guard let s = r.httpBodyStream else { return Data() }
    s.open(); defer { s.close() }
    var out = Data(); var buf = [UInt8](repeating: 0, count: 1024)
    while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; out.append(buf, count: n) }
    return out
}

private let minute: TimeInterval = 60

final class StageLog: @unchecked Sendable {
    private let lock = NSLock(); private var items: [DeletionStage] = []
    func add(_ s: DeletionStage) { lock.withLock { items.append(s) } }
    var all: [DeletionStage] { lock.withLock { items } }
}

private func run(_ flow: AccountDeletionFlow, unknown: Bool = false) async throws -> (DeletionAccepted, [DeletionStage]) {
    let log = StageLog()
    let r = try await flow.run(outcomeUnknown: unknown) { log.add($0) }
    return (r, log.all)
}
private func errorOf(_ flow: AccountDeletionFlow, unknown: Bool = false) async -> AccountError? {
    do { _ = try await run(flow, unknown: unknown); return nil } catch { return error as? AccountError }
}

@Suite struct AccountDeletionFlowTests {
    @Test func aFreshSignInSendsStraightAway() async throws {
        let auth = FakeDeletionAuth(authAge: 30), api = FakeAccountAPI([.success(.notLinked)])
        let (r, stages) = try await run(AccountDeletionFlow(auth: auth, api: api))
        #expect(r.apple == .notLinked && !r.assumed && r.idToken == auth.currentToken)
        #expect(auth.reauthCount == 0 && api.deleteTokens == [auth.currentToken])
        #expect(stages == [.checking, .sending])
    }

    @Test func aStaleSignInIsRenewedBeforeTheRequestAndTheNewTokenIsSent() async throws {
        let auth = FakeDeletionAuth(authAge: 3600), api = FakeAccountAPI()
        let old = auth.currentToken
        let (r, stages) = try await run(AccountDeletionFlow(auth: auth, api: api))
        #expect(stages == [.checking, .signingIn, .sending])
        #expect(auth.reauthCount == 1 && api.deleteTokens.count == 1)
        #expect(api.deleteTokens[0] != old && api.deleteTokens[0] == auth.currentToken && r.idToken == auth.currentToken)
        #expect(JWT.authTime(api.deleteTokens[0]).map { Date().timeIntervalSince($0) < 10 } == true)
    }

    @Test func theFreshnessEdges() {
        let now = Date()
        func tok(_ age: TimeInterval) -> String { FakeToken.make(authAge: age, now: now) }
        #expect(AccountDeletionFlow.isRecent(tok(5 * minute), now: now))
        #expect(AccountDeletionFlow.isRecent(tok(8 * minute), now: now))
        #expect(!AccountDeletionFlow.isRecent(tok(9.5 * minute), now: now), "within a minute of the limit counts as stale")
        #expect(!AccountDeletionFlow.isRecent(tok(11 * minute), now: now))
        #expect(!AccountDeletionFlow.isRecent(tok(-2 * minute), now: now), "a time far in the future is not trusted")
        #expect(!AccountDeletionFlow.isRecent(jwt(), now: now), "no auth_time: stale")
        #expect(AccountDeletionFlow.maxAge == 600)
    }

    @Test func aServer401RenewsOnceAndRetriesOnce() async throws {
        let auth = FakeDeletionAuth(authAge: 10), api = FakeAccountAPI([.failure(.reauthRequired), .success(.revokeAvailable)])
        let first = auth.currentToken
        let (r, stages) = try await run(AccountDeletionFlow(auth: auth, api: api))
        #expect(r.apple == .revokeAvailable && auth.reauthCount == 1 && api.deleteTokens.count == 2)
        #expect(api.deleteTokens[0] == first && api.deleteTokens[1] != first)
        #expect(stages == [.checking, .sending, .signingIn, .sending])
    }

    @Test func aSecond401NeverLoops() async {
        // fresh token, server still says too old after the renewal
        let a = FakeDeletionAuth(authAge: 10), api = FakeAccountAPI([.failure(.reauthRequired)])
        #expect(await errorOf(AccountDeletionFlow(auth: a, api: api)) == .reauthNotAccepted)
        #expect(a.reauthCount == 1 && api.deleteTokens.count == 2)
        // stale token renewed up front, server still says too old: no second renewal
        let b = FakeDeletionAuth(authAge: 3600), api2 = FakeAccountAPI([.failure(.reauthRequired)])
        #expect(await errorOf(AccountDeletionFlow(auth: b, api: api2)) == .reauthNotAccepted)
        #expect(b.reauthCount == 1 && api2.deleteTokens.count == 1)
    }

    @Test func aCancelledSignInSendsNothingAndKeepsTheSession() async throws {
        for age in [3600.0, 10.0] {
            let auth = FakeDeletionAuth(authAge: age, reauthError: AuthError.cancelled)
            let api = FakeAccountAPI(age == 10 ? [.failure(.reauthRequired)] : [.success(.notLinked)])
            let sent = age == 10 ? 1 : 0
            #expect(await errorOf(AccountDeletionFlow(auth: auth, api: api)) == .reauthCancelled)
            #expect(api.deleteTokens.count == sent)
            _ = try await auth.authorization()       // still signed in, same tokens
        }
    }

    @Test func aFailedOrWrongAccountSignInSendsNothing() async {
        let failed = FakeDeletionAuth(authAge: 3600, reauthError: AuthError.failed), api = FakeAccountAPI()
        #expect(await errorOf(AccountDeletionFlow(auth: failed, api: api)) == .reauthFailed && api.deleteTokens.isEmpty)
        let other = FakeDeletionAuth(authAge: 3600, reauthError: AuthError.wrongAccount)
        #expect(await errorOf(AccountDeletionFlow(auth: other, api: api)) == .wrongAccount && api.deleteTokens.isEmpty)
    }

    @Test func aRenewedTokenForAnotherSubIsRefused() async {
        struct Swap: DeletionAuth {
            let n: Counter
            func authorization() async throws -> (idToken: String, userID: String) { n.bump() == 0 ? (FakeToken.make(sub: "a", authAge: 3600), "a") : (FakeToken.make(sub: "b", authAge: 1), "b") }
            func reauthenticate(expectedSub: String) async throws {}
        }
        final class Counter: @unchecked Sendable { private let l = NSLock(); private var c = 0; func bump() -> Int { l.withLock { defer { c += 1 }; return c } } }
        let api = FakeAccountAPI()
        #expect(await errorOf(AccountDeletionFlow(auth: Swap(n: Counter()), api: api)) == .wrongAccount && api.deleteTokens.isEmpty)
    }

    @Test func offlineThenRetryGoesStraightToTheServerWithoutSigningInAgain() async throws {
        let auth = FakeDeletionAuth(authAge: 20 * minute)      // would need a renewal on a normal run
        let api = FakeAccountAPI([.failure(.uncertain), .success(.notLinked)])
        // first attempt: renewal up front, then the request is lost
        #expect(await errorOf(AccountDeletionFlow(auth: auth, api: api)) == .uncertain)
        #expect(auth.reauthCount == 1)
        // retry after the lost answer: no second renewal, same call repeated (idempotent on the server)
        let (r, stages) = try await run(AccountDeletionFlow(auth: auth, api: api, now: { Date().addingTimeInterval(30 * minute) }), unknown: true)
        #expect(r.apple == .notLinked && auth.reauthCount == 1 && stages == [.checking, .sending])
        #expect(api.deleteTokens.count == 2)
    }

    @Test func aRetryAfterALostAnswerStillRenewsIfTheServerAsks() async throws {
        let auth = FakeDeletionAuth(authAge: 10), api = FakeAccountAPI([.failure(.reauthRequired), .success(.notLinked)])
        let (r, _) = try await run(AccountDeletionFlow(auth: auth, api: api), unknown: true)
        #expect(r.apple == .notLinked && auth.reauthCount == 1)
    }

    @Test func aLostAnswerFollowedByASwitchedOffSessionCountsAsAccepted() async throws {
        let auth = FakeDeletionAuth(authAge: 10), api = FakeAccountAPI()
        auth.revokeSession()
        let (r, _) = try await run(AccountDeletionFlow(auth: auth, api: api), unknown: true)
        #expect(r.assumed && r.apple == .unknown && r.idToken == nil && api.deleteTokens.isEmpty)
        // but without a lost answer, a missing session is just "signed out" and nothing is claimed
        #expect(await errorOf(AccountDeletionFlow(auth: auth, api: api)) == .signedOut)
    }

    @Test func serverRefusalsAreMappedAndNothingIsRenewedForThem() async {
        for e in [AccountError.forbidden, .requestRejected, .server, .sessionExpired, .network] {
            let auth = FakeDeletionAuth(authAge: 10), api = FakeAccountAPI([.failure(e)])
            #expect(await errorOf(AccountDeletionFlow(auth: auth, api: api)) == e)
            #expect(auth.reauthCount == 0 && api.deleteTokens.count == 1)
            #expect(!e.message.isEmpty && !e.message.contains("{"))
        }
    }

    @Test func callingAgainAfterAcceptanceIsHarmless() async throws {
        let auth = FakeDeletionAuth(authAge: 10), api = FakeAccountAPI([.success(.revokeOff)])
        let flow = AccountDeletionFlow(auth: auth, api: api)
        let (a, _) = try await run(flow), (b, _) = try await run(flow)
        #expect(a.apple == .revokeOff && b.apple == .revokeOff && api.deleteTokens.count == 2)
    }

    @Test func everyAppleAnswerIsCarriedThrough() async throws {
        for link in [AppleLink.notLinked, .revokeAvailable, .revokeOff, .unknown] {
            let (r, _) = try await run(AccountDeletionFlow(auth: FakeDeletionAuth(authAge: 1), api: FakeAccountAPI([.success(link)])))
            #expect(r.apple == link)
        }
        #expect(AppleLink(server: "revoke_available") == .revokeAvailable && AppleLink(server: "something_new") == .unknown && AppleLink(server: nil) == .unknown)
    }

    @Test func noMessageContainsATokenOrSubAndTheContractWordingIsUsed() {
        #expect(AppleRevoke.manualSteps == "To finish, open Settings on your iPhone, tap your name, Sign in with Apple, VideoMK, and choose Stop using Apple ID.")
        #expect(AccountError.uncertain.message.contains("safe to try again"))
        #expect(AccountError.reauthNotAccepted.offersEmail && !AccountError.network.offersEmail)
    }
}

@Suite(.serialized) struct AccountNetworkTests {
    struct AccountClientTests {
        private func client() -> AccountClient { AccountClient(config: config, session: accountSession(), appVersion: "9") }
        private func token(_ sub: String = "sub-123") -> String { FakeToken.make(sub: sub, authAge: 1) }

        @Test func theRequestIsThePathOfTheTokensOwnSubWithTheConfirmWord() async throws {
            nonisolated(unsafe) var seen: URLRequest?; nonisolated(unsafe) var body = Data()
            AccountStub.handler = { r in seen = r; body = bodyData(r); return (202, Data(#"{"status":"deleting","apple":"revoke_available"}"#.utf8)) }
            let t = token("abc-sub")
            let apple = try await client().deleteAccount(idToken: t)
            #expect(apple == .revokeAvailable)
            #expect(seen?.url?.absoluteString == "https://api.test/prod/users/abc-sub/account/delete" && seen?.httpMethod == "POST")
            #expect(seen?.value(forHTTPHeaderField: "Authorization") == "Bearer \(t)")
            #expect((try? JSONSerialization.jsonObject(with: body) as? [String: String]) == ["confirm": "DELETE"])
        }

        @Test func answersAreMapped() async {
            func outcome(_ code: Int, _ body: String) async -> Result<AppleLink, AccountError> {
                AccountStub.handler = { _ in (code, Data(body.utf8)) }
                do { return .success(try await client().deleteAccount(idToken: token())) } catch { return .failure(error as! AccountError) }
            }
            #expect(await outcome(202, #"{"status":"deleting","apple":"not_linked"}"#) == .success(.notLinked))
            #expect(await outcome(202, #"{"status":"deleting","apple":"revoke_off"}"#) == .success(.revokeOff))
            #expect(await outcome(202, "not json") == .success(.unknown), "accepted, whatever the body")
            #expect(await outcome(202, #"{"apple":"from_the_future"}"#) == .success(.unknown))
            #expect(await outcome(401, #"{"message":"x","code":"reauth_required","max_age_seconds":600}"#) == .failure(.reauthRequired))
            #expect(await outcome(401, #"{"message":"Unauthorized"}"#) == .failure(.sessionExpired))
            #expect(await outcome(403, #"{"message":"Forbidden"}"#) == .failure(.forbidden))
            #expect(await outcome(400, #"{"code":"confirmation_required"}"#) == .failure(.requestRejected))
            #expect(await outcome(500, #"{"message":"Something went wrong. Please try again."}"#) == .failure(.server))
            #expect(await outcome(502, "") == .failure(.server))
        }

        @Test func aDroppedConnectionIsUncertainNotFailed() async {
            AccountStub.handler = { _ in throw URLError(.notConnectedToInternet) }
            await #expect(throws: AccountError.uncertain) { try await client().deleteAccount(idToken: token()) }
            await #expect(throws: AccountError.network) { try await client().appleRevokeURL(idToken: token()) }
        }

        @Test func aTokenWithoutASubSendsNothing() async {
            nonisolated(unsafe) var called = false
            AccountStub.handler = { _ in called = true; return (202, Data()) }
            await #expect(throws: AccountError.signedOut) { try await client().deleteAccount(idToken: "garbage") }
            #expect(!called)
        }

        @Test func theRevokeURLMustBeAppleOverHTTPS() async throws {
            func url(_ s: String) async -> URL? {
                AccountStub.handler = { _ in (200, Data(#"{"authorize_url":"\#(s)","expires_in":600}"#.utf8)) }
                return try? await client().appleRevokeURL(idToken: token())
            }
            #expect(await url("https://appleid.apple.com/auth/authorize?x=1") != nil)
            #expect(await url("https://evil.example/auth/authorize") == nil)
            #expect(await url("http://appleid.apple.com/auth/authorize") == nil)
            #expect(await url("https://appleid.apple.com.evil.example/a") == nil)
            nonisolated(unsafe) var seen: URLRequest?; nonisolated(unsafe) var body = Data()
            AccountStub.handler = { r in seen = r; body = bodyData(r); return (200, Data(#"{"authorize_url":"https://appleid.apple.com/a","expires_in":600}"#.utf8)) }
            _ = try await client().appleRevokeURL(idToken: token("s9"))
            #expect(seen?.url?.path == "/prod/users/s9/account/apple-revoke" && (try? JSONSerialization.jsonObject(with: body) as? [String: String]) == ["return": "app"])
            AccountStub.handler = { _ in (404, Data(#"{"code":"apple_revoke_off"}"#.utf8)) }
            await #expect(throws: AccountError.revokeUnavailable) { try await client().appleRevokeURL(idToken: token()) }
        }

        @Test func theAppleReturnIsParsedStrictly() {
            func s(_ u: String) -> AppleRevoke.Status { AppleRevoke.status(of: URL(string: u)!) }
            #expect(s("com.videomk.app://auth/apple-revoked?status=ok") == .ok)
            for st in ["cancelled", "mismatch", "failed", "invalid"] { #expect(s("com.videomk.app://auth/apple-revoked?status=\(st)").rawValue == st) }
            #expect(s("com.videomk.app://auth/apple-revoked?status=OK") == .failed)
            #expect(s("com.videomk.app://auth/apple-revoked") == .failed)
            #expect(s("com.videomk.app://auth/callback?status=ok") == .failed)
            #expect(s("com.videomk.app://other/apple-revoked?status=ok") == .failed)
            #expect(s("evil.app://auth/apple-revoked?status=ok") == .failed)
        }
    }

    struct ReauthURLTests {
        private func q(_ u: URL) -> [String: String] { Dictionary(URLComponents(url: u, resolvingAgainstBaseURL: false)!.queryItems!.map { ($0.name, $0.value ?? "") }, uniquingKeysWith: { a, _ in a }) }
        private func auth(_ store: InMemoryTokenStore = InMemoryTokenStore()) -> AuthService { AuthService(config: config, store: store, session: accountSession()) }

        @Test func logoutIsTheRegisteredHostedUIUrl() async {
            let u = await auth().logoutURL()
            #expect(u.host == "auth.test" && u.path == "/logout" && q(u) == ["client_id": "cid", "logout_uri": "com.videomk.app://auth/signout"])
        }

        @Test func reauthIsANormalAuthorizeWithPromptLoginAndMaxAgeZero() async {
            let a = auth()
            let plain = q(await a.beginSignIn()), re = q(await a.beginReauth())
            #expect(Set(re.keys).subtracting(plain.keys) == ["prompt", "max_age"] && re["prompt"] == "login" && re["max_age"] == "0")
            #expect(re["response_type"] == "code" && re["code_challenge_method"] == "S256" && re["redirect_uri"] == "com.videomk.app://auth/callback")
            #expect(re["identity_provider"] == nil)
        }

        private func tokenResponse(sub: String) -> Data {
            Data(#"{"id_token":"\#(FakeToken.make(sub: sub, authAge: 1))","access_token":"at","refresh_token":"rt","expires_in":3600}"#.utf8)
        }

        @Test func aRenewalForTheSameAccountReplacesTheTokensAndOneForAnotherDoesNot() async throws {
            let old = Tokens(idToken: FakeToken.make(sub: "me", authAge: 3600), accessToken: "", refreshToken: "old-rt", expiresAt: Date().addingTimeInterval(1000))
            for (sub, ok) in [("me", true), ("someone-else", false)] {
                let store = InMemoryTokenStore(old)
                AccountStub.handler = { _ in (200, self.tokenResponse(sub: sub)) }
                let a = auth(store)
                let state = q(await a.beginReauth())["state"]!
                let cb = URL(string: "com.videomk.app://auth/callback?code=c&state=\(state)")!
                if ok {
                    try await a.completeReauth(callback: cb, expectedSub: "me")
                    #expect(store.load()?.refreshToken == "rt" && JWT.subject(store.load()!.idToken) == "me")
                } else {
                    await #expect(throws: AuthError.wrongAccount) { try await a.completeReauth(callback: cb, expectedSub: "me") }
                    #expect(store.load() == old, "another person's sign-in never replaces this session")
                }
            }
        }

        @Test func aCancelledOrForgedRenewalLeavesTheSessionAlone() async {
            let old = Tokens(idToken: FakeToken.make(sub: "me", authAge: 3600), accessToken: "", refreshToken: "rt0", expiresAt: Date().addingTimeInterval(1000))
            let store = InMemoryTokenStore(old); let a = auth(store)
            let state = q(await a.beginReauth())["state"]!
            await #expect(throws: AuthError.cancelled) { try await a.completeReauth(callback: URL(string: "com.videomk.app://auth/callback?error=access_denied&state=\(state)")!, expectedSub: "me") }
            _ = await a.beginReauth()
            await #expect(throws: AuthError.failed) { try await a.completeReauth(callback: URL(string: "com.videomk.app://auth/callback?code=c&state=forged")!, expectedSub: "me") }
            #expect(store.load() == old)
        }
    }

}

@Suite struct LocalWipeTests {
    @Test func folderContentsGoButTheFoldersStay() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent("wipe-\(UUID().uuidString)")
        let a = root.appendingPathComponent("a"), b = root.appendingPathComponent("b")
        try fm.createDirectory(at: a.appendingPathComponent("thumbs"), withIntermediateDirectories: true)
        try fm.createDirectory(at: b, withIntermediateDirectories: true)
        try Data("x".utf8).write(to: a.appendingPathComponent("thumbs/1.jpg")); try Data("x".utf8).write(to: b.appendingPathComponent("queue.json"))
        LocalWipe.clearContents(of: [a, b, root.appendingPathComponent("missing")])
        #expect(fm.fileExists(atPath: a.path) && fm.fileExists(atPath: b.path))
        let left = try fm.contentsOfDirectory(atPath: a.path) + fm.contentsOfDirectory(atPath: b.path)
        #expect(left.isEmpty)
        try? fm.removeItem(at: root)
    }

    @Test func preferencesAreEmptiedExceptTheExplicitSignOutFlag() {
        let name = "wipe-test-\(UUID().uuidString)"
        let d = UserDefaults(suiteName: name)!
        d.set(true, forKey: "mediaPrivacyNoteSeen"); d.set(Data("draft".utf8), forKey: "createDefaults.user-1"); d.set(false, forKey: "usePhotoDates")
        LocalWipe.resetDefaults(d, domain: name, then: ["vmk.explicitSignOut": true])
        #expect(d.object(forKey: "mediaPrivacyNoteSeen") == nil && d.object(forKey: "createDefaults.user-1") == nil && d.object(forKey: "usePhotoDates") == nil)
        #expect(d.bool(forKey: "vmk.explicitSignOut"))
        d.removePersistentDomain(forName: name)
    }
}
