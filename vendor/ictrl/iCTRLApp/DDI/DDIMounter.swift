import Foundation
import IDevice

enum DDIError: LocalizedError {
    case invalidPairingFile(String)
    case missingPairingFile
    case missingImage
    case tunnelUnavailable(String)
    case tunnelDown
    case localNetworkDenied
    case ffi(String, String)          // operation, message
    case downloadFailed(String, String)

    var errorDescription: String? {
        switch self {
        case .invalidPairingFile(let why):
            return "Pairing file rejected: \(why)"
        case .missingPairingFile:
            return "No pairing file imported yet."
        case .missingImage:
            return "Developer Disk Image files are missing — download them first."
        case .tunnelDown:
            return "LocalDevVPN isn't connected. The tunnel doesn't survive a reboot — "
                 + "open LocalDevVPN and connect it (step 1), then mount again."
        case .localNetworkDenied:
            return "iOS blocked the connection to the tunnel: Local Network access is off for iCTRL. "
                 + "Turn it on in Settings → Privacy & Security → Local Network (or Settings → iCTRL), then mount again."
        case .tunnelUnavailable(let why):
            return "Can't reach the device's debug service: \(why)"
        case .ffi(let op, let msg):
            return "\(op) failed: \(msg)"
        case .downloadFailed(let file, let why):
            return "Couldn't download \(file): \(why)"
        }
    }
}

/// Mounts the Developer Disk Image on this device, from this device.
///
/// The trick — and it is StikDebug's, ported here — is that no privileged
/// entitlement is involved. A local VPN app (LocalDevVPN / StosVPN) makes the
/// device's own `remoted` service routable at 10.7.0.1:49152, and this code then
/// talks to it as an ordinary network client, exactly as Xcode on a Mac would.
/// The pairing file is what authenticates that conversation.
///
/// All of the real work happens in the `idevice` Rust library (MIT); this is the
/// Swift side that sequences it.
@MainActor
final class DDIMounter: ObservableObject {

    /// Where LocalDevVPN/StosVPN publishes this device. Both use the same
    /// address, and it is not configurable in either app.
    static let tunnelAddress = "10.7.0.1"
    /// `remoted` — the RemotePairing service the tunnel exposes.
    static let tunnelPort: UInt16 = 49152

    enum Phase: Equatable {
        case idle
        case connecting
        case queryingDevice
        case uploading(Double)      // 0…1
        case finalizing
        case mounted
        case failed(String)
    }

    @Published private(set) var phase: Phase = .idle {
        didSet {
            // Progress ticks would flood the file; every other transition is
            // exactly the breadcrumb trail a failed mount needs.
            if case .uploading = phase { return }
            ictrlLog("DDI phase → \(phase)")
        }
    }

    var isRunning: Bool {
        switch phase {
        case .idle, .mounted, .failed: return false
        default: return true
        }
    }

    /// Mount the image. Long-running and blocking at the FFI layer, so the whole
    /// sequence runs off the main actor and only publishes back to it.
    func mount() async {
        guard !isRunning else { return }
        phase = .connecting

        do {
            guard PairingFileStore.exists else { throw DDIError.missingPairingFile }
            guard DeveloperDiskImageStore.isComplete else { throw DDIError.missingImage }
            // Check the tunnel before dialling it. Without this a disconnected
            // VPN surfaces as "device socket io failed", which names a socket
            // rather than the step the user has to fix — and the tunnel is down
            // after every reboot, so this is the common case, not an edge one.
            switch await LocalDevVPN.probeTunnel() {
            case .reachable: break
            case .localNetworkDenied: throw DDIError.localNetworkDenied
            case .unreachable: throw DDIError.tunnelDown
            }

            let pairingPath = PairingFileStore.storedURL.path
            let method = DeveloperDiskImageStore.mountMethod
            let imageDir = DeveloperDiskImageStore.directory.path

            // A dedicated Thread with an explicit stack, not a Task.
            //
            // The TSS request builds a reqwest client, whose TLS setup needs far
            // more stack than a Swift concurrency worker provides — it aborted
            // there (SIGABRT, panic inside ClientBuilder::build) on the first
            // real mount. StikDebug runs the same call on a plain Thread for the
            // same reason; 4MB is generous enough not to have to think about it.
            try await withCheckedThrowingContinuation { (cont: CheckedContinuation<Void, Error>) in
                let thread = Thread {
                    do {
                        try Self.performMount(pairingPath: pairingPath, method: method,
                                              imageDir: imageDir) { phase in
                            Task { @MainActor in self.phase = phase }
                        }
                        cont.resume()
                    } catch {
                        cont.resume(throwing: error)
                    }
                }
                thread.stackSize = 4 * 1024 * 1024
                thread.name = "ictrl.ddi.mount"
                thread.qualityOfService = .userInitiated
                thread.start()
            }

            phase = .mounted
        } catch {
            ictrlLog("❌ DDI mount failed: \(error.localizedDescription)")
            phase = .failed(error.localizedDescription)
        }
    }

