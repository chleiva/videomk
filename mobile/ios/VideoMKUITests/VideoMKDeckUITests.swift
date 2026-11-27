import XCTest

/// "Add a presentation" against the in-app fake server (debug builds only, no network, no account): every state of the journey, in English and Spanish,
/// at normal and accessibility text. The Files picker itself is system UI and cannot be driven here: `VMK_DEBUG_DECK_FILE=<name>[:<MB>]` picks a file the way the
/// picker would (see mobile/ios/README.md). Screenshots: `TEST_RUNNER_VMK_SHOTS_DIR` (+ `_PREFIX`, `_MODE=dark|large`, which the tests below read).
final class VideoMKDeckUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func launch(spanish: Bool = false, large: Bool = false, _ env: [String: String]) -> XCUIApplication {
        let app = spanish ? XCUIApplication.spanish() : XCUIApplication.english()
        let mode = ProcessInfo.processInfo.environment["VMK_SHOTS_MODE"] ?? ""
        if mode == "dark" { app.launchArguments += ["-AppleInterfaceStyle", "Dark"] }
        if large || mode == "large" { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXL"] }
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        app.launchEnvironment["VMK_DEBUG_BALANCE"] = "12"
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

    /// Create open on the fake server with a deck script and an optional picked file.
    private func create(_ script: String, file: String? = "Quarterly review.pptx", state: String = "empty", spanish: Bool = false, large: Bool = false) -> XCUIApplication {
        var env = ["VMK_DEBUG_CREATE": state, "VMK_DEBUG_DECK": script]
        if let file { env["VMK_DEBUG_DECK_FILE"] = file }
        return launch(spanish: spanish, large: large, env)
    }

    /// The photo icon is a small menu when presentations are on: open it, and the "Add a presentation" row is there.
    @discardableResult private func openDeckMenu(_ app: XCUIApplication) -> Bool {
        guard el(app, "photoButton").waitForExistence(timeout: 15) else { return false }
        el(app, "photoButton").tap()
        return el(app, "deckButton").waitForExistence(timeout: 5)
    }

    /// Scrolls (either way) until the element can be tapped: at large text the Create form is several screens tall and the deck card scrolls itself into view.
    private func reveal(_ app: XCUIApplication, _ id: String) {
        let e = el(app, id), h = app.windows.firstMatch.frame.height
        func drag(up: Bool) {
            let from = up ? 0.62 : 0.4, to = up ? 0.44 : 0.58
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: from)).press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: to)))
        }
        _ = e.waitForExistence(timeout: 3)
        for _ in 0..<60 {          // small drags until the element sits between the title bar and the bottom bar (which covers the lowest 30 % at large text)
            guard e.exists else { drag(up: true); continue }            // a lazily built chip is not there until its row is near
            let f = e.frame
            guard f.minY.isFinite else { drag(up: false); continue }    // scrolled far past it: no frame at all
            if e.isHittable, f.minY >= 120, f.maxY <= h * 0.68 { return }
            drag(up: f.maxY > h * 0.68 || (!e.isHittable && f.minY > 120))
        }
    }

    private func focus(_ app: XCUIApplication, _ id: String) {
        reveal(app, id)
        for _ in 0..<3 where !app.keyboards.firstMatch.exists { el(app, id).tap(); _ = app.keyboards.firstMatch.waitForExistence(timeout: 3) }
    }

    private func waitForLabel(_ e: XCUIElement, contains text: String, timeout: TimeInterval = 8) -> Bool {
        XCTWaiter().wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label CONTAINS %@", text), object: e)], timeout: timeout) == .completed
    }

    private func label(_ app: XCUIApplication, _ id: String) -> String { el(app, id).label }

    private func assertFits(_ app: XCUIApplication, _ ids: [String]) {
        let screen = app.windows.firstMatch.frame
        for id in ids {
            let e = el(app, id)
            XCTAssertTrue(e.waitForExistence(timeout: 5), id)
            XCTAssertGreaterThanOrEqual(e.frame.minX, 0, "\(id) not clipped left")
            XCTAssertLessThanOrEqual(e.frame.maxX, screen.maxX + 0.5, "\(id) not clipped right")
        }
    }

    // MARK: the feature is hidden unless the server enables it

    func testNoPresentationRowWhenTheServerDoesNotSendIt() {
        let app = launch(["VMK_DEBUG_CREATE": "empty"])
        XCTAssertTrue(el(app, "photoButton").waitForExistence(timeout: 15))
        XCTAssertFalse(el(app, "deckButton").exists, "capabilities.deck is absent: nothing about presentations is shown")
    }

    func testRowAppearsWhenEnabledAndOffersTheFilesPicker() {
        let app = create("ok", file: nil)
        XCTAssertTrue(openDeckMenu(app), "the photo button offers a presentation")
        XCTAssertEqual(el(app, "deckButton").label, "Add a presentation")
        shot(app, "deck-01-row")
        el(app, "deckButton").tap()
        XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 10), "the Files picker opens")
    }

    // MARK: the journey

    func testUploadingThenReadingThenReady() {
        var app = create("slow")          // the transient states are too quick to catch here: the stalled scripts below hold them still
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30), "the deck is ready")
        XCTAssertEqual(label(app, "deckName"), "Quarterly review.pptx")
        XCTAssertTrue(label(app, "deckSummary").contains("12 slides") && label(app, "deckSummary").contains("4 minutes"), label(app, "deckSummary"))
        XCTAssertTrue(el(app, "deckPromise").exists)
        XCTAssertTrue(el(app, "deckCost").label.contains("4 credits"), el(app, "deckCost").label)
        XCTAssertTrue(el(app, "sendButton").value as? String != nil)
        XCTAssertFalse(el(app, "photoNote").exists)
        shot(app, "deck-05-ready")
        app.terminate()
        app = create("uploading"); XCTAssertTrue(el(app, "deckUploading").waitForExistence(timeout: 15)); shot(app, "deck-03-uploading")
        el(app, "deckCancel").tap()
        XCTAssertTrue(openDeckMenu(app), "cancel removes it and the photo menu offers a presentation again")
        app.terminate()
        app = create("processing"); XCTAssertTrue(el(app, "deckProcessing").waitForExistence(timeout: 15)); shot(app, "deck-04-processing")
    }

    func testChangingTheLengthChangesThePriceAndCreateStartsTheWaitingCard() {
        let app = create("ok")
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
        XCTAssertTrue(el(app, "deckCost").label.contains("4 credits"))
        el(app, "lengthPill").tap()
        el(app, "length-2").tap()
        reveal(app, "deckCost")
        XCTAssertTrue(waitForLabel(el(app, "deckCost"), contains: "2 credits"), "the usual rule for another length: \(el(app, "deckCost").label)")
        el(app, "sendButton").tap()
        XCTAssertTrue(el(app, "runningRow").waitForExistence(timeout: 15), "the video is on the home screen")
        XCTAssertTrue(app.staticTexts["Reading your slides"].waitForExistence(timeout: 5), "the deck's first stage in the Making card")
        shot(app, "deck-09-making-reading")
        XCTAssertTrue(app.staticTexts["Writing the narration"].waitForExistence(timeout: 12), "then the second")
        shot(app, "deck-10-making-writing")
    }

    func testTheDescriptionIsOptionalForADeck() {
        let app = create("ok")
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
        XCTAssertEqual(el(app, "composerField").placeholderValue, "Who is it for?")
        let send = el(app, "sendButton")
        XCTAssertTrue((send.value as? String ?? "").contains("Ready") || send.isEnabled, "Create works with no description")
        XCTAssertFalse(el(app, "notEnoughCredits").exists)
    }

    func testAOneToNineCharacterDescriptionIsHeldBackInBothLanguages() {
        for (spanish, hint) in [(false, "Add a few more words, or leave it empty"), (true, "Agrega unas palabras más o déjalo vacío")] {
            let app = create("ok", spanish: spanish)
            XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
            XCTAssertFalse(app.staticTexts[hint].exists, "empty is fine")
            focus(app, "composerField")
            el(app, "composerField").typeText("students")
            XCTAssertTrue(app.staticTexts[hint].waitForExistence(timeout: 5), "8 characters: the hint shows and Create waits")
            shot(app, "\(spanish ? "es-" : "")deck-12-short-prompt")
            el(app, "composerField").typeText(" and teachers")
            XCTAssertFalse(app.staticTexts[hint].waitForExistence(timeout: 2), "10 characters or more: accepted")
            app.terminate()
        }
    }

    // MARK: failures

    func testEachServerFailureShowsItsOwnCalmMessageAndAction() {
        let cases: [(code: String, title: String, action: String)] = [
            ("deck_too_large", "This file is too big", "Choose another file"), ("deck_too_many_slides", "Too many slides", "Choose another file"),
            ("deck_encrypted", "This presentation is protected", "Choose another file"), ("deck_macro", "This file has macros", "Choose another file"),
            ("deck_corrupt", "We couldn't open this file", "Choose another file"), ("deck_empty", "This presentation is empty", "Choose another file"),
            ("deck_unsafe", "We can't use this file", "Choose another file"), ("deck_convert_timeout", "We couldn't read the slides", "Choose the file again"),
            ("deck_convert_failed", "We couldn't read the slides", "Choose the file again")]
        for c in cases {
            let app = create("fail:\(c.code)")
            XCTAssertTrue(el(app, "deckErrorTitle").waitForExistence(timeout: 30), c.code)
            XCTAssertEqual(label(app, "deckErrorTitle"), c.title, c.code)
            XCTAssertEqual(label(app, "deckAction"), c.action, c.code)
            XCTAssertFalse(label(app, "deckErrorMessage").contains("Server message"), "our own words, not the server's")
            shot(app, "deck-err-\(c.code)")
            app.terminate()
        }
    }

    func testLocalChecksExplainBeforeAnyUpload() {
        var app = create("ok", file: "huge.pptx:80")
        XCTAssertTrue(el(app, "deckErrorTitle").waitForExistence(timeout: 15))
        XCTAssertEqual(label(app, "deckErrorTitle"), "This file is too big")
        XCTAssertTrue(label(app, "deckErrorMessage").contains("50 MB"))
        shot(app, "deck-err-local-too-large"); app.terminate()
        app = create("ok", file: "old.ppt")
        XCTAssertTrue(el(app, "deckErrorTitle").waitForExistence(timeout: 15))
        XCTAssertTrue(label(app, "deckErrorMessage").contains("PPT") && label(app, "deckErrorMessage").contains("PDF"))
        shot(app, "deck-err-local-export"); app.terminate()
        app = create("ok", file: "notes.txt")
        XCTAssertTrue(el(app, "deckErrorTitle").waitForExistence(timeout: 15))
        XCTAssertEqual(label(app, "deckErrorTitle"), "We can't use this file type")
        el(app, "deckRemove").tap()
        XCTAssertTrue(openDeckMenu(app), "Remove puts the option back")
    }

    func testALostConnectionOffersTryAgainThatWorks() {
        let app = create("offline")
        XCTAssertTrue(el(app, "deckErrorTitle").waitForExistence(timeout: 15))
        XCTAssertEqual(label(app, "deckErrorTitle"), "Connection problem")
        XCTAssertEqual(label(app, "deckAction"), "Try again")
        shot(app, "deck-err-network")
        el(app, "deckAction").tap()
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30), "the retry sends the same file again and succeeds")
    }

    // MARK: format and exclusion

    func testVerticalFormatGetsAGentleWarningAndOneTapBack() {
        let app = create("ok", state: "shorts")
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
        XCTAssertTrue(el(app, "deckVerticalWarning").waitForExistence(timeout: 5), "9:16 with a deck: the slide is small")
        app.swipeUp(); shot(app, "deck-07-vertical")
        el(app, "deckUse169").tap()
        XCTAssertFalse(el(app, "deckVerticalWarning").waitForExistence(timeout: 2))
    }

    func testADeckDefaultsToLandscape() {
        let app = create("ok", state: "empty")
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
        XCTAssertTrue(el(app, "forPill").exists, "the For pill is there, on the landscape default")
        XCTAssertFalse(el(app, "deckVerticalWarning").exists)
    }

    func testChoosingADeckRemovesPhotosAfterAskingAndKeepingThemIsPossible() {
        var app = create("ok", file: nil, state: "photos")
        XCTAssertTrue(el(app, "photosNote").waitForExistence(timeout: 15))
        XCTAssertTrue(openDeckMenu(app))
        el(app, "deckButton").tap()
        XCTAssertTrue(app.alerts["Use a presentation instead?"].waitForExistence(timeout: 5))
        shot(app, "deck-08-replace-photos")
        XCTAssertTrue(app.alerts.buttons["Use presentation"].exists, "the destructive choice is offered")
        app.alerts.buttons["Keep photos"].tap()        // the photos stay
        XCTAssertTrue(el(app, "photosNote").exists, "photos stay when the person keeps them")
        app.terminate()
        app = create("ok", state: "photos")      // the file is picked: photos are dropped
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
        XCTAssertFalse(el(app, "photosNote").exists, "choosing a deck removed the photos")
        XCTAssertFalse(el(app, "attachedPhoto").exists)
        reveal(app, "photoButton")
        el(app, "photoButton").tap()
        app.buttons["photosMenuItem"].tap()
        XCTAssertTrue(app.alerts.buttons["Use photos"].waitForExistence(timeout: 5), "and the reverse asks before removing the deck")
        app.alerts.buttons["Keep presentation"].tap()
        XCTAssertTrue(el(app, "deckSummary").exists)
    }

    // MARK: waiting

    func testWaitingCardsShowTheDeckStages() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "deck"])
        XCTAssertTrue(app.staticTexts["Reading your slides"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["Writing the narration"].exists)
        shot(app, "deck-11-making-both")
    }

    // MARK: Spanish

    func testSpanishJourneyAndErrors() {
        var app = create("ok", spanish: true)
        XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
        XCTAssertTrue(label(app, "deckSummary").contains("12 diapositivas"), label(app, "deckSummary"))
        XCTAssertTrue(el(app, "deckCost").label.contains("4 créditos"), el(app, "deckCost").label)
        XCTAssertEqual(el(app, "composerField").placeholderValue, "¿Para quién es?")
        shot(app, "es-deck-05-ready")
        app.terminate()
        app = create("fail:deck_encrypted", spanish: true)
        XCTAssertTrue(el(app, "deckErrorTitle").waitForExistence(timeout: 30))
        XCTAssertEqual(label(app, "deckErrorTitle"), "Esta presentación está protegida")
        XCTAssertEqual(label(app, "deckAction"), "Elegir otro archivo")
        shot(app, "es-deck-err-deck_encrypted")
        app.terminate()
        app = create("ok", file: nil, spanish: true)
        XCTAssertTrue(openDeckMenu(app)); XCTAssertEqual(el(app, "deckButton").label, "Agregar una presentación")
        shot(app, "es-deck-01-row")
        app.terminate()
        app = create("uploading", spanish: true); XCTAssertTrue(el(app, "deckUploading").waitForExistence(timeout: 15)); shot(app, "es-deck-03-uploading"); app.terminate()
        app = create("processing", spanish: true); XCTAssertTrue(el(app, "deckProcessing").waitForExistence(timeout: 15)); shot(app, "es-deck-04-processing"); app.terminate()
        app = create("ok", state: "shorts", spanish: true); XCTAssertTrue(el(app, "deckVerticalWarning").waitForExistence(timeout: 30)); app.swipeUp(); shot(app, "es-deck-07-vertical"); app.terminate()
        app = launch(spanish: true, ["VMK_DEBUG_FAKE_VIDEOS": "deck"])
        XCTAssertTrue(app.staticTexts["Leyendo tus diapositivas"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["Escribiendo la narración"].exists)
        shot(app, "es-deck-11-making-both")
    }

    // MARK: accessibility text

    func testTheCardsFitAtAccessibilityXLInBothLanguages() {
        for spanish in [false, true] {
            var app = create("ok", spanish: spanish, large: true)
            XCTAssertTrue(el(app, "deckSummary").waitForExistence(timeout: 30))
            assertFits(app, ["deckSummary", "deckPromise", "deckCost"])
            for id in ["deckChoose", "deckRemove"] { XCTAssertGreaterThanOrEqual(el(app, id).frame.height, 44, "\(id) keeps a 44 pt target") }
            shot(app, "\(spanish ? "es-" : "")deck-05-ready-xl")
            app.terminate()
            app = create("fail:deck_macro", spanish: spanish, large: true)
            XCTAssertTrue(el(app, "deckErrorTitle").waitForExistence(timeout: 30))
            assertFits(app, ["deckErrorTitle", "deckErrorMessage"])
            XCTAssertGreaterThanOrEqual(el(app, "deckAction").frame.height, 44)
            shot(app, "\(spanish ? "es-" : "")deck-err-deck_macro-xl")
            app.terminate()
        }
    }
}
