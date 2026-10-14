import Foundation
import XCTest
@testable import MiaCore

final class BridgeRunnerTests: XCTestCase {
    private var roots: [URL] = []
    override func tearDownWithError() throws { for root in roots { try? FileManager.default.removeItem(at: root) }; roots = [] }
    private func fixture(_ body: String) throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("mia-native-bridge-tests-" + UUID().uuidString)
        roots.append(root)
        try FileManager.default.createDirectory(at: root.appendingPathComponent("runtime/bin"), withIntermediateDirectories: true)
        let executable = root.appendingPathComponent("runtime/bin/python3")
        try Data(("#!/bin/sh\n" + body + "\n").utf8).write(to: executable)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: executable.path)
        try Data("# synthetic bridge fixture".utf8).write(to: root.appendingPathComponent("desktop_bridge.py"))
        return root
    }
    func testDrainsPrivateStderrAndReturnsStructuredResult() async throws {
        let root = try fixture("/bin/cat >/dev/null\nprintf 'private synthetic diagnostic' >&2\nprintf '%s' '{\"ok\":true,\"result\":{\"protocol\":1}}'")
        let result = try await BridgeRunner(resources: root).call(BridgeRequest(action: "status"))
        XCTAssertEqual(result["protocol"], .number(1))
    }
    func testMalformedOutputDoesNotExposeDiagnostics() async throws {
        let root = try fixture("/bin/cat >/dev/null\nprintf 'synthetic secret' >&2\nprintf 'not JSON'")
        do { _ = try await BridgeRunner(resources: root).call(BridgeRequest(action: "status")); XCTFail("Invalid output accepted") }
        catch { XCTAssertEqual(error as? BridgeFailure, .invalidResponse); XCTAssertFalse(error.localizedDescription.contains("secret")) }
    }
    func testOutsideRuntimeSymlinkIsRejectedBeforeExecuting() async throws {
        let root = try fixture("printf '%s' '{\"ok\":true,\"result\":{}}'")
        let executable = root.appendingPathComponent("runtime/bin/python3")
        try FileManager.default.removeItem(at: executable)
        try FileManager.default.createSymbolicLink(atPath: executable.path, withDestinationPath: "/bin/sh")
        do { _ = try await BridgeRunner(resources: root).call(BridgeRequest(action: "status")); XCTFail("Outside executable accepted") }
        catch { XCTAssertEqual(error as? BridgeFailure, .missingRuntime) }
    }
    func testNonReadingChildCannotBlockStdinPastDeadline() async throws {
        let root = try fixture("exec /bin/sleep 30")
        let request = try BridgeRequest(action: "status", payload: ["synthetic": .string(String(repeating: "a", count: 50_000))])
        let started = Date()
        do { _ = try await BridgeRunner(resources: root, testDeadline: 0.2).call(request); XCTFail("Hung process accepted") }
        catch { XCTAssertEqual(error as? BridgeFailure, .timeout); XCTAssertLessThan(Date().timeIntervalSince(started), 8) }
    }
    func testResponseFloodIsBounded() async throws {
        let root = try fixture("/bin/cat >/dev/null\n/usr/bin/head -c 2097152 /dev/zero")
        do { _ = try await BridgeRunner(resources: root, testDeadline: 2).call(BridgeRequest(action: "status")); XCTFail("Unbounded response accepted") }
        catch { XCTAssertEqual(error as? BridgeFailure, .responseTooLarge) }
    }
    func testOversizedRequestIsRejectedBeforeExecution() async throws {
        let root = try fixture("exit 1")
        let request = try BridgeRequest(action: "status", payload: ["synthetic": .string(String(repeating: "a", count: 70_000))])
        do { _ = try await BridgeRunner(resources: root).call(request); XCTFail("Oversized request accepted") }
        catch { XCTAssertEqual(error as? BridgeFailure, .requestTooLarge) }
    }
}
