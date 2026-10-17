#if os(macOS)
import Foundation
import XCTest
import MiaCore
@testable import Mia

private actor RecordedBridge: BridgeCalling {
    private var responses: [String: [[String: JSONValue]]]
    private let failures: Set<String>
    private var history: [BridgeRequest] = []

    init(_ responses: [String: [[String: JSONValue]]] = [:], failures: Set<String> = []) {
        self.responses = responses
        self.failures = failures
    }

    func call(_ request: BridgeRequest) async throws -> [String: JSONValue] {
        history.append(request)
        if failures.contains(request.action) { throw BridgeFailure.backend("Falha sintética; confira a instalação.") }
        guard var queued = responses[request.action], !queued.isEmpty else { throw BridgeFailure.invalidResponse }
        let response = queued.removeFirst()
        responses[request.action] = queued
        return response
    }

    func requests() -> [BridgeRequest] { history }
}

final class ControllerTests: XCTestCase {
    private func localValues(_ identity: String = "local-fixture") -> [String: JSONValue] {
        ["installation_id": .string(identity), "url": .string("http://127.0.0.1:8190/"), "version": .string("0.2.0a13"), "running": .bool(true)]
    }
    private var review: [String: JSONValue] {
        ["sha256": .string(String(repeating: "a", count: 64)), "summary": .array([.string("Atualizar somente esta instalação com recuperação.")]), "update_available": .bool(true)]
    }
    @MainActor private func model(_ bridge: RecordedBridge) -> MiaModel {
        // Test preferences are isolated from any real selected installation.
        MiaModel(bridge: bridge, preferences: UserDefaults(suiteName: "mia-controller-tests-" + UUID().uuidString)!)
    }

    @MainActor func testSwitchingDestinationDiscardsReviewedLocalUpdate() async throws {
        let remote: [String: JSONValue] = ["connection_id": .string("remote-fixture"), "installation_id": .string("remote-instance"), "mode": .string("https"), "url": .string("https://mia.example/"), "running": .bool(true)]
        let bridge = RecordedBridge(["local_bundle_plan": [review], "https_connect": [remote]])
        let client = model(bridge)
        client.state.show(try MiaConnection(localValues(), local: true))
        await client.inspectBundledUpdate()
        XCTAssertNotNil(client.updatePlan)

        await client.connectSaved(try MiaConnection(remote))
        XCTAssertNil(client.updatePlan)
        XCTAssertFalse(client.backendRefreshPlan)
        await client.applyBundledUpdate()
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["local_bundle_plan", "https_connect"])
        XCTAssertEqual(client.state.connection?.installationID, "remote-instance")
    }

    @MainActor func testReviewedUpdateCannotApplyToAnotherLocalInstallation() async throws {
        let bridge = RecordedBridge(["local_bundle_plan": [review]])
        let client = model(bridge)
        client.state.show(try MiaConnection(localValues("original-instance"), local: true))
        await client.inspectBundledUpdate()
        client.state.show(try MiaConnection(localValues("replacement-instance"), local: true))
        await client.applyBundledUpdate()
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["local_bundle_plan"])
        XCTAssertEqual(client.state.connection?.installationID, "replacement-instance")
    }

    @MainActor func testHostApprovalCannotBeReusedAfterEditingServer() async throws {
        let first: [String: JSONValue] = ["host_key_fingerprint": .string("SHA256:synthetic-first"), "host_key_known": .bool(false)]
        let second: [String: JSONValue] = ["host_key_fingerprint": .string("SHA256:synthetic-second"), "host_key_known": .bool(false)]
        let bridge = RecordedBridge(["remote_preflight": [first, second]])
        let client = model(bridge)
        client.serverHost = "first.example"; client.serverUser = "tester"
        await client.inspectServer()
        XCTAssertEqual(client.hostFingerprint, "SHA256:synthetic-first")

        client.serverHost = "second.example"
        await client.approveHostIdentity()
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_preflight", "remote_preflight"])
        XCTAssertEqual(requests.last?.payload["host"], .string("second.example"))
        XCTAssertNil(requests.last?.payload["approved_host_fingerprint"])
        XCTAssertEqual(client.hostFingerprint, "SHA256:synthetic-second")
        XCTAssertNil(client.plan)
    }

    @MainActor func testReconnectingSavedServerOnlyReconnectsAndChangesWebOrigin() async throws {
        let original: [String: JSONValue] = ["connection_id": .string("saved-fixture"), "installation_id": .string("existing-instance"), "mode": .string("ssh"), "url": .string("http://127.0.0.1:8190/"), "running": .bool(false)]
        var restored = original
        restored["url"] = .string("http://127.0.0.1:8191/"); restored["running"] = .bool(true)
        let bridge = RecordedBridge(["remote_connect": [restored]])
        let client = model(bridge)
        let selected = try MiaConnection(original)
        await client.connectSaved(selected)
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_connect"])
        XCTAssertEqual(requests.first?.payload, ["connection_id": .string("saved-fixture")])
        XCTAssertEqual(client.state.connection?.installationID, "existing-instance")
        XCTAssertNotEqual(client.state.connection?.webIdentity, selected.webIdentity)
        XCTAssertEqual(client.state.phase, .ready)
    }

    @MainActor func testUnconfirmedStopPreservesInstallationAndRequiresRecovery() async throws {
        let bridge = RecordedBridge(failures: ["local_stop"])
        let client = model(bridge)
        let selected = try MiaConnection(localValues(), local: true)
        client.state.show(selected)
        await client.stopLocal()
        XCTAssertEqual(client.state.connection, selected)
        XCTAssertEqual(client.state.phase, .recoveryRequired)
        XCTAssertTrue(client.state.uncertainMutation)
        XCTAssertFalse(client.busy)
        XCTAssertNotNil(client.errorMessage)
    }
}
#endif
