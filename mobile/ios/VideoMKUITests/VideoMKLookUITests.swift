import XCTest

/// The Look picker and the cast (docs/CREATE_API.md, "Video look (chosen and enforced)") on the in-app fake server (debug builds only, no network, no account).
/// The fake lists the picker only with `VMK_DEBUG_LOOKS`; the tiles and faces are the backend's own answer, saved in `Fixtures/looks_<lang>.json`.
/// Screenshots: `TEST_RUNNER_VMK_SHOTS_DIR` (+ `TEST_RUNNER_VMK_SHOTS_MODE=dark|large|es`), written as `look-<name>.png` by `testCaptures`.
final class VideoMKLookUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private var mode: String { ProcessInfo.processInfo.environment["VMK_SHOTS_MODE"] ?? "" }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func fixture(_ lang: String) -> String { URL(fileURLWithPath: #filePath).deletingLastPathComponent().appendingPathComponent("Fixtures/looks_\(lang).json").path }

    /// `looks`: what the fake server lists ("1", "locked", "soon"…); nil is a server from before the picker.
    private func launch(spanish: Bool = false, large: Bool = false, dark: Bool = false, looks: String? = "1", forget: Bool = true, _ env: [String: String] = [:]) -> XCUIApplication {
        let app = spanish ? XCUIApplication.spanish() : XCUIApplication.english()
        if dark { app.launchArguments += ["-AppleInterfaceStyle", "Dark"] }
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        app.launchEnvironment["VMK_DEBUG_BALANCE"] = "12"
        app.launchEnvironment["VMK_DEBUG_CREATE"] = "filled"
        if forget { app.launchEnvironment["VMK_DEBUG_FORGET_CREATE"] = "1" }
        if let looks { app.launchEnvironment["VMK_DEBUG_LOOKS"] = looks; app.launchEnvironment["VMK_DEBUG_LOOKS_FILE"] = fixture(spanish ? "es" : "en") }
        for (k, v) in env { app.launchEnvironment[k] = v.isEmpty ? nil : v }       // "" removes a default (VMK_DEBUG_CREATE: stay on the Videos tab)
        app.launch()
        return app
    }

    private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }

    private func openSheet(_ app: XCUIApplication) {
        XCTAssertTrue(el(app, "lookPill").waitForExistence(timeout: 20), "the Look pill")
        el(app, "lookPill").tap()
        XCTAssertTrue(el(app, "lookTile-auto").waitForExistence(timeout: 5), "the sheet of tiles")
    }

