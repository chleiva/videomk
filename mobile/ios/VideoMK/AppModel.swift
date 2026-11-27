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
    private var heldStarts: Set<String> = []               // requests the Create screen is still waiting on ("Starting your video"): their outcome goes back to it
    private var heldProblems: [String: CreateProblem] = [:]
    private var liveMaking: [String: MakingInfo] = [:]     // the freshest "making" of a video whose screen is open (the list answer may lag behind)
    private var lookNotes: [String: String] = [:]          // the server's one sentence when the chosen look had to be adapted (shown on Making)
    private var startedLooks: [String: AppliedLook] = [:]  // what the start answer said the video gets, until the video record says it itself
    private(set) var revealing: String?                    // the video that has just become ready while its Making screen or card was showing
    var createPrefill: CreatePrefill?                      // "Make another" on a finished video: Create opens with the same sentence and one choice changed
    struct CreatePrefill: Equatable { var text: String; var platformChip: String?; var minutes: Double?; var language: String? }

    /// How a held start ended (see `startOutcome`).
    enum StartOutcome: Equatable { case accepted, handedOff, failed(String), refused(CreateProblem) }

    struct CreateProblem: Identifiable, Equatable { let id = UUID(); let message: String; let retryAfter: Int?; let paused: Bool; let prompt: String }
    var selectedTab = 0                                    // 0 videos, 1 media
    var tabBarHidden = false                               // a video is open: the floating bar steps aside
    var composerDraft: String?                             // text to put in the composer (Try again on a failed video)
    var retryNotice: RetryNotice?                          // why "Try again" or Remove could not be done (shown once)
    private(set) var retrying: Set<String> = []            // failed videos whose Try again is on its way
    private var attachments: [String: Int] = [:]           // videos made in this session: how many photos and presentations they were made with (an older server's fallback never drops them)
    struct RetryNotice: Identifiable, Equatable { let id = UUID(); var title: String = tr("retry.notice_title"); let message: String }
    var composerLibrary: [LibraryPhoto] = []               // library photos chosen for the next video
    var mediaSelection: [LibraryPhoto] = []                // what is ticked on the Media tab right now (the round (+) attaches it to a new video)
    var mediaPushed = false                                // a collection page is open in Media: the tab bar steps aside there too
    var mediaSelecting = false                             // Select mode is on in Media: the tab bar steps aside so the action bar is never covered
    private(set) var submitted = 0                         // counts videos sent from Create: Media clears its selection when it grows
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
        if ProcessInfo.processInfo.environment["VMK_DEBUG_FAKE_LIBRARY"] == "1" {
            if ProcessInfo.processInfo.environment["VMK_DEBUG_FORGET_CREATE"] == "1" { CreateDefaults.forget(userID: "demo-user") }      // a first run: no remembered platform, length or look
            media = MediaModel(api: FakeLibraryAPI.demo(), fake: true); createModel = CreateModel(api: Self.debugCreateAPI()); userID = "demo-user"
        }
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

    /// The account has made a video (or the list is not known yet, which counts the same: nothing first-time is shown to someone who may be a regular).
    /// Create's example chips and its "2 credits. You have 11." caption are for the first video only.
    var hasFinishedVideo: Bool { loadState != .loaded || videos.contains { $0.status == .complete } }

    var hasRunningVideos: Bool { videos.contains { $0.status.isRunning } || pending.contains { $0.state == .sending } }
    /// Videos that are being deleted (the Undo toast is still up): hidden everywhere, not yet removed on the server.
    var entries: [LibraryEntry] { LibraryMerge.entries(pending: pending, server: videos.filter { !deleting.contains($0.id) }) }
    private(set) var deleting: Set<String> = []
    /// "Deleted · Undo": one pending delete at a time, for videos, photos and collections.
    let undo = UndoCenter()

    func refreshWallet() async {
        guard let api else { return }
        #if DEBUG
        if media?.isFake == true { return }
        #endif
        if let w = try? await api.wallet(), w != wallet { wallet = w }
        scheduleFreeCredit()
    }

    @ObservationIgnored private var freeCreditTask: Task<Void, Never>?
    /// The free credit is not pushed: the server adds it the first time the wallet is read at or after `next_free_credit_at`. So the wallet is read
    /// again at that moment (while the app is running; coming back to the front reads it anyway).
    private func scheduleFreeCredit() {
        freeCreditTask?.cancel()
        guard let at = wallet?.nextFree?.at else { return }
        let wait = at.timeIntervalSinceNow + 2
        guard wait > 0, wait < 36 * 3600 else { return }
        freeCreditTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(wait))
            guard !Task.isCancelled else { return }
            await self?.refreshWallet()
        }
    }

    /// What the server says about a video being made: the screen's own fresher answer when there is one, else what came with the list.
    func making(for video: VideoItem) -> MakingInfo? { liveMaking[video.id] ?? video.making }

    /// The Making screen asks for the video's own status while it is open (every few seconds): scenes and lines arrive sooner than with the list.
    /// Any failure, and a server that does not send "making" yet, leaves what is on screen.
    func refreshMaking(_ id: String) async {
        guard let api else { return }
        #if DEBUG
        if media?.isFake == true { return }
        #endif
        if let info = try? await api.makingInfo(videoID: id), liveMaking[id].map({ !$0.visiblyEqual(info) }) ?? true { liveMaking[id] = info }
    }

    func brief(for id: String) -> String? { briefs[id] }
    /// "Made from your photos: the Cartoon look is not used with your own photos.": only when the server adapted the chosen look.
    func lookNote(for id: String) -> String? { lookNotes[id] }
    /// The look the video was made in: the video record's own, else what the start answer said.
    func appliedLook(for id: String) -> AppliedLook? { video(id)?.look ?? startedLooks[id] }
    private func remember(_ started: StartedVideo) {
        if let note = started.note { lookNotes[started.videoID] = note }
        if let look = started.look { startedLooks[started.videoID] = look }
    }
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
                let callback = try await web.authenticate(url: await auth.beginSignIn(provider: provider, language: Localization.shared.language.rawValue), callbackScheme: config.callbackScheme, ephemeral: ephemeral)
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
        lookNotes = [:]; startedLooks = [:]
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
        composerDraft = nil; createProblem = nil; requestCredits = false; createRequested = false; selectedTab = 0; mediaSelection = []; mediaSelecting = false; userID = nil; signInError = nil
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

    /// Bumps each time the app comes back to the front: the screens' polling tasks carry it in their id, so SwiftUI cancels the old ones (and with
    /// them any request left hanging from before the app was suspended) and starts fresh ones.
    private(set) var foregroundEpoch = 0
    @ObservationIgnored private var wasInBackground = false
    @ObservationIgnored private var lastForegroundRefresh = Date.distantPast

    func appWentToBackground() {
        wasInBackground = true
        #if DEBUG
        // `VMK_DEBUG_FINISH_IN_BACKGROUND=1` (fake runs): the fake server finishes every running video while the app is away
        if media?.isFake == true, ProcessInfo.processInfo.environment["VMK_DEBUG_FINISH_IN_BACKGROUND"] == "1" {
            fakeServerVideos = videos.map { v in v.status.isRunning ? VideoItem(id: v.id, status: .complete, title: v.title, durationSeconds: 62, createdAt: v.createdAt, videoURL: nil, previewGifURL: URL(string: "fake://landscape/clip_05"), rejectReason: nil, editable: true, aspect: "16:9", resolution: "1080p", deckStage: nil, canRetry: nil) : v }
        }
        #endif
    }

    /// The app is in front again (from another app or from the lock screen): the list is read NOW, not at the next poll, whatever was in flight
    /// before. A video that finished while the app was away shows as finished at once; polling restarts if anything is still being made; an
    /// expired token is refreshed inside the call (`APIClient.perform`).
    func appBecameActive() async {
        guard case .signedIn = phase else { return }
        let away = wasInBackground; wasInBackground = false
        guard away || Date().timeIntervalSince(lastForegroundRefresh) > 10 else { return }       // Control Centre or a banner: not every flicker asks the server
        lastForegroundRefresh = .now
        foregroundEpoch += 1
        await refresh()
    }

    #if DEBUG
    @ObservationIgnored private var fakeServerVideos: [VideoItem]?
    #endif

    func refresh() async {
        guard let api else { return }
        #if DEBUG
        if media?.isFake == true {          // fake-library runs never call the real backend (its 401 would sign the demo session out)
            if let fresh = fakeServerVideos { fakeServerVideos = nil; track(old: videos, new: fresh); videos = fresh }
            loadState = .loaded; return
        }
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
                stageSince[v.id] = nil; liveMaking[v.id] = nil
                if let b = before[v.id], b.isRunning, v.status == .complete { completions += 1; reveal(v.id, title: v.displayTitle) }
            }
        }
    }

    /// iOS gave the app a moment in the background ("Tell me when it's ready"): look once; if something is still being made, ask for another look.
    func backgroundCheck() async {
        await refresh()
        ReadyNotifier.shared.appDidEnterBackground(hasRunning: hasRunningVideos)
    }

    /// A video has just become ready: its poster takes the place of the Making card (the reveal), and the first play fades in.
    private func reveal(_ id: String, title: String) {
        ReadyNotifier.shared.videoReady(title: title)
        revealing = id
        Task { try? await Task.sleep(for: .seconds(4)); if revealing == id { revealing = nil } }
    }

    // MARK: ask for a video without leaving the home screen

    /// Adds a placeholder row immediately and sends the request in the background; the user can keep browsing or ask for more.
    /// `held`: the Create screen stays open on "Starting your video" until the outcome is known (`startOutcome`), then calls `releaseStart` or `abandonStart`.
    @discardableResult func submit(brief: String, options: CreateOptions, photos: [Data] = [], meta: [PhotoMeta?] = [], libraryMedia: [String] = [], intake: [String: String]? = nil, deckID: String? = nil, deckName: String? = nil, sendsMinutes: Bool = true, held: Bool = false) -> String {
        let title = Brief.normalized(brief).isEmpty && deckID != nil ? tr("deck.video_title", deckName ?? "") : Brief.normalized(brief)
        let p = PendingVideo(brief: title, options: options, photoCount: photos.count, state: photos.isEmpty ? .sending : .uploading(done: 0, total: photos.count))
        if !photos.isEmpty { photoData[p.id] = photos; photoMeta[p.id] = meta }
        if !libraryMedia.isEmpty { libraryIDs[p.id] = libraryMedia }
        if let intake, !intake.isEmpty { intakeBriefs[p.id] = intake }
        if let deckID { deckIDs[p.id] = deckID; deckMinutes[p.id] = sendsMinutes; deckPrompts[p.id] = Brief.normalized(brief) }
        pending.insert(p, at: 0)
        if held { heldStarts.insert(p.id) } else { submitted += 1; selectedTab = 0 }      // the new video is on the Videos tab: go and see it making
        Task { await send(p.id) }
        return p.id
    }

    /// Waits for a held start to be accepted or to fail, at most `wait` (then the list takes over: `.handedOff`) and at least `minimum` (so the words can be read).
    func startOutcome(_ id: String, wait: Duration, minimum: Duration) async -> StartOutcome {
        let clock = ContinuousClock(), began = clock.now
        var result = StartOutcome.handedOff
        while clock.now - began < wait {
            guard let p = pending.first(where: { $0.id == id }) else { result = .accepted; break }       // the server's own row has already replaced it
            if case .accepted = p.state { result = .accepted; break }
            if case .failed(let m) = p.state { result = heldProblems[id].map(StartOutcome.refused) ?? .failed(m); break }
            try? await Task.sleep(for: .milliseconds(80))
        }
        let spent = clock.now - began
        if spent < minimum { try? await Task.sleep(for: minimum - spent) }
        return result
    }

    /// The held start went through (or is left to the list): Media clears its selection and the Videos tab shows the Making card.
    func releaseStart(_ id: String) { heldStarts.remove(id); heldProblems[id] = nil; submitted += 1; selectedTab = 0 }

    /// The held start failed while Create was still open: its placeholder goes; Create still has everything (sentence, photos, options).
    func abandonStart(_ id: String) { heldStarts.remove(id); heldProblems[id] = nil; dismissPending(id) }

    /// "Make a video" from Media (selection bar, viewer, a collection, the round (+)): Create opens over the tab the person is on, with these photos attached.
    /// Closing Create brings them back to where they were; a selection in Media stays ticked until the video is sent.
    func startVideo(with photos: [LibraryPhoto]) {
        composerLibrary = Array(photos.prefix(PhotoLimits.maxPhotos))
        createRequested = true
    }

    /// The round (+): on the Media tab, with photos ticked, the video starts with them (when nothing else is attached yet).
    func requestCreate() {
        if selectedTab == 1, composerLibrary.isEmpty, !mediaSelection.isEmpty { composerLibrary = Array(mediaSelection.prefix(PhotoLimits.maxPhotos)) }
        createRequested = true
    }

    func retry(_ id: String) {
        guard let i = pending.firstIndex(where: { $0.id == id }) else { return }
        pending[i].state = pending[i].photoCount > 0 ? .uploading(done: uploadedMedia[id]?.count ?? 0, total: pending[i].photoCount) : .sending
        Task { await send(id) }
    }

    /// "Try again" on a video the server could not finish: the SAME video starts again on the server with everything it was made with (every photo, option, language, watermark):
    /// no new row, nothing resent from the phone. An older server without the route: only a video known to have had no attachments is asked for again the old way; any other is
    /// never rebuilt without its photos (that is how a 60-photo video once came back with none): the person is told instead.
    func tryAgain(_ video: VideoItem) {
        guard let api, !retrying.contains(video.id) else { return }
        #if DEBUG
        if media?.isFake == true { fakeTryAgain(video); return }     // fake-library runs never call the real backend
        #endif
        retrying.insert(video.id)
        Task {
            defer { retrying.remove(video.id) }
            do {
                switch try await api.retryVideo(videoID: video.id) {
                case .started(_, let unusable):
                    markRunning(video.id)                    // the row turns into the making card at once
                    await refresh()
                    if unusable > 0 { retryNotice = RetryNotice(message: tr("retry.photos_unusable", unusable)) }
                case .alreadyRunning:
                    markRunning(video.id); await refresh()
                case .unsupported:
                    if let brief = briefs[video.id], RetryRules.mayResendFromPrompt(attachments: attachments[video.id], briefIsValid: Brief.isValid(brief), fromPresentation: deckVideos.contains(video.id)) {
                        submit(brief: brief, options: CreateOptions(minutes: minutes[video.id] ?? CreateOptions.defaultMinutes))
                    } else { retryNotice = RetryNotice(message: tr("retry.unavailable")) }
                case .refused(_, let message):
                    retryNotice = RetryNotice(message: message); await refresh()
                }
            } catch let e as AuthError where e == .signedOut { await signOut()
            } catch let e as APIError where e == .unauthorized { await signOut()
            } catch let e as APIError {
                if case .insufficientCredits = e { await refreshWallet() }
                retryNotice = RetryNotice(message: e.message)
            } catch { retryNotice = RetryNotice(message: APIError.server.message) }
        }
    }

    private func markRunning(_ id: String) {
        guard let i = videos.firstIndex(where: { $0.id == id }) else { return }
        let v = videos[i]
        videos[i] = VideoItem(id: v.id, status: .running(.starting), title: v.title, durationSeconds: nil, createdAt: v.createdAt, videoURL: nil, previewGifURL: nil, rejectReason: nil, editable: false, aspect: v.aspect, resolution: v.resolution, deckStage: nil, canRetry: nil)
        stageSince[id] = (.starting, .now)
    }

    #if DEBUG
    /// Fake-library runs: what the server would answer to Try again. `VMK_DEBUG_FAKE_RETRY=unusable|unsupported|refused` (default: the video starts again).
    private func fakeTryAgain(_ video: VideoItem) {
        switch ProcessInfo.processInfo.environment["VMK_DEBUG_FAKE_RETRY"] {
        case "unsupported":
            if let brief = briefs[video.id], RetryRules.mayResendFromPrompt(attachments: attachments[video.id], briefIsValid: Brief.isValid(brief), fromPresentation: deckVideos.contains(video.id)) {
                submit(brief: brief, options: CreateOptions(minutes: minutes[video.id] ?? CreateOptions.defaultMinutes))
            } else { retryNotice = RetryNotice(message: tr("retry.unavailable")) }
        case "refused": retryNotice = RetryNotice(message: "These photos are no longer available. Start a new video with them.")
        case "unusable": markRunning(video.id); retryNotice = RetryNotice(message: tr("retry.photos_unusable", 1))
        default: markRunning(video.id)
        }
    }
    #endif

    /// Deletes a video (one that did not finish, or a finished one from the player's More menu): it leaves the list at once and "Deleted · Undo" shows
    /// for six seconds; the DELETE is only sent when that time is up, because the server has no undo and no bin (rule 8: undo over confirm).
    /// If the server says no (an edit of it is still rendering, or it is being made), the video comes back and one line says why.
    func deleteVideo(_ video: VideoItem) {
        let id = video.id
        deleting.insert(id)
        Haptics.play(.selection)
        undo.offer(tr("undo.deleted"), undo: { [weak self] in self?.deleting.remove(id) }, commit: { [weak self] in await self?.commitDelete(id) })
    }

    // MARK: cancel a video that is being made

    /// One line that needs no answer ("Cancelled · 2 credits back"): shown where the Undo toast shows, for a few seconds.
    private(set) var infoToast: InfoToast?
    struct InfoToast: Identifiable, Equatable { let id = UUID(); let text: String }
    func say(_ text: String) {
        let t = InfoToast(text: text); infoToast = t
        Task { try? await Task.sleep(for: UndoCenter.window); if infoToast?.id == t.id { infoToast = nil } }
    }
    private(set) var cancelling: Set<String> = []

    /// "Cancel video" on a video that is being made. The server stops it and gives the credits of this attempt back; the card becomes a cancelled one
    /// (Try again, Remove). If it finished in the meantime, nothing is refunded and the finished video is simply there.
    func cancelVideo(_ video: VideoItem) {
        guard !cancelling.contains(video.id) else { return }
        let id = video.id
        #if DEBUG
        if media?.isFake == true {
            if ProcessInfo.processInfo.environment["VMK_DEBUG_FAKE_CANCEL"] == "finished" { retryNotice = RetryNotice(title: tr("making.not_cancelled"), message: "This video is already made."); return }
            markCancelled(id); say(tr("making.cancelled_refund", max(1, Int((minutes[id] ?? 1).rounded(.up))))); Haptics.play(.selection); return
        }
        #endif
        guard let api else { return }
        cancelling.insert(id)
        Task {
            defer { cancelling.remove(id) }
            do {
                switch try await api.cancelVideo(videoID: id) {
                case .cancelled(let refunded):
                    markCancelled(id); Haptics.play(.selection)
                    say(refunded > 0 ? tr("making.cancelled_refund", refunded) : tr("making.cancelled"))
                    await refresh()          // the server's own item (can_retry) and the credits that came back
                case .notCancellable(let message): await refresh(); if self.video(id)?.status.isRunning == true { retryNotice = RetryNotice(title: tr("making.not_cancelled"), message: message) }
                case .tryAgain, .unsupported: retryNotice = RetryNotice(title: tr("making.not_cancelled"), message: tr("making.cancel_unavailable"))
                }
            } catch let e as AuthError where e == .signedOut { await signOut()
            } catch let e as APIError where e == .unauthorized { await signOut()
            } catch let e as APIError { retryNotice = RetryNotice(title: tr("making.not_cancelled"), message: e.message)
            } catch { retryNotice = RetryNotice(title: tr("making.not_cancelled"), message: APIError.server.message) }
        }
    }

    private func markCancelled(_ id: String) {
        guard let i = videos.firstIndex(where: { $0.id == id }) else { return }
        let v = videos[i]
        videos[i] = VideoItem(id: v.id, status: .cancelled, title: v.title, durationSeconds: nil, createdAt: v.createdAt, videoURL: nil, previewGifURL: nil, rejectReason: nil, editable: false, aspect: v.aspect, resolution: v.resolution, deckStage: nil, canRetry: !deckVideos.contains(id))
        stageSince[id] = nil; liveMaking[id] = nil
    }

    private func commitDelete(_ id: String) async {
        defer { deleting.remove(id) }
        #if DEBUG
        if media?.isFake == true {
            if ProcessInfo.processInfo.environment["VMK_DEBUG_FAKE_DELETE_VIDEO"] == "busy", video(id)?.status == .complete { retryNotice = RetryNotice(title: tr("undo.not_deleted"), message: "An edit of this video is still rendering. Try again when it is done."); return }
            videos.removeAll { $0.id == id }; return
        }
        #endif
        guard let api else { return }
        do {
            if try await api.deleteVideo(videoID: id) { videos.removeAll { $0.id == id } }
            else { retryNotice = RetryNotice(title: tr("undo.not_deleted"), message: tr("retry.remove_unavailable")) }
        } catch let e as AuthError where e == .signedOut { await signOut()
        } catch let e as APIError where e == .unauthorized { await signOut()
        } catch let e as APIError { retryNotice = RetryNotice(title: tr("undo.not_deleted"), message: e.message); await refresh()
        } catch { retryNotice = RetryNotice(title: tr("undo.not_deleted"), message: APIError.server.message) }
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
            if self.media?.isFake == true { try await acceptFake(p); return }
            #endif
            let started = try await create(brief: deckIDs[id] != nil ? (deckPrompts[id] ?? "") : p.brief, requestID: p.id, options: p.options, media: media, mediaMeta: PhotoMetaReader.mediaMeta(ids: media, metas: photoMeta[id] ?? []), libraryMedia: libraryIDs[id] ?? [], intake: intakeBriefs[id], deck: deckIDs[id], sendMinutes: deckMinutes[id] ?? true)
            let videoID = started.videoID
            remember(started)
            if deckIDs[id] != nil { deckVideos.insert(videoID) }
            attachments[videoID] = media.count + (libraryIDs[id] ?? []).count + (deckIDs[id] != nil ? 1 : 0)
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
            let problem = CreateProblem(message: e.message, retryAfter: retry, paused: isPaused, prompt: p.brief)
            if heldStarts.contains(id) { heldProblems[id] = problem } else { createProblem = problem }      // Create is still open: it shows the kind sheet itself
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

    func create(brief: String, requestID: String, options: CreateOptions, media: [String] = [], mediaMeta: [String: PhotoMeta] = [:], libraryMedia: [String] = [], intake: [String: String]? = nil, deck: String? = nil, sendMinutes: Bool = true) async throws -> StartedVideo {
        guard let api else { throw APIError.server }
        do { return try await api.startVideo(prompt: brief, clientRequestID: requestID, options: options, media: media, mediaMeta: mediaMeta, libraryMedia: libraryMedia, brief: intake, deck: deck, sendMinutes: sendMinutes) }
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
        #if DEBUG
        if media?.isFake == true { throw APIError.network }       // fake-library runs never reach the backend (its 401 would sign the demo session out)
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
        // `VMK_DEBUG_LOOKS=1|locked|lockedplain|soon|noboard|short` (comma list): the fake server lists the look picker. `VMK_DEBUG_LOOKS_FILE=/path/looks.json` is a saved
        // capabilities answer with the real pictures (VideoMKUITests/Fixtures); without it tiles and faces draw their placeholders.
        if let spec = env["VMK_DEBUG_LOOKS"] { caps = caps.withLooks((env["VMK_DEBUG_LOOKS_FILE"].flatMap(LookCapabilities.from(file:)) ?? .fake).variant(spec)) }
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

    /// Fake-library runs: what the server would do with a new video. `VMK_DEBUG_FAKE_START=fail|blocked|paused|slow` (default: accepted after a moment);
    /// the fake video then finishes its scenes one by one (`VMK_DEBUG_MAKING` picks what the fake server reports) and becomes ready.
    private func acceptFake(_ p: PendingVideo) async throws {
        let script = ProcessInfo.processInfo.environment["VMK_DEBUG_FAKE_START"] ?? ""
        try? await Task.sleep(for: script == "slow" ? .seconds(12) : .milliseconds(1200))
        switch script {
        case "fail": throw APIError.network
        case "blocked": throw APIError.blocked("We can’t make this one. Try describing something different.")
        case "paused": throw APIError.paused("Creating videos is paused for this account for now.", retryAfter: 3600)
        default: break
        }
        let videoID = "fakevideo-\(p.id.prefix(6))"
        briefs[videoID] = p.brief; minutes[videoID] = p.options.minutes
        remember(FakeLook.started(videoID: videoID, options: p.options, photos: p.photoCount > 0 || libraryIDs[p.id] != nil, caps: createModel.caps.looks, spanish: Localization.shared.language == .es))
        videos.insert(VideoItem(id: videoID, status: .running(.starting), title: p.brief, createdAt: .now, aspect: p.options.aspect, resolution: p.options.resolution), at: 0)
        stageSince[videoID] = (.starting, .now)
        if let i = pending.firstIndex(where: { $0.id == p.id }) { pending[i].state = .accepted(videoID: videoID) }
        photoData[p.id] = nil; photoMeta[p.id] = nil; libraryIDs[p.id] = nil
        Task { @MainActor in await runFakeMaking(videoID, title: p.brief, aspect: p.options.aspect, resolution: p.options.resolution) }
    }

    /// The fake server's "making": scenes finish one by one, then the video is ready (so the film strip, the live lines and the reveal can be seen and tested).
    private func runFakeMaking(_ id: String, title: String, aspect: String, resolution: String) async {
        let mode = ProcessInfo.processInfo.environment["VMK_DEBUG_MAKING"] ?? "thumbs"
        let total = 6
        func set(_ status: VideoStatus, _ making: MakingInfo?, done: Bool = false) {
            guard let i = videos.firstIndex(where: { $0.id == id }) else { return }
            videos[i] = VideoItem(id: id, status: status, title: title, durationSeconds: done ? 62 : nil, createdAt: videos[i].createdAt, previewGifURL: done ? URL(string: "fake://\(aspect == "9:16" ? "portrait" : "landscape")/clip_01") : nil, aspect: aspect, resolution: resolution, making: making, look: done ? startedLooks[id] : nil)
        }
        try? await Task.sleep(for: .seconds(2))
        stageSince[id] = (.voiceAndVisuals, .now)
        for done in 0...total {
            set(.running(done == total ? .rendering : .voiceAndVisuals), mode == "none" ? nil : Self.fakeMaking(done: done, total: total, thumbs: mode == "thumbs"))
            try? await Task.sleep(for: .milliseconds(2200))
        }
        set(.complete, nil, done: true)
        stageSince[id] = nil; completions += 1; reveal(id, title: title)
    }

    static func fakeMaking(done: Int, total: Int, thumbs: Bool) -> MakingInfo {
        let lines = ["Finding the right footage", "Adding footage of sunlit canopies", "Recording the narration", "Choosing the music", "Timing the captions", "Adding the last scene"]
        let narration = ["Sunlight pours through the canopy, and the forest breathes.", "Every leaf is a small green lung.", "Roots trade water for sugar, underground.", "At night the whole forest exhales.", "One tree can cool a street.", "That is why forests matter."]
        let clips = ["clip_01", "clip_03", "clip_08", "clip_10", "clip_05", "clip_07", "s_forest", "p08", "p09"]
        let scenes = (1...total).map { i in MakingInfo.Scene(index: i, thumbURL: thumbs && i <= done + 1 ? URL(string: "fake://landscape/\(clips[(i - 1) % clips.count])") : nil, done: i <= done) }
        return MakingInfo(sceneTotal: total, sceneDone: done, liveLine: done >= total ? "Putting it all together" : lines[done % lines.count], narrationLine: done >= total ? nil : narration[done % narration.count], scenes: scenes)
    }

    /// Screenshots with `VMK_DEBUG_FAKE_LIBRARY=1`: a wallet (`VMK_DEBUG_BALANCE`), a few videos (`VMK_DEBUG_FAKE_VIDEOS=1`) and an upload moment.
    private func seedDebugScreens() {
        guard media?.isFake == true else { return }
        let env = ProcessInfo.processInfo.environment
        if let b = env["VMK_DEBUG_BALANCE"].flatMap(Int.init) {
            // `VMK_DEBUG_WALLET=buckets` lists where the credits came from; `nodate` is a server that sends no date for the next free credit
            let tomorrow = Calendar.current.startOfDay(for: .now.addingTimeInterval(86400))
            let buckets = env["VMK_DEBUG_WALLET"] == "buckets" ? [WalletBucket(kind: "daily", remaining: 1, expiresAt: tomorrow), WalletBucket(kind: "signup", remaining: max(0, b - 1), expiresAt: .now.addingTimeInterval(20 * 86400))] : []
            wallet = env["VMK_DEBUG_WALLET"] == "dailyoff" ? WalletInfo(balance: b, nextFreeCredits: 0, dailyCredits: 0) : WalletInfo(balance: b, buckets: buckets, nextFreeAt: env["VMK_DEBUG_WALLET"] == "nodate" ? nil : tomorrow, nextFreeCredits: env["VMK_DEBUG_WALLET"] == "nodate" ? nil : 1)
        }
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
        if env["VMK_DEBUG_FAKE_VIDEOS"] == "bar" {
            // the videos of the design-bar mockups: one being made (what the fake server reports about it: `VMK_DEBUG_MAKING=thumbs|tiles|none`), a large first poster, then a
            // landscape and a vertical one side by side, one that did not finish
            let mode = env["VMK_DEBUG_MAKING"] ?? "thumbs"
            let making = mode == "none" ? nil : Self.fakeMaking(done: 4, total: 9, thumbs: mode == "thumbs")
            func pic(_ kind: String, _ name: String) -> URL? { URL(string: "fake://\(kind)/\(name)") }
            videos = [
                VideoItem(id: "v1", status: .running(.voiceAndVisuals), title: "How honey is made", createdAt: .now, making: making),
                VideoItem(id: "v3", status: .complete, title: "How a forest breathes", durationSeconds: 91, createdAt: .now.addingTimeInterval(-1800), previewGifURL: pic("landscape", "clip_01"), editable: true, aspect: "16:9", resolution: "1080p",
                          look: env["VMK_DEBUG_LOOKS"] == nil ? nil : AppliedLook(chosen: "auto", applied: "whiteboard", why: Localization.shared.language == .es ? "Un proceso paso a paso se entiende mejor dibujado." : "A step-by-step process is clearest drawn.", byAuto: true)),
                VideoItem(id: "v4", status: .complete, title: "How bees make honey", durationSeconds: 124, createdAt: .now.addingTimeInterval(-7200), previewGifURL: pic("landscape", "s_bees"), aspect: "16:9", resolution: "1080p"),
                VideoItem(id: "v5", status: .complete, title: "3 focus tips", durationSeconds: 30, createdAt: .now.addingTimeInterval(-86400), previewGifURL: pic("portrait", "s_focus"), aspect: "9:16", resolution: "1080p"),
                VideoItem(id: "v2", status: .failed, title: "Thailand highlights", createdAt: .now.addingTimeInterval(-90000)),
                VideoItem(id: "v6", status: .complete, title: "Why octopuses are so clever", durationSeconds: 75, createdAt: .now.addingTimeInterval(-172800), previewGifURL: pic("landscape", "s_pulpo"), aspect: "16:9", resolution: "1080p"),
                VideoItem(id: "v7", status: .complete, title: "The jobs of tomorrow", durationSeconds: 58, createdAt: .now.addingTimeInterval(-272800), previewGifURL: pic("landscape", "s_jobs"), aspect: "16:9", resolution: "1080p"),
            ]
            briefs["v1"] = "How honey is made"; minutes["v1"] = 2
            if env["VMK_DEBUG_LOOK_NOTE"] == "1" { lookNotes["v1"] = Localization.shared.language == .es ? "Presenta un solo personaje. Una conversación necesita 20 s o más." : "One character presents. A conversation needs 20 s or more." }
            stageSince["v1"] = (.voiceAndVisuals, Date().addingTimeInterval(-40))
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
