import XCTest

/// The signature interactions of docs/DESIGN_BAR_2026.md, on the fake-library build (no network, debug builds only): the Create capsule and its endings,
/// the Making screen in its three states (pictures, tiles without pictures, nothing from the server), the player's actions and "Make another".
/// Screenshots: set `TEST_RUNNER_VMK_SHOTS_DIR`.
final class VideoMKDesignBarUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func launch(spanish: Bool = false, _ env: [String: String]) -> XCUIApplication {
        let app = spanish ? XCUIApplication.spanish() : XCUIApplication.english()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        for (k, v) in env { app.launchEnvironment[k] = v }
        app.launch()
        return app
    }

    private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }

    private func shot(_ app: XCUIApplication, _ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] else { return }
        sleep(1)
        try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("bar-\(name).png"))
    }

    /// Every static text on screen, joined (to check what the screen does NOT say).
    private func allText(_ app: XCUIApplication) -> String { app.staticTexts.allElementsBoundByIndex.map { $0.label }.joined(separator: " | ") }

    // MARK: Making

    func testMakingScreenTellsAStoryWithoutStepNamesOrPercentages() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v1"])
        XCTAssertTrue(el(app, "liveLine").waitForExistence(timeout: 20), "one live line")
        XCTAssertEqual(el(app, "makingTitle").label, "How honey is made")
        XCTAssertEqual(el(app, "sceneCounter").label, "Scene 5 of 9")
        XCTAssertTrue(el(app, "narrationLine").exists, "the sentence being narrated")
        XCTAssertTrue(el(app, "timeAbout").exists)
        XCTAssertTrue(el(app, "notifySwitch").exists, "one switch: Tell me when it's ready")
        XCTAssertTrue(el(app, "backButton").exists, "a visible way back")
        let text = allText(app)
        XCTAssertFalse(text.contains("%"), "no percentages: \(text)")
        for step in ["Script", "Voice", "Pictures", "Final cut"] { XCTAssertFalse(text.contains(step), "no step names (\(step)): \(text)") }
        shot(app, "making-pictures")
        app.buttons["backButton"].tap()
        XCTAssertTrue(el(app, "runningRow").waitForExistence(timeout: 5), "back on Videos, the Making card is there")
        XCTAssertTrue(el(app, "runningRow").label.contains("Scene 5 of 9"), "the card and the screen say the same: \(el(app, "runningRow").label)")
    }

    func testMakingDegradesWithoutPicturesAndWithoutMaking() {
        var app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v1", "VMK_DEBUG_MAKING": "tiles"])
        XCTAssertTrue(el(app, "sceneCounter").waitForExistence(timeout: 20), "scenes without pictures still count")
        shot(app, "making-tiles")
        app.terminate()
        app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v1", "VMK_DEBUG_MAKING": "none"])
        XCTAssertTrue(el(app, "liveLine").waitForExistence(timeout: 20), "an older server: a calm state with one line")
        XCTAssertFalse(el(app, "sceneCounter").exists, "no invented scene numbers")
        XCTAssertTrue(el(app, "timeAbout").exists && el(app, "notifySwitch").exists)
        XCTAssertFalse(el(app, "narrationLine").exists)
        XCTAssertFalse(el(app, "liveLine").label.isEmpty, "one line from the status")
        XCTAssertFalse(allText(app).contains("%"))
        shot(app, "making-none")
    }

    func testMakingIsSpanish() {
        let app = launch(spanish: true, ["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v1"])
        XCTAssertTrue(el(app, "sceneCounter").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "sceneCounter").label, "Escena 5 de 9")
        shot(app, "making-es")
    }

    // MARK: Create

    private func typeAndCreate(_ app: XCUIApplication, _ sentence: String) {
        let field = el(app, "composerField")
        XCTAssertTrue(field.waitForExistence(timeout: 20))
        field.tap(); field.typeText(sentence)
        app.buttons["sendButton"].tap()
    }

    /// Three taps: New video, type, Create. The button becomes the capsule and the screen ends on the Making card.
    func testCreateEndsOnTheMakingCard() {
        let app = launch([:])
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20))
        app.buttons["newVideo"].tap()
        typeAndCreate(app, "How a forest breathes, calm and warm")
        XCTAssertTrue(el(app, "createCapsule").waitForExistence(timeout: 5), "the button becomes the live capsule")
        XCTAssertFalse(app.buttons["sendButton"].exists, "nothing to tap twice")
        shot(app, "create-capsule")
        let card = app.descendants(matching: .any).matching(NSPredicate(format: "identifier IN %@", ["runningRow", "pendingRow"])).firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 30), "Create closes onto the Making card")
        XCTAssertFalse(el(app, "composerField").exists)
        XCTAssertTrue(card.label.contains("How a forest breathes"), card.label)
    }

    /// The start fails: the form is back with everything in it, one line says what happened.
    func testAFailedStartRestoresTheForm() {
        let app = launch(["VMK_DEBUG_FAKE_START": "fail"])
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20))
        app.buttons["newVideo"].tap()
        typeAndCreate(app, "How a forest breathes, calm and warm")
        XCTAssertTrue(el(app, "startError").waitForExistence(timeout: 30), "one line says what happened")
        XCTAssertEqual(el(app, "composerField").value as? String, "How a forest breathes, calm and warm", "the sentence is intact")
        XCTAssertTrue(app.buttons["sendButton"].isEnabled, "one action: Create again")
        XCTAssertFalse(el(app, "createCapsule").exists)
        shot(app, "create-restored")
    }

    /// An example chip types its sentence into the prompt.
    func testAnExampleTypesItselfIn() {
        let app = launch(["VMK_DEBUG_CREATE": "empty"])
        let chip = app.buttons.matching(identifier: "createExample").firstMatch
        XCTAssertTrue(chip.waitForExistence(timeout: 20))
        XCTAssertEqual(app.buttons.matching(identifier: "createExample").count, 3, "three examples")
        chip.tap()
        let field = el(app, "composerField")
        let typed = NSPredicate { _, _ in ((field.value as? String) ?? "").count > 20 }
        wait(for: [XCTNSPredicateExpectation(predicate: typed, object: nil)], timeout: 10)
        XCTAssertFalse(chip.exists, "the examples step aside once there is a sentence")
        XCTAssertTrue(app.buttons["sendButton"].isEnabled)
    }

    // MARK: player

    func testPlayerHasOnePrimaryAndRemixOpensCreatePrefilled() {
        var env = ["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v3"]
        let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"] ?? ""
        if !file.isEmpty { env["VMK_DEBUG_PLAYBACK_FILE"] = file }
        let app = launch(env)
        XCTAssertTrue(el(app, "videoTitle").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "videoTitle").label, "How a forest breathes")
        XCTAssertTrue(el(app, "moreButton").exists)
        if !file.isEmpty {
            XCTAssertTrue(app.buttons["shareButton"].waitForExistence(timeout: 20), "Share is the one labelled primary")
            XCTAssertEqual(app.buttons["shareButton"].label, "Share")
            XCTAssertEqual(app.buttons["saveButton"].label, "Save to Photos")
            XCTAssertTrue(app.buttons["infoButton"].exists && app.buttons["editButton"].exists, "Save, Edit, Info and More are quiet icons with spoken labels")
        }
        shot(app, "player")
        let short = app.buttons["remix-short"]
        XCTAssertTrue(short.waitForExistence(timeout: 5), "Make it a Short is offered: the server can make vertical videos")
        short.tap()
        let field = el(app, "composerField")
        XCTAssertTrue(field.waitForExistence(timeout: 10), "the chip opens Create; nothing is sent yet")
        XCTAssertEqual(field.value as? String, "How a forest breathes", "the same sentence")
        XCTAssertTrue(app.buttons["sendButton"].isEnabled)
        shot(app, "remix-short-create")
    }
}