    // MARK: - FFI

    /// Ask the device what images it already has mounted.
    ///
    /// iOS refuses a second mount with a bare "ImageMountFailed", so without
    /// this an already-mounted device reports a hard failure that reads like
    /// something is broken. StikDebug guards its mount the same way.
    ///
    /// Returns nil when the question can't be answered (no tunnel, no pairing
    /// file) — the caller should treat that as "unknown", not "not mounted".
    nonisolated static func mountedImageCount(adapter: OpaquePointer,
                                              handshake: OpaquePointer) -> Int? {
        var client: OpaquePointer?
        if let err = image_mounter_connect_rsd(adapter, handshake, &client) {
            idevice_error_free(err)
            return nil
        }
        guard let client else { return nil }
        defer { image_mounter_free(client) }

        var devices: UnsafeMutablePointer<plist_t?>?
        var count = 0
        if let err = image_mounter_copy_devices(client, &devices, &count) {
            idevice_error_free(err)
            return nil
        }
        if let devices { idevice_plist_array_free(devices, UInt(count)) }
        return count
    }

    /// Whether the DDI cryptex (iOS 26.4+) is installed. False when cryptexd
    /// can't be asked — an older OS has no such service.
    nonisolated static func cryptexDDIInstalled(adapter: OpaquePointer, handshake: OpaquePointer) -> Bool {
        var installed: UnsafeMutablePointer<InstalledCryptexC>?
        if let err = cryptexd_installed_ddi(adapter, handshake, &installed) {
            idevice_error_free(err)
        }
        defer { if let installed { cryptexd_free_installed_cryptex(installed) } }
        return installed != nil
    }

    /// Install the DDI as a cryptex (iOS 26.4+). cryptexd takes the whole
    /// restore directory — image, trust cache, manifest, cryptex info and root
    /// hash — and does the personalization itself, so there is no ECID to read
    /// and no upload progress to report.
    nonisolated private static func installCryptex(adapter: OpaquePointer, handshake: OpaquePointer,
                                                   imageDir: String,
                                                   report: @escaping (Phase) -> Void) throws {
        var assets: OpaquePointer?
        try check("Reading the DDI cryptex files") { cryptex1_assets_load(imageDir, &assets) }
        guard let assets else { throw DDIError.ffi("Reading the DDI cryptex files", "nothing loaded") }
        defer { cryptex1_assets_free(assets) }
        report(.uploading(0))
        try check("Installing the DDI cryptex") { cryptexd_install_ddi(adapter, handshake, assets, nil) }
        report(.finalizing)
    }


