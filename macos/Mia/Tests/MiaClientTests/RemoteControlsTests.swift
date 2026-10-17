#if os(macOS)
import Foundation
import XCTest
import MiaCore
@testable import Mia

private actor RemoteControlsBridge: BridgeCalling {
    private var responses: [String: [[String: JSONValue]]]
    private let failures: Set<String>
    private var history: [BridgeRequest] = []
    init(_ responses: [String: [[String: JSONValue]]] = [:], failures: Set<String> = []) {
        self.responses = responses; self.failures = failures
    }
    func call(_ request: BridgeRequest) async throws -> [String: JSONValue] {
        history.append(request)
        if failures.contains(request.action) { throw BridgeFailure.backend("Resultado remoto não confirmado; confira a recuperação.") }
        guard var queue = responses[request.action], !queue.isEmpty else { throw BridgeFailure.invalidResponse }
        let response = queue.removeFirst(); responses[request.action] = queue
        return response
    }
    func requests() -> [BridgeRequest] { history }
}

final class RemoteControlsTests: XCTestCase {
    private let reviewHash = String(repeating: "b", count: 64)
    private func connection(_ identity: String = "fixture-installation", port: Int = 8190, paused: Bool = false) -> [String: JSONValue] {
        ["connection_id": .string("fixture-connection"), "installation_id": .string(identity), "mode": .string("ssh"),
         "host": .string("server.example"), "user": .string("fixture-user"), "port": .number(22), "remote_port": .number(8123),
         "host_key_fingerprint": .string("SHA256:fixture-pinned-host"), "url": .string("http://127.0.0.1:\(port)/"),
         "version": .string("0.2.0a13"), "running": .bool(!paused), "paused": .bool(paused), "recovery_required": .bool(false)]
    }
    private func plan(_ operation: RemoteOperation, paused: Bool = false) -> [String: JSONValue] {
        ["connection_id": .string("fixture-connection"), "installation_id": .string("fixture-installation"),
         "host_key_fingerprint": .string("SHA256:fixture-pinned-host"), "sha256": .string(reviewHash),
         "summary": .array([.string("Operar somente esta instalação no servidor; preservar a biblioteca.")]),
         "current_version": .string("0.2.0a13"), "candidate_version": .string("0.2.0a14"),
         "paused": .bool(paused), "update_available": .bool(operation == .bundledUpdate), "recovery_required": .bool(operation == .recovery)]
    }
    @MainActor private func model(_ bridge: RemoteControlsBridge, selected: [String: JSONValue]? = nil) throws -> MiaModel {
        let result = MiaModel(bridge: bridge, preferences: UserDefaults(suiteName: "mia-remote-controls-tests-" + UUID().uuidString)!)
        result.state.show(try MiaConnection(selected ?? connection()))
        return result
    }

    @MainActor func testHTTPSDoesNotAuthorizeServerOperations() async throws {
        let bridge = RemoteControlsBridge()
        let client = try model(bridge, selected: ["installation_id": .string("fixture"), "url": .string("https://mia.example/"), "running": .bool(true)])
        for operation in [RemoteOperation.bundledUpdate, .snapshot, .recovery] { await client.inspectRemoteOperation(operation) }
        await client.applyRemoteOperation(); await client.snapshot()
        let requests = await bridge.requests()
        XCTAssertTrue(requests.isEmpty)
        XCTAssertNil(client.remotePlan)
    }

    @MainActor func testChangingDestinationDiscardsRemoteApprovalEvenWhenReconnectFails() async throws {
        let bridge = RemoteControlsBridge(["remote_bundle_plan": [plan(.bundledUpdate)]], failures: ["https_connect"])
        let client = try model(bridge)
        await client.inspectRemoteOperation(.bundledUpdate)
        XCTAssertNotNil(client.remotePlan)
        let other = try MiaConnection(["installation_id": .string("other"), "url": .string("https://other.example/"), "running": .bool(false)])
        await client.connectSaved(other)
        await client.applyRemoteOperation()
        XCTAssertNil(client.remotePlan)
        XCTAssertEqual(client.state.connection?.installationID, "other")
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_bundle_plan", "https_connect"])
    }

