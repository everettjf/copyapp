// Bounded, structured guest observations for Copy APP. No shell or input synthesis.
import AppKit
import ApplicationServices
import CryptoKit
import Foundation
import IOKit

let protocolVersion = 2
let toolVersion = "0.1.2-macos-development"
let supportedMethods = ["health", "app_identity", "observe", "launch_app", "export_app", "package_identity"]
let fm = FileManager.default

struct Failure: Error, CustomStringConvertible {
    let description: String
    init(_ message: String) { description = message }
}

func sha256(_ path: URL) throws -> String {
    let file = try FileHandle(forReadingFrom: path)
    defer { try? file.close() }
    var hash = SHA256()
    var bytes: UInt64 = 0
    while let data = try file.read(upToCount: 1 << 20), !data.isEmpty {
        bytes += UInt64(data.count)
        guard bytes <= 8 << 30 else { throw Failure("File exceeds the hashing bound") }
        hash.update(data: data)
    }
    return hash.finalize().map { String(format: "%02x", $0) }.joined()
}

func json(_ value: Any) throws -> Data {
    try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
}

func readJSON(_ path: URL, limit: Int = 1 << 20) throws -> [String: Any] {
    let values = try path.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
    guard values.isRegularFile == true, values.isSymbolicLink != true, (values.fileSize ?? Int.max) <= limit,
          let object = try JSONSerialization.jsonObject(with: Data(contentsOf: path)) as? [String: Any]
    else { throw Failure("Invalid bounded JSON file") }
    return object
}

func writeJSON(_ value: [String: Any], to path: URL) throws {
    try fm.createDirectory(at: path.deletingLastPathComponent(), withIntermediateDirectories: true)
    try json(value).write(to: path, options: .atomic)
}

func machineID() -> String {
    let service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("IOPlatformExpertDevice"))
    guard service != 0 else { return "unavailable" }
    defer { IOObjectRelease(service) }
    return IORegistryEntryCreateCFProperty(service, kIOPlatformUUIDKey as CFString, kCFAllocatorDefault, 0)?
        .takeRetainedValue() as? String ?? "unavailable"
}

func appURL(_ params: [String: Any]) throws -> URL {
    guard let path = params["app_path"] as? String, path.hasPrefix("/"),
          let bundleID = params["bundle_id"] as? String, !bundleID.isEmpty else {
        throw Failure("An absolute app_path and exact bundle_id are required")
    }
    let url = URL(fileURLWithPath: path).resolvingSymlinksInPath().standardizedFileURL
    guard url.pathExtension == "app", let bundle = Bundle(url: url), bundle.bundleIdentifier == bundleID else {
        throw Failure("App path does not identify the requested bundle")
    }
    return url
}

func identity(_ params: [String: Any]) throws -> [String: Any] {
    let url = try appURL(params)
    guard let bundle = Bundle(url: url), let binary = bundle.executableURL else {
        throw Failure("App executable is unavailable")
    }
    let executable = binary.resolvingSymlinksInPath().standardizedFileURL
    guard executable.path.hasPrefix(url.path + "/") else { throw Failure("Executable escapes app bundle") }
    let hash = try sha256(executable)
    if let expected = params["binary_sha256"] as? String, expected != hash {
        throw Failure("Installed executable hash differs from requested build")
    }
    let running = NSRunningApplication.runningApplications(withBundleIdentifier: bundle.bundleIdentifier!).filter {
        $0.bundleURL?.resolvingSymlinksInPath().standardizedFileURL == url &&
        $0.executableURL?.resolvingSymlinksInPath().standardizedFileURL == executable
    }
    let processes: [[String: Any]] = running.map {
        ["pid": Int($0.processIdentifier), "started_at": $0.launchDate?.timeIntervalSince1970 as Any? ?? NSNull(),
         "cpu_type": Int($0.executableArchitecture), "active": $0.isActive, "terminated": $0.isTerminated]
    }
    var result: [String: Any] = [
        "bundle_id": bundle.bundleIdentifier!, "app_path": url.path,
        "executable_path": executable.path, "binary_sha256": hash,
        "info_plist_sha256": try sha256(url.appendingPathComponent("Contents/Info.plist")),
        "version": bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "",
        "build": bundle.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "",
        "processes": processes,
    ]
    if let pid = params["pid"] as? Int {
        guard let process = processes.first(where: { ($0["pid"] as? Int) == pid }) else {
            throw Failure("Requested PID does not execute this exact app build")
        }
        result["process"] = process
    }
    if let front = NSWorkspace.shared.frontmostApplication {
        result["foreground"] = ["pid": Int(front.processIdentifier),
            "bundle_id": front.bundleIdentifier as Any? ?? NSNull(),
            "app_path": front.bundleURL?.resolvingSymlinksInPath().standardizedFileURL.path as Any? ?? NSNull()]
    } else { result["foreground"] = NSNull() }
    return result
}

