import Foundation
import Testing
@testable import VideoMKCore

@MainActor @Suite struct UndoTests {
    final class Log { var undone = 0, committed: [String] = [] }

    @Test func undoBringsItBackAndNothingIsSent() async throws {
        let center = UndoCenter(window: .milliseconds(80)), log = Log()
        center.offer("Deleted", undo: { log.undone += 1 }, commit: { log.committed.append("a") })
        #expect(center.current?.text == "Deleted")
        center.undo()
        #expect(center.current == nil && log.undone == 1)
        try await Task.sleep(for: .milliseconds(200))
        #expect(log.committed.isEmpty, "an undone delete never reaches the server")
    }

    @Test func theDeleteIsSentWhenTheTimeIsUp() async throws {
        let center = UndoCenter(window: .milliseconds(60)), log = Log()
        center.offer("Deleted", undo: { log.undone += 1 }, commit: { log.committed.append("a") })
        try await Task.sleep(for: .milliseconds(300))
        #expect(log.committed == ["a"] && center.current == nil && log.undone == 0)
        center.undo()       // too late: nothing to undo
        #expect(log.undone == 0)
    }

    @Test func aSecondDeleteSendsTheFirst() async throws {
        let center = UndoCenter(window: .seconds(30)), log = Log()
        center.offer("One", undo: { log.undone += 1 }, commit: { log.committed.append("one") })
        center.offer("Two", undo: { log.undone += 10 }, commit: { log.committed.append("two") })
        try await Task.sleep(for: .milliseconds(100))
        #expect(log.committed == ["one"] && center.current?.text == "Two")
        center.flush()      // leaving the app sends what is pending
        try await Task.sleep(for: .milliseconds(100))
        #expect(log.committed == ["one", "two"] && center.current == nil && log.undone == 0)
    }
}

@Suite struct VideoInfoTextTests {
    @Test func theDescriptionIsSplitIntoTitledGroups() {
        let g = VideoInfoText.groups("A calm look at how forests breathe.\n\nChapters\n0:00 Intro\n0:20 Leaves\n\nSources:\nhttps://en.wikipedia.org/wiki/Forest\n\nPhoto credits: Example Photographer on Unsplash")
        #expect(g.map(\.title) == [nil, "Chapters", "Sources", "Photo credits"])
        #expect(g[1].body == "0:00 Intro\n0:20 Leaves" && g[2].body == "https://en.wikipedia.org/wiki/Forest" && g[3].body == "Example Photographer on Unsplash")
    }

    @Test func nothingIsLostAndLinksAreNotMistakenForLabels() {
        #expect(VideoInfoText.groups("https://example.com/a: b") == [.init(title: nil, body: "https://example.com/a: b")])
        #expect(VideoInfoText.groups("0:00 Intro\n0:20 Leaves") == [.init(title: nil, body: "0:00 Intro\n0:20 Leaves")])
        #expect(VideoInfoText.groups("  \n\n") == [])
        #expect(VideoInfoText.groups("One sentence. Another: with a colon.").first?.title == nil)
    }
}

@Suite struct AuditRulingTests {
    private let q = [IntakeQuestion(id: "audience", title: "Who?", helper: nil, options: [IntakeOption(id: "kids", label: "Kids")]),
                     IntakeQuestion(id: "tone", title: "Tone?", helper: nil, options: [IntakeOption(id: "calm", label: "Calm")]),
                     IntakeQuestion(id: "focus", title: "Focus?", helper: nil, options: [IntakeOption(id: "bees", label: "Bees")])]

    @Test func skipAllFinishesTheQuestionsInOneTap() {
        var f = IntakeFlow(q)
        f.skipRest()
        #expect(f.isComplete && !f.needsSummary, "nothing answered: no summary, the video starts")
        #expect(f.payload.count == 3 && f.payload.allSatisfy { $0.skip == true })
    }

    @Test func skipAllKeepsWhatWasAnsweredAndThenShowsTheSummary() {
        var f = IntakeFlow(q)
        f.choose(q[0].options[0])
        f.skipRest()
        #expect(f.isComplete && f.needsSummary && f.realAnswers.map(\.id) == ["audience"])
    }

