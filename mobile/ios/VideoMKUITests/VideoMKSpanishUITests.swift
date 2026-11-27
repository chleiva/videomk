import XCTest

extension XCUIApplication {
    /// The English UI tests pin the language so they pass on a phone or simulator set to anything else.
    static func english() -> XCUIApplication { localized("en", "en_US") }
    static func spanish() -> XCUIApplication { localized("es", "es_ES") }
    private static func localized(_ lang: String, _ locale: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments += ["-AppleLanguages", "(\(lang))", "-AppleLocale", locale, "-vmk_locale", "system"]      // an earlier test that switched the language in Settings must not leak into this launch
        return app
    }
}

/// The app in Spanish (`-AppleLanguages "(es)" -AppleLocale es_ES`): key labels, then screenshots of the main screens.
/// No backend: a made-up session and the in-app fake library (debug builds only).
/// Screenshots: set `TEST_RUNNER_VMK_SHOTS_DIR` (and `TEST_RUNNER_VMK_SHOTS_PREFIX`, `TEST_RUNNER_VMK_SHOTS_MODE=dark|large`).
final class VideoMKSpanishUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func session(_ env: [String: String] = [:], signedIn: Bool = true) -> XCUIApplication {
        let app = XCUIApplication.spanish()
        let mode = ProcessInfo.processInfo.environment["VMK_SHOTS_MODE"] ?? ""
        if mode == "dark" { app.launchArguments += ["-AppleInterfaceStyle", "Dark"] }
        if mode == "large" { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityL"] }
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        if signedIn {
            app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token()
            app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"
            app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        }
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

    func testSignInIsSpanish() {
        let app = session(["VMK_DEBUG_AUTH_APPLE": "1", "VMK_DEBUG_AUTH_GOOGLE": "1"], signedIn: false)
        _ = app.buttons["signInButton"].waitForExistence(timeout: 15)
        XCTAssertTrue(app.buttons["Continuar con Google"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Continuar con Apple"].exists)
        XCTAssertEqual(app.buttons["signInButton"].label, "Continuar con correo")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Nosotros creamos el video")).firstMatch.exists, "the sign-in tagline is the home headline")
    }

    func testCreateSettingsAndDeleteAccountAreSpanish() {
        let app = session()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.buttons["newVideo"].label, "Nuevo video")
        XCTAssertTrue(app.buttons["tabMedia"].exists && app.buttons["tabVideos"].exists)
        XCTAssertEqual(app.buttons["tabMedia"].label, "Biblioteca")
        app.buttons["newVideo"].tap()
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["sendButton"].label.contains("Crear"))
        XCTAssertEqual(el(app, "forPill").label, "Para", "the pills speak Spanish")
        app.buttons["createCancel"].tap()
        app.buttons["settingsButton"].tap()
        XCTAssertTrue(app.navigationBars["Ajustes"].waitForExistence(timeout: 5))
        for _ in 0..<5 where !app.buttons["deleteAccountButton"].exists { app.swipeUp() }
        XCTAssertEqual(app.buttons["deleteAccountButton"].label, "Eliminar cuenta")
        XCTAssertTrue(app.buttons["signOutButton"].exists)
        app.buttons["deleteAccountButton"].tap()
        XCTAssertTrue(app.navigationBars["Eliminar cuenta"].waitForExistence(timeout: 5))
        for _ in 0..<6 where !app.textFields["deleteConfirmField"].exists { app.swipeUp() }
        XCTAssertTrue(app.textFields["deleteConfirmField"].exists)
        XCTAssertEqual(app.textFields["deleteConfirmField"].placeholderValue, "ELIMINAR")
        XCTAssertFalse(app.buttons["deleteConfirmButton"].isEnabled)
        app.textFields["deleteConfirmField"].tap(); app.textFields["deleteConfirmField"].typeText("ELIMINAR")
        XCTAssertTrue(app.buttons["deleteConfirmButton"].isEnabled, "the Spanish confirmation word works")
    }

    /// The in-app language row switches the whole app at once, without a restart.
    func testLanguageRowSwitchesWithoutRestart() {
        let app = session(["VMK_DEBUG_SHEET": "settings"])
        XCTAssertTrue(app.navigationBars["Ajustes"].waitForExistence(timeout: 15))
        for _ in 0..<3 where !app.buttons["languagePicker"].exists { app.swipeUp() }      // the list grew taller with the new Support and Terms rows
        app.buttons["languagePicker"].tap()
        app.buttons["English"].tap()
        XCTAssertTrue(app.navigationBars["Settings"].waitForExistence(timeout: 5))
    }

    /// Screenshots of the main screens (no assertions beyond "it renders").
    func testScreenshots() {
        var app = session(); XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 15)); shot(app, "01-home")
        XCTAssertTrue(app.buttons["tabMedia"].waitForExistence(timeout: 10)); app.buttons["tabMedia"].tap(); sleep(2); shot(app, "02-media"); app.terminate()
        app = session(["VMK_DEBUG_SIGNED_OUT": "1"], signedIn: false); _ = app.buttons["signInButton"].waitForExistence(timeout: 15); shot(app, "03-signin"); app.terminate()
        for s in ["empty", "filled", "photos", "options", "notaffordable", "q1", "summary", "checking", "unsupported", "paused"] {
            app = session(["VMK_DEBUG_CREATE": s]); _ = el(app, "composerField").waitForExistence(timeout: 15); sleep(1); shot(app, "10-create-\(s)"); app.terminate()
        }
        app = session(["VMK_DEBUG_SHEET": "settings"]); _ = app.navigationBars["Ajustes"].waitForExistence(timeout: 15); shot(app, "20-settings"); app.swipeUp(); shot(app, "21-settings-bottom"); app.terminate()
        app = session(["VMK_DEBUG_SHEET": "delete"]); _ = app.navigationBars["Eliminar cuenta"].waitForExistence(timeout: 15); shot(app, "22-delete"); for _ in 0..<3 { app.swipeUp() }; shot(app, "23-delete-bottom"); app.terminate()
        app = session(["VMK_DEBUG_DELETE_DONE": "available"]); _ = el(app, "deletedTitle").waitForExistence(timeout: 15); shot(app, "24-deleted"); app.terminate()
    }
}
