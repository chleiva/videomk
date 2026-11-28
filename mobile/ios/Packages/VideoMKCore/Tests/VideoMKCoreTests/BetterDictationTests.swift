import Foundation
import Testing
@testable import VideoMKCore

private func hexID(_ n: Int) -> String { String(format: "%032x", n) }

@Suite struct BetterDictationRulesTests {
    private let capsJSON = #"{"premium":true,"available":true,"paused":false,"seconds_per_day":600,"seconds_left_today":540,"max_clip_seconds":360,"max_clip_bytes":3145728,"requires_plan":null,"provider":"openai"}"#

    @Test func capabilitiesAreReadLeniently() throws {
        let c = try JSONDecoder().decode(AnyJSON.self, from: Data(capsJSON.utf8))
        let d = try #require(DictationCapabilities(json: c))
        #expect(d.premium && d.available && !d.paused && d.secondsLeft == 540 && d.maxClipSeconds == 360 && d.maxClipBytes == 3_145_728 && d.requiresPlan == nil && d.isUsable)
        #expect(DictationCapabilities(json: .string("x")) == nil && DictationCapabilities(json: nil) == nil)
        let big = DictationCapabilities(maxClipSeconds: 9999, maxClipBytes: 99_000_000)
        #expect(big.maxClipSeconds == 360 && big.maxClipBytes == 3 * 1024 * 1024, "the app never goes past the server's hard limits")
    }

