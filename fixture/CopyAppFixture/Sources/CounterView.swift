import SwiftUI

struct CounterView: View {
    @AppStorage("fixture.counter") private var count = 0

    var body: some View {
        VStack(spacing: 24) {
            Text("Counter: \(count)").font(.largeTitle)
            Button("Increment counter") { count += 1 }
                .buttonStyle(.borderedProminent)
            Button("Reset counter") { count = 0 }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .navigationTitle("Counter")
    }
}
