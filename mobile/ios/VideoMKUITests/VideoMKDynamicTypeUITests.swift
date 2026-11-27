import XCTest

/// Layout at accessibility-extra-large text (AX3, the largest size the app is designed for), English and Spanish, on whatever device runs the test
/// (run it on iPhone 17 Pro and on the SE simulator). No backend: a made-up session and the in-app fake library (debug builds only).
final class VideoMKDynamicTypeUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func launch(spanish: Bool, signedIn: Bool, env: [String: String] = [:], largeText: Bool = true) -> XCUIApplication {
        let app = spanish ? XCUIApplication.spanish() : XCUIApplication.english()
        if largeText { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXL"] }
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        if signedIn {
            app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        } else {
            app.launchEnvironment["VMK_DEBUG_AUTH_APPLE"] = "1"; app.launchEnvironment["VMK_DEBUG_AUTH_GOOGLE"] = "1"
        }
        for (k, v) in env { app.launchEnvironment[k] = v }
        app.launch()
        return app
    }

    private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }

    private func assertSignInFits(_ app: XCUIApplication, google: String) {
        let screen = app.windows.firstMatch.frame
        let g = app.buttons[google]
        XCTAssertTrue(g.waitForExistence(timeout: 15))
        for b in [g, app.buttons["signInButton"]] {
            if !b.isHittable { app.swipeUp() }       // the page scrolls: reaching a button is the requirement, not seeing all of them at once
            XCTAssertTrue(b.exists)
            XCTAssertGreaterThanOrEqual(b.frame.minX, 0, "\(b.label) is not clipped on the left")
            XCTAssertLessThanOrEqual(b.frame.maxX, screen.maxX + 0.5, "\(b.label) is not clipped on the right")
            XCTAssertGreaterThanOrEqual(b.frame.height, 44, "\(b.label) keeps a 44 pt target")
        }
    }

    func testSignInFitsAtAccessibilityXLEnglish() { assertSignInFits(launch(spanish: false, signedIn: false), google: "Continue with Google") }
    func testSignInFitsAtAccessibilityXLSpanish() { assertSignInFits(launch(spanish: true, signedIn: false), google: "Continuar con Google") }

    func testHomeListIsUsableAtAccessibilityXLInBothLanguages() {
        for spanish in [false, true] {
            let app = launch(spanish: spanish, signedIn: true, env: ["VMK_DEBUG_FAKE_VIDEOS": "1"])
            XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 15))
            XCTAssertGreaterThanOrEqual(app.buttons["newVideo"].frame.height, 44)
            XCTAssertLessThanOrEqual(app.buttons["newVideo"].frame.maxX, app.windows.firstMatch.frame.maxX + 0.5)
            XCTAssertTrue(el(app, "runningRow").exists, "the Making card is on the list")
            for _ in 0..<3 where !el(app, "tryAgain").isHittable { app.swipeUp() }
            XCTAssertTrue(el(app, "tryAgain").exists, "the failed row keeps its action")
            app.terminate()
        }
    }

    func testFirstRunOffersAPromptAndExamples() {
        let app = launch(spanish: false, signedIn: true, largeText: false)
        XCTAssertTrue(el(app, "firstVideoButton").waitForExistence(timeout: 15), "an empty list shows the prompt field")
        XCTAssertTrue(el(app, "example").exists, "and example chips")
        el(app, "example").tap()
        XCTAssertTrue(el(app, "composerField").waitForExistence(timeout: 10))
        XCTAssertFalse((el(app, "composerField").value as? String ?? "").isEmpty, "an example fills the prompt")
        XCTAssertTrue(el(app, "lengthPill").waitForExistence(timeout: 5), "the length is a pill")
    }

    func testCreditsInfoOpensFromTheCreditsSheet() {
        let app = launch(spanish: false, signedIn: true, env: ["VMK_DEBUG_SHEET": "wallet"], largeText: false)
        XCTAssertTrue(el(app, "walletInfo").waitForExistence(timeout: 15))
        el(app, "walletInfo").tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS '1 min = 1 credit'")).firstMatch.waitForExistence(timeout: 5))
    }
}
