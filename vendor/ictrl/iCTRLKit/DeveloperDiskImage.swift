import Foundation

/// Detects whether a Developer Disk Image is mounted on this device.
///
/// This exists for the main app, not the runner. `iCTRLUITests-Runner` links
/// XCTest.framework, which only exists once a DDI is mounted — so a runner that
/// is executing has already proven the answer is yes, and a runner without a DDI
/// dies in dyld before any code of ours runs. The main app has no such
/// dependency: it launches fine either way, which is exactly why it's the one
/// that has to tell the user whether the runner will start at all.
///
/// Detection is a plain file-existence check. Two alternatives were rejected:
/// weak-linking XCTest.framework pulls a developer-only framework into the
/// shipping app's link map and signature for no gain, and `dlopen` actually
/// loads the library, with side effects, when all we want is a yes/no. A status
/// readout must never be able to take the process down.
public enum DeveloperDiskImage {

    /// Where the DDI puts XCTest.framework, newest OS layout first.
    ///
    /// iOS 17 moved to personalized images under `/private/preboot/Cryptexes`;
    /// earlier releases mount at `/Developer`. Probing all three and reporting
    /// which one hit also tells us the mount style, not just the fact.
    public enum Layout: String, CaseIterable, Sendable {
        case cryptex, system, legacy

        public var frameworkPath: String {
            switch self {
            case .cryptex:
                return "/private/preboot/Cryptexes/OS/System/Developer/Library/Frameworks/XCTest.framework"
            case .system:
                return "/System/Developer/Library/Frameworks/XCTest.framework"
            case .legacy:
                return "/Developer/Library/Frameworks/XCTest.framework"
            }
        }
    }

    public struct Status: Sendable {
        /// A DDI providing XCTest.framework is mounted — the runner can launch.
        public let isMounted: Bool
        /// Which layout satisfied the probe, if any.
        public let layout: Layout?
        /// A developer directory exists even though XCTest.framework wasn't found
        /// under it. Distinguishes "Developer Mode was never enabled" from
        /// "enabled, but the image is gone" — the DDI does not survive a reboot
        /// on iOS 17+, and the two states need different advice.
        public let hasDeveloperDirectory: Bool

        public var summary: String {
            if isMounted { return "Mounted" }
            return hasDeveloperDirectory ? "Not mounted" : "Unavailable"
        }

        /// What the user should actually do about it.
        ///
        /// Points at the in-app mount rather than a Mac: the app can do this
        /// itself now, and telling someone to go find a Mac when the button is
        /// directly below would be worse than saying nothing.
        public var advice: String? {
            if isMounted { return nil }
            if hasDeveloperDirectory {
                return "Developer Mode is on, but the Developer Disk Image isn't mounted — "
                     + "a reboot drops it. Mount it below, or connect this device to a Mac with Xcode once."
            }
            return "Enable Developer Mode in Settings › Privacy & Security first, then mount the "
                 + "Developer Disk Image below (or connect this device to a Mac with Xcode once)."
        }
    }

    /// Probes the filesystem. Cheap enough to call on demand; nothing is cached,
    /// because the DDI can be unmounted while the app is running.
    public static func status() -> Status {
        let fm = FileManager.default
        let layout = Layout.allCases.first { fm.fileExists(atPath: $0.frameworkPath) }
        let hasDeveloperDir = ["/private/preboot/Cryptexes/OS/System/Developer",
                               "/System/Developer",
                               "/Developer"].contains { fm.fileExists(atPath: $0) }
        return Status(isMounted: layout != nil,
                      layout: layout,
                      hasDeveloperDirectory: hasDeveloperDir)
    }
}
