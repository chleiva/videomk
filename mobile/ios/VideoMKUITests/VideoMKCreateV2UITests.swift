import XCTest

/// The redesigned Create screen (docs/design_bar/CREATE_SCREEN_REDESIGN_BRIEF.md): one dock, a row of pills with glyphs, ONE tool row with the compact Create pill.
/// Fake in-app server, no network. The tests MEASURE (dock height, targets, edges) and assert the budget; `testCaptures` writes a screenshot of every state
/// into `TEST_RUNNER_VMK_SHOTS_DIR` (`TEST_RUNNER_VMK_SHOTS_MODE=dark|large|es`).
final class VideoMKCreateV2UITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private var mode: String { ProcessInfo.processInfo.environment["VMK_SHOTS_MODE"] ?? "" }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func fixture(_ lang: String) -> String { URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/looks_\(lang).json").path }

    /// A returning account (`videos`: the fake library has finished videos) or a first-time one (none). `looks`: what the fake server lists for the picker.
    private func launch(videos: Bool = false, balance: Int = 11, looks: String? = nil, spanish: Bool? = nil, _ env: [String: String] = [:]) -> XCUIApplication {
        let es = spanish ?? (mode == "es")
        let app = es ? XCUIApplication.spanish() : XCUIApplication.english()
        if mode == "dark" { app.launchArguments += ["-AppleInterfaceStyle", "Dark"] }
        if mode == "large" { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        app.launchEnvironment["VMK_DEBUG_BALANCE"] = String(balance)
        app.launchEnvironment["VMK_DEBUG_CREATE"] = "empty"
        app.launchEnvironment["VMK_DEBUG_FORGET_CREATE"] = "1"
        app.launchEnvironment["VMK_DEBUG_DEFAULT_MINUTES"] = "2"      // 2 credits, as in the brief's caption
        if videos { app.launchEnvironment["VMK_DEBUG_FAKE_VIDEOS"] = "bar" }
        if let looks { app.launchEnvironment["VMK_DEBUG_LOOKS"] = looks; app.launchEnvironment["VMK_DEBUG_LOOKS_FILE"] = fixture(es ? "es" : "en") }
        for (k, v) in env { app.launchEnvironment[k] = v.isEmpty ? nil : v }
        app.launch()
        return app
    }

    private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }

    @discardableResult private func ready(_ app: XCUIApplication, _ id: String = "sendButton") -> XCUIElement {
        let e = el(app, id)
        XCTAssertTrue(e.waitForExistence(timeout: 25), "\(id) is on screen")
        return e
    }

