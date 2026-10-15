#if os(macOS)
import Foundation
import Network
import XCTest
@testable import Mia

@MainActor private final class MemoryBetaSecrets: BetaSecretStoring {
    var values: [String: Data] = [:]
    var failWrite = false
    var failLeaseWrite = false
    func read(_ account: String) throws -> Data? { values[account] }
    func write(_ data: Data, account: String) throws {
        if failWrite || (failLeaseWrite && account.hasSuffix(".lease")) { throw BetaAccessFailure.storageUnavailable }
        values[account] = data
    }
    func delete(_ account: String) throws { values.removeValue(forKey: account) }
}

private actor ScriptedBetaHTTP: BetaHTTPCalling {
    private var results: [Result<BetaHTTPResponse, BetaAccessFailure>]
    private var history: [(URL, Data)] = []
    init(_ results: [Result<BetaHTTPResponse, BetaAccessFailure>]) { self.results = results }
    func activate(url: URL, body: Data) async throws -> BetaHTTPResponse {
        history.append((url, body))
        guard !results.isEmpty else { throw BetaAccessFailure.unavailable }
        return try results.removeFirst().get()
    }
    func requests() -> [(URL, Data)] { history }
}

final class BetaAccessTests: XCTestCase {
    private let ticket = String(repeating: "t", count: 43)
    private let nonce = String(repeating: "n", count: 43)
    private let token = String(repeating: "a", count: 43)
    private func policy(_ origin: String = "https://updates.example") throws -> BetaDistributionPolicy {
        try BetaDistributionPolicy(distributionURL: origin, feedURL: origin + "/updates/arm64/appcast.xml", architecture: "arm64")
    }
    private func response(expiry: Int = 2_000, url: URL? = nil, status: Int = 200, type: String = "application/json") throws -> BetaHTTPResponse {
        let defaultURL = try policy().activationURL
        return BetaHTTPResponse(status: status, url: url ?? defaultURL, contentType: type,
                                body: try JSONSerialization.data(withJSONObject: ["access_token": token, "expires_at": expiry]))
    }
    @MainActor private func access(_ store: MemoryBetaSecrets, _ http: ScriptedBetaHTTP) throws -> BetaAccess {
        BetaAccess(policy: try policy(), store: store, http: http, clock: { Date(timeIntervalSince1970: 1_000) }, randomSecret: { self.nonce })
    }

    func testActivationLinkCannotOverrideTheTrustedServiceOrAddParameters() throws {
        XCTAssertEqual(try BetaDistributionPolicy.activationTicket(from: URL(string: "mia-demo://activate?ticket=" + ticket)!), ticket)
        for raw in ["https://updates.example/activate?ticket=" + ticket,
                    "mia-demo://activate?ticket=" + ticket + "&url=https://outside.example",
                    "mia-demo://activate?ticket=" + ticket + "&ticket=" + ticket,
                    "mia-demo://activate?ticket=" + ticket + "#fragment",
                    "mia-demo://user@activate?ticket=" + ticket,
                    "mia-demo://activate/extra?ticket=" + ticket,
                    "mia-demo://activate?ticket=short"] {
            XCTAssertThrowsError(try BetaDistributionPolicy.activationTicket(from: URL(string: raw)!))
        }
    }

    func testChannelAndDownloadsAreBoundToOriginPrefixAndArchitecture() throws {
        let trusted = try policy("https://updates.example/api/mia")
        XCTAssertTrue(trusted.allowsFeed(URL(string: "https://updates.example/api/mia/updates/arm64/appcast.xml")!))
        XCTAssertTrue(trusted.allowsDownload(URL(string: "https://updates.example/api/mia/app-updates/0.2.0a14-s1/arm64")!))
        for raw in ["https://updates.example.evil/api/mia/app-updates/release/arm64",
                    "http://updates.example/api/mia/app-updates/release/arm64",
                    "https://updates.example/api/other/app-updates/release/arm64",
                    "https://updates.example/api/mia/app-updates/release/x86_64",
                    "https://updates.example/api/mia/app-updates/release/arm64?token=anything",
                    "https://updates.example/api/mia/app-updates/release/arm64#fragment",
                    "https://updates.example/api/mia/app-updates/%2e%2e/arm64",
                    "https://blob.example/private/Mia.dmg"] {
            XCTAssertFalse(trusted.allowsDownload(URL(string: raw)!), raw)
        }
        XCTAssertThrowsError(try BetaDistributionPolicy(distributionURL: "https://updates.example", feedURL: "https://outside.example/updates/arm64/appcast.xml", architecture: "arm64"))
    }