func attribute(_ element: AXUIElement, _ name: CFString) -> CFTypeRef? {
    var value: CFTypeRef?
    guard AXUIElementCopyAttributeValue(element, name, &value) == .success else { return nil }
    return value
}

func frame(_ element: AXUIElement) -> [String: Double]? {
    guard let position = attribute(element, kAXPositionAttribute as CFString),
          let size = attribute(element, kAXSizeAttribute as CFString),
          CFGetTypeID(position) == AXValueGetTypeID(), CFGetTypeID(size) == AXValueGetTypeID() else { return nil }
    let p = unsafeBitCast(position, to: AXValue.self), s = unsafeBitCast(size, to: AXValue.self)
    guard AXValueGetType(p) == .cgPoint, AXValueGetType(s) == .cgSize else { return nil }
    var point = CGPoint.zero, extent = CGSize.zero
    guard AXValueGetValue(p, .cgPoint, &point), AXValueGetValue(s, .cgSize, &extent),
          [point.x, point.y, extent.width, extent.height].allSatisfy({ $0.isFinite }) else { return nil }
    return ["x": point.x, "y": point.y, "width": extent.width, "height": extent.height]
}

func observe(_ params: [String: Any]) throws -> [String: Any] {
    guard AXIsProcessTrusted() else { throw Failure("Collector needs Accessibility permission in the guest") }
    guard let pid = params["pid"] as? Int, pid > 0, pid <= Int(Int32.max),
          params["binary_sha256"] is String else { throw Failure("Observe requires exact PID and executable hash") }
    let before = try identity(params)
    guard NSWorkspace.shared.frontmostApplication.map({ Int($0.processIdentifier) }) == pid else {
        throw Failure("Requested app is not foreground")
    }
    let root = AXUIElementCreateApplication(pid_t(pid))
    AXUIElementSetMessagingTimeout(root, 0.5)
    let focused = attribute(root, kAXFocusedWindowAttribute as CFString)
    let deadline = ProcessInfo.processInfo.systemUptime + 8
    var nodes: [[String: Any]] = [], visited: [AXUIElement] = []
    var truncated = false
    func string(_ element: AXUIElement, _ name: CFString) -> String? {
        guard let value = attribute(element, name) as? String else { return nil }
        if value.count > 4096 { truncated = true }
        return String(value.prefix(4096))
    }
    func visit(_ element: AXUIElement, parent: Int?, depth: Int) {
        guard nodes.count < 2000, depth <= 32, ProcessInfo.processInfo.systemUptime < deadline else {
            truncated = true; return
        }
        if visited.contains(where: { CFEqual($0, element) }) { return }
        visited.append(element)
        let id = nodes.count
        let role = string(element, kAXRoleAttribute as CFString) ?? "unknown"
        let subrole = string(element, kAXSubroleAttribute as CFString) ?? ""
        var node: [String: Any] = ["id": id, "parent": parent as Any? ?? NSNull(), "role": role,
                                   "subrole": subrole]
        for (key, name) in [("title", kAXTitleAttribute), ("description", kAXDescriptionAttribute),
                            ("identifier", kAXIdentifierAttribute)] {
            if let value = string(element, name as CFString) { node[key] = value }
        }
        if !subrole.lowercased().contains("secure"), role != "AXSecureTextField",
           let value = string(element, kAXValueAttribute as CFString) { node["value"] = value }
        if let rect = frame(element) { node["frame"] = rect }
        node["enabled"] = attribute(element, kAXEnabledAttribute as CFString) as? Bool ?? false
        nodes.append(node)
        let children = attribute(element, kAXChildrenAttribute as CFString) as? [AXUIElement] ?? []
        for child in children {
            if nodes.count >= 2000 || ProcessInfo.processInfo.systemUptime >= deadline { truncated = true; break }
            visit(child, parent: id, depth: depth + 1)
        }
    }
    visit(root, parent: nil, depth: 0)
    let after = try identity(params)
    guard try json(before) == json(after), NSWorkspace.shared.frontmostApplication.map({ Int($0.processIdentifier) }) == pid else {
        throw Failure("App identity or foreground changed during observation")
    }
    let focusedAfter = attribute(root, kAXFocusedWindowAttribute as CFString)
    if let focused, let focusedAfter, !CFEqual(focused, focusedAfter) {
        throw Failure("Focused window changed during observation")
    }
    let display = CGDisplayBounds(CGMainDisplayID())
    return ["app": before, "source_channel": "ax", "coordinate_space": "display_points",
            "display": ["x": display.minX, "y": display.minY, "width": display.width, "height": display.height],
            "focused_window_node": focused.flatMap { focus in visited.firstIndex(where: { CFEqual($0, focus) }) } as Any? ?? NSNull(),
            "nodes": nodes, "truncated": truncated]
}

