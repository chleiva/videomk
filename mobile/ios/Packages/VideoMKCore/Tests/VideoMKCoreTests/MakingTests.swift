import Foundation
import Testing
@testable import VideoMKCore

private func making(_ s: String) -> MakingInfo? { MakingInfo(json: try? JSONDecoder().decode(AnyJSON.self, from: Data(s.utf8))) }

/// The "making" object of docs/CREATE_API.md: every field optional, read leniently, never a reason to fail the answer it arrives in.
@Suite struct MakingDecodingTests {
    @Test func theContractExampleIsRead() throws {
        let m = try #require(making(#"{"scene_total": 9, "scene_done": 4, "live_line": "Adding footage of sunlit canopies", "narration_line": "Sunlight pours through the canopy.", "scenes": [{"index": 1, "thumb_url": "https://x.example/a.jpg?sig=1", "done": true}, {"index": 2, "done": true}, {"index": 3, "done": false}]}"#))
        #expect(m.sceneTotal == 9 && m.sceneDone == 4)
        #expect(m.liveLine == "Adding footage of sunlit canopies")
        #expect(m.narrationLine == "Sunlight pours through the canopy.")
        #expect(m.scenes.count == 3 && m.scenes[0].thumbURL?.host == "x.example" && m.scenes[1].thumbURL == nil)
        #expect(m.counterScene == 5, "Scene 5 of 9: one more than the scenes finished")
        #expect(m.tiles.count == 9)
    }

    @Test func nothingUsableIsNil() {
        #expect(making("null") == nil)
        #expect(making("{}") == nil)
        #expect(making(#""soon""#) == nil)
        #expect(making("[1,2]") == nil)
        #expect(making(#"{"scene_total": "many", "live_line": "  ", "scenes": "none"}"#) == nil)
        #expect(MakingInfo(json: nil) == nil)
    }

    @Test func eachFieldStandsAlone() throws {
        let line = try #require(making(#"{"live_line": "Recording the narration"}"#))
        #expect(line.liveLine == "Recording the narration" && line.sceneTotal == nil && line.tiles.isEmpty && line.counterScene == nil)
        let count = try #require(making(#"{"scene_total": 6, "scene_done": 2}"#))
        #expect(count.tiles.map(\.state) == [.done, .done, .current, .upcoming, .upcoming, .upcoming], "without a list the strip fills from the left")
        #expect(!count.hasThumbnails && count.heroThumb == nil)
        let doneOnly = try #require(making(#"{"scene_done": 4, "narration_line": "One tree can cool a street."}"#))
        #expect(doneOnly.sceneDone == nil, "4 done of an unknown number says nothing")
    }

    @Test func wrongTypesAreToleratedFieldByField() throws {
        let m = try #require(making(#"{"scene_total": "9", "scene_done": 4.0, "live_line": 12, "narration_line": "Line one\nline two", "scenes": [{"index": "2", "done": "true", "thumb_url": 7}, "junk", {"done": 1}, {"index": 2, "done": false}, {"index": 0}, {"index": 999}]}"#))
        #expect(m.sceneTotal == 9 && m.sceneDone == 4)
        #expect(m.liveLine == nil)
        #expect(m.narrationLine == "Line one line two")
        #expect(m.scenes.map(\.index) == [2, 3, 5], "a duplicate index and an absurd one are dropped; a missing index takes its place in the list")
        #expect(m.scenes[0].done && m.scenes[0].thumbURL == nil)
        #expect(m.scenes[1].done)
    }

    @Test func numbersStayHonest() throws {
        let over = try #require(making(#"{"scene_total": 5, "scene_done": 12}"#))
        #expect(over.sceneDone == 5 && over.counterScene == 5, "never more done than there are, and the counter stops at the total")
        #expect(over.currentScene == nil)
        let negative = try #require(making(#"{"scene_total": -3, "scene_done": -1, "live_line": "Finding the right footage"}"#))
        #expect(negative.sceneTotal == nil && negative.sceneDone == nil)
        let huge = try #require(making(#"{"scene_total": 5000}"#))
        #expect(huge.sceneTotal == MakingInfo.maxScenes)
        let fromList = try #require(making(#"{"scenes": [{"index": 1, "done": true}, {"index": 2, "done": true}, {"index": 3}]}"#))
        #expect(fromList.sceneTotal == 3 && fromList.sceneDone == 2, "the list itself says how many")
        let longer = try #require(making(#"{"scene_total": 2, "scenes": [{"index": 1}, {"index": 2}, {"index": 3}]}"#))
        #expect(longer.sceneTotal == 3, "never fewer tiles than scenes listed")
    }

