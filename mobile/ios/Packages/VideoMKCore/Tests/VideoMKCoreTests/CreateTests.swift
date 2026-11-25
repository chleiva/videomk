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

@Suite struct VideoShapeTests {
    @Test func listAndGetResponsesCarryTheVideoShape() throws {
        let v = try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"a","status":"COMPLETE","aspect":"9:16","resolution":"1080p"}"#.utf8))
        #expect(v.aspect == "9:16" && v.resolution == "1080p" && v.isPortrait && abs(v.aspectRatio - 0.5625) < 0.001)
        let old = try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"b","status":"COMPLETE"}"#.utf8))
        #expect(old.aspect == nil && !old.isPortrait && abs(old.aspectRatio - 16.0 / 9.0) < 0.001)       // before formats existed: landscape
        #expect(VideoItem.ratio("1:1") == 1 && VideoItem.ratio("4:5") == 0.8 && VideoItem.ratio("nonsense") == 16.0 / 9.0 && VideoItem.ratio("0:9") == 16.0 / 9.0)
    }
}

@Suite struct StableImageTests {
    private func url(_ video: String, sig: String) -> URL { URL(string: "https://bucket.s3.eu-west-1.amazonaws.com/u/me/videos/\(video)/preview.gif?X-Amz-Date=20261125T10&X-Amz-Signature=\(sig)")! }

    @Test func theKeyIgnoresTheSignatureButNotTheVideo() {
        #expect(ImageKey.stable(url("v1", sig: "aaa")) == ImageKey.stable(url("v1", sig: "bbb")))
        #expect(ImageKey.stable(url("v1", sig: "aaa")) != ImageKey.stable(url("v2", sig: "aaa")))
        #expect(ImageKey.stable(url("v1", sig: "a")) == "bucket.s3.eu-west-1.amazonaws.com/u/me/videos/v1/preview.gif")
        #expect(ImageKey.stable(nil as URL?) == nil)
    }

    private func item(_ id: String, _ status: VideoStatus = .complete, sig: String, title: String? = nil) -> VideoItem {
        VideoItem(id: id, status: status, title: title ?? id, durationSeconds: 80, createdAt: Date(timeIntervalSince1970: 1_800_000_000), videoURL: url(id, sig: sig), previewGifURL: url(id, sig: sig))
    }

    @Test func aRefreshWithIdenticalDataChangesNothing() {
        var stamps: [String: Date] = [:]
        let t0 = Date(timeIntervalSince1970: 1_800_000_000)
        let first = VideoListMerge.merge(old: [], fresh: [item("a", .running(.writing), sig: "1"), item("b", sig: "1"), item("c", sig: "1")], linkStamp: &stamps, now: t0)
        #expect(first.changed && first.items.count == 3)
        // four seconds later: every link has a new signature, nothing else moved
        let again = VideoListMerge.merge(old: first.items, fresh: [item("a", .running(.writing), sig: "2"), item("b", sig: "2"), item("c", sig: "2")], linkStamp: &stamps, now: t0.addingTimeInterval(4))
        #expect(!again.changed && again.items == first.items)
        #expect(zip(again.items, first.items).allSatisfy { $0.previewGifURL == $1.previewGifURL })             // the very same instances, links included
    }

    @Test func onlyTheVideoThatChangedIsReplaced() {
        var stamps: [String: Date] = [:]
        let t0 = Date(timeIntervalSince1970: 1_800_000_000)
        let first = VideoListMerge.merge(old: [], fresh: [item("a", .running(.writing), sig: "1"), item("b", sig: "1")], linkStamp: &stamps, now: t0)
        let next = VideoListMerge.merge(old: first.items, fresh: [item("a", .running(.voiceAndVisuals), sig: "2"), item("b", sig: "2")], linkStamp: &stamps, now: t0.addingTimeInterval(4))
        #expect(next.changed && next.items[0].status == .running(.voiceAndVisuals) && next.items[1] == first.items[1])
        let title = VideoListMerge.merge(old: next.items, fresh: [item("a", .running(.voiceAndVisuals), sig: "3", title: "Renamed"), item("b", sig: "3")], linkStamp: &stamps, now: t0.addingTimeInterval(8))
        #expect(title.changed && title.items[0].title == "Renamed" && title.items[1] == first.items[1])
    }

