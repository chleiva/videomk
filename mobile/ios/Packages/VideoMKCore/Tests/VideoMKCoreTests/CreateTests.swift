import Foundation
import Testing
@testable import VideoMKCore

private func vertical() -> CreateCapabilities {
    CreateCapabilities(aspects: [.init(id: "16:9", label: "Landscape"), .init(id: "9:16", label: "Vertical", ready: true, beta: true), .init(id: "1:1", label: "Square", ready: false)],
                       resolutions: [.init(id: "720p"), .init(id: "1080p")], platforms: CreateCapabilities.platformDefaults, languages: [.init(id: "en", label: "English"), .init(id: "es", label: "Español")])
}
private let landscapeOnly = CreateCapabilities(aspects: [.init(id: "16:9", label: "Landscape")], resolutions: [.init(id: "1080p")], platforms: CreateCapabilities.platformDefaults)

@Suite struct CreateCapabilityTests {
    @Test func decodesTheContractAndToleratesGaps() throws {
        let json = #"{"aspects":[{"id":"16:9","label":"Landscape","ready":true,"beta":false},{"id":"9:16","label":"Vertical","ready":true,"beta":true}],"resolutions":[{"id":"720p","label":"720p"},{"id":"1080p","label":"1080p"}],"platforms":[{"id":"youtube","label":"YouTube","aspect":"16:9","resolution":"1080p","note":"Landscape 16:9 · 1080p"}],"languages":[{"id":"en","label":"English"}],"lengths":{"min_minutes":1,"max_minutes":12},"max_photos":100,"intake":true}"#
        let c = try JSONDecoder().decode(CreateCapabilities.self, from: Data(json.utf8))
        #expect(c.readyAspects.map(\.id) == ["16:9", "9:16"] && c.aspect("9:16")?.beta == true && c.resolutions.count == 2 && c.intake && c.maxPhotos == 100 && c.languages.first?.label == "English")
        let sparse = try JSONDecoder().decode(CreateCapabilities.self, from: Data(#"{"aspects":[{"id":"16:9"}]}"#.utf8))
        #expect(sparse.readyAspects.isEmpty && !sparse.intake)                       // ready defaults to false: never offer what the server did not say is ready
    }

    @Test func theFallbackOffersOnlyLandscape1080pAndSkipsTheCheck() {
        let f = CreateCapabilities.fallback
        #expect(f.readyAspects.map(\.id) == ["16:9"] && f.resolutions.map(\.id) == ["1080p"] && !f.intake)
        let form = CreateForm()
        #expect(!form.canChangeFormat(f))
    }

    @Test func platformChipsAreDataSupportedFirstAndGroupedLikeTheDesign() {
        let chips = PlatformChips.make(landscapeOnly)
        #expect(chips.map(\.label) == ["YouTube", "LinkedIn", "X", "Just a video", "Shorts · Reels · TikTok", "Instagram"])
        #expect(chips.map(\.supported) == [true, true, true, true, false, false])
        #expect(chips[4].members == ["shorts", "reels", "tiktok"] && chips[4].aspect == "9:16")
        let v = PlatformChips.make(vertical())
        #expect(v.first { $0.label.hasPrefix("Shorts") }?.supported == true && v.first { $0.label == "Instagram" }?.supported == false)
        #expect(v.prefix(5).allSatisfy { $0.supported })                                   // the newly supported one moves up
    }

    @Test func selectingAPlatformSetsItsFormatAndAnUnsupportedOneDoesNothing() {
        var f = CreateForm()
        let chips = PlatformChips.make(landscapeOnly)
        f.select(chips[0])
        #expect(f.platform == "youtube" && f.aspect == "16:9" && f.resolution == "1080p")
        f.select(chips[4])
        #expect(f.platform == "youtube")                                               // "Soon": not selectable
        var g = CreateForm(); g.select(PlatformChips.make(vertical())[3])
        #expect(g.platform == "other")
    }

    @Test func theRecommendationLineIsPlainWordsAndSaysCustomWhenOverridden() {
        var f = CreateForm(); f.select(PlatformChips.make(landscapeOnly)[0])
        #expect(f.recommendation(landscapeOnly) == "YouTube · Landscape 16:9 · 1080p")
        var g = f; g.aspect = "9:16"
        #expect(g.recommendation(vertical()) == "Custom · Vertical 9:16 · 1080p" && g.isCustom(vertical()))
        var h = f; h.resolution = "720p"
        #expect(h.recommendation(vertical()) == "Custom · Landscape 16:9 · 720p")
        #expect(f.canChangeFormat(vertical()) && !f.canChangeFormat(landscapeOnly))
    }

    @Test func theMoreOptionsLineSummarisesTheChoices() {
        var f = CreateForm()
        #expect(f.moreSummary(vertical()) == "Auto look · Subtitles on · Same language as description")
        f.look = .midnight; f.captions = false; f.language = "es"
        #expect(f.moreSummary(vertical()) == "Midnight look · Subtitles off · Español")
    }

    @Test func choicesStayInsideWhatTheServerLists() {
        var f = CreateForm(); f.aspect = "9:16"; f.resolution = "720p"; f.platform = "shorts"; f.language = "fr"
        f.normalize(landscapeOnly)
        #expect(f.aspect == "16:9" && f.resolution == "1080p" && f.platform == "other" && f.language == "auto")
        var ok = CreateForm(); ok.aspect = "9:16"; ok.resolution = "720p"; ok.language = "es"
        ok.normalize(vertical())
        #expect(ok.aspect == "9:16" && ok.resolution == "720p" && ok.language == "es")
    }

    @Test func defaultsAreRememberedPerPersonAndNeverTheirPromptOrPhotos() throws {
        let suite = UserDefaults(suiteName: "create-\(UUID())")!
        var f = CreateForm(); f.text = "secret prompt"; f.minutes = 2; f.look = .paper; f.captions = false; f.language = "es"; f.platform = "youtube"
        CreateDefaults(f).save(userID: "alice", defaults: suite)
        let again = CreateDefaults.load(userID: "alice", defaults: suite).form(vertical())
        #expect(again.minutes == 2 && again.look == .paper && !again.captions && again.language == "es" && again.platform == "youtube" && again.text.isEmpty)
        let bob = CreateDefaults.load(userID: "bob", defaults: suite).form(vertical())
        #expect(bob.minutes == 3 && bob.look == nil && bob.captions && bob.platform == "other")           // first-time defaults
        let data = try #require(suite.data(forKey: CreateDefaults.key("alice")))
        #expect(!String(decoding: data, as: UTF8.self).contains("secret"))
    }

    @Test func optionsCarryTheNewFieldsWithTodaysDefaults() {
        let o = CreateOptions()
        #expect(o.platform == "other" && o.aspect == "16:9" && o.resolution == "1080p" && o.language == "auto" && o.minutes == 3)
    }
}

@Suite struct RequestCheckTests {
    private let request = BriefRequest(prompt: "How bees make honey", options: CreateOptions(minutes: 3, platform: "youtube"), mediaCount: 4)

    @Test func theRequestBodyHasTheContractShape() throws {
        let obj = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(BriefRequest(prompt: "  A   prompt ", options: CreateOptions(minutes: 2, captions: false, platform: "youtube", language: "es"), mediaCount: 3, answers: [.chose("audience", IntakeOption(id: "kids", label: "Kids")), .other("tone", "warm"), .skipped("focus")]))) as? [String: Any])
        #expect(obj["prompt"] as? String == "A prompt" && obj["media_count"] as? Int == 3)
        let o = try #require(obj["options"] as? [String: Any])
        #expect(o["platform"] as? String == "youtube" && o["aspect"] as? String == "16:9" && o["resolution"] as? String == "1080p" && o["captions"] as? Bool == false && o["language"] as? String == "es" && o["target_minutes"] as? Double == 2)
        let a = try #require(obj["answers"] as? [[String: Any]])
        #expect(a[0]["option"] as? String == "kids" && a[0]["label"] == nil && a[1]["text"] as? String == "warm" && a[2]["skip"] as? Bool == true && a[2]["option"] == nil)
    }

