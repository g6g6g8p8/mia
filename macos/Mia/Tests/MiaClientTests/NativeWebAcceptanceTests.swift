#if os(macOS)
import AppKit
import Foundation
import WebKit
import XCTest
import MiaCore
@testable import Mia

/// Opt-in integration with the final bundled Python/backend, on a real Mac.
/// The wrapper creates disposable synthetic data. This does not certify a
/// physical NSOpenPanel interaction, Gatekeeper, login, boot, sleep or a Vault.
@MainActor final class NativeWebAcceptanceTests: XCTestCase {
    private struct AcceptanceFailure: LocalizedError { let message: String; var errorDescription: String? { message } }

    private func javascript(_ view: WKWebView, _ body: String, arguments: [String: Any] = [:]) async throws -> Any? {
        try await withCheckedThrowingContinuation { continuation in
            view.callAsyncJavaScript(body, arguments: arguments, in: nil, in: .page) { result in
                continuation.resume(with: result.map { $0 as Any? })
            }
        }
    }

    private func wait(_ view: WKWebView, _ expression: String, label: String, timeout: TimeInterval = 30) async throws {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end {
            if (try? await javascript(view, "return Boolean(\(expression));")) as? Bool == true { return }
            try await Task.sleep(nanoseconds: 100_000_000)
        }
        throw AcceptanceFailure(message: "Native WebKit did not reach: " + label)
    }

    private func assertNumber(_ view: WKWebView, _ body: String, _ expected: Int, file: StaticString = #filePath, line: UInt = #line) async throws {
        let result = try await javascript(view, body)
        XCTAssertEqual(result as? Int, expected, file: file, line: line)
    }

    private func assertBoolean(_ view: WKWebView, _ body: String, _ expected: Bool, _ message: String = "", file: StaticString = #filePath, line: UInt = #line) async throws {
        let result = try await javascript(view, body)
        XCTAssertEqual(result as? Bool, expected, message, file: file, line: line)
    }

    private func cookies(_ store: WKWebsiteDataStore) async -> [HTTPCookie] {
        await withCheckedContinuation { completion in
            store.httpCookieStore.getAllCookies { completion.resume(returning: $0) }
        }
    }

    private func cookie(_ cookie: HTTPCookie, in store: WKWebsiteDataStore) async {
        await withCheckedContinuation { completion in
            store.httpCookieStore.setCookie(cookie) { completion.resume() }
        }
    }

