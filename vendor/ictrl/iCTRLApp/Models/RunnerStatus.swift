import Foundation

/// Live status of the automation server, probed over HTTP.
///
/// The server runs in the XCUITest runner — a separate process this app cannot
/// see into — so "is it running?" is answered by asking it, not by inspecting
/// local state. `/schema` is unauthenticated and cheap, and it carries the
/// version and capabilities, which is exactly what's worth showing.
@MainActor
final class RunnerStatus: ObservableObject {

    struct Info: Equatable {
        var serverVersion: String?
        var protocolVersion: Int?
        var capabilities: [String] = []
        var methodCount: Int?
    }

    enum State: Equatable {
        case unknown
        case checking
        case running(Info)
        case stopped
    }

    @Published private(set) var state: State = .unknown
    @Published private(set) var lastChecked: Date?

    private var pollTask: Task<Void, Never>?
    private let port: Int

    init(port: Int) { self.port = port }

    var isRunning: Bool { if case .running = state { return true }; return false }

    /// Poll while the view is on screen. The runner can be started or killed
    /// from outside this app (a URL scheme, a crash, iOS reclaiming it), so a
    /// one-shot check at appear would go stale while the user is looking at it.
    func startPolling(every seconds: TimeInterval = 3) {
        stopPolling()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.check()
                try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func check() async {
        if case .unknown = state { state = .checking }

        var request = URLRequest(url: URL(string: "http://127.0.0.1:\(port)/schema")!)
        // Short: this is a loopback call to a process on this device. Anything
        // slower than a moment means it isn't there.
        request.timeoutInterval = 2
        request.cachePolicy = .reloadIgnoringLocalCacheData

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                state = .stopped
                lastChecked = Date()
                return
            }
            var info = Info()
            info.serverVersion = json["server_version"] as? String
            info.protocolVersion = json["protocol_version"] as? Int
            info.capabilities = json["capability_tags"] as? [String] ?? []
            info.methodCount = (json["methods"] as? [Any])?.count
            state = .running(info)
        } catch {
            state = .stopped
        }
        lastChecked = Date()
    }
}
