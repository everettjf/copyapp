import SwiftUI
import UIKit

/// Shown in place of runner data until this app holds a key: explains the
/// one-time approval and starts it.
private struct RunnerConnectSection: View {
    @EnvironmentObject var admin: RunnerAdmin

    var body: some View {
        Section {
            Text(L10n.t(.connectRunnerBody))
                .font(.callout)
                .foregroundColor(.secondary)
            Button {
                Task { await admin.connect() }
            } label: {
                if admin.pairing {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text(L10n.t(.waitingApproval))
                    }
                } else {
                    Label(L10n.t(.connectButton), systemImage: "link")
                }
            }
            .disabled(admin.pairing)
        } header: {
            Text(L10n.t(.connectRunnerTitle))
        } footer: {
            NoticeText()
        }
    }
}

/// The last error, if any.
private struct NoticeText: View {
    @EnvironmentObject var admin: RunnerAdmin

    var body: some View {
        if let notice = admin.notice {
            Text(notice).foregroundColor(.orange)
        }
    }
}

/// "Visibility: 🟢 This device only · safe" and the like; tap to change it.
struct RunnerVisibilityRow: View {
    @EnvironmentObject var admin: RunnerAdmin
    let visibility: RunnerAdmin.Visibility

    private static let choices: [RunnerAdmin.Visibility] = [.local, .lan, .lanAndNearby]

    var body: some View {
        Menu {
            ForEach(Self.choices, id: \.self) { choice in
                Button {
                    Task { await admin.setVisibility(choice) }
                } label: {
                    if choice == visibility {
                        Label(Self.text(choice), systemImage: "checkmark")
                    } else {
                        Text(Self.text(choice))
                    }
                }
            }
        } label: {
            HStack {
                Text(L10n.t(.visibilityLabel))
                    .foregroundColor(.primary)
                Spacer()
                if admin.changingVisibility {
                    ProgressView().controlSize(.small)
                } else {
                    Text(visibility == .lanAndNearby && admin.nearbyPending
                         ? L10n.t(.visibilityNearbyPending) : Self.text(visibility))
                        .foregroundColor(.secondary)
                }
                Image(systemName: "chevron.up.chevron.down")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
        .disabled(admin.changingVisibility)
    }

    /// 🟢 only for loopback; anything another device can reach is 🟡.
    static func text(_ visibility: RunnerAdmin.Visibility) -> String {
        switch visibility {
        case .local: return L10n.t(.visibilityLocal)
        case .lan: return L10n.t(.visibilityLAN)
        case .lanAndNearby: return L10n.t(.visibilityLANNearby)
        }
    }
}

// MARK: - Authorized clients

/// Every client holding a key to the runner, with revocation.
struct RunnerClientsView: View {
    @EnvironmentObject var admin: RunnerAdmin
    @State private var pendingRevoke: RunnerAdmin.Client?
    @State private var confirmRevokeOthers = false
    @State private var confirmDisconnect = false

    var body: some View {
        List {
            if admin.isPaired {
                if let visibility = admin.visibility {
                    Section {
                        RunnerVisibilityRow(visibility: visibility)
                    }
                }
                clientsSection
                actionsSection
            } else {
                RunnerConnectSection()
            }
        }
        .navigationTitle(L10n.t(.authorizedClients))
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await admin.loadClients() }
        // Alerts, not confirmation dialogs: newer iOS draws a dialog as a
        // popover pointing at its anchor, which from a list points at the
        // wrong row — and one attached to a row is not shown after a swipe.
        .alert(String(format: L10n.t(.revokeConfirmTitle), pendingRevoke?.name ?? ""),
               isPresented: Binding(get: { pendingRevoke != nil }, set: { if !$0 { pendingRevoke = nil } }),
               presenting: pendingRevoke) { client in
            Button(L10n.t(.cancelButton), role: .cancel) {}
            Button(L10n.t(.revokeButton), role: .destructive) {
                Task { await admin.revoke(client.id) }
            }
        } message: { _ in
            Text(L10n.t(.revokeConfirmBody))
        }
        .alert(String(format: L10n.t(.revokeOthersConfirm), admin.otherClients.count),
               isPresented: $confirmRevokeOthers) {
            Button(L10n.t(.cancelButton), role: .cancel) {}
            Button(L10n.t(.revokeOthers), role: .destructive) {
                Task { await admin.revokeOthers() }
            }
        } message: {
            Text(L10n.t(.revokeConfirmBody))
        }
        .alert(L10n.t(.disconnectThisApp), isPresented: $confirmDisconnect) {
            Button(L10n.t(.cancelButton), role: .cancel) {}
            Button(L10n.t(.disconnectThisApp), role: .destructive) {
                Task { await admin.disconnect() }
            }
        } message: {
            Text(L10n.t(.disconnectConfirmBody))
        }
        // A new client can pair while this screen is open; keep it current.
        .task(id: admin.isPaired) {
            while !Task.isCancelled && admin.isPaired {
                await admin.loadClients()
                try? await Task.sleep(nanoseconds: 5_000_000_000)
            }
        }
    }

    private var clientsSection: some View {
        Section {
            if !admin.clientsLoaded && admin.notice == nil {
                HStack { Spacer(); ProgressView(); Spacer() }
            } else if admin.clients.isEmpty {
                Text(L10n.t(.noClients)).foregroundColor(.secondary)
            }
            ForEach(admin.clients) { client in
                ClientRow(client: client, isSelf: client.id == admin.ownSessionID)
                    .swipeActions {
                        if client.id != admin.ownSessionID {
                            Button(L10n.t(.revokeButton), role: .destructive) { pendingRevoke = client }
                        }
                    }
                    .contextMenu {
                        if client.id != admin.ownSessionID {
                            Button(role: .destructive) { pendingRevoke = client } label: {
                                Label(L10n.t(.revokeButton), systemImage: "xmark.circle")
                            }
                        }
                    }

            }
        } header: {
            Text(L10n.t(.authorizedClients))
        } footer: {
            VStack(alignment: .leading, spacing: 4) {
                NoticeText()
                Text(L10n.t(.clientsFooter))
            }
        }
    }

    private var actionsSection: some View {
        Section {
            if !admin.otherClients.isEmpty {
                Button(role: .destructive) { confirmRevokeOthers = true } label: {
                    Label(L10n.t(.revokeOthers), systemImage: "person.crop.circle.badge.xmark")
                }

            }
            Button(role: .destructive) { confirmDisconnect = true } label: {
                Label(L10n.t(.disconnectThisApp), systemImage: "personalhotspot.slash")
            }

        }
    }
}

private struct ClientRow: View {
    let client: RunnerAdmin.Client
    let isSelf: Bool

