import SwiftUI

struct SessionListView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Connected Sessions")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Revoke All") {
                    withAnimation { appState.revokeAllSessions() }
                }
                .font(.caption)
                .foregroundColor(.red)
            }
            .padding(.horizontal)

            ForEach(appState.sessions) { session in
                SessionRow(session: session) {
                    withAnimation { appState.revokeSession(id: session.id) }
                }
            }
        }
        .padding(.top, 12)
        .onAppear {
            appState.refreshSessions()
        }
    }
}

struct SessionRow: View {
    let session: AuthSession
    let onRevoke: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(.green)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                Text(session.clientName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                Text(formatRelative(session.lastActiveAt))
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }

            Spacer()

            Button {
                onRevoke()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.secondary.opacity(0.5))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
        .padding(.horizontal)
    }

    private func formatRelative(_ date: Date) -> String {
        let interval = Date().timeIntervalSince(date)
        if interval < 60 { return "Active now" }
        if interval < 3600 { return "\(Int(interval / 60))m ago" }
        if interval < 86400 { return "\(Int(interval / 3600))h ago" }
        return "\(Int(interval / 86400))d ago"
    }
}
