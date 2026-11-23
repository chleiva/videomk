import XCTest

/// Runs against the QA backend. Signed-in tests need `TEST_RUNNER_VMK_DEBUG_ID_TOKEN` (and `_REFRESH_TOKEN`) in the environment of
/// the `xcodebuild test` command; see mobile/ios/README.md. They are skipped without it.
final class VideoMKUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func launch(signedIn: Bool) throws -> XCUIApplication {
        let app = XCUIApplication()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"  // the simulator Keychain survives between launches
        if signedIn {
            let env = ProcessInfo.processInfo.environment
            guard let id = env["VMK_DEBUG_ID_TOKEN"], !id.isEmpty else { throw XCTSkip("no QA token in the environment") }
            app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = id
            app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = env["VMK_DEBUG_REFRESH_TOKEN"] ?? ""
        }
        app.launch()
        return app
    }

    func testSignedOutUserSeesSignIn() throws {
        let app = try launch(signedIn: false)
        XCTAssertTrue(app.buttons["signInButton"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["videomk"].exists)
    }

    func testCreateVideoShowsProgressThenPlays() throws {
        let app = try launch(signedIn: true)
        XCTAssertTrue(app.buttons["newVideoButton"].waitForExistence(timeout: 15), "library did not open")

        app.buttons["newVideoButton"].tap()
        let field = app.textViews["briefField"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        let create = app.buttons["createButton"]
        XCTAssertFalse(create.isEnabled, "an empty brief must not be submittable")
        field.tap()
        field.typeText("Explain how rainbows form, in simple terms.")
        XCTAssertTrue(create.isEnabled)
        create.tap()

        // After creating, the app opens the new video, which shows stages while it is made.
        XCTAssertTrue(app.otherElements["progressCard"].waitForExistence(timeout: 30) || app.staticTexts["Making your video"].waitForExistence(timeout: 30),
                      "progress screen did not appear")
        // Real generation on QA takes about 1.5 minutes.
        XCTAssertTrue(app.otherElements["player"].waitForExistence(timeout: 300), "the finished video did not appear")
        XCTAssertTrue(app.buttons["Share"].waitForExistence(timeout: 10))
    }

    /// Saves screenshots for visual review when `TEST_RUNNER_VMK_SHOTS_DIR` is set; always asserts the screens exist.
    func testScreensRender() throws {
        let dir = ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"]
        func shot(_ app: XCUIApplication, _ name: String) {
            guard let dir else { return }
            try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
        }
        let out = try launch(signedIn: false)
        XCTAssertTrue(out.buttons["signInButton"].waitForExistence(timeout: 10))
        shot(out, "1-signin")
        out.terminate()

        let app = try launch(signedIn: true)
        XCTAssertTrue(app.buttons["newVideoButton"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.cells.firstMatch.waitForExistence(timeout: 15))
        shot(app, "2-library")
        app.cells.firstMatch.tap()
        XCTAssertTrue(app.otherElements["player"].waitForExistence(timeout: 20))
        sleep(3); shot(app, "3-player")
        app.navigationBars.buttons.firstMatch.tap()
        app.buttons["newVideoButton"].tap()
        XCTAssertTrue(app.textViews["briefField"].waitForExistence(timeout: 5))
        shot(app, "4-create-empty")
        app.textViews["briefField"].typeText("A visual tour of the landmarks of Rome")
        shot(app, "5-create-filled")
        app.buttons["Cancel"].tap()
        app.buttons["settingsButton"].tap()
        XCTAssertTrue(app.buttons["signOutButton"].waitForExistence(timeout: 5))
        shot(app, "6-settings")
    }
}
