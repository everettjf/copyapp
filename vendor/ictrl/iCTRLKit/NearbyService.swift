import Foundation
import Network
import dnssd

/// What a nearby (peer-to-peer Wi-Fi) client sees of this device: a stable
/// random identifier and a display name.
///
/// The identifier is generated once and kept in the app's sandbox next to the
/// pairing keys, so clients can recognise the same device although its AWDL
/// address changes. It is random — not derived from any hardware identifier.
///
/// iOS does not give apps the user-assigned device name, so the default name is
/// the hardware model plus the first four characters of the identifier; a
/// paired client can replace it (`config{device_name}`).
enum NearbyIdentity {
    private struct Stored: Codable {
        var id: String
        var name: String?
    }

    private static let lock = NSLock()
    private static var cached: Stored?

    private static var fileURL: URL? {
        let fm = FileManager.default
        guard let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return nil }
        let dir = base.appendingPathComponent("iCTRL", isDirectory: true)
        try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("nearby_identity.json")
    }

    private static func load() -> Stored {
        lock.lock(); defer { lock.unlock() }
        if let cached { return cached }
        if let url = fileURL, let data = try? Data(contentsOf: url),
           let stored = try? JSONDecoder().decode(Stored.self, from: data), stored.id.count == 32 {
            cached = stored
            return stored
        }
        var bytes = [UInt8](repeating: 0, count: 16)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        let fresh = Stored(id: bytes.map { String(format: "%02x", $0) }.joined(), name: nil)
        save(fresh)
        cached = fresh
        return fresh
    }

    private static func save(_ stored: Stored) {
        guard let url = fileURL, let data = try? JSONEncoder().encode(stored) else { return }
        try? data.write(to: url, options: .atomic)
    }

    /// 32 lowercase hex characters, stable for this installation.
    static var deviceID: String { load().id }

    /// The name advertised to nearby clients.
    static var name: String { load().name ?? defaultName }

    /// Whether `name` was set by a client rather than generated.
    static var hasCustomName: Bool { load().name != nil }

    static var defaultName: String { "\(modelName) (\(deviceID.prefix(4)))" }

    /// Longest name accepted: a DNS-SD instance name is one DNS label (63 bytes).
    static let maxNameBytes = 63

    /// Set a custom name; nil or blank restores the default. Returns the name in
    /// effect, or nil when the new name is too long.
    @discardableResult
    static func setName(_ newName: String?) -> String? {
        let trimmed = newName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard trimmed.utf8.count <= maxNameBytes else { return nil }
        var stored = load()
        stored.name = trimmed.isEmpty ? nil : trimmed
        lock.lock()
        cached = stored
        lock.unlock()
        save(stored)
        return stored.name ?? defaultName
    }

    /// Marketing name of the hardware, e.g. "iPhone 11"; the generic family
    /// name for identifiers this table does not know yet.
    static var modelName: String {
        var size = 0
        sysctlbyname("hw.machine", nil, &size, nil, 0)
        var raw = [CChar](repeating: 0, count: max(size, 1))
        sysctlbyname("hw.machine", &raw, &size, nil, 0)
        let machine = String(cString: raw)
        if let known = models[machine] { return known }
        if machine.hasPrefix("iPad") { return "iPad" }
        if machine.hasPrefix("iPod") { return "iPod touch" }
        return "iPhone"
    }

    private static let models: [String: String] = [
        "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max", "iPhone11,6": "iPhone XS Max",
        "iPhone11,8": "iPhone XR",
        "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro", "iPhone12,5": "iPhone 11 Pro Max",
        "iPhone12,8": "iPhone SE",
        "iPhone13,1": "iPhone 12 mini", "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro",
        "iPhone13,4": "iPhone 12 Pro Max",
        "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13", "iPhone14,2": "iPhone 13 Pro",
        "iPhone14,3": "iPhone 13 Pro Max", "iPhone14,6": "iPhone SE",
        "iPhone14,7": "iPhone 14", "iPhone14,8": "iPhone 14 Plus",
        "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
        "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus",
        "iPhone16,1": "iPhone 15 Pro", "iPhone16,2": "iPhone 15 Pro Max",
        "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus",
        "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max", "iPhone17,5": "iPhone 16e",
        "iPhone18,3": "iPhone 17", "iPhone18,1": "iPhone 17 Pro", "iPhone18,2": "iPhone 17 Pro Max",
        "iPhone18,4": "iPhone Air",
    ]
}

