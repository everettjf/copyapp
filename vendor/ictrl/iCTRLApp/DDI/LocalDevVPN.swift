import Foundation
import Network
import UIKit

/// Talking to LocalDevVPN, the app that makes this device's debug service
/// routable so the DDI mount can reach it.
///
/// It registers `localdevvpn://` and takes a callback scheme, so we can send the
/// user straight into "connect" and get them back — rather than telling them to
/// go find an app and return on their own.
enum LocalDevVPN {

    /// Bare scheme, used only as a `canOpenURL:` probe. The app's handler falls
    /// through to `default: break` for it, so probing can't cause side effects.
    static let probeURL = URL(string: "localdevvpn://")!

    /// Starts the tunnel, then returns to `ictrl-app://`.
    static let enableURL = URL(string: "localdevvpn://enable?scheme=ictrl-app")!

    static let appStoreURL = URL(string: "https://apps.apple.com/app/localdevvpn/id6755608044")!

    /// Whether LocalDevVPN is installed.
    ///
    /// Requires `localdevvpn` in this app's `LSApplicationQueriesSchemes` —
    /// without it iOS answers `false` no matter what is installed, which would
    /// silently send every user to the App Store.
    @MainActor
    static var isInstalled: Bool {
        UIApplication.shared.canOpenURL(probeURL)
    }

    enum TunnelProbe: Equatable {
        /// The device's own service answered through the tunnel.
        case reachable
        /// iOS refused the connection: Local Network access is off for iCTRL.
        case localNetworkDenied
        /// Nothing answered (tunnel down, or set to other addresses).
        case unreachable(String)
    }

    /// Whether the tunnel actually works: a TCP connection to the service the
    /// mount talks to.
    ///
    /// Not "is there a 10.7.0.x address": LocalDevVPN's addresses are
    /// user-configurable, another VPN can use the same range, and another
    /// app's tunnel interface is not always listed. A connection is exactly
    /// what the mount needs, and it tells a Local Network denial apart from
    /// "nothing there".
    static func probeTunnel(timeout: TimeInterval = 1.5) async -> TunnelProbe {
        let host = NWEndpoint.Host(DDIMounter.tunnelAddress)
        guard let port = NWEndpoint.Port(rawValue: DDIMounter.tunnelPort) else { return .unreachable("bad port") }
        let conn = NWConnection(host: host, port: port, using: .tcp)
        let queue = DispatchQueue(label: "ictrl.tunnel.probe")
        let result: TunnelProbe = await withCheckedContinuation { cont in
            var done = false
            func finish(_ r: TunnelProbe) {
                guard !done else { return }
                done = true
                conn.cancel()
                cont.resume(returning: r)
            }
            conn.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    finish(.reachable)
                case .waiting(let err), .failed(let err):
                    if #available(iOS 14.2, *), conn.currentPath?.unsatisfiedReason == .localNetworkDenied {
                        finish(.localNetworkDenied)
                    } else if case .waiting = state {
                        // Keep waiting: a refused connect retries until the timeout.
                        _ = err
                    } else {
                        finish(.unreachable(err.localizedDescription))
                    }
                default:
                    break
                }
            }
            conn.start(queue: queue)
            queue.asyncAfter(deadline: .now() + timeout) {
                if #available(iOS 14.2, *), conn.currentPath?.unsatisfiedReason == .localNetworkDenied {
                    finish(.localNetworkDenied)
                } else {
                    finish(.unreachable("no answer in \(timeout)s"))
                }
            }
        }
        ictrlLog("Tunnel probe \(DDIMounter.tunnelAddress):\(DDIMounter.tunnelPort) → \(result); interfaces: \(interfaceSummary())")
        return result
    }

    /// Every IPv4 address on an up interface, as "name address" — for the log
    /// and the screen when the tunnel can't be found.
    static func interfaceSummary() -> String {
        var head: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&head) == 0, let first = head else { return "unavailable" }
        defer { freeifaddrs(head) }
        var out: [String] = []
        for ptr in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let flags = Int32(ptr.pointee.ifa_flags)
            guard flags & IFF_UP != 0, let addr = ptr.pointee.ifa_addr,
                  addr.pointee.sa_family == UInt8(AF_INET) else { continue }
            var host = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            guard getnameinfo(addr, socklen_t(addr.pointee.sa_len), &host, socklen_t(host.count),
                              nil, 0, NI_NUMERICHOST) == 0 else { continue }
            let name = String(cString: ptr.pointee.ifa_name)
            if name == "lo0" { continue }
            out.append("\(name) \(String(cString: host))")
        }
        return out.isEmpty ? "none" : out.joined(separator: ", ")
    }
}
