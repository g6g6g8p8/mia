#if os(macOS)
import CryptoKit
import Foundation
import Security
import SwiftUI
import MiaCore

enum BetaAccessFailure: Error, LocalizedError, Equatable {
    case unconfigured, invalidTicket, unavailable, invalidResponse, storageUnavailable, activationRequired, unsafeURL
    var errorDescription: String? {
        switch self {
        case .unconfigured: return "Este pacote ainda não tem um serviço de convites configurado. Sua biblioteca continua disponível."
        case .invalidTicket: return "O código de ativação é inválido, expirou ou foi revogado. Use o código do seu convite."
        case .unavailable: return "Não foi possível confirmar a ativação. Tente novamente com o mesmo código; sua biblioteca permanece disponível."
        case .invalidResponse: return "O serviço não confirmou uma autorização válida. Nenhuma configuração da sua biblioteca foi alterada."
        case .storageUnavailable: return "Não foi possível guardar a autorização no Chaves deste Mac. Nenhum segredo foi salvo em preferências ou arquivos da biblioteca."
        case .activationRequired: return "Ative seu convite para receber atualizações oficiais da demonstração. Sua biblioteca funciona sem essa ativação."
        case .unsafeURL: return "A atualização apontou para um endereço fora do serviço configurado neste aplicativo e foi bloqueada."
        }
    }
}

/// Only a bundled, signed channel supplies the service address. Activation
/// links supply one ticket and cannot change an origin, feed, key or endpoint.
struct BetaDistributionPolicy: Equatable {
    let baseURL: URL
    let feedURL: URL
    let architecture: String
    let identity: String

    init(distributionURL: String, feedURL: String, architecture: String) throws {
        guard ["arm64", "x86_64"].contains(architecture),
              let base = Self.cleanHTTPS(distributionURL), let feed = Self.cleanHTTPS(feedURL),
              base.path == "/" || !base.path.hasSuffix("/") else { throw BetaAccessFailure.unconfigured }
        let prefix = base.path == "/" ? "" : base.path
        guard feed.absoluteString == base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/updates/" + architecture + "/appcast.xml",
              feed.path == prefix + "/updates/" + architecture + "/appcast.xml" else { throw BetaAccessFailure.unconfigured }
        self.baseURL = base; self.feedURL = feed; self.architecture = architecture
        identity = Self.hash(base.absoluteString + "|" + architecture)
    }

    private static func cleanHTTPS(_ raw: String) -> URL? {
        guard raw.utf8.count <= 2_048, let components = URLComponents(string: raw),
              components.scheme == "https", let host = components.host, !host.isEmpty,
              components.user == nil, components.password == nil, components.query == nil, components.fragment == nil,
              components.port == nil || components.port == 443,
              !components.percentEncodedPath.contains("%"), !components.path.contains("\\"),
              !components.path.contains("//"), !components.path.split(separator: "/").contains(where: { $0 == "." || $0 == ".." }),
              let url = components.url, WebOrigin(url) != nil else { return nil }
        return url
    }

    var activationURL: URL { baseURL.appendingPathComponent("beta/activate") }
    func allowsFeed(_ url: URL) -> Bool { url == feedURL }
    func allowsDownload(_ url: URL) -> Bool {
        guard Self.cleanHTTPS(url.absoluteString) != nil, WebOrigin(url) == WebOrigin(baseURL) else { return false }
        let prefix = baseURL.path == "/" ? "" : baseURL.path
        guard url.path.hasPrefix(prefix + "/app-updates/") else { return false }
        let parts = url.path.dropFirst((prefix + "/app-updates/").count).split(separator: "/", omittingEmptySubsequences: false)
        guard parts.count == 2, parts[1] == Substring(architecture), (1...100).contains(parts[0].utf8.count) else { return false }
        return parts[0].allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || "._-".contains($0)) }
    }
    static func hash(_ value: String) -> String { SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined() }
    static func validSecret(_ value: String) -> Bool {
        value.utf8.count == 43 && value.allSatisfy { $0.isASCII && ($0.isLetter || $0.isNumber || $0 == "_" || $0 == "-") }
    }
    static func activationTicket(from url: URL) throws -> String {
        guard url.absoluteString.utf8.count <= 256, let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              components.scheme == "mia-demo", components.host == "activate", components.path.isEmpty,
              components.user == nil, components.password == nil, components.port == nil, components.fragment == nil,
              let items = components.queryItems, items.count == 1, items[0].name == "ticket",
              let ticket = items[0].value, validSecret(ticket) else { throw BetaAccessFailure.invalidTicket }
        return ticket
    }
}

@MainActor protocol BetaSecretStoring {
    func read(_ account: String) throws -> Data?
    func write(_ data: Data, account: String) throws
    func delete(_ account: String) throws
}

