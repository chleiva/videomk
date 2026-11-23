import Foundation
import Testing
@testable import VideoMKCore

// MARK: helpers

final class StubProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: (@Sendable (URLRequest) -> (Int, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let (code, data) = Self.handler?(request) ?? (500, Data())
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

func stubSession() -> URLSession {
    let c = URLSessionConfiguration.ephemeral
    c.protocolClasses = [StubProtocol.self]
    return URLSession(configuration: c)
}

let config = AppConfig(apiBase: URL(string: "https://api.test/prod")!, authDomain: URL(string: "https://auth.test")!, clientID: "cid")

func jwt(sub: String = "user-1", email: String = "a@b.c") -> String {
    func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64URLEncoded }
    return "\(b64(["alg": "none"])).\(b64(["sub": sub, "email": email])).sig"
}

struct FixedAuth: AuthorizationProviding {
    func authorization() async throws -> (idToken: String, userID: String) { ("tok", "user-1") }
}

// The suites share the static stub handler, so they run serially.
@Suite(.serialized) struct CoreTests {

    // MARK: models

    @Test func statusMapping() {
        #expect(VideoStatus(serverStatus: "COMPLETE") == .complete)
        #expect(VideoStatus(serverStatus: "REJECTED") == .rejected)
        #expect(VideoStatus(serverStatus: "FAILED") == .failed)
        #expect(VideoStatus(serverStatus: "PLOT_CREATION") == .running(.writing))
        #expect(VideoStatus(serverStatus: "ASSETS_CREATION") == .running(.voiceAndVisuals))
        #expect(VideoStatus(serverStatus: "RENDERING") == .running(.rendering))
        #expect(VideoStatus(serverStatus: "SOMETHING_NEW") == .running(.starting))  // unknown never looks like success
    }

    @Test func decodesTheServersListShape() throws {
        let json = """
        {"user_id":"u","items":[
          {"video_id":"v1","status":"COMPLETE","title":"Paris","duration_s":80,"created_at":"2026-11-22T21:35:56Z","video_url":"https://s3/x.mp4","preview_gif_url":"https://s3/x.gif","editable":true},
          {"video_id":"v2","status":"REJECTED","reject_reason":"Not suitable.","editable":false},
          {"video_id":"v3","status":"PLOT_CREATION"}]}
        """
        let items = try JSONDecoder().decode(VideoListResponse.self, from: Data(json.utf8)).items
        #expect(items.count == 3)
        #expect(items[0].displayTitle == "Paris" && items[0].durationSeconds == 80 && items[0].editable && items[0].createdAt != nil)
        #expect(items[1].status == .rejected && items[1].rejectReason == "Not suitable." && items[1].displayTitle == "Untitled video")
        #expect(items[2].status == .running(.writing))
    }

    @Test func briefValidationMatchesTheServer() {
        #expect(!Brief.isValid("too short"))
        #expect(Brief.isValid("A tour of Paris landmarks"))
        #expect(Brief.normalized("  a \n\n b\tc ") == "a b c")
        #expect(!Brief.isValid(String(repeating: "x", count: 2001)))
    }

    // MARK: API

    @Test func listSendsBearerAndPlatformHeaders() async throws {
        nonisolated(unsafe) var seen: URLRequest?
        StubProtocol.handler = { req in seen = req; return (200, Data(#"{"items":[{"video_id":"v1","status":"COMPLETE"}]}"#.utf8)) }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession(), appVersion: "1.2")
        let items = try await api.listVideos()
        #expect(items.map(\.id) == ["v1"])
        #expect(seen?.url?.absoluteString == "https://api.test/prod/users/user-1/videos")
        #expect(seen?.value(forHTTPHeaderField: "Authorization") == "Bearer tok")
        #expect(seen?.value(forHTTPHeaderField: "X-Platform") == "ios" && seen?.value(forHTTPHeaderField: "X-App-Version") == "1.2")
    }

    @Test func startGenerationSendsNormalizedPromptAndRequestID() async throws {
        nonisolated(unsafe) var body: [String: String] = [:]
        StubProtocol.handler = { req in
            body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: String]) ?? [:]
            return (202, Data(#"{"message":"workflow started","video_id":"abc"}"#.utf8))
        }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        let id = try await api.startGeneration(prompt: "  A tour   of Paris ", clientRequestID: "req-12345678")
        #expect(id == "abc")
        #expect(body["prompt"] == "A tour of Paris" && body["client_request_id"] == "req-12345678")
    }

    @Test(arguments: [(400, "invalid"), (429, "quota"), (401, "unauthorized"), (403, "unauthorized"), (500, "server")])
    func errorMapping(code: Int, kind: String) async {
        StubProtocol.handler = { _ in (code, Data(#"{"message":"nope"}"#.utf8)) }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        do { _ = try await api.startGeneration(prompt: "A tour of Paris", clientRequestID: "r") ; Issue.record("expected an error") }
        catch let e as APIError {
            switch (e, kind) {
            case (.invalid(let m), "invalid"), (.quota(let m), "quota"): #expect(m == "nope")
            case (.unauthorized, "unauthorized"), (.server, "server"): break
            default: Issue.record("unexpected \(e) for \(code)")
            }
        } catch { Issue.record("unexpected \(error)") }
    }

    @Test func notReadyCarriesTheStatus() async {
        StubProtocol.handler = { _ in (409, Data(#"{"message":"Video not ready","status":"RENDERING"}"#.utf8)) }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        do { _ = try await api.playbackURL(videoID: "v"); Issue.record("expected an error") }
        catch { #expect(error as? APIError == .notReady(.running(.rendering))) }
    }

    // MARK: auth

    @Test func pkceChallengeIsTheS256OfTheVerifier() {
        // RFC 7636 appendix B
        #expect(PKCE(verifier: "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk").challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
        let p = PKCE.generate()
        #expect(p.verifier.count >= 43 && !p.verifier.contains("=") && !p.verifier.contains("+"))
    }

    @Test func jwtClaims() {
        #expect(JWT.subject(jwt(sub: "abc")) == "abc" && JWT.email(jwt(email: "x@y.z")) == "x@y.z")
        #expect(JWT.subject("garbage") == nil)
    }

    @Test func signInURLAndCodeExchange() async throws {
        let store = InMemoryTokenStore()
        let auth = AuthService(config: config, store: store, session: stubSession())
        let url = await auth.beginSignIn()
        let q = Dictionary(uniqueKeysWithValues: URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems!.map { ($0.name, $0.value ?? "") })
        #expect(url.host == "auth.test" && url.path == "/oauth2/authorize")
        #expect(q["code_challenge_method"] == "S256" && q["client_id"] == "cid" && q["redirect_uri"] == "com.videomk.app://auth/callback")

        nonisolated(unsafe) var form = ""
        StubProtocol.handler = { req in
            form = String(data: req.bodyData ?? Data(), encoding: .utf8) ?? ""
            return (200, Data(#"{"id_token":"\#(jwt())","access_token":"at","refresh_token":"rt","expires_in":3600}"#.utf8))
        }
        try await auth.completeSignIn(callback: URL(string: "com.videomk.app://auth/callback?code=thecode&state=\(q["state"]!)")!)
        #expect(form.contains("grant_type=authorization_code") && form.contains("code=thecode") && form.contains("code_verifier="))
        #expect(store.load()?.refreshToken == "rt")
        #expect(try await auth.authorization().userID == "user-1")
    }

    @Test func aWrongStateIsRejected() async throws {
        let auth = AuthService(config: config, store: InMemoryTokenStore(), session: stubSession())
        _ = await auth.beginSignIn()
        await #expect(throws: AuthError.failed) {
            try await auth.completeSignIn(callback: URL(string: "com.videomk.app://auth/callback?code=c&state=forged")!)
        }
    }

    @Test func expiredTokensRefreshOnceAndKeepTheRefreshToken() async throws {
        let store = InMemoryTokenStore(Tokens(idToken: jwt(), accessToken: "old", refreshToken: "rt", expiresAt: Date().addingTimeInterval(-10)))
        let auth = AuthService(config: config, store: store, session: stubSession())
        nonisolated(unsafe) var calls = 0
        StubProtocol.handler = { _ in calls += 1; return (200, Data(#"{"id_token":"\#(jwt(sub: "user-1"))","access_token":"new","expires_in":3600}"#.utf8)) }
        async let a = auth.authorization(), b = auth.authorization()
        _ = try await (a, b)
        #expect(calls == 1)
        #expect(store.load()?.accessToken == "new" && store.load()?.refreshToken == "rt")
    }

    @Test func aRevokedRefreshTokenSignsOut() async {
        let store = InMemoryTokenStore(Tokens(idToken: jwt(), accessToken: "old", refreshToken: "rt", expiresAt: Date().addingTimeInterval(-10)))
        let auth = AuthService(config: config, store: store, session: stubSession())
        StubProtocol.handler = { _ in (400, Data(#"{"error":"invalid_grant"}"#.utf8)) }
        await #expect(throws: AuthError.signedOut) { _ = try await auth.authorization() }
        #expect(store.load() == nil)
    }
}

extension URLRequest {
    /// URLProtocol receives bodies as a stream.
    var bodyData: Data? {
        if let httpBody { return httpBody }
        guard let s = httpBodyStream else { return nil }
        s.open(); defer { s.close() }
        var out = Data(); var buf = [UInt8](repeating: 0, count: 4096)
        while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; out.append(buf, count: n) }
        return out
    }
}
