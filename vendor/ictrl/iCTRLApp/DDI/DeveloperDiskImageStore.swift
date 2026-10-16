import Foundation

/// The files a DDI mount needs, kept on disk.
///
/// Which files depends on the OS: up to iOS 26.3 the personalized image is
/// mounted through the image mounter; from iOS 26.4 the DDI is a cryptex,
/// installed through cryptexd from a different set of files. Each set lives in
/// its own directory, so an OS update that crosses 26.4 downloads the other
/// set instead of mounting files the device no longer accepts.
///
/// Not bundled in the app: the images change with Xcode releases, and most
/// users mounting a DDI already have network. Downloaded once and reused — the
/// mount itself is what needs to be repeated after a reboot, not the download.
@MainActor
final class DeveloperDiskImageStore: ObservableObject {

    enum MountMethod: String {
        /// iOS 17 – 26.3: image mounter, personalized image.
        case personalized
        /// iOS 26.4 and later: cryptexd installs the DDI cryptex.
        case cryptex

        /// Mirror folder, maintained by the pymobiledevice3 author. Apple does
        /// not publish these for direct download; the same content ships inside
        /// Xcode, so a user with a Mac can supply their own copy instead (see
        /// `importComponent`).
        var mirrorFolder: String {
            switch self {
            case .personalized: return "Xcode_iOS_DDI_Personalized"
            case .cryptex: return "Xcode_iOS_DDI_Cryptex"
            }
        }

        var components: [Component] {
            switch self {
            case .personalized: return [.buildManifest, .image, .trustCache]
            case .cryptex: return [.buildManifest, .image, .trustCache, .cryptexInfo, .rootHash]
            }
        }
    }

    /// The method this device's OS needs.
    nonisolated static var mountMethod: MountMethod {
        let v = ProcessInfo.processInfo.operatingSystemVersion
        return v.majorVersion > 26 || (v.majorVersion == 26 && v.minorVersion >= 4) ? .cryptex : .personalized
    }

    private static let mirrorBase =
        "https://github.com/doronz88/DeveloperDiskImage/raw/refs/heads/main/PersonalizedImages"

    enum Component: String, CaseIterable {
        case buildManifest = "BuildManifest.plist"
        case image = "Image.dmg"
        case trustCache = "Image.dmg.trustcache"
        case cryptexInfo = "Image.dmg.cryptex_info"
        case rootHash = "Image.dmg.root_hash"

        /// Download location for this device's mount method.
        var remoteURL: URL {
            URL(string: "\(DeveloperDiskImageStore.mirrorBase)/\(DeveloperDiskImageStore.mountMethod.mirrorFolder)/\(rawValue)")!
        }

        /// Share of the download, for a progress bar that moves with the bytes.
        var weight: Double {
            switch self {
            case .image: return 0.9
            case .buildManifest: return 0.07
            default: return 0.01
            }
        }
    }

    @Published private(set) var isDownloading = false
    @Published private(set) var progress: Double = 0
    @Published private(set) var statusMessage: String?

