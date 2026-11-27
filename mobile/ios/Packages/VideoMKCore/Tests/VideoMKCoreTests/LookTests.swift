import Foundation
import Testing
@testable import VideoMKCore

private let caps = FakeCreateAPI.richCapabilities.withLooks()
private let looks = LookCapabilities.fake

/// The capabilities answer as the server writes it (docs/CREATE_API.md), short.
private let contract = #"""
{"aspects":[{"id":"16:9","label":"Landscape","ready":true}],"resolutions":[{"id":"1080p"}],
 "looks":{"style":{"param":"style"},
  "look":{"param":"look","default":"auto","enforced":true,"options":[
   {"id":"auto","label":"Auto","note":"Picked for your topic","preview":"data:image/jpeg;base64,/9j/AA==","available":true,"allowed":true,"requires_plan":null,"with_photos":true,"with_deck":true,"min_seconds":15,"aspects":["16:9","9:16"],"best_aspects":["16:9","9:16"],"cast":false,"extras":[]},
   {"id":"real","label":"Real","note":"Photos and footage","preview":"https://example.com/not-inline.jpg","with_photos":true,"with_deck":true,"cast":false,"extras":[]},
   {"id":"whiteboard","label":"Whiteboard","note":"Drawn by hand","with_photos":false,"with_deck":false,"best_aspects":["16:9","1:1"],"cast":false,"extras":[]},
   {"id":"cartoon","label":"Cartoon","note":"Characters explain it","with_photos":false,"with_deck":false,"min_seconds":15,"cast":true,
    "extras":[{"id":"board","label":"Characters explain at a board","note":"The characters explain on a board.","available":true}]}]},
  "cast":{"param":"cast","default":"auto","min":1,"max":3,"available":true,
   "auto":{"id":"auto","label":"Auto","note":"We pick for you. Or choose up to 3."},
   "conversation":{"from":2,"min_seconds":20,"note":"They talk it through."},
   "members":[{"id":"ines","name":"Inés","role":"Teacher","kind":"person","topic":"Learning","thumbnail":"data:image/png;base64,iVBORw0KGgo="},
              {"id":"fox","name":"Fox","role":"Guide for children","kind":"animal","topic":"For children","thumbnail":"data:image/png;base64,iVBORw0KGgo="}]}}}
