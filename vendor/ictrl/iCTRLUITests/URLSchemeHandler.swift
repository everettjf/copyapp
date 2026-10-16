import UIKit
import ObjectiveC.runtime

/// Captures `ictrl://` URLs delivered to the XCUITest runner.
///
/// The runner is hosted by Apple's private `_XCTRunnerAppDelegate`, so we can't
/// implement `application(_:open:options:)` the normal way. We add that method
/// to the delegate class; it forwards the URL to this singleton. The test body
/// drains `takeAllPendingURLs()` after the server is up.
///
/// Timing is the tricky part on a COLD start: iOS may deliver the launch URL
/// (and, if the device is locked / the developer must be trusted, only AFTER the
/// user types a passcode) before our test's setUp runs. To not lose it we:
///   1) install the hooks from a `+load`-style path, as early as the bundle loads,
///   2) also hook `application:didFinishLaunchingWithOptions:` to read the launch
///      URL out of launchOptions, and
///   3) QUEUE urls (not a single slot) so a second delivery can't overwrite a
///      first that hasn't been drained yet.
final class URLSchemeHandler {
    static let shared = URLSchemeHandler()

    static let scheme = "ictrl"

    private let lock = NSLock()
    private var pendingURLs: [URL] = []

    private init() {}

    /// Called when a fresh URL lands, so the test's run loop can drain it
    /// immediately instead of waiting for the next safety-timer tick.
    var onURLReceived: (() -> Void)?

    func record(_ url: URL) {
        guard url.scheme?.lowercased() == Self.scheme else { return }
        lock.lock()
        // De-dupe identical back-to-back deliveries (iOS sometimes double-delivers).
        if pendingURLs.last?.absoluteString != url.absoluteString {
            pendingURLs.append(url)
        }
        lock.unlock()
        iCTRLUITests.logBuffer.append("🔗 Received URL: \(url.scheme ?? "")://\(url.host ?? "")")

        // Wake the waiting run loop. It blocks on distantFuture, so without a
        // nudge a URL arriving at an already-running runner sat in the queue
        // until the 2s timer happened to fire — long enough that the callback
        // looked like it never came, and the user was left staring at a blank
        // XCTest screen.
        onURLReceived?()
    }

    /// Returns and clears ALL pending URLs (oldest first). Also pulls in anything
    /// the early Obj-C +load hook captured before our Swift hooks were installed
    /// (the cold-start launch URL).
    func takeAllPendingURLs() -> [URL] {
        Self.drainEarlyLogs()
        for u in EarlyURLHook.drainURLs() { record(u) }
        lock.lock()
        defer { lock.unlock() }
        let urls = pendingURLs
        pendingURLs.removeAll()
        return urls
    }

    /// Back-compat single-URL drain (returns the oldest pending, if any).
    func takePendingURL() -> URL? {
        lock.lock()
        defer { lock.unlock() }
        return pendingURLs.isEmpty ? nil : pendingURLs.removeFirst()
    }

    // MARK: - Delegate hook install

    /// The actual delegate hooks (openURL + launch options) are installed by the
    /// Obj-C `EarlyURLHook` at bundle +load — earlier than any Swift setUp — so we
    /// don't miss the cold-start launch URL. This drains anything it captured so
    /// far (URLs + its early log lines) into our pending queue / the log file.
    /// Safe to call repeatedly.
    static func installURLHandler() {
        drainEarlyLogs()
        for u in EarlyURLHook.drainURLs() { shared.record(u) }
        iCTRLUITests.logBuffer.append("🔗 ictrl:// URL capture active (early hooks)")
    }

    /// Flush +load-era log lines captured by EarlyURLHook into the persisted log.
    static func drainEarlyLogs() {
        for line in EarlyURLHook.drainLogs() {
            iCTRLUITests.logBuffer.append(line)
        }
    }
}
