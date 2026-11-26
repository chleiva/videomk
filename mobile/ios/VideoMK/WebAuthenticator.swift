import AuthenticationServices
import UIKit
import VideoMKCore

/// Ephemeral or shared Safari session: shared (the default) lets Google/Apple/Cognito cookies make a repeat sign-in one tap, but the app cannot clear
/// them, so after an explicit sign-out `AppModel` asks for an ephemeral session once (see `SignInFlow.useEphemeralSession`).
/// Presents the Cognito hosted sign-in page in the system's secure browser sheet and returns the redirect URL.
@MainActor
final class WebAuthenticator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?

    func authenticate(url: URL, callbackScheme: String, ephemeral: Bool = false) async throws -> URL {
        try await withCheckedThrowingContinuation { (cont: CheckedContinuation<URL, Error>) in
            let s = ASWebAuthenticationSession(url: url, callbackURLScheme: callbackScheme) { callback, error in
                if let callback { cont.resume(returning: callback) }
                else if let e = error as? ASWebAuthenticationSessionError, e.code == .canceledLogin { cont.resume(throwing: AuthError.cancelled) }
                else { cont.resume(throwing: AuthError.failed) }
            }
            s.presentationContextProvider = self
            s.prefersEphemeralWebBrowserSession = ephemeral
            session = s
            if !s.start() { cont.resume(throwing: AuthError.failed) }
        }
    }

    nonisolated func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
            return scene?.keyWindow ?? scene.map(UIWindow.init(windowScene:)) ?? ASPresentationAnchor()
        }
    }
}