    /// The app ships no .lproj, so Foundation formats in English by default;
    /// follow the language the rest of the UI is shown in instead.
    private static let locale: Locale = {
        switch L10n.lang {
        case .zhHans: return Locale(identifier: "zh-Hans")
        case .zhHant: return Locale(identifier: "zh-Hant")
        default: return Locale.current
        }
    }()

    private static let relative: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .short
        f.dateTimeStyle = .named
        f.locale = locale
        return f
    }()

    private static let absolute: DateFormatter = {
        let f = DateFormatter()
        f.locale = locale
        f.dateStyle = .medium
        f.timeStyle = .short
        return f
    }()

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(client.name).lineLimit(1)
                if isSelf {
                    Text(L10n.t(.thisApp))
                        .font(.caption2)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(Color.accentColor.opacity(0.15)))
                        .foregroundColor(.accentColor)
                }
            }
            if let via = client.lastVia {
                HStack(spacing: 6) {
                    HStack(spacing: 3) {
                        Image(systemName: Self.sourceIcon(via))
                        Text(Self.sourceName(via))
                    }
                    .font(.caption.weight(.medium))
                    .foregroundColor(Self.sourceColor(via))
                    // Loopback says nothing useful ("127.0.0.1"); the source does.
                    if let address = client.lastAddress, via != PeerSource.local.rawValue {
                        Text(address)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                            .textSelection(.enabled)
                    }
                }
            }
            Text(subtitle)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 2)
    }

    private static func sourceName(_ via: String) -> String {
        switch PeerSource(rawValue: via) {
        case .local: return L10n.t(.viaLocal)
        case .lan: return L10n.t(.viaLAN)
        case .nearby: return L10n.t(.viaNearby)
        case .vpn: return L10n.t(.viaVPN)
        case .cellular: return L10n.t(.viaCellular)
        case .other, nil: return L10n.t(.viaOther)
        }
    }

    private static func sourceIcon(_ via: String) -> String {
        switch PeerSource(rawValue: via) {
        case .local: return "iphone"
        case .lan: return "wifi"
        case .nearby: return "dot.radiowaves.left.and.right"
        case .vpn: return "lock.shield"
        case .cellular: return "antenna.radiowaves.left.and.right"
        case .other, nil: return "network"
        }
    }

    private static func sourceColor(_ via: String) -> Color {
        switch PeerSource(rawValue: via) {
        case .local: return .secondary
        case .lan: return .blue
        case .nearby: return .purple
        case .vpn: return .orange
        default: return .secondary
        }
    }

    private var subtitle: String {
        var parts = [String]()
        if let granted = client.grantedAt {
            parts.append(String(format: L10n.t(.pairedAt), Self.absolute.string(from: granted)))
        }
        if let active = client.lastActiveAt {
            // Clamp: the runner's clock reading can be a moment ahead of ours.
            let now = Date()
            parts.append(String(format: L10n.t(.lastActive),
                                Self.relative.localizedString(for: min(active, now), relativeTo: now)))
        }
        parts.append(client.id)
        return parts.joined(separator: " · ")
    }
}

