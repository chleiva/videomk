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

    /// The Create surface after the redesign (docs/design_bar/CREATE_SCREEN_REDESIGN_BRIEF.md): a returning account sees the sentence, three pills and the tool row,
    /// nothing else: no examples, no helper line, no caption.
    func testCreateSurfaceStaysUnderTenWords() {
        let app = launch(["VMK_DEBUG_CREATE": "empty", "VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_BALANCE": "12"])
        XCTAssertTrue(app.textFields["composerField"].waitForExistence(timeout: 20))
        sleep(1)
        let words = visibleWords(app, excluding: ["9:41"])
        let seen = app.staticTexts.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.map { $0.label }
        // the three pills (Video, 2 min, Auto = 4 words), "Options", "Create": 6; the prompt placeholder (3) is the field's own
        XCTAssertLessThanOrEqual(words, 10, "Create's surface has \(words) visible words, over its budget: \(seen)")
        XCTAssertTrue(app.staticTexts["Describe your video"].exists == false, "the helper line is gone")
    }

    /// The first video of an account: the same surface plus two or three examples and ONE caption that teaches the price ("2 credits. You have 11.").
    func testFirstVideoCreateSurfaceStaysUnderTwentyTwoWords() {
        let app = launch(["VMK_DEBUG_CREATE": "empty", "VMK_DEBUG_BALANCE": "11"])
        XCTAssertTrue(app.textFields["composerField"].waitForExistence(timeout: 20))
        sleep(1)
        let chips = app.buttons.matching(identifier: "createExample").allElementsBoundByIndex.map { $0.label }
        XCTAssertTrue((2...3).contains(chips.count), "two or three examples: \(chips)")
        let words = visibleWords(app, excluding: ["9:41"])
        let seen = app.staticTexts.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.map { $0.label }
        XCTAssertLessThanOrEqual(words, 22, "the first-video surface has \(words) visible words: \(seen)")
    }

    func testVideoScreenStaysUnderSixWords() throws {
        guard let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"], !file.isEmpty else { throw XCTSkip("needs TEST_RUNNER_VMK_DEBUG_PLAYBACK_FILE (a local mp4)") }
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "1", "VMK_DEBUG_OPEN": "v3", "VMK_DEBUG_PLAYBACK_FILE": file])
        XCTAssertTrue(app.buttons["shareButton"].waitForExistence(timeout: 20))
        let seen = app.staticTexts.allElementsBoundByIndex.filter { $0.exists && $0.isHittable }.map { $0.label }
        // the title is the person's own words; the "Make another" chips are suggestions (as the examples on Create are), counted apart
        let chips = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "remix-")).allElementsBoundByIndex.map { $0.label }
        XCTAssertLessThanOrEqual(chips.count, 3, "at most three suggestions")
        let words = visibleWords(app, excluding: Set(chips + [app.staticTexts["videoTitle"].label]))
        // design bar rule 4: the video screen has 8 words (the caption "1:20 · 1080p", Share, "Make another")
        XCTAssertLessThanOrEqual(words, 8, "the video screen has \(words) visible words: \(seen)")
    }

    func testFirstRunStaysUnderFourteenWords() {
        let app = launch([:])
        XCTAssertTrue(app.buttons["firstVideoButton"].waitForExistence(timeout: 20))
        let words = visibleWords(app)
        XCTAssertLessThanOrEqual(words, 24, "first run has \(words) visible words (headline 6, prompt 3, three short examples, two tab titles)")
    }
}
