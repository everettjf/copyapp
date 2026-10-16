import SwiftUI

struct MainView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Spacer()

                ServerControlView()
                    .environmentObject(appState)

                if appState.isServerRunning && !appState.sessions.isEmpty {
                    SessionListView()
                        .environmentObject(appState)
                        .transition(.move(edge: .bottom).combined(with: .opacity))
                }

                Spacer()
            }
            .animation(.easeInOut(duration: 0.35), value: appState.sessions.count)
            .navigationTitle("iCTRL")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    NavigationLink {
                        SettingsView()
                            .environmentObject(appState)
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
        }
        .sheet(item: $appState.pendingAuthRequest) { request in
            AuthRequestView(request: request)
                .environmentObject(appState)
        }
    }
}

struct ServerControlView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 16) {
            if appState.isServerRunning {
                HStack(spacing: 8) {
                    Circle()
                        .fill(.green)
                        .frame(width: 10, height: 10)
                    Text("Running")
                        .font(.subheadline)
                        .foregroundColor(.green)
                }

                Text(appState.serverAddress)
                    .font(.system(.title3, design: .monospaced))
                    .foregroundColor(.secondary)

                VStack(spacing: 6) {
                    EndpointRow(label: "API Docs", path: "/", address: appState.serverAddress)
                    EndpointRow(label: "Schema", path: "/schema", address: appState.serverAddress)
                    EndpointRow(label: "Auth", path: "/auth", address: appState.serverAddress)
                    EndpointRow(label: "RPC", path: "/rpc", address: appState.serverAddress)
                }
                .padding(.top, 4)

                Button {
                    withAnimation { appState.stopServer() }
                } label: {
                    Text("Stop Server")
                        .font(.headline)
                        .frame(width: 200)
                        .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .tint(.red)

            } else {
                if let error = appState.serverError {
                    VStack(spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 36))
                            .foregroundColor(.orange)

                        Text("Failed to start")
                            .font(.headline)
                            .foregroundColor(.orange)

                        Text(error)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 32)

                        NavigationLink {
                            SettingsView()
                                .environmentObject(appState)
                        } label: {
                            Label("Go to Settings", systemImage: "gearshape")
                                .font(.subheadline)
                        }
                        .padding(.top, 4)
                    }
                    .padding(.bottom, 20)
                } else {
                    Image(systemName: "power")
                        .font(.system(size: 40))
                        .foregroundColor(.secondary.opacity(0.4))
                        .padding(.bottom, 4)
                }

                Button {
                    withAnimation { appState.startServer() }
                } label: {
                    Label("Start Server", systemImage: "power")
                        .font(.headline)
                        .frame(width: 200)
                        .padding(.vertical, 14)
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
            }
        }
        .padding(.vertical, 24)
    }
}

struct EndpointRow: View {
    let label: String
    let path: String
    let address: String
    @State private var copied = false

    private var url: String { "http://\(address)\(path)" }

    var body: some View {
        HStack(spacing: 6) {
            Text(label)
                .font(.caption)
                .foregroundColor(.secondary)
                .frame(width: 55, alignment: .trailing)

            Text(url)
                .font(.system(.caption, design: .monospaced))
                .foregroundColor(.primary.opacity(0.7))

            Button {
                UIPasteboard.general.string = url
                withAnimation { copied = true }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                    withAnimation { copied = false }
                }
            } label: {
                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    .font(.caption2)
                    .foregroundColor(copied ? .green : .secondary)
            }
            .buttonStyle(.plain)
        }
    }
}
