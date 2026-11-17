import SwiftUI
import WebKit
import AVFoundation

// Native shell for the same authenticated Cloud Run workspace as Android.
struct CloudWebView: UIViewRepresentable {
    static let workspace = URL(string: "https://linguafusion-cloud-pilot-jl77ipbeua-ey.a.run.app/pilot/")!
    let reloadToken: Int
    let onConnection: (String?) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onConnection: onConnection) }
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true
        config.userContentController.add(context.coordinator, name: "linguafusionAudio")
        config.userContentController.addUserScript(WKUserScript(source: """
            window.LFNativeCloudRecording = true;
            window.LinguaFusionNativeAudio = {
              onmessage: null,
              postMessage: function(body) { window.webkit.messageHandlers.linguafusionAudio.postMessage(body); }
            };
            """, injectionTime: .atDocumentStart, forMainFrameOnly: true))
        let view = WKWebView(frame: .zero, configuration: config)
        context.coordinator.webView = view
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        view.scrollView.contentInsetAdjustmentBehavior = .never
        view.scrollView.keyboardDismissMode = .interactive
        view.load(URLRequest(url: Self.workspace))
        return view
    }
    func updateUIView(_ view: WKWebView, context: Context) {
        guard context.coordinator.reloadToken != reloadToken else { return }
        context.coordinator.reloadToken = reloadToken
        view.load(URLRequest(url: Self.workspace, cachePolicy: .reloadIgnoringLocalCacheData))
    }
    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        coordinator.cancelRecording()
        view.configuration.userContentController.removeScriptMessageHandler(forName: "linguafusionAudio")
        view.stopLoading(); view.navigationDelegate = nil; view.uiDelegate = nil
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler, AVAudioRecorderDelegate {
        let onConnection: (String?) -> Void
        var reloadToken = 0
        weak var webView: WKWebView?
        private var recorder: AVAudioRecorder?
        private var recordingURL: URL?
        private var activeID: String?
        private var readyID: String?
        private var audioParts: [Data] = []
        private var timer: Timer?

        init(onConnection: @escaping (String?) -> Void) { self.onConnection = onConnection }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            DispatchQueue.main.async { self.onConnection(nil) }
        }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            if (error as NSError).code != NSURLErrorCancelled {
                DispatchQueue.main.async { self.onConnection("Check your internet connection, then try again.") }
            }
        }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            if (error as NSError).code != NSURLErrorCancelled {
                DispatchQueue.main.async { self.onConnection("The cloud workspace could not load. Try again shortly.") }
            }
        }
        func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                     decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            if let http = response.response as? HTTPURLResponse, http.statusCode >= 400 {
                DispatchQueue.main.async { self.onConnection("Cloud service returned HTTP \(http.statusCode). Try again shortly.") }
                decisionHandler(.cancel)
            } else { decisionHandler(.allow) }
        }

        private func trusted(_ url: URL?) -> Bool {
            guard let url else { return false }
            return url.scheme == CloudWebView.workspace.scheme && url.host == CloudWebView.workspace.host
                && (url.port ?? 443) == 443
        }
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { decisionHandler(.cancel); return }
            if url.scheme == "linguafusion-record" {
                if trusted(webView.url), action.sourceFrame.isMainFrame,
                   let id = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "id" })?.value {
                    switch url.host {
                    case "capture": startRecording(id: id)
                    case "stop": stopRecording(id: id)
                    case "cancel": cancelRecording(); emit(id: id, kind: "cancel")
                    default: break
                    }
                }
                decisionHandler(.cancel); return
            }
            if trusted(url) { decisionHandler(.allow) }
            else {
                if action.navigationType == .linkActivated { UIApplication.shared.open(url) }
                decisionHandler(.cancel)
            }
        }
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                     for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url {
                if trusted(url) { webView.load(URLRequest(url: url)) }
                else { UIApplication.shared.open(url) }
            }
            return nil
        }
        @available(iOS 15.0, *)
        func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin,
                     initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType,
                     decisionHandler: @escaping (WKPermissionDecision) -> Void) {
            decisionHandler(origin.host == CloudWebView.workspace.host && frame.isMainFrame ? .grant : .deny)
        }
        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "linguafusionAudio", message.frameInfo.isMainFrame,
                  message.frameInfo.securityOrigin.host == CloudWebView.workspace.host,
                  let raw = message.body as? String, let data = raw.data(using: .utf8),
                  let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  object["type"] as? String == "read", let id = object["id"] as? String,
                  let part = object["part"] as? Int, let offset = object["offset"] as? Int else { return }
            readPacket(id: id, part: part, offset: offset)
        }
        private func startRecording(id: String) {
            guard recorder == nil else { emit(id: id, kind: "error", data: "Recording is already active."); return }
            let session = AVAudioSession.sharedInstance()
            switch session.recordPermission {
            case .granted: beginRecording(id: id)
            case .denied: emit(id: id, kind: "error", data: "Enable microphone access in iPhone Settings.")
            case .undetermined:
                session.requestRecordPermission { [weak self] granted in
                    DispatchQueue.main.async {
                        guard let self else { return }
                        if granted { self.beginRecording(id: id) }
                        else { self.emit(id: id, kind: "error", data: "Microphone permission was denied.") }
                    }
                }
            @unknown default: emit(id: id, kind: "error", data: "Microphone permission is unavailable.")
            }
        }
        private func beginRecording(id: String) {
            do {
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.playAndRecord, mode: .measurement, options: [.defaultToSpeaker, .allowBluetooth])
                try session.setActive(true)
                let url = FileManager.default.temporaryDirectory.appendingPathComponent("linguafusion-\(UUID().uuidString).wav")
                let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 16_000.0,
                    AVNumberOfChannelsKey: 1, AVLinearPCMBitDepthKey: 16,
                    AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false]
                let next = try AVAudioRecorder(url: url, settings: settings)
                next.delegate = self
                guard next.prepareToRecord(), next.record(forDuration: 1200) else { throw NSError(domain: "LinguaFusionAudio", code: 1) }
                recordingURL = url; recorder = next; activeID = id; readyID = nil; audioParts = []
                timer = Timer.scheduledTimer(withTimeInterval: 1200, repeats: false) { [weak self] _ in self?.stopRecording(id: id) }
                emit(id: id, kind: "started")
            } catch { cancelRecording(); emit(id: id, kind: "error", data: "The microphone could not start: \(error.localizedDescription)") }
        }
        private func stopRecording(id: String) {
            guard id == activeID, let recorder, let url = recordingURL else { return }
            recorder.stop(); self.recorder = nil; activeID = nil
            timer?.invalidate(); timer = nil; recordingURL = nil
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
            defer { try? FileManager.default.removeItem(at: url) }
            do {
                audioParts = try Self.splitWav(Data(contentsOf: url))
                readyID = id
                emit(id: id, kind: "ready", total: audioParts.count)
            } catch { audioParts = []; readyID = nil; emit(id: id, kind: "error", data: "The recording could not be prepared.") }
        }
        func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
            if let id = activeID { stopRecording(id: id) }
        }
        func cancelRecording() {
            recorder?.stop(); recorder = nil; activeID = nil; readyID = nil; audioParts = []
            timer?.invalidate(); timer = nil
            if let url = recordingURL { try? FileManager.default.removeItem(at: url) }; recordingURL = nil
            try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
        }
        private static func splitWav(_ data: Data) throws -> [Data] {
            guard data.count > 44, data.prefix(4) == Data("RIFF".utf8), data[8..<12] == Data("WAVE".utf8) else {
                throw NSError(domain: "LinguaFusionAudio", code: 2)
            }
            var cursor = 12
            var pcm: Data?
            var expectedFormat = false
            while cursor + 8 <= data.count {
                let size = Int(UInt32(data[cursor + 4]) | UInt32(data[cursor + 5]) << 8 |
                    UInt32(data[cursor + 6]) << 16 | UInt32(data[cursor + 7]) << 24)
                let start = cursor + 8
                guard start <= data.count, size <= data.count - start else { break }
                if data[cursor..<cursor + 4] == Data("fmt ".utf8), size >= 16 {
                    let format = UInt16(data[start]) | UInt16(data[start + 1]) << 8
                    let channels = UInt16(data[start + 2]) | UInt16(data[start + 3]) << 8
                    let rate = UInt32(data[start + 4]) | UInt32(data[start + 5]) << 8 |
                        UInt32(data[start + 6]) << 16 | UInt32(data[start + 7]) << 24
                    let bits = UInt16(data[start + 14]) | UInt16(data[start + 15]) << 8
                    expectedFormat = format == 1 && channels == 1 && rate == 16_000 && bits == 16
                }
                if data[cursor..<cursor + 4] == Data("data".utf8) { pcm = data.subdata(in: start..<start + size); break }
                cursor = start + size + (size % 2)
            }
            guard expectedFormat, let pcm, !pcm.isEmpty else { throw NSError(domain: "LinguaFusionAudio", code: 3) }
            let partSize = 300 * 16_000 * 2
            let length = min(pcm.count, partSize * 4)
            return stride(from: 0, to: length, by: partSize).map { offset in
                let segment = pcm.subdata(in: offset..<min(offset + partSize, length))
                var wav = Data("RIFF".utf8)
                wav.appendLE(UInt32(36 + segment.count)); wav.append(Data("WAVEfmt ".utf8))
                wav.appendLE(UInt32(16)); wav.appendLE(UInt16(1)); wav.appendLE(UInt16(1))
                wav.appendLE(UInt32(16_000)); wav.appendLE(UInt32(32_000))
                wav.appendLE(UInt16(2)); wav.appendLE(UInt16(16)); wav.append(Data("data".utf8))
                wav.appendLE(UInt32(segment.count)); wav.append(segment)
                return wav
            }
        }
        private func readPacket(id: String, part: Int, offset: Int) {
            guard id == readyID, part >= 0, part < audioParts.count,
                  offset >= 0, offset < audioParts[part].count else { return }
            let bytes = audioParts[part]
            let end = min(offset + 48_000, bytes.count)
            let reply: [String: Any] = ["id":id, "part":part, "offset":offset,
                "data":bytes.subdata(in: offset..<end).base64EncodedString(), "nextOffset":end, "done":end == bytes.count]
            if end == bytes.count { audioParts[part] = Data() }
            if audioParts.allSatisfy({ $0.isEmpty }) { readyID = nil }
            sendJavaScript("window.LinguaFusionNativeAudio.onmessage({data:\(json(reply))});")
        }
        private func emit(id: String, kind: String, data: String = "", total: Int = 0) {
            sendJavaScript("window.dispatchEvent(new CustomEvent('lf-native-recording',{detail:\(json(["id":id,"kind":kind,"data":data,"total":total]))}));")
        }
        private func sendJavaScript(_ script: String) {
            DispatchQueue.main.async { [weak self] in self?.webView?.evaluateJavaScript(script) }
        }
        private func json(_ value: Any) -> String {
            guard let data = try? JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed]),
                  let text = String(data: data, encoding: .utf8) else { return "null" }
            return text
        }
    }
}

private extension Data {
    mutating func appendLE<T: FixedWidthInteger>(_ value: T) {
        var little = value.littleEndian
        Swift.withUnsafeBytes(of: &little) { append(contentsOf: $0) }
    }
}
