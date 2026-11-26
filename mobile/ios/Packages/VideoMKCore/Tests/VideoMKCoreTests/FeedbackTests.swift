import Foundation
import Testing
@testable import VideoMKCore

private func suite() -> UserDefaults { UserDefaults(suiteName: "fb-\(UUID().uuidString)")! }

private final class Clock: @unchecked Sendable { var t = Date(timeIntervalSince1970: 1_800_000_000); func advance(_ s: TimeInterval) { t += s } }

private func prompt(_ d: UserDefaults, _ clock: Clock, version: String = "1.0", configured: Bool = true) -> RatingPrompt {
    RatingPrompt(defaults: d, now: { clock.t }, version: version, configured: configured)
}
private func watch(_ p: RatingPrompt, _ n: Int, from: Int = 1) { for i in 0..<n { p.recordCompleted("v\(from + i)") } }

@Suite struct RatingPromptTests {
    @Test func eligibleOnlyAtTheEleventhDistinctVideo() {
        let c = Clock(), p = prompt(suite(), c); c.advance(300)
        watch(p, 10)
        #expect(!p.shouldPrompt())
        p.recordCompleted("v11")
        #expect(p.shouldPrompt())
    }

    @Test func theSameVideoCountsOnce() {
        let c = Clock(), p = prompt(suite(), c); c.advance(300)
        for _ in 0..<30 { p.recordCompleted("same") }
        #expect(p.state.completedCount == 1 && !p.shouldPrompt())
        #expect(!p.recordCompleted("same") && !p.recordCompleted(""))
    }

    @Test func closedThenAskedAgainAtTwentyOneThenThirtyOneThenNever() {
        let c = Clock(), d = suite(); let p = prompt(d, c); c.advance(300)
        watch(p, 11); #expect(p.shouldPrompt()); p.didShow(); p.resolve(.maybeLater)
        #expect(!p.shouldPrompt(), "not again at once")
        watch(p, 9, from: 12); #expect(!p.shouldPrompt(), "20 is not enough")
        // a new app version cycle between asks
        let p2 = prompt(d, c, version: "1.1"); c.advance(300)
        p2.recordCompleted("v21"); #expect(p2.shouldPrompt()); p2.didShow(); p2.resolve(.notReally)
        watch(p2, 10, from: 22); #expect(!p2.shouldPrompt(), "the same version is asked once")
        let p3 = prompt(d, c, version: "1.2"); c.advance(300)
        #expect(p3.shouldPrompt() && p3.threshold == 31); p3.didShow(); p3.resolve(.maybeLater)
        let p4 = prompt(d, c, version: "1.3"); c.advance(300)
        watch(p4, 50, from: 100)
        #expect(!p4.shouldPrompt() && p4.state.asked == 3, "at most three asks")
    }

    @Test func alreadyRatedAndRateEndItForever() {
        for outcome in [RatingOutcome.alreadyRated, .rate] {
            let c = Clock(), d = suite(), p = prompt(d, c); c.advance(300)
            watch(p, 11); p.didShow(); p.resolve(outcome)
            watch(p, 100, from: 12)
            #expect(!prompt(d, c, version: "9.9").shouldPrompt())
        }
    }

    @Test func neverEarlyOrWhileBusy() {
        let c = Clock(), p = prompt(suite(), c)
        watch(p, 11)
        #expect(!p.shouldPrompt(), "within 2 minutes of launch")
        c.advance(119); #expect(!p.shouldPrompt())
        c.advance(2); #expect(p.shouldPrompt())
        #expect(!p.shouldPrompt(RatingContext(isPlaying: true)))
        #expect(!p.shouldPrompt(RatingContext(isCreating: true)))
        #expect(!p.shouldPrompt(RatingContext(sheetOpen: true)))
        #expect(!p.shouldPrompt(RatingContext(suppressed: true)))
    }

    @Test func notWithoutARealAppStoreId() {
        let c = Clock(), p = prompt(suite(), c, configured: false); c.advance(300); watch(p, 11)
        #expect(!p.shouldPrompt())
        #expect(!AppStoreInfo.isConfigured, "placeholder id until the owner fills it in")
        #expect(AppStoreInfo.writeReviewURL(appID: "123").absoluteString == "https://apps.apple.com/app/id123?action=write-review")
    }

    @Test func stateSurvivesARestartAndTheIdSetIsBounded() {
        let c = Clock(), d = suite(); let p = prompt(d, c); c.advance(300)
        watch(p, 11); p.didShow(); p.resolve(.maybeLater)
        let q = prompt(d, c)
        #expect(q.state.completedCount == 11 && q.state.asked == 1 && q.state.askedAtCount == 11 && q.state.lastAskedAt != nil)
        watch(q, RatingPrompt.idCap + 50, from: 1000)
        #expect(q.state.completedIDs.count == RatingPrompt.idCap && q.state.completedCount == 11 + RatingPrompt.idCap + 50)
        #expect(prompt(d, c).state == q.state)
    }

    @Test func suppressedInTestsAndScreenshots() {
        #expect(RatingPrompt.isSuppressed(environment: ["XCTestConfigurationFilePath": "/x"]))
        #expect(RatingPrompt.isSuppressed(environment: ["VMK_SHOTS_DIR": "/x"]))
        #expect(RatingPrompt.isSuppressed(environment: ["VMK_DEBUG_FAKE_LIBRARY": "1"]))
        #expect(!RatingPrompt.isSuppressed(environment: [:]))
    }
}

