import SwiftUI

struct AuthRequestView: View {
    @EnvironmentObject var appState: AppState
    let request: AppState.PendingAuth
    @Environment(\.dismiss) var dismiss

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "person.badge.key.fill")
                .font(.system(size: 56))
                .foregroundColor(.blue)

            Text("Authorization Request")
                .font(.title2)
                .fontWeight(.bold)

            Text("**\(request.clientName)** is requesting access to control this device.")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
                .padding(.horizontal)

            Spacer()

            VStack(spacing: 12) {
                Button {
                    request.completion(true)
                    appState.refreshSessions()
                    dismiss()
                } label: {
                    Text("Allow")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                }
                .buttonStyle(.borderedProminent)

                Button {
                    request.completion(false)
                    dismiss()
                } label: {
                    Text("Deny")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                }
                .buttonStyle(.bordered)
                .tint(.red)
            }
            .padding(.horizontal)
            .padding(.bottom, 32)
        }
        .interactiveDismissDisabled()
    }
}