    @Test func onlyWebPictureLinksAreKept() throws {
        let m = try #require(making(#"{"scenes": [{"index": 1, "done": true, "thumb_url": "file:///etc/passwd"}, {"index": 2, "done": true, "thumb_url": "javascript:alert(1)"}, {"index": 3, "done": true, "thumb_url": " https://x.example/3.jpg "}]}"#))
        #expect(m.scenes.map { $0.thumbURL != nil } == [false, false, true])
    }

    @Test func aLongLineIsCut() throws {
        let m = try #require(making("{\"live_line\": \"\(String(repeating: "a", count: 2000))\"}"))
        #expect(m.liveLine?.count == MakingInfo.maxLine)
    }

    @Test func scenesFinishOutOfOrder() throws {
        // made several at a time: 1, 3 and 4 are done, 2 is still in work
        let m = try #require(making(#"{"scene_total": 6, "scene_done": 3, "scenes": [{"index": 1, "done": true, "thumb_url": "https://x.example/1.jpg"}, {"index": 2, "done": false}, {"index": 3, "done": true}, {"index": 4, "done": true, "thumb_url": "https://x.example/4.jpg"}, {"index": 5, "done": false}, {"index": 6, "done": false}]}"#))
        #expect(m.tiles.map(\.state) == [.done, .current, .done, .done, .upcoming, .upcoming])
        #expect(m.currentScene == 2)
        #expect(m.counterScene == 4, "the words count what is finished: scene_done + 1")
        #expect(m.heroThumb?.lastPathComponent == "4.jpg", "the scene in work has no picture yet: the last finished one that has")
        #expect(m.doneScenes == 3)
    }

    @Test func theCardWindowKeepsTheCurrentSceneInView() throws {
        let m = try #require(making(#"{"scene_total": 20, "scene_done": 12}"#))
        let w = m.window(7)
        #expect(w.count == 7 && w.contains { $0.state == .current })
        #expect(m.window(30).count == 20)
        let finished = try #require(making(#"{"scene_total": 20, "scene_done": 20}"#))
        #expect(finished.window(7).map(\.index) == Array(14...20))
    }

    @Test func aNewSignatureIsNotAChange() throws {
        let a = try #require(making(#"{"scene_total": 2, "scene_done": 1, "scenes": [{"index": 1, "done": true, "thumb_url": "https://x.example/v/thumbs/1.jpg?X-Amz-Signature=aaa"}]}"#))
        let b = try #require(making(#"{"scene_total": 2, "scene_done": 1, "scenes": [{"index": 1, "done": true, "thumb_url": "https://x.example/v/thumbs/1.jpg?X-Amz-Signature=bbb"}]}"#))
        let c = try #require(making(#"{"scene_total": 2, "scene_done": 2, "scenes": [{"index": 1, "done": true, "thumb_url": "https://x.example/v/thumbs/1.jpg?X-Amz-Signature=bbb"}]}"#))
        #expect(a.visiblyEqual(b) && !a.visiblyEqual(c))
    }

    @Test func theStatusBodyOfAVideoStillBeingMade() throws {
        let m = try #require(MakingInfo.fromStatusBody(Data(#"{"message": "not ready", "status": "VIDEO_GENERATION", "making": {"scene_total": 3, "scene_done": 1}}"#.utf8)))
        #expect(m.sceneTotal == 3)
        #expect(MakingInfo.fromStatusBody(Data(#"{"message": "not ready", "status": "PLOT_CREATION"}"#.utf8)) == nil)
        #expect(MakingInfo.fromStatusBody(Data("<html>".utf8)) == nil)
        #expect(MakingInfo.fromStatusBody(Data()) == nil)
    }

    @Test func aMalformedMakingNeverFailsTheList() throws {
        let body = #"{"items": [{"video_id": "a", "status": "VIDEO_GENERATION", "making": "broken"}, {"video_id": "b", "status": "VIDEO_GENERATION", "making": {"scene_total": 4, "scene_done": 1, "scenes": [{"index": 1, "done": true}]}}, {"video_id": "c", "status": "COMPLETE"}]}"#
        let items = try JSONDecoder().decode(VideoListResponse.self, from: Data(body.utf8)).items
        #expect(items.count == 3)
        #expect(items[0].making == nil && items[2].making == nil)
        #expect(items[1].making?.sceneTotal == 4)
    }
}

