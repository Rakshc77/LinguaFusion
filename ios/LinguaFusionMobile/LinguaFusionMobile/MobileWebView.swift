import SwiftUI
import WebKit
import AVFoundation

struct MobileWebView: UIViewRepresentable {
    let serverURL: String
    let apiKey: String
    let onConnectionFailure: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(serverURL: serverURL, onConnectionFailure: onConnectionFailure) }
    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.allowsInlineMediaPlayback = true
        configuration.mediaTypesRequiringUserActionForPlayback = []
        configuration.userContentController.add(context.coordinator, name: "linguafusionAudio")
        let serverJSON = jsonString(serverURL), keyJSON = jsonString(apiKey)
        let injection = "localStorage.setItem('lf.server', \(serverJSON)); localStorage.setItem('lf.key', \(keyJSON));"
        configuration.userContentController.addUserScript(WKUserScript(source: injection, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.uiDelegate = context.coordinator
        view.navigationDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = true
        view.scrollView.keyboardDismissMode = .interactive
        if let url = URL(string: serverURL + "/mobile/") { view.load(URLRequest(url: url)) }
        return view
    }
    func updateUIView(_ view: WKWebView, context: Context) {}
    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        coordinator.cancelAudioRecording()
        view.configuration.userContentController.removeScriptMessageHandler(forName: "linguafusionAudio")
        view.navigationDelegate = nil
        view.uiDelegate = nil
        view.stopLoading()
    }
    private func jsonString(_ value: String) -> String {
        let data = try! JSONSerialization.data(withJSONObject: [value])
        let array = String(data: data, encoding: .utf8)!
        return String(array.dropFirst().dropLast())
    }

    final class Coordinator: NSObject, WKUIDelegate, WKNavigationDelegate, WKScriptMessageHandler {
        let serverURL: String
        let onConnectionFailure: (String) -> Void
        private var audioRecorder: AVAudioRecorder?
        private var audioURL: URL?

        init(serverURL: String, onConnectionFailure: @escaping (String) -> Void) {
            self.serverURL = serverURL
            self.onConnectionFailure = onConnectionFailure
        }

        private func report(_ message: String) {
            cancelAudioRecording()
            DispatchQueue.main.async { self.onConnectionFailure(message) }
        }

        private func trustedOrigin(_ origin: WKSecurityOrigin) -> Bool {
            guard let expected = URLComponents(string: serverURL),
                  let scheme = expected.scheme, let host = expected.host else { return false }
            let expectedPort = expected.port ?? (scheme.lowercased() == "https" ? 443 : 80)
            return origin.protocol.lowercased() == scheme.lowercased()
                && origin.host.lowercased() == host.lowercased()
                && origin.port == expectedPort
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "linguafusionAudio", message.frameInfo.isMainFrame,
                  trustedOrigin(message.frameInfo.securityOrigin),
                  let body = message.body as? [String: Any],
                  let action = body["action"] as? String,
                  let id = body["id"] as? String else {
                return
            }
            switch action {
            case "start": requestAndStartRecording(webView: message.webView, id: id)
            case "stop": stopAudioRecording(webView: message.webView, id: id)
            case "cancel": cancelAudioRecording()
            default: reply(webView: message.webView, id: id, ok: false, value: "Unsupported microphone action.")
            }
        }

        private func requestAndStartRecording(webView: WKWebView?, id: String) {
            let session = AVAudioSession.sharedInstance()
            switch session.recordPermission {
            case .granted:
                beginAudioRecording(webView: webView, id: id)
            case .denied:
                reply(webView: webView, id: id, ok: false, value: "Microphone permission was denied. Enable it in iOS Settings.")
            case .undetermined:
                session.requestRecordPermission { [weak self] granted in
                    DispatchQueue.main.async {
                        guard let self else { return }
                        if granted { self.beginAudioRecording(webView: webView, id: id) }
                        else { self.reply(webView: webView, id: id, ok: false, value: "Microphone permission was denied.") }
                    }
                }
            @unknown default:
                reply(webView: webView, id: id, ok: false, value: "Microphone permission is unavailable.")
            }
        }

        private func beginAudioRecording(webView: WKWebView?, id: String) {
            guard audioRecorder == nil else { reply(webView: webView, id: id, ok: false, value: "Recording is already active."); return }
            do {
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetooth])
                try session.setActive(true)
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("linguafusion-\(UUID().uuidString).wav")
                let settings: [String: Any] = [
                    AVFormatIDKey: kAudioFormatLinearPCM,
                    AVSampleRateKey: 16_000.0,
                    AVNumberOfChannelsKey: 1,
                    AVLinearPCMBitDepthKey: 16,
                    AVLinearPCMIsFloatKey: false,
                    AVLinearPCMIsBigEndianKey: false
                ]
                let recorder = try AVAudioRecorder(url: url, settings: settings)
                guard recorder.prepareToRecord(), recorder.record() else { throw NSError(domain: "LinguaFusionAudio", code: 1, userInfo: [NSLocalizedDescriptionKey: "The iPhone microphone could not start."]) }
                audioURL = url; audioRecorder = recorder
                reply(webView: webView, id: id, ok: true, value: "OK")
            } catch {
                cancelAudioRecording()
                reply(webView: webView, id: id, ok: false, value: error.localizedDescription)
            }
        }

        private func stopAudioRecording(webView: WKWebView?, id: String) {
            guard let recorder = audioRecorder, let url = audioURL else { reply(webView: webView, id: id, ok: false, value: "No recording is active."); return }
            recorder.stop(); audioRecorder = nil; audioURL = nil
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            defer { try? FileManager.default.removeItem(at: url) }
            do {
                let data = try Data(contentsOf: url)
                guard data.count > 44 else { throw NSError(domain: "LinguaFusionAudio", code: 2, userInfo: [NSLocalizedDescriptionKey: "No speech was recorded."]) }
                reply(webView: webView, id: id, ok: true, value: data.base64EncodedString())
            } catch { reply(webView: webView, id: id, ok: false, value: error.localizedDescription) }
        }

        func cancelAudioRecording() {
            audioRecorder?.stop(); audioRecorder = nil
            if let url = audioURL { try? FileManager.default.removeItem(at: url) }
            audioURL = nil
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }

        private func reply(webView: WKWebView?, id: String, ok: Bool, value: String) {
            guard let webView else { return }
            let idJSON = jsonLiteral(id), valueJSON = jsonLiteral(value)
            webView.evaluateJavaScript("window.LFNativeIOSAudioResult && window.LFNativeIOSAudioResult(\(idJSON),\(ok ? "true" : "false"),\(valueJSON));")
        }

        private func jsonLiteral(_ value: String) -> String {
            guard let data = try? JSONSerialization.data(withJSONObject: [value]),
                  let array = String(data: data, encoding: .utf8) else { return "\"\"" }
            return String(array.dropFirst().dropLast())
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            report("The PC backend stopped responding: \(error.localizedDescription)")
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            report("Could not reach \(serverURL): \(error.localizedDescription)")
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationResponse: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            if let response = navigationResponse.response as? HTTPURLResponse, response.statusCode >= 400 {
                if [502, 503, 504].contains(response.statusCode) {
                    report("The PC backend is offline (HTTP \(response.statusCode)). Start LinguaFusion on the PC and retry.")
                } else {
                    report("The PC returned HTTP \(response.statusCode) for the mobile app.")
                }
                decisionHandler(.cancel)
            } else {
                decisionHandler(.allow)
            }
        }

        @available(iOS 15.0, *)
        func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            guard trustedOrigin(origin) else { decisionHandler(.deny); return }
            decisionHandler(type == .microphone || type == .cameraAndMicrophone ? .grant : .prompt)
        }
    }
}
