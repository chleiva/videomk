import XCTest

/// Feedback sheet and rating pre-prompt, fake library only (debug fixtures `VMK_DEBUG_SHEET=feedback|rating`). Large text, English and Spanish.
final class VideoMKFeedbackUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func launch(spanish: Bool, sheet: String) -> XCUIApplication {
        let app = spanish ? XCUIApplication.spanish() : XCUIApplication.english()
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXL"]
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        app.launchEnvironment["VMK_DEBUG_SHEET"] = sheet
        app.launch()
        return app
    }

    private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }

    func testFeedbackCanBeWrittenAndSentInBothLanguages() {
        for spanish in [false, true] {
            let app = launch(spanish: spanish, sheet: "feedback")
            XCTAssertTrue(el(app, "feedbackField").waitForExistence(timeout: 15), app.debugDescription)
            XCTAssertFalse(app.buttons["feedbackSend"].isEnabled, "too short to send")
            el(app, "feedbackField").tap(); el(app, "feedbackField").typeText("More music, please")
            el(app, "feedbackKind_idea").tap()
            XCTAssertTrue(app.buttons["feedbackSend"].isEnabled && app.buttons["feedbackSend"].isHittable, "Send stays reachable above the keyboard")
            app.buttons["feedbackSend"].tap()
            XCTAssertTrue(el(app, "feedbackThanks").waitForExistence(timeout: 10))
            XCTAssertTrue(app.buttons["feedbackDone"].exists)
            app.terminate()
        }
    }

    func testRatingQuestionLeadsToTheAskOrToFeedback() {
        var app = launch(spanish: false, sheet: "rating")
        XCTAssertTrue(app.buttons["ratingYes"].waitForExistence(timeout: 15))
        app.buttons["ratingYes"].tap()
        XCTAssertTrue(app.buttons["ratingRate"].waitForExistence(timeout: 5) && app.buttons["ratingLater"].exists && el(app, "ratingAlready").exists)
        app.terminate()
        app = launch(spanish: true, sheet: "rating")
        XCTAssertTrue(app.buttons["ratingNotReally"].waitForExistence(timeout: 15))
        app.buttons["ratingNotReally"].tap()
        XCTAssertTrue(el(app, "feedbackField").waitForExistence(timeout: 5))
    }
}