/// Advertises the device over Bonjour while nearby discovery is on: the
/// peer-to-peer listener on the AWDL interface, and the main listener on the
/// LAN (see `registerLAN`), so a first connection needs no typed address.
/// With nearby discovery off nothing is advertised anywhere.
///
/// The AWDL record is registered with the *specific* interface index of
/// `awdl0`, and must stay so: interface 0 or `kDNSServiceInterfaceIndexP2P`
/// with the AWDL flag would also put the peer-to-peer port on Wi-Fi/Ethernet
/// (dns_sd.h maps P2P on Register to "any interface, including P2P"), where
/// that listener refuses every connection anyway.
///
/// `awdl0` can exist while it is unusable (Wi-Fi off): a registration made
/// then never completes and never fails. So the interface's own state decides
/// whether to register, and it is re-checked every few seconds while enabled;
/// registration follows it both ways without the user doing anything.
final class NearbyAdvertiser {
    /// Why the device is or is not discoverable right now.
    enum Status: String {
        case off
        /// Registration sent, not yet confirmed.
        case starting
        case advertising
        /// No usable peer-to-peer interface: Wi-Fi is off (or the hardware has none).
        case needsWiFi = "needs_wifi"
        /// Refused by the system: Local Network access or the Bonjour declaration.
        case denied
        /// Any other registration error; retried periodically.
        case failed
    }

    /// The peer-to-peer interface as the system reports it.
    struct LinkState {
        var index: UInt32 = 0
        var up = false
        var running = false
        var linkLocal = false

        /// Whether a registration on it can complete.
        var usable: Bool { index != 0 && up && running }

        var json: JSONValue {
            .object(["index": .int(Int(index)), "up": .bool(up), "running": .bool(running),
                     "link_local": .bool(linkLocal)])
        }
    }

    private let port: UInt16
    /// The main (LAN) listener's port, advertised on the LAN while nearby
    /// discovery is on so a first connection needs no typed address.
    private let lanPort: UInt16
    private let queue: DispatchQueue
    private let log: (String) -> Void
    private var ref: DNSServiceRef?
    /// The awdl0 index `ref` was registered on. If the interface is rebuilt
    /// under a new index the old registration is silently dead.
    private var registeredIndex: UInt32 = 0
    private var lanRef: DNSServiceRef?
    private var lanRetryAt = Date.distantPast
    private var poll: DispatchSourceTimer?
    private var nextRetry = Date.distantPast
    private var stopped = true

    /// Called on `queue` whenever `status` changes.
    var onChange: ((Status) -> Void)?
    private(set) var status: Status = .off {
        didSet { if status != oldValue { onChange?(status) } }
    }
    var isAdvertising: Bool { status == .advertising }

    static let serviceType = "_ictrl._tcp"
    static let interfaceName = "awdl0"
    /// How often the interface is re-checked while enabled (a getifaddrs call).
    private static let pollInterval: TimeInterval = 5
    /// Back-off after a registration error before trying again.
    private static let retryInterval: TimeInterval = 30

    init(port: UInt16, lanPort: UInt16, queue: DispatchQueue, log: @escaping (String) -> Void) {
        self.port = port
        self.lanPort = lanPort
        self.queue = queue
        self.log = log
    }

    deinit {
        poll?.cancel()
        if let ref { DNSServiceRefDeallocate(ref) }
        if let lanRef { DNSServiceRefDeallocate(lanRef) }
    }

    func start() {
        queue.async {
            guard self.stopped else { return }
            self.stopped = false
            self.nextRetry = .distantPast
            self.lanRetryAt = .distantPast
            self.startPolling()
            self.evaluate()
        }
    }

    func stop() {
        queue.async {
            self.stopped = true
            self.poll?.cancel()
            self.poll = nil
            self.deregister()
            self.deregisterLAN()
            self.status = .off
        }
    }

    /// Re-register under the current `NearbyIdentity.name`.
    func refreshName() {
        queue.async {
            guard !self.stopped else { return }
            self.deregisterLAN()
            self.registerLAN()
            guard self.ref != nil else { return }
            self.deregister()
            let link = Self.linkState()
            if link.usable { self.register(index: link.index) } else { self.evaluate() }
        }
    }