@Suite struct PlaybackCompletionTests {
    private func play(_ pc: inout PlaybackCompletion, from: Double, to: Double, duration: Double, step: Double = 0.5) {
        var t = from; while t < to { t = min(to, t + step); pc.observe(position: t, duration: duration) }
    }

    @Test func watchingThroughCounts() {
        var pc = PlaybackCompletion(); pc.observe(position: 0, duration: 60)
        play(&pc, from: 0, to: 59.2, duration: 60)
        #expect(pc.isComplete)
    }

    @Test func scrubbingToTheEndDoesNot() {
        var pc = PlaybackCompletion(); pc.observe(position: 0, duration: 60)
        pc.observe(position: 59.9, duration: 60)
        #expect(!pc.isComplete)
        var skip = PlaybackCompletion()
        play(&skip, from: 0, to: 10, duration: 60); skip.observe(position: 59.5, duration: 60)
        #expect(!skip.isComplete, "10 s watched of 60 is not 90%")
    }

    @Test func ninetyPercentWithForwardPlayAndEndWithinOneSecond() {
        var pc = PlaybackCompletion()
        play(&pc, from: 0, to: 55, duration: 60)            // over 90% watched, then skip the credits
        pc.observe(position: 59.2, duration: 60)            // jump to the end
        #expect(pc.isComplete)
        var short = PlaybackCompletion()
        play(&short, from: 0, to: 50, duration: 60)
        pc = short; pc.observe(position: 59.5, duration: 60)
        #expect(!pc.isComplete, "83% is not enough")
        var notAtEnd = PlaybackCompletion(); play(&notAtEnd, from: 0, to: 57, duration: 60)
        #expect(!notAtEnd.isComplete, "95% but 3 s from the end")
    }

    @Test func pausingAndBadValuesAreHarmless() {
        var pc = PlaybackCompletion()
        for _ in 0..<20 { pc.observe(position: 5, duration: 60) }
        pc.observe(position: .nan, duration: 60); pc.observe(position: 5, duration: 0)
        #expect(pc.watched == 0 && !pc.isComplete)
    }
}

@Suite @MainActor struct FeedbackComposerTests {
    final class Fake: FeedbackAPI, @unchecked Sendable {
        var result: Error?; var sent: [FeedbackRequest] = []
        func sendFeedback(_ r: FeedbackRequest) async throws { sent.append(r); if let result { throw result } }
    }
    private func make(_ api: Fake, _ d: UserDefaults = suite(), context: FeedbackContext = .settings) -> FeedbackComposer {
        FeedbackComposer(context: context, api: api, version: "1.2", drafts: FeedbackDraftStore(defaults: d), locale: { "es" })
    }

    @Test func lengthRules() {
        #expect(!FeedbackRules.isValid("  ab  ") && FeedbackRules.isValid(" abc ") && FeedbackRules.isValid(String(repeating: "x", count: 2000)))
        #expect(!FeedbackRules.isValid(String(repeating: "x", count: 2001)))
        let c = make(Fake()); c.text = String(repeating: "y", count: 2500)
        #expect(c.count == 2000)
    }

    @Test func sendsTheContractBody() async throws {
        let api = Fake(), c = make(api, context: .ratingPrompt)
        c.text = "  I would love dark mode  "; c.choose(.idea)
        await c.send()
        #expect(c.phase == .sent)
        let r = try #require(api.sent.first)
        let j = r.json
        #expect(j["text"] as? String == "I would love dark mode" && j["kind"] as? String == "idea" && j["app"] as? String == "ios")
        #expect(j["version"] as? String == "1.2" && j["locale"] as? String == "es" && j["context"] as? String == "rating_prompt")
        #expect(FeedbackRequest(text: "abc", kind: nil, version: "1", locale: "en", context: .afterVideo).json["kind"] == nil)
    }

    @Test func failureKeepsTheTextAndRetrySucceeds() async {
        let api = Fake(), d = suite(), c = make(api, d)
        c.text = "It crashed when I opened it"
        for e in [FeedbackError.network, .rateLimited, .server, .invalid] {
            api.result = e; await c.send()
            #expect(c.phase == .failed(e) && c.text == "It crashed when I opened it" && c.canSend)
        }
        #expect(make(Fake(), d).text == "It crashed when I opened it", "saved on the phone for the next time")
        api.result = nil; await c.send()
        #expect(c.phase == .sent && make(Fake(), d).text == "", "cleared only after success")
    }

    @Test func tooShortCannotSendAndKindToggles() async {
        let api = Fake(), c = make(api); c.text = "hi"
        await c.send(); #expect(api.sent.isEmpty && !c.canSend)
        c.choose(.problem); c.choose(.problem); #expect(c.kind == nil)
    }

    @Test func errorsAndKeysAreLocalised() {
        for e in [FeedbackError.network, .rateLimited, .invalid, .unauthorized, .server] {
            let en = Localization.$override.withValue(.en) { e.message }, es = Localization.$override.withValue(.es) { e.message }
            #expect(!en.hasPrefix("feedback.") && !es.hasPrefix("feedback.") && en != es)
        }
        for k in ["feedback.title", "feedback.intro", "feedback.thanks_title", "rating.question", "rating.ask_title", "rating.rate", "rating.later", "rating.already", "rating.not_really", "rating.sorry"] {
            let en = Localization.$override.withValue(.en) { tr(k) }, es = Localization.$override.withValue(.es) { tr(k) }
            #expect(en != k && es != k && en != es, "\(k)")
        }
    }
}
