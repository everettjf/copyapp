import Foundation

/// File-backed store for persisting auth sessions across launches.
///
/// Replaces the Keychain store: the XCTest runner is re-signed by the OTA
/// distribution service, which changes the keychain-access-group (team prefix)
/// and made previously-issued tokens unreadable after a re-install. A plain file
/// in the app's Application Support directory survives launches/reinstalls of the
/// same container and doesn't depend on the signing identity.
enum TokenFileStore {
    /// <sandbox>/Library/Application Support/iCTRL/auth_sessions.json
    private static var fileURL: URL? {
        let fm = FileManager.default
        guard let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            return nil
        }
        let dir = base.appendingPathComponent("iCTRL", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("auth_sessions.json")
    }

    static func save(_ data: Data) {
        guard let url = fileURL else { return }
        // Write atomically; exclude from iCloud backup (device-local secret).
        try? data.write(to: url, options: .atomic)
        var u = url
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try? u.setResourceValues(values)
    }

    static func load() -> Data? {
        guard let url = fileURL else { return nil }
        return try? Data(contentsOf: url)
    }

    static func clear() {
        guard let url = fileURL else { return }
        try? FileManager.default.removeItem(at: url)
    }
}
