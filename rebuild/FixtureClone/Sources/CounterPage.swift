import SwiftUI

struct CounterPage: View {
    @AppStorage("fixture.counter") private var count = 0

    var body: some View {
        VStack(spacing: 20) {
            Text("Counter: \(count)")
                .font(.system(size: 34))
            Button("Increment counter") { count += 1 }
                .buttonStyle(.borderedProminent)
            Button("Reset counter") { count = 0 }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(uiColor: .systemBackground))
    }
}
