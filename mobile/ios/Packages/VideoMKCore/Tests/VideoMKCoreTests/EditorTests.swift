import Foundation
import Testing
@testable import VideoMKCore

private func beat(_ id: String, _ text: String = "This is a perfectly fine narration for one scene.") -> EditorBeat {
    EditorBeat(id: id, narration: text)
}

// Pure logic: safe to run in parallel with everything else.
@Suite struct EditorLogicTests {
    let server = [beat("a"), beat("b"), beat("c"), beat("d")]

    @Test func noChangesNoOps() {
        #expect(EditorDiff.ops(serverTitle: "T", server: server, localTitle: "T", local: server).isEmpty)
    }

    @Test func narrationEditsIgnoreWhitespaceOnlyChanges() {
        var local = server
        local[1].narration = "  This is a perfectly   fine narration for one scene. "
        #expect(EditorDiff.ops(serverTitle: "T", server: server, localTitle: "T", local: local).isEmpty)
        local[1].narration = "A completely different sentence about the second scene."
        #expect(EditorDiff.ops(serverTitle: "T", server: server, localTitle: "T", local: local)
                == [.setNarration(id: "b", text: "A completely different sentence about the second scene.")])
    }

    @Test func deletesComeBeforeMovesAndMovesUseFinalIndexes() {
        // server a b c d  ->  local d a c   (b deleted, d moved to the front)
        let local = [server[3], server[0], server[2]]
        let ops = EditorDiff.ops(serverTitle: "T", server: server, localTitle: "T", local: local)
        #expect(ops == [.delete(id: "b"), .move(id: "d", to: 0)])
        #expect(Self.apply(ops, to: ["a", "b", "c", "d"]) == ["d", "a", "c"])
    }

    @Test(arguments: [["d", "c", "b", "a"], ["b", "a", "c", "d"], ["c", "d", "a", "b"], ["a", "c", "d", "b"], ["b", "c", "d", "a"]])
    func anyReorderReplaysToTheTargetOrder(target: [String]) {
        let byID = Dictionary(uniqueKeysWithValues: server.map { ($0.id, $0) })
        let ops = EditorDiff.ops(serverTitle: "T", server: server, localTitle: "T", local: target.map { byID[$0]! })
        #expect(Self.apply(ops, to: ["a", "b", "c", "d"]) == target)
    }

    @Test func everythingTogether() {
        var local = [server[2], server[0]]           // delete b and d, reorder c before a
        local[0].narration = "Edited words for the very first scene here."
        let ops = EditorDiff.ops(serverTitle: "Old", server: server, localTitle: "New title", local: local, picks: ["a": "unsplash:xyz"])
        #expect(ops.contains(.setNarration(id: "c", text: "Edited words for the very first scene here.")))
        #expect(ops.contains(.pickImage(id: "a", candidate: "unsplash:xyz")))
        #expect(ops.contains(.setTitle("New title")))
        #expect(Self.apply(ops, to: ["a", "b", "c", "d"]) == ["c", "a"])
    }

    @Test func narrationLimitsMirrorTheServer() {
        let l = EditorLimits()
        #expect(EditorDiff.narrationError("too short here", limits: l) != nil)
        #expect(EditorDiff.narrationError("one two three four five six", limits: l) == nil)
        #expect(EditorDiff.narrationError(Array(repeating: "word", count: 71).joined(separator: " "), limits: l) != nil)
        #expect(EditorDiff.narrationError(Array(repeating: "word", count: 70).joined(separator: " "), limits: l) == nil)
    }

    @Test func opsSerializeToTheServersShape() {
        #expect(EditOp.setNarration(id: "a", text: "x").json as NSDictionary == ["op": "set_narration", "id": "a", "text": "x"] as NSDictionary)
        #expect(EditOp.move(id: "a", to: 2).json as NSDictionary == ["op": "move", "id": "a", "to": 2] as NSDictionary)
        #expect(EditOp.setTitle("T").json as NSDictionary == ["op": "set_meta", "title": "T"] as NSDictionary)
        #expect(EditOp.pickImage(id: "a", candidate: "openverse:1").json as NSDictionary == ["op": "pick_image", "id": "a", "candidate": "openverse:1"] as NSDictionary)
    }

    @Test func decodesTheServersPlanShape() throws {
        let json = """
        {"video_id":"v","rev":3,"status":"COMPLETE","edit_state":"RENDERING","edit_mode":"preview","title":"Rainbows",
         "limits":{"max_beats":90,"min_words":6,"max_words":70},
         "final":{"url":"https://s3/final.mp4","rev":2},"preview":{"url":null,"rev":null},
         "beats":[
          {"id":"b1","narration":"Why does a rainbow look like a bridge of color?","scene":{"type":"title","props":{"title":"How Rainbows Form","subtitle":""}},"chapter":"Intro","duration":14.9,"stale":false,"pick":null},
          {"id":"b2","narration":"Here is the first clue about rainbows and rain.","scene":{"type":"image","props":{"image_query":"rainbow","alt":"A rainbow over a field"}},"duration":12.5,"stale":true,
           "photo":{"url":"https://s3/p.jpg","credit":"Photo: Ann (CC0)","chosen":"openverse:1","no_photo":false},
           "candidates":[{"provider":"openverse","id":"1","thumb_url":"https://x/t.jpg","creator":"Ann","license":"cc0","alt":"rainbow","landing_url":"https://x/1"}]},
          {"id":"b3","narration":"A stat scene with one big number in it today.","scene":{"type":"stat","props":{"value":"7","label":"colors"}}}]}
        """
        let s = try JSONDecoder().decode(EditorSnapshot.self, from: Data(json.utf8))
        #expect(s.rev == 3 && s.editState == .rendering && s.finalURL != nil && s.finalRev == 2 && s.previewURL == nil)
        #expect(s.beats.map(\.kind) == [.title, .image, .stat])
        #expect(s.beats[0].summary == "How Rainbows Form" && s.beats[0].chapter == "Intro")
        #expect(s.beats[1].summary == "A rainbow over a field" && s.beats[1].stale && s.beats[1].candidates.first?.key == "openverse:1")
        #expect(s.beats[1].photo?.credit == "Photo: Ann (CC0)" && s.beats[2].summary == "7 colors")
    }

    /// Replays server-side semantics for delete and move so the diff is checked against what the server will actually do.
    static func apply(_ ops: [EditOp], to ids: [String]) -> [String] {
        var ids = ids
        for op in ops {
            switch op {
            case .delete(let id): ids.removeAll { $0 == id }
            case .move(let id, let to): ids.removeAll { $0 == id }; ids.insert(id, at: to)
            default: break
            }
        }
        return ids
    }
}

