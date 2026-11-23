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
    var signInError: String?
    var isSigningIn = false

    private let auth: AuthService?
    private let api: APIClient?
    private let web = WebAuthenticator()
    let config: AppConfig?

    init(config: AppConfig? = AppConfig.fromBundle(), store: any TokenStore = KeychainTokenStore()) {
        self.config = config
        guard let config else { auth = nil; api = nil; return }
        let a = AuthService(config: config, store: store)
        auth = a
        api = APIClient(config: config, auth: a, appVersion: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0")
    }

    var hasRunningVideos: Bool { videos.contains { $0.status.isRunning } || pending.contains { $0.state == .sending } }
    var entries: [LibraryEntry] { LibraryMerge.entries(pending: pending, server: videos) }

    func refreshWallet() async {
        guard let api else { return }
        if let w = try? await api.wallet() { wallet = w }
    }

    func brief(for id: String) -> String? { briefs[id] }
    func stage(for id: String) -> (stage: VideoStatus.Stage, since: Date)? { stageSince[id] }
    func requestedMinutes(for id: String) -> Double { minutes[id] ?? CreateOptions.defaultMinutes }
    func video(_ id: String) -> VideoItem? { videos.first { $0.id == id } }

    // MARK: session

    func start() async {
        guard let auth else { phase = .notConfigured; return }
        #if DEBUG
        await seedDebugSession(auth)
        #endif
        phase = await auth.isSignedIn ? .signedIn(email: await auth.email) : .signedOut
    }

    func signIn() async {
        guard let auth, let config, !isSigningIn else { return }
        isSigningIn = true; signInError = nil
        defer { isSigningIn = false }
        do {
            let callback = try await web.authenticate(url: await auth.beginSignIn(), callbackScheme: config.callbackScheme)
            try await auth.completeSignIn(callback: callback)
            phase = .signedIn(email: await auth.email)
        } catch AuthError.cancelled {
            // the user closed the sheet: nothing to report
        } catch {
            signInError = "We couldn't sign you in. Please try again."
        }
    }

    func signOut() async {
        await auth?.signOut()
        wallet = nil; videos = []; pending = []; stageSince = [:]; briefs = [:]; minutes = [:]; loadState = .idle
        phase = .signedOut
    }

    // MARK: library

    func refresh() async {
        guard let api else { return }
        if videos.isEmpty { loadState = .loading }
        do {
            Task { await refreshWallet() }  // credits load alongside the list
            let fresh = try await api.listVideos()
            track(old: videos, new: fresh)
            videos = fresh
            pending = LibraryMerge.stillPending(pending, server: fresh)
            loadState = .loaded
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
    func submit(brief: String, options: CreateOptions) {
        let p = PendingVideo(brief: Brief.normalized(brief), options: options)
        pending.insert(p, at: 0)
        Task { await send(p.id) }
    }

    func retry(_ id: String) {
        guard let i = pending.firstIndex(where: { $0.id == id }) else { return }
        pending[i].state = .sending
        Task { await send(id) }
    }

    func dismissPending(_ id: String) { pending.removeAll { $0.id == id } }

    private func send(_ id: String) async {
        guard let p = pending.first(where: { $0.id == id }) else { return }
        do {
            let videoID = try await create(brief: p.brief, requestID: p.id, options: p.options)
            briefs[videoID] = p.brief; minutes[videoID] = p.options.minutes
            if let i = pending.firstIndex(where: { $0.id == id }) { pending[i].state = .accepted(videoID: videoID) }
            await refresh()  // also re-reads the credits the video just used
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

    func create(brief: String, requestID: String, options: CreateOptions) async throws -> String {
        guard let api else { throw APIError.server }
        do { return try await api.startGeneration(prompt: brief, clientRequestID: requestID, options: options) }
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