func launchApp(_ params: [String: Any]) throws -> [String: Any] {
    guard params["binary_sha256"] is String else { throw Failure("Launch requires the acquired executable hash") }
    _ = try identity(params)
    let url = try appURL(params)
    let configuration = NSWorkspace.OpenConfiguration()
    configuration.activates = true
    configuration.createsNewApplicationInstance = false
    configuration.promptsUserIfNeeded = false
    var launched: NSRunningApplication?, failure: Error?
    NSWorkspace.shared.openApplication(at: url, configuration: configuration) { app, error in
        launched = app; failure = error
    }
    let deadline = ProcessInfo.processInfo.systemUptime + 20
    while launched == nil && failure == nil && ProcessInfo.processInfo.systemUptime < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }
    if let failure { throw failure }
    guard let launched else { throw Failure("Launch did not return a process within its deadline") }
    while NSWorkspace.shared.frontmostApplication?.processIdentifier != launched.processIdentifier &&
            ProcessInfo.processInfo.systemUptime < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
    }
    guard NSWorkspace.shared.frontmostApplication?.processIdentifier == launched.processIdentifier else {
        throw Failure("Launched process could not be verified as foreground")
    }
    var exact = params
    exact["pid"] = Int(launched.processIdentifier)
    return try identity(exact)
}

func bundleInventory(_ originalRoot: URL) throws -> [[String: Any]] {
    let root = originalRoot.resolvingSymlinksInPath().standardizedFileURL
    // Foundation may return /private/var children for a /var parent URL. Build
    // relative names while walking rather than slicing absolute path strings.
    var pending: [(URL, String)] = [(root, "")]
    var rows: [[String: Any]] = [], bytes: UInt64 = 0
    while let (directory, prefix) = pending.popLast() {
        for file in try fm.contentsOfDirectory(at: directory, includingPropertiesForKeys: nil) {
            let path = prefix.isEmpty ? file.lastPathComponent : prefix + "/" + file.lastPathComponent
            let values = try fm.attributesOfItem(atPath: file.path)
            let mode = (values[.posixPermissions] as? NSNumber)?.intValue ?? 0
            var row: [String: Any] = ["path": path, "mode": mode]
            switch values[.type] as? FileAttributeType {
            case .typeDirectory:
                row["kind"] = "directory"; pending.append((file, path))
            case .typeSymbolicLink:
                let target = try fm.destinationOfSymbolicLink(atPath: file.path)
                let resolved = file.resolvingSymlinksInPath().standardizedFileURL
                guard !target.hasPrefix("/"), resolved.path.hasPrefix(root.path + "/"),
                      fm.fileExists(atPath: resolved.path) else { throw Failure("Bundle symlink escapes or is dangling") }
                row["kind"] = "symlink"; row["target"] = target
            case .typeRegular:
                let size = (values[.size] as? NSNumber)?.uint64Value ?? 0
                bytes += size
                guard bytes <= 8 << 30 else { throw Failure("Bundle exceeds the 8 GiB acquisition bound") }
                row["kind"] = "file"; row["size"] = size; row["sha256"] = try sha256(file)
                let after = try fm.attributesOfItem(atPath: file.path)
                guard (after[.size] as? NSNumber) == (values[.size] as? NSNumber),
                      (after[.modificationDate] as? Date) == (values[.modificationDate] as? Date) else {
                    throw Failure("Bundle changed during inventory")
                }
            default: throw Failure("Unsupported bundle file kind")
            }
            rows.append(row)
            guard rows.count <= 40_000 else { throw Failure("Bundle exceeds the entry count bound") }
        }
    }
    return rows.sorted { ($0["path"] as! String).utf8.lexicographicallyPrecedes(($1["path"] as! String).utf8) }
}

