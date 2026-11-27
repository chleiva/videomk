import Foundation
import Observation
import VideoMKCore

@MainActor @Observable
final class AppModel {
    enum Phase: Equatable { case launching, notConfigured, signedOut, signedIn(email: String?) }
    enum LoadState: Equatable { case idle, loading, loaded, failed(String) }

    private(set) var phase: Phase = .launching
    private(set) var videos: [VideoItem] = []
    private(set) var loadState: LoadState = .idle
    private(set) var pending: [PendingVideo] = []
    private(set) var wallet: WalletInfo?
    private(set) var completions = 0                       // bumps when a video finishes: drives the success haptic
    private var stageSince: [String: (stage: VideoStatus.Stage, since: Date)] = [:]
    private var briefs: [String: String] = [:]             // what the user asked for, shown while the server has no title yet
    private var minutes: [String: Double] = [:]
    private var photoData: [String: [Data]] = [:]          // photos waiting to be uploaded, kept until the video is accepted (so a retry needs no new selection)
    private var photoMeta: [String: [PhotoMeta?]] = [:]       // capture time / approximate place per photo, same order as photoData
    private var uploadedMedia: [String: [Int: String]] = [:]   // photos already uploaded per pending request, so a retry sends only the rest
    private var libraryIDs: [String: [String]] = [:]      // library photo ids per pending request (kept for a retry)
    private(set) var media: MediaModel?
    private(set) var createModel: CreateModel                                 // the Create screen's state
    private(set) var userID: String?
    let rating = RatingPrompt(version: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0")   // on-device rating logic (docs/FEEDBACK.md)
    var isPlayingVideo = false                             // a video is playing right now: the rating question never opens over it
    var requestCredits = false                              // "Add credits" in Create asks the home screen to show the wallet
    var createRequested = false                             // "Make a video from this" in Media opens Create on the home screen
    var createProblem: CreateProblem?                       // generate answered blocked or paused after Create closed
    private var linkStamp: [String: Date] = [:]            // when each video's picture links were last taken (they are swapped quietly before they expire)
    private var intakeBriefs: [String: [String: String]] = [:]
    private var deckIDs: [String: String] = [:]            // the ready presentation per pending request (kept for a retry; the server deletes it when the video starts)
    private var deckPrompts: [String: String] = [:]       // what the person typed (who it is for); the row's title may be the file name instead
    private var deckMinutes: [String: Bool] = [:]          // whether the person chose a length (only then `target_minutes` is sent)
    private var deckVideos: Set<String> = []               // videos made from a presentation: "Try again" cannot reuse the (deleted) deck

    struct CreateProblem: Identifiable, Equatable { let id = UUID(); let message: String; let retryAfter: Int?; let paused: Bool; let prompt: String }
    var selectedTab = 0                                    // 0 videos, 1 media
    var tabBarHidden = false                               // a video is open: the floating bar steps aside
    var composerDraft: String?                             // text to put in the composer (Try again on a failed video)
    var composerLibrary: [LibraryPhoto] = []               // library photos chosen for the next video
    var signInError: String?
    var isSigningIn = false
    var signingInWith: SignInChoice?                        // which button shows the spinner
    let authOptions: AuthOptions
    /// Set once a deletion was accepted: the signed-out app shows "Your account is being deleted" first. Never persisted.
    private(set) var deletionNotice: DeletionNotice?

    struct DeletionNotice: Equatable {
        var apple: AppleLink
        var assumed: Bool
        fileprivate(set) var revokeToken: String?     // memory only, for the Apple step; dropped when the screen is dismissed
    }

    private let auth: AuthService?
    private let api: APIClient?
    private var account: (any AccountAPI)?
    private var deletionAuth: (any DeletionAuth)?
    private var fakeRevokeStatus: AppleRevoke.Status?  // debug fixtures only
    private let web = WebAuthenticator()
    let config: AppConfig?

    init(config: AppConfig? = AppConfig.fromBundle(), store: any TokenStore = KeychainTokenStore()) {
        self.config = config
        var options = AuthOptions.fromBundle()
        #if DEBUG
        let env = ProcessInfo.processInfo.environment   // screenshots and UI tests: show the buttons without changing the build settings
        if env["VMK_DEBUG_AUTH_APPLE"] == "1" { options.apple = true }
        if env["VMK_DEBUG_AUTH_GOOGLE"] == "1" { options.google = true }
        #endif
        authOptions = options
        guard let config else { auth = nil; api = nil; createModel = CreateModel(api: nil); return }
        let a = AuthService(config: config, store: store)
        auth = a
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
        account = AccountClient(config: config, appVersion: version)
        deletionAuth = LiveDeletionAuth(auth: a, web: web, config: config)
        api = APIClient(config: config, auth: a, appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0")
        media = api.map { MediaModel(api: LibraryClient(api: $0)) }
        createModel = CreateModel(api: api)
        #if DEBUG
        if ProcessInfo.processInfo.environment["VMK_DEBUG_FAKE_LIBRARY"] == "1" { media = MediaModel(api: FakeLibraryAPI.demo(), fake: true); createModel = CreateModel(api: Self.debugCreateAPI()); userID = "demo-user" }
        selectedTab = Int(ProcessInfo.processInfo.environment["VMK_DEBUG_TAB"] ?? "") ?? 0
        seedDebugScreens()
        configureDebugDeletion()
        #endif
    }

    /// A fresh "Send feedback" form. Fake-library runs (screenshots, UI tests) never reach the real backend.
    func makeFeedback(_ context: FeedbackContext) -> FeedbackComposer {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
        var feedbackAPI: (any FeedbackAPI)? = api
        #if DEBUG
        if media?.isFake == true { feedbackAPI = FakeFeedbackAPI() }
        #endif
        return FeedbackComposer(context: context, api: feedbackAPI, version: version)
    }

    var hasRunningVideos: Bool { videos.contains { $0.status.isRunning } || pending.contains { $0.state == .sending } }
    var entries: [LibraryEntry] { LibraryMerge.entries(pending: pending, server: videos) }

    func refreshWallet() async {
        guard let api else { return }
        #if DEBUG
        if media?.isFake == true { return }
        #endif
        if let w = try? await api.wallet(), w != wallet { wallet = w }
    }

    func brief(for id: String) -> String? { briefs[id] }
    func stage(for id: String) -> (stage: VideoStatus.Stage, since: Date)? { stageSince[id] }
    func requestedMinutes(for id: String) -> Double { minutes[id] ?? CreateOptions.defaultMinutes }
    func video(_ id: String) -> VideoItem? { videos.first { $0.id == id } }

    // MARK: session

    private var started = false

    /// Once per launch. The root view's `.task` can run again (a rotation or a full-screen presentation can rebuild it); a second start must
    /// never re-run the session setup (in debug builds that includes the test sign-out).
    func start() async {
        guard let auth else { phase = .notConfigured; return }
        guard !started else { return }
        started = true
        #if DEBUG
        await seedDebugSession(auth)
        #endif
        phase = await auth.isSignedIn ? .signedIn(email: await auth.email) : .signedOut
        if userID == nil { userID = (try? await auth.authorization())?.userID }
    }

    private static let signedOutKey = "vmk.explicitSignOut"

    /// `provider` nil is the hosted page with email and password. Social providers go straight to Apple or Google through the same
    /// authorize request (code + PKCE + state); the one-off Cognito account-link error is retried once, see `SignInFlow`.
    func signIn(_ provider: SocialProvider? = nil) async {
        guard let auth, let config, !isSigningIn else { return }
        isSigningIn = true; signInError = nil
        signingInWith = provider.map { $0 == .apple ? .apple : .google } ?? .email
        defer { isSigningIn = false; signingInWith = nil }
        let ephemeral = SignInFlow.useEphemeralSession(afterExplicitSignOut: UserDefaults.standard.bool(forKey: Self.signedOutKey))
        do {
            try await SignInFlow.run {
                let callback = try await web.authenticate(url: await auth.beginSignIn(provider: provider), callbackScheme: config.callbackScheme, ephemeral: ephemeral)
                try await auth.completeSignIn(callback: callback)
            }
            UserDefaults.standard.removeObject(forKey: Self.signedOutKey)
            phase = .signedIn(email: await auth.email)
            userID = (try? await auth.authorization())?.userID
        } catch {
            signInError = SignInFlow.message(for: error)   // nil when the person just closed the sheet
        }
    }

    /// The language row in Settings: applied at once (no restart). The server's capability labels are fetched again in the new language.
    func setLanguage(_ choice: LanguageChoice) {
        Localization.shared.setChoice(choice)
        Task { await createModel.loadCapabilities(userID: userID) }
    }

    func signOut() async {
        UserDefaults.standard.set(true, forKey: Self.signedOutKey)
        await auth?.signOut()
        await media?.wipe()      // another account must never see this one's cached photos or queued uploads
        createModel.deck.wipe()  // a presentation copy left in the temp folder
        composerLibrary = []; libraryIDs = [:]
        wallet = nil; videos = []; pending = []; deckIDs = [:]; deckMinutes = [:]; deckPrompts = [:]; deckVideos = []; photoData = [:]; photoMeta = [:]; stageSince = [:]; briefs = [:]; minutes = [:]; loadState = .idle
        phase = .signedOut
    }

    // MARK: account deletion (docs/ACCOUNT_DELETION.md)

    func makeDeletionFlow() -> AccountDeletionFlow? {
        guard let account, let deletionAuth else { return nil }
        return AccountDeletionFlow(auth: deletionAuth, api: account)
    }

    /// The deletion was accepted (202). Clears everything on this device, signs out through the normal path (so the next web sign-in is private, never silent)
    /// and shows the confirmation. Nothing here can fail the deletion: it is already under way on the server.
    func finishDeletion(_ accepted: DeletionAccepted) async {
        await signOut()                                   // tokens, explicit-sign-out flag, Media caches and queue, in-memory lists
        let fm = FileManager.default
        let caches = fm.urls(for: .cachesDirectory, in: .userDomainMask)[0], support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        LocalWipe.clearContents(of: [caches.appendingPathComponent("VideoMKMedia"), caches.appendingPathComponent("VideoMKVideoImages"),
                                     support.appendingPathComponent("VideoMKUploadQueue"), DeckTempStore.defaultDirectory, fm.temporaryDirectory])
        await media?.wipe()                               // again: recreates the empty folders its stores expect
        StableImageStore.shared.removeAll()
        URLCache.shared.removeAllCachedResponses()
        HTTPCookieStorage.shared.removeCookies(since: .distantPast)
        LocalWipe.resetDefaults(.standard, domain: Bundle.main.bundleIdentifier ?? "com.videomk.app", then: [Self.signedOutKey: true])
        createModel = CreateModel(api: api)               // drafts and remembered choices
        composerDraft = nil; createProblem = nil; requestCredits = false; createRequested = false; selectedTab = 0; userID = nil; signInError = nil
        deletionNotice = DeletionNotice(apple: accepted.apple, assumed: accepted.assumed, revokeToken: accepted.idToken)
    }

    func dismissDeletionNotice() { deletionNotice = nil }

    /// The optional Apple step, only offered when the server said `revoke_available`. Never blocks anything; every failure ends in the manual steps.
    func revokeApple() async -> AppleRevoke.Status {
        guard let config, let account, let token = deletionNotice?.revokeToken else { return .failed }
        #if DEBUG
        if let fake = fakeRevokeStatus { try? await Task.sleep(for: .seconds(1)); return fake }
        #endif
        do {
            let url = try await account.appleRevokeURL(idToken: token)
            let back = try await web.authenticate(url: url, callbackScheme: config.callbackScheme, ephemeral: false)
            return AppleRevoke.status(of: back, scheme: config.callbackScheme)
        } catch AuthError.cancelled { return .cancelled }
        catch { return .failed }
    }

    // MARK: library

    func refresh() async {
        guard let api else { return }
        #if DEBUG
        if media?.isFake == true { loadState = .loaded; return }      // fake-library runs never call the real backend (its 401 would sign the demo session out)
        #endif
        if videos.isEmpty { loadState = .loading }
        do {
            Task { await refreshWallet() }  // credits load alongside the list
            let fresh = try await api.listVideos()
            track(old: videos, new: fresh)
            // Every list call brings freshly signed picture links for every video: nothing is replaced unless something visible changed.
            let merged = VideoListMerge.merge(old: videos, fresh: fresh, linkStamp: &linkStamp)
            if merged.changed { videos = merged.items }
            let stillPending = LibraryMerge.stillPending(pending, server: fresh)
            if stillPending != pending { pending = stillPending }
            if loadState != .loaded { loadState = .loaded }
        } catch is CancellationError {
        } catch let e as APIError where e == .unauthorized {
            await signOut()
        } catch let e as AuthError where e == .signedOut {
            await signOut()
        } catch {
            // keep what we have on screen; only a first load shows a full-screen error
            if videos.isEmpty { loadState = .failed((error as? APIError)?.message ?? tr("videos.load_failed")) } else { loadState = .loaded }
        }
    }

    /// Remembers when each running video entered its current stage (for the progress estimate) and notices completions.
    private func track(old: [VideoItem], new: [VideoItem]) {
        let before = Dictionary(uniqueKeysWithValues: old.map { ($0.id, $0.status) })
        for v in new {
            if case .running(let s) = v.status {
                if stageSince[v.id]?.stage != s { stageSince[v.id] = (s, .now) }
            } else {
                stageSince[v.id] = nil
                if let b = before[v.id], b.isRunning, v.status == .complete { completions += 1 }
            }
        }
    }

    // MARK: ask for a video without leaving the home screen

    /// Adds a placeholder row immediately and sends the request in the background; the user can keep browsing or ask for more.
    func submit(brief: String, options: CreateOptions, photos: [Data] = [], meta: [PhotoMeta?] = [], libraryMedia: [String] = [], intake: [String: String]? = nil, deckID: String? = nil, deckName: String? = nil, sendsMinutes: Bool = true) {
        let title = Brief.normalized(brief).isEmpty && deckID != nil ? tr("deck.video_title", deckName ?? "") : Brief.normalized(brief)
        let p = PendingVideo(brief: title, options: options, photoCount: photos.count, state: photos.isEmpty ? .sending : .uploading(done: 0, total: photos.count))
        if !photos.isEmpty { photoData[p.id] = photos; photoMeta[p.id] = meta }
        if !libraryMedia.isEmpty { libraryIDs[p.id] = libraryMedia }
        if let intake, !intake.isEmpty { intakeBriefs[p.id] = intake }
        if let deckID { deckIDs[p.id] = deckID; deckMinutes[p.id] = sendsMinutes; deckPrompts[p.id] = Brief.normalized(brief) }
        pending.insert(p, at: 0)
        Task { await send(p.id) }
    }

    func retry(_ id: String) {
        guard let i = pending.firstIndex(where: { $0.id == id }) else { return }
        pending[i].state = pending[i].photoCount > 0 ? .uploading(done: uploadedMedia[id]?.count ?? 0, total: pending[i].photoCount) : .sending
        Task { await send(id) }
    }

    /// "Try again" on a video the server could not finish: ask for the same thing again when we remember it, else put its title back in the composer.
    func tryAgain(_ video: VideoItem) {
        if deckVideos.contains(video.id) { createRequested = true; return }       // the deck was used up: start again from Create
        if let brief = briefs[video.id], Brief.isValid(brief) {
            submit(brief: brief, options: CreateOptions(minutes: minutes[video.id] ?? CreateOptions.defaultMinutes))
        } else { composerDraft = video.displayTitle }
    }

    func dismissPending(_ id: String) { pending.removeAll { $0.id == id }; deckIDs[id] = nil; deckMinutes[id] = nil; deckPrompts[id] = nil; photoData[id] = nil; photoMeta[id] = nil; uploadedMedia[id] = nil; libraryIDs[id] = nil }

    private func setProgress(_ id: String, done: Int, total: Int) {
        if let i = pending.firstIndex(where: { $0.id == id }), case .uploading = pending[i].state { pending[i].state = .uploading(done: done, total: total) }
    }

    private func send(_ id: String) async {
        guard let p = pending.first(where: { $0.id == id }) else { return }
        do {
            var media: [String] = []
            if let photos = photoData[id] {
                guard let api else { throw APIError.server }
                media = try await PhotoUploader(api: api).upload(photos, already: uploadedMedia[id] ?? [:]) { [weak self] done, total in
                    Task { @MainActor in self?.setProgress(id, done: done, total: total) }
                }
                if let i = pending.firstIndex(where: { $0.id == id }) { pending[i].state = .sending }
            }
            #if DEBUG
            if self.media?.isFake == true, deckIDs[id] != nil { acceptFakeDeck(p); return }        // fake runs never reach the backend
            #endif
            let videoID = try await create(brief: deckIDs[id] != nil ? (deckPrompts[id] ?? "") : p.brief, requestID: p.id, options: p.options, media: media, mediaMeta: PhotoMetaReader.mediaMeta(ids: media, metas: photoMeta[id] ?? []), libraryMedia: libraryIDs[id] ?? [], intake: intakeBriefs[id], deck: deckIDs[id], sendMinutes: deckMinutes[id] ?? true)
            if deckIDs[id] != nil { deckVideos.insert(videoID) }
            deckIDs[id] = nil; deckMinutes[id] = nil; deckPrompts[id] = nil
            photoData[id] = nil; photoMeta[id] = nil; uploadedMedia[id] = nil; libraryIDs[id] = nil
            briefs[videoID] = p.brief; minutes[videoID] = p.options.minutes
            if let i = pending.firstIndex(where: { $0.id == id }) { pending[i].state = .accepted(videoID: videoID) }
            await refresh()  // also re-reads the credits the video just used
        } catch let e as PhotoUploadFailure {
            uploadedMedia[id] = e.uploaded
            if let i = pending.firstIndex(where: { $0.id == id }) { pending[i].state = .failed(e.message) }
        } catch let e as APIError where { if case .blocked = e { return true }; if case .paused = e { return true }; return false }() {
            // the safety check (or a pause) stopped it at the last step: nothing was charged; the kind sheet explains and offers Edit request
            if let i = pending.firstIndex(where: { $0.id == id }) { pending[i].state = .failed(e.message) }
            var retry: Int? = nil; var isPaused = false
            if case .paused(_, let t) = e { retry = t; isPaused = true }
            createProblem = CreateProblem(message: e.message, retryAfter: retry, paused: isPaused, prompt: p.brief)
        } catch let e as APIError {
            if case .insufficientCredits = e { await refreshWallet() }
            if let i = pending.firstIndex(where: { $0.id == id }) { pending[i].state = .failed(e.message) }
        } catch {
            if let i = pending.firstIndex(where: { $0.id == id }) { pending[i].state = .failed(APIError.server.message) }
        }
    }

    /// Polls while anything is running; ends when the view disappears (task cancelled) or everything has settled.
    func pollWhileRunning() async {
        while !Task.isCancelled, hasRunningVideos {
            try? await Task.sleep(for: .seconds(4))
            if Task.isCancelled { break }
            await refresh()
        }
    }

    // MARK: create / play

    func create(brief: String, requestID: String, options: CreateOptions, media: [String] = [], mediaMeta: [String: PhotoMeta] = [:], libraryMedia: [String] = [], intake: [String: String]? = nil, deck: String? = nil, sendMinutes: Bool = true) async throws -> String {
        guard let api else { throw APIError.server }
        do { return try await api.startGeneration(prompt: brief, clientRequestID: requestID, options: options, media: media, mediaMeta: mediaMeta, libraryMedia: libraryMedia, brief: intake, deck: deck, sendMinutes: sendMinutes) }
        catch let e as AuthError where e == .signedOut { await signOut(); throw APIError.unauthorized }
    }

    func editorSnapshot(_ id: String) async throws -> EditorSnapshot {
        guard let api else { throw APIError.server }
        do { return try await api.editorSnapshot(videoID: id) }
        catch let e as AuthError where e == .signedOut { await signOut(); throw APIError.unauthorized }
    }

    func applyEdits(_ id: String, baseRev: Int, ops: [EditOp], mode: RenderMode) async throws -> Int {
        guard let api else { throw APIError.server }
        do { return try await api.applyEdits(videoID: id, baseRev: baseRev, ops: ops, mode: mode) }
        catch let e as AuthError where e == .signedOut { await signOut(); throw APIError.unauthorized }
    }

    func playback(for id: String) async throws -> PlaybackInfo {
        #if DEBUG
        if media?.isFake == true, let file = ProcessInfo.processInfo.environment["VMK_DEBUG_PLAYBACK_FILE"] { return PlaybackInfo(url: URL(fileURLWithPath: file), description: "Chapters\n0:00 Intro\n\nPhoto credits: Example Photographer on Unsplash") }
        #endif
        guard let api else { throw APIError.server }
        return try await api.playback(videoID: id)
    }

    #if DEBUG
    /// The fake Create backend of screenshot runs: `VMK_DEBUG_DECK` (any value) switches the presentation feature on in its capabilities, and says how the fake server treats the deck.
    static func debugCreateAPI() -> FakeCreateAPI {
        let env = ProcessInfo.processInfo.environment
        var caps = env["VMK_DEBUG_CREATE"]?.hasPrefix("4k") == true ? FakeCreateAPI.fourKCapabilities : FakeCreateAPI.richCapabilities
        var script = FakeDeckScript()
        if let spec = env["VMK_DEBUG_DECK"] { caps = caps.withDeck(); script = FakeDeckScript.parse(spec) }
        return FakeCreateAPI(capabilities: .success(caps), deck: script)
    }

    /// A fake video made from a presentation: first reading the slides, then writing the narration (what the server reports while it plans).
    private func acceptFakeDeck(_ p: PendingVideo) {
        let videoID = "fakedeckvideo-\(p.id.prefix(6))"
        deckVideos.insert(videoID); briefs[videoID] = p.brief; minutes[videoID] = p.options.minutes
        videos.insert(VideoItem(id: videoID, status: .running(.writing), title: p.brief, createdAt: .now, deckStage: .reading), at: 0)
        stageSince[videoID] = (.writing, .now)
        if let i = pending.firstIndex(where: { $0.id == p.id }) { pending[i].state = .accepted(videoID: videoID) }
        deckIDs[p.id] = nil; deckMinutes[p.id] = nil; deckPrompts[p.id] = nil
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(6))
            if let i = videos.firstIndex(where: { $0.id == videoID }) { videos[i] = VideoItem(id: videoID, status: .running(.writing), title: p.brief, createdAt: videos[i].createdAt, deckStage: .writing) }
        }
    }

