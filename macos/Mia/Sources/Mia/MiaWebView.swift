#if os(macOS)
import AppKit
import CryptoKit
import SwiftUI
import UniformTypeIdentifiers
import WebKit
import MiaCore

@MainActor private enum InstanceStores {
    private static var stores: [String: WKWebsiteDataStore] = [:]
    static func store(for connection: MiaConnection) -> WKWebsiteDataStore {
        let selectedOrigin = WebOrigin(connection.url)!
        let key = connection.id + "|" + connection.installationID + "|" + selectedOrigin.scheme + "|" + selectedOrigin.host + "|" + String(selectedOrigin.port)
        if let existing = stores[key] { return existing }
        let store: WKWebsiteDataStore
        if #available(macOS 14.0, *) {
            let digest = Array(SHA256.hash(data: Data(key.utf8)).prefix(16))
            let identifier = UUID(uuid: (digest[0], digest[1], digest[2], digest[3], digest[4], digest[5], digest[6], digest[7], digest[8], digest[9], digest[10], digest[11], digest[12], digest[13], digest[14], digest[15]))
            store = WKWebsiteDataStore(forIdentifier: identifier)
        } else {
            // macOS 13 has no per-identifier persistent stores. Isolated sessions
            // are preferable to sharing cookies between localhost installations.
            store = WKWebsiteDataStore.nonPersistent()
        }
        stores[key] = store
        return store
    }
}

