import Foundation

extension MiaConnection {
    /// Storage survives a verified SSH tunnel reconnecting on another local
    /// port. Navigation still uses webIdentity and checks the complete origin.
    public var websiteDataIdentity: String {
        let origin = WebOrigin(url)!
        let values = [mode, id, installationID, origin.scheme, origin.host,
                      mode == "ssh" ? "verified-ssh-tunnel" : String(origin.port),
                      mode == "ssh" ? metadata["host_key_fingerprint"]?.string ?? "" : ""]
        // Length prefixes keep arbitrary installation identifiers unambiguous.
        return values.map { String($0.utf8.count) + ":" + $0 }.joined()
    }
}
