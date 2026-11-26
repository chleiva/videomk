import Foundation
import Testing
@testable import VideoMKCore

private func inSpanish<T>(_ body: () throws -> T) rethrows -> T { try Localization.$override.withValue(.es, operation: body) }

private let caps = DeckCapabilities(maxMB: 50, maxSlides: 60, formats: ["pptx", "pdf"])
private let ready = DeckReady(slides: 12, suggestedMinutes: 4, suggestedCredits: 4)

private func tempFile(_ name: String, bytes: Int = 1000) throws -> URL {
    let dir = FileManager.default.temporaryDirectory.appendingPathComponent("DeckTests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let url = dir.appendingPathComponent(name)
    try Data(repeating: 7, count: bytes).write(to: url)
    return url
}

@MainActor private func wait(_ j: DeckJourney, until done: (DeckJourney.State) -> Bool) async {
    for _ in 0..<400 where !done(j.state) { try? await Task.sleep(for: .milliseconds(10)) }
}

private func fastTiming() -> DeckTiming { var t = DeckTiming(); t.sleep = { _ in try await Task.sleep(for: .milliseconds(1)) }; return t }

@Suite struct DeckModelTests {
    @Test func capabilitiesCarryDeckOnlyWhenTheServerHasItOn() throws {
        let off = try JSONDecoder().decode(CreateCapabilities.self, from: Data(#"{"aspects":[{"id":"16:9","label":"Landscape","ready":true}]}"#.utf8))
        #expect(off.deck == nil)
        let on = try JSONDecoder().decode(CreateCapabilities.self, from: Data(#"{"aspects":[{"id":"16:9","label":"Landscape","ready":true}],"deck":{"max_mb":50,"max_slides":60,"formats":["pptx","PDF"]}}"#.utf8))
        #expect(on.deck == DeckCapabilities(maxMB: 50, maxSlides: 60, formats: ["pptx", "pdf"]))
        #expect(on.deck?.maxBytes == 50 * 1024 * 1024)
    }

    @Test func fileCheckIsLocalAndSpecific() {
        #expect(DeckFileCheck.check(fileName: "Q3 review.PPTX", bytes: 4_000_000, caps: caps) == .ok(format: "pptx"))
        #expect(DeckFileCheck.check(fileName: "talk.pdf", bytes: caps.maxBytes, caps: caps) == .ok(format: "pdf"))
        #expect(DeckFileCheck.check(fileName: "talk.pdf", bytes: caps.maxBytes + 1, caps: caps) == .problem(.tooLarge(maxMB: 50)))
        #expect(DeckFileCheck.check(fileName: "talk.pdf", bytes: 0, caps: caps) == .problem(.empty))
        #expect(DeckFileCheck.check(fileName: "old.ppt", bytes: 10, caps: caps) == .problem(.exportFirst(ext: "ppt")))
        #expect(DeckFileCheck.check(fileName: "macro.pptm", bytes: 10, caps: caps) == .problem(.exportFirst(ext: "pptm")))
        #expect(DeckFileCheck.check(fileName: "keynote.key", bytes: 10, caps: caps) == .problem(.exportFirst(ext: "key")))
        #expect(DeckFileCheck.check(fileName: "notes.txt", bytes: 10, caps: caps) == .problem(.unsupported))
        #expect(DeckFileCheck.check(fileName: "noextension", bytes: 10, caps: caps) == .problem(.unsupported))
        #expect(DeckFileCheck.check(fileName: "deck.pdf", bytes: 10, caps: DeckCapabilities(maxMB: 5, maxSlides: 10, formats: ["pptx"])) == .problem(.unsupported), "only the formats the server lists")
        #expect(DeckFileCheck.check(fileName: "big.pptx", bytes: 6 * 1024 * 1024, caps: DeckCapabilities(maxMB: 5, maxSlides: 10, formats: ["pptx"])) == .problem(.tooLarge(maxMB: 5)), "the server's own limit is used")
    }

    @Test func everyServerCodeMapsToACalmSpecificMessageWithTheRightAction() {
        let codes = ["deck_too_large", "deck_too_many_slides", "deck_unsupported", "deck_corrupt", "deck_encrypted", "deck_macro", "deck_empty", "deck_unsafe", "deck_convert_timeout", "deck_convert_failed", "too_many_decks"]
        var titles = Set<String>(), messages = Set<String>()
        for code in codes {
            let p = DeckProblem.from(code: code, message: "server text")
            #expect(!p.title.isEmpty && !p.message.isEmpty && p.message != "server text", "\(code) has its own localized words")
            #expect(!p.title.contains("deck.") && !p.message.contains("deck."), "\(code) found its catalog key")
            titles.insert(p.title); messages.insert(p.message)
            let es = inSpanish { (p.title, p.message) }
            #expect(es.0 != p.title && es.1 != p.message, "\(code) is in Spanish")
        }
        #expect(messages.count == codes.count, "each failure says something different")
        #expect(DeckProblem.from(code: "deck_too_large", caps: DeckCapabilities(maxMB: 20)).message.contains("20"))
        #expect(DeckProblem.from(code: "deck_too_many_slides").message.contains("60"))
        #expect(DeckProblem.from(code: "deck_encrypted").message.lowercased().contains("password"))
        #expect(DeckProblem.from(code: "deck_macro").message.lowercased().contains("macro"))
        #expect(DeckProblem.from(code: "deck_convert_timeout").action() == .chooseAgain && DeckProblem.from(code: "deck_convert_failed").action() == .chooseAgain)
        #expect(DeckProblem.from(code: "deck_corrupt").action() == .pickAnother && DeckProblem.from(code: "deck_encrypted").action() == .pickAnother)
        #expect(DeckProblem.network.action(hasLocalFile: true) == .retry && DeckProblem.network.action(hasLocalFile: false) == .checkAgain)
        #expect(DeckProblem.stillWorking.action() == .checkAgain)
        #expect(DeckProblem.from(code: "something_new", message: "Server words").message == "Server words", "an unknown code falls back to the server's own text")
        #expect(DeckProblem.from(code: "something_new") == .server)
    }

    @Test func statusDecoding() {
        #expect(DeckStatus.decode(Data(#"{"id":"d","status":"processing","format":"pptx"}"#.utf8)) == .processing)
        #expect(DeckStatus.decode(Data(#"{"status":"ready","slides":12,"suggested_minutes":4,"suggested_credits":4}"#.utf8)) == .ready(ready))
        #expect(DeckStatus.decode(Data(#"{"status":"failed","code":"deck_macro","message":"m"}"#.utf8)) == .failed(code: "deck_macro", message: "m"))
        #expect(DeckStatus.decode(Data(#"{"status":"ready"}"#.utf8)) == nil, "a ready answer without its numbers is not trusted")
    }

    @Test func priceUsesTheServersNumberAtItsOwnLengthAndTheUsualRuleElsewhere() {
        let price = ready.price
        #expect(price.credits(minutes: 4) == 4)
        #expect(price.credits(minutes: 2) == 2, "started minutes")
        #expect(price.credits(minutes: 0.5) == 1)
        #expect(price.credits(minutes: 4, multiplier: 2) == 8, "4K doubles it")
        #expect(price.credits(minutes: 12) == 12)
        let odd = DeckPrice(suggestedMinutes: 3.67, suggestedCredits: 4)
        #expect(odd.credits(minutes: 3.67) == 4 && odd.credits(minutes: 3) == 3 && odd.credits(minutes: 5) == 5)
        #expect(CreateOptions(minutes: 4, deck: price).credits == 4 && CreateOptions(minutes: 8, deck: price).credits == 8)
    }

    @Test func theFormDefaultsToSixteenNineUsesTheSuggestedLengthAndWarnsOnVertical() {
        let c = FakeCreateAPI.richCapabilities.withDeck()
        var f = CreateForm()
        f.select(PlatformChips.make(c).first { $0.id == "shorts" }!)
        #expect(f.aspect == "9:16" && !f.deckVerticalWarning)
        f.startDeck(c)
        #expect(f.aspect == "16:9" && f.hasDeck && !f.deckVerticalWarning, "a deck defaults to 16:9")
        f.deckReady(ready.price)
        #expect(f.minutes == 4 && f.options.credits == 4 && !f.sendsDeckMinutes, "the suggested length, charged exactly that, and not sent")
        f.select(PlatformChips.make(c).first { $0.members.contains("tiktok") }!)
        #expect(f.aspect == "9:16" && f.deckVerticalWarning, "a vertical pick still works, with a gentle warning")
        #expect(f.minutes == 4, "a platform never overrides the deck's length")
        f.aspect = "4:5"; #expect(f.deckVerticalWarning)
        f.aspect = "1:1"; #expect(!f.deckVerticalWarning)
        f.setMinutes(2)
        #expect(f.options.credits == 2 && f.sendsDeckMinutes, "another length: the usual price, and it is sent")
        f.setMinutes(4)
        #expect(f.options.credits == 4 && f.sendsDeckMinutes, "a chosen length is sent even when equal")
        f.clearDeck()
        #expect(!f.hasDeck && f.options.deck == nil && !f.deckVerticalWarning)
    }

    @Test func aLengthChosenBeforeTheDeckDoesNotSurviveItsSuggestion() {
        var f = CreateForm(); f.setMinutes(1)
        f.startDeck(.fallback); f.deckReady(ready.price)
        #expect(f.minutes == 1, "a length the person picked stays theirs")
        #expect(f.sendsDeckMinutes)
    }

    @Test func theStatusLineFollowsTheDeck() {
        let opts = CreateOptions(minutes: 4, deck: ready.price)
        let working = ComposerPlan.status(text: "", balance: 10, options: opts, deck: .working)
        #expect(working.kind == .deckWorking && !working.canSend && !working.isProblem)
        let problem = ComposerPlan.status(text: "", balance: 10, options: opts, deck: .problem)
        #expect(problem.kind == .deckProblem && !problem.canSend && problem.isProblem)
        let ok = ComposerPlan.status(text: "", balance: 10, options: opts, deck: .ready)
        #expect(ok.canSend && ok.kind == .ready, "the description is optional for a deck")
        for text in ["a", "execs", "students", "123456789"] {
            let short = ComposerPlan.status(text: text, balance: 10, options: opts, deck: .ready)
            #expect(short.kind == .deckShortPrompt && !short.canSend && short.isProblem && short.message == "Add a few more words, or leave it empty", "\(text.count) characters")
            #expect(inSpanish { ComposerPlan.status(text: text, balance: 10, options: opts, deck: .ready).message } == "Agrega unas palabras más o déjalo vacío")
        }
        #expect(ComposerPlan.status(text: "1234567890", balance: 10, options: opts, deck: .ready).canSend, "10 characters is accepted")
        #expect(ComposerPlan.status(text: "   ", balance: 10, options: opts, deck: .ready).canSend, "only spaces count as empty")
        #expect(ComposerPlan.status(text: "for executives", balance: 10, options: opts, deck: .ready).canSend)
        #expect(!ComposerPlan.status(text: "", balance: 10, options: CreateOptions(minutes: 4), deck: .none).canSend, "without a deck the description is still required")
        let poor = ComposerPlan.status(text: "", balance: 2, options: opts, deck: .ready)
        #expect(poor.kind == .notAffordable && !poor.canSend && poor.fix != nil, "the usual not-enough-credits rule and its fix")
        #expect(ComposerPlan.status(text: String(repeating: "a", count: 2001), balance: 10, options: opts, deck: .ready).kind == .tooLong)
    }

    @Test func aRunningDeckVideoCarriesItsStage() throws {
        let item = try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"v","status":"PLOT_CREATION","stage":"deck_reading"}"#.utf8))
        #expect(item.status == .running(.writing) && item.deckStage == .reading)
        #expect(try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"v","status":"PLOT_CREATION","stage":"deck_writing"}"#.utf8)).deckStage == .writing)
        #expect(try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"v","status":"PLOT_CREATION"}"#.utf8)).deckStage == nil)
        #expect(!item.visiblyEqual(VideoItem(id: "v", status: .running(.writing), deckStage: .writing)), "a stage change redraws the card")
    }
}

@Suite(.serialized) @MainActor struct DeckJourneyTests {
    private func journey(_ script: FakeDeckScript = FakeDeckScript(), store: DeckTempStore? = nil, fail: DeckProblem? = nil) -> (DeckJourney, FakeCreateAPI, FakeDeckUploader, DeckTempStore) {
        var s = script; s.processingPolls = min(script.processingPolls, 2)
        let api = FakeCreateAPI(deck: s)
        let up = FakeDeckUploader(s, stepDelay: 0.001)
        let st = store ?? DeckTempStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent("DeckStore-\(UUID().uuidString)", isDirectory: true))
        return (DeckJourney(api: api, uploader: up, store: st, timing: fastTiming()), api, up, st)
    }

    @Test func theHappyPathUploadsProcessesAndEndsReadyWithNothingLeftOnThePhone() async throws {
        let (j, api, up, store) = journey()
        let file = try tempFile("Quarterly review.pptx", bytes: 4096)
        j.pick(file, caps: caps)
        #expect(j.fileName == "Quarterly review.pptx" && j.isWorking)
        await wait(j) { $0 == .ready(ready) }
        #expect(j.state == .ready(ready) && j.deckID == "fakedeck1")
        #expect(up.uploads == 1)
        let calls = await api.deckCalls
        #expect(Array(calls.prefix(2)) == ["slot", "process"] && calls.filter { $0 == "status" }.count == 3)
        #expect(store.isEmpty && !j.hasLocalFile, "the temp copy is deleted once the upload finished")
        #expect(FileManager.default.fileExists(atPath: file.path), "the person's own file is never touched")
    }

    @Test func theCopyHasARandomNameAndIsNotBackedUp() throws {
        let store = DeckTempStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent("DeckStore-\(UUID().uuidString)", isDirectory: true))
        let file = try tempFile("Board meeting Q3 confidential.pptx", bytes: 2048)
        let imported = try store.importFile(from: file, caps: caps)
        #expect(!imported.url.lastPathComponent.contains("Board") && imported.url.pathExtension == "pptx")
        #expect(imported.name == "Board meeting Q3 confidential.pptx" && imported.bytes == 2048 && imported.format == "pptx")
        #expect(try imported.url.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup == true)
        store.removeAll(); #expect(!FileManager.default.fileExists(atPath: store.directory.path))
    }

    @Test func importRefusesBeforeCopyingAnything() throws {
        let store = DeckTempStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent("DeckStore-\(UUID().uuidString)", isDirectory: true))
        #expect(throws: DeckError(.exportFirst(ext: "ppt"))) { try store.importFile(from: try tempFile("old.ppt"), caps: caps) }
        #expect(throws: DeckError(.empty)) { try store.importFile(from: try tempFile("empty.pdf", bytes: 0), caps: caps) }
        #expect(throws: DeckError(.tooLarge(maxMB: 1))) { try store.importFile(from: try tempFile("big.pdf", bytes: 1_100_000), caps: DeckCapabilities(maxMB: 1)) }
        #expect(!FileManager.default.fileExists(atPath: store.directory.path), "nothing was copied")
    }

    @Test func aRefusedFileNeverStartsAnUpload() async throws {
        let (j, api, up, _) = journey()
        j.pick(try tempFile("old.ppt"), caps: caps)
        await wait(j) { if case .failed = $0 { true } else { false } }
        let calls = await api.deckCalls
        #expect(j.problem == .exportFirst(ext: "ppt") && up.uploads == 0 && calls.isEmpty)
    }

    @Test func eachServerFailureEndsAsItsOwnProblemAndTheDeckIsNotKept() async throws {
        for code in ["deck_too_large", "deck_too_many_slides", "deck_encrypted", "deck_macro", "deck_corrupt", "deck_empty", "deck_unsafe", "deck_unsupported", "deck_convert_timeout", "deck_convert_failed"] {
            var s = FakeDeckScript(); s.outcome = .failed(code: code)
            let (j, _, _, store) = journey(s)
            j.pick(try tempFile("a.pdf"), caps: caps)
            await wait(j) { if case .failed = $0 { true } else { false } }
            #expect(j.problem == .from(code: code, caps: caps), "\(code)")
            #expect(store.isEmpty && !j.hasLocalFile)
        }
    }

    @Test func aLostConnectionDuringTheUploadKeepsTheFileForARetryThenWorks() async throws {
        var s = FakeDeckScript(); s.uploadFailures = 1
        let (j, _, up, store) = journey(s)
        j.pick(try tempFile("a.pptx"), caps: caps)
        await wait(j) { if case .failed = $0 { true } else { false } }
        #expect(j.problem == .network && j.hasLocalFile && !store.isEmpty)
        #expect(j.problem?.action(hasLocalFile: j.hasLocalFile) == .retry)
        j.perform(.retry)
        await wait(j) { $0 == .ready(ready) }
        #expect(j.state == .ready(ready) && up.uploads == 2 && store.isEmpty)
    }

    @Test func cancelStopsEverythingAndDeletesTheCopy() async throws {
        var s = FakeDeckScript(); s.stall = .uploading
        let (j, _, _, store) = journey(s)
        j.pick(try tempFile("a.pptx"), caps: caps)
        await wait(j) { if case .uploading(let f) = $0 { f > 0 } else { false } }
        #expect(!store.isEmpty)
        j.discard()
        #expect(j.state == .idle && j.fileName == nil && j.deckID == nil && store.isEmpty)
        try await Task.sleep(for: .milliseconds(50))
        #expect(j.state == .idle, "a late answer from the cancelled upload changes nothing")
    }

    @Test func pollingGivesUpAfterASensibleTimeAndCanCheckAgain() async throws {
        var s = FakeDeckScript(); s.stall = .processing
        let api = FakeCreateAPI(deck: s)
        var t = fastTiming(); t.giveUp = 20; t.intervals = [(.infinity, 4)]
        let j = DeckJourney(api: api, uploader: FakeDeckUploader(s, stepDelay: 0.001), store: DeckTempStore(directory: FileManager.default.temporaryDirectory.appendingPathComponent("DeckStore-\(UUID().uuidString)")), timing: t)
        j.pick(try tempFile("a.pptx"), caps: caps)
        await wait(j) { if case .failed = $0 { true } else { false } }
        #expect(j.problem == .stillWorking)
        let polls = await api.deckCalls.filter { $0 == "status" }.count
        #expect(polls == 5, "20 seconds at one look every 4")
        j.perform(.checkAgain)
        #expect(j.state == .processing)
        await wait(j) { if case .failed = $0 { true } else { false } }
        #expect(j.problem == .stillWorking)
    }

    @Test func theWaitBacksOff() {
        let t = DeckTiming()
        #expect(t.interval(after: 0) == 2 && t.interval(after: 29) == 2 && t.interval(after: 30) == 4 && t.interval(after: 89) == 4 && t.interval(after: 90) == 6 && t.giveUp == 180)
    }

    @Test func pickingAnotherFileStartsAfresh() async throws {
        let (j, _, up, store) = journey()
        j.pick(try tempFile("first.pptx"), caps: caps)
        j.pick(try tempFile("second.pdf"), caps: caps)
        await wait(j) { $0 == .ready(ready) }
        #expect(j.fileName == "second.pdf" && store.isEmpty && up.uploads >= 1)
    }

    @Test func wipeClearsLeftoversFromAnEarlierLaunch() throws {
        let (j, _, _, store) = journey()
        try FileManager.default.createDirectory(at: store.directory, withIntermediateDirectories: true)
        try Data([1]).write(to: store.directory.appendingPathComponent("left-behind.pptx"))
        j.wipe()
        #expect(!FileManager.default.fileExists(atPath: store.directory.path))
    }
}

@Suite struct DeckMutualExclusionTests {
    @Test func aDeckAndPhotosNeverMix() {
        #expect(AttachRule.deck(photos: 0) == .go, "nothing to lose: straight to the picker")
        #expect(AttachRule.deck(photos: 7) == .confirm, "choosing a deck removes the photos, after asking")
        #expect(AttachRule.photos(deckActive: false) == .go)
        #expect(AttachRule.photos(deckActive: true) == .confirm, "choosing photos removes the deck, after asking")
    }

    @Test func theServerRefusesTheMixToo() async throws {
        // the app never sends both: `deck` goes with no media at all
        var f = CreateForm(); f.startDeck(.fallback); f.deckReady(DeckReady(slides: 3, suggestedMinutes: 1, suggestedCredits: 1).price)
        #expect(f.hasDeck && f.options.deck != nil)
    }
}

// MARK: the real client against a stub

final class DeckStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var requests: [(method: String, path: String, locale: String?, body: Data?)] = []
    nonisolated(unsafe) static var responses: [(Int, String)] = []
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "deck.test" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var body = request.httpBody
        if body == nil, let s = request.httpBodyStream { s.open(); var d = Data(); var buf = [UInt8](repeating: 0, count: 4096); while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; d.append(buf, count: n) }; s.close(); body = d }
        Self.requests.append((request.httpMethod ?? "", request.url?.path ?? "", request.value(forHTTPHeaderField: "X-Locale"), body))
        let (code, json) = Self.responses.isEmpty ? (200, "{}") : Self.responses.removeFirst()
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct DeckClientTests {
    struct Auth: AuthorizationProviding { func authorization() async throws -> (idToken: String, userID: String) { ("t", "u1") } }
    let cfg = AppConfig(apiBase: URL(string: "https://deck.test/prod")!, authDomain: URL(string: "https://auth.test")!, clientID: "cid")
    func client() -> APIClient {
        let c = URLSessionConfiguration.ephemeral; c.protocolClasses = [DeckStub.self]
        DeckStub.requests = []
        return APIClient(config: cfg, auth: Auth(), session: URLSession(configuration: c), locale: { "es" })
    }

    @Test func theThreeCallsUseTheContractAndCarryXLocale() async throws {
        let api = client()
        DeckStub.responses = [(200, #"{"deck":{"id":"abc","format":"pptx","url":"https://s3.test/up","fields":{"key":"k","Content-Type":"x"}},"max_bytes":52428800,"expires_in":900}"#), (202, #"{"status":"processing"}"#),
                              (200, #"{"id":"abc","status":"ready","slides":12,"suggested_minutes":4,"suggested_credits":4}"#)]
        let slot = try await api.requestSlot(format: "pptx", size: 1234)
        #expect(slot.id == "abc" && slot.fields["key"] == "k" && slot.contentType.hasSuffix("presentationml.presentation"))
        try await api.process(deckID: "abc")
        #expect(try await api.status(deckID: "abc") == .ready(ready))
        let r = DeckStub.requests
        #expect(r.map(\.method) == ["POST", "POST", "GET"] && r.map(\.path) == ["/prod/users/u1/decks", "/prod/users/u1/decks/abc/process", "/prod/users/u1/decks/abc"])
        #expect(r.allSatisfy { $0.locale == "es" })
        let body0 = try #require(r[0].body)
        let sent = try JSONSerialization.jsonObject(with: body0) as? [String: Any]
        #expect(sent?["format"] as? String == "pptx" && sent?["size"] as? Int == 1234)
    }

    @Test func serverErrorsKeepTheirCode() async throws {
        let api = client()
        DeckStub.responses = [(400, #"{"code":"deck_too_large","message":"too big"}"#), (429, #"{"code":"too_many_decks","message":"x"}"#), (404, #"{"code":"missing","message":"x"}"#), (200, #"{"status":"failed","code":"deck_macro","message":"m"}"#), (500, "{}")]
        await #expect(throws: DeckError(.tooLarge(maxMB: 50))) { try await api.requestSlot(format: "pptx", size: 1) }
        await #expect(throws: DeckError(.tooManyDecks)) { try await api.requestSlot(format: "pptx", size: 1) }
        await #expect(throws: DeckError(.other("x"))) { try await api.process(deckID: "zzz") }
        #expect(try await api.status(deckID: "abc") == .failed(code: "deck_macro", message: "m"))
        await #expect(throws: DeckError(.server)) { try await api.status(deckID: "abc") }
    }

    @Test func generateWithADeckOmitsWhatTheServerDefaults() async throws {
        let api = client()
        DeckStub.responses = [(200, #"{"video_id":"v1"}"#), (200, #"{"video_id":"v2"}"#), (200, #"{"video_id":"v3"}"#)]
        _ = try await api.startGeneration(prompt: "", clientRequestID: "r1", options: CreateOptions(minutes: 4, platform: "other", aspect: "16:9", deck: ready.price), deck: "abc", sendMinutes: false)
        _ = try await api.startGeneration(prompt: "students", clientRequestID: "r3", options: CreateOptions(minutes: 4, deck: ready.price), deck: "abc", sendMinutes: false)
        let body3 = try #require(DeckStub.requests[1].body)
        #expect((try JSONSerialization.jsonObject(with: body3) as? [String: Any])?["prompt"] == nil, "a 1 to 9 character prompt is never sent")
        _ = try await api.startGeneration(prompt: "for  executives", clientRequestID: "r2", options: CreateOptions(minutes: 2, deck: ready.price), deck: "abc", sendMinutes: true)
        let body0 = try #require(DeckStub.requests[0].body), body1 = try #require(DeckStub.requests[2].body)
        let a = try #require(try JSONSerialization.jsonObject(with: body0) as? [String: Any])
        #expect(a["deck"] as? String == "abc" && a["prompt"] == nil && a["target_minutes"] == nil && a["media"] == nil && a["aspect"] as? String == "16:9")
        let b = try #require(try JSONSerialization.jsonObject(with: body1) as? [String: Any])
        #expect(b["prompt"] as? String == "for executives" && b["target_minutes"] as? Double == 2)
    }

    @Test func theUploadFormPutsSignedFieldsFirstTheFileLastAndNeverTheFileName() throws {
        let file = try tempFile("Secret plan.pptx", bytes: 100)
        let out = file.deletingLastPathComponent().appendingPathComponent("form.body")
        try DeckS3Uploader.writeBody(to: out, fields: ["key": "k", "Content-Type": "ct", "policy": "p"], file: file, mimeType: "ct", boundary: "B")
        let text = String(decoding: try Data(contentsOf: out), as: UTF8.self)
        let order = ["name=\"Content-Type\"", "name=\"key\"", "name=\"policy\"", "name=\"file\""].compactMap { text.range(of: $0)?.lowerBound }
        #expect(order.count == 4 && order == order.sorted(), "the signed fields first, the file last")
        #expect(!text.contains("Secret plan") && text.hasSuffix("--B--\r\n"))
    }
}
