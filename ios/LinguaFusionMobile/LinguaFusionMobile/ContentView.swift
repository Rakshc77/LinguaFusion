import SwiftUI
import UIKit

struct ContentView: View {
    @AppStorage("serverURL") private var savedServer = ""
    @State private var savedKey = CredentialStore.loadOrMigrateAPIKey()
    @State private var server = ""
    @State private var key = ""
    @State private var connecting = false
    @State private var errorMessage = ""
    @State private var backendUnavailable = false
    @State private var offlineReason = ""

    var body: some View {
        Group {
            if savedServer.isEmpty { pairingView }
            else if backendUnavailable { offlineView }
            else {
                MobileWebView(serverURL: savedServer, apiKey: savedKey) { reason in
                    offlineReason = reason
                    backendUnavailable = true
                }
            }
        }
        .onAppear { server = savedServer; key = savedKey }
        .onOpenURL { handlePairingLink($0) }
    }

    private var offlineView: some View {
        VStack(spacing: 16) {
            Text("!").font(.system(size: 28, weight: .bold)).foregroundStyle(.orange)
                .frame(width: 56, height: 56).background(Color.orange.opacity(0.14)).clipShape(RoundedRectangle(cornerRadius: 14))
            Text(accessPaused ? "Access paused by owner" : "PC backend is offline").font(.title.bold()).multilineTextAlignment(.center)
            Text(accessPaused ? "Your pairing is still saved. The owner can restore this device without another QR code." : "Start LinguaFusion on the PC and keep the backend window open. Your saved pairing has not been removed.")
                .foregroundStyle(.secondary).multilineTextAlignment(.center)
            if !offlineReason.isEmpty { Text(offlineReason).font(.footnote).foregroundStyle(.orange).multilineTextAlignment(.center) }
            Button { retrySavedConnection() } label: {
                HStack { Spacer(); if connecting { ProgressView().tint(.white) }; Text(connecting ? "Checking…" : "Retry connection").bold(); Spacer() }
            }.buttonStyle(.borderedProminent).controlSize(.large).disabled(connecting)
            Button("Change PC or pairing") {
                savedServer = ""; savedKey = ""; CredentialStore.deleteAPIKey(); backendUnavailable = false; offlineReason = ""
            }.buttonStyle(.bordered).controlSize(.large)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(uiColor: .secondarySystemBackground))
    }

    private func retrySavedConnection() {
        connecting = true
        validateConnection(serverURL: savedServer, apiKey: savedKey) { error in
            DispatchQueue.main.async {
                connecting = false
                if let error { offlineReason = error; return }
                offlineReason = ""; backendUnavailable = false
            }
        }
    }