    @Test func orderAndCountChangesAreSeenAndLinksAreRefreshedBeforeTheyExpire() {
        var stamps: [String: Date] = [:]
        let t0 = Date(timeIntervalSince1970: 1_800_000_000)
        let first = VideoListMerge.merge(old: [], fresh: [item("a", sig: "1"), item("b", sig: "1")], linkStamp: &stamps, now: t0)
        #expect(VideoListMerge.merge(old: first.items, fresh: [item("b", sig: "1"), item("a", sig: "1")], linkStamp: &stamps, now: t0).changed)       // order
        #expect(VideoListMerge.merge(old: first.items, fresh: [item("new", sig: "1"), item("a", sig: "1"), item("b", sig: "1")], linkStamp: &stamps, now: t0).changed)   // a new video
        let late = VideoListMerge.merge(old: first.items, fresh: [item("a", sig: "9"), item("b", sig: "9")], linkStamp: &stamps, now: t0.addingTimeInterval(31 * 60))
        #expect(late.changed && ImageKey.stable(late.items[0].previewGifURL) == ImageKey.stable(first.items[0].previewGifURL) && late.items[0].previewGifURL != first.items[0].previewGifURL)   // new signature after 30 minutes
    }
}

@Suite struct PlatformRecommendationTests {
    private let caps = FakeCreateAPI.richCapabilities
    private func chip(_ id: String) -> PlatformChip { PlatformChips.make(caps).first { $0.members.contains(id) }! }

    @Test func lengthsComeFromTheServerPresetsWithShortOnesFirst() throws {
        #expect(caps.lengthPresets == [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12])
        #expect([0.25, 0.5, 0.75, 1, 2, 12].map(LengthLabel.chip) == ["15 s", "30 s", "45 s", "1 min", "2 min", "12 min"])
        #expect(LengthLabel.clock(2.3333) == "2:20" && LengthLabel.spoken(0.75) == "45 seconds" && LengthLabel.spoken(1) == "1 minute")
        let json = #"{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}],"platforms":[],"lengths":{"min_minutes":0.25,"max_minutes":12,"presets":[12,0.5,0.25,99,0]}}"#
        let c = try JSONDecoder().decode(CreateCapabilities.self, from: Data(json.utf8))
        #expect(c.lengthPresets == [0.25, 0.5, 12])                       // sorted, nothing above the maximum or at zero
        #expect(CreateCapabilities.fallback.lengthPresets == [1, 2, 3, 5, 8, 12])
        #expect(try JSONDecoder().decode(CreateCapabilities.self, from: Data(#"{"aspects":[{"id":"16:9","ready":true}]}"#.utf8)).lengthPresets == [1, 2, 3, 5, 8, 12])   // no `lengths`: the old six
    }

    @Test func creditsFollowCeilingWithAMinimumOfOne() {
        let credits = [0.25, 0.5, 0.75, 1, 2, 3].map { ComposerPlan.credits(forMinutes: $0) }
        #expect(credits == [1, 1, 1, 1, 2, 3])
        #expect(CreateOptions(minutes: 61.0 / 60).credits == 2)                 // 61 seconds costs 2
        var f = CreateForm(); f.setMinutes(0.25)
        #expect(ComposerPlan.status(text: "A story about a lighthouse keeper", balance: 1, options: f.options, lengths: caps.lengthPresets).message == "1 credit · you'll have 0 left")
    }

    @Test func linkedInAndXRecommendDifferentlyAndVisibly() {
        var f = CreateForm()
        f.select(chip("linkedin"))
        #expect(f.aspect == "4:5" && f.resolution == "1080p" && f.minutes == 1)
        #expect(f.recommendation(caps) == "LinkedIn · Portrait 4:5 · 1080p · about 1 min")
        f.select(chip("x"))
        #expect(f.aspect == "16:9" && f.minutes == 0.75)
        #expect(f.recommendation(caps) == "X · Landscape 16:9 · 1080p · about 45 s")
        f.select(chip("shorts"))
        #expect(f.aspect == "9:16" && f.minutes == 0.75 && f.recommendation(caps).hasPrefix("Shorts · Reels · TikTok · Vertical 9:16"))
    }

