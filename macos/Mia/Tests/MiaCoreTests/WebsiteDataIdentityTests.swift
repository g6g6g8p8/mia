import Foundation
import XCTest
@testable import MiaCore

final class WebsiteDataIdentityTests: XCTestCase {
    private func connection(_ overrides: [String: JSONValue] = [:]) throws -> MiaConnection {
        let base: [String: JSONValue] = [
            "connection_id": .string("saved-server"), "installation_id": .string("personal-installation"),
            "mode": .string("ssh"), "url": .string("http://127.0.0.1:8190/"),
            "host_key_fingerprint": .string("SHA256:verified-server")
        ]
        return try MiaConnection(base.merging(overrides, uniquingKeysWith: { _, new in new }))
    }

    func testSSHLoginStoreSurvivesNewTunnelPortWhileWebViewOriginChanges() throws {
        let first = try connection()
        let reconnected = try connection(["url": .string("http://127.0.0.1:8191/")])
        XCTAssertEqual(first.websiteDataIdentity, reconnected.websiteDataIdentity)
        XCTAssertNotEqual(first.webIdentity, reconnected.webIdentity)
        XCTAssertFalse(WebOrigin(first.url)!.allows(reconnected.url))
    }

    func testDifferentConnectionsInstallationsPinsAndHostsNeverShareSSHStore() throws {
        let first = try connection()
        let differences: [[String: JSONValue]] = [
            ["connection_id": .string("another-server")],
            ["installation_id": .string("another-installation")],
            ["host_key_fingerprint": .string("SHA256:changed-server")],
            ["url": .string("http://localhost:8190/")],
            ["url": .string("https://127.0.0.1:8190/")]
        ]
        for difference in differences {
            XCTAssertNotEqual(first.websiteDataIdentity, try connection(difference).websiteDataIdentity)
        }
    }

    func testHTTPSStoresRemainBoundToCompleteEffectiveOrigin() throws {
        let first = try connection(["mode": .string("https"), "url": .string("https://mia.example/")])
        let equivalent = try connection(["mode": .string("https"), "url": .string("https://MIA.example:443/library")])
        XCTAssertEqual(first.websiteDataIdentity, equivalent.websiteDataIdentity)
        for url in ["https://mia.example:444/", "https://other.example/"] {
            let other = try connection(["mode": .string("https"), "url": .string(url)])
            XCTAssertNotEqual(first.websiteDataIdentity, other.websiteDataIdentity)
        }
    }

    func testLocalStoresKeepPortIsolationAndIdentityComponentsCannotCollide() throws {
        let base: [String: JSONValue] = ["installation_id": .string("local-installation"), "url": .string("http://127.0.0.1:8190/")]
        let local = try MiaConnection(base, local: true)
        let moved = try MiaConnection(base.merging(["url": .string("http://127.0.0.1:8191/")], uniquingKeysWith: { _, new in new }), local: true)
        XCTAssertNotEqual(local.websiteDataIdentity, moved.websiteDataIdentity)
        let first = try connection(["connection_id": .string("a|b"), "installation_id": .string("c")])
        let other = try connection(["connection_id": .string("a"), "installation_id": .string("b|c")])
        XCTAssertNotEqual(first.websiteDataIdentity, other.websiteDataIdentity)
    }
}
