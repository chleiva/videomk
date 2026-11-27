import XCTest

/// Acceptance tests for the design audit of 2026-11-27 (docs/audits/2026-11-27/IOS_AUDIT.md), on the fake-library build: undo instead of confirm,
/// the photo menu with direct pickers, Skip all, the paused sheet, the keyboard and the tab bar, portrait only, and the rebuilt screens.
/// Screenshots: set `TEST_RUNNER_VMK_SHOTS_DIR` (files are named `audit-<name>.png`); `TEST_RUNNER_VMK_SHOTS_MODE=dark` runs them in the dark appearance.
final class VideoMKAuditUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false; XCUIDevice.shared.orientation = .portrait }

    private func token() -> String {
        func b64(_ o: [String: Any]) -> String { (try! JSONSerialization.data(withJSONObject: o)).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
        return "\(b64(["alg": "none"])).\(b64(["sub": "demo-user", "email": "demo@example.com", "exp": Int(Date().timeIntervalSince1970) + 86400])).sig"
    }

    private func launch(spanish: Bool = false, _ env: [String: String]) -> XCUIApplication {
        let app = spanish ? XCUIApplication.spanish() : XCUIApplication.english()
        app.launchEnvironment["VMK_DEBUG_RESET"] = "1"
        app.launchEnvironment["VMK_DEBUG_ID_TOKEN"] = token(); app.launchEnvironment["VMK_DEBUG_REFRESH_TOKEN"] = "fake"; app.launchEnvironment["VMK_DEBUG_FAKE_LIBRARY"] = "1"
        if let dir = ProcessInfo.processInfo.environment["VMK_DEBUG_IMAGE_DIR"] { app.launchEnvironment["VMK_DEBUG_IMAGE_DIR"] = dir }
        if ProcessInfo.processInfo.environment["VMK_SHOTS_MODE"] == "dark" { app.launchArguments += ["-AppleInterfaceStyle", "Dark"] }
        for (k, v) in env { app.launchEnvironment[k] = v }
        app.launch()
        return app
    }

    private func el(_ app: XCUIApplication, _ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }
    private func tiles(_ app: XCUIApplication) -> XCUIElementQuery { app.descendants(matching: .any).matching(identifier: "mediaTile") }

    private func shot(_ app: XCUIApplication, _ name: String) {
        guard let dir = ProcessInfo.processInfo.environment["VMK_SHOTS_DIR"], !dir.isEmpty else { return }
        sleep(1)
        let suffix = ProcessInfo.processInfo.environment["VMK_SHOTS_MODE"] == "dark" ? "_dark" : ""
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: URL(fileURLWithPath: dir).appendingPathComponent("audit-\(name)\(suffix).png"))
    }

    // MARK: Media

    /// Select, three photos, "Make a video · 3"; Delete asks nothing, shows "Deleted · Undo", and Undo brings the photos back (rule 8).
    func testMediaSelectionDeleteCanBeUndone() {
        let app = launch(["VMK_DEBUG_TAB": "1"])
        XCTAssertTrue(tiles(app).firstMatch.waitForExistence(timeout: 20))
        let before = tiles(app).count
        app.buttons["selectButton"].tap()
        XCTAssertFalse(app.buttons["tabMedia"].exists, "the tab bar steps aside while selecting")
        XCTAssertFalse(app.buttons["makeVideoFromSelection"].isEnabled, "nothing selected yet")
        XCTAssertEqual(app.buttons["selectAll"].label.hasPrefix("Select all"), true, "the bar says Select all, as the mockup does")
        shot(app, "media_select_empty")
        for i in 0..<3 { tiles(app).element(boundBy: i).tap() }
        XCTAssertEqual(el(app, "selectionTitle").label, "3 selected")
        shot(app, "media_selected3")
        app.buttons["deleteSelection"].tap()
        XCTAssertFalse(app.sheets.firstMatch.waitForExistence(timeout: 1) || app.alerts.firstMatch.exists, "no confirm dialog")
        XCTAssertTrue(el(app, "undoToast").waitForExistence(timeout: 5), "Deleted · Undo")
        XCTAssertTrue(app.staticTexts["Deleted"].exists)
        XCTAssertEqual(tiles(app).count, before - 3, "the photos left the grid at once")
        shot(app, "media_deleted_undo")
        app.buttons["undoToastAction"].tap()
        XCTAssertTrue(el(app, "undoToast").waitForNonExistence(timeout: 3))
        XCTAssertGreaterThanOrEqual(tiles(app).count, before, "Undo brings them back")
    }

    /// The tab bar never rides above the keyboard, search has a Cancel, and Select puts the keyboard away so the selection bar sits at the bottom.
    func testSearchKeyboardNeverLiftsTheBars() {
        let app = launch(["VMK_DEBUG_TAB": "1"])
        XCTAssertTrue(tiles(app).firstMatch.waitForExistence(timeout: 20))
        let barY = app.buttons["newVideo"].frame.midY
        el(app, "mediaSearch").tap()
        XCTAssertTrue(app.buttons["searchCancel"].waitForExistence(timeout: 5), "Cancel sits beside the field while it has the focus")
        if app.keyboards.firstMatch.waitForExistence(timeout: 3) {
            XCTAssertFalse(app.buttons["newVideo"].isHittable && app.buttons["newVideo"].frame.midY < barY - 40, "the New video button did not ride up over the grid")
        }
        shot(app, "media_search_keyboard")
        app.buttons["selectButton"].tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5), "Select puts the keyboard away")
        let bar = app.buttons["makeVideoFromSelection"]
        XCTAssertTrue(bar.waitForExistence(timeout: 5))
        XCTAssertGreaterThan(bar.frame.midY, app.windows.firstMatch.frame.height * 0.8, "the selection bar is at the bottom, not mid-screen")
        shot(app, "media_select_after_search")
        app.buttons["selectCancel"].tap()
        el(app, "mediaSearch").tap()
        app.buttons["searchCancel"].tap()
        XCTAssertTrue(app.buttons["searchCancel"].waitForNonExistence(timeout: 3))
    }

    /// The viewer uses the app's own controls: one close, one primary with the play-sparkle, quiet icons; delete can be undone.
    func testPhotoViewerControlsAndUndo() {
        let app = launch(["VMK_DEBUG_TAB": "1"])
        XCTAssertTrue(tiles(app).firstMatch.waitForExistence(timeout: 20))
        tiles(app).firstMatch.tap()
        XCTAssertTrue(app.buttons["viewerMakeVideo"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.buttons["viewerMakeVideo"].label, "Make a video")
        XCTAssertGreaterThanOrEqual(app.buttons["viewerClose"].frame.width, 44, "a 44 pt close button")
        XCTAssertTrue(el(app, "viewerPosition").exists)
        shot(app, "viewer")
        el(app, "viewerMore").tap()
        XCTAssertTrue(app.buttons["viewerInfo"].waitForExistence(timeout: 5))
        shot(app, "viewer_more")
        app.buttons["viewerInfo"].tap()
        XCTAssertTrue(app.buttons["photoInfoClose"].waitForExistence(timeout: 5))
        shot(app, "viewer_info")
        app.buttons["photoInfoClose"].tap()
        let position = el(app, "viewerPosition").label
        app.buttons["viewerDelete"].tap()
        XCTAssertFalse(app.alerts.firstMatch.waitForExistence(timeout: 1), "no confirm dialog")
        XCTAssertTrue(el(app, "undoToast").waitForExistence(timeout: 5))
        XCTAssertNotEqual(el(app, "viewerPosition").label, position, "one photo fewer in the pages")
        shot(app, "viewer_deleted_undo")
        let undo = app.buttons.matching(identifier: "undoToastAction")      // the viewer's own toast is the one on top
        undo.element(boundBy: undo.count - 1).tap()
        XCTAssertEqual(el(app, "viewerPosition").label, position, "Undo puts it back where it was")
        app.buttons["viewerClose"].tap()
        XCTAssertTrue(app.buttons["tabMedia"].waitForExistence(timeout: 5))
    }

    /// Collections live behind More. Their pages use the app's top bar, the tab bar is hidden on every pushed page, an empty collection offers
    /// "Add photos", and deleting a collection can be undone.
    func testCollectionsPagesAndUndo() {
        let app = launch(["VMK_DEBUG_TAB": "1"])
        XCTAssertTrue(tiles(app).firstMatch.waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts["Collections"].exists, "Media goes straight to the month grid")
        app.buttons["mediaMore"].tap()
        shot(app, "media_more_menu")
        app.buttons["seeAllCollections"].tap()
        let rows = app.descendants(matching: .any).matching(identifier: "collectionRow")
        XCTAssertTrue(rows.firstMatch.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["tabMedia"].exists, "the tab bar is hidden on a pushed page")
        XCTAssertFalse(app.navigationBars.firstMatch.exists, "the app's own top bar, not the system's")
        let count = rows.count
        shot(app, "collections_list")
        rows.firstMatch.tap()
        XCTAssertTrue(el(app, "collectionTitle").waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["tabMedia"].exists)
        if app.buttons["collectionAddPhotos"].waitForExistence(timeout: 5) { XCTAssertEqual(app.buttons["collectionAddPhotos"].label, "Add photos", "an empty collection has a next step") }
        shot(app, "collection_detail")
        el(app, "collectionMore").tap()
        XCTAssertTrue(app.buttons["deleteCollection"].waitForExistence(timeout: 5))
        shot(app, "collection_more_menu")
        app.buttons["deleteCollection"].tap()
        XCTAssertFalse(app.alerts.firstMatch.waitForExistence(timeout: 1), "no confirm dialog")
        XCTAssertTrue(el(app, "undoToast").waitForExistence(timeout: 5), "back on the list with Deleted · Undo")
        XCTAssertEqual(rows.count, count - 1)
        shot(app, "collection_deleted_undo")
        app.buttons["undoToastAction"].tap()
        XCTAssertTrue(el(app, "undoToast").waitForNonExistence(timeout: 3))
        XCTAssertEqual(rows.count, count, "Undo brings the collection back")
        app.buttons["backButton"].tap()
        XCTAssertTrue(app.buttons["tabMedia"].waitForExistence(timeout: 5), "the tab bar is back on the tab's root")
    }

    /// Storage and Add to collection are opaque sheets with the app's header; the storage bar says what it measures.
    func testStorageAndAddToCollectionSheets() {
        let app = launch(["VMK_DEBUG_TAB": "1"])
        XCTAssertTrue(tiles(app).firstMatch.waitForExistence(timeout: 20))
        app.buttons["mediaMore"].tap()
        app.buttons.matching(NSPredicate(format: "label == 'Storage'")).firstMatch.tap()
        XCTAssertTrue(app.buttons["storageClose"].waitForExistence(timeout: 5))
        shot(app, "media_storage_sheet")
        app.buttons["storageClose"].tap()
        app.buttons["selectButton"].tap()
        tiles(app).firstMatch.tap()
        app.buttons["addToCollection"].tap()
        XCTAssertTrue(app.buttons["addToCollectionClose"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["newCollectionInSheet"].exists)
        shot(app, "media_add_to_collection")
        app.buttons["addToCollectionClose"].tap()
    }

    // MARK: Create

    /// Photo icon, Media, photos, "Add · 2": no explainer sheet. Closing Create keeps the draft.
    func testPhotoMenuOpensThePickersDirectlyAndTheDraftIsKept() {
        let app = launch(["VMK_DEBUG_CREATE": "empty", "VMK_DEBUG_BALANCE": "12"])
        XCTAssertTrue(app.buttons["photoButton"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.buttons["photoButton"].label, "Add photos")
        app.buttons["photoButton"].tap()
        XCTAssertTrue(app.buttons["photosMenuItem"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["photosMenuItem"].label, "Photo library"); XCTAssertEqual(app.buttons["mediaMenuItem"].label, "Media")
        shot(app, "create_photo_menu")
        app.buttons["mediaMenuItem"].tap()
        XCTAssertTrue(tiles(app).firstMatch.waitForExistence(timeout: 10))
        XCTAssertEqual(el(app, "pickerTitle").label, "Media")
        tiles(app).element(boundBy: 0).tap(); tiles(app).element(boundBy: 1).tap()
        XCTAssertEqual(app.buttons["addSelected"].label, "Add · 2")
        shot(app, "create_media_picker")
        app.buttons["addSelected"].tap()
        XCTAssertTrue(el(app, "photosNote").waitForExistence(timeout: 5))
        XCTAssertTrue(el(app, "photosNote").label.contains("2 photos"), "one count")
        let field = el(app, "composerField")
        field.tap(); field.typeText("My week in Lisbon")
        shot(app, "create_with_library_photos")
        app.buttons["createCancel"].tap()
        XCTAssertFalse(app.buttons["Discard"].waitForExistence(timeout: 1), "closing never asks")
        XCTAssertTrue(app.buttons["newVideo"].waitForExistence(timeout: 5))
        app.buttons["newVideo"].tap()
        XCTAssertEqual(el(app, "composerField").value as? String, "My week in Lisbon", "the draft is there again")
        XCTAssertTrue(el(app, "photosNote").label.contains("2 photos"))
    }

    /// "Skip all" starts the video in one tap (three questions no longer cost three taps and a summary).
    func testSkipAllStartsTheVideoAtOnce() {
        let app = launch(["VMK_DEBUG_CREATE": "q1", "VMK_DEBUG_BALANCE": "12"])
        XCTAssertTrue(app.buttons["skipQuestion"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.buttons["skipQuestion"].label, "Skip all")
        XCTAssertTrue(el(app, "questionProgress").exists, "the dots are one accessibility element")
        app.buttons["skipQuestion"].tap()
        XCTAssertFalse(app.buttons["summaryCreate"].waitForExistence(timeout: 2), "nothing answered: no summary")
        let card = app.descendants(matching: .any).matching(NSPredicate(format: "identifier == 'runningRow' OR identifier == 'pendingRow'")).firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 30), "the video is being made")
    }

    /// One answer, then Skip all: the summary shows what was said, sized to its content, with Close on the X.
    func testAnAnswerThenSkipAllShowsTheSummary() {
        let app = launch(["VMK_DEBUG_CREATE": "q1", "VMK_DEBUG_BALANCE": "12"])
        XCTAssertTrue(app.buttons["answer-kids"].waitForExistence(timeout: 20))
        app.buttons["answer-kids"].tap()
        XCTAssertTrue(app.buttons["answer-calm"].waitForExistence(timeout: 5))
        app.buttons["skipQuestion"].tap()
        XCTAssertTrue(app.buttons["summaryCreate"].waitForExistence(timeout: 5), "something was answered: the summary shows it")
        XCTAssertEqual(app.buttons["summaryClose"].label, "Close")
        XCTAssertEqual(app.buttons.matching(identifier: "summaryChip").count, 1)
    }

    /// Paused: the title says when to come back, the one primary is OK (editing cannot lift a pause), and no line repeats the title.
    func testPausedSheetOffersOKAndSaysWhen() {
        let app = launch(["VMK_DEBUG_CREATE": "paused", "VMK_DEBUG_BALANCE": "12"])
        XCTAssertTrue(el(app, "kindTitle").waitForExistence(timeout: 20))
        XCTAssertEqual(el(app, "kindTitle").label, "Paused · try again in about 1 hour")
        XCTAssertFalse(el(app, "kindMessage").exists, "no message that repeats the title")
        XCTAssertFalse(app.buttons["editRequest"].exists)
        XCTAssertEqual(app.buttons["pausedOK"].label, "OK")
        app.buttons["pausedOK"].tap()
        XCTAssertTrue(el(app, "kindTitle").waitForNonExistence(timeout: 5))
        XCTAssertEqual(el(app, "composerField").value as? String, "How bees make honey, explained for kids", "the form is intact underneath")
    }

    /// Cannot afford the chosen length but can afford a shorter one: the fix is on the button, and one tap makes that video.
    func testTheAffordableLengthIsOnTheCreateButton() {
        let app = launch(["VMK_DEBUG_CREATE": "filled", "VMK_DEBUG_BALANCE": "2", "VMK_DEBUG_DEFAULT_MINUTES": "3"])
        XCTAssertTrue(app.buttons["sendButton"].waitForExistence(timeout: 20))
        XCTAssertEqual(app.buttons["sendButton"].label, "Create · 2 minutes")
        XCTAssertTrue(el(app, "notEnoughCredits").exists)
        XCTAssertFalse(app.buttons["fixChip"].exists, "the fix is on the button, not a second control")
        app.buttons["sendButton"].tap()
        XCTAssertTrue(el(app, "createCapsule").waitForExistence(timeout: 5) || el(app, "runningRow").waitForExistence(timeout: 20), "one tap starts the 2 minute video")
    }

    /// Every format tile says its ratio, and a beta format says so in words.
    func testFormatTilesAlwaysShowTheirRatio() {
        let app = launch(["VMK_DEBUG_CREATE": "options", "VMK_DEBUG_BALANCE": "12"])
        XCTAssertTrue(app.buttons["optionsDone"].waitForExistence(timeout: 20))
        for _ in 0..<3 where !app.buttons["aspect-4:5"].isHittable { app.swipeUp() }
        for ratio in ["16:9", "9:16", "1:1", "4:5"] { XCTAssertTrue(app.buttons["aspect-\(ratio)"].exists, ratio) }
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == 'Beta'")).count >= 1 || app.buttons["aspect-9:16"].label.contains("beta"))
        XCTAssertEqual(app.switches["subtitlesToggle"].exists || el(app, "subtitlesToggle").exists, true)
        shot(app, "options_bottom")
    }

    // MARK: Settings, sheets, the tab bar, orientation

    /// Settings: one row style, the Photos sentence is always in view (no clipped popover), and Sign out asks nothing.
    func testSettingsRowsAndSignOutWithoutAQuestion() {
        let app = launch(["VMK_DEBUG_SHEET": "settings", "VMK_DEBUG_FAKE_VIDEOS": "bar"])
        XCTAssertTrue(app.buttons["signOutButton"].waitForExistence(timeout: 20))
        XCTAssertTrue(el(app, "accountEmail").label.contains("demo@example.com"), "the whole address")
        XCTAssertTrue(el(app, "photosInfo").exists, "the sentence about photos is on the page")
        XCTAssertFalse(app.navigationBars.firstMatch.exists)
        for _ in 0..<3 where !app.buttons["deleteAccountButton"].isHittable { app.swipeUp() }
        XCTAssertTrue(app.buttons["termsLink"].exists && app.buttons["privacyLink"].exists && app.buttons["supportLink"].exists)
        shot(app, "settings_bottom")
        for _ in 0..<3 where !app.buttons["signOutButton"].isHittable { app.swipeDown() }
        app.buttons["signOutButton"].tap()
        XCTAssertFalse(app.sheets.buttons.firstMatch.waitForExistence(timeout: 1), "no confirm dialog")
        XCTAssertTrue(app.buttons["signInButton"].waitForExistence(timeout: 10), "signed out at once")
    }

    /// The player's Info sheet: About (made with AI, captions), then the description, one Copy button. More holds New video, feedback and Delete.
    func testInfoSheetAndMoreMenu() throws {
        guard let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"], !file.isEmpty else { throw XCTSkip("needs TEST_RUNNER_VMK_DEBUG_PLAYBACK_FILE (a local mp4)") }
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar", "VMK_DEBUG_OPEN": "v3", "VMK_DEBUG_PLAYBACK_FILE": file])
        XCTAssertTrue(app.buttons["infoButton"].waitForExistence(timeout: 20))
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label ==[c] 'make another'")).firstMatch.exists, "no header over the remix chips")
        XCTAssertEqual(app.buttons["remix-short"].label, "As a Short"); XCTAssertEqual(app.buttons["remix-language"].label, "In Spanish"); XCTAssertEqual(app.buttons["remix-cut30"].label, "30 seconds")
        app.buttons["infoButton"].tap()
        XCTAssertTrue(el(app, "infoAbout").waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Made with AI"].exists && app.staticTexts["Chapters"].exists)
        XCTAssertTrue(app.buttons["copyDescription"].exists)
        shot(app, "player_info_sheet")
        app.buttons["infoClose"].tap()
        el(app, "moreButton").tap()
        XCTAssertTrue(app.buttons["deleteVideo"].waitForExistence(timeout: 5))
        shot(app, "player_more_menu")
    }

    /// The floating bar is a tab bar to VoiceOver, with the selected trait on the current tab, and the app stays upright when the phone is turned.
    func testTabBarTraitsAndPortraitOnly() {
        let app = launch(["VMK_DEBUG_FAKE_VIDEOS": "bar"])
        XCTAssertTrue(app.buttons["tabVideos"].waitForExistence(timeout: 20))
        XCTAssertTrue(app.tabBars["tabBar"].exists || el(app, "tabBar").exists, "the two tabs sit in a tab-bar container")
        XCTAssertTrue(app.buttons["tabVideos"].isSelected && !app.buttons["tabMedia"].isSelected)
        XCUIDevice.shared.orientation = .landscapeLeft
        sleep(2)
        let window = app.windows.firstMatch
        XCTAssertGreaterThan(window.frame.height, window.frame.width, "iPhone is portrait: turning the phone does not turn the app")
        shot(app, "landscape_stays_portrait")
        XCUIDevice.shared.orientation = .portrait
    }
}