@MainActor final class KeychainBetaSecrets: BetaSecretStoring {
    private let service = "org.mia.demo.beta-access"
    private func query(_ account: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
         kSecAttrAccount as String: account, kSecAttrSynchronizable as String: false]
    }
    func read(_ account: String) throws -> Data? {
        var request = query(account)
        request[kSecReturnData as String] = true; request[kSecMatchLimit as String] = kSecMatchLimitOne
        request[kSecUseAuthenticationUI as String] = kSecUseAuthenticationUIFail
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data, data.count <= 16_384 else { throw BetaAccessFailure.storageUnavailable }
        return data
    }
    func write(_ data: Data, account: String) throws {
        guard data.count <= 16_384 else { throw BetaAccessFailure.storageUnavailable }
        let existing = query(account)
        let status = SecItemUpdate(existing as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var create = existing; create[kSecValueData as String] = data
            create[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            guard SecItemAdd(create as CFDictionary, nil) == errSecSuccess else { throw BetaAccessFailure.storageUnavailable }
        } else if status != errSecSuccess { throw BetaAccessFailure.storageUnavailable }
    }
    func delete(_ account: String) throws {
        let status = SecItemDelete(query(account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw BetaAccessFailure.storageUnavailable }
    }
}

struct BetaHTTPResponse: Sendable {
    let status: Int
    let url: URL
    let contentType: String
    let body: Data
}
protocol BetaHTTPCalling: Sendable {
    func activate(url: URL, body: Data) async throws -> BetaHTTPResponse
}

/// One ephemeral, bounded request. It accepts normal system TLS validation and
/// refuses every redirect before another request can carry activation data.
struct BetaHTTPClient: BetaHTTPCalling {
    func activate(url: URL, body: Data) async throws -> BetaHTTPResponse {
        var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 20)
        request.httpMethod = "POST"; request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        return try await withCheckedThrowingContinuation { continuation in
            let receiver = BetaHTTPReceiver(continuation)
            let config = URLSessionConfiguration.ephemeral
            config.urlCache = nil; config.httpCookieStorage = nil; config.httpShouldSetCookies = false
            config.timeoutIntervalForRequest = 20; config.timeoutIntervalForResource = 30
            let session = URLSession(configuration: config, delegate: receiver, delegateQueue: nil)
            receiver.session = session
            session.dataTask(with: request).resume()
        }
    }
}

private final class BetaHTTPReceiver: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private var continuation: CheckedContinuation<BetaHTTPResponse, Error>?
    private var response: HTTPURLResponse?
    private var bytes = Data()
    var session: URLSession?
    init(_ continuation: CheckedContinuation<BetaHTTPResponse, Error>) { self.continuation = continuation }
    private func finish(_ result: Result<BetaHTTPResponse, Error>) {
        guard let continuation else { return }
        self.continuation = nil
        session?.invalidateAndCancel(); session = nil
        continuation.resume(with: result)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil); finish(.failure(BetaAccessFailure.unsafeURL))
    }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse, completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        guard let http = response as? HTTPURLResponse, response.expectedContentLength <= 16_384 else {
            completionHandler(.cancel); finish(.failure(BetaAccessFailure.invalidResponse)); return
        }
        self.response = http; completionHandler(.allow)
    }
    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard data.count <= 16_384 - bytes.count else { finish(.failure(BetaAccessFailure.invalidResponse)); return }
        bytes.append(data)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard error == nil, let response, let url = response.url else { finish(.failure(BetaAccessFailure.unavailable)); return }
        finish(.success(BetaHTTPResponse(status: response.statusCode, url: url,
                                         contentType: response.value(forHTTPHeaderField: "Content-Type") ?? "", body: bytes)))
    }
}

private struct BetaLease: Codable {
    let token: String
    let expiresAt: Int
}

@MainActor final class BetaAccess: ObservableObject {
    @Published private(set) var busy = false
    @Published private(set) var message = "Ative seu convite para receber atualizações oficiais. Sua biblioteca funciona sem essa ativação."
    @Published var activationTicket = ""
    @Published var showActivation = false
    let policy: BetaDistributionPolicy?
    private let store: any BetaSecretStoring
    private let http: any BetaHTTPCalling
    private let clock: () -> Date
    private let randomSecret: () throws -> String
    private var lease: BetaLease?

