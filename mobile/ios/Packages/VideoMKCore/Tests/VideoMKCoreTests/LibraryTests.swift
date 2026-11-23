import Foundation
import Testing
@testable import VideoMKCore

@Suite struct LibraryTests {
    let now = Date(timeIntervalSince1970: 1_000_000)

    func pending(_ id: String, _ state: PendingVideo.State = .sending, age: TimeInterval = 0) -> PendingVideo {
        PendingVideo(id: id, brief: "A brief about \(id)", options: CreateOptions(), state: state, createdAt: now.addingTimeInterval(-age))
    }
    func video(_ id: String, _ status: VideoStatus = .complete) -> VideoItem { VideoItem(id: id, status: status) }

    @Test func placeholdersComeFirstNewestFirstThenServerOrder() {
        let e = LibraryMerge.entries(pending: [pending("old", age: 30), pending("new", age: 1)], server: [video("s1"), video("s2")])
        #expect(e.map(\.id) == ["pending-new", "pending-old", "s1", "s2"])
    }

    @Test func aPlaceholderHandsOverToTheServerRowWithoutDuplicates() {
        let p = pending("p1", .accepted(videoID: "v1"))
        // server doesn't list it yet: the placeholder stays
        #expect(LibraryMerge.entries(pending: [p], server: [video("other")]).map(\.id) == ["pending-p1", "other"])
        // once the server lists it, only the server row remains
        let after = LibraryMerge.entries(pending: [p], server: [video("v1", .running(.writing)), video("other")])
        #expect(after.map(\.id) == ["v1", "other"])
    }

    @Test func sendingAndFailedPlaceholdersAreNeverDropped() {
        let s = [pending("a"), pending("b", .failed("No connection"))]
        #expect(LibraryMerge.entries(pending: s, server: [video("x")]).count == 3)
        #expect(LibraryMerge.stillPending(s, server: [video("x")]).count == 2)
    }

    @Test func stillPendingForgetsOnlyTheTakenOverOnes() {
        let s = [pending("a", .accepted(videoID: "v1")), pending("b", .accepted(videoID: "v2"))]
        #expect(LibraryMerge.stillPending(s, server: [video("v1")]).map(\.id) == ["b"])
    }

    @Test func progressNeverGoesBackwardsAcrossStagesAndNeverReachesDone() {
        var last = -1.0
        for stage in VideoStatus.Stage.allCases {
            for seconds in stride(from: 0.0, through: 600, by: 5) {
                let f = ProgressEstimator.fraction(stage: stage, secondsInStage: seconds)
                #expect(f >= last - 1e-9 || seconds == 0)  // within a stage it only grows; a new stage starts at its own floor
                #expect(f < 0.97 + 1e-9)
                last = f
            }
            last = -1
        }
    }

    @Test func eachStageStartsWhereThePreviousOneCannotReach() {
        let stages = VideoStatus.Stage.allCases
        for (a, b) in zip(stages, stages.dropFirst()) {
            let endOfA = ProgressEstimator.fraction(stage: a, secondsInStage: 10_000)
            let startOfB = ProgressEstimator.fraction(stage: b, secondsInStage: 0)
            #expect(endOfA < startOfB)  // so the bar never jumps backwards when the server moves to the next stage
        }
    }

    @Test func rowStageNamesFitOnOneLine() {
        for s in VideoStatus.Stage.allCases { #expect(s.shortTitle.count <= 20) }
    }

    @Test func longerVideosTakeLongerPerStage() {
        #expect(ProgressEstimator.expectedSeconds(.rendering, minutes: 12) > ProgressEstimator.expectedSeconds(.rendering, minutes: 1))
        let slow = ProgressEstimator.fraction(stage: .rendering, secondsInStage: 60, minutes: 12)
        let fast = ProgressEstimator.fraction(stage: .rendering, secondsInStage: 60, minutes: 1)
        #expect(slow < fast)
    }
}
