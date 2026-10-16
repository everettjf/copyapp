import Foundation

/// What this device has taught us about apps: name → bundle_id pairs learned
/// from App Store lookups, and which of those were actually opened here.
///
/// Exists because `list_apps` enumerates through LSApplicationWorkspace, which
/// iOS 26 answers with an empty list — so "what is installed" can no longer be
/// asked, only observed. Every successful launch_app/activate_app is exactly
/// such an observation, and every online resolve_app is a name mapping worth
/// not paying a network round-trip for twice.
///
/// Entries share AppBundles.plist's shape ({name, bundle_id, query, country})
/// so the two catalogs merge without translation; the extra keys say where an
/// entry came from and whether it has been seen installed.
///
/// Persisted in the runner's UserDefaults, so it survives runner restarts.
final class AppMemory {
    static let shared = AppMemory()

    private static let defaultsKey = "ictrl.learnedApps"
    /// Enough for every app a person realistically has plus a history of
    /// store lookups; past this the least recently touched entries go first.
    private static let maxEntries = 400

    private let lock = NSLock()
    private var entries: [String: [String: Any]]   // keyed by bundle_id

    private init() {
        let stored = UserDefaults.standard.array(forKey: Self.defaultsKey) as? [[String: Any]] ?? []
        var byId: [String: [String: Any]] = [:]
        for entry in stored {
            guard let bid = entry["bundle_id"] as? String, !bid.isEmpty else { continue }
            byId[bid] = entry
        }
        entries = byId
    }

    // MARK: - Recording

    /// An app was brought to the foreground here — proof it is installed.
    /// `name` is optional: the first launch may not be able to read it, and a
    /// later one (or a store lookup) fills it in.
    func recordOpened(bundleId: String, name: String?) {
        guard !bundleId.isEmpty else { return }
        let now = Date().timeIntervalSince1970
        mutate { entries in
            var e = entries[bundleId] ?? ["bundle_id": bundleId, "learned_at": now]
            if let name = name, !name.isEmpty { e["name"] = name }
            e["installed"] = true
            e["last_opened"] = now
            e["open_count"] = ((e["open_count"] as? Int) ?? 0) + 1
            e["touched_at"] = now
            entries[bundleId] = e
        }
    }

    /// The App Store says `name` is `bundleId`. Says nothing about this device,
    /// so it never sets `installed` — but it never clears it either.
    func recordResolved(bundleId: String, name: String, query: String, country: String) {
        guard !bundleId.isEmpty else { return }
        let now = Date().timeIntervalSince1970
        mutate { entries in
            var e = entries[bundleId] ?? ["bundle_id": bundleId, "learned_at": now]
            // A name read off the running app is what the home screen shows;
            // the store's trackName is a marketing title. Keep the former.
            if (e["name"] as? String ?? "").isEmpty { e["name"] = name }
            e["store_name"] = name
            e["query"] = query
            e["country"] = country
            e["touched_at"] = now
            entries[bundleId] = e
        }
    }

    /// launch_app was refused for this bundle id — it is not (or no longer)
    /// installed. The name mapping stays valid, so the entry is kept.
    func recordNotInstalled(bundleId: String) {
        mutate { entries in
            guard var e = entries[bundleId] else { return }
            e["installed"] = false
            e["touched_at"] = Date().timeIntervalSince1970
            entries[bundleId] = e
        }
    }

    /// Whether a readable name is already on file — lets launch skip the
    /// accessibility read after the first time.
    func hasName(_ bundleId: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        return !((entries[bundleId]?["name"] as? String) ?? "").isEmpty
    }

    // MARK: - Reading

    /// Entries matching `term`: substring on name / store name / query, exact
    /// on bundle_id (a substring on ids made "trip.com" match "ctrip.com"),
    /// installed-and-recent first.
    func lookup(_ term: String) -> [[String: Any]] {
        let t = term.lowercased()
        return sorted(snapshot().filter { e in
            ["name", "store_name", "query"].contains { key in
                (e[key] as? String)?.lowercased().contains(t) ?? false
            } || (e["bundle_id"] as? String)?.lowercased() == t
        })
    }

    /// The stored entry for one bundle id, if any.
    func entry(for bundleId: String) -> [String: Any]? {
        lock.lock(); defer { lock.unlock() }
        return entries[bundleId]
    }

    /// Apps seen opened on this device, most recently opened first.
    func openedApps() -> [[String: Any]] {
        sorted(snapshot().filter { ($0["installed"] as? Bool) == true })
    }

    // MARK: - Internals

    private func snapshot() -> [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        return Array(entries.values)
    }

    private func sorted(_ list: [[String: Any]]) -> [[String: Any]] {
        list.sorted { a, b in
            let ai = (a["installed"] as? Bool) == true, bi = (b["installed"] as? Bool) == true
            if ai != bi { return ai }
            let at = (a["last_opened"] as? Double) ?? (a["touched_at"] as? Double) ?? 0
            let bt = (b["last_opened"] as? Double) ?? (b["touched_at"] as? Double) ?? 0
            return at > bt
        }
    }

    private func mutate(_ change: (inout [String: [String: Any]]) -> Void) {
        lock.lock()
        change(&entries)
        if entries.count > Self.maxEntries {
            let oldest = entries.values
                .sorted { ($0["touched_at"] as? Double ?? 0) < ($1["touched_at"] as? Double ?? 0) }
                .prefix(entries.count - Self.maxEntries)
                .compactMap { $0["bundle_id"] as? String }
            oldest.forEach { entries.removeValue(forKey: $0) }
        }
        let stored = Array(entries.values)
        lock.unlock()
        UserDefaults.standard.set(stored, forKey: Self.defaultsKey)
    }
}
