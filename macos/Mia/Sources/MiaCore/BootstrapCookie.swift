import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// The first-owner nonce is delivered by the private native/SSH controller, never
/// in a URL, JavaScript source, shared cookie store, preference, or public API.
public enum BootstrapCookie {
    public static func make(for connection: MiaConnection) throws -> HTTPCookie? {
        guard let value = connection.metadata["bootstrap_token"], value != .null else { return nil }
        guard let token = value.string, (32...256).contains(token.utf8.count),
              token.utf8.allSatisfy({ (65...90).contains($0) || (97...122).contains($0) || (48...57).contains($0) || $0 == 45 || $0 == 95 }),
              let origin = WebOrigin(connection.url) else { throw BridgeFailure.invalidResponse }
        var properties: [HTTPCookiePropertyKey: Any] = [
            .name: "mia_bootstrap", .value: token, .domain: origin.host,
            .originURL: connection.url, .path: "/", .discard: "TRUE",
            HTTPCookiePropertyKey(rawValue: "HttpOnly"): "TRUE"
        ]
        if origin.scheme == "https" { properties[.secure] = "TRUE" }
        #if os(macOS)
        properties[.sameSitePolicy] = "strict"
        #else
        properties[HTTPCookiePropertyKey(rawValue: "SameSitePolicy")] = "strict"
        #endif
        guard let cookie = HTTPCookie(properties: properties), cookie.isHTTPOnly, cookie.path == "/", cookie.isSecure == (origin.scheme == "https") else { throw BridgeFailure.invalidResponse }
        return cookie
    }
}
