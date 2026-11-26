import Foundation

/// Federated sign-in through the Cognito hosted UI. `rawValue` is the exact (case-sensitive) `identity_provider` value.
public enum SocialProvider: String, Sendable, Equatable, CaseIterable {
    case apple = "SignInWithApple"
    case google = "Google"
}

/// Which sign-in buttons exist. Build-time switches (Info.plist `VMKAuthApple` / `VMKAuthGoogle`, from the build settings
/// `VMK_AUTH_APPLE` / `VMK_AUTH_GOOGLE`); anything but an explicit yes is off.
public struct AuthOptions: Sendable, Equatable {
    public var apple: Bool
    public var google: Bool
    public init(apple: Bool = false, google: Bool = false) { self.apple = apple; self.google = google }

    public static let off = AuthOptions()

    public static func fromBundle(_ bundle: Bundle = .main) -> AuthOptions {
        func on(_ key: String) -> Bool { parse(bundle.object(forInfoDictionaryKey: key) as? String) }
        return AuthOptions(apple: on("VMKAuthApple"), google: on("VMKAuthGoogle"))
    }

    static func parse(_ s: String?) -> Bool {
        guard let s else { return false }
        return ["yes", "1", "true"].contains(s.trimmingCharacters(in: .whitespaces).lowercased())
    }

    /// The buttons to draw, top to bottom. Apple first (it must be at least as prominent as any other third-party option), then Google, then email.
    public var choices: [SignInChoice] {
        (apple ? [SignInChoice.apple] : []) + (google ? [.google] : []) + [.email]
    }
    /// With no social option the email button is the only one and keeps its original primary look and wording.
    public var emailIsOnlyOption: Bool { !apple && !google }
}

public enum SignInChoice: Sendable, Hashable {
    case apple, google, email
    public var provider: SocialProvider? {
        switch self { case .apple: .apple; case .google: .google; case .email: nil }
    }
}

public enum SignInFlow {
    /// Cognito can return an error containing this text for the first federated sign-in after an account link; trying again works.
    public static let linkQuirk = "Already found an entry for username"

    /// Runs one sign-in attempt, and repeats it ONCE if (and only if) it ended with the account-link quirk. A second quirk is thrown to the caller.
    public static func run(isolation: isolated (any Actor)? = #isolation, _ attempt: () async throws -> Void) async throws {
        do { try await attempt() }
        catch AuthError.accountLinkRetry { try await attempt() }
    }

    /// Plain words for the person; never provider or Cognito error text.
    public static func message(for error: Error) -> String? {
        switch error as? AuthError {
        case .cancelled: nil
        case .accountLinkRetry: tr("auth.link_retry")
        default: tr("auth.failed")
        }
    }

    /// After an explicit sign-out the next web sign-in uses a private session, so cookies left by the last person cannot sign the next one in silently.
    public static func useEphemeralSession(afterExplicitSignOut: Bool) -> Bool { afterExplicitSignOut }
}