    @MainActor func testApprovalCannotApplyAfterHostIdentityOrInstallationChanges() async throws {
        for field in ["connection_id", "installation_id", "host", "host_key_fingerprint", "url"] {
            let bridge = RemoteControlsBridge(["remote_snapshot_plan": [plan(.snapshot)]])
            let client = try model(bridge)
            await client.inspectRemoteOperation(.snapshot)
            var changed = connection()
            changed[field] = .string(field == "url" ? "http://127.0.0.1:8199/" : "changed-fixture")
            client.state.show(try MiaConnection(changed))
            await client.applyRemoteOperation()
            let requests = await bridge.requests()
            XCTAssertEqual(requests.map(\.action), ["remote_snapshot_plan"], field)
        }
    }

    @MainActor func testPlanMustMatchSelectedIdentityAndPinnedHost() async throws {
        for field in ["connection_id", "installation_id", "host_key_fingerprint"] {
            var invalid = plan(.bundledUpdate); invalid[field] = .string("wrong-fixture")
            let bridge = RemoteControlsBridge(["remote_bundle_plan": [invalid]])
            let client = try model(bridge)
            await client.inspectRemoteOperation(.bundledUpdate)
            XCTAssertNil(client.remotePlan, field); XCTAssertNotNil(client.errorMessage, field)
            XCTAssertEqual(client.state.connection?.installationID, "fixture-installation")
        }
    }

    @MainActor func testActiveUpdateAdoptsVerifiedNewVersionAndTunnelOrigin() async throws {
        var result = connection(port: 8191); result["version"] = .string("0.2.0a14"); result["updated"] = .bool(true)
        let bridge = RemoteControlsBridge(["remote_bundle_plan": [plan(.bundledUpdate)], "remote_bundle_update": [result]])
        let client = try model(bridge)
        let originalIdentity = client.state.connection?.webIdentity
        let originalReloadID = client.webReloadID
        await client.inspectRemoteOperation(.bundledUpdate); await client.applyRemoteOperation()
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_bundle_plan", "remote_bundle_update"])
        XCTAssertEqual(requests.last?.payload, ["connection_id": .string("fixture-connection"), "approve_sha256": .string(reviewHash)])
        XCTAssertEqual(client.state.connection?.version, "0.2.0a14"); XCTAssertEqual(client.state.phase, .ready)
        XCTAssertNotEqual(client.state.connection?.webIdentity, originalIdentity); XCTAssertNotEqual(client.webReloadID, originalReloadID)
        XCTAssertNil(client.remotePlan); XCTAssertFalse(client.state.uncertainMutation)
    }

    @MainActor func testPausedUpdateNeverReconnectsOrResumesBackend() async throws {
        var result = connection(paused: true); result["version"] = .string("0.2.0a14"); result["updated"] = .bool(true)
        let bridge = RemoteControlsBridge(["remote_bundle_plan": [plan(.bundledUpdate, paused: true)], "remote_bundle_update": [result]])
        let client = try model(bridge, selected: connection(paused: true))
        await client.inspectRemoteOperation(.bundledUpdate); await client.applyRemoteOperation()
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_bundle_plan", "remote_bundle_update"])
        XCTAssertEqual(client.state.phase, .offline); XCTAssertFalse(client.state.connection?.running ?? true)
        XCTAssertEqual(client.state.connection?.metadata["paused"], .bool(true))
        XCTAssertTrue(client.notice?.contains("continua pausada") ?? false)
    }

    @MainActor func testSelectingPausedConnectionDoesNotStartIt() async throws {
        let bridge = RemoteControlsBridge()
        let client = try model(bridge)
        await client.connectSaved(try MiaConnection(connection(paused: true)))
        let requests = await bridge.requests()
        XCTAssertTrue(requests.isEmpty)
        XCTAssertEqual(client.state.phase, .offline); XCTAssertTrue(client.showControls)
    }

    @MainActor func testUnconfirmedUpdateClearsApprovalAndPreservesRecoveryAcrossPollingAndPageEvents() async throws {
        var offline = connection(); offline["running"] = .bool(false)
        let status: [String: JSONValue] = ["protocol": .number(1), "connections": .array([.object(offline)])]
        let bridge = RemoteControlsBridge(["remote_bundle_plan": [plan(.bundledUpdate)], "status": [status, status]], failures: ["remote_bundle_update"])
        let client = try model(bridge)
        let selected = client.state.connection
        await client.inspectRemoteOperation(.bundledUpdate); await client.applyRemoteOperation()
        await client.refresh(); await client.refresh(initial: true); client.pageDisconnected(); client.pageConnected()
        await client.reconnect(); await client.applyRemoteOperation()
        XCTAssertEqual(client.state.connection, selected); XCTAssertEqual(client.state.phase, .recoveryRequired)
        XCTAssertTrue(client.state.uncertainMutation); XCTAssertNil(client.remotePlan)
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_bundle_plan", "remote_bundle_update", "status", "status"])
    }