    private nonisolated static var rootDirectory: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DDI")
    }

    /// This device's file set. Builds before the cryptex split kept the
    /// personalized files directly in `DDI/`; they are moved into place
    /// rather than downloaded again.
    nonisolated static var directory: URL {
        let dir = rootDirectory.appendingPathComponent(mountMethod.mirrorFolder)
        migrateLegacyFiles(into: dir)
        return dir
    }

    private nonisolated static func migrateLegacyFiles(into dir: URL) {
        guard mountMethod == .personalized else { return }
        let fm = FileManager.default
        for c in MountMethod.personalized.components {
            let old = rootDirectory.appendingPathComponent(c.rawValue)
            guard fm.fileExists(atPath: old.path) else { continue }
            try? fm.createDirectory(at: dir, withIntermediateDirectories: true)
            let new = dir.appendingPathComponent(c.rawValue)
            if fm.fileExists(atPath: new.path) { try? fm.removeItem(at: old) } else { try? fm.moveItem(at: old, to: new) }
        }
    }

    nonisolated static func url(for component: Component) -> URL {
        directory.appendingPathComponent(component.rawValue)
    }

    /// True when every file of this device's set is present. Deliberately does
    /// not validate their contents — a corrupt image surfaces as a mount error,
    /// and guessing at validity here would just add a second place to be wrong.
    static var isComplete: Bool {
        mountMethod.components.allSatisfy {
            FileManager.default.fileExists(atPath: url(for: $0).path)
        }
    }

    static var totalBytesOnDisk: Int64 {
        mountMethod.components.reduce(0) { sum, c in
            let attrs = try? FileManager.default.attributesOfItem(atPath: url(for: c).path)
            return sum + ((attrs?[.size] as? Int64) ?? 0)
        }
    }

    func download() async throws {
        guard !isDownloading else { return }
        isDownloading = true
        progress = 0
        defer { isDownloading = false }

        try FileManager.default.createDirectory(at: Self.directory,
                                                withIntermediateDirectories: true)

        // Weight by size so the bar reflects reality: the image dwarfs the
        // rest, and an evenly-weighted bar would sit near the end for the
        // whole download.
        let components = Self.mountMethod.components
        let total = components.reduce(0) { $0 + $1.weight }
        var completed = 0.0

        for component in components {
            let dest = Self.url(for: component)
            let weight = component.weight / total
            if FileManager.default.fileExists(atPath: dest.path) {
                completed += weight
                progress = completed
                continue
            }
            statusMessage = "Downloading \(component.rawValue)…"
            try await download(component, to: dest) { [weak self] frac in
                Task { @MainActor in self?.progress = completed + frac * weight }
            }
            completed += weight
            progress = completed
        }
        statusMessage = nil
    }

    /// Generous limits: the mirror is GitHub, which can crawl and stall for
    /// long stretches on some networks, and the default 60s idle limit then
    /// fails the image partway.
    private static let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 120
        config.timeoutIntervalForResource = 60 * 60
        return URLSession(configuration: config)
    }()
    private static let downloadAttempts = 4

    /// Download one file, resuming from what already arrived when the
    /// connection drops (a Range request; a server that ignores it sends the
    /// whole file again, and the partial copy is discarded).
    private func download(_ component: Component, to dest: URL,
                          onProgress: @escaping (Double) -> Void) async throws {
        var data = Data()
        var expected: Int64 = -1
        var lastError: Error?
        for attempt in 1...Self.downloadAttempts {
            do {
                var request = URLRequest(url: component.remoteURL)
                if !data.isEmpty { request.setValue("bytes=\(data.count)-", forHTTPHeaderField: "Range") }
                let (bytes, response) = try await Self.session.bytes(for: request)
                guard let http = response as? HTTPURLResponse, http.statusCode == 200 || http.statusCode == 206 else {
                    throw DDIError.downloadFailed(component.rawValue,
                        (response as? HTTPURLResponse).map { "HTTP \($0.statusCode)" } ?? "no response")
                }
                if http.statusCode == 200 {
                    data = Data()
                    expected = response.expectedContentLength
                } else if expected < 0, response.expectedContentLength > 0 {
                    expected = Int64(data.count) + response.expectedContentLength
                }
                if expected > 0 { data.reserveCapacity(Int(expected)) }

                var lastReport = 0.0
                for try await byte in bytes {
                    data.append(byte)
                    if expected > 0 {
                        let frac = Double(data.count) / Double(expected)
                        // Reporting every byte would flood the main actor; 1% is
                        // plenty for a progress bar.
                        if frac - lastReport >= 0.01 {
                            lastReport = frac
                            onProgress(frac)
                        }
                    }
                }
                try data.write(to: dest, options: .atomic)
                ictrlLog("Downloaded \(component.rawValue) — \(data.count)B" + (attempt > 1 ? " (attempt \(attempt))" : ""))
                onProgress(1.0)
                return
            } catch let error as DDIError {
                throw error
            } catch {
                lastError = error
                ictrlLog("⚠️ \(component.rawValue) download interrupted at \(data.count)B (attempt \(attempt)): \(error.localizedDescription)")
                statusMessage = "Downloading \(component.rawValue)… (retrying, \(attempt)/\(Self.downloadAttempts - 1))"
            }
        }
        throw lastError ?? DDIError.downloadFailed(component.rawValue, "no response")
    }

    /// Accept a user-supplied copy, for people who'd rather pull the files out
    /// of their own Xcode than trust a third-party mirror.
    static func importComponent(_ component: Component, from url: URL) throws {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try Data(contentsOf: url)
        try data.write(to: self.url(for: component), options: .atomic)
    }

    static func removeAll() {
        try? FileManager.default.removeItem(at: rootDirectory)
    }
}