func exportApp(_ params: [String: Any], output: URL, requestID: String) throws -> [String: Any] {
    guard params["binary_sha256"] is String else { throw Failure("Export requires the observed executable hash") }
    let source = try appURL(params), beforeIdentity = try identity(params)
    let before = try bundleInventory(source)
    let staging = output.appendingPathComponent(".export-" + requestID)
    let final = output.appendingPathComponent("exports/" + requestID)
    guard !fm.fileExists(atPath: staging.path), !fm.fileExists(atPath: final.path) else {
        throw Failure("An export attempt already exists; preserve it and use a new request")
    }
    let target = staging.appendingPathComponent(source.lastPathComponent)
    try fm.createDirectory(at: target, withIntermediateDirectories: true)
    let directories = before.filter { $0["kind"] as? String == "directory" }.sorted {
        ($0["path"] as! String).split(separator: "/").count < ($1["path"] as! String).split(separator: "/").count
    }
    for row in directories {
        try fm.createDirectory(at: target.appendingPathComponent(row["path"] as! String), withIntermediateDirectories: false)
    }
    for row in before {
        let relative = row["path"] as! String
        let destination = target.appendingPathComponent(relative)
        switch row["kind"] as! String {
        case "file":
            let input = try FileHandle(forReadingFrom: source.appendingPathComponent(relative))
            guard fm.createFile(atPath: destination.path, contents: nil) else { throw Failure("Cannot stage bundle file") }
            let writer = try FileHandle(forWritingTo: destination)
            do {
                var copied: UInt64 = 0
                let expected = row["size"] as! UInt64
                while let data = try input.read(upToCount: 1 << 20), !data.isEmpty {
                    copied += UInt64(data.count)
                    guard copied <= expected else { throw Failure("Source file grew during export") }
                    try writer.write(contentsOf: data)
                }
                guard copied == expected else { throw Failure("Source file shrank during export") }
                try input.close(); try writer.close()
            } catch { try? input.close(); try? writer.close(); throw error }
            try fm.setAttributes([.posixPermissions: row["mode"] as! Int], ofItemAtPath: destination.path)
        case "symlink":
            try fm.createSymbolicLink(atPath: destination.path, withDestinationPath: row["target"] as! String)
        default: break
        }
    }
    for row in directories.reversed() {
        try fm.setAttributes([.posixPermissions: row["mode"] as! Int],
                             ofItemAtPath: target.appendingPathComponent(row["path"] as! String).path)
    }
    guard try json(before) == json(bundleInventory(target)), try json(before) == json(bundleInventory(source)) else {
        throw Failure("Bundle snapshot did not match two source inventories")
    }
    let afterIdentity = try identity(params)
    for key in ["bundle_id", "app_path", "executable_path", "binary_sha256", "info_plist_sha256", "version", "build"] {
        guard (beforeIdentity[key] as? String) == (afterIdentity[key] as? String) else {
            throw Failure("App build changed during export")
        }
    }
    try fm.createDirectory(at: final.deletingLastPathComponent(), withIntermediateDirectories: true)
    try fm.moveItem(at: staging, to: final)
    let hash = SHA256.hash(data: try json(before)).map { String(format: "%02x", $0) }.joined()
    return ["source_app": beforeIdentity, "relative_path": "exports/" + requestID + "/" + source.lastPathComponent,
            "package_sha256": hash, "entry_count": before.count, "consistency": "matching_source_copy_source_inventories"]
}

