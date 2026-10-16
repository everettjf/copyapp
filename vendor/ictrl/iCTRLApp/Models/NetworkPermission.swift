import CoreTelephony
import Foundation
import Network
import UIKit

/// The two network permissions iCTRL depends on, probed at every launch.
///
/// Neither has an API that asks for it directly: iOS shows each prompt the
/// first time the app does the thing it covers. Probing at launch puts both
/// prompts on a fresh install's first screen, instead of in the middle of the
/// DDI setup, where a silent denial looks like a download or tunnel failure.
///
/// - Network data (mainland China models): "Allow iCTRL to use wireless data?"
///   appears on the first request leaving the device; until it is allowed the
///   app has no network at all, and the DDI download fails.
/// - Local Network: the DDI mount connects to the tunnel's private address,
///   which iOS gates behind it.
@MainActor
final class NetworkPermission: ObservableObject {
    enum Status: Equatable { case unknown, allowed, denied }

    @Published private(set) var networkData: Status = .unknown
    @Published private(set) var localNetwork: Status = .unknown

    /// Something denied: what the launch alert names.
    var denied: [String] {
        var out: [String] = []
        if networkData == .denied { out.append(L10n.t(.networkDataPermission)) }
        if localNetwork == .denied { out.append(L10n.t(.localNetworkPermission)) }
        return out
    }

    private let cellular = CTCellularData()
    private var browser: NWBrowser?

    func probe() {
        probeNetworkData()
        probeLocalNetwork()
    }

    private func probeNetworkData() {
        // Reports .restricted only where the per-app data switch exists and
        // is off; elsewhere it is .notRestricted.
        cellular.cellularDataRestrictionDidUpdateNotifier = { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                switch state {
                case .restricted: self.networkData = .denied
                case .notRestricted: self.networkData = .allowed
                default: break
                }
                ictrlLog("Network data permission: \(self.networkData)")
            }
        }
        // A tiny request to the host the DDI download uses: on a fresh install
        // this is what raises the prompt.
        var req = URLRequest(url: DeveloperDiskImageStore.Component.buildManifest.remoteURL, timeoutInterval: 10)
        req.httpMethod = "HEAD"
        URLSession.shared.dataTask(with: req) { _, resp, err in
            ictrlLog("Network probe: \((resp as? HTTPURLResponse)?.statusCode.description ?? err?.localizedDescription ?? "no answer")")
        }.resume()
    }

    private func probeLocalNetwork() {
        // Browsing for a Bonjour service is the documented way to raise the
        // Local Network prompt, and the browser reports a denial as a DNS
        // policy error. The service type must be listed in NSBonjourServices.
        let b = NWBrowser(for: .bonjour(type: "_ictrl._tcp", domain: nil), using: .tcp)
        b.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                guard let self else { return }
                switch state {
                case .ready:
                    self.localNetwork = .allowed
                case .waiting(let err), .failed(let err):
                    if case .dns(let code) = err, code == DNSServiceErrorType(kDNSServiceErr_PolicyDenied) {
                        self.localNetwork = .denied
                    }
                default:
                    return
                }
                ictrlLog("Local Network permission: \(self.localNetwork)")
            }
        }
        b.start(queue: .main)
        browser = b
        // Long enough for the user to answer the prompt; the state is kept.
        DispatchQueue.main.asyncAfter(deadline: .now() + 60) { [weak self] in
            self?.browser?.cancel()
            self?.browser = nil
        }
    }
}
