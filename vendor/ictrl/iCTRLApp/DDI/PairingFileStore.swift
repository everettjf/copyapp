import Foundation
import UniformTypeIdentifiers

/// Where the device pairing record lives.
///
/// The pairing file is what `idevicepair pair` writes on a Mac: a plist holding
/// the host certificate and keys that let a client authenticate to this device's
/// `lockdownd`. Mounting a DDI needs one because the mount goes through the same
/// trusted channel Xcode would use.
///
/// Only its *path* matters to the mounting code — the plist is parsed by the
/// idevice library, never here.
enum PairingFileStore {

    /// Types the import picker accepts.
    ///
    /// `.fileImporter` matches a picked file's type against this list, and the
    /// match has to hold for the file's *actual* UTI. A pairing record is an
    /// XML property list, which iOS types as `public.xml` — a sibling of
    /// `public.data`, not a subtype, so `.data` alone does not let it through.
    ///
    /// Two traps made the old list miss real files:
    ///  * `UTType(filenameExtension:)` returns nil for `plist` /
    ///    `mobiledevicepairing` on iOS — no such UTI is registered — so those
    ///    entries silently vanished and the list collapsed to `.data`.
    ///  * A picker only enables what the list *contains*; `.xml` has to be
    ///    listed on its own because it is not covered by `.data`.
    ///
    /// So declare every type explicitly with `UTType(tag:tagClass:conformingTo:)`
    /// (which does not depend on a system-registered UTI) and keep `.data` last
    /// as the permissive catch-all. The file is validated after the pick anyway,
    /// so a wider list costs nothing but a clearer failure.
    static let supportedContentTypes: [UTType] = {
        var types: [UTType] = []

        // The standard property-list type (both XML and binary forms).
        types.append(.propertyList)
        // A pairing record is usually XML: iOS reports `public.xml`, and the
        // picker must be told about it explicitly.
        types.append(.xml)

        // Apple's tooling and the community write these extensions. Build the
        // types from their tags rather than by filename lookup, so they exist
        // even where the system has no UTI registered for the extension.
        for ext in ["mobiledevicepairing", "mobiledevicepair"] {
            if let t = UTType(tag: ext, tagClass: .filenameExtension,
                              conformingTo: .propertyList) {
                types.append(t)
            }
        }
        // A plain `.plist` extension, in case the file keeps it.
        if let t = UTType(tag: "plist", tagClass: .filenameExtension,
                          conformingTo: .propertyList) {
            types.append(t)
        }

        // Permissive catch-all: every file conforms to `.data`, so this keeps
        // the picker from greying out a record saved under an unexpected
        // extension. Content is validated by `validate(_:)` after import.
        types.append(.data)

        return types
    }()

    /// Application Support/Pairing/pairingFile.plist — outside Documents so it
    /// isn't casually deleted from the Files app, since losing it means
    /// re-pairing from a Mac.
    static var storedURL: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory,
                                            in: .userDomainMask)[0]
        return base.appendingPathComponent("Pairing/pairingFile.plist")
    }

    static var exists: Bool {
        FileManager.default.fileExists(atPath: storedURL.path)
    }

    /// When the current file was imported — shown in the UI so a stale pairing
    /// file (a common cause of confusing mount failures) is at least visible.
    static var importedAt: Date? {
        try? FileManager.default.attributesOfItem(atPath: storedURL.path)[.modificationDate] as? Date
    }

    /// Copy a user-picked file into place.
    ///
    /// The picker hands back a security-scoped URL that is only readable inside
    /// a start/stop pair, so the bytes are copied out immediately rather than
    /// holding the URL.
    static func importFile(from url: URL) throws {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }

        let data = try Data(contentsOf: url)
        try validate(data)

        let dest = storedURL
        try FileManager.default.createDirectory(at: dest.deletingLastPathComponent(),
                                                withIntermediateDirectories: true)
        // 0600 from the start: this file authenticates as a trusted host to the
        // device, so it deserves the same care as a private key.
        try data.write(to: dest, options: [.atomic, .completeFileProtection])
        try? FileManager.default.setAttributes([.posixPermissions: 0o600],
                                               ofItemAtPath: dest.path)
        ictrlLog("Pairing file imported (\(data.count)B)")
    }

    /// Posted after a pairing file is stored, so a screen showing the old
    /// state can refresh.
    static let didImport = Notification.Name("PairingFileStore.didImport")

    /// Store a file shared to the app ("Open in iCTRL"). iOS hands over a copy
    /// in an inbox folder of ours (Documents/Inbox, or tmp/<bundle id>-Inbox
    /// on newer systems), which is removed afterwards whatever the outcome.
    static func importShared(from url: URL) throws {
        defer {
            if url.deletingLastPathComponent().lastPathComponent.hasSuffix("Inbox") {
                try? FileManager.default.removeItem(at: url)
            }
        }
        try importFile(from: url)
        NotificationCenter.default.post(name: didImport, object: nil)
    }

    static func remove() {
        try? FileManager.default.removeItem(at: storedURL)
    }

    /// Reject anything that clearly isn't a pairing record, so the failure lands
    /// at import time with a clear message instead of surfacing later as an
    /// opaque error from deep inside the mount.
    private static func validate(_ data: Data) throws {
        guard let plist = try? PropertyListSerialization.propertyList(
                from: data, options: [], format: nil) as? [String: Any] else {
            throw DDIError.invalidPairingFile("Not a property list. Expected the file "
                + "`idevicepair pair` writes (a .plist / .mobiledevicepairing).")
        }
        // These are the fields a lockdown pairing record always carries.
        let required = ["HostID", "HostCertificate", "HostPrivateKey"]
        let missing = required.filter { plist[$0] == nil }
        guard missing.isEmpty else {
            throw DDIError.invalidPairingFile(
                "Missing \(missing.joined(separator: ", ")). This looks like a "
                + "property list but not a pairing record — re-export it with "
                + "`idevicepair pair` (libimobiledevice) or pymobiledevice3.")
        }
    }
}