    @Test func firstRunIsYouTubeOneMinuteOneCreditAndTheLastChoiceIsRemembered() {
        let suite = UserDefaults(suiteName: "audit-\(UUID().uuidString)")!
        let first = CreateDefaults.load(userID: "u", defaults: suite).form(.fallback)
        #expect(first.platform == "youtube" && first.minutes == 1 && first.options.credits == 1 && first.aspect == "16:9")
        var mine = first; mine.setMinutes(3)
        CreateDefaults(mine).save(userID: "u", defaults: suite)
        let again = CreateDefaults.load(userID: "u", defaults: suite).form(.fallback)
        #expect(again.minutes == 3 && again.options.credits == 3, "the price follows the remembered length")
    }

    @Test func aPauseSaysWhenInItsTitleAndNeverRepeatsItself() {
        Localization.$override.withValue(.en) {
            #expect(RetryText.short(3600) == "try again in about 1 hour" && RetryText.short(7200) == "try again in about 2 hours" && RetryText.short(60) == "try again in about a minute" && RetryText.short(nil) == nil)
            #expect(tr("create.paused_title_retry", RetryText.short(3600)!) == "Paused · try again in about 1 hour")
            #expect(KindCopy.message("Creating videos is paused for this account for now.", title: "Paused · try again in about 1 hour", alsoNot: ["Creating videos is paused", "Creating videos is paused for this account for now."]) == nil)
            #expect(KindCopy.message("We can’t make this one.", title: "We can’t make this one") == nil)
            #expect(KindCopy.message("We can’t make this one. Try describing something different.", title: "We can’t make this one") == "Try describing something different.")
            #expect(KindCopy.message("This request names a private person. Try a public topic instead of a named individual.", title: "We can’t make this one") != nil)
            #expect(KindCopy.message("  ", title: "x") == nil && KindCopy.message(nil, title: "x") == nil)
        }
        Localization.$override.withValue(.es) { #expect(RetryText.short(3600) == "inténtalo en 1 hora") }
    }

    @Test func oneWordForTheLibraryInEachLanguage() {
        for key in ["media.media", "tab.media"] {
            Localization.$override.withValue(.en) { #expect(tr(key) == "Media") }
            Localization.$override.withValue(.es) { #expect(tr(key) == "Biblioteca") }
        }
        Localization.$override.withValue(.en) { #expect(tr("detail.remix_short") == "As a Short" && tr("detail.remix_spanish") == "In Spanish" && tr("detail.remix_30s") == "30 seconds") }
    }
}

/// Answers 401 to the first token and 200 to the refreshed one.
final class ExpiredStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var tokens: [String] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let token = request.value(forHTTPHeaderField: "Authorization") ?? ""
        Self.tokens.append(token)
        let ok = token == "Bearer fresh"
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: ok ? 200 : 401, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data((ok ? "{\"balance\":4,\"buckets\":[]}" : "{\"message\":\"Unauthorized\"}").utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct ExpiredSessionTests {
    actor Auth: AuthorizationProviding {
        var token = "stale", refreshes = 0
        let canRefresh: Bool
        init(canRefresh: Bool) { self.canRefresh = canRefresh }
        func authorization() async throws -> (idToken: String, userID: String) { (token, "u1") }
        func refreshNow() async throws -> Bool { guard canRefresh else { return false }; refreshes += 1; token = "fresh"; return true }
    }
    let cfg = AppConfig(apiBase: URL(string: "https://expired.test/prod")!, authDomain: URL(string: "https://auth.test")!, clientID: "cid")
    func session() -> URLSession { let c = URLSessionConfiguration.ephemeral; c.protocolClasses = [ExpiredStub.self]; return URLSession(configuration: c) }

    /// Back from the background with a token the server no longer takes: the token is refreshed and the same call is sent again; nobody is signed out.
    @Test func anExpiredTokenIsRefreshedAndTheCallIsSentAgain() async throws {
        ExpiredStub.tokens = []
        let auth = Auth(canRefresh: true)
        let wallet = try await APIClient(config: cfg, auth: auth, session: session()).wallet()
        #expect(wallet.balance == 4)
        #expect(ExpiredStub.tokens == ["Bearer stale", "Bearer fresh"])
        #expect(await auth.refreshes == 1)
    }

    @Test func withoutARefreshTokenA401IsStillASignOut() async {
        ExpiredStub.tokens = []
        await #expect(throws: APIError.unauthorized) { _ = try await APIClient(config: cfg, auth: Auth(canRefresh: false), session: session()).wallet() }
        #expect(ExpiredStub.tokens == ["Bearer stale"], "one try, no loop")
    }
}
