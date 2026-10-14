import Foundation
import XCTest
@testable import MiaCore

final class SafetyTests: XCTestCase {
    func testSelectedOriginBlocksOtherLocalPortsAndInsecureServers() throws {
        let origin = try XCTUnwrap(WebOrigin(URL(string: "http://127.0.0.1:8123/")!))
        XCTAssertTrue(origin.allows(URL(string: "http://127.0.0.1:8123/api/migrations")!))
        for string in ["http://127.0.0.1:8124/", "http://localhost:8123/", "https://127.0.0.1:8123/", "file:///etc/passwd", "javascript:alert(1)", "http://192.168.1.10:8123/", "http://mia.example/"] {
            XCTAssertFalse(origin.allows(URL(string: string)!), string)
        }
        XCTAssertNil(WebOrigin(URL(string: "http://mia.example/")!))
        XCTAssertNil(WebOrigin(URL(string: "https://owner:password@mia.example/")!))
    }

    func testHTTPSOriginUsesEffectivePortAndDoesNotAcceptLookalikes() throws {
        let origin = try XCTUnwrap(WebOrigin(URL(string: "https://mia.example/")!))
        XCTAssertTrue(origin.allows(URL(string: "https://MIA.example:443/library")!))
        XCTAssertFalse(origin.allows(URL(string: "https://mia.example.evil/")!))
        XCTAssertFalse(origin.allows(URL(string: "https://mia.example:444/")!))
        XCTAssertFalse(WebOrigin.externalLinkAllowed(URL(string: "mia-exec://open/")!))
        XCTAssertFalse(WebOrigin.externalLinkAllowed(URL(string: "https://user:secret@example.com/")!))
    }

    func testConnectionRequiresIdentityAndCorrectTransport() throws {
        let value: [String: JSONValue] = ["installation_id": .string("owner-instance"), "url": .string("http://127.0.0.1:8190/"), "running": .bool(true)]
        let local = try MiaConnection(value, local: true)
        XCTAssertEqual(local.id, "local"); XCTAssertEqual(local.mode, "local")
        XCTAssertThrowsError(try MiaConnection(value)) // HTTPS mode cannot adopt HTTP.
        var remote = value; remote["mode"] = .string("ssh"); remote["connection_id"] = .string("saved-server")
        XCTAssertEqual(try MiaConnection(remote).id, "saved-server")
        remote["url"] = .string("http://remote.example:8123/")
        XCTAssertThrowsError(try MiaConnection(remote))
        remote["installation_id"] = .null
        XCTAssertThrowsError(try MiaConnection(remote))
    }
    func testWebIdentityChangesWhenATunnelReconnectsOnAnotherPort() throws {
        let original: [String: JSONValue] = ["connection_id": .string("same-server"), "installation_id": .string("same-installation"), "mode": .string("ssh"), "url": .string("http://127.0.0.1:8190/")]
        var reconnected = original; reconnected["url"] = .string("http://127.0.0.1:8191/")
        XCTAssertNotEqual(try MiaConnection(original).webIdentity, try MiaConnection(reconnected).webIdentity)
        var another = original; another["installation_id"] = .string("another-installation")
        XCTAssertNotEqual(try MiaConnection(original).webIdentity, try MiaConnection(another).webIdentity)
    }

    func testReviewNeedsExactHashAndReadableScope() throws {
        let review = ["sha256": JSONValue.string(String(repeating: "a", count: 64)), "summary": .array([.string("Criar Mia vazia neste Mac.")]), "details": .object(["port": .number(8123)])]
        XCTAssertEqual(try ReviewPlan(review).summary.count, 1)
        var bad = review; bad["sha256"] = .string(String(repeating: "A", count: 64)); XCTAssertThrowsError(try ReviewPlan(bad))
        bad = review; bad["summary"] = .array([]); XCTAssertThrowsError(try ReviewPlan(bad))
        bad = review; bad["sha256"] = .string("unreviewed"); XCTAssertThrowsError(try ReviewPlan(bad))
    }

    func testUncertainMutationPreservesSelectedInstallation() throws {
        var state = ClientState()
        let connection = try MiaConnection(["installation_id": .string("existing"), "url": .string("http://127.0.0.1:8123/"), "running": .bool(true)], local: true)
        state.show(connection); state.disconnected()
        XCTAssertEqual(state.phase, .offline); XCTAssertEqual(state.connection, connection)
        state.mutationFailed()
        XCTAssertEqual(state.phase, .recoveryRequired); XCTAssertTrue(state.uncertainMutation); XCTAssertEqual(state.connection?.installationID, "existing")
        state.show(connection); XCTAssertFalse(state.uncertainMutation)
    }

    func testBridgeRejectsPrivilegedOrUnknownActions() throws {
        for action in ["exec", "read_file", "shell", "install_at", "open_terminal"] { XCTAssertThrowsError(try BridgeRequest(action: action)) }
        let request = try BridgeRequest(action: "local_install", payload: ["approve_sha256": .string(String(repeating: "f", count: 64))])
        let encoded = try JSONEncoder().encode(request)
        XCTAssertTrue(String(decoding: encoded, as: UTF8.self).contains("approve_sha256"))
    }

    func testResponseCannotMixSuccessAndErrorOrOmitResult() throws {
        let decoder = JSONDecoder()
        for json in [#"{"ok":true}"#, #"{"ok":true,"result":{},"error":{"code":"bad","message":"bad"}}"#, #"{"ok":true,"result":[]}"#] {
            XCTAssertThrowsError(try decoder.decode(BridgeResponse.self, from: Data(json.utf8)).checkedResult())
        }
        let failure = try decoder.decode(BridgeResponse.self, from: Data(#"{"ok":false,"error":{"code":"safe","message":"Destino indisponível."}}"#.utf8))
        XCTAssertThrowsError(try failure.checkedResult()) { XCTAssertEqual($0 as? BridgeFailure, .backend("Destino indisponível.")) }
    }
    func testFirstOwnerCookieIsHTTPOnlyAndUsesSelectedTransport() throws {
        let token = String(repeating: "x", count: 43)
        let local = try MiaConnection(["installation_id": .string("fresh"), "url": .string("http://127.0.0.1:8123/"), "bootstrap_token": .string(token)], local: true)
        let cookie = try XCTUnwrap(BootstrapCookie.make(for: local))
        XCTAssertEqual(cookie.name, "mia_bootstrap"); XCTAssertEqual(cookie.domain, "127.0.0.1"); XCTAssertEqual(cookie.value, token)
        XCTAssertTrue(cookie.isHTTPOnly); XCTAssertFalse(cookie.isSecure); XCTAssertTrue(cookie.isSessionOnly)
        let remote = try MiaConnection(["installation_id": .string("fresh-server"), "url": .string("https://mia.example/"), "bootstrap_token": .string(token)])
        XCTAssertTrue(try XCTUnwrap(BootstrapCookie.make(for: remote)).isSecure)
        let alreadyConfigured = try MiaConnection(["installation_id": .string("ready"), "url": .string("https://mia.example/")])
        XCTAssertNil(try BootstrapCookie.make(for: alreadyConfigured))
    }
    func testFirstOwnerTokenCannotInjectCookieAttributes() throws {
        for token in ["too-short", String(repeating: "x", count: 40) + "; HttpOnly", String(repeating: "x", count: 40) + "\r\n", String(repeating: "x", count: 257)] {
            let connection = try MiaConnection(["installation_id": .string("fresh"), "url": .string("http://127.0.0.1:8123/"), "bootstrap_token": .string(token)], local: true)
            XCTAssertThrowsError(try BootstrapCookie.make(for: connection))
        }
    }
}
