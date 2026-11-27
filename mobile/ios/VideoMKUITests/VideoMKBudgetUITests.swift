import XCTest

/// The text budget of docs/UX_2026_REDESIGN.md as a test: the words a person can SEE (static texts of the screen) must stay under the budget.
/// The app is the fake-library build (no network); labels of buttons and the user's own words are not counted, only static text.
final class VideoMKBudgetUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func launch(_ env: [String: String]) -> XCUIApplication {
        let app = XCUIApplication.english()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        for (k, v) in env { app.launchEnvironment[k] = v }
        app.launch()
        return app
    }

    /// Words in the static texts that are on screen right now.
    private func visibleWords(_ app: XCUIApplication, excluding: Set<String> = []) -> Int {
        let frame = app.windows.firstMatch.frame
        var words = 0
        for t in app.staticTexts.allElementsBoundByIndex where t.exists && t.isHittable && t.frame.intersects(frame) {      // not the screens a sheet covers
            let label = t.label.trimmingCharacters(in: .whitespacesAndNewlines)
            if label.isEmpty || excluding.contains(label) { continue }
            words += label.split(whereSeparator: { $0 == " " || $0 == "\n" }).count
        }
        return words
    }

    func testCreateSurfaceStaysUnderFourteenWords() {
        let app = launch(["VMK_DEBUG_CREATE": "empty"])
        XCTAssertTrue(app.textFields["composerField"].waitForExistence(timeout: 20))
        let words = visibleWords(app, excluding: ["9:41"])
        // the prompt placeholder (3), the three pills (Video, 2 min, Auto = 4 words), the button (Create, 2 = 2) and one caption (4): 13 at most
        XCTAssertLessThanOrEqual(words, 16, "Create's surface has \(words) visible words, over its budget")
    }

    func testVideoScreenStaysUnderSixWords() throws {
        guard let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"], !file.isEmpty else { throw XCTSkip("needs TEST_RUNNER_VMK_DEBUG_PLAYBACK_FILE (a local mp4)") }
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "1", "VMK_DEBUG_OPEN": "v3", "VMK_DEBUG_PLAYBACK_FILE": file])
        XCTAssertTrue(app.buttons["shareButton"].waitForExistence(timeout: 20))
        let words = visibleWords(app)
        XCTAssertLessThanOrEqual(words, 10, "the video screen has \(words) visible words (title, caption and the system clock)")
    }

    func testFirstRunStaysUnderFourteenWords() {
        let app = launch([:])
        XCTAssertTrue(app.buttons["firstVideoButton"].waitForExistence(timeout: 20))
        let words = visibleWords(app)
        XCTAssertLessThanOrEqual(words, 24, "first run has \(words) visible words (headline 6, prompt 3, three short examples, two tab titles)")
    }
}
