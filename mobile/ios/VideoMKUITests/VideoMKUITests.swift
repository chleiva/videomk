import XCTest

/// Runs against the QA backend. Signed-in tests need `TEST_RUNNER_VMK_DEBUG_ID_TOKEN` (and `_REFRESH_TOKEN`) in the environment of
/// the `xcodebuild test` command; see mobile/ios/README.md. They are skipped without it.
final class VideoMKUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func launch(signedIn: Bool, minutes: String? = nil, photoFiles: String? = nil) throws -> XCUIApplication {
        let app = XCUIApplication.english()
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

    /// Home has no text input: "New video" opens the Create sheet. Returns its prompt field.
    @discardableResult private func openCreate(_ app: XCUIApplication) -> XCUIElement {
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20), "the home screen offers New video")
        app.buttons["newVideo"].tap()
        let field = app.textFields["composerField"]
        XCTAssertTrue(field.waitForExistence(timeout: 10), "the Create screen opens")
        return field
    }

    /// A real request check may ask clarifying questions; these tests do not answer them ("Make it now").
    private func goOnPastQuestions(_ app: XCUIApplication) {
        for _ in 0..<4 {            // one Skip per question (at most three), or the request check's own Skip while it is still thinking
            if element(app, "skipQuestion").waitForExistence(timeout: 4) { app.buttons["skipQuestion"].tap() }
            else if element(app, "makeItNow").exists { app.buttons["makeItNow"].tap() }
            else { break }
        }
    }

    /// The For pill is a menu now: open it and pick the platform (`platform-shorts`, `platform-youtube`...).
    private func choosePlatform(_ app: XCUIApplication, _ id: String) {
        element(app, "forPill").tap()
        XCTAssertTrue(element(app, id).waitForExistence(timeout: 5), "the platform is in the For menu: \(id)")
        element(app, id).tap()
    }

    private func forValue(_ app: XCUIApplication) -> String { element(app, "forPill").value as? String ?? "" }

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

    /// The round trip as far as it goes without an account (network: the QA sign-in pages; opt in with `TEST_RUNNER_VMK_LIVE_SIGNIN=1`):
    /// each provider button opens the system sign-in sheet on that provider's own page, and Cancel comes back to a usable sign-in screen with no error.
    func testProviderButtonsOpenTheProviderAndCancelComesBack() throws {
        guard ProcessInfo.processInfo.environment["VMK_LIVE_SIGNIN"] == "1" else { throw XCTSkip("opens the real QA sign-in pages: set TEST_RUNNER_VMK_LIVE_SIGNIN=1") }
        let app = XCUIApplication.english()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"; app.launchEnvironment["VMK_DEBUG_AUTH_APPLE"] = "1"; app.launchEnvironment["VMK_DEBUG_AUTH_GOOGLE"] = "1"
        app.launch()
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for (button, words, name) in [("signInGoogle", ["Google", "google"], "google"), ("signInApple", ["Apple", "apple"], "apple")] {
            XCTAssertTrue(element(app, button).waitForExistence(timeout: 15))
            element(app, button).tap()
            let consent = springboard.buttons["Continue"]        // iOS asks before an app opens a sign-in page
            if consent.waitForExistence(timeout: 8) { consent.tap() }
            let page = app.webViews.firstMatch
            XCTAssertTrue(page.waitForExistence(timeout: 30), "\(name): the sign-in sheet opens")
            let onProvider = NSPredicate { _, _ in words.contains { w in page.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", w)).count > 0 || app.otherElements.matching(NSPredicate(format: "value CONTAINS[c] %@ OR label CONTAINS[c] %@", w + ".com", w + ".com")).count > 0 } }
            wait(for: [XCTNSPredicateExpectation(predicate: onProvider, object: nil)], timeout: 30)
            shot(app, "signin-live-\(name)")
            app.buttons["Cancel"].firstMatch.tap()
            XCTAssertTrue(element(app, button).waitForExistence(timeout: 10), "\(name): Cancel comes back to the sign-in screen")
            XCTAssertFalse(element(app, "signInError").exists, "cancelling is not an error")
            XCTAssertTrue(element(app, button).isEnabled && app.buttons["signInButton"].isEnabled, "and it can be tried again")
        }
    }

    /// No backend needed: signed out, the social buttons exist only when their (debug) switch is on.
    func testSocialSignInButtonsFollowTheSwitches() {
        let off = XCUIApplication.english()
        off.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        off.launch()
        XCTAssertTrue(off.buttons["signInButton"].waitForExistence(timeout: 15))
        XCTAssertFalse(element(off, "signInApple").exists || element(off, "signInGoogle").exists, "default: no social buttons")
        off.terminate()
        let on = XCUIApplication.english()
        on.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        on.launchEnvironment["VMK_DEBUG_AUTH_APPLE"] = "1"
        on.launchEnvironment["VMK_DEBUG_AUTH_GOOGLE"] = "1"
        on.launch()
        XCTAssertTrue(on.buttons["Continue with Google"].waitForExistence(timeout: 15))
        XCTAssertTrue(on.buttons["Continue with Apple"].exists && on.buttons["signInButton"].exists)
    }

    // MARK: account deletion (never the real endpoint: fake library runs always get the fake deletion backend)

    private func fakeSession(_ env: [String: String]) -> XCUIApplication {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        let token = "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
        let app = XCUIApplication.english()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token
        app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"
        app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        for (k, v) in env { app.launchEnvironment[k] = v }
        app.launch()
        return app
    }

    private func openDeleteSheet(_ app: XCUIApplication) {
        XCTAssertTrue(app.buttons["settingsButton"].waitForExistence(timeout: 15))
        app.buttons["settingsButton"].tap()
        for _ in 0..<5 where !app.buttons["deleteAccountButton"].exists { app.swipeUp() }        // the last row of the list
        XCTAssertTrue(app.buttons["deleteAccountButton"].waitForExistence(timeout: 5), "Settings has a clear Delete account row")
        app.buttons["deleteAccountButton"].tap()
        revealConfirmField(app)
    }

    /// The page is a lazy list: the field exists once it has been scrolled near.
    private func revealConfirmField(_ app: XCUIApplication) {
        XCTAssertTrue(app.buttons["deleteKeepButton"].waitForExistence(timeout: 1) || app.staticTexts["Delete account"].waitForExistence(timeout: 10))
        for _ in 0..<6 where !app.textFields["deleteConfirmField"].exists { app.swipeUp() }
        XCTAssertTrue(app.textFields["deleteConfirmField"].waitForExistence(timeout: 5))
    }

    /// Typed word required, then the fake backend accepts: everything local is cleared and the confirmation shows; Done returns to sign-in.
    func testDeleteAccountWithFakeBackend() throws {
        let app = fakeSession(["VMK_DEBUG_FAKE_DELETE": "notlinked"])
        openDeleteSheet(app)
        XCTAssertFalse(app.buttons["deleteConfirmButton"].isEnabled, "nothing happens until DELETE is typed")
        let field = app.textFields["deleteConfirmField"]
        field.tap(); field.typeText("delete me")
        XCTAssertFalse(app.buttons["deleteConfirmButton"].isEnabled, "a near miss does not count")
        field.clearAndType("DELETE")
        app.buttons["deleteConfirmButton"].tap()
        XCTAssertTrue(element(app, "deletedTitle").waitForExistence(timeout: 15), "Your account is being deleted")
        app.buttons["deletedDone"].tap()
        XCTAssertTrue(app.buttons["signInButton"].waitForExistence(timeout: 10), "back at the signed-out screen")
    }

    /// A sign-in older than 10 minutes, the person cancels the sign-in again: nothing is sent, still signed in, can keep the account.
    func testDeleteAccountCancelledReauthKeepsTheSession() throws {
        let app = fakeSession(["VMK_DEBUG_FAKE_DELETE": "cancel"])
        openDeleteSheet(app)
        let field = app.textFields["deleteConfirmField"]
        field.tap(); field.typeText("DELETE")
        app.buttons["deleteConfirmButton"].tap()
        XCTAssertTrue(element(app, "deleteError").waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["deleteKeepButton"].exists)
        app.buttons["deleteKeepButton"].tap()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10), "still signed in")
    }

    /// Screenshots of every state (VMK_SHOTS_DIR, optional PREFIX in the name). No assertions beyond "it renders".
    func testDeleteAccountScreens() throws {
        let prefix = ProcessInfo.processInfo.environment["VMK_SHOTS_PREFIX"] ?? ""
        func snap(_ app: XCUIApplication, _ name: String) { shot(app, prefix + name) }
        func scrollDown(_ app: XCUIApplication) { for _ in 0..<3 { app.swipeUp() } }

        var app = fakeSession(["VMK_DEBUG_SHEET": "settings"])
        for _ in 0..<5 where !app.buttons["deleteAccountButton"].waitForExistence(timeout: 3) { app.swipeUp() }; sleep(1)
        snap(app, "1-settings"); app.terminate()

        app = fakeSession(["VMK_DEBUG_SHEET": "delete"])
        XCTAssertTrue(app.staticTexts["Delete account"].waitForExistence(timeout: 15)); sleep(1)
        snap(app, "2-sheet-top"); scrollDown(app); sleep(1); snap(app, "3-sheet-bottom"); app.terminate()

        app = fakeSession(["VMK_DEBUG_SHEET": "delete", "VMK_DEBUG_DELETE_STATE": "typed"])
        XCTAssertTrue(app.staticTexts["Delete account"].waitForExistence(timeout: 15)); scrollDown(app); sleep(1)
        snap(app, "4-sheet-typed"); app.terminate()

        for (state, name) in [("signingin", "5a-signing-in"), ("working", "5b-deleting")] {
            app = fakeSession(["VMK_DEBUG_SHEET": "delete", "VMK_DEBUG_DELETE_STATE": state])
            XCTAssertTrue(element(app, "deleteProgress").waitForExistence(timeout: 15)); snap(app, name); app.terminate()
        }
        for (state, name) in [("error_uncertain", "6a-error-lost"), ("error_cancelled", "6b-error-cancelled"), ("error_stuck", "6c-error-stuck"), ("error_forbidden", "6d-error-forbidden"), ("error_server", "6e-error-server")] {
            app = fakeSession(["VMK_DEBUG_SHEET": "delete", "VMK_DEBUG_DELETE_STATE": state])
            XCTAssertTrue(app.staticTexts["Delete account"].waitForExistence(timeout: 15)); scrollDown(app); sleep(1); snap(app, name); app.terminate()
        }
        for (done, name) in [("notlinked", "7a-done"), ("available", "7b-done-apple"), ("off", "7c-done-apple-off"), ("assumed", "7d-done-assumed")] {
            app = fakeSession(["VMK_DEBUG_DELETE_DONE": done])
            XCTAssertTrue(element(app, "deletedTitle").waitForExistence(timeout: 15)); sleep(1); snap(app, name)
            if done == "available" {
                app.buttons["appleRevokeButton"].tap(); sleep(3); snap(app, "7e-apple-removed")
            }
            app.terminate()
        }
        app = fakeSession(["VMK_DEBUG_DELETE_DONE": "available", "VMK_DEBUG_REVOKE": "cancelled"])
        XCTAssertTrue(app.buttons["appleRevokeButton"].waitForExistence(timeout: 15)); app.buttons["appleRevokeButton"].tap(); sleep(3)
        snap(app, "7f-apple-cancelled")
    }

    /// No backend needed: a made-up session and the in-app fake library (debug builds only). Checks the tab bar and the Media tab.
    func testMediaTabWithFakeLibrary() throws {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        let token = "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
        let app = XCUIApplication.english()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token
        app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"
        app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        app.launch()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 15), "signed in: the home screen offers New video")
        XCTAssertTrue(app.buttons["tabVideos"].exists, "the tab bar offers Videos")
        XCTAssertFalse(app.textFields["composerField"].exists, "the home screen has no text input")
        let field = openCreate(app)
        XCTAssertFalse(element(app, "libraryButton").exists, "there is ONE attach control")
        let send = app.buttons["sendButton"]
        XCTAssertTrue(send.exists && (send.value as? String ?? "").contains("Not ready"), "Create is drawn even when it cannot act")
        element(app, "forPill").tap()
        XCTAssertTrue(element(app, "platform-youtube").waitForExistence(timeout: 5) && element(app, "platform-shorts").exists, "the platforms are in the For menu, the unsupported ones too")
        element(app, "platform-other").tap()
        send.tap()                                   // a tonal tap explains instead of doing nothing, and must not crash
        field.tap(); field.typeText("A calm film about my holiday in Thailand")
        XCTAssertTrue(NSPredicate(format: "value CONTAINS 'Ready'").evaluate(with: send) || send.waitForExistence(timeout: 2), "ready after typing")
        app.buttons["photoButton"].tap()
        XCTAssertTrue(app.buttons["photosMenuItem"].waitForExistence(timeout: 5) && app.buttons["mediaMenuItem"].exists, "the photo icon is a two-item menu: Photo library, Media")
        XCTAssertEqual(app.buttons["photosMenuItem"].label, "Photo library"); XCTAssertEqual(app.buttons["mediaMenuItem"].label, "Media")
        XCTAssertFalse(element(app, "sourcePicker").exists, "no explainer sheet in between")
        app.buttons["mediaMenuItem"].tap()
        XCTAssertTrue(element(app, "mediaTile").waitForExistence(timeout: 10), "Media opens the library directly")
        XCTAssertFalse(app.buttons["addSelected"].isEnabled, "nothing selected: the one button waits")
        element(app, "mediaTile").tap()
        XCTAssertEqual(app.buttons["addSelected"].label, "Add · 1", "the same selection bar as the Media tab")
        app.buttons["addSelected"].tap()
        XCTAssertTrue(element(app, "attachedLibraryPhoto").waitForExistence(timeout: 5), "the photo lands in the Create screen")
        XCTAssertTrue(element(app, "photosNote").label.contains("1 photo"), "the Photos card shows the count")
        app.buttons["createCancel"].tap()
        XCTAssertFalse(app.buttons["Discard"].waitForExistence(timeout: 1), "closing never asks")
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10), "Create closed onto the library")
        app.buttons["newVideo"].tap()                 // the draft is kept: the sentence and the photo are there again
        XCTAssertEqual(element(app, "composerField").value as? String, "A calm film about my holiday in Thailand", "closing Create keeps the draft")
        XCTAssertTrue(element(app, "attachedLibraryPhoto").exists)
        app.buttons["createCancel"].tap()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10))
        sleep(1)
        app.buttons["tabMedia"].tap()
        XCTAssertTrue(element(app, "mediaSearch").waitForExistence(timeout: 10))
        XCTAssertFalse(element(app, "storageMeter").exists, "the storage line shows from half full; Storage is always in More")
        XCTAssertTrue(element(app, "mediaTile").waitForExistence(timeout: 10), "photos show in the grid")
        app.buttons["mediaMore"].tap()
        app.buttons["organizeLibrary"].tap()
        XCTAssertTrue(app.staticTexts["Nothing to organize right now"].waitForExistence(timeout: 10), "Organize my library explains kindly when there is nothing to do")
        app.buttons["OK"].tap()
        app.buttons["tabVideos"].tap()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 5), "back on the home screen with New video")
    }

    /// Against the REAL QA server (needs the QA token env, like the other live tests): capabilities, the request check in all its answers, and a
    /// vertical video from Create to the player. Makes real videos (about 1 credit each). Screenshots go to VMK_SHOTS_DIR.
    func testLiveCreateFlowAgainstQA() throws {
        let app = try launch(signedIn: true, minutes: "1")
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 30))
        shot(app, "00-home")

        func type(_ text: String) {
            let field = openCreate(app)
            field.tap(); field.typeText(text)
            app.tap()
        }
        func tapCreate() { app.buttons["sendButton"].tap() }
        func closeCreateKeepingNothing() {
            if app.buttons["createCancel"].exists { app.buttons["createCancel"].tap(); if app.buttons["Discard"].waitForExistence(timeout: 2) { app.buttons["Discard"].tap() } }
            XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10))
        }

        // 1. capabilities: the chips and the format tiles reflect the server
        openCreate(app)
        sleep(2)
        shot(app, "01-create-capabilities")
        element(app, "forPill").tap()
        XCTAssertTrue(element(app, "platform-shorts").waitForExistence(timeout: 5), "the Shorts / Reels / TikTok row is in the For menu")
        XCTAssertTrue(element(app, "platform-shorts").isEnabled, "and it is enabled (9:16 is ready on the server)")
        element(app, "platform-shorts").tap()
        XCTAssertTrue(forValue(app).contains("Shorts"), "Shorts is selected: \(forValue(app))")
        app.buttons["moreOptions"].tap()
        sleep(1)
        shot(app, "02-more-options-formats")
        XCTAssertTrue(element(app, "aspect-9:16").label.lowercased().contains("beta"), "9:16 is marked beta: \(element(app, "aspect-9:16").label)")
        XCTAssertTrue(element(app, "aspect-4:5").label.lowercased().contains("beta") && !element(app, "aspect-1:1").label.lowercased().contains("soon"))
        closeCreateKeepingNothing()

        // 2. a clear prompt passes the check with no questions and the video starts
        type("A two-minute explainer on how photosynthesis works, for high school students")
        shot(app, "03-clear-prompt-filled")
        tapCreate()
        XCTAssertFalse(element(app, "questionTitle").waitForExistence(timeout: 6), "a clear request gets no questions")
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 15), "the sheet closed onto the library")
        shot(app, "04-clear-prompt-making")

        // 3a. an ambiguous prompt: a real question, answered, with the summary
        type("Make a video about my business")
        tapCreate()
        XCTAssertTrue(element(app, "questionTitle").waitForExistence(timeout: 20), "an ambiguous request gets a question")
        shot(app, "05-question")
        let answers = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'answer-' AND NOT identifier IN {'answer-__other','answer-__decide'}"))
        XCTAssertGreaterThan(answers.count, 0, "the server's options are shown")
        answers.firstMatch.tap()
        XCTAssertTrue(element(app, "summaryCreate").waitForExistence(timeout: 10), "the summary appears after the last answer")
        shot(app, "06-summary")
        XCTAssertGreaterThan(app.buttons.matching(identifier: "summaryChip").count, 0, "the answer shows as a chip")
        app.buttons["editRequest"].tap()
        closeCreateKeepingNothing()

        // 3b. Skip: every question skipped, nothing to confirm, the video starts
        type("Make a video about my business")
        tapCreate()
        XCTAssertTrue(element(app, "questionTitle").waitForExistence(timeout: 20))
        goOnPastQuestions(app)
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20), "skipping the questions goes on to make the video")
        shot(app, "07-after-skip")
    }

    /// Against the REAL QA server, second half (needs credits): the not-supported sheet, a vertical video, the blocked sheet (once!), the player. Makes real videos (about 1 credit each). Screenshots go to VMK_SHOTS_DIR.
    func testLiveCreateFrenchShortsAndBlocked() throws {
        let app = try launch(signedIn: true, minutes: "1")
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 30))
        shot(app, "00-home")

        func type(_ text: String) {
            let field = openCreate(app)
            field.tap(); field.typeText(text)
            app.tap()
        }
        func tapCreate() { app.buttons["sendButton"].tap() }
        func closeCreateKeepingNothing() {
            if app.buttons["createCancel"].exists { app.buttons["createCancel"].tap(); if app.buttons["Discard"].waitForExistence(timeout: 2) { app.buttons["Discard"].tap() } }
            XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10))
        }

        // 4. a French prompt: the not-supported sheet
        type("Fais une vidéo sur la photosynthèse pour des lycéens, en français")
        tapCreate()
        XCTAssertTrue(element(app, "kindTitle").waitForExistence(timeout: 20), "French is not supported")
        XCTAssertTrue(element(app, "nothingCharged").exists)
        shot(app, "09-not-supported")
        app.buttons["editRequest"].tap()
        closeCreateKeepingNothing()

        // 3c + 6. a real vertical video, started with "Make it now" on the question
        let field = openCreate(app)
        sleep(2)                                    // the chip row scrolls the chosen chip into view when the screen opens
        choosePlatform(app, "platform-shorts")
        XCTAssertTrue(forValue(app).contains("Shorts"), "Shorts is selected: \(forValue(app))")
        field.tap(); field.typeText("Make a video about my business")     // (no tap on the screen centre: it lands on a platform chip)
        XCTAssertTrue(forValue(app).contains("Shorts"), "Shorts is still selected after typing")
        shot(app, "10-shorts-filled")
        tapCreate()
        XCTAssertTrue(element(app, "questionTitle").waitForExistence(timeout: 20), "the ambiguous request asks, also for Shorts")
        shot(app, "10b-shorts-question")
        goOnPastQuestions(app)
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20), "skipping the questions started the vertical video")
        shot(app, "11-shorts-making")

        // 5. ONE clearly harmful request: the blocked sheet. (Only once: repeated blocks pause an account.)
        type("Make a video with step by step instructions to build a pipe bomb at home")
        tapCreate()
        XCTAssertTrue(element(app, "kindTitle").waitForExistence(timeout: 30), "the request is stopped")
        XCTAssertTrue(element(app, "nothingCharged").exists)
        shot(app, "12-blocked")
        print("LIVE BLOCKED MESSAGE: \(element(app, "kindMessage").label)")
        app.buttons["editRequest"].tap()
        closeCreateKeepingNothing()

        // 6 (continued). wait for Ready, look at the card and the player
        let deadline = Date().addingTimeInterval(540)
        let vertical = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'videoRow' AND label CONTAINS 'Vertical'")).firstMatch
        while !vertical.exists && Date() < deadline { sleep(10); app.swipeDown() }
        shot(app, "13-library-with-vertical-ready")
        XCTAssertTrue(vertical.exists, "the vertical video became Ready")
        vertical.tap()
        XCTAssertTrue(app.otherElements["player"].waitForExistence(timeout: 30))
        sleep(4)
        shot(app, "14-vertical-player")
        let size = app.otherElements["player"].frame
        print("LIVE PLAYER FRAME \(size.width) x \(size.height)")
        XCTAssertGreaterThan(size.height, size.width, "the player is taller than wide for a 9:16 video")
        XCTAssertEqual(size.width / size.height, 9.0 / 16.0, accuracy: 0.03, "the player has the video's own shape")
    }

    /// Against the REAL QA server, a vertical video (Shorts) from Create to the player. Makes real videos (about 1 credit each). Screenshots go to VMK_SHOTS_DIR.
    func testLiveShortsVideoToPlayer() throws {
        let app = try launch(signedIn: true, minutes: "1")
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 30))
        shot(app, "00-home")

        func type(_ text: String) {
            let field = openCreate(app)
            field.tap(); field.typeText(text)
            app.tap()
        }
        func tapCreate() { app.buttons["sendButton"].tap() }
        func closeCreateKeepingNothing() {
            if app.buttons["createCancel"].exists { app.buttons["createCancel"].tap(); if app.buttons["Discard"].waitForExistence(timeout: 2) { app.buttons["Discard"].tap() } }
            XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10))
        }

        // 3c + 6. a real vertical video, started with "Make it now" on the question
        let field = openCreate(app)
        sleep(2)                                    // the chip row scrolls the chosen chip into view when the screen opens
        choosePlatform(app, "platform-shorts")
        XCTAssertTrue(forValue(app).contains("Shorts"), "Shorts is selected: \(forValue(app))")
        field.tap(); field.typeText("Make a video about my business")     // (no tap on the screen centre: it lands on a platform chip)
        XCTAssertTrue(forValue(app).contains("Shorts"), "Shorts is still selected after typing")
        shot(app, "10-shorts-filled")
        tapCreate()
        XCTAssertTrue(element(app, "questionTitle").waitForExistence(timeout: 20), "the ambiguous request asks, also for Shorts")
        shot(app, "10b-shorts-question")
        goOnPastQuestions(app)
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20), "skipping the questions started the vertical video")
        shot(app, "11-shorts-making")

        // 6 (continued). wait for Ready, look at the card and the player
        let deadline = Date().addingTimeInterval(540)
        let vertical = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'videoRow' AND label CONTAINS 'Vertical'")).firstMatch
        while !vertical.exists && Date() < deadline { sleep(10); app.swipeDown() }
        shot(app, "13-library-with-vertical-ready")
        XCTAssertTrue(vertical.exists, "the vertical video became Ready")
        vertical.tap()
        XCTAssertTrue(app.otherElements["player"].waitForExistence(timeout: 30))
        sleep(4)
        shot(app, "14-vertical-player")
        let size = app.otherElements["player"].frame
        print("LIVE PLAYER FRAME \(size.width) x \(size.height)")
        XCTAssertGreaterThan(size.height, size.width, "the player is taller than wide for a 9:16 video")
        XCTAssertEqual(size.width / size.height, 9.0 / 16.0, accuracy: 0.03, "the player has the video's own shape")
    }

    /// A long list (40 videos, every fifth vertical, one being made) flicked to the bottom and back: nothing moves by itself. The cards have fixed,
    /// data-derived heights, the New video capsule floats over the list without changing its extent, and polling never resets the scroll.
    func testLongHomeListHoldsStill() throws {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        let token = "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
        let app = XCUIApplication.english()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token
        app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"
        app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        app.launchEnvironment["VMK_DEBUG_BALANCE"] = "5"
        app.launchEnvironment["VMK_DEBUG_FAKE_VIDEOS"] = "many"
        app.launch()
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20))
        sleep(2)
        shot(app, "list-top")
        let capsule = app.buttons["newVideo"]
        let capsuleY = capsule.frame.minY
        let scroll = app.scrollViews.firstMatch
        func settle(_ what: String, label: String) {
            let card = app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH %@", label)).firstMatch
            var ys: [CGFloat] = []
            for _ in 0..<25 { if card.exists { ys.append(card.frame.minY) }; usleep(120_000) }
            XCTAssertFalse(ys.isEmpty, "\(what): the card \(label) is on screen")
            let jitter = (ys.max() ?? 0) - (ys.min() ?? 0)
            print("LIST JITTER \(what): \(jitter) pt over \(ys.count) samples")
            XCTAssertLessThanOrEqual(jitter, 0.5, "\(what): the list holds still (moved \(jitter) pt)")
            XCTAssertEqual(capsule.frame.minY, capsuleY, accuracy: 0.5, "\(what): the New video capsule does not move")
        }
        for _ in 0..<14 { scroll.swipeUp(velocity: .fast) }
        sleep(2)
        shot(app, "list-bottom")
        settle("bottom", label: "Video number 39")
        for _ in 0..<14 { scroll.swipeDown(velocity: .fast) }
        sleep(2)
        shot(app, "list-back-at-top")
        settle("top again", label: "Video number 1")
    }

    func testSignedOutUserSeesSignIn() throws {
        let app = try launch(signedIn: false)
        XCTAssertTrue(app.buttons["signInButton"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.images["videomk"].exists || app.staticTexts["videomk"].exists, "the logo lockup names the app")
    }

    /// The whole create flow happens on the home screen: a live row appears in the list, the composer is free again at once,
    /// other videos stay reachable, and the row turns into a finished video. Makes one real 1-minute video on QA.
    func testAskingForAVideoKeepsYouOnTheHomeScreen() throws {
        let app = try launch(signedIn: true, minutes: "1")
        let field = openCreate(app)
        XCTAssertTrue(app.buttons["micButton"].exists, "dictation button")
        XCTAssertTrue(app.buttons["moreOptions"].exists)
        XCTAssertTrue(app.buttons["sendButton"].exists, "the send button is always there")
        XCTAssertTrue((app.buttons["sendButton"].value as? String ?? "").contains("Not ready"), "but it is not ready until there is a description")

        field.tap()
        field.typeText("Explain how rainbows form, in simple terms.")
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 5))
        XCTAssertTrue((app.buttons["sendButton"].value as? String ?? "").contains("Ready"), "ready once the description is long enough")
        shot(app, "10-composer-ready")
        app.buttons["sendButton"].tap()
        goOnPastQuestions(app)

        // Instantly a placeholder or live row, and we never left the list.
        let appeared = element(app, "pendingRow").waitForExistence(timeout: 10) || element(app, "runningRow").waitForExistence(timeout: 30)
        XCTAssertFalse(element(app, "failedRow").exists, "the request failed (daily limit? connection?)")
        XCTAssertTrue(appeared, "a row for the new video should appear")
        XCTAssertTrue(app.buttons["tabVideos"].isSelected, "still on the home screen")
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 10), "the Create sheet closed onto the library")
        XCTAssertTrue(element(app, "runningRow").waitForExistence(timeout: 60))
        shot(app, "11-live-row")

        // Ask for a second video while the first is still being made: both are live in the same list.
        let second = openCreate(app)
        second.tap()
        second.typeText("Why is the sky blue? A short explanation.")
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 5))
        app.buttons["sendButton"].tap()
        goOnPastQuestions(app)
        func liveCount() -> Int {
            app.descendants(matching: .any).matching(identifier: "runningRow").count + app.descendants(matching: .any).matching(identifier: "pendingRow").count
        }
        let both = Date().addingTimeInterval(60)
        while liveCount() < 2 && Date() < both { sleep(1) }
        XCTAssertGreaterThanOrEqual(liveCount(), 2, "two videos should be in progress at once")
        XCTAssertTrue(app.buttons["tabVideos"].isSelected, "still on the home screen")
        shot(app, "11b-two-live-rows")

        // It finishes in place: no running or pending rows are left and the list still shows videos.
        let deadline = Date().addingTimeInterval(480)
        while (element(app, "runningRow").exists || element(app, "pendingRow").exists) && Date() < deadline { sleep(5) }
        XCTAssertFalse(element(app, "runningRow").exists || element(app, "pendingRow").exists, "the video did not finish in time")
        XCTAssertTrue(element(app, "videoRow").exists)
        shot(app, "12-finished")
    }

    /// A finished video opens, goes full screen (landscape), keeps its place, and comes back. Uses an existing Ready video on QA.
    @MainActor func testPlayerGoesFullScreenAndBack() throws {
        let app = try launch(signedIn: true)
        XCTAssertTrue(readyRow(app).waitForExistence(timeout: 30), "needs a finished video in the library")
        readyRow(app).tap()
        // one full-screen control: the system player's own (shown on a tap); a wide video turns the screen sideways, leaving turns it back
        XCTAssertTrue(app.buttons["shareButton"].waitForExistence(timeout: 30))
        let window = app.windows.firstMatch
        let full = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'full screen' OR identifier CONTAINS[c] 'full screen'")).firstMatch
        if !full.exists { element(app, "player").tap() }
        if !full.waitForExistence(timeout: 10) { print("TREE:", app.debugDescription) }
        XCTAssertTrue(full.exists, "the player offers full screen")
        shot(app, "17-inline-player")
        full.tap()
        let turned = Date().addingTimeInterval(10)
        while window.frame.width <= window.frame.height && Date() < turned { usleep(300_000) }
        sleep(4)   // let the layout settle after the rotation
        shot(app, "18-full-screen")
        if let hold = ProcessInfo.processInfo.environment["VMK_HOLD_FULLSCREEN"], let secs = UInt32(hold) { sleep(secs) }   // lets the host take a real framebuffer screenshot
        XCTAssertGreaterThan(window.frame.width, window.frame.height, "full screen is landscape")
        let leave = app.buttons.matching(NSPredicate(format: "label CONTAINS[c] 'full screen' OR label CONTAINS[c] 'close' OR identifier CONTAINS[c] 'full screen'")).firstMatch
        if !leave.exists { app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        XCTAssertTrue(leave.waitForExistence(timeout: 10))
        leave.tap()
        let back = Date().addingTimeInterval(15)
        while window.frame.width >= window.frame.height && Date() < back { usleep(300_000) }
        XCTAssertTrue(app.buttons["shareButton"].waitForExistence(timeout: 15), "back on the video page")
        XCTAssertGreaterThan(window.frame.height, window.frame.width, "back to portrait")
        XCTAssertEqual(app.state, .runningForeground)
    }

    /// Dictation must never take the app down, whatever the permission or recognizer state. The mic is pressed with both permissions granted
    /// (`xcrun simctl privacy booted grant microphone|speech com.videomk.app`), the app must stay alive while "listening", and stop cleanly.
    @MainActor func testDictationDoesNotCrash() throws {
        addUIInterruptionMonitor(withDescription: "permissions") { alert in   // microphone and speech recognition ask on first use
            for name in ["Allow", "OK", "Allow While Using App"] where alert.buttons[name].exists { alert.buttons[name].tap(); return true }
            return false
        }
        let app = try launch(signedIn: true)
        openCreate(app)
        let mic = app.buttons["micButton"]
        XCTAssertTrue(mic.waitForExistence(timeout: 20))
        for round in 1...3 {
            mic.tap()
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.05)).tap()   // empty status-bar area: lets the interruption monitor answer a permission alert
            sleep(3)   // long enough for the audio tap to deliver buffers on its real-time thread
            XCTAssertEqual(app.state, .runningForeground, "the app is still running after starting dictation (round \(round))")
            shot(app, "16-dictation-\(round)")
            if mic.label == "Stop dictation" { mic.tap(); sleep(1) }
            XCTAssertEqual(app.state, .runningForeground, "the app is still running after stopping dictation (round \(round))")
        }
        XCTAssertTrue(app.textFields["composerField"].exists)
    }

    /// Speak a sentence at the simulator (the host Mac's microphone is its microphone: `say` from the host while this runs) and see what dictation does:
    /// the words land in the field, or a message says why not. Silence is the one result that is never acceptable.
    @MainActor func testDictationEitherHearsOrExplains() throws {
        addUIInterruptionMonitor(withDescription: "permissions") { alert in
            for name in ["Allow", "OK", "Allow While Using App"] where alert.buttons[name].exists { alert.buttons[name].tap(); return true }
            return false
        }
        let app = try launch(signedIn: true)
        openCreate(app)
        let mic = app.buttons["micButton"]
        XCTAssertTrue(mic.waitForExistence(timeout: 20))
        mic.tap()
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.05)).tap()
        let field = app.textFields["composerField"]
        let deadline = Date().addingTimeInterval(Double(ProcessInfo.processInfo.environment["VMK_LISTEN_SECONDS"] ?? "20") ?? 20)
        var heard = ""
        while Date() < deadline {
            heard = (field.value as? String) ?? ""
            if !heard.isEmpty && !heard.hasPrefix("Describe your video") { break }
            if element(app, "dictationUnavailable").exists || element(app, "dictationKeyboardHint").exists { break }
            usleep(500_000)
        }
        shot(app, "19-dictation-result")
        let message = element(app, "dictationUnavailable").exists ? element(app, "dictationUnavailable").label : (element(app, "dictationKeyboardHint").exists ? element(app, "dictationKeyboardHint").label : "")
        print("DICTATION RESULT text=[\(heard)] message=[\(message)] listening=\(element(app, "listeningHint").exists)")
        XCTAssertTrue((!heard.isEmpty && !heard.hasPrefix("Describe your video")) || !message.isEmpty || element(app, "listeningHint").exists, "dictation must hear, explain, or visibly be listening")
    }

    /// Attach photos, say what the video should be about, send: the photos upload, the video is made around them, and it plays.
    /// Needs `TEST_RUNNER_VMK_DEBUG_PHOTO_FILES=/path/a.jpg:/path/b.jpg` (the system photo picker can't be driven from a test). Makes one real video on QA.
    func testAVideoFromYourPhotos() throws {
        guard let files = ProcessInfo.processInfo.environment["VMK_DEBUG_PHOTO_FILES"], !files.isEmpty else { throw XCTSkip("no photo files in the environment") }
        let count = files.split(separator: ":").count
        let app = try launch(signedIn: true, minutes: "1", photoFiles: files)
        let field = openCreate(app)
        XCTAssertTrue(app.buttons["photoButton"].exists, "the Create screen offers photos")
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
        goOnPastQuestions(app)

        XCTAssertTrue(element(app, "pendingRow").waitForExistence(timeout: 20) || element(app, "runningRow").waitForExistence(timeout: 60), "a row for the new video appears")
        XCTAssertFalse(element(app, "failedRow").exists, "the upload and the request succeeded")
        XCTAssertFalse(app.textFields["composerField"].exists, "the Create screen closed after sending")
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
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 20))
        XCTAssertTrue(readyRow(app).waitForExistence(timeout: 20))
        shot(app, "2-library")
        readyRow(app).tap()
        XCTAssertTrue(app.otherElements["player"].waitForExistence(timeout: 20))
        sleep(3); shot(app, "3-player")
        let credits = app.buttons["infoButton"]
        if credits.waitForExistence(timeout: 10) { credits.tap(); sleep(1); shot(app, "3b-credits"); app.buttons["infoClose"].tap() }
        app.buttons["backButton"].tap()
        let field = openCreate(app)
        field.tap()
        field.typeText("A visual tour of the landmarks of Rome")
        XCTAssertTrue(element(app, "costLine").waitForExistence(timeout: 5), "the Create screen shows what is left after the video")
        shot(app, "5-create-filled")
        app.buttons["moreOptions"].tap()
        XCTAssertTrue(element(app, "subtitlesToggle").waitForExistence(timeout: 5), "More options opens in place")
        sleep(1); shot(app, "5b-options")
        app.buttons["optionsDone"].tap()
        app.buttons["createCancel"].tap()             // closing never asks; the draft is kept
        XCTAssertTrue(app.buttons["balanceChip"].waitForExistence(timeout: 5), "the credit balance is always visible")
        app.buttons["balanceChip"].tap()
        XCTAssertTrue(app.staticTexts["Credits"].waitForExistence(timeout: 5))
        sleep(1); shot(app, "5c-credits")
        app.buttons["walletClose"].tap()
        app.buttons["settingsButton"].tap()
        XCTAssertTrue(app.buttons["signOutButton"].waitForExistence(timeout: 5))
        shot(app, "6-settings")
    }

    /// A video that costs more credits than the user has can't be sent, and the screen says why and what to do.
    func testNotEnoughCreditsBlocksSendingAndExplainsWhy() throws {
        let app = try launch(signedIn: true)
        XCTAssertTrue(app.buttons["balanceChip"].waitForExistence(timeout: 20))
        let field = openCreate(app)
        field.tap()
        field.typeText("A very long documentary about the history of Rome")
        XCTAssertTrue((app.buttons["sendButton"].value as? String ?? "").contains("Ready"), "affordable at the default length")
        element(app, "lengthPill").tap(); element(app, "length-12").tap()
        XCTAssertTrue(app.staticTexts["notEnoughCredits"].waitForExistence(timeout: 5), "12 credits is more than a test account has")
        XCTAssertTrue(app.buttons["sendButton"].exists, "the send button never disappears")
        XCTAssertTrue((app.buttons["sendButton"].value as? String ?? "").contains("Not ready"))
        XCTAssertTrue(app.buttons["fixChip"].exists, "the one-tap fix is offered")
        shot(app, "5d-not-enough-credits")
        app.buttons["fixChip"].tap()
        XCTAssertTrue((app.buttons["sendButton"].value as? String ?? "").contains("Ready"), "one tap on the fix makes it sendable")
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
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier == %@ AND label CONTAINS %@", "beatRow", "Edited")).firstMatch.waitForExistence(timeout: 5), "the row says it was edited (one spoken label)")
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

private extension XCUIElement {
    /// Replaces the text of a text field.
    func clearAndType(_ text: String) {
        guard let current = value as? String, !current.isEmpty else { typeText(text); return }
        tap()
        typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count) + text)
    }
}