    private func shot(_ app: XCUIApplication, _ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] else { return }
        sleep(1)
        try? app.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("look-\(name).png"))
    }

    // MARK: the main paths

    /// Pill, tile: two taps. The sheet steps aside by itself and the pill says the choice.
    func testOneTapChoosesALookAndThePillSaysIt() {
        let app = launch()
        XCTAssertTrue(el(app, "lookPill").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto", "Auto is the default")
        openSheet(app)
        for (id, label) in [("auto", "Auto"), ("real", "Real"), ("whiteboard", "Whiteboard"), ("cartoon", "Cartoon")] { XCTAssertEqual(el(app, "lookTile-\(id)").label, label) }
        XCTAssertTrue(el(app, "lookTile-auto").isSelected, "Auto is ticked")
        XCTAssertEqual(el(app, "lookTile-auto").value as? String, "We pick one look that suits your topic.", "the server's own line says VideoMK chooses")
        XCTAssertFalse(el(app, "cast-auto").exists, "no cast until Cartoon is chosen")
        el(app, "lookTile-whiteboard").tap()
        XCTAssertTrue(el(app, "lookTile-whiteboard").waitForNonExistence(timeout: 5), "one tap is the whole job: the sheet closes by itself")
        XCTAssertEqual(el(app, "lookPill").value as? String, "Whiteboard")
        openSheet(app)
        XCTAssertTrue(el(app, "lookTile-whiteboard").isSelected && !el(app, "lookTile-auto").isSelected)
        el(app, "lookTile-auto").tap()
        XCTAssertTrue(el(app, "lookTile-auto").waitForNonExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto")
    }

    /// Cartoon keeps the sheet open for its cast: Auto, then up to three faces; two or three talk; one switch for the board.
    func testCartoonCastUpToThreeAndTheBoardSwitch() {
        let app = launch()
        openSheet(app)
        el(app, "lookTile-cartoon").tap()
        XCTAssertTrue(el(app, "cast-auto").waitForExistence(timeout: 5), "the cast is in the same sheet")
        XCTAssertTrue(el(app, "lookTile-cartoon").isSelected && el(app, "cast-auto").isSelected, "Cartoon with Auto cast: nothing more to do")
        XCTAssertEqual(el(app, "castLine").label, "We pick characters that suit the topic.")
        for id in ["ines", "david", "priya", "mateo", "fox", "owl", "bear", "cat", "parrot", "turtle"] { XCTAssertTrue(el(app, "cast-\(id)").exists, "\(id) is on screen without scrolling to another page") }
        XCTAssertEqual(el(app, "cast-owl").label, "Hugo")
        XCTAssertGreaterThanOrEqual(el(app, "cast-fox").frame.width, 44); XCTAssertGreaterThanOrEqual(el(app, "cast-fox").frame.height, 44)
        el(app, "cast-fox").tap()
        XCTAssertTrue(el(app, "cast-fox").isSelected && !el(app, "cast-auto").isSelected)
        XCTAssertEqual(el(app, "castLine").label, "Fox · Guide for children · For children")
        el(app, "cast-bear").tap()
        XCTAssertEqual(el(app, "castLine").label, "Pick 2 or 3 and they talk it through together.", "the server's line: they talk to each other")
        el(app, "cast-cat").tap()
        el(app, "cast-owl").tap()
        XCTAssertFalse(el(app, "cast-owl").isSelected, "a fourth is refused")
        XCTAssertEqual(el(app, "castLine").label, "Choose up to 3.")
        let board = app.switches["extra-board"]
        XCTAssertTrue(board.exists, "the one extra the server lists")
        XCTAssertEqual(board.label, "Hand-drawn board")
        board.switches.firstMatch.exists ? board.switches.firstMatch.tap() : board.tap()
        XCTAssertEqual(board.value as? String, "1")
        app.buttons["lookDone"].tap()
        XCTAssertTrue(el(app, "lookTile-cartoon").waitForNonExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookPill").label, "Look")
        let spoken = el(app, "lookPill").value as? String ?? ""
        XCTAssertTrue(spoken.hasPrefix("Cartoon, Fox, Bruno") && spoken.hasSuffix("Mika, Hand-drawn board"), "VoiceOver hears the whole choice: \(spoken)")
        XCTAssertTrue(app.staticTexts["Cartoon · Fox + 2"].exists, "the pill is compact: no name is cut")
        // back to Auto in the cast
        el(app, "lookPill").tap()
        XCTAssertTrue(el(app, "cast-auto").waitForExistence(timeout: 5))
        el(app, "cast-auto").tap()
        XCTAssertTrue(el(app, "cast-auto").isSelected && !el(app, "cast-fox").isSelected)
        el(app, "cast-fox").tap(); el(app, "cast-bear").tap()
        app.buttons["lookDone"].tap()
        XCTAssertTrue(app.staticTexts["Cartoon · Fox + Bruno"].waitForExistence(timeout: 5))
    }

    /// The choice is sent with the video, the Making screen says what the server adapted, and the next Create remembers the look.
    func testTheChoiceIsSentRememberedAndTheNoteShowsOnMaking() {
        var app = launch(["VMK_DEBUG_DEFAULT_MINUTES": "0.25", "VMK_DEBUG_MAKING": "tiles"])
        openSheet(app)
        el(app, "lookTile-cartoon").tap()
        XCTAssertTrue(el(app, "cast-fox").waitForExistence(timeout: 5))
        el(app, "cast-fox").tap(); el(app, "cast-bear").tap()
        XCTAssertTrue(el(app, "lookLengthLine").waitForExistence(timeout: 5), "the length was moved, and the sheet says so")
        XCTAssertEqual(el(app, "lookLengthLine").label, "Length is now 30 s: a conversation needs 20 s.")
        app.buttons["lookDone"].tap()
        XCTAssertTrue(el(app, "lengthPill").waitForExistence(timeout: 5))
        XCTAssertEqual(el(app, "lengthPill").value as? String, "30 s")
        // shortened again by hand: Create only offers the way back
        el(app, "lengthPill").tap(); el(app, "length-15s").tap()
        XCTAssertTrue(el(app, "lookLengthHint").waitForExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookLengthHint").label, "A conversation needs 20 s.")
        app.buttons["sendButton"].tap()
        XCTAssertTrue(el(app, "runningRow").waitForExistence(timeout: 30), "the video is being made")
        el(app, "runningRow").tap()
        XCTAssertTrue(el(app, "lookNote").waitForExistence(timeout: 10), "the server's sentence about the adapted look, on Making")
        XCTAssertEqual(el(app, "lookNote").label, "In a video this short one character presents; a conversation needs at least 20 seconds.")
        app.terminate()
        app = launch(forget: false, ["VMK_DEBUG_CREATE": "empty"])
        XCTAssertTrue(el(app, "lookPill").waitForExistence(timeout: 20))
        XCTAssertTrue(app.staticTexts["Cartoon · Fox + Bruno"].waitForExistence(timeout: 5), "the last look is remembered")
        app.terminate()
        app = launch(looks: nil, forget: false, ["VMK_DEBUG_CREATE": "empty"])
        XCTAssertTrue(el(app, "lookPill").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto", "a server without the picker: the remembered look is not used")
    }

    /// Photos are the pictures of the video: a drawn look goes back to Auto with one line, and only the looks made from photos are offered.
    func testPhotosResetTheLookAndHideTheDrawnOnes() {
        let app = launch(["VMK_DEBUG_CREATE": "photos", "VMK_DEBUG_LOOK": "cartoon:fox"])
        XCTAssertTrue(el(app, "lookNotice").waitForExistence(timeout: 20), "one line says the look changed")
        XCTAssertEqual(el(app, "lookNotice").label, "Look is now Auto: Cartoon is not made from your photos.")
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto")
        openSheet(app)
        XCTAssertTrue(el(app, "lookTile-real").exists)
        XCTAssertFalse(el(app, "lookTile-whiteboard").exists || el(app, "lookTile-cartoon").exists, "not offered with photos")
        XCTAssertEqual(el(app, "lookHiddenLine").label, "Not with your photos: Whiteboard and Cartoon.")
        el(app, "lookTile-real").tap()
        XCTAssertTrue(el(app, "lookTile-real").waitForNonExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Real")
        XCTAssertFalse(el(app, "lookNotice").exists, "the line goes once a look is chosen")
    }

    /// A look the plan does not include: shown with the plan's name, not selectable, no purchase button.
    func testALookOutsideThePlanIsLockedAndAnUnavailableOneIsHidden() {
        let app = launch(looks: "locked,soon")
        openSheet(app)
        XCTAssertFalse(el(app, "lookTile-whiteboard").exists, "a look this stage does not have is hidden")
        let cartoon = el(app, "lookTile-cartoon")
        XCTAssertTrue(cartoon.exists && !cartoon.isEnabled, "locked")
        XCTAssertEqual(cartoon.value as? String, "Pro plan")
        cartoon.tap()
        XCTAssertFalse(el(app, "cast-auto").exists || cartoon.isSelected, "it cannot be chosen")
        XCTAssertTrue(el(app, "lookTile-auto").isSelected)
        let words = app.buttons.allElementsBoundByIndex.map { $0.label }.joined(separator: " | ")
        for w in ["Upgrade", "Buy", "Subscribe"] { XCTAssertFalse(words.contains(w), "no purchase button: \(words)") }
    }

    /// A server from before the contract: the pill is the menu it always was, and nothing new is on screen.
    func testAnOlderServerKeepsTodaysMenu() {
        let app = launch(looks: nil)
        XCTAssertTrue(el(app, "lookPill").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto")
        el(app, "lookPill").tap()
        XCTAssertTrue(app.buttons["Midnight"].waitForExistence(timeout: 5), "the colour menu of before")
        XCTAssertFalse(el(app, "lookTile-auto").exists)
        app.buttons["Paper"].tap()
        XCTAssertEqual(el(app, "lookPill").value as? String, "Paper")
    }

    /// Spanish: the server's words, our lines, and the pill.
    func testSpanish() {
        let app = launch(spanish: true, ["VMK_DEBUG_DEFAULT_MINUTES": "0.25"])
        openSheet(app)
        XCTAssertEqual(el(app, "lookTile-auto").label, "Automático")
        XCTAssertEqual(el(app, "lookTile-cartoon").label, "Dibujos animados")
        el(app, "lookTile-cartoon").tap()
        XCTAssertTrue(el(app, "cast-fox").waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Personajes"].exists)
        el(app, "cast-priya").tap(); el(app, "cast-mateo").tap()
        XCTAssertEqual(el(app, "castLine").label, "Elige 2 o 3 y lo explican conversando.")
        XCTAssertEqual(el(app, "lookLengthLine").label, "La duración ahora es 30 s: una conversación necesita 20 s.")
        XCTAssertEqual(app.switches["extra-board"].label, "Pizarra dibujada")
        app.buttons["lookDone"].tap()
        XCTAssertTrue(app.staticTexts["Dibujos animados · Priya + Mateo"].waitForExistence(timeout: 5), "the longest pill is whole")
        XCTAssertEqual(el(app, "lookPill").label, "Estilo")
    }

    /// The largest text: every tile and face can be reached, names are whole, targets are at least 44 pt.
    func testLargestText() {
        let app = launch(large: true)
        openSheet(app)
        let cartoon = el(app, "lookTile-cartoon")
        for _ in 0..<4 where !cartoon.isHittable { app.swipeUp() }
        XCTAssertTrue(cartoon.isHittable)
        cartoon.tap()
        let turtle = el(app, "cast-turtle")
        XCTAssertTrue(turtle.waitForExistence(timeout: 5))
        for _ in 0..<6 where !turtle.isHittable { app.swipeUp() }
        XCTAssertTrue(turtle.isHittable, "the last face is reachable by scrolling")
        XCTAssertGreaterThanOrEqual(turtle.frame.height, 44)
        turtle.tap()
        XCTAssertTrue(turtle.isSelected)
        let board = app.switches["extra-board"]
        for _ in 0..<3 where !board.isHittable { app.swipeUp() }
        XCTAssertTrue(board.isHittable)
    }

    /// The applied look is kept in the video's Info.
    func testInfoKeepsTheAppliedLook() throws {
        guard let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"], !file.isEmpty else { throw XCTSkip("needs TEST_RUNNER_VMK_DEBUG_PLAYBACK_FILE (a local mp4)") }
        let app = launch(["VMK_DEBUG_CREATE": "", "VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v3", "VMK_DEBUG_PLAYBACK_FILE": file])
        XCTAssertTrue(app.buttons["infoButton"].waitForExistence(timeout: 30))
        app.buttons["infoButton"].tap()
        XCTAssertTrue(el(app, "infoLook").waitForExistence(timeout: 5))
        XCTAssertTrue(el(app, "infoLook").label.contains("Whiteboard · chosen for you") && el(app, "infoLook").label.contains("A step-by-step process is clearest drawn."), el(app, "infoLook").label)
        shot(app, "info")
    }

    // MARK: captures

    /// Every state, in the appearance `TEST_RUNNER_VMK_SHOTS_MODE` asks for (default light; `dark`, `large`, `es`). Skipped without a folder to write to.
    func testCaptures() throws {
        guard ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] != nil else { throw XCTSkip("set TEST_RUNNER_VMK_SHOTS_DIR") }
        let es = mode == "es", large = mode == "large", dark = mode == "dark"
        func start(looks: String? = "1", _ env: [String: String] = [:]) -> XCUIApplication { launch(spanish: es, large: large, dark: dark, looks: looks, env) }
        func settle(_ app: XCUIApplication, _ id: String) { XCTAssertTrue(el(app, id).waitForExistence(timeout: 20), id); sleep(1) }

        var app = start(); settle(app, "lookPill"); shot(app, "01-create-auto")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "02-sheet-auto"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "whiteboard"]); settle(app, "lookPill"); shot(app, "03-create-whiteboard")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "04-sheet-whiteboard"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "cartoon:sheet"]); settle(app, "cast-auto"); shot(app, "05-sheet-cartoon-auto")
        if large { app.swipeUp(); shot(app, "05b-sheet-cartoon-auto-scrolled"); app.swipeUp(); shot(app, "05c-sheet-cartoon-auto-end") }
        app.terminate()

        app = start(["VMK_DEBUG_LOOK": "cartoon:fox:sheet"]); settle(app, "cast-auto"); shot(app, "06-sheet-cartoon-one"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "cartoon:fox+bear:board:sheet"]); settle(app, "cast-auto"); shot(app, "07-sheet-cartoon-talk")
        if large { app.swipeUp(); app.swipeUp(); shot(app, "07b-sheet-cartoon-talk-end") }
        app.terminate()
        app = start(["VMK_DEBUG_LOOK": "cartoon:fox+bear:board"]); settle(app, "lookPill"); shot(app, "08-create-cartoon-talk"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "cartoon:fox+bear+cat:sheet"]); settle(app, "cast-auto")
        el(app, "cast-owl").tap(); shot(app, "09-sheet-cartoon-three-full"); app.terminate()
        app = start(["VMK_DEBUG_LOOK": "cartoon:priya+mateo+cat"]); settle(app, "lookPill"); shot(app, "10-create-cartoon-three"); app.terminate()

        app = start(["VMK_DEBUG_DEFAULT_MINUTES": "0.25", "VMK_DEBUG_LOOK": "cartoon:fox:sheet"]); settle(app, "cast-auto")
        let bear = el(app, "cast-bear"); for _ in 0..<4 where !bear.isHittable { app.swipeUp() }
        bear.tap(); sleep(1); if large { app.swipeUp(); app.swipeUp() }
        shot(app, "11-sheet-length-moved"); app.terminate()

        app = start(looks: "locked"); settle(app, "lookPill"); el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "12-sheet-plan-locked"); app.terminate()
        app = start(looks: "soon"); settle(app, "lookPill"); el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "13-sheet-one-hidden"); app.terminate()

        app = start(["VMK_DEBUG_CREATE": "photos", "VMK_DEBUG_LOOK": "cartoon:fox"]); settle(app, "lookNotice"); shot(app, "14-create-photos-reset")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "15-sheet-with-photos"); app.terminate()

        app = start(["VMK_DEBUG_CREATE": "shorts", "VMK_DEBUG_LOOK": "whiteboard:sheet"]); settle(app, "lookTile-auto"); shot(app, "16-sheet-shape-hint"); app.terminate()

        app = start(["VMK_DEBUG_CREATE": "", "VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v1", "VMK_DEBUG_LOOK_NOTE": "1", "VMK_DEBUG_IMAGE_DIR": ProcessInfo.processInfo.environment["VMK_DEBUG_IMAGE_DIR"] ?? ""])
        settle(app, "lookNote"); shot(app, "17-making-note"); app.terminate()

        app = start(looks: nil); settle(app, "lookPill"); el(app, "lookPill").tap(); sleep(1); shot(app, "18-older-server-menu"); app.terminate()

        if let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"], !file.isEmpty {
            app = start(["VMK_DEBUG_CREATE": "", "VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v3", "VMK_DEBUG_PLAYBACK_FILE": file])
            if app.buttons["infoButton"].waitForExistence(timeout: 30) { app.buttons["infoButton"].tap(); settle(app, "infoLook"); shot(app, "19-info-look") }
            app.terminate()
        }
    }
}
