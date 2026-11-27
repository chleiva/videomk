import Foundation
import Testing
@testable import VideoMKCore

private func query(_ url: URL) -> [String: String] {
    Dictionary(uniqueKeysWithValues: URLComponents(url: url, resolvingAgainstBaseURL: false)!.queryItems!.map { ($0.name, $0.value ?? "") })
}

@Suite struct SocialAuthTests {
    private func auth() -> AuthService { AuthService(config: config, store: InMemoryTokenStore(), session: stubSession()) }

    @Test func providerValuesAreTheExactCognitoNames() {
        #expect(SocialProvider.apple.rawValue == "SignInWithApple" && SocialProvider.google.rawValue == "Google")
    }

    @Test func theAppsLanguagePassesThrough() async {
        let a = auth()
        #expect(query(await a.beginSignIn())["lang"] == nil)
        #expect(query(await a.beginSignIn(language: "es"))["lang"] == "es")
        for p in SocialProvider.allCases {
            let q = query(await a.beginSignIn(provider: p, language: "es"))
            #expect(q["lang"] == "es" && q["identity_provider"] == p.rawValue)
        }
    }

    @Test func socialURLAddsOnlyTheProviderParameter() async {
        let a = auth()
        let plain = query(await a.beginSignIn())
        #expect(plain["identity_provider"] == nil)
        for p in SocialProvider.allCases {
            let url = await a.beginSignIn(provider: p)
            let q = query(url)
            #expect(q["identity_provider"] == p.rawValue)
            #expect(Set(q.keys).subtracting(plain.keys) == ["identity_provider"])
            #expect(url.path == "/oauth2/authorize" && q["response_type"] == "code" && q["code_challenge_method"] == "S256")
            #expect(q["redirect_uri"] == "com.videomk.app://auth/callback" && q["scope"] == "openid email profile")
            #expect(q["state"]?.count ?? 0 >= 43 && q["code_challenge"]?.count == 43)
        }
    }

    @Test func everyAttemptHasFreshStateAndChallenge() async {
        let a = auth()
        let one = query(await a.beginSignIn(provider: .google)), two = query(await a.beginSignIn(provider: .google))
        #expect(one["state"] != two["state"] && one["code_challenge"] != two["code_challenge"])
    }

    @Test func aCallbackWithoutOrWithWrongStateIsRejectedEvenWhenItIsAnError() async {
        for tail in ["code=c", "code=c&state=forged", "error=access_denied", "error=invalid_request&error_description=Already+found+an+entry+for+username+x&state=forged"] {
            let a = auth()
            _ = await a.beginSignIn(provider: .apple)
            await #expect(throws: AuthError.failed) { try await a.completeSignIn(callback: URL(string: "com.videomk.app://auth/callback?\(tail)")!) }
        }
    }

    @Test func theLinkQuirkIsRecognisedAndOtherErrorsAreNot() async {
        func outcome(_ tail: String) async -> AuthError? {
            let a = auth()
            let state = query(await a.beginSignIn(provider: .google))["state"]!
            do { try await a.completeSignIn(callback: URL(string: "com.videomk.app://auth/callback?\(tail)&state=\(state)")!); return nil }
            catch { return error as? AuthError }
        }
        #expect(await outcome("error=invalid_request&error_description=Already%20found%20an%20entry%20for%20username%20Google_123") == .accountLinkRetry)
        #expect(await outcome("error=access_denied") == .cancelled)
        #expect(await outcome("error=server_error&error_description=boom") == .failed)
    }

    @Test func theQuirkIsRetriedExactlyOnce() async throws {
        nonisolated(unsafe) var attempts = 0
        try await SignInFlow.run { attempts += 1; if attempts == 1 { throw AuthError.accountLinkRetry } }
        #expect(attempts == 2)

        attempts = 0
        await #expect(throws: AuthError.accountLinkRetry) { try await SignInFlow.run { attempts += 1; throw AuthError.accountLinkRetry } }
        #expect(attempts == 2, "never a third try")

        attempts = 0
        await #expect(throws: AuthError.cancelled) { try await SignInFlow.run { attempts += 1; throw AuthError.cancelled } }
        #expect(attempts == 1, "other errors are not retried")

        attempts = 0
        try await SignInFlow.run { attempts += 1 }
        #expect(attempts == 1)
    }

    @Test func messagesAreClearAndCancelIsSilent() {
        #expect(SignInFlow.message(for: AuthError.cancelled) == nil)
        #expect(SignInFlow.message(for: AuthError.accountLinkRetry)?.contains("tap the button again") == true)
        #expect(SignInFlow.message(for: AuthError.failed)?.contains("couldn't sign you in") == true)
    }

    @Test func everythingIsOffByDefault() {
        #expect(AuthOptions.off == AuthOptions() && AuthOptions().choices == [.email] && AuthOptions().emailIsOnlyOption)
        for s in [nil, "", "NO", "0", "$(VMK_AUTH_APPLE)", "maybe"] { #expect(!AuthOptions.parse(s)) }
        for s in ["YES", "yes", "1", "true"] { #expect(AuthOptions.parse(s)) }
        #expect(!AuthOptions.fromBundle(Bundle(for: StubProtocol.self)).apple)   // a bundle without the keys
    }

    @Test func buttonsRenderOnlyWhenSwitchedOnAppleFirst() {
        #expect(AuthOptions(apple: true).choices == [.apple, .email])
        #expect(AuthOptions(google: true).choices == [.google, .email])
        #expect(AuthOptions(apple: true, google: true).choices == [.apple, .google, .email])
        #expect(!AuthOptions(google: true).emailIsOnlyOption)
        #expect(SignInChoice.apple.provider == .apple && SignInChoice.google.provider == .google && SignInChoice.email.provider == nil)
    }

    @Test func privateSessionAfterExplicitSignOutOnly() {
        #expect(SignInFlow.useEphemeralSession(afterExplicitSignOut: true) && !SignInFlow.useEphemeralSession(afterExplicitSignOut: false))
    }
}