final class Server {
    let shared: URL
    let instance = UUID().uuidString.lowercased()
    let executableHash: String
    let guestMachine = machineID()
    var busy = false
    init(shared: URL) throws {
        self.shared = shared.resolvingSymlinksInPath().standardizedFileURL
        executableHash = try sha256(URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath())
    }
    func poll() {
        guard !busy else { return }
        busy = true; defer { busy = false }
        do {
            let active = try readJSON(shared.appendingPathComponent("inbox/copyapp-bridge/active.json"))
            guard active["protocol_version"] as? Int == protocolVersion,
                  let session = active["session_id"] as? String, UUID(uuidString: session) != nil else { return }
            let requests = shared.appendingPathComponent("inbox/copyapp-bridge/" + session)
            let output = shared.appendingPathComponent("outbox/copyapp-bridge/" + session)
            for file in try fm.contentsOfDirectory(at: requests, includingPropertiesForKeys: nil).sorted(by: { $0.path < $1.path }) {
                guard file.pathExtension == "json", UUID(uuidString: file.deletingPathExtension().lastPathComponent) != nil else { continue }
                let id = file.deletingPathExtension().lastPathComponent
                let target = output.appendingPathComponent(id + ".json")
                if fm.fileExists(atPath: target.path) { continue }
                let request = try readJSON(file)
                guard request["session_id"] as? String == session,
                      request["request_id"] as? String == id,
                      request["protocol_version"] as? Int == protocolVersion else { continue }
                let hash = SHA256.hash(data: try json(request)).map { String(format: "%02x", $0) }.joined()
                var response: [String: Any] = ["protocol_version": protocolVersion,
                    "session_id": session, "request_id": id, "request_sha256": hash,
                    "collector_instance": instance, "collector_sha256": executableHash,
                    "guest_machine_id": guestMachine, "recorded_at": Date().timeIntervalSince1970]
                do {
                    guard request["collector_sha256"] as? String == executableHash else {
                        throw Failure("Collector build differs from requested hash")
                    }
                    if let expected = request["collector_instance"] as? String, expected != instance {
                        throw Failure("Collector restarted; create a new session")
                    }
                    let params = request["params"] as? [String: Any] ?? [:]
                    switch request["method"] as? String {
                    case "health":
                        response["result"] = ["tool_version": toolVersion, "guest_machine_id": guestMachine,
                            "os_version": ProcessInfo.processInfo.operatingSystemVersionString,
                            "accessibility_granted": AXIsProcessTrusted(), "pid": Int(getpid()),
                            "capabilities": supportedMethods]
                    case "app_identity": response["result"] = try identity(params)
                    case "observe": response["result"] = try observe(params)
                    case "export_app": response["result"] = try exportApp(params, output: output, requestID: id)
                    case "package_identity":
                        let source = try appURL(params), app = try identity(params)
                        let first = try bundleInventory(source), second = try bundleInventory(source)
                        guard try json(first) == json(second) else { throw Failure("Package changed between inventories") }
                        let hash = SHA256.hash(data: try json(first)).map { String(format: "%02x", $0) }.joined()
                        response["result"] = ["app": app, "package_sha256": hash, "entry_count": first.count,
                                              "consistency": "two_matching_inventories"]
                    case "launch_app":
                        let started = output.appendingPathComponent(id + ".started.json")
                        guard !fm.fileExists(atPath: started.path) else {
                            response["completion_unknown"] = true
                            throw Failure("Launch attempt already started; do not replay an interrupted action")
                        }
                        try writeJSON(["request_sha256": hash, "collector_instance": instance], to: started)
                        response["completion_unknown"] = true
                        response["result"] = try launchApp(params)
                        response.removeValue(forKey: "completion_unknown")
                    default: throw Failure("Unknown bounded collector method")
                    }
                    response["status"] = "complete"
                } catch {
                    response["status"] = "failed"
                    response["error"] = String(describing: error)
                }
                try writeJSON(response, to: target)
            }
        } catch { /* A half-created or unavailable share is retried on the next poll; no actions exist here. */ }
    }
}

if CommandLine.arguments.contains("--self-test") {
    print(String(data: try json(["protocol_version": protocolVersion, "methods": supportedMethods]), encoding: .utf8)!)
} else if let flag = CommandLine.arguments.firstIndex(of: "--shared-root"), CommandLine.arguments.count > flag + 1 {
    do {
        let server = try Server(shared: URL(fileURLWithPath: CommandLine.arguments[flag + 1]))
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        if CommandLine.arguments.contains("--request-accessibility") {
            let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
            _ = AXIsProcessTrustedWithOptions(options)
        }
        let timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { _ in server.poll() }
        RunLoop.main.add(timer, forMode: .common)
        app.run()
    } catch {
        fputs("Copy APP collector: \(error)\n", stderr)
        exit(1)
    }
} else {
    fputs("Usage: CopyAppMacCollector --shared-root '/Volumes/My Shared Files'\n", stderr)
    exit(2)
}
