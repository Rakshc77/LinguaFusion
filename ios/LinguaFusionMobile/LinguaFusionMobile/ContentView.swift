import SwiftUI

struct ContentView: View {
    @State private var connectionError: String?
    @State private var reloadToken = 0

    var body: some View {
        ZStack {
            CloudWebView(reloadToken: reloadToken, onConnection: { connectionError = $0 })
                .ignoresSafeArea(.keyboard, edges: .bottom)
            if let connectionError {
                VStack(spacing: 16) {
                    Text("LinguaFusion is temporarily unavailable").font(.title2.bold())
                    Text(connectionError).multilineTextAlignment(.center).foregroundStyle(.secondary)
                    Button("Try again") { reloadToken += 1 }.buttonStyle(.borderedProminent)
                }
                .padding(28).frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Color(uiColor: .systemBackground))
            }
        }
            .onAppear {
                // The previous PC-pairing credential has no role in cloud mode.
                CredentialStore.deleteAPIKey()
                UserDefaults.standard.removeObject(forKey: "serverURL")
                UserDefaults.standard.removeObject(forKey: "apiKey")
            }
    }
}
