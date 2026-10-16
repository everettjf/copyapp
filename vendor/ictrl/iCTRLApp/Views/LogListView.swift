import SwiftUI
import UIKit

/// Every log this app has written, one per run, newest first.
///
/// Exists so a failure that happened on a device with no debugger can leave with
/// the user: tap a run, read it, share it. The per-PID split is what makes that
/// useful — the run that crashed is still its own file after the relaunch.
struct LogListView: View {
    @State private var files = AppLog.allFiles()
    @State private var shareURL: ShareItem?
    @State private var confirmClear = false

    /// `sheet(item:)` wants Identifiable, and URL isn't.
    private struct ShareItem: Identifiable {
        let id = UUID()
        let url: URL
    }

    var body: some View {
        List {
            // The runner is a separate process with its own log; it is read
            // live over the runner's RPC rather than from a file here.
            Section {
                NavigationLink {
                    RunnerLogsView()
                } label: {
                    Label(L10n.t(.runnerLogs), systemImage: "dot.radiowaves.left.and.right")
                }
            } header: {
                Text(L10n.t(.runnerSection))
            }

            Section {
                if files.isEmpty {
                    Text("No logs yet.")
                        .foregroundColor(.secondary)
                }

                ForEach(files, id: \.self) { url in
                    NavigationLink {
                        LogDetailView(url: url)
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            HStack {
                                Text(Self.title(for: url))
                                if url == AppLog.shared.fileURL {
                                    Text("current")
                                        .font(.caption2)
                                        .padding(.horizontal, 6).padding(.vertical, 2)
                                        .background(Capsule().fill(Color.accentColor.opacity(0.15)))
                                        .foregroundColor(.accentColor)
                                }
                            }
                            Text(Self.subtitle(for: url))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .swipeActions {
                        Button("Share") { shareURL = ShareItem(url: url) }
                            .tint(.blue)
                    }
                }
            } header: {
                Text(L10n.t(.appLogsSection))
            }
        }
        .navigationTitle("Logs")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    if let current = AppLog.shared.fileURL {
                        Button {
                            shareURL = ShareItem(url: current)
                        } label: {
                            Label("Share current log", systemImage: "square.and.arrow.up")
                        }
                    }
                    Button(role: .destructive) {
                        confirmClear = true
                    } label: {
                        Label("Delete all logs", systemImage: "trash")
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
        .confirmationDialog("Delete all logs?", isPresented: $confirmClear, titleVisibility: .visible) {
            Button("Delete All", role: .destructive) {
                AppLog.removeAll()
                files = AppLog.allFiles()
            }
        } message: {
            Text("This removes every saved run, including the current one.")
        }
        .sheet(item: $shareURL) { item in
            ShareSheet(items: [item.url])
        }
        .onAppear { files = AppLog.allFiles() }
    }

    /// "Aug 15, 1:42 PM" — when the run happened, which is how you'd look for it.
    private static func title(for url: URL) -> String {
        let date = (try? url.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate)
        guard let date else { return url.lastPathComponent }
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    private static func subtitle(for url: URL) -> String {
        let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        let pid = url.lastPathComponent
            .split(separator: "-").last?
            .replacingOccurrences(of: ".log", with: "") ?? ""
        return "\(pid) · \(ByteCountFormatter.string(fromByteCount: Int64(size), countStyle: .file))"
    }
}

/// One log's contents.
private struct LogDetailView: View {
    let url: URL
    @State private var text = ""
    @State private var showShare = false

    var body: some View {
        ScrollView {
            Text(text.isEmpty ? "(empty)" : text)
                .font(.system(.caption, design: .monospaced))
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
                .padding()
        }
        .navigationTitle(url.lastPathComponent)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button { showShare = true } label: {
                    Image(systemName: "square.and.arrow.up")
                }
            }
        }
        .sheet(isPresented: $showShare) { ShareSheet(items: [url]) }
        .onAppear {
            text = (try? String(contentsOf: url, encoding: .utf8)) ?? "(unreadable)"
        }
    }
}

/// The system share sheet. Shares the file URL rather than its text, so the
/// receiving app gets a real .log attachment instead of a wall of pasted lines.
struct ShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
