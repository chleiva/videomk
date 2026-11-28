import XCTest

/// The Look picker and the cast (docs/CREATE_API.md, "Video look (chosen and enforced)") on the in-app fake server (debug builds only, no network, no account).
/// The fake lists the picker only with `VMK_DEBUG_LOOKS`; the tiles and faces are the backend's own answer, saved in `Fixtures/looks_<lang>.json`.
/// Screenshots: `TEST_RUNNER_VMK_SHOTS_DIR` (+ `TEST_RUNNER_VMK_SHOTS_MODE=dark|large|es|small`), written as `look-<name>.png` by `testCaptures`.
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

    /// The Characters pill of a look with a cast, and its sheet.
    private func openCast(_ app: XCUIApplication) {
        XCTAssertTrue(el(app, "castPill").waitForExistence(timeout: 20), "the Characters pill")
        el(app, "castPill").tap()
        XCTAssertTrue(el(app, "cast-fox").waitForExistence(timeout: 5), "the sheet of faces")
    }

    private func closeCast(_ app: XCUIApplication) {
        app.buttons["castDone"].tap()
        XCTAssertTrue(el(app, "cast-fox").waitForNonExistence(timeout: 5))
    }

    /// How many rows the pills take (they wrap when they do not fit).
    private func pillRows(_ app: XCUIApplication) -> Int {
        Set(["forPill", "lengthPill", "lookPill", "castPill"].map { el(app, $0) }.filter { $0.exists }.map { Int(($0.frame.midY / 4).rounded()) }).count
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
        XCTAssertFalse(el(app, "castPill").exists, "no Characters pill until a look has a cast")
        openSheet(app)
        for (id, label) in [("auto", "Auto"), ("real", "Real"), ("whiteboard", "Whiteboard"), ("cartoon", "Cartoon")] { XCTAssertEqual(el(app, "lookTile-\(id)").label, label) }
        XCTAssertTrue(el(app, "lookTile-auto").isSelected, "Auto is chosen")
        XCTAssertEqual(el(app, "lookTile-auto").value as? String, "Picked for your topic", "the server's own line says VideoMK chooses")
        let top = el(app, "sheetTitle").frame.minY
        el(app, "lookTile-whiteboard").tap()
        XCTAssertTrue(el(app, "lookTile-whiteboard").waitForNonExistence(timeout: 5), "one tap is the whole job: the sheet closes by itself")
        XCTAssertEqual(el(app, "lookPill").value as? String, "Whiteboard")
        openSheet(app)
        XCTAssertTrue(el(app, "lookTile-whiteboard").isSelected && !el(app, "lookTile-auto").isSelected)
        el(app, "lookTile-cartoon").tap()
        XCTAssertTrue(el(app, "lookTile-cartoon").waitForNonExistence(timeout: 5), "the same tap behaves the same for every look: Cartoon closes too")
        XCTAssertEqual(el(app, "lookPill").value as? String, "Cartoon")
        XCTAssertTrue(el(app, "castPill").waitForExistence(timeout: 5), "a look with a cast: the Characters pill is on Create")
        openSheet(app)
        XCTAssertFalse(el(app, "cast-fox").exists, "the Look sheet holds the four tiles and nothing else")
        XCTAssertEqual(el(app, "sheetTitle").frame.minY, top, accuracy: 1, "and is always the same height")
        el(app, "lookTile-auto").tap()
        XCTAssertTrue(el(app, "lookTile-auto").waitForNonExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto")
        XCTAssertFalse(el(app, "castPill").exists)
    }

    /// The Characters sheet: none chosen is Auto, then up to three faces; one line says what the choice means; one switch for the board.
    func testCartoonCastUpToThreeAndTheBoardSwitch() {
        let app = launch(["VMK_DEBUG_LOOK": "cartoon"])
        XCTAssertTrue(el(app, "castPill").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "castPill").label, "Characters"); XCTAssertEqual(el(app, "castPill").value as? String, "Auto")
        openCast(app)
        XCTAssertFalse(el(app, "cast-auto").exists, "no Auto face: none chosen is Auto")
        XCTAssertEqual(el(app, "castLine").label, "We pick for you. Or choose up to 3.")
        let ids = ["ines", "david", "priya", "mateo", "fox", "owl", "bear", "cat", "parrot", "turtle"]
        for id in ids { XCTAssertTrue(el(app, "cast-\(id)").isHittable, "\(id) is on screen without scrolling") }
        XCTAssertEqual(el(app, "cast-fox").frame.minY, el(app, "cast-ines").frame.minY, accuracy: 1, "five across: the fifth face is in the first row")
        XCTAssertEqual(el(app, "cast-owl").frame.minX, el(app, "cast-ines").frame.minX, accuracy: 1, "two even rows")
        XCTAssertEqual(el(app, "cast-owl").label, "Otto")
        XCTAssertGreaterThanOrEqual(el(app, "cast-fox").frame.width, 44); XCTAssertGreaterThanOrEqual(el(app, "cast-fox").frame.height, 44)
        let size = el(app, "cast-fox").frame.size
        el(app, "cast-fox").tap()
        XCTAssertTrue(el(app, "cast-fox").isSelected)
        XCTAssertEqual(el(app, "cast-fox").frame.size, size, "a chosen face is the size it was")
        XCTAssertEqual(el(app, "castLine").label, "Fox presents.")
        el(app, "cast-bear").tap()
        XCTAssertEqual(el(app, "castLine").label, "Fox and Bruno talk it through.")
        el(app, "cast-cat").tap()
        XCTAssertEqual(el(app, "castLine").label, "Fox, Bruno, and Mika talk it through.")
        XCTAssertFalse(el(app, "cast-owl").isEnabled, "at the limit the others are dimmed and do nothing")
        XCTAssertTrue(el(app, "cast-fox").isEnabled && el(app, "cast-cat").isEnabled, "the chosen ones can be let go")
        let board = app.switches["extra-board"]
        XCTAssertTrue(board.exists, "the one extra the server lists")
        XCTAssertEqual(board.label, "Characters explain at a board")
        board.switches.firstMatch.exists ? board.switches.firstMatch.tap() : board.tap()
        XCTAssertEqual(board.value as? String, "1")
        XCTAssertTrue(el(app, "cast-fox").exists, "the sheet stays until it is closed")
        closeCast(app)
        XCTAssertEqual(el(app, "lookPill").label, "Look"); XCTAssertEqual(el(app, "lookPill").value as? String, "Cartoon")
        XCTAssertEqual(el(app, "castPill").value as? String, "Fox, Bruno, and Mika, Characters explain at a board", "VoiceOver hears the whole choice")
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Fox'")).firstMatch.exists, "no names in a pill: the cast is faces")
        for id in ["lookPill", "castPill"] { XCTAssertLessThanOrEqual(el(app, id).frame.height, 46, "\(id) is one line") }
        XCTAssertLessThanOrEqual(pillRows(app), 2)
        // letting them go: none chosen is Auto again
        openCast(app)
        el(app, "cast-cat").tap()
        XCTAssertTrue(el(app, "cast-owl").isEnabled, "one let go: the others wake")
        el(app, "cast-fox").tap(); el(app, "cast-bear").tap()
        XCTAssertEqual(el(app, "castLine").label, "We pick for you. Or choose up to 3.")
        closeCast(app)
        XCTAssertEqual(el(app, "castPill").value as? String, "Auto, Characters explain at a board")
    }

    /// The choice is sent with the video, the Making screen says what the server adapted, and the next Create remembers the look.
    func testTheChoiceIsSentRememberedAndTheNoteShowsOnMaking() {
        var app = launch(["VMK_DEBUG_DEFAULT_MINUTES": "0.25", "VMK_DEBUG_MAKING": "tiles"])
        openSheet(app)
        el(app, "lookTile-cartoon").tap()
        openCast(app)
        el(app, "cast-fox").tap(); el(app, "cast-bear").tap()
        XCTAssertEqual(el(app, "castLine").label, "Length changed to 30 s. A conversation needs 20 s or more.", "the length was moved, and the one line says so")
        closeCast(app)
        XCTAssertEqual(el(app, "lengthPill").value as? String, "30 s")
        // shortened again by hand: Create only offers the way back
        el(app, "lengthPill").tap(); el(app, "length-15s").tap()
        XCTAssertTrue(el(app, "lookLengthHint").waitForExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookLengthHint").label, "A conversation needs 20 s.")
        app.buttons["sendButton"].tap()
        XCTAssertTrue(el(app, "runningRow").waitForExistence(timeout: 30), "the video is being made")
        el(app, "runningRow").tap()
        XCTAssertTrue(el(app, "lookNote").waitForExistence(timeout: 10), "the server's sentence about the adapted look, on Making")
        XCTAssertEqual(el(app, "lookNote").label, "One character presents. A conversation needs 20 s or more.")
        app.terminate()
        app = launch(forget: false, ["VMK_DEBUG_CREATE": "empty"])
        XCTAssertTrue(el(app, "castPill").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Cartoon", "the last look is remembered")
        XCTAssertEqual(el(app, "castPill").value as? String, "Fox and Bruno", "with its characters")
        app.terminate()
        app = launch(looks: nil, forget: false, ["VMK_DEBUG_CREATE": "empty"])
        XCTAssertTrue(el(app, "lookPill").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto", "a server without the picker: the remembered look is not used")
        XCTAssertFalse(el(app, "castPill").exists)
    }

    /// A look that needs a longer video moves the length when it is chosen: the sheet still closes, and Create says what was done right above the pills.
    func testALookThatNeedsALongerVideoSaysSoOnCreate() {
        let app = launch(looks: "short", ["VMK_DEBUG_DEFAULT_MINUTES": "0.25"])
        openSheet(app)
        el(app, "lookTile-cartoon").tap()
        XCTAssertTrue(el(app, "lookTile-cartoon").waitForNonExistence(timeout: 5))
        XCTAssertTrue(el(app, "lookNotice").waitForExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookNotice").label, "Length changed to 30 s. Cartoon needs 30 s or more.")
        XCTAssertEqual(el(app, "lengthPill").value as? String, "30 s")
        el(app, "castPill").tap()
        XCTAssertTrue(el(app, "cast-fox").waitForExistence(timeout: 5))
        XCTAssertFalse(el(app, "lookNotice").exists, "the line goes with the next touch of a look pill")
    }

    /// Photos are the pictures of the video: a drawn look goes back to Auto with one line right above the pills, and the drawn looks stay in place, dimmed, with the reason.
    func testPhotosResetTheLookAndDimTheDrawnOnes() {
        let app = launch(["VMK_DEBUG_CREATE": "photos", "VMK_DEBUG_LOOK": "cartoon:fox"])
        XCTAssertTrue(el(app, "lookNotice").waitForExistence(timeout: 20), "one line says the look changed")
        XCTAssertEqual(el(app, "lookNotice").label, "Look set to Auto. Cartoon can't use your photos.")
        XCTAssertEqual(el(app, "lookPill").value as? String, "Auto")
        XCTAssertFalse(el(app, "castPill").exists)
        let gap = el(app, "forPill").frame.minY - el(app, "lookNotice").frame.maxY
        XCTAssertTrue(gap >= 0 && gap <= 16, "the line sits right above the pill row it is about (\(gap) pt)")
        openSheet(app)
        XCTAssertFalse(el(app, "lookNotice").exists, "the line goes with the next touch of the pill")
        XCTAssertTrue(el(app, "lookTile-real").exists && el(app, "lookTile-real").isEnabled)
        for id in ["whiteboard", "cartoon"] {
            XCTAssertTrue(el(app, "lookTile-\(id)").exists && !el(app, "lookTile-\(id)").isEnabled, "\(id) stays in place, dimmed")
            XCTAssertEqual(el(app, "lookTile-\(id)").value as? String, "Not with photos")
        }
        el(app, "lookTile-cartoon").tap()
        XCTAssertTrue(el(app, "lookTile-auto").isSelected && el(app, "lookTile-cartoon").exists, "a dimmed tile changes nothing and closes nothing")
        el(app, "lookTile-real").tap()
        XCTAssertTrue(el(app, "lookTile-real").waitForNonExistence(timeout: 5))
        XCTAssertEqual(el(app, "lookPill").value as? String, "Real")
    }

    /// A look the plan does not include: in place, dimmed, with the plan's name, not selectable, no purchase button. A look the stage does not have is hidden.
    func testALookOutsideThePlanIsDimmedAndAnUnavailableOneIsHidden() {
        let app = launch(looks: "locked,soon")
        openSheet(app)
        XCTAssertFalse(el(app, "lookTile-whiteboard").exists, "a look this stage does not have is hidden")
        let cartoon = el(app, "lookTile-cartoon")
        XCTAssertTrue(cartoon.exists && !cartoon.isEnabled, "dimmed")
        XCTAssertEqual(cartoon.value as? String, "Pro plan")
        cartoon.tap()
        XCTAssertFalse(cartoon.isSelected, "it cannot be chosen")
        XCTAssertTrue(el(app, "lookTile-auto").isSelected)
        let words = app.buttons.allElementsBoundByIndex.map { $0.label }.joined(separator: " | ")
        for w in ["Upgrade", "Buy", "Subscribe"] { XCTAssertFalse(words.contains(w), "no purchase button: \(words)") }
    }

    /// What the review measured: one left edge in each sheet (the 20 pt gutter), and the densest state inside the screen with room under the switch.
    func testOneLeftEdgeAndTheDensestStateFits() {
        for spanish in [false, true] {
            var app = launch(spanish: spanish, ["VMK_DEBUG_LOOK": "whiteboard:sheet"])
            XCTAssertTrue(el(app, "lookTile-auto").waitForExistence(timeout: 20)); sleep(1)
            var screen = app.windows.firstMatch.frame
            var title = el(app, "sheetTitle").frame.minX
            for id in ["lookTile-auto", "lookTile-whiteboard"] { XCTAssertEqual(el(app, id).frame.minX, title, accuracy: 0.6, "\(id) starts where the title starts") }
            XCTAssertEqual(screen.width - el(app, "lookTile-real").frame.maxX, title, accuracy: 0.6, "and the right edge mirrors it")
            let home: CGFloat = screen.height >= 800 ? 34 : 16          // phones with a home indicator need its 34 pt clear; the others the sheet's own 16 pt
            XCTAssertGreaterThanOrEqual(screen.height - el(app, "lookTile-cartoon").frame.maxY, home)
            print("MEASURE look sheet \(spanish ? "es" : "en"): title x \(title), tiles x \(el(app, "lookTile-auto").frame.minX), right margin \(screen.width - el(app, "lookTile-real").frame.maxX), title y \(el(app, "sheetTitle").frame.minY) of \(screen.height)")
            app.terminate()

            app = launch(spanish: spanish, ["VMK_DEBUG_DEFAULT_MINUTES": "0.25", "VMK_DEBUG_LOOK": "cartoon:fox:cast"])
            XCTAssertTrue(el(app, "cast-bear").waitForExistence(timeout: 20))
            el(app, "cast-bear").tap()          // a conversation in a 15 s video: the length line shows, the tallest the sheet gets
            let board = app.switches["extra-board"]
            XCTAssertTrue(board.waitForExistence(timeout: 5)); sleep(1)
            screen = app.windows.firstMatch.frame
            title = el(app, "sheetTitle").frame.minX
            let edges = ["cast-ines", "cast-owl", "castLine", "extra-board"].map { ($0, el(app, $0).frame.minX) }
            for (id, x) in edges { XCTAssertEqual(x, title, accuracy: 0.6, "\(id) starts where the title starts (\(x) against \(title))") }
            let clear = screen.height - board.frame.maxY
            print("MEASURE characters sheet densest \(spanish ? "es" : "en"): title x \(title), edges \(edges), switch bottom \(board.frame.maxY) of \(screen.height): \(clear) pt clear")
            XCTAssertGreaterThanOrEqual(clear, home, "at least 34 pt clear below the switch (16 pt on a phone without a home indicator)")
            XCTAssertTrue(board.isHittable && app.buttons["castDone"].isHittable && el(app, "cast-ines").isHittable, "nothing scrolls: header, faces and switch are all on screen")
            app.terminate()
        }
    }

    /// The decision of the review: with the Characters pill the row of pills may take a second row, never a third (English and Spanish, with one and with three faces).
    func testThePillRowHolds() {
        for spanish in [false, true] {
            for spec in ["cartoon", "cartoon:fox+bear+cat:board"] {
                let app = launch(spanish: spanish, large: mode == "large", ["VMK_DEBUG_LOOK": spec])
                XCTAssertTrue(el(app, "castPill").waitForExistence(timeout: 20)); sleep(1)
                let rows = pillRows(app), screen = app.windows.firstMatch.frame
                print("MEASURE pills \(spanish ? "es" : "en") \(mode.isEmpty ? "default" : mode) \(Int(screen.width))x\(Int(screen.height)) \(spec): \(rows) rows; " + ["forPill", "lengthPill", "lookPill", "castPill"].map { "\($0) \(el(app, $0).frame)" }.joined(separator: "; "))
                shot(app, "pills-\(spanish ? "es" : "en")-\(spec.contains("+") ? "three-faces" : "auto")")
                XCTAssertLessThanOrEqual(rows, 2, "the pills never take a third row")
                XCTAssertTrue(el(app, "castPill").isHittable && app.buttons["sendButton"].isHittable)
                XCTAssertLessThanOrEqual(el(app, "castPill").frame.maxX, screen.width - 19, "the pill is whole")
                app.terminate()
            }
        }
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

    /// Spanish: the server's words, our lines, and the pills.
    func testSpanish() {
        let app = launch(spanish: true, ["VMK_DEBUG_DEFAULT_MINUTES": "0.25"])
        openSheet(app)
        XCTAssertEqual(el(app, "lookTile-auto").label, "Auto")
        XCTAssertEqual(el(app, "lookTile-cartoon").label, "Animado")
        XCTAssertEqual(el(app, "lookTile-cartoon").value as? String, "Personajes lo explican")
        el(app, "lookTile-cartoon").tap()
        XCTAssertTrue(el(app, "castPill").waitForExistence(timeout: 5))
        XCTAssertEqual(el(app, "castPill").label, "Personajes"); XCTAssertEqual(el(app, "castPill").value as? String, "Auto")
        openCast(app)
        XCTAssertEqual(el(app, "castLine").label, "Elegimos por ti. O elige hasta 3.")
        el(app, "cast-priya").tap()
        XCTAssertEqual(el(app, "castLine").label, "Priya presenta.")
        el(app, "cast-mateo").tap()
        XCTAssertEqual(el(app, "castLine").label, "Duración cambiada a 30 s. Una conversación necesita 20 s o más.")
        XCTAssertEqual(app.switches["extra-board"].label, "Los personajes explican en una pizarra")
        closeCast(app)
        XCTAssertEqual(el(app, "lookPill").label, "Estilo"); XCTAssertEqual(el(app, "lookPill").value as? String, "Animado")
        XCTAssertEqual(el(app, "castPill").value as? String, "Priya y Mateo")
        openCast(app)
        XCTAssertEqual(el(app, "castLine").label, "Priya y Mateo lo conversan.")
    }

    /// The largest text: the looks are rows on one screen, every face can be reached, the header stays, targets are at least 44 pt.
    func testLargestText() {
        let app = launch(large: true)
        openSheet(app)
        let cartoon = el(app, "lookTile-cartoon")
        XCTAssertTrue(cartoon.isHittable && el(app, "lookTile-auto").isHittable, "rows: all four looks are on one screen")
        XCTAssertLessThan(el(app, "lookTile-auto").frame.height, 120)
        cartoon.tap()
        openCast(app)
        XCTAssertTrue(el(app, "cast-ines").isHittable, "the faces are the first thing in their sheet")
        let turtle = el(app, "cast-turtle")
        for _ in 0..<6 where !turtle.isHittable { app.swipeUp() }
        XCTAssertTrue(turtle.isHittable, "the last face is reachable by scrolling")
        XCTAssertGreaterThanOrEqual(turtle.frame.height, 44)
        turtle.tap()
        XCTAssertTrue(turtle.isSelected)
        let board = app.switches["extra-board"]
        for _ in 0..<3 where !board.isHittable { app.swipeUp() }
        XCTAssertTrue(board.isHittable)
        XCTAssertTrue(app.buttons["castDone"].isHittable, "the header is pinned: the close button is there after scrolling")
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

    /// Every state, in the appearance `TEST_RUNNER_VMK_SHOTS_MODE` asks for (default light; `dark`, `large`, `es`, `small`). Skipped without a folder to write to.
    func testCaptures() throws {
        guard ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"] != nil else { throw XCTSkip("set TEST_RUNNER_VMK_SHOTS_DIR") }
        let es = mode == "es", dark = mode == "dark"
        let tall = mode == "large"      // the Characters sheet scrolls there: take the scrolled shots as well
        func start(looks: String? = "1", _ env: [String: String] = [:]) -> XCUIApplication { launch(spanish: es, large: mode == "large", dark: dark, looks: looks, env) }
        func settle(_ app: XCUIApplication, _ id: String) { XCTAssertTrue(el(app, id).waitForExistence(timeout: 20), id); sleep(1) }
        var app: XCUIApplication

        app = start(); settle(app, "lookPill"); shot(app, "01-create-auto")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "02-sheet-auto"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "whiteboard"]); settle(app, "lookPill"); shot(app, "03-create-whiteboard")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "04-sheet-whiteboard"); app.terminate()
        app = start(["VMK_DEBUG_LOOK": "real"]); settle(app, "lookPill"); shot(app, "03b-create-real")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "04b-sheet-real"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "cartoon"]); settle(app, "castPill"); shot(app, "05-create-cartoon-auto")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "05b-sheet-cartoon"); app.terminate()
        app = start(["VMK_DEBUG_LOOK": "cartoon:cast"]); settle(app, "cast-fox"); shot(app, "06-characters-auto")
        if tall { app.swipeUp(); shot(app, "06b-characters-auto-end") }
        app.terminate()
        app = start(["VMK_DEBUG_LOOK": "cartoon:fox:cast"]); settle(app, "cast-fox"); shot(app, "06c-characters-one"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "cartoon:fox+bear:board:cast"]); settle(app, "cast-fox"); shot(app, "07-characters-talk")
        if tall { app.swipeUp(); shot(app, "07b-characters-talk-end") }
        app.terminate()
        app = start(["VMK_DEBUG_LOOK": "cartoon:fox+bear:board"]); settle(app, "castPill"); shot(app, "08-create-cartoon-talk"); app.terminate()

        app = start(["VMK_DEBUG_LOOK": "cartoon:fox+bear+cat:cast"]); settle(app, "cast-fox"); shot(app, "09-characters-three-full"); app.terminate()
        app = start(["VMK_DEBUG_LOOK": "cartoon:priya+mateo+cat"]); settle(app, "castPill"); shot(app, "10-create-cartoon-three"); app.terminate()

        app = start(["VMK_DEBUG_DEFAULT_MINUTES": "0.25", "VMK_DEBUG_LOOK": "cartoon:fox:cast"]); settle(app, "cast-fox")
        let bear = el(app, "cast-bear"); for _ in 0..<4 where !bear.isHittable { app.swipeUp() }
        bear.tap(); sleep(1); if tall { app.swipeUp() }
        shot(app, "11-characters-length-moved"); app.terminate()

        app = start(looks: "locked"); settle(app, "lookPill"); el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "12-sheet-plan-locked"); app.terminate()
        app = start(looks: "soon"); settle(app, "lookPill"); el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "13-sheet-one-hidden"); app.terminate()

        app = start(["VMK_DEBUG_CREATE": "photos", "VMK_DEBUG_LOOK": "cartoon:fox"]); settle(app, "lookNotice"); shot(app, "14-create-photos-reset")
        el(app, "lookPill").tap(); settle(app, "lookTile-auto"); shot(app, "15-sheet-with-photos"); app.terminate()

        app = start(looks: "short", ["VMK_DEBUG_DEFAULT_MINUTES": "0.25"]); settle(app, "lookPill"); el(app, "lookPill").tap(); settle(app, "lookTile-cartoon")
        el(app, "lookTile-cartoon").tap(); settle(app, "lookNotice"); shot(app, "16-create-length-moved"); app.terminate()

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
