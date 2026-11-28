import Testing
@testable import VideoMKCore

@Suite struct DictationTextTests {
    @Test func composeAddsOneSpaceAndNeverDoublesIt() {
        #expect(DictationText.compose("", "hello") == "hello")
        #expect(DictationText.compose("A video", "about bees") == "A video about bees")
        #expect(DictationText.compose("A video  ", "about bees") == "A video about bees")
        #expect(DictationText.compose("Line one\n", "line two") == "Line one\nline two")
        #expect(DictationText.compose("keep", "   ") == "keep")
    }

    @Test func speakingAgainAppendsInsteadOfReplacing() {
        var d = DictationText(startingWith: "About bees")
        var field = "About bees"
        func hear(_ s: String) { if case .write(let t) = d.hear(s, field: field) { field = t } }
        func fold(_ s: String) { if case .write(let t) = d.fold(s, field: field) { field = t } }
        hear("and"); hear("and honey"); fold("and honey")
        #expect(field == "About bees and honey")
        hear("for"); hear("for kids")      // a new task: its transcript starts empty again
        #expect(field == "About bees and honey for kids")
        fold("for kids")
        #expect(field == "About bees and honey for kids")
    }

    @Test func partialResultsNeverResetTheBase() {
        var d = DictationText(startingWith: "")
        var field = ""
        for s in ["a", "a b", "a b c"] { if case .write(let t) = d.hear(s, field: field) { field = t } }
        #expect(field == "a b c")
        #expect(d.base == "")
    }

    @Test func aHandEditDuringDictationRebasesAndIsNeverOverwritten() {
        var d = DictationText(startingWith: "Bees")
        var field = "Bees"
        if case .write(let t) = d.hear("and honey", field: field) { field = t }
        field = "Bees and honey, no wasps"      // the person typed
        #expect(d.hear("and honey and more", field: field) == .rebased)
        #expect(d.base == "Bees and honey, no wasps")
        // the recognizer restarts: its next transcript is new speech, appended after the typed text
        #expect(d.hear("flowers", field: field) == .write("Bees and honey, no wasps flowers"))
    }

    @Test func textTypedBeforeTheFirstWordIsKept() {
        var d = DictationText(startingWith: "x")
        #expect(d.hear("y", field: "x typed") == .rebased)
        #expect(d.base == "x typed")
    }

    @Test func restartPolicyKeepsGoingThroughPausesAndStopsOnLimits() {
        var p = DictationRestartPolicy(maxSeconds: 300, idleSeconds: 60, maxRapidFailures: 3)
        p.sessionStarted(now: 0)
        p.taskStarted(now: 0)
        p.textArrived(now: 50)
        #expect(p.taskEnded(hadText: true, now: 55) == .restart)       // the roughly one minute limit
        p.taskStarted(now: 55)
        #expect(p.taskEnded(hadText: false, now: 70) == .restart)      // a pause
        p.taskStarted(now: 70)
        #expect(p.taskEnded(hadText: false, now: 130) == .stopIdle)    // a minute of nothing since the last words
        var q = DictationRestartPolicy()
        q.sessionStarted(now: 0); q.taskStarted(now: 0)
        #expect(q.taskEnded(hadText: true, now: 301) == .stopTimeLimit)
    }

    @Test func aRecognizerThatFailsAtOnceDoesNotLoop() {
        var p = DictationRestartPolicy()
        p.sessionStarted(now: 0)
        var actions: [DictationRestartPolicy.Action] = []
        for i in 0..<3 { p.taskStarted(now: Double(i) * 0.3); actions.append(p.taskEnded(hadText: false, now: Double(i) * 0.3 + 0.1)) }
        #expect(actions == [.restart, .restart, .stopFailing])
    }

    @Test func languageFollowsTheAppAndFallsBackLoudly() {
        let supported = ["en-US", "en-GB", "es-ES", "es-MX", "fr-FR"]
        // Spanish app on an English phone: Spanish, not English
        #expect(DictationLocaleChoice.resolve(app: .es, deviceLanguages: ["en-US"], region: "US", supported: supported) == .init(tag: "es-MX", fellBack: false))
        #expect(DictationLocaleChoice.resolve(app: .es, deviceLanguages: ["es-ES"], region: "ES", supported: supported) == .init(tag: "es-ES", fellBack: false))
        #expect(DictationLocaleChoice.resolve(app: .en, deviceLanguages: ["es-ES"], region: "GB", supported: supported) == .init(tag: "en-GB", fellBack: false))
        // the recognizer has no Spanish here: the phone's other language, reported
        #expect(DictationLocaleChoice.resolve(app: .es, deviceLanguages: ["es-MX", "fr-FR"], region: nil, supported: ["en-US", "fr-FR"]) == .init(tag: "fr-FR", fellBack: true))
        #expect(DictationLocaleChoice.resolve(app: .es, deviceLanguages: ["es-MX"], region: nil, supported: ["en-US"]) == .init(tag: "en-US", fellBack: true))
        // supported list unknown: trust the app language
        #expect(DictationLocaleChoice.resolve(app: .es, deviceLanguages: [], region: nil, supported: []).fellBack == false)
    }
}