    /// Screenshots with `VMK_DEBUG_FAKE_LIBRARY=1`: a wallet (`VMK_DEBUG_BALANCE`), a few videos (`VMK_DEBUG_FAKE_VIDEOS=1`) and an upload moment.
    private func seedDebugScreens() {
        guard media?.isFake == true else { return }
        let env = ProcessInfo.processInfo.environment
        if let b = env["VMK_DEBUG_BALANCE"].flatMap(Int.init) { wallet = WalletInfo(balance: b) }
        if env["VMK_DEBUG_FAKE_VIDEOS"] == "many" {
            // 40 videos, every fifth one vertical, one still being made: a long list to flick through
            videos = (0..<40).map { n in
                let vertical = n % 5 == 2
                return VideoItem(id: "v\(n)", status: n == 0 ? .running(.voiceAndVisuals) : n == 7 ? .failed : .complete, title: "Video number \(n)", durationSeconds: 60 + Double(n), createdAt: .now.addingTimeInterval(-Double(n) * 3600),
                                 previewGifURL: URL(string: "fake://\(vertical ? "portrait" : "landscape")/v\(n)"), aspect: vertical ? "9:16" : "16:9", resolution: "1080p")
            }
            briefs["v0"] = "Making a long list"; minutes["v0"] = 3
            stageSince["v0"] = (.voiceAndVisuals, Date().addingTimeInterval(-40))
        }
        if env["VMK_DEBUG_FAKE_VIDEOS"] == "deck" {
            // two videos made from presentations: reading the slides, then writing the narration
            videos = [VideoItem(id: "d1", status: .running(.writing), title: "Presentation: Quarterly review", createdAt: .now, deckStage: .reading),
                      VideoItem(id: "d2", status: .running(.writing), title: "Presentation: Onboarding for new teachers", createdAt: .now.addingTimeInterval(-60), deckStage: .writing)]
            for id in ["d1", "d2"] { briefs[id] = videos.first { $0.id == id }?.title; minutes[id] = 4; deckVideos.insert(id); stageSince[id] = (.writing, Date().addingTimeInterval(-20)) }
        }
        if env["VMK_DEBUG_FAKE_VIDEOS"] == "1" {
            videos = [
                VideoItem(id: "v1", status: .running(.voiceAndVisuals), title: "Golden retriever's first summer", createdAt: .now),
                VideoItem(id: "v2", status: .failed, title: "Thailand highlights", createdAt: .now.addingTimeInterval(-3600)),
                VideoItem(id: "v3", status: .complete, title: "Sunset over Lisbon", durationSeconds: 80, createdAt: .now.addingTimeInterval(-86400)),
            ]
            briefs["v1"] = "Golden retriever's first summer"; minutes["v1"] = 3
            stageSince["v1"] = (.voiceAndVisuals, Date().addingTimeInterval(-40))
        }
        UserDefaults.standard.set(true, forKey: "mediaPrivacyNoteSeen")
        if let scene = env["VMK_DEBUG_UPLOAD_SCENE"] { media?.loadDebugScene(scene) }
        if let scene = env["VMK_DEBUG_ORGANIZE"] { media?.loadDebugOrganize(scene) }
    }