    @Test func aLengthChosenByHandSurvivesAPlatformPick() {
        var f = CreateForm()
        f.setMinutes(5)
        f.select(chip("linkedin"))
        #expect(f.aspect == "4:5" && f.minutes == 5)                            // the format follows, the length stays
        #expect(f.recommendation(caps) == "LinkedIn · Portrait 4:5 · 1080p · about 1 min")      // and the recommendation is still shown
        var fresh = CreateForm(); fresh.select(chip("linkedin")); fresh.select(chip("x"))
        #expect(fresh.minutes == 0.75)                                          // picks alone never count as a chosen length
    }

    @Test func otherFormatsOfAPlatformAreSecondaryChoicesThatSwitchOnlyTheFormat() {
        var f = CreateForm(); f.select(chip("linkedin"))
        #expect(f.alsoWorks(caps).map(\.name) == ["Square", "Landscape"])
        f.aspect = "1:1"
        #expect(!f.isCustom(caps) && f.minutes == 1 && f.recommendation(caps) == "LinkedIn · Square 1:1 · 1080p")         // still LinkedIn, same length
        #expect(f.alsoWorks(caps).map(\.name) == ["Portrait", "Landscape"])
        f.aspect = "9:16"
        #expect(f.isCustom(caps) && f.recommendation(caps).hasPrefix("Custom"))                                            // not one the platform endorses
    }

    @Test func overThePlatformsLimitAGentleHintOffersItsLongestPreset() {
        var f = CreateForm(); f.select(chip("x")); f.setMinutes(3)
        let hint = f.maxLengthHint(caps)
        #expect(hint?.text == "X allows up to 2:20." && hint?.fixMinutes == 2)                    // the longest preset within 2:20
        f.setMinutes(2); #expect(f.maxLengthHint(caps) == nil)
        f.select(chip("youtube")); f.setMinutes(12); #expect(f.maxLengthHint(caps) == nil)       // no limit
        f.select(chip("instagram_feed")); f.setMinutes(0.75)
        #expect(f.maxLengthHint(caps) == nil)                                                    // 45 s is within a minute
        f.setMinutes(2); #expect(f.maxLengthHint(caps)?.fixMinutes == 1)
    }

    @Test func rememberedChoicesNeverOverrideAnExplicitNewPick() {
        var d = CreateDefaults(); d.platform = "youtube"; d.minutes = 3
        var f = d.form(caps)
        #expect(f.platform == "youtube" && f.minutes == 3 && !f.userTouched)
        f.select(chip("linkedin"))
        #expect(f.userTouched && f.platform == "linkedin" && f.minutes == 1)                     // the pick wins over what was remembered
        var g = d.form(caps); g.setMinutes(0.5)
        #expect(g.userTouched && g.lengthTouched)
        let short = CreateDefaults({ var x = CreateForm(); x.minutes = 0.25; return x }())
        #expect(short.form(caps).minutes == 0.25)                                                // a short length can be remembered
        #expect(short.form(.fallback).minutes == 3)                                              // but not if the server no longer lists it
    }

    @Test func thePlatformNoteSurvivesDecoding() throws {
        let json = #"{"aspects":[{"id":"4:5","ready":true}],"resolutions":[{"id":"1080p"}],"platforms":[{"id":"linkedin","label":"LinkedIn","aspect":"4:5","resolution":"1080p","note":"Portrait 4:5 · 1080p · about 1 min","recommended_minutes":1,"max_minutes":10,"other_aspects":["1:1","16:9"]},{"id":"x","label":"X","aspect":"16:9","resolution":"1080p","recommended_minutes":0.75,"max_minutes":null,"other_aspects":[]}]}"#
        let c = try JSONDecoder().decode(CreateCapabilities.self, from: Data(json.utf8))
        let li = c.platforms[0], x = c.platforms[1]
        #expect(li.recommendedMinutes == 1 && li.maxMinutes == 10 && li.otherAspects == ["1:1", "16:9"] && li.note == "Portrait 4:5 · 1080p · about 1 min")
        #expect(x.recommendedMinutes == 0.75 && x.maxMinutes == nil && x.note == nil)
    }
}