    @MainActor func testNonceIsDurableBeforeARequestAndReusedAfterLostResponseAndRestart() async throws {
        let store = MemoryBetaSecrets()
        let http = ScriptedBetaHTTP([.failure(.unavailable), .success(try response())])
        let initial = try access(store, http); initial.activationTicket = ticket
        await initial.activate()
        let account = try policy().identity + ".pending." + BetaDistributionPolicy.hash(ticket)
        XCTAssertEqual(store.values[account], Data(nonce.utf8))
        XCTAssertFalse(initial.canUpdate)
        let restarted = try access(store, http); restarted.activationTicket = ticket
        await restarted.activate()
        let requests = await http.requests()
        XCTAssertEqual(requests.count, 2)
        for (_, body) in requests {
            let data = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: String])
            XCTAssertEqual(data, ["ticket": ticket, "client_nonce": nonce, "architecture": "arm64"])
        }
        XCTAssertTrue(restarted.canUpdate)
        XCTAssertTrue(store.values.keys.allSatisfy { !$0.contains(ticket) })
        XCTAssertTrue(store.values.values.allSatisfy { String(data: $0, encoding: .utf8)?.contains(ticket) != true })
        XCTAssertEqual(store.values[account], Data(nonce.utf8)) // Reopening the same link remains idempotent.
    }

    @MainActor func testKeychainFailurePreventsSendingAOneUseTicket() async throws {
        let store = MemoryBetaSecrets(); store.failWrite = true
        let http = ScriptedBetaHTTP([.success(try response())])
        let client = try access(store, http); client.activationTicket = ticket
        await client.activate()
        let requests = await http.requests()
        XCTAssertTrue(requests.isEmpty); XCTAssertFalse(client.canUpdate)
    }

    @MainActor func testLostLeaseWriteKeepsNonceForIdempotentRetry() async throws {
        let store = MemoryBetaSecrets(); store.failLeaseWrite = true
        let http = ScriptedBetaHTTP([.success(try response()), .success(try response())])
        let client = try access(store, http); client.activationTicket = ticket
        await client.activate(); XCTAssertFalse(client.canUpdate)
        store.failLeaseWrite = false
        await client.activate()
        XCTAssertTrue(client.canUpdate)
        let requests = await http.requests()
        XCTAssertEqual(requests.count, 2); XCTAssertEqual(requests[0].1, requests[1].1)
    }

    @MainActor func testStoredAuthorizationRestoresWithoutNetworkAndNeverAuthorizesForeignHosts() async throws {
        let store = MemoryBetaSecrets(); let http = ScriptedBetaHTTP([.success(try response())])
        let initial = try access(store, http); initial.activationTicket = ticket; await initial.activate()
        let restarted = try access(store, http)
        XCTAssertEqual(try restarted.authorization(for: policy().feedURL), "Bearer " + token)
        XCTAssertEqual(try restarted.authorization(for: URL(string: "https://updates.example/app-updates/0.2.0a14-s1/arm64")!, download: true), "Bearer " + token)
        XCTAssertThrowsError(try restarted.authorization(for: URL(string: "https://blob.example/Mia.dmg")!, download: true))
        let requests = await http.requests(); XCTAssertEqual(requests.count, 1)
    }

    @MainActor func testExpiredOrRevokedAccessBlocksOnlyDistributionAuthorization() async throws {
        let store = MemoryBetaSecrets()
        let http = ScriptedBetaHTTP([.success(try response(status: 410))])
        let client = try access(store, http); client.activationTicket = ticket; await client.activate()
        XCTAssertFalse(client.canUpdate); XCTAssertThrowsError(try client.authorization(for: policy().feedURL))
        XCTAssertEqual(client.message, BetaAccessFailure.invalidTicket.localizedDescription)
        store.values[try policy().identity + ".lease"] = try JSONSerialization.data(withJSONObject: ["token": token, "expiresAt": 999])
        let expired = try access(store, http)
        XCTAssertFalse(expired.canUpdate); XCTAssertThrowsError(try expired.authorization(for: policy().feedURL))
        // This component owns only a distribution credential. It has no bridge,
        // backend login, filesystem-library or provider mutation capability.
        XCTAssertEqual(store.values.count, 2)
    }

    @MainActor func testActivationRejectsRedirectedOversizedOrUnboundedAuthorization() async throws {
        let cases = [
            try response(expiry: 999),
            try response(expiry: 1_000 + 91 * 86_400),
            try response(url: URL(string: "https://outside.example/beta/activate")!),
            try response(type: "text/html"),
            BetaHTTPResponse(status: 200, url: try policy().activationURL, contentType: "application/json", body: Data(repeating: 65, count: 16_385)),
        ]
        for result in cases {
            let client = try access(MemoryBetaSecrets(), ScriptedBetaHTTP([.success(result)])); client.activationTicket = ticket
            await client.activate(); XCTAssertFalse(client.canUpdate)
            XCTAssertFalse(client.message.contains(ticket)); XCTAssertFalse(client.message.contains(token))
        }
    }

    @MainActor func testUnconfiguredAppNeverActivatesAnExternalLink() async throws {
        let http = ScriptedBetaHTTP([])
        let client = BetaAccess(policy: nil, store: MemoryBetaSecrets(), http: http)
        await client.accept(URL(string: "mia-demo://activate?ticket=" + ticket)!)
        let requests = await http.requests(); XCTAssertTrue(requests.isEmpty)
        XCTAssertFalse(client.canUpdate)
    }
}

