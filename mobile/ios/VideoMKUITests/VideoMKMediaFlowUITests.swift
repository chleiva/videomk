import XCTest

/// The photos-to-video journey on the Media tab and in Create (fake library, no backend; debug builds only).
/// Screenshots: set `TEST_RUNNER_VMK_SHOTS_DIR` (and `TEST_RUNNER_VMK_SHOTS_PREFIX`, `TEST_RUNNER_VMK_SHOTS_MODE=dark`).
final class VideoMKMediaFlowUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func launch(spanish: Bool = false, env: [String: String] = [:]) -> XCUIApplication {
        let app = spanish ? XCUIApplication.spanish() : XCUIApplication.english()
        if ProcessInfo.processInfo.environment["VMK_SHOTS_MODE"] == "dark" { app.launchArguments += ["-AppleInterfaceStyle", "Dark"] }
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        app.launchEnvironment["VMK_DEBUG_TAB"] = "1"
        for (k, v) in env { app.launchEnvironment[k] = v }
        app.launch()
        return app
    }

    private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }

    private func shot(_ app: XCUIApplication, _ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] else { return }
        let prefix = ProcessInfo.processInfo.environment["VMK_SHOTS_PREFIX"] ?? ""
        sleep(1)
        try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(prefix)\(name).png"))
    }

    private func tapTiles(_ app: XCUIApplication, _ n: Int) {
        let tiles = app.descendants(matching: .any).matching(identifier: "mediaTile")
        XCTAssertTrue(tiles.firstMatch.waitForExistence(timeout: 20))
        for i in 0..<n { tiles.element(boundBy: i).tap() }
    }

    /// The upload action is one labelled button; no plain "+" competes with it; the storage line is not shown at 10% used.
    func testAddPhotosIsTheOneLabelledUploadAction() {
        let app = launch()
        XCTAssertTrue(el(app, "mediaTile").waitForExistence(timeout: 20))
        shot(app, "10-media-idle")
        XCTAssertEqual(app.buttons["addToLibraryButton"].label, "Add photos")
        XCTAssertTrue(app.buttons["selectButton"].exists && app.buttons["mediaMore"].exists)
        XCTAssertFalse(el(app, "storageMeter").exists, "a thin storage line at 10% used tells nobody anything")
        XCTAssertEqual(app.buttons["newCollection"].label, "New collection", "the small folder-plus in the Collections row")
        XCTAssertTrue(app.buttons["newVideo"].exists, "the round tab-bar button creates a video")
    }

    /// Select mode: the title counts, Cancel and Select all sit in the navigation bar, ONE primary button makes the video, the tab bar steps aside.
    func testSelectionHasOnePrimaryActionAndNothingCoversIt() {
        let app = launch()
        XCTAssertTrue(el(app, "mediaTile").waitForExistence(timeout: 20))
        app.buttons["selectButton"].tap()
        XCTAssertTrue(app.navigationBars.element.staticTexts["Select photos"].waitForExistence(timeout: 5) || app.staticTexts["Select photos"].waitForExistence(timeout: 2), "the title says what to do")
        XCTAssertFalse(app.buttons["newVideo"].exists, "the tab bar steps aside while selecting")
        XCTAssertFalse(app.buttons["makeVideoFromSelection"].isEnabled)
        shot(app, "11-select-mode-empty")
        tapTiles(app, 3)
        XCTAssertEqual(app.buttons["makeVideoFromSelection"].label, "Make a video · 3")
        XCTAssertTrue(app.buttons["makeVideoFromSelection"].isEnabled)
        XCTAssertTrue(app.staticTexts["3 selected"].exists, "the title counts")
        XCTAssertTrue(app.buttons["selectAll"].exists && app.buttons["selectCancel"].exists)
        let frame = app.buttons["makeVideoFromSelection"].frame
        XCTAssertLessThanOrEqual(frame.maxY, app.windows.firstMatch.frame.maxY, "the primary button is fully on screen")
        XCTAssertGreaterThanOrEqual(frame.height, 44)
        shot(app, "12-three-selected")
    }

    /// Photos to video in four taps (Select, photos, Make a video, Create's X brings the person back with the selection still ticked).
    func testMakeVideoAttachesThePhotosAndTheXComesBackToTheSelection() {
        let app = launch()
        XCTAssertTrue(el(app, "mediaTile").waitForExistence(timeout: 20))
        app.buttons["selectButton"].tap()
        tapTiles(app, 3)
        app.buttons["makeVideoFromSelection"].tap()
        XCTAssertTrue(el(app, "composerField").waitForExistence(timeout: 15), "Create opens")
        XCTAssertTrue(app.staticTexts["3 photos"].waitForExistence(timeout: 5), "the attached photos are counted")
        XCTAssertEqual(app.descendants(matching: .any).matching(identifier: "attachedLibraryPhoto").count, 3)
        XCTAssertTrue(app.buttons["Remove photo 1"].exists || app.buttons.matching(NSPredicate(format: "label BEGINSWITH 'Remove'")).count >= 3, "each photo has its own (x)")
        shot(app, "13-create-with-three-photos")
        app.buttons["createCancel"].tap()
        XCTAssertTrue(app.buttons["makeVideoFromSelection"].waitForExistence(timeout: 10), "back on Media, still selecting")
        XCTAssertEqual(app.buttons["makeVideoFromSelection"].label, "Make a video · 3", "the selection survived")
        shot(app, "14-back-on-media-selection-kept")
        app.buttons["selectCancel"].tap()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 5), "the tab bar is back")
    }

    /// After an upload finishes, the next step is on screen: Make a video from the photos just added.
    func testJustAddedPhotosOfferMakeAVideo() {
        let app = launch(env: ["VMK_DEBUG_UPLOAD_SCENE": "added"])
        XCTAssertTrue(el(app, "nextStepBar").waitForExistence(timeout: 20), "the next step is offered")
        shot(app, "15-next-step-after-upload")
        app.buttons["makeVideoFromNew"].tap()
        XCTAssertTrue(el(app, "composerField").waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["6 photos"].waitForExistence(timeout: 5))
    }

    /// A photo opens in a viewer whose main action is Make a video.
    func testViewerMakesAVideoFromOnePhoto() {
        let app = launch()
        XCTAssertTrue(el(app, "mediaTile").waitForExistence(timeout: 20))
        el(app, "mediaTile").tap()
        XCTAssertTrue(app.buttons["viewerMakeVideo"].waitForExistence(timeout: 10))
        shot(app, "16-viewer")
        app.buttons["viewerMakeVideo"].tap()
        XCTAssertTrue(el(app, "composerField").waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["1 photo"].waitForExistence(timeout: 5))
    }

    /// Create opened from the Media tab's round button with nothing ticked: the library is one tap away.
    func testCreateFromMediaOffersTheLibrary() {
        let app = launch()
        XCTAssertTrue(el(app, "mediaTile").waitForExistence(timeout: 20))
        app.buttons["newVideo"].tap()
        XCTAssertTrue(app.buttons["useLibrary"].waitForExistence(timeout: 15))
        shot(app, "17-create-from-media-use-library")
        app.buttons["createCancel"].tap()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10), "back on Media")
    }

    /// Create while the request is checked (debug stage `checking`): the whole form is locked and dimmed, the button says what is happening,
    /// one small Cancel gives the form back exactly as it was, and nothing can be sent twice.
    func testCreateIsLockedWhileTheRequestIsChecked() {
        let app = launch(env: ["VMK_DEBUG_TAB": "0", "VMK_DEBUG_CREATE": "checkingfast"])
        XCTAssertTrue(el(app, "checkingCancel").waitForExistence(timeout: 20), "one small Cancel while checking")
        XCTAssertFalse(el(app, "composerField").isEnabled, "the prompt is locked")
        XCTAssertFalse(app.buttons["sendButton"].isEnabled, "no second tap can send it again")
        XCTAssertFalse(app.buttons["moreOptions"].isEnabled, "options are locked")
        XCTAssertFalse(el(app, "micButton").isEnabled, "the mic is locked")
        XCTAssertFalse(el(app, "photoButton").isEnabled, "the photos are locked")
        XCTAssertTrue(app.staticTexts["Checking your request…"].exists, "one short honest line")
        shot(app, "20-create-locked-while-checking")
        app.buttons["checkingCancel"].tap()
        XCTAssertTrue(el(app, "composerField").waitForExistence(timeout: 5))
        XCTAssertTrue(el(app, "composerField").isEnabled, "the form is back")
        XCTAssertFalse(el(app, "checkingCancel").exists)
        XCTAssertTrue(app.buttons["sendButton"].isEnabled, "and it can be sent again")
        shot(app, "21-create-unlocked-after-cancel")
    }

    /// A check that takes longer shows where the questions will appear, with one Skip; the form behind stays locked.
    func testASlowCheckShowsTheQuestionsPlaceholderWithSkip() {
        let app = launch(env: ["VMK_DEBUG_TAB": "0", "VMK_DEBUG_CREATE": "checking"])
        XCTAssertTrue(el(app, "checkingText").waitForExistence(timeout: 20))
        XCTAssertTrue(app.buttons["Skip"].exists, "one way to stop waiting")
        shot(app, "22-create-slow-check")
    }

    /// Try again on a video that did not finish: the SAME card turns into the making card; no new row appears.
    func testTryAgainTurnsTheFailedCardIntoTheMakingCardInPlace() {
        let app = launch(env: ["VMK_DEBUG_TAB": "0", "VMK_DEBUG_FAKE_VIDEOS": "1"])
        let failed = el(app, "failedVideo")
        XCTAssertTrue(failed.waitForExistence(timeout: 20))
        let running = app.descendants(matching: .any).matching(identifier: "runningRow")
        let ready = app.descendants(matching: .any).matching(identifier: "videoRow")
        XCTAssertEqual(running.count, 1); XCTAssertEqual(ready.count, 1)
        shot(app, "30-failed-card")
        app.buttons["tryAgain"].tap()
        XCTAssertTrue(failed.waitForNonExistence(timeout: 5), "the failed card is gone")
        XCTAssertEqual(running.count, 2, "the same video is now being made")
        XCTAssertEqual(ready.count, 1, "nothing else changed")
        XCTAssertFalse(el(app, "pendingRow").exists, "no second row was added")
        XCTAssertTrue(app.staticTexts["Thailand highlights"].exists, "it is the same video")
        shot(app, "31-failed-card-is-making-again")
    }

    /// An older server has no retry route: a video is never asked for again without its attachments; the person is told instead.
    func testTryAgainOnAnOlderServerNeverRebuildsTheRequest() {
        let app = launch(env: ["VMK_DEBUG_TAB": "0", "VMK_DEBUG_FAKE_VIDEOS": "1", "VMK_DEBUG_FAKE_RETRY": "unsupported"])
        XCTAssertTrue(el(app, "failedVideo").waitForExistence(timeout: 20))
        app.buttons["tryAgain"].tap()
        XCTAssertTrue(app.alerts.element.waitForExistence(timeout: 5), "a message, not a photo-less copy")
        shot(app, "32-try-again-unavailable")
        app.alerts.element.buttons["OK"].tap()
        XCTAssertTrue(el(app, "failedVideo").exists, "the failed card is still there")
        XCTAssertFalse(el(app, "pendingRow").exists, "nothing new was sent")
        XCTAssertEqual(app.descendants(matching: .any).matching(identifier: "runningRow").count, 1)
    }

    /// A video that did not finish can be removed from its own menu.
    func testAFailedVideoCanBeRemoved() {
        let app = launch(env: ["VMK_DEBUG_TAB": "0", "VMK_DEBUG_FAKE_VIDEOS": "1"])
        XCTAssertTrue(el(app, "failedVideo").waitForExistence(timeout: 20))
        app.buttons["failedMore"].tap()
        shot(app, "33-failed-card-menu")
        app.buttons["Remove"].tap()
        XCTAssertTrue(el(app, "failedVideo").waitForNonExistence(timeout: 5))
        XCTAssertEqual(app.descendants(matching: .any).matching(identifier: "runningRow").count, 1)
    }

    /// Screenshots of the journey in one language and appearance (`TEST_RUNNER_VMK_SHOTS_LANG=es`, `TEST_RUNNER_VMK_SHOTS_MODE=dark`). Skipped without a folder to write to.
    func testJourneyShotsInThisLanguageAndAppearance() throws {
        guard ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] != nil else { throw XCTSkip("screenshots only") }
        let es = ProcessInfo.processInfo.environment["VMK_SHOTS_LANG"] == "es"
        var app = launch(spanish: es)
        XCTAssertTrue(el(app, "mediaTile").waitForExistence(timeout: 20))
        shot(app, "40-media-idle")
        app.buttons["selectButton"].tap()
        tapTiles(app, 3)
        shot(app, "41-three-selected")
        app.buttons["makeVideoFromSelection"].tap()
        XCTAssertTrue(el(app, "composerField").waitForExistence(timeout: 15))
        shot(app, "42-create-with-photos")
        app.terminate()
        app = launch(spanish: es, env: ["VMK_DEBUG_TAB": "0", "VMK_DEBUG_CREATE": "checkingfast"])
        XCTAssertTrue(el(app, "checkingCancel").waitForExistence(timeout: 20))
        shot(app, "43-create-locked")
        app.terminate()
        app = launch(spanish: es, env: ["VMK_DEBUG_TAB": "0", "VMK_DEBUG_FAKE_VIDEOS": "1"])
        XCTAssertTrue(el(app, "failedVideo").waitForExistence(timeout: 20))
        shot(app, "44-failed-card")
        app.buttons["tryAgain"].tap()
        XCTAssertTrue(el(app, "failedVideo").waitForNonExistence(timeout: 5))
        shot(app, "45-making-again")
    }

    /// Screenshots of the first states (kept for before/after comparisons).
    func testJourneyStates() throws {
        let app = launch()
        XCTAssertTrue(el(app, "mediaTile").waitForExistence(timeout: 20))
        shot(app, "01-media-idle")
        app.buttons["selectButton"].tap()
        shot(app, "02-select-mode-empty")
        tapTiles(app, 3)
        shot(app, "03-three-selected")
    }
}