    init(policy: BetaDistributionPolicy?, store: (any BetaSecretStoring)? = nil, http: any BetaHTTPCalling = BetaHTTPClient(), clock: @escaping () -> Date = Date.init, randomSecret: (() throws -> String)? = nil) {
        let selectedStore = store ?? KeychainBetaSecrets()
        self.policy = policy; self.store = selectedStore; self.http = http; self.clock = clock; self.randomSecret = randomSecret ?? { try Self.makeSecret() }
        guard let policy else { message = BetaAccessFailure.unconfigured.localizedDescription; return }
        do {
            if let data = try selectedStore.read(policy.identity + ".lease") {
                let stored = try JSONDecoder().decode(BetaLease.self, from: data)
                guard BetaDistributionPolicy.validSecret(stored.token), stored.expiresAt > 0 else { throw BetaAccessFailure.storageUnavailable }
                lease = stored
                message = stored.expiresAt > Int(clock().timeIntervalSince1970) ? "Convite ativado neste Mac. A autorização serve somente às atualizações oficiais." : BetaAccessFailure.activationRequired.localizedDescription
            }
        } catch { message = BetaAccessFailure.storageUnavailable.localizedDescription }
    }
    var configured: Bool { policy != nil }
    var canUpdate: Bool { lease.map { $0.expiresAt > Int(clock().timeIntervalSince1970) } ?? false }
    var expiresAt: Date? { lease.map { Date(timeIntervalSince1970: Double($0.expiresAt)) } }
    func authorization(for url: URL, download: Bool = false) throws -> String {
        guard let policy else { throw BetaAccessFailure.unconfigured }
        guard (download ? policy.allowsDownload(url) : policy.allowsFeed(url)) else { throw BetaAccessFailure.unsafeURL }
        guard let lease, lease.expiresAt > Int(clock().timeIntervalSince1970) else { throw BetaAccessFailure.activationRequired }
        return "Bearer " + lease.token
    }
    func accept(_ url: URL) async {
        do { activationTicket = try BetaDistributionPolicy.activationTicket(from: url); showActivation = true; await activate() }
        catch { message = BetaAccessFailure.invalidTicket.localizedDescription; showActivation = true }
    }
    func activate() async {
        guard !busy else { return }
        guard let policy else { message = BetaAccessFailure.unconfigured.localizedDescription; return }
        let ticket = activationTicket.trimmingCharacters(in: .whitespacesAndNewlines)
        guard BetaDistributionPolicy.validSecret(ticket) else { message = BetaAccessFailure.invalidTicket.localizedDescription; return }
        busy = true; defer { busy = false }
        do {
            let account = policy.identity + ".pending." + BetaDistributionPolicy.hash(ticket)
            let nonce: String
            if let pending = try store.read(account) {
                guard let value = String(data: pending, encoding: .utf8), BetaDistributionPolicy.validSecret(value) else { throw BetaAccessFailure.storageUnavailable }
                nonce = value
            } else {
                nonce = try randomSecret()
                guard BetaDistributionPolicy.validSecret(nonce) else { throw BetaAccessFailure.storageUnavailable }
                // Persist before the first request. A lost final response can be
                // repeated with exactly this nonce and does not consume a new use.
                try store.write(Data(nonce.utf8), account: account)
            }
            let body = try JSONSerialization.data(withJSONObject: ["ticket": ticket, "client_nonce": nonce, "architecture": policy.architecture])
            let response = try await http.activate(url: policy.activationURL, body: body)
            if response.status == 401 || response.status == 403 { throw BetaAccessFailure.invalidTicket }
            guard response.status == 200, response.url == policy.activationURL, response.body.count <= 16_384,
                  response.contentType.split(separator: ";").first?.trimmingCharacters(in: .whitespaces).lowercased() == "application/json",
                  let value = try JSONSerialization.jsonObject(with: response.body) as? [String: Any], Set(value.keys) == ["access_token", "expires_at"],
                  let token = value["access_token"] as? String, BetaDistributionPolicy.validSecret(token),
                  let expiry = value["expires_at"] as? NSNumber, CFGetTypeID(expiry) != CFBooleanGetTypeID(),
                  expiry.doubleValue == floor(expiry.doubleValue), expiry.doubleValue <= Double(Int.max),
                  expiry.intValue > Int(clock().timeIntervalSince1970), expiry.intValue <= Int(clock().timeIntervalSince1970) + 90 * 86_400 else { throw BetaAccessFailure.invalidResponse }
            let confirmed = BetaLease(token: token, expiresAt: expiry.intValue)
            try store.write(JSONEncoder().encode(confirmed), account: policy.identity + ".lease")
            lease = confirmed
            // Keep the nonce in Keychain for later retries of this same link.
            // Deleting it would turn reopening a consumed ticket into a new use.
            activationTicket = ""
            message = "Convite ativado neste Mac. Agora você pode buscar atualizações oficiais. Seu acesso e sua biblioteca continuam no destino escolhido."
        } catch {
            message = (error as? BetaAccessFailure)?.localizedDescription ?? BetaAccessFailure.unavailable.localizedDescription
        }
    }
    func forget() {
        guard let policy else { return }
        do { try store.delete(policy.identity + ".lease"); lease = nil; message = BetaAccessFailure.activationRequired.localizedDescription }
        catch { message = BetaAccessFailure.storageUnavailable.localizedDescription }
    }
    nonisolated private static func makeSecret() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw BetaAccessFailure.storageUnavailable }
        return Data(bytes).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}
#endif