    private var pairingView: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("文").font(.system(size: 28, weight: .bold)).foregroundStyle(Color(red: 0.04, green: 0.34, blue: 0.82))
                    .frame(width: 56, height: 56).background(Color(red: 0.91, green: 0.94, blue: 1.0)).clipShape(RoundedRectangle(cornerRadius: 14))
                Text("Connect LinguaFusion").font(.largeTitle.bold())
                Text("Use your PC's GPU and offline language models from this iPhone or iPad.").foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 14) {
                    Text("PC address").font(.caption.bold())
                    TextField("http://192.168.1.20:8000", text: $server).textInputAutocapitalization(.never).keyboardType(.URL).textFieldStyle(.roundedBorder)
                    Text("Pairing key").font(.caption.bold())
                    SecureField("Shown by the PC", text: $key).textFieldStyle(.roundedBorder)
                    Button { connect() } label: { HStack { Spacer(); if connecting { ProgressView().tint(.white) }; Text(connecting ? "Testing connection…" : "Connect to PC").bold(); Spacer() } }
                        .buttonStyle(.borderedProminent).controlSize(.large).disabled(connecting)
                    if !errorMessage.isEmpty { Text(errorMessage).font(.footnote).foregroundStyle(.red) }
                }
                .padding(18).background(.background).clipShape(RoundedRectangle(cornerRadius: 16)).overlay(RoundedRectangle(cornerRadius: 16).stroke(.quaternary))
                Text("Scan a one-time owner invitation to connect securely from anywhere, or enter a private-network PC address.").font(.footnote).foregroundStyle(.secondary)
            }.padding(24).padding(.top, 28)
        }.background(Color(uiColor: .secondarySystemBackground))
    }

    private func connect() {
        let normalized = server.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "/+$", with: "", options: .regularExpression)
        guard let url = URL(string: normalized + "/"), url.scheme == "http" || url.scheme == "https", url.host != nil else { errorMessage = "Enter a full http:// or https:// PC address."; return }
        connecting = true; errorMessage = ""
        validateConnection(serverURL: normalized, apiKey: key) { error in
            DispatchQueue.main.async {
                connecting = false
                if let error { errorMessage = error; return }
                guard CredentialStore.saveAPIKey(key) else { errorMessage = "The pairing key could not be stored securely in Keychain."; return }
                savedServer = normalized; savedKey = key
            }
        }
    }

    private func validateConnection(serverURL: String, apiKey: String, completion: @escaping (String?) -> Void) {
        guard let rootURL = URL(string: serverURL + "/") else { completion("The saved PC address is invalid."); return }
        var rootRequest = URLRequest(url: rootURL); rootRequest.timeoutInterval = 6
        if !apiKey.isEmpty { rootRequest.setValue(apiKey, forHTTPHeaderField: "X-API-Key") }
        URLSession.shared.dataTask(with: rootRequest) { data, response, error in
            if let error { completion("Could not reach the PC: \(error.localizedDescription)"); return }
            if let http = response as? HTTPURLResponse, [502, 503, 504].contains(http.statusCode) {
                completion("The PC backend is offline (HTTP \(http.statusCode)). Start LinguaFusion on the PC and retry.")
                return
            }
            guard let http = response as? HTTPURLResponse, http.statusCode == 200, let data,
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any], object["ok"] as? Bool == true else {
                completion("The address did not return a LinguaFusion backend."); return
            }
            guard object["auth_required"] as? Bool == true else { completion(nil); return }
            guard !apiKey.isEmpty else { completion("This phone is not paired yet. Scan a fresh QR code or enter the pairing key."); return }
            guard let diagnosticsURL = URL(string: serverURL + "/diagnostics") else { completion("The PC address is invalid."); return }
            var diagnosticsRequest = URLRequest(url: diagnosticsURL); diagnosticsRequest.timeoutInterval = 6
            diagnosticsRequest.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
            URLSession.shared.dataTask(with: diagnosticsRequest) { diagnosticsData, diagnosticsResponse, diagnosticsError in
                if let diagnosticsError { completion("Could not verify pairing: \(diagnosticsError.localizedDescription)"); return }
                if let diagnosticsHTTP = diagnosticsResponse as? HTTPURLResponse, diagnosticsHTTP.statusCode == 403 {
                    let detail = diagnosticsData.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["detail"] as? String
                    completion(detail ?? "Access paused by the LinguaFusion owner."); return
                }
                guard let diagnosticsHTTP = diagnosticsResponse as? HTTPURLResponse, diagnosticsHTTP.statusCode == 200 else {
                    completion("The pairing key is invalid. Scan a fresh QR code from the PC."); return
                }
                completion(nil)
            }.resume()
        }.resume()
    }

    private func handlePairingLink(_ url: URL) {
        guard url.scheme?.lowercased() == "linguafusion", url.host?.lowercased() == "pair",
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let pairingServer = components.queryItems?.first(where: { $0.name == "server" })?.value,
              let token = components.queryItems?.first(where: { $0.name == "token" })?.value,
              (pairingServer.hasPrefix("http://") || pairingServer.hasPrefix("https://")), !token.isEmpty,
              let endpoint = URL(string: pairingServer.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/pair") else {
            errorMessage = "This pairing QR code is invalid. Create a fresh one on the PC."
            return
        }
        connecting = true; errorMessage = ""; backendUnavailable = false
        var request = URLRequest(url: endpoint); request.httpMethod = "POST"; request.timeoutInterval = 8
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["token": token, "device_name": UIDevice.current.name, "platform": "ios"])
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                connecting = false
                if let error { errorMessage = "Pairing failed: \(error.localizedDescription)"; return }
                guard let http = response as? HTTPURLResponse, http.statusCode == 200, let data,
                      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let apiKey = object["api_key"] as? String, !apiKey.isEmpty else {
                    errorMessage = "Pairing failed or expired. Create a fresh QR code on the PC."; return
                }
                guard CredentialStore.saveAPIKey(apiKey) else { errorMessage = "The device key could not be stored securely in Keychain."; return }
                let normalized = pairingServer.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                server = normalized; key = apiKey; savedServer = normalized; savedKey = apiKey
                offlineReason = ""; backendUnavailable = false
            }
        }.resume()
    }

    private var accessPaused: Bool {
        offlineReason.localizedCaseInsensitiveContains("access paused")
    }
}