    /// Fake deletion backend. `VMK_DEBUG_FAKE_DELETE` is a comma list: `notlinked|available|off|unknown` (the answer's `apple`), `stale` (sign-in older than 10 minutes),
    /// `offline` (first request lost, retry works), `forbidden`, `server`, `stuck` (server always says sign-in too old), `cancel` (re-auth cancelled), `slow` (3 s pauses).
    /// Fake-library runs always get the fake: a test on the shared QA accounts must never reach the real endpoint.
    /// `VMK_DEBUG_DELETE_DONE=notlinked|available|off|unknown|assumed` opens the confirmation screen directly; `VMK_DEBUG_REVOKE=ok|cancelled|mismatch|failed` is the Apple step's result.
    private func configureDebugDeletion() {
        let env = ProcessInfo.processInfo.environment
        let spec = env["VMK_DEBUG_FAKE_DELETE"] ?? (media?.isFake == true ? "notlinked" : nil)
        if let spec {
            let f = Set(spec.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) })
            let apple: AppleLink = f.contains("available") ? .revokeAvailable : f.contains("off") ? .revokeOff : f.contains("unknown") ? .unknown : .notLinked
            let delay: Duration? = f.contains("slow") ? .seconds(3) : nil
            let script: [Result<AppleLink, AccountError>] =
                f.contains("offline") ? [.failure(.uncertain), .success(apple)] : f.contains("forbidden") ? [.failure(.forbidden)] :
                f.contains("server") ? [.failure(.server)] : f.contains("stuck") ? [.failure(.reauthRequired)] : [.success(apple)]
            let fakeAuth = FakeDeletionAuth(sub: userID ?? "demo-user", authAge: f.contains("stale") || f.contains("cancel") ? 3600 : 30,
                                            reauthError: f.contains("cancel") ? AuthError.cancelled : nil, delay: delay)
            account = FakeAccountAPI(script, delay: delay); deletionAuth = fakeAuth
            fakeRevokeStatus = AppleRevoke.Status(rawValue: env["VMK_DEBUG_REVOKE"] ?? "ok") ?? .ok
        }
        if let d = env["VMK_DEBUG_DELETE_DONE"] {
            let apple: AppleLink = d == "available" ? .revokeAvailable : d == "off" ? .revokeOff : d == "unknown" || d == "assumed" ? .unknown : .notLinked
            deletionNotice = DeletionNotice(apple: apple, assumed: d == "assumed", revokeToken: d == "available" ? "fake" : nil)
            fakeRevokeStatus = AppleRevoke.Status(rawValue: env["VMK_DEBUG_REVOKE"] ?? "ok") ?? .ok
        }
    }

    /// QA/automation only (compiled out of Release): `SIMCTL_CHILD_VMK_DEBUG_ID_TOKEN` / `_REFRESH_TOKEN` start a signed-in session; `VMK_DEBUG_RESET=1` signs out first.
    private func seedDebugSession(_ auth: AuthService) async {
        let env = ProcessInfo.processInfo.environment
        if env["VMK_DEBUG_RESET"] == "1" { await auth.signOut() }
        guard let id = env["VMK_DEBUG_ID_TOKEN"], !id.isEmpty else { return }
        let exp = (JWT.claims(id)?["exp"] as? Double).map(Date.init(timeIntervalSince1970:)) ?? Date().addingTimeInterval(3000)
        await auth.seed(Tokens(idToken: id, accessToken: "", refreshToken: env["VMK_DEBUG_REFRESH_TOKEN"], expiresAt: exp))
    }
    #endif
}

#if DEBUG
/// Screenshots and UI tests: sending always works, after a short wait.
struct FakeFeedbackAPI: FeedbackAPI {
    func sendFeedback(_ request: FeedbackRequest) async throws { try? await Task.sleep(for: .milliseconds(500)) }
}
#endif
