import Foundation
import UIKit

/// File logging for the host app, one file per process.
///
/// Written because the interesting failures here happen on a device with no
/// debugger attached — a DDI mount that aborts inside a Rust FFI leaves nothing
/// behind but a crash report, and `print` goes nowhere once the app ships. One
/// file per PID keeps a crash-and-relaunch cycle from overwriting the very run
/// that failed, which is the one worth reading.
final class AppLog {
    static let shared = AppLog()

    /// Serial: several threads log (the mount runs on its own), and interleaved
    /// partial writes would corrupt exactly the file being relied on.
    private let queue = DispatchQueue(label: "com.copyapp.ictrl.applog")
    private let handle: FileHandle?
    private let formatter: DateFormatter

    let fileURL: URL?

    static var directory: URL? {
        guard let base = FileManager.default.urls(for: .libraryDirectory,
                                                  in: .userDomainMask).first else { return nil }
        let dir = base.appendingPathComponent("Logs/iCTRL", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private init() {
        formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss.SSS"

        let pid = ProcessInfo.processInfo.processIdentifier
        let stamp = ISO8601DateFormatter()
        stamp.formatOptions = [.withYear, .withMonth, .withDay, .withTime]
        let name = "ictrl-app-\(Self.launchStamp())-pid\(pid).log"

        guard let dir = Self.directory else {
            fileURL = nil
            handle = nil
            return
        }
        let url = dir.appendingPathComponent(name)
        FileManager.default.createFile(atPath: url.path, contents: nil)
        fileURL = url
        handle = try? FileHandle(forWritingTo: url)

        Self.pruneOldFiles()
        write(header())
    }

    private static func launchStamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd-HHmmss"
        return f.string(from: Date())
    }

    private func header() -> String {
        let d = UIDevice.current
        return """
        ── iCTRL app log ─────────────────────────────
        started : \(Date())
        pid     : \(ProcessInfo.processInfo.processIdentifier)
        device  : \(DeviceInfo.modelIdentifier) · \(d.systemName) \(d.systemVersion)
        app     : \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?") \
        (\(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"))
        ──────────────────────────────────────────────
        """
    }

    func log(_ message: String) {
        let line = "[\(formatter.string(from: Date()))] \(message)"
        #if DEBUG
        print(line)
        #endif
        write(line)
    }

    private func write(_ text: String) {
        guard let handle else { return }
        queue.async {
            if let data = (text + "\n").data(using: .utf8) {
                try? handle.write(contentsOf: data)
            }
        }
    }

    /// Every log on disk, newest first.
    static func allFiles() -> [URL] {
        guard let dir = directory,
              let urls = try? FileManager.default.contentsOfDirectory(
                  at: dir, includingPropertiesForKeys: [.contentModificationDateKey]) else { return [] }
        return urls.filter { $0.pathExtension == "log" }.sorted {
            let a = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            let b = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            return a > b
        }
    }

    /// Keep the last 20 runs. A per-PID file means one crash loop could
    /// otherwise fill the container with hundreds of near-empty logs.
    private static func pruneOldFiles(keeping limit: Int = 20) {
        let files = allFiles()
        guard files.count > limit else { return }
        for url in files.dropFirst(limit) {
            try? FileManager.default.removeItem(at: url)
        }
    }

    static func removeAll() {
        for url in allFiles() { try? FileManager.default.removeItem(at: url) }
    }
}

/// Shorthand, so logging a line stays cheap enough to actually do.
func ictrlLog(_ message: String) { AppLog.shared.log(message) }