"""#

@Suite struct LookCapabilityTests {
    private func decode(_ json: String) throws -> CreateCapabilities { try JSONDecoder().decode(CreateCapabilities.self, from: Data(json.utf8)) }

    @Test func decodesTheContract() throws {
        let l = try #require(try decode(contract).looks)
        #expect(l.options.map(\.id) == ["auto", "real", "whiteboard", "cartoon"])
        let auto = l.options[0], cartoon = l.options[3]
        #expect(auto.label == "Auto" && auto.note == "Picked for your topic" && auto.preview?.hasPrefix("data:image/jpeg") == true && auto.minSeconds == 15 && auto.requiresPlan == nil && auto.allowed && auto.available)
        #expect(l.options[1].preview == nil, "only inline pictures are drawn: a link is not fetched")
        #expect(!l.options[2].withPhotos && !l.options[2].withDeck && l.options[2].bestAspects == ["16:9", "1:1"])
        #expect(cartoon.cast && cartoon.extras == [.init(id: "board", label: "Characters explain at a board", note: "The characters explain on a board.", available: true)])
        let cast = try #require(l.cast)
        #expect(cast.max == 3 && cast.min == 1 && cast.autoLabel == "Auto" && cast.autoNote == "We pick for you. Or choose up to 3." && cast.conversationFrom == 2 && cast.conversationMinSeconds == 20)
        #expect(cast.conversationNote == "They talk it through." && cast.members.map(\.name) == ["Inés", "Fox"] && cast.members[1].kind == "animal" && cast.members[1].topic == "For children")
        #expect(DataURI.data(cast.members[0].thumbnail) != nil && DataURI.data("https://x") == nil && DataURI.data(nil) == nil)
    }

    @Test func absentMeansTheAppBehavesAsBefore() throws {
        #expect(try decode(#"{"aspects":[{"id":"16:9","ready":true}]}"#).looks == nil)
        #expect(try decode(#"{"aspects":[{"id":"16:9","ready":true}],"looks":{"style":{"param":"style"},"presenter":{"cast":[]}}}"#).looks == nil, "the older looks.style and looks.presenter alone are not the picker")
        #expect(try decode(#"{"aspects":[{"id":"16:9","ready":true}],"looks":{"look":{"options":[]}}}"#).looks == nil)
        #expect(try decode(#"{"aspects":[{"id":"16:9","ready":true}],"looks":"soon"}"#).looks == nil)
        #expect(try decode(#"{"aspects":[{"id":"16:9","ready":true}],"looks":{"look":"x"}}"#).readyAspects.count == 1, "a malformed looks never fails the capabilities")
        #expect(CreateCapabilities.fallback.looks == nil)
    }

    @Test func partialAnswersAreReadLeniently() throws {
        let json = #"{"aspects":[{"id":"16:9","ready":true}],"looks":{"look":{"options":[{"id":"auto"},{"label":"no id"},17,{"id":"cartoon","cast":true,"extras":[{"id":"board"},{"label":"x"}],"min_seconds":"30","allowed":false,"requires_plan":"Pro"},{"id":"cartoon","label":"twice"}]},"cast":{"max":"2","members":[{"id":"fox"},{"name":"nobody"},{"id":"fox","name":"again"},{"id":"auto","name":"Auto"}]}}}"#
        let l = try #require(try decode(json).looks)
        #expect(l.options.map(\.id) == ["auto", "cartoon"])
        #expect(l.options[0].label == "auto" && l.options[0].available && l.options[0].allowed && l.options[0].withPhotos && l.options[0].note == nil && l.options[0].preview == nil)
        #expect(l.options[1].minSeconds == 30 && !l.options[1].allowed && l.options[1].requiresPlan == "Pro" && l.options[1].extras.map(\.label) == ["board"])
        #expect(l.cast?.max == 2 && l.cast?.members.map(\.name) == ["fox"] && l.cast?.members[0].kind == "person" && l.cast?.conversationFrom == 2 && l.cast?.autoNote == nil)
        let noCast = try #require(try decode(#"{"aspects":[{"id":"16:9","ready":true}],"looks":{"look":{"options":[{"id":"auto"},{"id":"cartoon","cast":true}]}}}"#).looks)
        #expect(noCast.cast == nil)
        var f = CreateForm(); var c = FakeCreateAPI.richCapabilities; c.looks = noCast
        f.selectLook("cartoon", caps: c); f.toggleCast("fox", caps: c)
        #expect(f.lookChoice == LookChoice(look: "cartoon"), "a cartoon without a cast list is still a look; no cast can be ticked")
    }

    @Test func theRealFixtureDecodes() throws {
        // the answer the backend builds (`look_choice.capabilities`), saved for UI tests and screenshots
        let dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("../../../../VideoMKUITests/Fixtures").standardizedFileURL
        for (lang, cartoon) in [("en", "Cartoon"), ("es", "Animado")] {
            let l = try #require(LookCapabilities.from(file: dir.appendingPathComponent("looks_\(lang).json").path))
            #expect(l.options.map(\.id) == ["auto", "real", "whiteboard", "cartoon"] && l.options[3].label == cartoon)
            #expect(l.options.allSatisfy { DataURI.data($0.preview) != nil } && l.cast?.members.count == 10 && l.cast?.members.allSatisfy { DataURI.data($0.thumbnail) != nil } == true)
            #expect(l.cast?.groups.map(\.kind) == ["person", "animal"] && l.cast?.groups.map(\.members.count) == [4, 6])
        }
        #expect(LookCapabilities.from(file: "/nowhere.json") == nil)
    }
}

@Suite struct LookRequestTests {
    private func briefOptions(_ o: CreateOptions) throws -> [String: Any] {
        let obj = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(BriefRequest(prompt: "How bees make honey", options: o, mediaCount: 0))) as? [String: Any])
        return try #require(obj["options"] as? [String: Any])
    }

    @Test func autoSendsNothing() throws {
        #expect(LookChoice().fields.isEmpty && LookChoice().isAuto)
        #expect(LookChoice(look: "auto", cast: ["fox"], extras: ["board"]).fields.isEmpty == true, "a cast without Cartoon cannot be built in the app; Auto still sends nothing")
        let o = try briefOptions(CreateOptions())
        #expect(o["look"] == nil && o["cast"] == nil && o["extras"] == nil && o.keys.sorted() == ["aspect", "captions", "language", "platform", "resolution", "target_minutes"], "an older server sees the request it always saw")
    }

    @Test func aChosenLookIsSentAsTheContractSays() throws {
        #expect(LookChoice(look: "whiteboard").fields as NSDictionary == ["look": "whiteboard"])
        #expect(LookChoice(look: "cartoon").fields as NSDictionary == ["look": "cartoon"], "cast auto is the default: not sent")
        #expect(LookChoice(look: "cartoon", cast: ["fox"]).fields as NSDictionary == ["look": "cartoon", "cast": ["fox"]], "one character is still a list")
        #expect(LookChoice(look: "cartoon", cast: ["fox", "bear"], extras: ["board"]).fields as NSDictionary == ["look": "cartoon", "cast": ["fox", "bear"], "extras": ["board"]])
        let o = try briefOptions(CreateOptions(lookChoice: LookChoice(look: "cartoon", cast: ["fox", "bear"], extras: ["board"])))
        #expect(o["look"] as? String == "cartoon" && o["cast"] as? [String] == ["fox", "bear"] && o["extras"] as? [String] == ["board"])
        let w = try briefOptions(CreateOptions(lookChoice: LookChoice(look: "whiteboard")))
        #expect(w["look"] as? String == "whiteboard" && w["cast"] == nil && w["extras"] == nil)
    }

    @Test func theFormCarriesTheChoiceIntoTheOptions() {
        var f = CreateForm()
        f.selectLook("cartoon", caps: caps); f.toggleCast("fox", caps: caps); f.setLookExtra("board", on: true)
        #expect(f.options.lookChoice == LookChoice(look: "cartoon", cast: ["fox"], extras: ["board"]))
        f.setLookExtra("board", on: false)
        #expect(f.options.lookChoice.extras.isEmpty)
    }

    @Test func theStartAnswerIsReadLeniently() throws {
        let full = try #require(StartedVideo.decode(Data(#"{"message":"workflow started","video_id":"v1","look":{"chosen":"cartoon","applied":"cartoon","enforced":true,"recipe":"conversation_board","cast":["fox","bear"],"extras":["board"],"reason":null}}"#.utf8)))
        #expect(full.videoID == "v1" && full.note == nil && full.look == AppliedLook(chosen: "cartoon", applied: "cartoon", cast: ["fox", "bear"], extras: ["board"]))
        let adapted = try #require(StartedVideo.decode(Data(#"{"video_id":"v2","note":"Made from your photos: the Cartoon look is not used with your own photos.","look":{"chosen":"cartoon","applied":"real","enforced":false,"recipe":null,"extras":[],"reason":"own_photos"}}"#.utf8)))
        #expect(adapted.note == "Made from your photos: the Cartoon look is not used with your own photos." && adapted.look?.applied == "real" && adapted.look?.reason == "own_photos")
        #expect(StartedVideo.decode(Data(#"{"video_id":"v3"}"#.utf8)) == StartedVideo(videoID: "v3"), "an older server: no look, no note")
        #expect(StartedVideo.decode(Data(#"{"video_id":"v4","look":"x","note":17}"#.utf8)) == StartedVideo(videoID: "v4"), "a malformed look never fails the start")
        #expect(StartedVideo.decode(Data(#"{"video_id":"v5","look":{"chosen":"cartoon","applied":"cartoon","cast":"auto"}}"#.utf8))?.look?.cast == [], "cast auto is no list")
        #expect(StartedVideo.decode(Data(#"{"message":"no"}"#.utf8)) == nil && StartedVideo.decode(Data("nope".utf8)) == nil)
    }

    @Test func theVideoRecordKeepsTheAppliedLook() throws {
        let v = try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"a","status":"COMPLETE","look":{"chosen":"auto","applied":"whiteboard","recipe":"whiteboard","cast":[],"extras":[],"why":"A step-by-step process is clearest drawn.","by":"auto","share":1.0,"repaired":0,"reason":null}}"#.utf8))
        #expect(v.look?.applied == "whiteboard" && v.look?.byAuto == true && v.look?.why == "A step-by-step process is clearest drawn.")
        #expect(v.look?.title(caps: looks) == "Whiteboard" && v.look?.title(caps: nil) == "Whiteboard", "our own word when the capabilities are not there")
        let c = AppliedLook(chosen: "cartoon", applied: "cartoon", cast: ["fox", "bear"])
        #expect(c.title(caps: looks) == "Cartoon · Fox + Bruno" && !c.byAuto)
        #expect(AppliedLook(chosen: "auto", applied: "auto").title(caps: looks) == nil && AppliedLook(applied: "hologram").title(caps: looks) == nil, "nothing to say, or a look this app does not know: no row")
        #expect(try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"b","status":"COMPLETE"}"#.utf8)).look == nil)
        #expect(try JSONDecoder().decode(VideoItem.self, from: Data(#"{"video_id":"c","status":"COMPLETE","look":[1]}"#.utf8)).look == nil)
    }
}

extension CoreTests {
    @Test func generateSendsTheChosenLookAndReadsWhatWasApplied() async throws {
        nonisolated(unsafe) var body: [String: Any] = [:]
        StubProtocol.handler = { req in
            body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:]
            return (202, Data(#"{"video_id":"abc","note":"One character presents. A conversation needs 20 s or more.","look":{"chosen":"cartoon","applied":"cartoon","cast":["fox"],"extras":["board"],"reason":"too_short"}}"#.utf8))
        }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        let started = try await api.startVideo(prompt: "A day out with the family", clientRequestID: "r", options: CreateOptions(minutes: 0.25, lookChoice: LookChoice(look: "cartoon", cast: ["fox", "bear"], extras: ["board"])))
        #expect(body["look"] as? String == "cartoon" && body["cast"] as? [String] == ["fox", "bear"] && body["extras"] as? [String] == ["board"])
        #expect(started.videoID == "abc" && started.look?.reason == "too_short" && started.look?.cast == ["fox"] && started.note?.hasPrefix("One character presents") == true)
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r", options: CreateOptions(look: .paper))
        #expect(body["look"] == nil && body["cast"] == nil && body["extras"] == nil && body["theme"] as? String == "paper", "Auto: nothing new is sent; the colour theme is its own field")
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r", options: CreateOptions(lookChoice: LookChoice(look: "cartoon")))
        #expect(body["look"] as? String == "cartoon" && body["cast"] == nil && body["extras"] == nil)
    }
}

@Suite struct LookRuleTests {
    @Test func fourTilesAutoFirstAndTheUnavailableOnesHidden() {
        #expect(LookRules.tiles(looks).map(\.id) == ["auto", "real", "whiteboard", "cartoon"] && LookRules.tiles(looks).allSatisfy { !$0.locked })
        #expect(LookRules.tiles(looks.variant("soon")).map(\.id) == ["auto", "real", "cartoon"], "a look this stage does not have is the only kind that is not shown")
        var many = looks; many.options.append(.init(id: "claymation", label: "Clay"))
        #expect(LookRules.tiles(many).count == 4, "never more than four")
    }

    @Test func aLookThePlanDoesNotIncludeIsShownLockedAndCannotBeChosen() {
        let locked = looks.variant("locked")
        let tile = LookRules.tiles(locked).first { $0.id == "cartoon" }
        #expect(tile?.locked == true && tile?.blocked == .plan && tile?.option.requiresPlan == "Pro")
        #expect(LookRules.select("cartoon", in: LookChoice(), caps: locked) == LookChoice(), "a tap on a locked tile changes nothing")
        #expect(LookRules.select("whiteboard", in: LookChoice(), caps: locked) == LookChoice(look: "whiteboard"))
        let stored = LookRules.normalized(LookChoice(look: "cartoon", cast: ["fox"]), caps: locked)
        #expect(stored.choice == LookChoice() && stored.reset == .plan, "a remembered look the plan lost goes back to Auto")
    }

    @Test func withPhotosOrADeckTheDrawnLooksStayInPlaceBlockedWithTheReason() {
        #expect(LookRules.tiles(looks, attached: .init(photos: true)).map(\.id) == ["auto", "real", "whiteboard", "cartoon"], "the grid never changes shape")
        #expect(LookRules.tiles(looks, attached: .init(photos: true)).map(\.blocked) == [nil, nil, .photos, .photos])
        #expect(LookRules.tiles(looks, attached: .init(deck: true)).map(\.blocked) == [nil, nil, .deck, .deck])
        #expect(LookRules.tiles(looks.variant("locked"), attached: .init(photos: true)).last?.blocked == .photos, "the reason that can be fixed now comes first")
        #expect(LookRules.select("cartoon", in: LookChoice(), caps: looks, attached: .init(photos: true)) == LookChoice())
    }

    @Test func attachingPhotosAfterChoosingGoesBackToAutoAndSaysSo() {
        var f = CreateForm()
        f.selectLook("cartoon", caps: caps); f.toggleCast("fox", caps: caps); f.setLookExtra("board", on: true)
        #expect(f.reconcileLook(caps, attached: .nothing) == nil && f.lookChoice.look == "cartoon")
        #expect(f.reconcileLook(caps, attached: .init(photos: true)) == "Look set to Auto. Cartoon can't use your photos.")
        #expect(f.lookChoice == LookChoice() && f.options.lookChoice.fields.isEmpty)
        #expect(f.reconcileLook(caps, attached: .init(photos: true)) == nil, "said once")
        f.selectLook("whiteboard", caps: caps)
        #expect(f.reconcileLook(caps, attached: .init(deck: true)) == "Look set to Auto. Whiteboard can't use a presentation.")
        f.selectLook("real", caps: caps, attached: .init(photos: true))
        #expect(f.reconcileLook(caps, attached: .init(photos: true, deck: false)) == nil && f.lookChoice.look == "real", "Real is made from photos")
    }

    @Test func theCastIsOneToThreeAndTwoOrThreeAreAConversation() {
        var c = LookChoice(look: "cartoon")
        #expect(LookRules.toggle("fox", in: &c, caps: looks) == .added && !LookRules.isConversation(c, caps: looks))
        #expect(LookRules.toggle("bear", in: &c, caps: looks) == .added && LookRules.isConversation(c, caps: looks))
        #expect(LookRules.toggle("cat", in: &c, caps: looks) == .added && c.cast == ["fox", "bear", "cat"])
        #expect(LookRules.toggle("owl", in: &c, caps: looks) == .full && c.cast.count == 3, "a fourth is refused")
        #expect(LookRules.toggle("bear", in: &c, caps: looks) == .removed && c.cast == ["fox", "cat"])
        #expect(LookRules.toggle("nobody", in: &c, caps: looks) == .full && c.cast == ["fox", "cat"], "only characters the server lists")
        var f = CreateForm(); f.selectLook("cartoon", caps: caps); f.toggleCast("fox", caps: caps); f.toggleCast("fox", caps: caps)
        #expect(f.lookChoice == LookChoice(look: "cartoon"), "none chosen is Auto: we choose")
    }

    @Test func oneLineSaysWhatTheCastMeansAndAtTheLimitTheOthersWait() {
        var c = LookChoice(look: "cartoon")
        #expect(LookRules.castLine(c, caps: looks) == "We pick for you. Or choose up to 3." && !LookRules.castIsFull(c, caps: looks))
        c.cast = ["fox"]; #expect(LookRules.castLine(c, caps: looks) == "Fox presents.")
        c.cast = ["fox", "bear"]; #expect(LookRules.castLine(c, caps: looks) == "Fox and Bruno talk it through." && !LookRules.castIsFull(c, caps: looks))
        c.cast = ["fox", "bear", "cat"]; #expect(LookRules.castLine(c, caps: looks) == "Fox, Bruno and Mika talk it through." && LookRules.castIsFull(c, caps: looks))
        var two = looks; two.cast?.max = 2
        #expect(LookRules.castLine(LookChoice(look: "cartoon"), caps: two) == "We pick for you. Or choose up to 2." && LookRules.castIsFull(LookChoice(look: "cartoon", cast: ["fox", "bear"]), caps: two))
    }

    @Test func anotherLookDropsTheCastAndTheExtra() {
        var f = CreateForm()
        f.selectLook("cartoon", caps: caps); f.toggleCast("fox", caps: caps); f.setLookExtra("board", on: true)
        f.selectLook("cartoon", caps: caps)
        #expect(f.lookChoice.cast == ["fox"] && f.lookChoice.extras == ["board"], "the same tile again keeps what was chosen under it")
        f.selectLook("whiteboard", caps: caps)
        #expect(f.lookChoice == LookChoice(look: "whiteboard"))
        #expect(LookRules.normalized(LookChoice(look: "whiteboard", cast: ["fox"], extras: ["board"]), caps: looks).choice == LookChoice(look: "whiteboard"))
        #expect(LookRules.normalized(LookChoice(look: "cartoon", cast: ["fox", "fox", "gone", "bear", "cat", "owl"], extras: ["board", "fog"]), caps: looks).choice == LookChoice(look: "cartoon", cast: ["fox", "bear", "cat"], extras: ["board"]))
        #expect(LookRules.normalized(LookChoice(look: "cartoon", extras: ["board"]), caps: looks.variant("noboard")).choice == LookChoice(look: "cartoon"))
        #expect(LookRules.normalized(LookChoice(look: "whiteboard"), caps: looks.variant("soon")) == (LookChoice(), .gone))
        #expect(LookRules.normalized(LookChoice(look: "cartoon", cast: ["fox"]), caps: nil) == (LookChoice(), nil), "an older server: nothing is kept, nothing is sent")
    }

    @Test func aConversationMovesAShortVideoToTheShortestLengthThatWorks() {
        var f = CreateForm(); f.setMinutes(0.25)
        #expect(f.selectLook("cartoon", caps: caps) == nil && f.minutes == 0.25, "15 s is enough for one character")
        #expect(f.toggleCast("fox", caps: caps).nudge == nil)
        let r = f.toggleCast("bear", caps: caps)
        #expect(r.tap == .added && r.nudge == LookRules.LengthNudge(minutes: 0.5, needSeconds: 20, conversation: true) && f.minutes == 0.5, "20 s is not a length on offer: 30 s is the next one")
        #expect(f.toggleCast("cat", caps: caps).nudge == nil && f.lookLengthNudge(caps) == nil)
        f.setMinutes(0.25)
        #expect(f.lookLengthNudge(caps)?.minutes == 0.5, "shortened again by hand: Create offers the way back, it does not move it twice")
        var long = CreateForm(); long.setMinutes(2); long.selectLook("cartoon", caps: caps); long.toggleCast("fox", caps: caps)
        #expect(long.toggleCast("bear", caps: caps).nudge == nil && long.minutes == 2)
    }

    @Test func aLookWithItsOwnMinimumMovesTheLengthToo() {
        let short = FakeCreateAPI.richCapabilities.withLooks(looks.variant("short"))
        var f = CreateForm(); f.setMinutes(0.25)
        #expect(f.selectLook("cartoon", caps: short) == LookRules.LengthNudge(minutes: 0.5, needSeconds: 30, conversation: false) && f.minutes == 0.5)
        #expect(LookRules.minSeconds(LookChoice(look: "cartoon", cast: ["fox", "bear"]), caps: looks) == 20 && LookRules.minSeconds(LookChoice(), caps: looks) == 15 && LookRules.minSeconds(LookChoice(look: "cartoon"), caps: nil) == 0)
        #expect(LookRules.lengthNudge(LookChoice(look: "cartoon"), caps: looks.variant("short"), minutes: 0.25, presets: [0.25]) == nil, "no length on offer is long enough: nothing is moved")
    }

    @Test func thePillSaysTheLookOnly() {
        #expect(LookRules.pillLabel(LookChoice(), caps: looks) == "Auto" && LookRules.pillLabel(LookChoice(look: "cartoon"), caps: nil) == "Auto")
        #expect(LookRules.pillLabel(LookChoice(look: "whiteboard"), caps: looks) == "Whiteboard")
        #expect(LookRules.pillLabel(LookChoice(look: "cartoon"), caps: looks) == "Cartoon")
        #expect(LookRules.pillLabel(LookChoice(look: "cartoon", cast: ["fox"]), caps: looks) == "Cartoon", "the cast is faces in the pill, never names")
        #expect(LookRules.pillLabel(LookChoice(look: "cartoon", cast: ["fox", "bear", "cat"]), caps: looks) == "Cartoon")
        #expect(LookRules.spoken(LookChoice(look: "cartoon", cast: ["fox", "bear", "cat"], extras: ["board"]), caps: looks) == "Cartoon, Fox, Bruno and Mika, Characters explain at a board")
    }

    @Test func theLastChoiceIsRememberedAndKeptInsideWhatTheServerLists() throws {
        let suite = "look-defaults-\(UUID().uuidString)"
        let store = try #require(UserDefaults(suiteName: suite)); defer { store.removePersistentDomain(forName: suite) }
        var f = CreateForm(); f.selectLook("cartoon", caps: caps); f.toggleCast("fox", caps: caps); f.toggleCast("bear", caps: caps); f.setLookExtra("board", on: true)
        CreateDefaults(f).save(userID: "u", defaults: store)
        let back = CreateDefaults.load(userID: "u", defaults: store)
        #expect(back.form(caps).lookChoice == LookChoice(look: "cartoon", cast: ["fox", "bear"], extras: ["board"]))
        #expect(back.form(FakeCreateAPI.richCapabilities).lookChoice == LookChoice(), "a server without the picker: Auto, nothing sent")
        #expect(back.form(FakeCreateAPI.richCapabilities.withLooks(looks.variant("locked"))).lookChoice == LookChoice())
        // what an older version stored has no look: it still loads
        store.set(Data(#"{"platform":"x","aspect":"16:9","resolution":"1080p","language":"auto","minutes":1,"captions":true}"#.utf8), forKey: "createDefaults.old")
        let old = CreateDefaults.load(userID: "old", defaults: store)
        #expect(old.platform == "x" && old.lookChoice == nil && old.form(caps).lookChoice == LookChoice())
        #expect(CreateDefaults(CreateForm()).lookChoice == nil, "Auto is not stored")
    }

    @Test func theFakeServerAnswersLikeTheContract() {
        #expect(FakeLook.started(videoID: "v", options: CreateOptions(), photos: false, caps: looks) == StartedVideo(videoID: "v"))
        let talk = FakeLook.started(videoID: "v", options: CreateOptions(minutes: 0.25, lookChoice: LookChoice(look: "cartoon", cast: ["fox", "bear"])), photos: false, caps: looks)
        #expect(talk.look?.reason == "too_short" && talk.look?.cast == ["fox"] && talk.note != nil)
        #expect(FakeLook.started(videoID: "v", options: CreateOptions(lookChoice: LookChoice(look: "cartoon")), photos: true, caps: looks).look?.applied == "real")
        #expect(FakeLook.started(videoID: "v", options: CreateOptions(minutes: 1, lookChoice: LookChoice(look: "whiteboard")), photos: false, caps: looks) == StartedVideo(videoID: "v", look: AppliedLook(chosen: "whiteboard", applied: "whiteboard")))
    }
}