// Uses the shared URLProtocol stub, so it joins the serialized suite.
extension CoreTests {
    @Test func editsPostAndConflictMapping() async throws {
        nonisolated(unsafe) var body: [String: Any] = [:]
        nonisolated(unsafe) var status = 202
        StubProtocol.handler = { req in
            body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:]
            return status == 202 ? (202, Data(#"{"rev":4,"mode":"preview","message":"render started"}"#.utf8))
                                 : (409, Data(#"{"message":"This video changed since you loaded it. Reload to continue.","rev":5}"#.utf8))
        }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        let rev = try await api.applyEdits(videoID: "v", baseRev: 3, ops: [.setNarration(id: "a", text: "x y z"), .delete(id: "b")], mode: .preview)
        #expect(rev == 4 && body["base_rev"] as? Int == 3 && body["mode"] as? String == "preview" && (body["ops"] as? [[String: Any]])?.count == 2)

        status = 409
        do { _ = try await api.applyEdits(videoID: "v", baseRev: 3, ops: [], mode: .final); Issue.record("expected a conflict") }
        catch { #expect(error as? APIError == .conflict("This video changed since you loaded it. Reload to continue.")) }
    }
}

@Suite struct ClipSceneTests {
    @Test func aClipBeatDecodesAsAVideoClipWithItsDescription() throws {
        let json = #"{"id":"b1","narration":"Waves roll in slowly over the sand.","scene":{"type":"clip","props":{"clip_query":"ocean waves","alt":"waves rolling in"}},"duration":4.2,"stale":false,"clip":{"has_clip":true,"credit":"Video: Z / Pexels"}}"#
        let b = try JSONDecoder().decode(EditorBeat.self, from: Data(json.utf8))
        #expect(b.kind == .clip && b.kind?.label == "Video clip" && b.kind?.symbol == "film" && b.summary == "waves rolling in")
        let noAlt = try JSONDecoder().decode(EditorBeat.self, from: Data(#"{"id":"b2","narration":"Another line of narration here.","scene":{"type":"clip","props":{"clip_query":"city traffic"}}}"#.utf8))
        #expect(noAlt.summary == "city traffic")
    }
}

@Suite struct CaptionsOptionTests {
    @Test func theSnapshotCarriesTheSubtitlesChoiceAndDefaultsToOn() throws {
        func snap(_ extra: String) throws -> EditorSnapshot {
            try JSONDecoder().decode(EditorSnapshot.self, from: Data(#"{"video_id":"v","rev":1,"edit_state":"READY","title":"T","beats":[]\#(extra)}"#.utf8))
        }
        #expect(try snap(#","captions":false"#).captions == false)
        #expect(try snap(#","captions":true"#).captions == true)
        #expect(try snap("").captions == true)                       // an older server that does not send it
    }

    @Test func togglingSubtitlesInTheEditorIsOneSetMetaOperation() {
        let none = EditorDiff.ops(serverTitle: "T", server: [], localTitle: "T", local: [])
        #expect(none.isEmpty)
        let off = EditorDiff.ops(serverTitle: "T", server: [], localTitle: "T", local: [], serverCaptions: true, localCaptions: false)
        #expect(off == [.setCaptions(false)] && off[0].json["op"] as? String == "set_meta" && off[0].json["captions"] as? Bool == false)
        let back = EditorDiff.ops(serverTitle: "T", server: [], localTitle: "T", local: [], serverCaptions: false, localCaptions: true)
        #expect(back == [.setCaptions(true)])
    }

    @Test func newVideosHaveSubtitlesOnUnlessTheCreatorTurnsThemOff() {
        #expect(CreateOptions().captions == true && CreateOptions(captions: false).captions == false)
    }
}
