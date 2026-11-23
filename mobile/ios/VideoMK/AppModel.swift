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

    var hasRunningVideos: Bool { videos.contains { $0.status.isRunning } }
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
        videos = []; loadState = .idle
        phase = .signedOut
    }

    // MARK: library

    func refresh() async {
        guard let api else { return }
        if videos.isEmpty { loadState = .loading }
        do {
            videos = try await api.listVideos()
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

    /// Polls while anything is running; ends when the view disappears (task cancelled) or everything has settled.
    func pollWhileRunning() async {
        while !Task.isCancelled, hasRunningVideos {
            try? await Task.sleep(for: .seconds(4))
            if Task.isCancelled { break }
            await refresh()
        }
    }

    // MARK: create / play

    func create(brief: String, requestID: String) async throws -> String {
        guard let api else { throw APIError.server }
        do { return try await api.startGeneration(prompt: brief, clientRequestID: requestID) }
        catch let e as AuthError where e == .signedOut { await signOut(); throw APIError.unauthorized }
    }

    func playbackURL(for id: String) async throws -> URL {
        guard let api else { throw APIError.server }
        return try await api.playbackURL(videoID: id)
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
