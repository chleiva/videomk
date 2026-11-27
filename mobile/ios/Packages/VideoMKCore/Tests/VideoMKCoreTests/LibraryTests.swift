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

    @Test func dictationLanguageDefaultsFromThePhoneAndRespectsASavedChoice() {
        #expect(DictationLanguage.initial(saved: nil, preferred: ["en-US", "es-ES"]) == .english)
        #expect(DictationLanguage.initial(saved: nil, preferred: ["fr-FR", "es-MX"]) == .spanish)  // first supported one wins
        #expect(DictationLanguage.initial(saved: nil, preferred: ["fr-FR"]) == .english)
        #expect(DictationLanguage.initial(saved: "es", preferred: ["en-US"]) == .spanish)
        #expect(DictationLanguage.initial(saved: "xx", preferred: ["es-ES"]) == .spanish)
    }

    @Test func dictationPicksAnInstalledLocaleOfTheRightLanguageNearThePhonesRegion() {
        let supported = ["en-US", "en-GB", "es-ES", "es-MX", "es-US", "fr-FR"]
        #expect(DictationLanguage.spanish.locale(region: "ES", supported: supported) == "es-ES")
        #expect(DictationLanguage.spanish.locale(region: "US", supported: supported) == "es-US")
        #expect(DictationLanguage.spanish.locale(region: "AR", supported: supported) == "es-MX")  // no es-AR: the biggest Latin American one
        #expect(DictationLanguage.english.locale(region: "GB", supported: supported) == "en-GB")
        #expect(DictationLanguage.english.locale(region: "IN", supported: supported) == "en-US")
        #expect(DictationLanguage.spanish.locale(region: nil, supported: []) == "es-MX")
    }

    @Test func creditsAreStartedMinutes() {
        #expect([0.2, 1, 1.01, 2.5, 3, 12, 40].map { CreateOptions(minutes: $0).credits } == [1, 1, 2, 3, 3, 12, 12])
        #expect(CreateOptions().credits == 3)
        #expect(WalletInfo(balance: 2).canAfford(2) && !WalletInfo(balance: 2).canAfford(3))
        #expect(WalletInfo(balance: 0, unlimited: true).canAfford(12))   // test accounts are never blocked
    }

    @Test func decodesTheServersWalletShape() throws {
        let json = """
        {"balance":9,"buckets":[{"kind":"daily","remaining":2,"expires_at":1800000000},{"kind":"signup","remaining":5,"expires_at":1802000000},{"kind":"paid","remaining":2,"expires_at":null}],
         "next_daily_at":1800003600,"rules":{"credit_unit_seconds":60,"max_minutes":12,"signup":5,"daily":2,"signup_valid_days":30}}
        """
        let w = try JSONDecoder().decode(WalletInfo.self, from: Data(json.utf8))
        #expect(w.balance == 9 && w.buckets.map(\.kind) == [.daily, .signup, .paid] && w.buckets[2].expiresAt == nil && w.buckets[0].expiresAt != nil)
        #expect(w.nextFreeAt != nil && w.dailyCredits == 2 && w.signupCredits == 5 && !w.unlimited)
        let u = try JSONDecoder().decode(WalletInfo.self, from: Data(#"{"balance":999,"unlimited":true,"buckets":[]}"#.utf8))
        #expect(u.unlimited && u.canAfford(12))
    }

    @Test func nextFreeCreditIsSaidInPlainWords() {
        var cal = Calendar(identifier: .gregorian); cal.timeZone = TimeZone(identifier: "UTC")!
        let now = Date(timeIntervalSince1970: 1_800_000_000)            // 2027-01-15 08:00 UTC
        let midnight = cal.startOfDay(for: now).addingTimeInterval(86400)
        Localization.$override.withValue(.en) {
            #expect(Localization.shared.nextFree(midnight, now: now, calendar: cal) == "tomorrow")
            #expect(Localization.shared.nextFree(midnight.addingTimeInterval(86399), now: now, calendar: cal) == "tomorrow")
            #expect(Localization.shared.nextFree(now.addingTimeInterval(3 * 3600), now: now, calendar: cal) != "tomorrow")
            #expect(tr("wallet.next_free_n", 1, "tomorrow") == "1 free credit tomorrow" && tr("wallet.next_free_n", 3, "tomorrow") == "3 free credits tomorrow")
            #expect(tr("composer.fix.add_credits") == "See credits")
        }
        Localization.$override.withValue(.es) {
            #expect(Localization.shared.nextFree(midnight, now: now, calendar: cal) == "mañana")
            #expect(tr("wallet.next_free_n", 1, "mañana") == "1 crédito gratis mañana")
        }
    }
}
