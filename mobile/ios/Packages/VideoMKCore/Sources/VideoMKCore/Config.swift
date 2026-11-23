import Foundation

/// Where the app talks to. Values come from the app's Info.plist (set per build configuration), never from code.
public struct AppConfig: Sendable, Equatable {
    public let apiBase: URL
    public let authDomain: URL
    public let clientID: String
    public let redirectURI: String
    public let callbackScheme: String

    public init(apiBase: URL, authDomain: URL, clientID: String, redirectURI: String = "com.videomk.app://auth/callback") {
        self.apiBase = apiBase
        self.authDomain = authDomain
        self.clientID = clientID
        self.redirectURI = redirectURI
        self.callbackScheme = URL(string: redirectURI)?.scheme ?? "com.videomk.app"
    }

    public static func fromBundle(_ bundle: Bundle = .main) -> AppConfig? {
        func value(_ key: String) -> String? {
            guard let s = bundle.object(forInfoDictionaryKey: key) as? String, !s.isEmpty, !s.hasPrefix("$(") else { return nil }
            return s
        }
        guard let api = value("VMKApiBase").flatMap(URL.init(string:)),
              let auth = value("VMKAuthDomain").flatMap(URL.init(string:)),
              let client = value("VMKClientID") else { return nil }
        return AppConfig(apiBase: api, authDomain: auth, clientID: client)
    }
}
