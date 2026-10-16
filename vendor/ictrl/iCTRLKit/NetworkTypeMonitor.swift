import Foundation
import Network

/// Classifies the current default network path so callers can behave differently
/// on Wi-Fi vs cellular. On cellular the device's routable address is a
/// public/CGNAT address that is NOT reachable from outside and has no concept of
/// "Local Network" — so remote-access self-checks and the Local Network
/// permission prompt should be skipped there (they'd fail / be meaningless).
final class NetworkTypeMonitor {
    enum NetworkType: String {
        case wifi        // en0 / Wi-Fi — LAN reachable, Local Network applies
        case cellular    // pdp_ip / WWAN — public/CGNAT, not LAN-reachable
        case wired       // ethernet / USB
        case other       // loopback-only, VPN, or not yet determined
    }

    static let shared = NetworkTypeMonitor()

    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "com.copyapp.ictrl.netmonitor")
    private let lock = NSLock()
    private var cached: NetworkType = .other
    /// Set once the first path update lands. Until then `current` is a default,
    /// not an observation — the distinction matters to anything gating UI on it.
    private var hasResolved = false
    private var observers: [(NetworkType) -> Void] = []

    private init() {
        monitor.pathUpdateHandler = { [weak self] path in
            self?.update(from: path)
        }
        monitor.start(queue: queue)
    }

    private func update(from path: NWPath) {
        let type: NetworkType
        if path.usesInterfaceType(.wifi) {
            type = .wifi
        } else if path.usesInterfaceType(.cellular) {
            type = .cellular
        } else if path.usesInterfaceType(.wiredEthernet) {
            type = .wired
        } else {
            type = .other
        }
        lock.lock()
        cached = type
        hasResolved = true
        let toNotify = observers
        lock.unlock()
        for notify in toNotify { notify(type) }
    }

    /// True once a real path update has been seen. `current` before this is the
    /// initial default and should not be treated as an answer.
    var isResolved: Bool {
        lock.lock(); defer { lock.unlock() }
        return hasResolved
    }

    /// Observe changes. Fires immediately if a path has already been resolved, so
    /// a late subscriber isn't left waiting for the next change that may never
    /// come on a stable connection.
    func observe(_ handler: @escaping (NetworkType) -> Void) {
        lock.lock()
        observers.append(handler)
        let resolved = hasResolved
        let type = cached
        lock.unlock()
        if resolved { handler(type) }
    }

    /// Current network type. Reflects the most recent path update; the monitor is
    /// started at init so this is populated within a moment of launch.
    var current: NetworkType {
        lock.lock(); defer { lock.unlock() }
        return cached
    }

    /// True when the LAN is meaningful here (Wi-Fi or wired) — i.e. remote access
    /// self-checks and the Local Network permission make sense.
    var isLANReachable: Bool {
        switch current {
        case .wifi, .wired: return true
        case .cellular, .other: return false
        }
    }
}
