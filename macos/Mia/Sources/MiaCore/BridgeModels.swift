import Foundation

public enum JSONValue: Codable, Equatable, Sendable {
    case string(String), number(Double), bool(Bool), object([String: JSONValue]), array([JSONValue]), null

    public init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let item = try? value.decode(Bool.self) { self = .bool(item) }
        else if let item = try? value.decode(String.self) { self = .string(item) }
        else if let item = try? value.decode(Double.self) { self = .number(item) }
        else if let item = try? value.decode([String: JSONValue].self) { self = .object(item) }
        else { self = .array(try value.decode([JSONValue].self)) }
    }

    public func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case let .string(item): try value.encode(item)
        case let .number(item): try value.encode(item)
        case let .bool(item): try value.encode(item)
        case let .object(item): try value.encode(item)
        case let .array(item): try value.encode(item)
        case .null: try value.encodeNil()
        }
    }

    public var string: String? { if case let .string(item) = self { return item }; return nil }
    public var bool: Bool? { if case let .bool(item) = self { return item }; return nil }
    public var number: Double? { if case let .number(item) = self { return item }; return nil }
    public var object: [String: JSONValue]? { if case let .object(item) = self { return item }; return nil }
    public var array: [JSONValue]? { if case let .array(item) = self { return item }; return nil }
}

public struct BridgeRequest: Encodable, Sendable {
    public let action: String
    public let payload: [String: JSONValue]
    public init(action: String, payload: [String: JSONValue] = [:]) throws {
        guard Self.actions.contains(action) else { throw BridgeFailure.unsupportedAction }
        self.action = action
        self.payload = payload
    }
    public static let actions: Set<String> = [
        "status", "local_plan", "local_install", "local_start", "local_stop", "local_recover", "local_snapshot", "local_bundle_plan", "local_bundle_update",
        "remote_preflight", "remote_install", "remote_connect", "remote_disconnect", "https_connect",
        "remote_bundle_plan", "remote_bundle_update", "remote_snapshot_plan", "remote_snapshot", "remote_recovery_plan", "remote_recover",
        "updates_status", "updates_check", "updates_prepare", "updates_apply", "updates_recover"
    ]
}

public struct BridgeResponse: Decodable, Sendable {
    public let ok: Bool
    public let result: JSONValue?
    public let error: BridgeError?
    public struct BridgeError: Decodable, Sendable { public let code: String; public let message: String }
    public func checkedResult() throws -> [String: JSONValue] {
        guard ok else { throw BridgeFailure.backend(error?.message ?? "A operação não foi concluída. Seus dados foram preservados.") }
        guard let result = result?.object, error == nil else { throw BridgeFailure.invalidResponse }
        return result
    }
}

public enum BridgeFailure: Error, LocalizedError, Equatable {
    case unsupportedAction, missingRuntime, invalidResponse, requestTooLarge, responseTooLarge, timeout, processFailed, backend(String)
    public var errorDescription: String? {
        switch self {
        case .unsupportedAction: return "Esta ação não está disponível nesta versão da Mia."
        case .missingRuntime: return "Este aplicativo está incompleto. Instale um pacote oficial compatível com este Mac."
        case .invalidResponse: return "A Mia não conseguiu confirmar o resultado. Confira o estado antes de tentar novamente."
        case .requestTooLarge: return "A configuração excedeu o limite permitido."
        case .responseTooLarge: return "A resposta excedeu o limite permitido. Confira o estado da instalação."
        case .timeout: return "A operação demorou além do previsto. Confira o estado antes de tentar novamente."
        case .processFailed: return "A Mia não conseguiu concluir a operação. Seus dados foram preservados."
        case let .backend(message): return message
        }
    }
}

public struct MiaConnection: Equatable, Identifiable, Sendable {
    public let id: String
    public let installationID: String
    public let mode: String
    public let url: URL
    public let version: String?
    public let running: Bool
    public let metadata: [String: JSONValue]

    public init(_ values: [String: JSONValue], local: Bool = false) throws {
        guard let installationID = values["installation_id"]?.string, !installationID.isEmpty, installationID.utf8.count <= 256,
              let rawURL = values["url"]?.string, let url = URL(string: rawURL), WebOrigin(url) != nil else {
            throw BridgeFailure.invalidResponse
        }
        self.installationID = installationID
        self.id = local ? "local" : (values["connection_id"]?.string ?? installationID)
        self.mode = local ? "local" : (values["mode"]?.string ?? "https")
        guard ["local", "ssh", "https"].contains(self.mode),
              (self.mode == "https" ? url.scheme == "https" : WebOrigin(url)?.isLoopback == true) else {
            throw BridgeFailure.invalidResponse
        }
        self.url = url
        self.version = values["version"]?.string
        self.running = values["running"]?.bool ?? false
        self.metadata = values
    }
    public var title: String { mode == "local" ? "Neste Mac" : (metadata["host"]?.string ?? url.host ?? "Minha Mia") }
    public var webIdentity: String {
        let origin = WebOrigin(url)!
        return id + "|" + installationID + "|" + origin.scheme + "|" + origin.host + "|" + String(origin.port)
    }
    public var storageDescription: String {
        mode == "local" ? "Seus arquivos ficam neste Mac. Disponível enquanto ele estiver ligado e acordado." : "Seus arquivos ficam nesta instalação no servidor. O app não copia a biblioteca para este Mac."
    }
}

public struct ReviewPlan: Identifiable, Sendable {
    public let id: String
    public let summary: [String]
    public let technicalDetails: String
    public init(_ values: [String: JSONValue], hashKey: String = "sha256") throws {
        guard let hash = values[hashKey]?.string, hash.count == 64, hash.allSatisfy({ $0.isHexDigit && !$0.isUppercase }) else { throw BridgeFailure.invalidResponse }
        let summary = values["summary"]?.array?.compactMap(\.string) ?? values["summary"]?.string.map { [$0] } ?? []
        guard !summary.isEmpty, summary.count <= 32, summary.allSatisfy({ !$0.isEmpty && $0.utf8.count <= 8_192 }) else { throw BridgeFailure.invalidResponse }
        self.id = hash
        self.summary = summary
        let data = try JSONEncoder().encode(values["details"] ?? .null)
        self.technicalDetails = String(data: data, encoding: .utf8) ?? ""
    }
}

public enum ClientPhase: Equatable, Sendable { case welcome, choosing, preparing, ready, offline, recoveryRequired }

public struct ClientState: Equatable, Sendable {
    public var phase: ClientPhase = .welcome
    public var connection: MiaConnection?
    public private(set) var uncertainMutation = false
    public init() {}
    public mutating func show(_ connection: MiaConnection) {
        self.connection = connection
        self.phase = connection.running ? .ready : .offline
        self.uncertainMutation = false
    }
    public mutating func disconnected() { phase = connection == nil ? .choosing : .offline }
    public mutating func mutationFailed() { uncertainMutation = true; phase = .recoveryRequired }
    public mutating func requireRecovery() { phase = .recoveryRequired }
    public mutating func chooseDestination() { connection = nil; phase = .choosing; uncertainMutation = false }
}