@Suite struct ChipFitTests {
    private let longEN = "Evolución biológica y primeros homínidos"       // 40 characters, the worst case from the server
    private let longES = "Civilizaciones antiguas hasta la edad media"   // 43

    @Test func shortLabelsStayOnOneLine() {
        #expect(ChipFit.mode(label: "Kids", availableWidth: 350) == .singleLine)
        #expect(ChipFit.mode(label: "Make a general one", availableWidth: 350) == .singleLine)
    }

    @Test func longLabelsWrapOrTakeTheWholeRowAndNeverStayOnOneLine() {
        for label in [longEN, longES] {
            for width in [320.0, 350, 402] {            // iPhone SE up to Pro Max
                #expect(ChipFit.mode(label: label, availableWidth: width) != .singleLine, "\(label) at \(width)")
            }
        }
        #expect(ChipFit.lines(label: longEN, availableWidth: 320) == 2)
    }

    @Test func narrowerContainersNeedMoreLines() {
        let wide = ChipFit.lines(label: longES, availableWidth: 400), narrow = ChipFit.lines(label: longES, availableWidth: 170)
        #expect(narrow > wide)
        #expect(ChipFit.mode(label: longES, availableWidth: 170) == .fullWidth)
        #expect(ChipFit.lines(label: "", availableWidth: 300) == 1)
    }
}

@Suite struct FourKTests {
    private let caps = FakeCreateAPI.fourKCapabilities
    private func chip(_ id: String) -> PlatformChip { PlatformChips.make(caps).first { $0.members.contains(id) }! }
    private func form() -> CreateForm { var f = CreateForm(); f.normalize(caps); return f }

    @Test func thePriceIsTheStartedMinutesTimesTheMultiplier() {
        var f = form()
        f.setMinutes(3); #expect(f.options.credits == 3)
        f.setResolution("2160p"); #expect(f.options.credits == 6 && f.creditsMultiplier == 2)
        f.setMinutes(0.25); #expect(f.options.credits == 2)                      // 15 seconds at 4K
        f.setMinutes(12); #expect(f.options.credits == 24)
        f.setResolution("720p"); #expect(f.options.credits == 12)
        #expect(ComposerPlan.credits(forMinutes: 61.0 / 60, multiplier: 2) == 4)
        f.setMinutes(3); f.setResolution("2160p")
        let s = ComposerPlan.status(text: "A story about a lighthouse keeper", balance: 5, options: f.options, lengths: caps.lengthPresets)
        #expect(!s.canSend && s.message == "Needs 6 credits, you have 5")
        #expect(s.fix == .useMinutes(2, credits: 4))                              // the fix chip's price is doubled too
    }

    @Test func decodingWithTheNewFields() throws {
        let json = #"{"aspects":[{"id":"16:9","ready":true},{"id":"9:16","ready":true}],"resolutions":[{"id":"720p","label":"720p","credits_multiplier":1,"aspects":["16:9","9:16"]},{"id":"2160p","label":"4K","credits_multiplier":2,"aspects":["16:9"],"note":"4K (2160p) costs twice the credits.","future":{"x":1}}],"platforms":[{"id":"youtube","label":"YouTube","aspect":"16:9","resolution":"1080p","supports_4k":true,"note_4k":null},{"id":"tiktok","label":"TikTok","aspect":"9:16","resolution":"1080p","supports_4k":false,"note_4k":"TikTok publishes at 1080p or lower."}]}"#
        let c = try JSONDecoder().decode(CreateCapabilities.self, from: Data(json.utf8))
        #expect(c.resolutions.map(\.id) == ["720p", "2160p"] && c.resolutionLabel("2160p") == "4K" && c.multiplier("2160p") == 2 && c.multiplier("720p") == 1)
        #expect(c.resolution("2160p")?.note == "4K (2160p) costs twice the credits." && c.resolution("2160p")?.aspects == ["16:9"])
        #expect(c.platforms[0].supports4K && c.platforms[0].note4K == nil && !c.platforms[1].supports4K && c.platforms[1].note4K == "TikTok publishes at 1080p or lower.")
        #expect(c.isSupported(aspect: "16:9", resolution: "2160p") && !c.isSupported(aspect: "9:16", resolution: "2160p"))
    }