/// Applies an event and checks whether the capsule took it.
private func step(_ c: inout CreateCapsule, _ e: CreateCapsule.Event, taken: Bool = true, sourceLocation: SourceLocation = #_sourceLocation) {
    let r = c.handle(e)
    #expect(r == taken, "\(e)", sourceLocation: sourceLocation)
}

/// After the Create tap (design bar, signature 2): locked, honest, and exactly one of four endings.
@Suite struct CreateCapsuleTests {
    @Test func aCheckedRequestGoesToMaking() {
        var c = CreateCapsule()
        #expect(!c.isLocked && !c.canCancel && c.ending == nil)
        step(&c, .tapCreate(needsCheck: true))
        #expect(c.phase == .checking(slow: false) && c.isLocked && c.canCancel)
        step(&c, .slow)
        #expect(c.isSlow && c.canCancel)
        step(&c, .slow, taken: false)          // slow is said once
        step(&c, .checkPassed)
        #expect(c.phase == .starting && c.isLocked && !c.canCancel, "once it is starting it is on its way: no Cancel")
        step(&c, .started)
        #expect(c.ending == .making && c.phase == .starting, "the button never flashes back before the screen closes")
    }

    @Test func withoutACheckItStartsAtOnce() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: false))
        #expect(c.phase == .starting)
    }

    @Test func aSecondTapDoesNothing() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: true))
        let before = c
        step(&c, .tapCreate(needsCheck: true), taken: false)
        #expect(c == before)
        step(&c, .checkPassed)
        step(&c, .tapCreate(needsCheck: false), taken: false)
        step(&c, .confirmed, taken: false)
    }

    @Test func cancelGivesTheFormBackAndALateAnswerIsIgnored() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: true))
        step(&c, .cancel)
        #expect(c.phase == .button && c.ending == .restored && !c.isLocked)
        for late in [CreateCapsule.Event.checkPassed, .needsQuestions, .refused, .started, .failed, .slow] { step(&c, late, taken: false) }
        #expect(c.phase == .button && c.ending == .restored)
    }

    @Test func cancelIsNotPossibleOnceStarting() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: false))
        step(&c, .cancel, taken: false)
        #expect(c.phase == .starting)
    }

    @Test func questionsThenConfirmed() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: true))
        step(&c, .needsQuestions)
        #expect(c.ending == .question && c.phase == .button)
        step(&c, .confirmed)
        #expect(c.phase == .starting && c.ending == nil)
    }

    @Test func aRefusalAtEitherStepRestoresTheForm() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: true))
        step(&c, .refused)
        #expect(c.ending == .refusal && !c.isLocked)
        step(&c, .tapCreate(needsCheck: false))
        #expect(c.ending == nil, "a new run forgets the last ending")
        step(&c, .refused)
        #expect(c.ending == .refusal && c.phase == .button)
    }

    @Test func aFailedStartRestoresEverything() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: false))
        step(&c, .failed)
        #expect(c.ending == .restored && c.phase == .button)
        step(&c, .failed, taken: false)
        step(&c, .started, taken: false)
    }

    @Test func everyRunEndsInExactlyOneOfFour() {
        // every event sequence of length 5 after the tap: an unlocked capsule always has an ending, a locked one has none (or is on its way to Making)
        let events: [CreateCapsule.Event] = [.slow, .checkPassed, .needsQuestions, .refused, .cancel, .confirmed, .started, .failed]
        var bad = 0
        func walk(_ c: CreateCapsule, _ depth: Int) {
            if c.isLocked { if !(c.ending == nil || c.ending == .making) { bad += 1 } } else if c.ending == nil || c.ending == .making { bad += 1 }
            guard depth > 0 else { return }
            for e in events { var n = c; if n.handle(e) { walk(n, depth - 1) } }
        }
        for check in [true, false] { var c = CreateCapsule(); c.handle(.tapCreate(needsCheck: check)); walk(c, 5) }
        #expect(bad == 0)
    }

    @Test func resetIsAFreshScreen() {
        var c = CreateCapsule()
        step(&c, .tapCreate(needsCheck: true)); step(&c, .refused); c.reset()
        #expect(c == CreateCapsule())
    }
}
