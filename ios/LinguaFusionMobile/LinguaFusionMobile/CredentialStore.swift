import Foundation
import Security

enum CredentialStore {
    private static let service = "com.linguafusion.mobile"
    private static let account = "device-api-key"

    static func loadAPIKey() -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data,
              let value = String(data: data, encoding: .utf8) else { return "" }
        return value
    }

    static func loadOrMigrateAPIKey() -> String {
        let current = loadAPIKey()
        if !current.isEmpty { return current }
        let legacy = UserDefaults.standard.string(forKey: "apiKey")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !legacy.isEmpty else { return "" }
        if saveAPIKey(legacy) {
            UserDefaults.standard.removeObject(forKey: "apiKey")
            return legacy
        }
        return ""
    }

    @discardableResult static func saveAPIKey(_ value: String) -> Bool {
        deleteAPIKey()
        guard let data = value.data(using: .utf8) else { return false }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
            kSecValueData as String: data
        ]
        return SecItemAdd(query as CFDictionary, nil) == errSecSuccess
    }

    static func deleteAPIKey() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