    @Test func decodingAnOlderServerWithoutThem() throws {
        let json = #"{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"720p"},{"id":"1080p","label":"1080p"}],"platforms":[{"id":"youtube","label":"YouTube","aspect":"16:9","resolution":"1080p"}]}"#
        let c = try JSONDecoder().decode(CreateCapabilities.self, from: Data(json.utf8))
        #expect(c.resolutions.allSatisfy { $0.creditsMultiplier == 1 && $0.aspects.isEmpty && $0.note == nil } && c.isSupported(aspect: "16:9", resolution: "1080p"))
        #expect(!c.platforms[0].supports4K && c.platforms[0].note4K == nil)
        var f = CreateForm(); f.normalize(c); f.select(PlatformChips.make(c).first { $0.id == "youtube" }!)
        #expect(f.options.credits == 3 && f.fourKAdvice(c) == nil && f.resolutionChoices(c).map(\.id) == ["720p", "1080p"])      // nothing changes without 4K
        let odd = try JSONDecoder().decode(CreateCapabilities.Resolution.self, from: Data(#"{"id":"2160p","credits_multiplier":"two","aspects":7}"#.utf8))
        #expect(odd.creditsMultiplier == 1 && odd.aspects.isEmpty)                // wrong types never fail decoding
    }

    @Test func fourKOnAPlatformThatDoesNotDeliverItIsRecommendedAgainstButNeverBlocked() {
        var f = form()
        f.select(chip("youtube")); #expect(f.resolution == "1080p")               // a platform never picks 4K
        f.setResolution("2160p")
        #expect(f.fourKAdvice(caps) == nil && f.resolutionNote(caps)?.hasPrefix("4K (2160p) costs twice") == true)
        #expect(f.recommendation(caps) == "YouTube · Landscape 16:9 · 4K")
        f.select(chip("tiktok"))
        #expect(f.resolution == "2160p")                                           // the explicit choice survives the platform change
        let advice = f.fourKAdvice(caps)
        #expect(advice?.text.contains("publishes at 1080p or lower") == true && advice?.useResolution == "1080p")
        #expect(ComposerPlan.status(text: "A story about a lighthouse keeper", balance: 10, options: f.options, lengths: caps.lengthPresets).canSend)   // still allowed
        f.setResolution("1080p"); #expect(f.fourKAdvice(caps) == nil)
        f.setResolution("2160p"); f.select(chip("other")); #expect(f.fourKAdvice(caps) == nil)      // "Just a video" is fine
        var fresh = form(); fresh.select(chip("linkedin")); fresh.select(chip("youtube"))
        #expect(fresh.resolution == "1080p")
    }

    @Test func aResolutionIsOfferedOnlyForShapesItCanBeMadeIn() {
        var c = caps
        c.resolutions = c.resolutions.map { $0.id == "2160p" ? .init(id: "2160p", label: "4K", creditsMultiplier: 2, aspects: ["16:9"]) : $0 }
        var f = CreateForm(); f.normalize(c); f.setResolution("2160p")
        #expect(f.resolutionChoices(c).map(\.id) == ["720p", "1080p", "2160p"])
        f.aspect = "9:16"; f.normalize(c)
        #expect(f.resolutionChoices(c).map(\.id) == ["720p", "1080p"] && f.resolution == "1080p" && f.options.credits == 3)
    }

    @Test func fourKIsNeverARememberedDefault() {
        var f = form(); f.setResolution("2160p")
        let again = CreateDefaults(f).form(caps)
        #expect(again.resolution == "1080p" && again.options.credits == 3 && !again.resolutionTouched)
    }
}