@MainActor struct MiaWebView: NSViewRepresentable {
    let connection: MiaConnection
    let reloadID: UUID
    var disconnected: () -> Void
    var connected: () -> Void
    var notice: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(connection: connection, reloadID: reloadID, disconnected: disconnected, connected: connected, notice: notice) }
    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = InstanceStores.store(for: connection)
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        // Deliberately no WKScriptMessageHandler or native execution bridge.
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.uiDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = true
        view.load(URLRequest(url: clientURL(connection)))
        return view
    }
    func updateNSView(_ view: WKWebView, context: Context) {
        if context.coordinator.reloadID != reloadID {
            context.coordinator.reloadID = reloadID
            view.load(URLRequest(url: clientURL(connection)))
        }
    }
    private func clientURL(_ connection: MiaConnection) -> URL {
        var components = URLComponents(url: connection.url, resolvingAgainstBaseURL: false)!
        components.queryItems = (components.queryItems ?? []).filter { !["mia_client", "mia_mode"].contains($0.name) } + [URLQueryItem(name: "mia_client", value: "mac"), URLQueryItem(name: "mia_mode", value: connection.mode == "local" ? "local" : "remote")]
        return components.url ?? connection.url
    }

    @MainActor final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
        let origin: WebOrigin
        var reloadID: UUID
        let disconnected: () -> Void
        let connected: () -> Void
        let notice: (String) -> Void
        init(connection: MiaConnection, reloadID: UUID, disconnected: @escaping () -> Void, connected: @escaping () -> Void, notice: @escaping (String) -> Void) {
            self.origin = WebOrigin(connection.url)!
            self.reloadID = reloadID; self.disconnected = disconnected; self.connected = connected; self.notice = notice
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url else { decisionHandler(.cancel); return }
            if origin.allows(url) { decisionHandler(action.shouldPerformDownload ? .download : .allow); return }
            decisionHandler(.cancel)
            if action.navigationType == .linkActivated, WebOrigin.externalLinkAllowed(url) { confirmExternal(url) }
            else { notice("A página tentou abrir outro destino. Sua conexão com esta Mia foi preservada.") }
        }
        func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse, decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            guard let url = response.response.url, origin.allows(url) else { decisionHandler(.cancel); return }
            decisionHandler(response.canShowMIMEType ? .allow : .download)
        }
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { connected() }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) { if (error as NSError).code != NSURLErrorCancelled { disconnected() } }
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) { if (error as NSError).code != NSURLErrorCancelled { disconnected() } }
        func webView(_ webView: WKWebView, didReceive challenge: URLAuthenticationChallenge, completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
            // WebKit performs normal certificate validation. No trust override.
            completionHandler(.performDefaultHandling, nil)
        }
        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            if let url = action.request.url, origin.allows(url) { webView.load(action.request) }
            else if let url = action.request.url, action.navigationType == .linkActivated, WebOrigin.externalLinkAllowed(url) { confirmExternal(url) }
            return nil
        }

        func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
            guard let page = webView.url, origin.allows(page), let frameURL = frame.request.url, origin.allows(frameURL) else { completionHandler(nil); return }
            let panel = NSOpenPanel()
            panel.title = parameters.allowsDirectories ? "Escolha seu Vault ou pasta de contexto" : "Escolha notas ou uma exportação de conversas"
            panel.prompt = "Escolher"
            panel.canChooseFiles = !parameters.allowsDirectories
            panel.canChooseDirectories = parameters.allowsDirectories
            panel.allowsMultipleSelection = parameters.allowsMultipleSelection
            panel.resolvesAliases = false
            panel.canCreateDirectories = false
            if !parameters.allowsDirectories {
                panel.allowedContentTypes = [.zip, .plainText, .json, UTType(filenameExtension: "md") ?? .plainText, UTType(filenameExtension: "markdown") ?? .plainText]
            }
            if let window = webView.window { panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) } }
            else { panel.begin { completionHandler($0 == .OK ? panel.urls : nil) } }
        }

        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            guard let url = frame.request.url, origin.allows(url) else { completionHandler(); return }
            let alert = NSAlert(); alert.messageText = "Mia"; alert.informativeText = String(message.prefix(8_192)); alert.addButton(withTitle: "OK")
            if let window = webView.window { alert.beginSheetModal(for: window) { _ in completionHandler() } } else { alert.runModal(); completionHandler() }
        }
        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            guard let url = frame.request.url, origin.allows(url) else { completionHandler(false); return }
            let alert = NSAlert(); alert.messageText = "Confira antes de continuar"; alert.informativeText = String(message.prefix(8_192)); alert.addButton(withTitle: "Continuar"); alert.addButton(withTitle: "Cancelar")
            if let window = webView.window { alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) } } else { completionHandler(alert.runModal() == .alertFirstButtonReturn) }
        }
        func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
            guard let url = frame.request.url, origin.allows(url) else { completionHandler(nil); return }
            let alert = NSAlert(); alert.messageText = "Mia"; alert.informativeText = String(prompt.prefix(8_192)); alert.addButton(withTitle: "Salvar"); alert.addButton(withTitle: "Cancelar")
            let field = NSTextField(string: String((defaultText ?? "").prefix(512))); field.frame = NSRect(x: 0, y: 0, width: 340, height: 24); alert.accessoryView = field
            if let window = webView.window { alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn ? String(field.stringValue.prefix(512)) : nil) } }
            else { completionHandler(alert.runModal() == .alertFirstButtonReturn ? String(field.stringValue.prefix(512)) : nil) }
        }
        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
        func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
        func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
            guard let url = response.url, origin.allows(url) else { completionHandler(nil); return }
            let panel = NSSavePanel(); panel.title = "Salvar exportação da Mia"; panel.nameFieldStringValue = URL(fileURLWithPath: suggestedFilename).lastPathComponent; panel.canCreateDirectories = true
            panel.begin { completionHandler($0 == .OK ? panel.url : nil) }
        }
        func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) { notice("A exportação não foi salva. Seus dados continuam nesta instalação; tente exportar novamente.") }
        private func confirmExternal(_ url: URL) {
            let alert = NSAlert(); alert.messageText = "Abrir no navegador?"; alert.informativeText = "Este endereço fica fora da sua Mia: \(url.host ?? "")"; alert.addButton(withTitle: "Abrir navegador"); alert.addButton(withTitle: "Cancelar")
            if alert.runModal() == .alertFirstButtonReturn { NSWorkspace.shared.open(url) }
        }
    }
}
#endif
