import Foundation

/// An origin selected by trusted native configuration. Web content cannot change it.
public struct WebOrigin: Hashable, Sendable {
    public let scheme: String
    public let host: String
    public let port: Int
    public let isLoopback: Bool
    public init?(_ url: URL) {
        guard let scheme = url.scheme?.lowercased(), let host = url.host?.lowercased(),
              url.user == nil, url.password == nil, ["http", "https"].contains(scheme),
              !host.isEmpty else { return nil }
        let loopback = host == "127.0.0.1" || host == "[::1]" || host == "::1"
        guard scheme == "https" || loopback else { return nil }
        let port = url.port ?? (scheme == "https" ? 443 : 80)
        guard (1...65535).contains(port) else { return nil }
        self.scheme = scheme; self.host = host; self.port = port; self.isLoopback = loopback
    }
    public func allows(_ url: URL) -> Bool { WebOrigin(url) == self }
    public static func externalLinkAllowed(_ url: URL) -> Bool {
        guard url.user == nil, url.password == nil, let scheme = url.scheme?.lowercased(), let host = url.host, !host.isEmpty else { return false }
        return ["https", "http"].contains(scheme)
    }
}