    private func shot(_ app: XCUIApplication, _ name: String, wait: UInt32 = 1) {
        guard let dir = ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] else { return }
        sleep(wait)
        try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
    }

    // MARK: the measurements and the budget

    /// The empty state of a returning account: nothing but the sentence and the dock.
    func testEmptyStateIsOneDockAndTheBudgetHolds() {
        let app = launch(videos: true)
        let send = ready(app)
        let field = el(app, "composerField"), dock = el(app, "createDock")
        XCTAssertTrue(dock.waitForExistence(timeout: 5))
        sleep(1)
        XCTAssertEqual(app.buttons.matching(identifier: "createExample").count, 0, "no example chips once the account has a finished video")
        XCTAssertFalse(el(app, "costCaption").exists, "no standing caption after the first video")
        XCTAssertFalse(el(app, "statusLine").exists, "no standing helper line")
        XCTAssertFalse(app.staticTexts["Describe your video"].exists, "the helper line is deleted")
        let window = app.windows.firstMatch.frame
        // the dock: pills + tool row. Brief: about 124 pt, about 172 with two pill rows.
        print("MEASURE dock height=\(dock.frame.height) send=\(send.frame.size) pills.minY=\(el(app, "forPill").frame.minY) window=\(window.size)")
        XCTAssertLessThanOrEqual(dock.frame.height, 132, "the dock is one row of pills and one tool row")
        XCTAssertGreaterThanOrEqual(send.frame.height, 48 - 0.5); XCTAssertLessThanOrEqual(send.frame.height, 48 + 0.5, "Create is 48 pt high")
        XCTAssertGreaterThanOrEqual(send.frame.width, 112 - 0.5, "Create is 112 pt wide at least")
        // one tool row: photos, mic, Options on the left of Create, all on one line
        for id in ["photoButton", "micButton", "moreOptions"] { XCTAssertEqual(el(app, id).frame.midY, send.frame.midY, accuracy: 3, "\(id) shares the row with Create") }
        XCTAssertLessThan(el(app, "micButton").frame.maxX, send.frame.minX, "the mic stays on the left, away from Create")
        XCTAssertGreaterThan(send.frame.minX, window.width / 2, "Create is at the trailing end")
        XCTAssertEqual(send.frame.maxX, window.width - 20, accuracy: 1.5, "Create ends on the gutter")
        // the inactive Create still says what it costs and what is missing
        XCTAssertTrue((send.value as? String ?? "").contains("Not ready"), "inactive: \(send.value as? String ?? "")")
        // one left edge: the sentence, the first pill and the first tool start at the 20 pt gutter
        let edges = [field.frame.minX, el(app, "forPill").frame.minX, el(app, "photoButton").frame.minX]
        print("MEASURE left edges=\(edges)")
        for e in edges { XCTAssertEqual(e, 20, accuracy: 1.5, "one left edge") }
        // elements and targets (the empty state of a returning account)
        let targets = app.buttons.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.count + app.textFields.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.count
        let texts = app.staticTexts.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.map { $0.label }
        print("MEASURE returning tap targets=\(targets) staticTexts=\(texts)")
        XCTAssertLessThanOrEqual(targets, 10, "X, field, photos, mic, Options, three pills, Create (+ the balance chip behind the sheet is not hittable)")
        // clear space below the tool row: down to the keyboard (or the screen edge)
        let keyboard = app.keyboards.firstMatch
        let floor = keyboard.exists ? keyboard.frame.minY : window.maxY
        print("MEASURE clear space below the tool row=\(floor - send.frame.maxY) keyboard=\(keyboard.exists)")
    }

    /// A first-time account: two or three examples and the one caption that teaches the price.
    func testFirstVideoAccountSeesExamplesAndTheCaption() {
        let app = launch(videos: false, balance: 11)
        ready(app)
        let chips = app.buttons.matching(identifier: "createExample")
        XCTAssertTrue(chips.firstMatch.waitForExistence(timeout: 10))
        XCTAssertTrue((2...3).contains(chips.count), "two or three examples: \(chips.count)")
        let caption = el(app, "costCaption")
        XCTAssertTrue(caption.waitForExistence(timeout: 5), "the first-video caption")
        XCTAssertEqual(caption.label, "2 credits. You have 11.")
        let targets = app.buttons.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.count + app.textFields.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.count
        let dock = el(app, "createDock")
        print("MEASURE first-video dock height=\(dock.frame.height) targets=\(targets) chips=\(chips.count)")
        XCTAssertLessThanOrEqual(targets, 13)
        // an example fills the sentence and the chips step aside
        chips.firstMatch.tap()
        let field = el(app, "composerField")
        wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in ((field.value as? String) ?? "").count > 20 }, object: nil)], timeout: 10)
        XCTAssertEqual(chips.count, 0)
        XCTAssertTrue((el(app, "sendButton").value as? String ?? "").contains("Ready, costs 2 credits"), "credits in words: \(el(app, "sendButton").value as? String ?? "")")
    }

    /// A tap on the inactive Create explains what is missing and puts the caret in the sentence.
    func testInactiveCreateExplainsOnTap() {
        let app = launch(videos: true)
        ready(app).tap()
        XCTAssertTrue(el(app, "costLine").waitForExistence(timeout: 5), "the line says what is missing")
        XCTAssertEqual(el(app, "costLine").label, "Describe your video")
    }

    /// Recording: the mic is a Stop, "Listening…" is in the tool row, photos and Options are off, Create is inactive.
    func testRecordingStateLeavesOnlyStop() {
        let app = launch(videos: true, ["VMK_DEBUG_LISTENING": "1"])
        let send = ready(app)
        el(app, "micButton").tap()
        XCTAssertTrue(el(app, "listeningHint").waitForExistence(timeout: 5), "Listening… shows")
        XCTAssertEqual(el(app, "listeningHint").frame.midY, send.frame.midY, accuracy: 4, "in the tool row")
        XCTAssertFalse(el(app, "photoButton").isEnabled, "attach is off while listening")
        XCTAssertFalse(el(app, "moreOptions").isEnabled, "Options is off while listening")
        XCTAssertEqual(el(app, "micButton").label, "Stop dictation")
        XCTAssertTrue((send.value as? String ?? "").contains("Not ready"), "Create is inactive until stop")
        el(app, "micButton").tap()
        XCTAssertTrue(el(app, "listeningHint").waitForNonExistence(timeout: 5))
        XCTAssertTrue(el(app, "photoButton").isEnabled)
    }

    /// Typing: Create goes active and the price is part of the label. Options no longer repeats the pills.
    func testTypingActivatesCreateAndOptionsHasNoDuplicates() {
        let app = launch(videos: true)
        let send = ready(app)
        let field = app.textFields["composerField"]
        field.tap(); field.typeText("How bees make honey, explained for kids")
        XCTAssertTrue((send.value as? String ?? "").contains("Ready, costs 2 credits"), "\(send.value as? String ?? "")")
        app.buttons["moreOptions"].tap()
        XCTAssertTrue(el(app, "subtitlesToggle").waitForExistence(timeout: 5))
        XCTAssertFalse(el(app, "optPlatform-shorts").exists, "no For chips in Options")
        XCTAssertFalse(el(app, "look-auto").exists, "no Look swatches in Options")
        XCTAssertTrue(el(app, "languageRow").exists)
    }

    /// With a look that has a cast: the Characters pill, and the pills stay in two rows at most.
    func testCastLookKeepsThePillsInTwoRows() {
        let app = launch(videos: true, looks: "1", ["VMK_DEBUG_LOOK": "cartoon:fox+bear"])
        ready(app, "castPill")
        let rows = Set(["forPill", "lengthPill", "lookPill", "castPill"].map { Int((el(app, $0).frame.midY / 4).rounded()) }).count
        XCTAssertLessThanOrEqual(rows, 2, "pills in at most two rows")
        XCTAssertEqual(el(app, "sendButton").frame.height, 48, accuracy: 0.5)
        print("MEASURE cast dock height=\(el(app, "createDock").frame.height) rows=\(rows)")
    }

    /// Creating: the form locks and the capsule replaces the dock.
    func testCreatingSpringsIntoTheCapsule() {
        let app = launch(videos: true, ["VMK_DEBUG_CREATE": "filled"])
        ready(app).tap()
        XCTAssertTrue(el(app, "createCapsule").waitForExistence(timeout: 10), "the live capsule")
        XCTAssertFalse(el(app, "sendButton").exists)
    }

    // MARK: every state

    func testCaptures() throws {
        guard ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] != nil else { throw XCTSkip("set TEST_RUNNER_VMK_SHOTS_DIR") }
        var app: XCUIApplication

        app = launch(videos: false); ready(app); sleep(1); shot(app, "01-empty-first-video"); app.terminate()
        app = launch(videos: true); ready(app); sleep(1); shot(app, "02-empty-returning")
        ready(app).tap(); sleep(1); shot(app, "02b-empty-inactive-tapped"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_CREATE": "filled"]); ready(app); shot(app, "03-typed-active"); app.terminate()
        app = launch(videos: true); let f = ready(app, "composerField"); f.tap(); f.typeText("How bees make honey, explained for kids"); shot(app, "03b-typing-keyboard"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_CREATE": "photos"]); ready(app); shot(app, "04-with-photos"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_LISTENING": "1"]); ready(app); el(app, "micButton").tap(); ready(app, "listeningHint"); shot(app, "05-recording"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_CREATE": "checkingfast"]); ready(app, "createCapsule"); shot(app, "06-creating-checking"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_CREATE": "checking"]); ready(app, "createCapsule"); shot(app, "06b-creating-slow"); app.terminate()
        app = launch(videos: true, looks: "1", ["VMK_DEBUG_CREATE": "filled", "VMK_DEBUG_LOOK": "cartoon:fox+bear"]); ready(app, "castPill"); shot(app, "07-look-with-cast"); app.terminate()
        app = launch(videos: true, looks: "1", ["VMK_DEBUG_CREATE": "filled", "VMK_DEBUG_LOOK": "cartoon:priya+mateo+cat", "VMK_DEBUG_DEFAULT_MINUTES": "0.25"]); ready(app, "castPill"); shot(app, "07b-look-with-three-faces"); app.terminate()
        app = launch(videos: true, looks: "locked", ["VMK_DEBUG_CREATE": "filled", "VMK_DEBUG_LOOK": "sheet"]); ready(app, "lookTile-auto"); shot(app, "08-look-sheet-plan-locked"); app.terminate()
        app = launch(videos: true, balance: 1, ["VMK_DEBUG_CREATE": "notaffordable"]); ready(app); shot(app, "09-not-enough-credits"); app.terminate()
        app = launch(videos: true, balance: 3, ["VMK_DEBUG_CREATE": "filled"]); ready(app); shot(app, "09b-low-balance-caption"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_CREATE": "startfailed"]); ready(app); shot(app, "10-error-start-failed"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_CREATE": "options"]); ready(app, "subtitlesToggle"); shot(app, "11-options-sheet"); app.terminate()
        app = launch(videos: true, ["VMK_DEBUG_CREATE": "overmax"]); ready(app); shot(app, "12-over-platform-limit"); app.terminate()
        app = launch(videos: false, balance: 11, ["VMK_DEBUG_CREATE": "filled"]); ready(app); shot(app, "13-first-video-caption-active"); app.terminate()
    }
}