    @Test func capabilitiesRideInsideTheCreateCapabilities() throws {
        let json = #"{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}],"lengths":{"presets":[1]},"dictation":\#(capsJSON)}"#
        let caps = try JSONDecoder().decode(CreateCapabilities.self, from: Data(json.utf8))
        #expect(caps.dictation?.isUsable == true)
        let none = try JSONDecoder().decode(CreateCapabilities.self, from: Data(#"{"aspects":[{"id":"16:9","ready":true}],"dictation":7}"#.utf8))
        #expect(none.dictation == nil, "malformed means not offered, never an error")
    }

    @Test func usableOnlyWhenAvailableAndNotPaused_hintOnlyForAPlanWithoutIt() {
        #expect(DictationCapabilities(premium: true, available: true).isUsable)
        #expect(!DictationCapabilities(premium: true, available: true, paused: true).isUsable)
        #expect(!DictationCapabilities(premium: true, available: false).isUsable, "today's seconds are used")
        #expect(DictationCapabilities(premium: false, available: false, requiresPlan: "pro").showsUpgradeHint)
        #expect(!DictationCapabilities(premium: true, available: false).showsUpgradeHint, "no nag when the plan has it")
    }

    @Test func thePreferenceDefaultsToOnAndRemembersOff() {
        let d = UserDefaults(suiteName: "better-test-\(UUID().uuidString)")!
        #expect(BetterDictationPreference.isOn(d))
        BetterDictationPreference.set(false, d); #expect(!BetterDictationPreference.isOn(d))
        let on = DictationCapabilities(premium: true, available: true)
        #expect(BetterDictationPreference.uses(on, preferred: true) && !BetterDictationPreference.uses(on, preferred: false) && !BetterDictationPreference.uses(nil, preferred: true))
    }

    @Test func idsAreKeptOnceAtMostTwentyNewestWin() {
        var ids = DictationIDs()
        ids.add(hexID(1)); ids.add(hexID(1)); ids.add("not an id")
        #expect(ids.list == [hexID(1)])
        for i in 2...25 { ids.add(hexID(i)) }
        #expect(ids.list.count == 20 && ids.list.first == hexID(6) && ids.list.last == hexID(25))
        ids.clear(); #expect(ids.list.isEmpty)
    }

    @Test func betterTextReplacesThePreviewOnTopOfTheBaseAndNeverAnEditedField() {
        #expect(placeBetterText(base: "Make it fun.", native: "Make it fun. a video abot bees", field: "Make it fun. a video abot bees", better: "A video about bees") == "Make it fun. A video about bees")
        #expect(placeBetterText(base: "Hi", native: "Hi", field: "Hi", better: "there") == "Hi there", "no preview: a plain append")
        #expect(placeBetterText(base: "a", native: "a b", field: "a b EDITED", better: "better") == nil, "the person's edit wins")
        #expect(placeBetterText(base: "a", native: "a", field: "a", better: "   ") == nil)
    }

    @Test func errorsMapAndOnlyUsefulOnesSpeak() {
        func f(_ s: Int, _ b: String?) -> BetterDictationFailure { .from(status: s, body: b.map { Data($0.utf8) }) }
        #expect(f(403, #"{"code":"dictation_plan"}"#) == .plan && f(429, #"{"code":"dictation_quota"}"#) == .quota && f(413, #"{"code":"dictation_too_long"}"#) == .tooLong)
        #expect(f(503, #"{"code":"dictation_paused"}"#) == .paused && f(502, #"{"code":"dictation_failed"}"#) == .failed && f(400, #"{"code":"bad_audio"}"#) == .badAudio)
        #expect(f(401, nil) == .auth && f(500, nil) == .failed && f(429, nil) == .quota)
        #expect(BetterDictationFailure.quota.messageKey == "better.quota" && BetterDictationFailure.tooLong.messageKey == "better.limit")
        #expect(BetterDictationFailure.failed.messageKey == "better.failed" && BetterDictationFailure.network.messageKey == "better.failed")
        #expect(BetterDictationFailure.plan.messageKey == nil && BetterDictationFailure.paused.messageKey == nil && BetterDictationFailure.auth.messageKey == nil)
    }

    @Test func theEndOfAnUploadResolvesToTextIdAndLine() {
        let ok = Result<DictationAnswer, BetterDictationFailure>.success(DictationAnswer(id: hexID(3), text: "Better"))
        #expect(BetterDictationResolution.resolve(base: "A", native: "A b", field: "A b", result: ok, limitHit: false) == BetterDictationResolution(write: "A Better", id: hexID(3), noteKey: nil))
        #expect(BetterDictationResolution.resolve(base: "A", native: "A b", field: "A b typed", result: ok, limitHit: true) == BetterDictationResolution(write: nil, id: hexID(3), noteKey: "better.limit"), "edited field untouched, the paid id still kept")
        let blank = Result<DictationAnswer, BetterDictationFailure>.success(DictationAnswer(id: hexID(4), text: " "))
        #expect(BetterDictationResolution.resolve(base: "A", native: "A", field: "A", result: blank, limitHit: false) == BetterDictationResolution(write: nil, id: nil, noteKey: nil))
        for (f, key) in [(BetterDictationFailure.quota, "better.quota"), (.failed, "better.failed"), (.network, "better.failed")] {
            #expect(BetterDictationResolution.resolve(base: "A", native: "A b", field: "A b", result: .failure(f), limitHit: false) == BetterDictationResolution(write: nil, id: nil, noteKey: key), "the native text stays")
        }
        #expect(BetterDictationResolution.resolve(base: "", native: "x", field: "x", result: .failure(.plan), limitHit: false).noteKey == nil)
        #expect(BetterDictationResolution.resolve(base: "", native: "x", field: "x", result: .failure(.paused), limitHit: false).noteKey == nil)
        #expect(BetterDictationResolution.resolve(base: "", native: "x", field: "x", result: .failure(.network), limitHit: true).noteKey == "better.limit")
    }

    @Test func theClipBodyFollowsTheContract() throws {
        let clip = DictationClip(audio: Data([1, 2, 3]), seconds: 23.456, languages: ["es", "en", "fr", "de", "it"], prompt: String(repeating: "x", count: 500))
        let o = try #require(try JSONSerialization.jsonObject(with: clip.body()) as? [String: Any])
        #expect(o["audio"] as? String == "AQID" && o["mime"] as? String == "audio/mp4" && o["seconds"] as? Double == 23.5)
        #expect((o["languages"] as? [String])?.count == 4 && (o["prompt"] as? String)?.count == 400)
        let bare = try #require(try JSONSerialization.jsonObject(with: DictationClip(audio: Data([1]), seconds: 1, languages: ["en"], prompt: "  ").body()) as? [String: Any])
        #expect(bare["prompt"] == nil)
    }
}

// Uses the shared URLProtocol stub, so it joins the serialized CoreTests suite.
extension CoreTests {
    @Test func dictateReturnsTheTextAndTheId() async throws {
        nonisolated(unsafe) var path = "", body: [String: Any] = [:]
        StubProtocol.handler = { req in
            path = req.url!.path; body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:]
            return (200, Data(#"{"id":"\#(hexID(9))","text":"Hola mundo","language":"es","seconds":23.0,"seconds_left_today":577,"max_clip_seconds":360}"#.utf8))
        }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        let r = await api.dictate(DictationClip(audio: Data([9, 9]), seconds: 2, languages: ["es"]))
        #expect(path.hasSuffix("/users/user-1/dictation") && body["languages"] as? [String] == ["es"])
        #expect(try r.get() == DictationAnswer(id: hexID(9), text: "Hola mundo", seconds: 23, secondsLeft: 577))
    }

    @Test func everyErrorIsATypedFailureNeverAThrow() async {
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        for (status, body, want) in [(403, #"{"code":"dictation_plan"}"#, BetterDictationFailure.plan), (429, #"{"code":"dictation_quota"}"#, .quota), (413, #"{"code":"dictation_too_long"}"#, .tooLong),
                                     (502, #"{"code":"dictation_failed"}"#, .failed), (503, #"{"code":"dictation_paused"}"#, .paused)] {
            StubProtocol.handler = { _ in (status, Data(body.utf8)) }
            let r = await api.dictate(DictationClip(audio: Data([1]), seconds: 1, languages: ["en"]))
            #expect(r == .failure(want), "\(status)")
        }
        StubProtocol.handler = { _ in (200, Data("{}".utf8)) }
        #expect(await api.dictate(DictationClip(audio: Data([1]), seconds: 1, languages: ["en"])) == .failure(.failed))
    }

    @Test func generateSendsTheDictationIDsOnlyWhenThereAreSome() async throws {
        nonisolated(unsafe) var body: [String: Any] = [:]
        StubProtocol.handler = { req in body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:]; return (202, Data(#"{"video_id":"abc"}"#.utf8)) }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r")
        #expect(body["dictation_ids"] == nil)
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r", dictationIDs: [hexID(1), hexID(2)])
        #expect(body["dictation_ids"] as? [String] == [hexID(1), hexID(2)])
    }
}
