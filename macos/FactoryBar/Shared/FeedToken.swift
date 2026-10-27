import Foundation
import Security

/// The feed's bearer token (FLEET_FEED_TOKEN on the server), kept in the Keychain rather than in the defaults.
enum FeedToken {
    private static let service = "dev.darkfactory.FactoryBar.feed-token"

    static func load() -> String? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                    kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        let token = String(decoding: data, as: UTF8.self)
        return token.isEmpty ? nil : token
    }

    /// Empty or nil removes it.
    static func save(_ token: String?) {
        let match: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service]
        SecItemDelete(match as CFDictionary)
        guard let token, !token.isEmpty else { return }
        var add = match
        add[kSecValueData as String] = Data(token.utf8)
        let status = SecItemAdd(add as CFDictionary, nil)
        if status != errSecSuccess { NSLog("FactoryBar: saving the feed token: \(status)") }
    }
}

/// `Authorization: Bearer <token>` when there is one.
func authorize(_ request: inout URLRequest, token: String?) {
    guard let token, !token.isEmpty else { return }
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
}