    /// Force the rustls crypto provider to be installed before anything needs it.
    ///
    /// The TSS request builds a reqwest client, and this library is compiled
    /// with `rustls-no-provider` — so if no process-default provider has been
    /// installed, `Client::new()` panics and aborts the app. The library only
    /// installs one from inside `start_session`, which the RSD path never calls
    /// (an RSD connection is already authenticated by the RemotePairing
    /// handshake — calling it there is what produced InvalidConnection).
    ///
    /// So we open a throwaway plain connection to the tunnel and start a session
    /// on it purely for that side effect. Both the connection and the session are
    /// expected to be short-lived; failures here are deliberately ignored,
    /// because the goal is the provider install, not the session.
    nonisolated static func primeCryptoProvider() {
        ictrlLog("Priming rustls crypto provider via a throwaway session")
        var pairing: OpaquePointer?
        guard idevice_pairing_file_read(PairingFileStore.storedURL.path, &pairing) == nil,
              let pairing else { return }
        defer { idevice_pairing_file_free(pairing) }

        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = tunnelPort.bigEndian
        guard tunnelAddress.withCString({ inet_pton(AF_INET, $0, &addr.sin_addr) }) == 1 else { return }

        var device: OpaquePointer?
        withUnsafePointer(to: &addr) { ptr in
            ptr.withMemoryRebound(to: idevice_sockaddr.self, capacity: 1) { sa in
                if let err = idevice_new_tcp_socket(sa, idevice_socklen_t(MemoryLayout<sockaddr_in>.size),
                                                    "iCTRL-crypto-prime", &device) {
                    idevice_error_free(err)
                }
            }
        }
        guard let device else { return }
        defer { idevice_free(device) }

        // The session itself may well fail — the provider is installed before
        // that can matter, which is the whole point of the call.
        if let err = idevice_start_session(device, pairing, false) {
            idevice_error_free(err)
        }
    }

    nonisolated private static func performMount(pairingPath: String,
                                                 method: DeveloperDiskImageStore.MountMethod,
                                                 imageDir: String,
                                                 report: @escaping (Phase) -> Void) throws {
        ictrlLog("DDI mount starting — \(method.rawValue) image from \(imageDir)")
        primeCryptoProvider()

        var pairing: OpaquePointer?
        try check("Reading pairing file") { rp_pairing_file_read(pairingPath, &pairing) }
        defer { if let pairing { rp_pairing_file_free(pairing) } }

        var addr = sockaddr_in()
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = tunnelPort.bigEndian
        guard tunnelAddress.withCString({ inet_pton(AF_INET, $0, &addr.sin_addr) }) == 1 else {
            throw DDIError.tunnelUnavailable("bad tunnel address")
        }

        var adapter: OpaquePointer?
        var handshake: OpaquePointer?
        try withUnsafePointer(to: &addr) { ptr in
            try ptr.withMemoryRebound(to: idevice_sockaddr.self, capacity: 1) { sa in
                try check("Connecting to the device") {
                    tunnel_create_rppairing(sa, idevice_socklen_t(MemoryLayout<sockaddr_in>.size),
                                            "iCTRL", pairing, nil, nil, &adapter, &handshake)
                }
            }
        }
        defer {
            if let handshake { rsd_handshake_free(handshake) }
            if let adapter { adapter_free(adapter) }
        }
        guard let adapter, let handshake else {
            throw DDIError.tunnelUnavailable("tunnel returned no handles")
        }

        report(.queryingDevice)

        // Already mounted? iOS answers a second mount with a bare
        // "ImageMountFailed", which reads like a real failure rather than
        // "nothing to do". Ask first and treat that case as success. Both
        // kinds are asked about whatever this OS uses: an image mounted by
        // Xcode, or before an OS update, counts just the same.
        if cryptexDDIInstalled(adapter: adapter, handshake: handshake) {
            ictrlLog("✅ The developer disk image cryptex is already installed — nothing to do")
            return
        }
        if let mounted = mountedImageCount(adapter: adapter, handshake: handshake) {
            ictrlLog("Device reports \(mounted) mounted image(s)")
            if mounted > 0 {
                ictrlLog("✅ A developer image is already mounted — nothing to do")
                return
            }
        }

        if method == .cryptex {
            try installCryptex(adapter: adapter, handshake: handshake, imageDir: imageDir, report: report)
            return
        }

        // Mapped, not read: the personalized image is about 100MB.
        let image = try Data(contentsOf: URL(fileURLWithPath: imageDir).appendingPathComponent("Image.dmg"),
                             options: .mappedIfSafe)
        let trustCache = try Data(contentsOf: URL(fileURLWithPath: imageDir).appendingPathComponent("Image.dmg.trustcache"))
        let manifest = try Data(contentsOf: URL(fileURLWithPath: imageDir).appendingPathComponent("BuildManifest.plist"))

        // The ECID identifies this specific device to Apple's signing service.
        // A personalized image is signed for one device and one nonce, which is
        // why this can't be pre-baked.
        let ecid = try uniqueChipID(adapter: adapter, handshake: handshake)

        var client: OpaquePointer?
        try check("Opening the image mounter") {
            image_mounter_connect_rsd(adapter, handshake, &client)
        }
        defer { if let client { image_mounter_free(client) } }
        guard let client else { throw DDIError.ffi("Opening the image mounter", "no client") }

        report(.uploading(0))

        // Progress arrives on a Rust thread; the context carries the callback so
        // no global state is involved.
        final class ProgressBox { let report: (Phase) -> Void; init(_ r: @escaping (Phase) -> Void) { report = r } }
        let box = Unmanaged.passRetained(ProgressBox(report))
        defer { box.release() }

        try image.withUnsafeBytes { img in
            try trustCache.withUnsafeBytes { tc in
                try manifest.withUnsafeBytes { mf in
                    try check("Mounting the image") {
                        image_mounter_mount_personalized_with_callback_rsd(
                            client, adapter, handshake,
                            img.bindMemory(to: UInt8.self).baseAddress, image.count,
                            tc.bindMemory(to: UInt8.self).baseAddress, trustCache.count,
                            mf.bindMemory(to: UInt8.self).baseAddress, manifest.count,
                            nil,
                            ecid,
                            { progress, total, context in
                                guard let context, total > 0 else { return }
                                let box = Unmanaged<ProgressBox>.fromOpaque(context).takeUnretainedValue()
                                box.report(.uploading(Double(progress) / Double(total)))
                            },
                            box.toOpaque())
                    }
                }
            }
        }
        report(.finalizing)
    }