    /// Check now instead of at the next poll (e.g. after a network change).
    func recheck() {
        queue.async { self.evaluate() }
    }

    /// Retry a refused registration now rather than after the back-off — for
    /// when the cause may just have been fixed (the permission prompt shown).
    func retryNow() {
        queue.async {
            self.nextRetry = .distantPast
            self.evaluate()
        }
    }

    /// Current state of `awdl0`.
    static func linkState() -> LinkState {
        var state = LinkState()
        state.index = if_nametoindex(interfaceName)
        guard state.index != 0 else { return state }
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let first = ifaddr else { return state }
        defer { freeifaddrs(ifaddr) }
        for ptr in sequence(first: first, next: { $0.pointee.ifa_next }) {
            let entry = ptr.pointee
            guard String(cString: entry.ifa_name) == interfaceName else { continue }
            state.up = state.up || entry.ifa_flags & UInt32(IFF_UP) != 0
            state.running = state.running || entry.ifa_flags & UInt32(IFF_RUNNING) != 0
            if let addr = entry.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET6) {
                state.linkLocal = true
            }
        }
        return state
    }

    // MARK: - On `queue`

    private func startPolling() {
        guard poll == nil else { return }
        let timer = DispatchSource.makeTimerSource(queue: queue)
        timer.schedule(deadline: .now() + Self.pollInterval, repeating: Self.pollInterval)
        timer.setEventHandler { [weak self] in self?.evaluate() }
        poll = timer
        timer.resume()
    }

    /// Bring the registration in line with the interface.
    private func evaluate() {
        guard !stopped else { return }
        if lanRef == nil, Date() >= lanRetryAt { registerLAN() }
        let link = Self.linkState()
        guard link.usable else {
            if status != .needsWiFi {
                log("📡 Nearby: \(Self.interfaceName) is not usable (index \(link.index), up \(link.up), running \(link.running)) — Wi-Fi off? Waiting for it")
            }
            deregister()
            status = .needsWiFi
            return
        }
        if ref != nil, link.index != registeredIndex {
            log("📡 Nearby: \(Self.interfaceName) is now index \(link.index) (was \(registeredIndex)) — registering again")
            deregister()
            register(index: link.index)
            return
        }
        switch status {
        case .advertising, .starting:
            return
        case .denied, .failed:
            guard Date() >= nextRetry else { return }
        case .off, .needsWiFi:
            break
        }
        register(index: link.index)
    }

    private func register(index: UInt32) {
        guard ref == nil else { return }
        var txt = TXTRecordRef()
        TXTRecordCreate(&txt, 0, nil)
        defer { TXTRecordDeallocate(&txt) }
        setTXT(&txt, "v", String(RPCMethodRegistry.protocolVersion))
        setTXT(&txt, "id", NearbyIdentity.deviceID)
        setTXT(&txt, "ch", "awdl")

        let name = NearbyIdentity.name
        var newRef: DNSServiceRef?
        // Unretained: the ref is always deallocated (on `queue`, or in deinit)
        // before this object goes away, and no callback is delivered after that.
        let context = Unmanaged.passUnretained(self).toOpaque()
        let err = DNSServiceRegister(
            &newRef, DNSServiceFlags(kDNSServiceFlagsIncludeAWDL), index,
            name, Self.serviceType, nil, nil, port.bigEndian,
            TXTRecordGetLength(&txt), TXTRecordGetBytesPtr(&txt),
            { _, _, errorCode, registeredName, _, _, context in
                guard let context else { return }
                let me = Unmanaged<NearbyAdvertiser>.fromOpaque(context).takeUnretainedValue()
                me.registrationCallback(errorCode, registeredName.map { String(cString: $0) })
            }, context)
        guard err == kDNSServiceErr_NoError, let newRef else {
            fail(err, "DNSServiceRegister failed")
            return
        }
        guard DNSServiceSetDispatchQueue(newRef, queue) == kDNSServiceErr_NoError else {
            DNSServiceRefDeallocate(newRef)
            fail(DNSServiceErrorType(kDNSServiceErr_Unknown), "could not attach to the dispatch queue")
            return
        }
        ref = newRef
        registeredIndex = index
        status = .starting
        log("📡 Nearby: registering \"\(name)\" on \(Self.interfaceName) (index \(index)), port \(port)")
    }

    private func registrationCallback(_ err: DNSServiceErrorType, _ registeredName: String?) {
        guard !stopped, ref != nil else { return }
        if err == kDNSServiceErr_NoError {
            log("📡 Nearby: advertised as \"\(registeredName ?? "?")\" on \(Self.interfaceName) only")
            status = .advertising
        } else {
            deregister()
            fail(err, "registration failed")
        }
    }

    private func fail(_ err: DNSServiceErrorType, _ what: String) {
        let denied = Int(err) == Int(kDNSServiceErr_NoAuth) || Int(err) == Int(kDNSServiceErr_PolicyDenied)
        log("📡 Nearby: \(what) (\(err))"
            + (denied ? " — Local Network access denied, or the service type is missing from NSBonjourServices" : "")
            + "; retrying in \(Int(Self.retryInterval))s")
        nextRetry = Date().addingTimeInterval(Self.retryInterval)
        status = denied ? .denied : .failed
    }

    // MARK: LAN

    /// Advertise the main listener on the ordinary (non peer-to-peer)
    /// interfaces: interface 0 without the AWDL/P2P flags, i.e. Wi-Fi and
    /// wired, never AWDL. Same name and device id as the AWDL record, port of
    /// the main listener, TXT ch=lan. Status reflects AWDL only; a LAN
    /// failure is logged and retried after the back-off.
    private func registerLAN() {
        guard !stopped, lanRef == nil else { return }
        var txt = TXTRecordRef()
        TXTRecordCreate(&txt, 0, nil)
        defer { TXTRecordDeallocate(&txt) }
        setTXT(&txt, "v", String(RPCMethodRegistry.protocolVersion))
        setTXT(&txt, "id", NearbyIdentity.deviceID)
        setTXT(&txt, "ch", "lan")

        var newRef: DNSServiceRef?
        let context = Unmanaged.passUnretained(self).toOpaque()
        let err = DNSServiceRegister(
            &newRef, 0, 0, NearbyIdentity.name, Self.serviceType, nil, nil, lanPort.bigEndian,
            TXTRecordGetLength(&txt), TXTRecordGetBytesPtr(&txt),
            { _, _, errorCode, registeredName, _, _, context in
                guard let context else { return }
                let me = Unmanaged<NearbyAdvertiser>.fromOpaque(context).takeUnretainedValue()
                me.lanRegistrationCallback(errorCode, registeredName.map { String(cString: $0) })
            }, context)
        guard err == kDNSServiceErr_NoError, let newRef,
              DNSServiceSetDispatchQueue(newRef, queue) == kDNSServiceErr_NoError else {
            if let newRef { DNSServiceRefDeallocate(newRef) }
            log("📡 Nearby: LAN registration failed (\(err)); retrying in \(Int(Self.retryInterval))s")
            lanRetryAt = Date().addingTimeInterval(Self.retryInterval)
            return
        }
        lanRef = newRef
    }

    private func lanRegistrationCallback(_ err: DNSServiceErrorType, _ registeredName: String?) {
        guard !stopped, lanRef != nil else { return }
        if err == kDNSServiceErr_NoError {
            log("📡 Nearby: also discoverable on the LAN as \"\(registeredName ?? "?")\", port \(lanPort)")
        } else {
            deregisterLAN()
            log("📡 Nearby: LAN registration failed (\(err)); retrying in \(Int(Self.retryInterval))s")
            lanRetryAt = Date().addingTimeInterval(Self.retryInterval)
        }
    }

    private func deregisterLAN() {
        if let lanRef { DNSServiceRefDeallocate(lanRef) }
        lanRef = nil
    }

    /// Drop the registration; callers set the resulting `status`.
    private func deregister() {
        if let ref { DNSServiceRefDeallocate(ref) }
        ref = nil
    }

    private func setTXT(_ txt: inout TXTRecordRef, _ key: String, _ value: String) {
        let bytes = Array(value.utf8.prefix(255))
        TXTRecordSetValue(&txt, key, UInt8(bytes.count), bytes)
    }
}
