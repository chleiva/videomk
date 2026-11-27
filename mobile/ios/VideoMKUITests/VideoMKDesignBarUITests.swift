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

    /// The video is over: Replay and New video on the last frame. Needs a short local mp4 (`TEST_RUNNER_VMK_DEBUG_SHORT_FILE`).
    func testEndCardOffersReplayAndNewVideo() throws {
        guard let file = ProcessInfo.processInfo.environment["VMK_DEBUG_SHORT_FILE"], !file.isEmpty else { throw XCTSkip("needs TEST_RUNNER_VMK_DEBUG_SHORT_FILE (a local mp4 of a few seconds)") }
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v3", "VMK_DEBUG_PLAYBACK_FILE": file, "VMK_DEBUG_AUTOPLAY": "1"])
        XCTAssertTrue(app.buttons["replayButton"].waitForExistence(timeout: 90), "the end card appears when the video is over")
        XCTAssertEqual(app.buttons["replayButton"].label, "Replay")
        XCTAssertEqual(app.buttons["endNewVideo"].label, "New video")
        shot(app, "end-card")
        app.buttons["replayButton"].tap()
        XCTAssertTrue(app.buttons["replayButton"].waitForNonExistence(timeout: 3), "Replay starts it again")
        XCTAssertTrue(app.buttons["replayButton"].waitForExistence(timeout: 90))
        app.buttons["endNewVideo"].tap()
        XCTAssertTrue(el(app, "composerField").waitForExistence(timeout: 10), "New video opens Create")
    }

    // MARK: audit 2026-11-27

    /// One full-screen control: the system's. Ours is gone; a wide video turns the screen sideways and leaving full screen turns it back upright.
    func testFullScreenIsTheSystemControlAndComesBackUpright() throws {
        guard let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"], !file.isEmpty else { throw XCTSkip("needs TEST_RUNNER_VMK_DEBUG_PLAYBACK_FILE (a local mp4)") }
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v3", "VMK_DEBUG_PLAYBACK_FILE": file])
        XCTAssertTrue(app.buttons["shareButton"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.buttons["fullScreenButton"].exists, "no second full-screen button of our own")
        let window = app.windows.firstMatch
        XCTAssertGreaterThan(window.frame.height, window.frame.width)
        let enter = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'full screen' OR identifier CONTAINS[c] 'full screen'")).firstMatch
        if !enter.exists { el(app, "player").tap() }          // the system controls show on a tap
        if !enter.waitForExistence(timeout: 5) { print("TREE:", app.debugDescription) }
        XCTAssertTrue(enter.exists, "the system player offers full screen")
        enter.tap()
        let turned = Date().addingTimeInterval(10)
        while window.frame.width <= window.frame.height && Date() < turned { usleep(300_000) }
        sleep(3)        // let the rotation settle
        shot(app, "player-fullscreen")
        if let hold = ProcessInfo.processInfo.environment["VMK_HOLD_FULLSCREEN"], let secs = UInt32(hold) { sleep(secs) }   // lets the host take a real framebuffer screenshot
        XCTAssertGreaterThan(window.frame.width, window.frame.height, "a wide video is shown sideways in full screen")
        let exit = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'full screen' OR label CONTAINS[c] 'close' OR identifier CONTAINS[c] 'full screen'")).firstMatch
        if !exit.exists { app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        if !exit.waitForExistence(timeout: 5) { print("TREE2:", app.debugDescription) }
        exit.tap()
        let back = Date().addingTimeInterval(10)
        while window.frame.width >= window.frame.height && Date() < back { usleep(300_000) }
        XCTAssertGreaterThan(window.frame.height, window.frame.width, "back on the page, upright")
        XCTAssertTrue(app.buttons["shareButton"].waitForExistence(timeout: 10))
        shot(app, "player-after-fullscreen")
    }

    /// Delete lives in the player's More menu. The video leaves the list at once, "Deleted · Undo" shows, and Undo brings it back.
    func testDeleteAVideoFromMoreAndUndo() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v3"])
        XCTAssertTrue(el(app, "moreButton").waitForExistence(timeout: 20))
        el(app, "moreButton").tap()
        XCTAssertTrue(app.buttons["deleteVideo"].waitForExistence(timeout: 5), "Delete is in More")
        app.buttons["deleteVideo"].tap()
        XCTAssertFalse(app.alerts.firstMatch.waitForExistence(timeout: 1), "no confirm dialog")
        XCTAssertTrue(el(app, "undoToast").waitForExistence(timeout: 5), "Deleted · Undo")
        XCTAssertFalse(app.staticTexts["How a forest breathes"].exists, "the video left the list at once")
        shot(app, "videos-deleted-undo")
        app.buttons["undoToastAction"].tap()
        XCTAssertTrue(app.staticTexts["How a forest breathes"].waitForExistence(timeout: 5), "Undo brings it back")
        XCTAssertTrue(el(app, "undoToast").waitForNonExistence(timeout: 3))
    }

    /// A video that did not finish says which video it is on its own page, with Try again and Remove; Remove can be undone.
    func testTheFailedPageNamesTheVideoAndOffersBothActions() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "1", "VMK_DEBUG_OPEN": "v2"])
        XCTAssertTrue(el(app, "failedPage").waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["Thailand highlights"].exists, "the title says which video")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Didn’t finish' AND label CONTAINS 'No credits were used.'")).firstMatch.exists, "the same words as in the list")
        XCTAssertTrue(app.buttons["tryAgain"].exists && app.buttons["removeVideo"].exists)
        shot(app, "failed-page")
        app.buttons["removeVideo"].tap()
        XCTAssertTrue(el(app, "undoToast").waitForExistence(timeout: 5))
        XCTAssertFalse(el(app, "failedVideo").exists, "gone from the list")
        app.buttons["undoToastAction"].tap()
        XCTAssertTrue(el(app, "failedVideo").waitForExistence(timeout: 5))
    }

    /// The video finished while the app was in the background (another app, the lock screen). Back in front, the list shows it as finished at once:
    /// not after the next poll, not after a pull to refresh.
    func testAVideoThatFinishedInTheBackgroundShowsAsFinishedAtOnce() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_FINISH_IN_BACKGROUND": "1"])
        XCTAssertTrue(el(app, "runningRow").waitForExistence(timeout: 20), "one video is being made")
        XCUIDevice.shared.press(.home)
        sleep(3)
        app.activate()
        XCTAssertTrue(el(app, "runningRow").waitForNonExistence(timeout: 2.5), "read immediately on return (the poll alone would take 4 s)")
        XCTAssertTrue(app.staticTexts["How honey is made"].waitForExistence(timeout: 3), "it is in the list as a finished video")
        shot(app, "back-from-background")
    }

    /// The same while its Making screen is open: it turns into the player without a manual refresh.
    func testAnOpenMakingScreenBecomesThePlayerAfterTheBackground() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v1", "VMK_DEBUG_FINISH_IN_BACKGROUND": "1"])
        XCTAssertTrue(el(app, "liveLine").waitForExistence(timeout: 20))
        XCUIDevice.shared.press(.home)
        sleep(3)
        app.activate()
        XCTAssertTrue(el(app, "videoTitle").waitForExistence(timeout: 2.5), "the Making screen became the video page at once")
        XCTAssertFalse(el(app, "liveLine").exists)
    }

    /// Making has a way out: More > Cancel video. No question; the credits of the attempt come back and the video becomes a cancelled one
    /// with Try again and Remove.
    func testCancelAVideoWhileItIsBeingMade() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v1"])
        XCTAssertTrue(el(app, "makingMore").waitForExistence(timeout: 20), "the Making screen has a More button")
        el(app, "makingMore").tap()
        XCTAssertTrue(app.buttons["cancelVideo"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["cancelVideo"].label, "Cancel video")
        app.buttons["cancelVideo"].tap()
        XCTAssertFalse(app.alerts.firstMatch.waitForExistence(timeout: 1), "no confirm dialog")
        XCTAssertTrue(app.staticTexts["Cancelled · 2 credits back"].waitForExistence(timeout: 5), "the toast says what came back")
        XCTAssertTrue(el(app, "cancelledPage").waitForExistence(timeout: 5), "the page shows the cancelled video")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Cancelled' AND label CONTAINS 'Your credits are back.'")).firstMatch.exists)
        XCTAssertTrue(app.buttons["tryAgain"].exists && app.buttons["removeVideo"].exists)
        XCTAssertFalse(el(app, "liveLine").exists)
        shot(app, "cancelled-page")
        el(app, "backButton").tap()
        XCTAssertTrue(el(app, "cancelledVideo").waitForExistence(timeout: 5), "and the list shows it as cancelled, not as failed")
    }
}