    /// Read `UniqueChipID` (ECID) from lockdownd.
    nonisolated private static func uniqueChipID(adapter: OpaquePointer, handshake: OpaquePointer) throws -> UInt64 {
        var client: OpaquePointer?
        try check("Connecting to lockdownd") {
            lockdownd_connect_rsd(adapter, handshake, &client)
        }
        defer { if let client { lockdownd_client_free(client) } }
        guard let client else { throw DDIError.ffi("Connecting to lockdownd", "no client") }

        // No start_session here. A lockdownd client reached over the RSD tunnel
        // is already authenticated by the RemotePairing handshake, so opening a
        // second session on it is rejected — that is the InvalidConnection
        // (code 15) this used to fail with. WebDriverAgent's equivalent (and
        // StikDebug's) reads the value straight off the connected client.
        var value: plist_t?
        try check("Reading UniqueChipID") {
            lockdownd_get_value(client, "UniqueChipID", nil, &value)
        }
        defer { if let value { plist_free(value) } }
        guard let value else { throw DDIError.ffi("Reading UniqueChipID", "no value") }

        var ecid: UInt64 = 0
        plist_get_uint_val(value, &ecid)
        guard ecid != 0 else { throw DDIError.ffi("Reading UniqueChipID", "device returned 0") }
        return ecid
    }

    /// Turn an `IdeviceFfiError*` into a Swift error, freeing it either way.
    ///
    /// The FFI reports failure by returning a pointer that the caller owns —
    /// ignoring it leaks, and reading `.message` after freeing is a use-after-free,
    /// so the message is copied out before the free.
    @discardableResult
    nonisolated private static func check(_ operation: String,
                              _ call: () -> UnsafeMutablePointer<IdeviceFfiError>?) throws -> Bool {
        guard let err = call() else { return true }
        let message = err.pointee.message.map { String(cString: $0) } ?? "code \(err.pointee.code)"
        let code = err.pointee.code
        idevice_error_free(err)
        ictrlLog("❌ \(operation): \(message) (code \(code))")
        // "ImageMountFailed" is the device's own word for it and says nothing
        // about why, so attach what it usually means rather than passing a bare
        // string to someone with no way to look it up.
        var detail = "\(message) (code \(code))"
        if message.contains("device socket io failed") || message.contains("connect:") {
            detail += ". The tunnel isn't reachable — LocalDevVPN is most likely disconnected "
                    + "(it doesn't survive a reboot). Connect it and try again."
        }
        if message.contains("ImageMountFailed") {
            detail += ". The device rejected the image — usually because it doesn't match this "
                    + "iOS version, or the download is incomplete. Re-download the image files "
                    + "and try again; if it persists, this iOS build may be newer than the mirror."
        }
        throw DDIError.ffi(operation, detail)
    }
}