    @Test func everyServerAnswerIsDecoded() {
        #expect(BriefResponse.decode(Data(#"{"status":"ok","brief":{"audience":"kids","summary":"For kids"}}"#.utf8)) == .ok(brief: ["audience": "kids", "summary": "For kids"]))
        #expect(BriefResponse.decode(Data(#"{"status":"not_supported","message":"m","suggestion":"s"}"#.utf8)) == .notSupported(message: "m", suggestion: "s"))
        #expect(BriefResponse.decode(Data(#"{"status":"blocked","message":"We can't make that."}"#.utf8)) == .blocked(message: "We can't make that."))
        #expect(BriefResponse.decode(Data(#"{"status":"paused","message":"Paused","retry_after":3600}"#.utf8)) == .paused(message: "Paused", retryAfter: 3600))
        #expect(BriefResponse.decode(Data(#"{"status":"nonsense"}"#.utf8)) == nil && BriefResponse.decode(Data("junk".utf8)) == nil)
        guard case .questions(let q)? = BriefResponse.decode(Data(#"{"status":"questions","questions":[{"id":"a","text":"Who?","options":[{"id":"k","label":"Kids"}],"allow_other":true},{"id":"b","text":"Tone?","options":[{"id":"c","label":"Calm"}]},{"id":"c","text":"Q3","options":[{"id":"x","label":"X"}]},{"id":"d","text":"Q4","options":[{"id":"x","label":"X"}]},{"id":"e","text":"empty","options":[]}]}"#.utf8)) else { Issue.record("expected questions"); return }
        #expect(q.map(\.id) == ["a", "b", "c"] && q[0].title == "Who?")                      // at most three, none without options
    }

    @Test func okOrQuestionsComeThrough() async {
        let ok = await CreateChecker(api: FakeCreateAPI(responses: [.ok(brief: ["tone": "calm"])])).check(request)
        #expect(ok == .proceed(brief: ["tone": "calm"]))
        let q = IntakeQuestion(id: "audience", title: "Who is this for?", options: [IntakeOption(id: "kids", label: "Kids")])
        #expect(await CreateChecker(api: FakeCreateAPI(responses: [.questions([q])])).check(request) == .questions([q]))
    }

    @Test func notSupportedBlockedAndPausedAreKeptApart() async {
        #expect(await CreateChecker(api: FakeCreateAPI(responses: [.notSupported(message: "m", suggestion: "s")])).check(request) == .notSupported(message: "m", suggestion: "s"))
        #expect(await CreateChecker(api: FakeCreateAPI(responses: [.blocked(message: "No.")])).check(request) == .blocked("No."))
        #expect(await CreateChecker(api: FakeCreateAPI(responses: [.paused(message: "p", retryAfter: 60)])).check(request) == .paused(message: "p", retryAfter: 60))
    }

    @Test func anyFailureMeansGoOnWithoutABrief() async {
        let api = FakeCreateAPI(); await api.setFails(true)
        #expect(await CreateChecker(api: api).check(request) == .proceed(brief: nil))
        #expect(await CreateChecker(api: FakeCreateAPI(responses: [.questions([])])).check(request) == .proceed(brief: nil))
    }

    @Test func aSlowCheckShowsTheSkeletonAfterTheShortBudgetAndGivesUpAtTheLongOne() async {
        let slowFlag = Flag()
        let slowButAnswers = FakeCreateAPI(responses: [.ok(brief: ["a": "b"])], delay: .milliseconds(80))
        let r1 = await CreateChecker(api: slowButAnswers, timeout: .milliseconds(400), slowAfter: .milliseconds(30)).check(request) { Task { await slowFlag.set() } }
        try? await Task.sleep(for: .milliseconds(20))
        #expect(r1 == .proceed(brief: ["a": "b"]))
        #expect(await slowFlag.value)                                                          // the skeleton was due before the answer came
        let fast = Flag()
        _ = await CreateChecker(api: FakeCreateAPI(), timeout: .milliseconds(400), slowAfter: .milliseconds(200)).check(request) { Task { await fast.set() } }
        try? await Task.sleep(for: .milliseconds(250))
        #expect(await !fast.value)                                                             // answered in time: no skeleton at all
        let never = FakeCreateAPI(responses: [.questions([IntakeQuestion(id: "a", title: "t", options: [IntakeOption(id: "o", label: "l")])])], delay: .seconds(5))
        let started = Date()
        let r2 = await CreateChecker(api: never, timeout: .milliseconds(60), slowAfter: .milliseconds(20)).check(request)
        #expect(r2 == .proceed(brief: nil) && Date().timeIntervalSince(started) < 2)           // the long budget ends the wait: just proceed
    }

    @Test func retryTextIsHumane() {
        #expect(RetryText.make(3600) == "Try again in about 1 hour." && RetryText.make(86_400) == "Try again in about 1 day." && RetryText.make(600) == "Try again in about 10 minutes." && RetryText.make(30) == "Try again in about a minute.")
        #expect(RetryText.make(nil) == nil && RetryText.make(0) == nil)
    }
}

private actor Flag { var value = false; func set() { value = true } }

@Suite struct IntakeFlowTests {
    private func flow() -> IntakeFlow {
        IntakeFlow([IntakeQuestion(id: "audience", title: "Who is this for?", options: [IntakeOption(id: "kids", label: "Kids"), IntakeOption(id: "adults", label: "Adults")]),
                    IntakeQuestion(id: "tone", title: "What tone?", options: [IntakeOption(id: "calm", label: "Calm")]),
                    IntakeQuestion(id: "focus", title: "Focus?", options: [IntakeOption(id: "honey", label: "Making honey")]),
                    IntakeQuestion(id: "extra", title: "Fourth?", options: [IntakeOption(id: "x", label: "X")])])
    }

    @Test func atMostThreeQuestionsAndEachTapAdvances() {
        var f = flow()
        #expect(f.questions.count == 3 && f.progressText == "Question 1 of 3" && f.current?.id == "audience")
        f.choose(IntakeOption(id: "kids", label: "Kids"))
        #expect(f.progressText == "Question 2 of 3" && !f.isComplete)
        f.other("  warm and slow  ")
        f.choose(IntakeOption(id: "honey", label: "Making honey"))
        #expect(f.isComplete && f.current == nil)
        #expect(f.payload.map(\.id) == ["audience", "tone", "focus"] && f.payload[1].text == "warm and slow" && f.payload[0].option == "kids")
    }

    @Test func skipYouDecideAndBackWork() {
        var f = flow()
        f.skip()
        #expect(f.index == 1 && f.canGoBack && f.answers["audience"]?.skip == true)
        f.back()
        #expect(f.index == 0 && !f.canGoBack)
        f.choose(IntakeOption(id: "adults", label: "Adults"))                              // answering again replaces the skip
        f.youDecide(); f.youDecide()
        #expect(f.isComplete && f.payload.map { $0.skip == true } == [false, true, true] && f.needsSummary && f.realAnswers.count == 1)
    }

    @Test func skippingEverythingNeedsNoSummary() {
        var f = flow(); f.skip(); f.skip(); f.skip()
        #expect(f.isComplete && !f.needsSummary && f.realAnswers.isEmpty)
    }

    @Test func makeItNowEndsTheQuestionsKeepingWhatWasAnswered() {
        var f = flow()
        f.choose(IntakeOption(id: "kids", label: "Kids"))
        f.makeItNow()
        #expect(f.isComplete && f.payload.map(\.id) == ["audience"] && f.needsSummary)
        var none = flow(); none.makeItNow()
        #expect(none.isComplete && !none.needsSummary)
    }

    @Test func aSummaryChipReopensItsQuestionAndAnsweringReturnsToTheSummary() {
        var f = flow()
        f.choose(IntakeOption(id: "kids", label: "Kids")); f.skip(); f.choose(IntakeOption(id: "honey", label: "Making honey"))
        #expect(f.chips(briefSummary: nil).map(\.text) == ["Kids", "Making honey"])
        #expect(f.chips(briefSummary: "For kids · Focus: Making honey").map(\.text) == ["For kids", "Focus: Making honey"])
        #expect(f.chips(briefSummary: "One · Two · Three").map(\.text) == ["Kids", "Making honey"])      // a summary that does not match the answers is not trusted
        f.edit("audience")
        #expect(f.current?.id == "audience" && !f.isComplete)
        f.choose(IntakeOption(id: "adults", label: "Adults"))
        #expect(f.isComplete && f.answers["audience"]?.option == "adults")
    }
}

extension CoreTests {
    @Test func generateCarriesTheCreationOptionsAndTheBrief() async throws {
        nonisolated(unsafe) var body: [String: Any] = [:]
        StubProtocol.handler = { req in body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:]; return (202, Data(#"{"video_id":"abc"}"#.utf8)) }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r", options: CreateOptions(minutes: 2, look: .paper, captions: false, platform: "youtube", aspect: "9:16", resolution: "720p", language: "es"), brief: ["audience": "kids", "summary": "For kids"])
        #expect(body["platform"] as? String == "youtube" && body["aspect"] as? String == "9:16" && body["resolution"] as? String == "720p" && body["language"] as? String == "es" && body["captions"] as? Bool == false)
        #expect(body["brief"] as? [String: String] == ["audience": "kids", "summary": "For kids"])
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r")
        #expect(body["language"] == nil && body["brief"] == nil && body["captions"] == nil && body["platform"] as? String == "other")      // auto language, no brief, captions on: not sent
    }

    @Test func generateMapsBlockedAndPausedAnswers() async throws {
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        StubProtocol.handler = { _ in (400, Data(#"{"status":"blocked","message":"We can't make this one."}"#.utf8)) }
        await #expect(throws: APIError.blocked("We can't make this one.")) { _ = try await api.startGeneration(prompt: "A long enough prompt", clientRequestID: "r") }
        StubProtocol.handler = { _ in (400, Data(#"{"message":"Too short"}"#.utf8)) }
        await #expect(throws: APIError.invalid("Too short")) { _ = try await api.startGeneration(prompt: "A long enough prompt", clientRequestID: "r") }
        StubProtocol.handler = { _ in (429, Data(#"{"status":"paused","message":"Paused for now.","retry_after":3600}"#.utf8)) }
        await #expect(throws: APIError.paused("Paused for now.", retryAfter: 3600)) { _ = try await api.startGeneration(prompt: "A long enough prompt", clientRequestID: "r") }
        StubProtocol.handler = { _ in (429, Data(#"{"message":"Daily limit"}"#.utf8)) }
        await #expect(throws: APIError.quota("Daily limit")) { _ = try await api.startGeneration(prompt: "A long enough prompt", clientRequestID: "r") }
    }

    @Test func theRealClientReadsCapabilitiesAndTheCheckAndDegradesOnMissingEndpoints() async throws {
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        nonisolated(unsafe) var seen: [URLRequest] = []
        StubProtocol.handler = { req in seen.append(req); return (200, Data(#"{"aspects":[{"id":"16:9","label":"Landscape","ready":true}],"resolutions":[{"id":"1080p"}],"platforms":[],"intake":true}"#.utf8)) }
        let caps = try await api.capabilities()
        #expect(caps.intake && seen.last?.url?.path == "/prod/users/user-1/capabilities")
        StubProtocol.handler = { req in seen.append(req); return (200, Data(#"{"status":"questions","questions":[{"id":"a","text":"Who?","options":[{"id":"k","label":"Kids"}]}]}"#.utf8)) }
        let r = try await api.checkRequest(BriefRequest(prompt: "A long enough prompt", options: CreateOptions(), mediaCount: 0))
        guard case .questions(let q) = r else { Issue.record("expected questions"); return }
        #expect(q.count == 1 && seen.last?.url?.path == "/prod/users/user-1/videos/brief" && seen.last?.httpMethod == "POST")
        StubProtocol.handler = { _ in (429, Data(#"{"status":"paused","message":"Paused","retry_after":600}"#.utf8)) }
        #expect(try await api.checkRequest(BriefRequest(prompt: "A long enough prompt", options: CreateOptions(), mediaCount: 0)) == .paused(message: "Paused", retryAfter: 600))
        for code in [404, 403, 500] {
            StubProtocol.handler = { _ in (code, Data()) }
            await #expect(throws: APIError.self) { _ = try await api.capabilities() }          // the app falls back to 16:9 and 1080p
            await #expect(throws: APIError.self) { _ = try await api.checkRequest(BriefRequest(prompt: "A long enough prompt", options: CreateOptions(), mediaCount: 0)) }   // the checker turns this into "proceed"
        }
    }
}
