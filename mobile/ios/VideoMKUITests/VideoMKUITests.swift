import XCTest

/// Runs against the QA backend. Signed-in tests need `TEST_RUNNER_VMK_DEBUG_ID_TOKEN` (and `_REFRESH_TOKEN`) in the environment of
/// the `xcodebuild test` command; see mobile/ios/README.md. They are skipped without it.
final class VideoMKUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func launch(signedIn: Bool, minutes: String? = nil, photoFiles: String? = nil) throws -> XCUIApplication {
        let app = XCUIApplication()
        if let photoFiles { app.launchEnvironment["VMK_DEBUG_PHOTO_FILES"] = photoFiles }
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"  // the simulator Keychain survives between launches
        if let minutes { app.launchEnvironment["VMK_DEBUG_DEFAULT_MINUTES"] = minutes }
        if signedIn {
            let env = ProcessInfo.processInfo.environment
            guard let id = env["VMK_DEBUG_ID_TOKEN"], !id.isEmpty else { throw XCTSkip("no QA token in the environment") }
            app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = id
            app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = env["VMK_DEBUG_REFRESH_TOKEN"] ?? ""
        }
        app.launch()
        return app
    }

    private func element(_ app: XCUIApplication, _ id: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: id).firstMatch
    }

    /// A finished (Ready) video: the newest row may be a declined or failed one, which has no player.
    private func readyRow(_ app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'videoRow' AND label CONTAINS 'Ready'")).firstMatch
    }

    private func shot(_ app: XCUIApplication, _ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] else { return }
        try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
    }

    func testSignedOutUserSeesSignIn() throws {
        let app = try launch(signedIn: false)
        XCTAssertTrue(app.buttons["signInButton"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["videomk"].exists)
    }

    /// The whole create flow happens on the home screen: a live row appears in the list, the composer is free again at once,
    /// other videos stay reachable, and the row turns into a finished video. Makes one real 1-minute video on QA.
    func testAskingForAVideoKeepsYouOnTheHomeScreen() throws {
        let app = try launch(signedIn: true, minutes: "1")
        let field = app.textFields["composerField"]
        XCTAssertTrue(field.waitForExistence(timeout: 20), "the composer should be on the home screen")
        XCTAssertTrue(app.buttons["micButton"].exists, "dictation button")
        XCTAssertTrue(app.buttons["optionsMenu"].exists)
        XCTAssertFalse(app.buttons["sendButton"].exists, "nothing to send yet")

        field.tap()
        field.typeText("Explain how rainbows form, in simple terms.")
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 5))
        shot(app, "10-composer-ready")
        app.buttons["sendButton"].tap()

        // Instantly a placeholder or live row, and we never left the list.
        let appeared = element(app, "pendingRow").waitForExistence(timeout: 10) || element(app, "runningRow").waitForExistence(timeout: 30)
        XCTAssertFalse(element(app, "failedRow").exists, "the request failed (daily limit? connection?)")
        XCTAssertTrue(appeared, "a row for the new video should appear")
        XCTAssertTrue(app.navigationBars["Videos"].exists, "still on the home screen")
        XCTAssertFalse(app.buttons["sendButton"].exists, "the composer is cleared and ready for another request")
        XCTAssertTrue(element(app, "runningRow").waitForExistence(timeout: 60))
        shot(app, "11-live-row")

        // Ask for a second video while the first is still being made: both are live in the same list.
        field.tap()
        field.typeText("Why is the sky blue? A short explanation.")
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 5))
        app.buttons["sendButton"].tap()
        func liveCount() -> Int {
            app.descendants(matching: .any).matching(identifier: "runningRow").count + app.descendants(matching: .any).matching(identifier: "pendingRow").count
        }
        let both = Date().addingTimeInterval(60)
        while liveCount() < 2 && Date() < both { sleep(1) }
        XCTAssertGreaterThanOrEqual(liveCount(), 2, "two videos should be in progress at once")
        XCTAssertTrue(app.navigationBars["Videos"].exists, "still on the home screen")
        shot(app, "11b-two-live-rows")

        // It finishes in place: no running or pending rows are left and the list still shows videos.
        let deadline = Date().addingTimeInterval(480)
        while (element(app, "runningRow").exists || element(app, "pendingRow").exists) && Date() < deadline { sleep(5) }
        XCTAssertFalse(element(app, "runningRow").exists || element(app, "pendingRow").exists, "the video did not finish in time")
        XCTAssertTrue(element(app, "videoRow").exists)
        shot(app, "12-finished")
    }

    /// Attach photos, say what the video should be about, send: the photos upload, the video is made around them, and it plays.
    /// Needs `TEST_RUNNER_VMK_DEBUG_PHOTO_FILES=/path/a.jpg:/path/b.jpg` (the system photo picker can't be driven from a test). Makes one real video on QA.
    func testAVideoFromYourPhotos() throws {
        guard let files = ProcessInfo.processInfo.environment["VMK_DEBUG_PHOTO_FILES"], !files.isEmpty else { throw XCTSkip("no photo files in the environment") }
        let count = files.split(separator: ":").count
        let app = try launch(signedIn: true, minutes: "1", photoFiles: files)
        let field = app.textFields["composerField"]
        XCTAssertTrue(field.waitForExistence(timeout: 20))
        XCTAssertTrue(app.buttons["photoButton"].exists, "the composer offers photos")
        let photos = app.descendants(matching: .any).matching(identifier: "attachedPhoto")
        let deadline = Date().addingTimeInterval(30)
        while photos.count < count && Date() < deadline { sleep(1) }
        XCTAssertEqual(photos.count, count, "the attached photos are shown")
        XCTAssertTrue(element(app, "photosNote").exists, "the privacy note is shown with the photos")
        field.tap()
        field.typeText("A relaxed day out with my family and our dog: the park, the beach, pizza and a hike.")
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 5))
        shot(app, "13-photos-attached")
        app.buttons["sendButton"].tap()

        XCTAssertTrue(element(app, "pendingRow").waitForExistence(timeout: 20) || element(app, "runningRow").waitForExistence(timeout: 60), "a row for the new video appears")
        XCTAssertFalse(element(app, "failedRow").exists, "the upload and the request succeeded")
        XCTAssertEqual(photos.count, 0, "the composer is cleared after sending")
        shot(app, "14-uploading")
        XCTAssertTrue(element(app, "runningRow").waitForExistence(timeout: 120), "the video is being made")
        let finish = Date().addingTimeInterval(420)
        while (element(app, "runningRow").exists || element(app, "pendingRow").exists) && Date() < finish { sleep(5) }
        XCTAssertFalse(element(app, "failedRow").exists)
        XCTAssertTrue(readyRow(app).waitForExistence(timeout: 20))
        readyRow(app).tap()
        XCTAssertTrue(app.otherElements["player"].waitForExistence(timeout: 30), "the finished video plays")
        sleep(3); shot(app, "15-photo-video")
    }

    /// Saves screenshots for visual review when `TEST_RUNNER_VMK_SHOTS_DIR` is set; always asserts the screens exist.
    func testScreensRender() throws {
        let out = try launch(signedIn: false)
        XCTAssertTrue(out.buttons["signInButton"].waitForExistence(timeout: 10))
        shot(out, "1-signin")
        out.terminate()

        let app = try launch(signedIn: true)
        XCTAssertTrue(app.textFields["composerField"].waitForExistence(timeout: 20))
        XCTAssertTrue(readyRow(app).waitForExistence(timeout: 20))
        shot(app, "2-library")
        readyRow(app).tap()
        XCTAssertTrue(app.otherElements["player"].waitForExistence(timeout: 20))
        sleep(3); shot(app, "3-player")
        let credits = app.buttons["Description and photo credits"]
        if credits.waitForExistence(timeout: 10) { credits.tap(); sleep(1); shot(app, "3b-credits") }
        app.navigationBars.buttons.firstMatch.tap()
        let field = app.textFields["composerField"]
        field.tap()
        field.typeText("A visual tour of the landmarks of Rome")
        XCTAssertTrue(app.staticTexts["costLine"].waitForExistence(timeout: 5), "the composer shows what the video will cost")
        shot(app, "5-composer-filled")
        app.buttons["optionsMenu"].tap()
        sleep(1); shot(app, "5b-options")
        app.tap()   // dismiss the menu
        XCTAssertTrue(app.buttons["balanceChip"].exists, "the credit balance is always visible")
        app.buttons["balanceChip"].tap()
        XCTAssertTrue(app.navigationBars["Credits"].waitForExistence(timeout: 5))
        sleep(1); shot(app, "5c-credits")
        app.buttons["Done"].tap()
        app.buttons["settingsButton"].tap()
        XCTAssertTrue(app.buttons["signOutButton"].waitForExistence(timeout: 5))
        shot(app, "6-settings")
    }

    /// A video that costs more credits than the user has can't be sent, and the screen says why and what to do.
    func testNotEnoughCreditsBlocksSendingAndExplainsWhy() throws {
        let app = try launch(signedIn: true)
        let field = app.textFields["composerField"]
        XCTAssertTrue(field.waitForExistence(timeout: 20))
        XCTAssertTrue(app.buttons["balanceChip"].waitForExistence(timeout: 20))
        field.tap()
        field.typeText("A very long documentary about the history of Rome")
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 5), "affordable at the default length")
        app.buttons["optionsMenu"].tap()
        app.buttons["12 minutes"].tap()
        XCTAssertTrue(app.staticTexts["notEnoughCredits"].waitForExistence(timeout: 5), "12 credits is more than a test account has")
        XCTAssertFalse(app.buttons["sendButton"].exists)
        shot(app, "5d-not-enough-credits")
    }

    /// Edit a scene's narration, render a draft preview, then publish. Uses a real, editable video on QA (about 3 minutes).
    func testEditNarrationPreviewThenPublish() throws {
        let app = try launch(signedIn: true)
        XCTAssertTrue(readyRow(app).waitForExistence(timeout: 20))
        readyRow(app).tap()
        XCTAssertTrue(app.buttons["editButton"].waitForExistence(timeout: 20), "an editable, completed video should offer Edit")
        app.buttons["editButton"].tap()

        XCTAssertTrue(app.buttons["beatRow"].firstMatch.waitForExistence(timeout: 20), "the scene list did not load")
        XCTAssertFalse(app.buttons["previewButton"].isEnabled, "nothing changed yet")
        shot(app, "7-editor")

        app.buttons["beatRow"].firstMatch.tap()
        let field = app.textViews["narrationField"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: 0.97)).tap()
        field.typeText(" And that is the idea.")
        shot(app, "8-scene")
        app.buttons["Done"].tap()
        XCTAssertTrue(app.staticTexts["Edited"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["previewButton"].isEnabled)

        app.buttons["previewButton"].tap()
        XCTAssertTrue(app.otherElements["renderingView"].waitForExistence(timeout: 20) || app.staticTexts["Making your preview"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["doneTitle"].waitForExistence(timeout: 400), "the preview did not finish")
        XCTAssertEqual(app.staticTexts["doneTitle"].label, "Preview ready")
        shot(app, "9-preview-ready")
        app.buttons["doneButton"].tap()   // back to editing

        XCTAssertTrue(app.buttons["publishButton"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["publishButton"].isEnabled, "an approved preview can be published without further changes")
        app.buttons["publishButton"].tap()
        XCTAssertTrue(app.staticTexts["doneTitle"].waitForExistence(timeout: 600), "publishing did not finish")
        XCTAssertEqual(app.staticTexts["doneTitle"].label, "Published")
    }
}