// MARK: - Runner log

/// The runner's recent log, pulled every 2 seconds while on screen.
struct RunnerLogsView: View {
    @EnvironmentObject var admin: RunnerAdmin
    @State private var live = true
    @State private var filter = ""
    @State private var refreshing = false
    @State private var shareItem: ShareText?

    private struct ShareText: Identifiable {
        let id = UUID()
        let text: String
    }

    private static let pollInterval: UInt64 = 2_000_000_000

    private var shownLines: [String] {
        filter.isEmpty ? admin.logLines : admin.logLines.filter { $0.localizedCaseInsensitiveContains(filter) }
    }

    var body: some View {
        Group {
            if admin.isPaired {
                logList
            } else {
                List { RunnerConnectSection() }
            }
        }
        .navigationTitle(L10n.t(.runnerLogs))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if admin.isPaired {
                ToolbarItemGroup(placement: .navigationBarTrailing) {
                    Button {
                        live.toggle()
                    } label: {
                        Image(systemName: live ? "pause.circle" : "play.circle")
                    }
                    .accessibilityLabel(live ? L10n.t(.pausedLabel) : L10n.t(.liveLabel))
                    Button {
                        Task { await refresh() }
                    } label: {
                        if refreshing { ProgressView().controlSize(.small) } else { Image(systemName: "arrow.clockwise") }
                    }
                    .disabled(refreshing)
                    Menu {
                        Button {
                            UIPasteboard.general.string = shownLines.joined(separator: "\n")
                        } label: {
                            Label(L10n.t(.copyButton), systemImage: "doc.on.doc")
                        }
                        Button {
                            shareItem = ShareText(text: shownLines.joined(separator: "\n"))
                        } label: {
                            Label("Share", systemImage: "square.and.arrow.up")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                    }
                }
            }
        }
        .sheet(item: $shareItem) { item in ShareSheet(items: [item.text]) }
        // Pull on entry, then keep pulling while the screen is visible. `.task`
        // is cancelled when the view goes away, which ends the polling.
        .task(id: admin.isPaired) {
            guard admin.isPaired else { return }
            await admin.loadLogs()
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: Self.pollInterval)
                if live && !Task.isCancelled { await admin.loadLogs() }
            }
        }
    }

    private var logList: some View {
        ScrollViewReader { proxy in
            List {
                Section {
                    if admin.logsLoaded && shownLines.isEmpty {
                        Text(L10n.t(.noLogLines)).foregroundColor(.secondary)
                    } else if !admin.logsLoaded && admin.notice == nil {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    }
                    ForEach(Array(shownLines.enumerated()), id: \.offset) { _, line in
                        Text(line)
                            .font(.system(.caption2, design: .monospaced))
                            .textSelection(.enabled)
                            .listRowInsets(EdgeInsets(top: 1, leading: 12, bottom: 1, trailing: 12))
                            .listRowSeparator(.hidden)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                        .listRowSeparator(.hidden)
                } header: {
                    // Above the lines, not in a footer: the bottom of the list
                    // sits under the search field.
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 6) {
                            Circle().fill(live ? Color.green : Color.secondary).frame(width: 7, height: 7)
                            Text(live ? L10n.t(.liveLabel) : L10n.t(.pausedLabel))
                            Spacer()
                            Text(verbatim: "\(shownLines.count)")
                        }
                        Text(L10n.t(.runnerLogsCaption))
                            .font(.caption2)
                            .textCase(nil)
                        NoticeText()
                            .font(.caption)
                            .textCase(nil)
                    }
                }
            }
            .listStyle(.plain)
            .environment(\.defaultMinListRowHeight, 0)
            .searchable(text: $filter, prompt: L10n.t(.filterPlaceholder))
            .refreshable { await refresh() }
            // Follow the newest line while live; a paused log stays where the
            // reader left it.
            .onChange(of: admin.logLines) { _ in
                guard live, filter.isEmpty else { return }
                proxy.scrollTo("bottom", anchor: .bottom)
            }
            .onAppear {
                DispatchQueue.main.async { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }

    private func refresh() async {
        refreshing = true
        await admin.loadLogs()
        refreshing = false
    }
}