    /// Supplies only reviewed synthetic fixture URLs through the same public
    /// WebKit completion handler as NSOpenPanel. This permits testing WebKit's
    /// actual directory enumeration without automating another app or TCC.
    private final class FixturePanels: NSObject, WKUIDelegate {
        let folder: URL
        let origin: WebOrigin
        var folderRequests = 0
        var directoryParameters = false
        var confirmations = 0
        init(folder: URL, origin: WebOrigin) { self.folder = folder; self.origin = origin }
        func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
            guard let page = webView.url, origin.allows(page), let url = frame.request.url, origin.allows(url), parameters.allowsDirectories else { completionHandler(nil); return }
            folderRequests += 1
            directoryParameters = parameters.allowsDirectories
            completionHandler([folder])
        }
        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            guard let url = frame.request.url, origin.allows(url), message.hasPrefix("Enviar "), message.contains("arquivos de texto") else { completionHandler(false); return }
            confirmations += 1
            completionHandler(true)
        }
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) { completionHandler() }
    }

    func testFinalBundledBackendThroughNativeWebKit() async throws {
        let environment = ProcessInfo.processInfo.environment
        guard environment["MIA_NATIVE_ACCEPTANCE"] == "1" else { throw XCTSkip("Run scripts/native_mac_acceptance.py against a final Mac bundle to enable real WKWebView acceptance.") }
        guard let rawURL = environment["MIA_TEST_BASE_URL"], let base = URL(string: rawURL), let origin = WebOrigin(base), origin.isLoopback,
              let tokenPath = environment["MIA_TEST_SETUP_TOKEN_PATH"], let zipPath = environment["MIA_TEST_ZIP_PATH"],
              let folderPath = environment["MIA_TEST_FOLDER_PATH"], let reportPath = environment["MIA_TEST_REPORT_PATH"] else {
            throw AcceptanceFailure(message: "Disposable native acceptance fixture is incomplete.")
        }
        let token = try String(contentsOfFile: tokenPath, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)
        _ = NSApplication.shared
        let connection = try MiaConnection(["installation_id": .string(UUID().uuidString), "url": .string(base.absoluteString), "running": .bool(true), "bootstrap_token": .string(token)], local: true)
        let coordinator = MiaWebView.Coordinator(connection: connection, reloadID: UUID(), disconnected: {}, connected: {}, notice: { _ in })
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .nonPersistent()
        configuration.preferences.javaScriptCanOpenWindowsAutomatically = false
        let view = WKWebView(frame: NSRect(x: 0, y: 0, width: 1040, height: 780), configuration: configuration)
        view.navigationDelegate = coordinator
        view.uiDelegate = coordinator
        let window = NSWindow(contentRect: view.frame, styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = view
        window.orderFront(nil)
        defer { view.stopLoading(); window.orderOut(nil); window.contentView = nil }
        var address = URLComponents(url: base, resolvingAgainstBaseURL: false)!
        address.queryItems = [URLQueryItem(name: "mia_client", value: "mac"), URLQueryItem(name: "mia_mode", value: "local")]

        // A desktop URL alone does not grant the capability to claim this Mia.
        view.load(URLRequest(url: address.url!))
        try await wait(view, "document.querySelector('#setup-form')", label: "first-owner form")
        let unauthorized = try await javascript(view, "return (await fetch('/api/setup', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:'Synthetic WebKit',password:'synthetic-wk-password-123'})})).status;")
        XCTAssertEqual(unauthorized as? Int, 401)
        let bootstrap = try XCTUnwrap(BootstrapCookie.make(for: connection))
        await cookie(bootstrap, in: configuration.websiteDataStore)
        let installedCookies = await cookies(configuration.websiteDataStore)
        XCTAssertTrue(installedCookies.contains { $0.name == "mia_bootstrap" && $0.isHTTPOnly && !$0.isSecure })
        let visibleCookies = try await javascript(view, "return document.cookie.includes('mia_bootstrap');")
        XCTAssertEqual(visibleCookies as? Bool, false)

        _ = try await javascript(view, "document.querySelector('#setup-form input[name=name]').value='Synthetic WebKit'; document.querySelector('#setup-form input[name=password]').value='synthetic-wk-password-123'; document.querySelector('#setup-form').requestSubmit(); return true;")
        try await wait(view, "document.querySelector('#migration-form')", label: "sources-first onboarding")
        try await assertNumber(view, "return document.querySelectorAll('.journey li').length;", 3)
        try await assertNumber(view, "return (await (await fetch('/api/documents')).json()).length;", 0)
        let afterSetup = await cookies(configuration.websiteDataStore)
        XCTAssertFalse(afterSetup.contains { $0.name == "mia_bootstrap" })
        XCTAssertTrue(afterSetup.contains { $0.name == "mia_session" && $0.isHTTPOnly })

        // Use actual File/DataTransfer APIs, actual chunk upload/checksum, and
        // the product's review UI. No API shortcut imports the documents.
        let archive = try Data(contentsOf: URL(fileURLWithPath: zipPath)).base64EncodedString()
        _ = try await javascript(view, "const bytes=Uint8Array.from(atob(archive), c=>c.charCodeAt(0)); const transfer=new DataTransfer(); transfer.items.add(new File([bytes],'synthetic-webkit.zip',{type:'application/zip'})); document.querySelector('#migration-form input[name=file]').files=transfer.files; document.querySelector('#migration-form').requestSubmit(); return true;", arguments: ["archive": archive])
        try await wait(view, "document.querySelector('#confirm-migration')", label: "explicit source review")
        try await assertNumber(view, "return (await (await fetch('/api/documents')).json()).length;", 0)
        _ = try await javascript(view, "document.querySelector('#confirm-migration').click(); return true;")
        try await wait(view, "(await (await fetch('/api/documents')).json()).length===2", label: "authorized imported sources")

        // WebKit itself must expose a directory-capable chooser and enumerate
        // only the selected synthetic directory. NSOpenPanel's physical dialog
        // remains a separate human acceptance check.
        let panels = FixturePanels(folder: URL(fileURLWithPath: folderPath), origin: origin)
        view.uiDelegate = panels
        try await assertBoolean(view, "return 'webkitdirectory' in document.querySelector('#migration-folder');", true)
        _ = try await javascript(view, "document.querySelector('#choose-folder').click(); return true;")
        try await wait(view, "document.querySelector('#confirm-migration') && (await (await fetch('/api/migrations')).json()).length===2", label: "native directory import review")
        XCTAssertEqual(panels.folderRequests, 1)
        XCTAssertTrue(panels.directoryParameters)
        XCTAssertEqual(panels.confirmations, 1)
        try await assertBoolean(view, "return Array.from(document.querySelector('#migration-folder').files).some(file=>file.name==='outside-secret.md'||file.name==='escaped.md');", false, "Directory upload must not read outside the selected folder through a symlink")
        try await assertNumber(view, "return (await (await fetch('/api/documents')).json()).length;", 2)
        _ = try await javascript(view, "document.querySelector('#confirm-migration').click(); return true;")
        try await wait(view, "(await (await fetch('/api/migrations')).json()).every(batch=>['completed','partial'].includes(batch.state))", label: "completed directory review")
        try await assertNumber(view, "return (await (await fetch('/api/documents')).json()).length;", 2)
        view.uiDelegate = coordinator

        _ = try await javascript(view, "document.querySelector('#guide-next').click(); return true;")
        try await wait(view, "document.querySelector('#focus-form')", label: "focus selection")
        let selectedSource = try await javascript(view, "document.querySelector('#focus-title').value='Retomar o projeto Aurora'; const choice=document.querySelector('#focus-form input[name=source_ids]'); choice.checked=true; choice.dispatchEvent(new Event('change',{bubbles:true})); const id=choice.value; document.querySelector('#guide-next').click(); return id;")
        let selectedSourceID = try XCTUnwrap(selectedSource as? String)
        try await wait(view, "document.querySelector('#guide-body h2')?.textContent==='2 fontes disponíveis para usar.'", label: "first value summary")
        let savedFocus = try await javascript(view, "return (await (await fetch('/api/experience')).json()).focus.source_ids;")
        XCTAssertEqual(savedFocus as? [String], [selectedSourceID])
        _ = try await javascript(view, "document.querySelector('#guide-back').click(); return true;")
        try await wait(view, "document.querySelector('#focus-title')?.value==='Retomar o projeto Aurora'", label: "persistent back navigation")
        _ = try await javascript(view, "document.querySelector('#guide-next').click(); return true;")
        try await wait(view, "document.querySelector('#guide-body h2')?.textContent==='2 fontes disponíveis para usar.'", label: "confirmed focus summary")
        _ = try await javascript(view, "document.querySelector('#guide-next').click(); return true;")
        try await wait(view, "document.querySelector('.source-card button[data-document]')", label: "useful Today source")
        _ = try await javascript(view, "document.querySelector('.source-card button[data-document]').click(); return true;")
        try await wait(view, "document.querySelector('#source-dialog')?.textContent.includes('Aurora')", label: "original source dialog")
        _ = try await javascript(view, "document.querySelector('#source-dialog button').click(); return true;")
        view.reload()
        try await wait(view, "document.querySelector('.source-card button[data-document]') && document.body.textContent.includes('Retomar o projeto Aurora')", label: "reload retaining focus and session")
        let restoredFocus = try await javascript(view, "return (await (await fetch('/api/experience')).json()).focus.source_ids;")
        XCTAssertEqual(restoredFocus as? [String], [selectedSourceID])
        _ = try await javascript(view, "document.querySelector('#logout').click(); return true;")
        try await wait(view, "document.querySelector('#login-form')", label: "logout")
        try await assertNumber(view, "return (await fetch('/api/documents')).status;", 401)
        _ = try await javascript(view, "document.querySelector('#login-form input[name=password]').value='synthetic-wk-password-123'; document.querySelector('#login-form').requestSubmit(); return true;")
        try await wait(view, "document.querySelector('.source-card button[data-document]')", label: "ordinary login restoring first value")
        _ = try await javascript(view, "document.querySelector('[data-view=settings]').click(); return true;")
        try await wait(view, "document.querySelector('#system-ai')", label: "settings")
        _ = try await javascript(view, "document.querySelector('#system-ai').click(); return true;")
        try await wait(view, "document.querySelector('#ai-form')", label: "optional provider configuration")
        try await assertNumber(view, "return (await (await fetch('/api/runs')).json()).length;", 0)
        try await assertBoolean(view, "return (await (await fetch('/api/ai/config')).json()).enabled;", false)
        try await assertBoolean(view, "return document.documentElement.scrollWidth<=innerWidth;", true)

        // Apply the actual app navigation policy, not just the pure origin
        // helper. A script-driven foreign origin is cancelled in WKWebView.
        _ = try await javascript(view, "location.href='http://127.0.0.1:1/untrusted'; return true;")
        try await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertEqual(WebOrigin(try XCTUnwrap(view.url)), origin)
        let isolated = WKWebsiteDataStore.nonPersistent()
        let isolatedCookies = await cookies(isolated)
        XCTAssertFalse(isolatedCookies.contains { $0.name == "mia_session" || $0.name == "mia_bootstrap" })
        let report: [String: Any] = [
            "schema": 1, "engine": "actual macOS WKWebView", "corpus": "disposable synthetic-only",
            "checks": ["unprivileged URL cannot create owner", "private HttpOnly bootstrap cookie", "cookie cleared after owner creation", "ordinary HttpOnly session", "File and DataTransfer upload", "chunked checksum transfer", "explicit review before indexing", "actual directory-capable WebKit callback", "directory symlink does not escape selection", "native directory enumeration", "confirmed focus and original source", "back and reload preserve focus", "logout and ordinary login", "optional provider settings and zero model calls", "native coordinator origin policy", "isolated cookie stores"],
            "source_count": 2, "model_calls": 0,
            "physical_file_dialog_verified": false, "gatekeeper_verified": false,
            "os_login_boot_sleep_verified": false, "personal_vault_verified": false
        ]
        try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys]).write(to: URL(fileURLWithPath: reportPath), options: .atomic)
    }
}
#endif