    @MainActor func testWrongUpdatedVersionDoesNotReplaceSelectedInstallation() async throws {
        var result = connection(port: 8191); result["updated"] = .bool(true) // Backend still reports the old version.
        let bridge = RemoteControlsBridge(["remote_bundle_plan": [plan(.bundledUpdate)], "remote_bundle_update": [result]])
        let client = try model(bridge)
        let selected = client.state.connection
        await client.inspectRemoteOperation(.bundledUpdate); await client.applyRemoteOperation()
        XCTAssertEqual(client.state.connection, selected); XCTAssertEqual(client.state.phase, .recoveryRequired)
        XCTAssertNil(client.remotePlan); XCTAssertNotNil(client.errorMessage)
    }

    @MainActor func testSuccessfulRecoveryResolvesUncertainOperationWithoutEmptyReinstall() async throws {
        var result = connection(port: 8192); result["recovered"] = .bool(true); result["recovery_confirmed"] = .bool(true)
        let bridge = RemoteControlsBridge(["remote_recovery_plan": [plan(.recovery)], "remote_recover": [result]])
        let client = try model(bridge)
        client.state.mutationFailed()
        await client.inspectRemoteOperation(.recovery); await client.applyRemoteOperation()
        XCTAssertFalse(client.state.uncertainMutation); XCTAssertEqual(client.state.phase, .ready)
        XCTAssertEqual(client.state.connection?.installationID, "fixture-installation")
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_recovery_plan", "remote_recover"])
    }

    @MainActor func testUnconfirmedRecoveryRetainsOriginalDestination() async throws {
        let bridge = RemoteControlsBridge(["remote_recovery_plan": [plan(.recovery)]], failures: ["remote_recover"])
        let client = try model(bridge)
        client.state.mutationFailed(); let selected = client.state.connection
        await client.inspectRemoteOperation(.recovery); await client.applyRemoteOperation()
        XCTAssertEqual(client.state.connection, selected); XCTAssertEqual(client.state.phase, .recoveryRequired)
        XCTAssertTrue(client.state.uncertainMutation); XCTAssertNil(client.remotePlan)
    }

    @MainActor func testNoOpRecoveryConfirmsStoppedDestinationWithoutStartingIt() async throws {
        var result = connection(); result["running"] = .bool(false)
        result["recovered"] = .bool(false); result["recovery_confirmed"] = .bool(true)
        let bridge = RemoteControlsBridge(["remote_recovery_plan": [plan(.recovery)], "remote_recover": [result]])
        let client = try model(bridge); client.state.mutationFailed()
        await client.inspectRemoteOperation(.recovery); await client.applyRemoteOperation()
        XCTAssertFalse(client.state.uncertainMutation); XCTAssertEqual(client.state.phase, .offline)
        XCTAssertEqual(client.state.connection?.installationID, "fixture-installation")
        XCTAssertTrue(client.notice?.contains("não o iniciou") ?? false)
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_recovery_plan", "remote_recover"])
    }

    @MainActor func testSnapshotRequiresConcreteReviewAndVerifiedResult() async throws {
        var result = connection(); result["snapshot_id"] = .string("fixture-snapshot"); result["verified"] = .bool(true)
        let bridge = RemoteControlsBridge(["remote_snapshot_plan": [plan(.snapshot)], "remote_snapshot": [result]])
        let client = try model(bridge); let selected = client.state.connection
        await client.applyRemoteOperation()
        let beforeReview = await bridge.requests()
        XCTAssertTrue(beforeReview.isEmpty)
        await client.inspectRemoteOperation(.snapshot); await client.applyRemoteOperation()
        let requests = await bridge.requests()
        XCTAssertEqual(requests.map(\.action), ["remote_snapshot_plan", "remote_snapshot"])
        XCTAssertEqual(requests.last?.payload["approve_sha256"], .string(reviewHash))
        XCTAssertEqual(client.state.connection, selected); XCTAssertEqual(client.state.phase, .ready)
        XCTAssertTrue(client.notice?.contains("mesmo destino") ?? false)
    }
}
#endif