/// Actual system NSURLSession behavior, matching Sparkle 2.10's downloader.
/// The second HTTP endpoint has a different hostname and must never receive
/// Authorization when the first endpoint redirects to a private Blob lease.
private final class RedirectFixtureServer: @unchecked Sendable {
    private let queue = DispatchQueue(label: "mia-beta-redirect-fixture-" + UUID().uuidString)
    private let listener: NWListener
    private let lock = NSLock()
    private var requests: [String] = []
    private let reply: String
    init(_ reply: String) throws { self.reply = reply; listener = try NWListener(using: .tcp, on: .any) }
    func start() async throws -> Int {
        try await withCheckedThrowingContinuation { continuation in
            var waiting = true
            listener.stateUpdateHandler = { [weak self] state in
                guard waiting else { return }
                if case .ready = state, let port = self?.listener.port { waiting = false; continuation.resume(returning: Int(port.rawValue)) }
                else if case .failed(let error) = state { waiting = false; continuation.resume(throwing: error) }
            }
            listener.newConnectionHandler = { [weak self] connection in
                guard let self else { connection.cancel(); return }
                connection.start(queue: self.queue)
                self.receive(connection, bytes: Data())
            }
            listener.start(queue: queue)
        }
    }
    private func receive(_ connection: NWConnection, bytes: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 16_384) { [weak self] content, _, complete, error in
            guard let self else { connection.cancel(); return }
            let combined = bytes + (content ?? Data())
            guard combined.count <= 32_768, error == nil else { connection.cancel(); return }
            if let raw = String(data: combined, encoding: .utf8), raw.contains("\r\n\r\n") {
                self.lock.lock(); self.requests.append(raw); self.lock.unlock()
                connection.send(content: Data(self.reply.utf8), completion: .contentProcessed { _ in connection.cancel() })
            } else if !complete { self.receive(connection, bytes: combined) }
            else { connection.cancel() }
        }
    }
    func received() -> [String] { lock.lock(); defer { lock.unlock() }; return requests }
    func stop() { listener.cancel() }
}

final class BetaRedirectTests: XCTestCase {
    func testSystemSessionStripsAuthorizationOnCrossHostRedirect() async throws {
        let target = try RedirectFixtureServer("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        let targetPort = try await target.start(); defer { target.stop() }
        let source = try RedirectFixtureServer("HTTP/1.1 302 Found\r\nLocation: http://localhost:\(targetPort)/lease\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        let sourcePort = try await source.start(); defer { source.stop() }
        var request = URLRequest(url: URL(string: "http://127.0.0.1:\(sourcePort)/download")!, timeoutInterval: 10)
        request.setValue("Bearer synthetic-private-entitlement", forHTTPHeaderField: "Authorization")
        let session = URLSession(configuration: .default); defer { session.invalidateAndCancel() }
        let (data, _) = try await session.data(for: request)
        XCTAssertEqual(data, Data("ok".utf8)); XCTAssertEqual(source.received().count, 1); XCTAssertEqual(target.received().count, 1)
        XCTAssertTrue(source.received()[0].lowercased().contains("authorization: bearer synthetic-private-entitlement"))
        XCTAssertFalse(target.received()[0].lowercased().contains("authorization:"))
    }
    func testActivationTransportRefusesRedirectBeforeForwardingTicket() async throws {
        let target = try RedirectFixtureServer("HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        let targetPort = try await target.start(); defer { target.stop() }
        let source = try RedirectFixtureServer("HTTP/1.1 307 Temporary Redirect\r\nLocation: http://localhost:\(targetPort)/activate\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        let sourcePort = try await source.start(); defer { source.stop() }
        do {
            _ = try await BetaHTTPClient().activate(url: URL(string: "http://127.0.0.1:\(sourcePort)/activate")!, body: Data(#"{"ticket":"synthetic-only"}"#.utf8))
            XCTFail("Redirected activation accepted")
        } catch { XCTAssertEqual(error as? BetaAccessFailure, .unsafeURL) }
        XCTAssertEqual(source.received().count, 1); XCTAssertTrue(target.received().isEmpty)
    }
}
#endif
