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
    var requestCredits = false                              // "Add credits" in Create asks the home screen to show the wallet
    var createRequested = false                             // "Make a video from this" in Media opens Create on the home screen
    var createProblem: CreateProblem?                       // generate answered blocked or paused after Create closed
    private var linkStamp: [String: Date] = [:]            // when each video's picture links were last taken (they are swapped quietly before they expire)
    private var intakeBriefs: [String: [String: String]] = [:]

    struct CreateProblem: Identifiable, Equatable { let id = UUID(); let message: String; let retryAfter: Int?; let paused: Bool; let prompt: String }
    var selectedTab = 0                                    // 0 videos, 1 media
    var composerDraft: String?                             // text to put in the composer (Try again on a failed video)
    var composerLibrary: [LibraryPhoto] = []               // library photos chosen for the next video
    var signInError: String?
    var isSigningIn = false

    private let auth: AuthService?
    private let api: APIClient?
    private let web = WebAuthenticator()
    let config: AppConfig?

    init(config: AppConfig? = AppConfig.fromBundle(), store: any TokenStore = KeychainTokenStore()) {
        self.config = config
        guard let config else { auth = nil; api = nil; createModel = CreateModel(api: nil); return }
        let a = AuthService(config: config, store: store)
        auth = a
        api = APIClient(config: config, auth: a, appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0")
        media = api.map { MediaModel(api: LibraryClient(api: $0)) }
        createModel = CreateModel(api: api)
        #if DEBUG
        if ProcessInfo.processInfo.environment["VMK_DEBUG_FAKE_LIBRARY"] == "1" { media = MediaModel(api: FakeLibraryAPI.demo(), fake: true); createModel = CreateModel(api: FakeCreateAPI()); userID = "demo-user" }
        selectedTab = Int(ProcessInfo.processInfo.environment["VMK_DEBUG_TAB"] ?? "") ?? 0
        seedDebugScreens()
        #endif
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

    func signIn() async {
        guard let auth, let config, !isSigningIn else { return }
        isSigningIn = true; signInError = nil
        defer { isSigningIn = false }
        do {
            let callback = try await web.authenticate(url: await auth.beginSignIn(), callbackScheme: config.callbackScheme)
            try await auth.completeSignIn(callback: callback)
            phase = .signedIn(email: await auth.email)
            userID = (try? await auth.authorization())?.userID
        } catch AuthError.cancelled {
            // the user closed the sheet: nothing to report
        } catch {
            signInError = "We couldn't sign you in. Please try again."
        }
    }

    func signOut() async {
        await auth?.signOut()
        await media?.wipe()      // another account must never see this one's cached photos or queued uploads
        composerLibrary = []; libraryIDs = [:]
        wallet = nil; videos = []; pending = []; photoData = [:]; photoMeta = [:]; stageSince = [:]; briefs = [:]; minutes = [:]; loadState = .idle
        phase = .signedOut
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
            if videos.isEmpty { loadState = .failed((error as? APIError)?.message ?? "Couldn't load your videos.") } else { loadState = .loaded }
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
    func submit(brief: String, options: CreateOptions, photos: [Data] = [], meta: [PhotoMeta?] = [], libraryMedia: [String] = [], intake: [String: String]? = nil) {
        let p = PendingVideo(brief: Brief.normalized(brief), options: options, photoCount: photos.count, state: photos.isEmpty ? .sending : .uploading(done: 0, total: photos.count))
        if !photos.isEmpty { photoData[p.id] = photos; photoMeta[p.id] = meta }
        if !libraryMedia.isEmpty { libraryIDs[p.id] = libraryMedia }
        if let intake, !intake.isEmpty { intakeBriefs[p.id] = intake }
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
        if let brief = briefs[video.id], Brief.isValid(brief) {
            submit(brief: brief, options: CreateOptions(minutes: minutes[video.id] ?? CreateOptions.defaultMinutes))
        } else { composerDraft = video.displayTitle }
    }

    func dismissPending(_ id: String) { pending.removeAll { $0.id == id }; photoData[id] = nil; photoMeta[id] = nil; uploadedMedia[id] = nil; libraryIDs[id] = nil }

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
            let videoID = try await create(brief: p.brief, requestID: p.id, options: p.options, media: media, mediaMeta: PhotoMetaReader.mediaMeta(ids: media, metas: photoMeta[id] ?? []), libraryMedia: libraryIDs[id] ?? [], intake: intakeBriefs[id])
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

    func create(brief: String, requestID: String, options: CreateOptions, media: [String] = [], mediaMeta: [String: PhotoMeta] = [:], libraryMedia: [String] = [], intake: [String: String]? = nil) async throws -> String {
        guard let api else { throw APIError.server }
        do { return try await api.startGeneration(prompt: brief, clientRequestID: requestID, options: options, media: media, mediaMeta: mediaMeta, libraryMedia: libraryMedia, brief: intake) }
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
        guard let api else { throw APIError.server }
        return try await api.playback(videoID: id)
    }

    #if DEBUG
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
