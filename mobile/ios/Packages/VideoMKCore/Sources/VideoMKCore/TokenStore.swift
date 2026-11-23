import Foundation
import Security

public struct Tokens: Codable, Sendable, Equatable {
    public var idToken: String
    public var accessToken: String
    public var refreshToken: String?
    public var expiresAt: Date

    public init(idToken: String, accessToken: String, refreshToken: String?, expiresAt: Date) {
        self.idToken = idToken; self.accessToken = accessToken; self.refreshToken = refreshToken; self.expiresAt = expiresAt
    }
}

public protocol TokenStore: Sendable {
    func load() -> Tokens?
    func save(_ tokens: Tokens)
    func clear()
}

public final class InMemoryTokenStore: TokenStore, @unchecked Sendable {
    private let lock = NSLock()
    private var tokens: Tokens?
    public init(_ tokens: Tokens? = nil) { self.tokens = tokens }
    public func load() -> Tokens? { lock.withLock { tokens } }
    public func save(_ t: Tokens) { lock.withLock { tokens = t } }
    public func clear() { lock.withLock { tokens = nil } }
}

/// Tokens live only in the Keychain, readable after first unlock (so background refresh and push-triggered fetches work).
public struct KeychainTokenStore: TokenStore {
    private let service: String
    private let account = "tokens"
    public init(service: String = "com.videomk.app.auth") { self.service = service }

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
    }

    public func load() -> Tokens? {
        var q = baseQuery
        q[kSecReturnData as String] = true
        q[kSecMatchLimit as String] = kSecMatchLimitOne
        var out: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &out) == errSecSuccess, let data = out as? Data else { return nil }
        return try? JSONDecoder().decode(Tokens.self, from: data)
    }

    public func save(_ tokens: Tokens) {
        guard let data = try? JSONEncoder().encode(tokens) else { return }
        let update = [kSecValueData as String: data]
        if SecItemUpdate(baseQuery as CFDictionary, update as CFDictionary) == errSecItemNotFound {
            var add = baseQuery
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    public func clear() { SecItemDelete(baseQuery as CFDictionary) }
}
