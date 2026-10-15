#if os(macOS)
import Foundation
import SwiftUI
import MiaCore

enum DestinationChoice: String, CaseIterable, Identifiable {
    case local = "Neste Mac", server = "No meu servidor", existing = "Conectar à minha Mia"
    var id: String { rawValue }
}

/// A review belongs to one selected installation and one trusted transport.
/// Backend hashes also bind the private pinned host and the operation's content.
private struct OperationScope: Equatable {
    let connectionID: String
    let installationID: String
    let mode: String
    let origin: WebOrigin
    let version: String?
    let paused: Bool?
    let hostIdentity: [String: JSONValue]

    init(_ connection: MiaConnection) {
        connectionID = connection.id; installationID = connection.installationID
        mode = connection.mode; origin = WebOrigin(connection.url)!
        version = connection.version; paused = connection.metadata["paused"]?.bool
        hostIdentity = connection.metadata.filter { ["host", "user", "port", "remote_port", "host_key_fingerprint"].contains($0.key) }
    }
}

enum RemoteOperation: String {
    case bundledUpdate, snapshot, recovery
    var planAction: String {
        switch self { case .bundledUpdate: return "remote_bundle_plan"; case .snapshot: return "remote_snapshot_plan"; case .recovery: return "remote_recovery_plan" }
    }
    var action: String {
        switch self { case .bundledUpdate: return "remote_bundle_update"; case .snapshot: return "remote_snapshot"; case .recovery: return "remote_recover" }
    }
    var title: String {
        switch self { case .bundledUpdate: return "Confira a atualização do servidor"; case .snapshot: return "Confira a cópia de recuperação"; case .recovery: return "Confira a recuperação do servidor" }
    }
    var actionTitle: String {
        switch self { case .bundledUpdate: return "Atualizar com recuperação"; case .snapshot: return "Criar e verificar cópia"; case .recovery: return "Confirmar recuperação" }
    }
    var progress: String {
        switch self { case .bundledUpdate: return "Atualizando e verificando sua instalação no servidor…"; case .snapshot: return "Criando e verificando a cópia no servidor…"; case .recovery: return "Recuperando e verificando sua instalação no servidor…" }
    }
}

@MainActor final class MiaModel: ObservableObject {
    @Published var state = ClientState()
    @Published var connections: [MiaConnection] = []
    @Published var choice: DestinationChoice = .local
    @Published var busy = false
    @Published var progress = ""
    @Published var errorMessage: String?
    @Published var notice: String?
    @Published var plan: ReviewPlan?
    @Published var hostFingerprint: String?
    @Published var serverHost = ""
    @Published var serverUser = ""
    @Published var serverPort = "22"
    @Published var serverKey: URL?
    @Published var serverConnectOnly = false
    @Published var existingURL = ""
    @Published var updates: [String: JSONValue] = [:]
    @Published var updatePlan: ReviewPlan?
    @Published var showControls = false
    @Published var webReloadID = UUID()
    @Published var backendRefreshPlan = false
    @Published var remoteOperation: RemoteOperation?
    @Published var remotePlan: ReviewPlan?
    private var updatePlanScope: OperationScope?
    private var remotePlanScope: OperationScope?
    private var remotePlanValues: [String: JSONValue] = [:]
    private var approvedFingerprint: String?
    private var approvedHostConfiguration: [String: JSONValue]?
    private var pendingRemotePayload: [String: JSONValue]?
    private let bridge: any BridgeCalling
    private let preferences: UserDefaults
    private var pollTask: Task<Void, Never>?
    static let appVersion = Bundle.main.object(forInfoDictionaryKey: "MiaBackendVersion") as? String ?? "0.2.0a14"

    init(bridge: any BridgeCalling, preferences: UserDefaults = .standard) { self.bridge = bridge; self.preferences = preferences }

    func start() async {
        await refresh(initial: true)
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 30_000_000_000)
                guard !Task.isCancelled, let self else { return }
                if !self.busy { await self.refresh() }
            }
        }
    }

    func refresh(initial: Bool = false) async {
        guard !busy else { return }
        do {
            let result = try await bridge.call(BridgeRequest(action: "status"))
            guard result["protocol"]?.number == 1 else { throw BridgeFailure.invalidResponse }
            var found: [MiaConnection] = []
            var localRecoveryRequired = false
            if let local = result["local"]?.object {
                if local["installed"]?.bool == true, let connection = try? MiaConnection(local, local: true) { found.append(connection) }
                if local["recovery_required"]?.bool == true && (initial || state.connection?.mode == "local") {
                    localRecoveryRequired = true
                    state.requireRecovery(); notice = "Uma operação anterior precisa de recuperação. A Mia preservou sua instalação; não crie uma nova por cima dela."
                }
            }
            for item in result["connections"]?.array ?? [] {
                if let object = item.object, let connection = try? MiaConnection(object) { found.append(connection) }
            }
            connections = found
            if initial && !state.uncertainMutation {
                let remembered = preferences.string(forKey: "Mia.selectedConnection")
                if let selected = found.first(where: { $0.id == remembered }), !localRecoveryRequired {
                    state.show(selected)
                    if selected.metadata["recovery_required"]?.bool == true { state.requireRecovery() }
                    else if !selected.running && selected.metadata["paused"]?.bool != true { await reconnect() }
                }
            } else if let selected = state.connection, let current = found.first(where: { $0.id == selected.id && $0.installationID == selected.installationID }) {
                if OperationScope(current) != OperationScope(selected) { clearUpdateReview() }
                if current.metadata["recovery_required"]?.bool == true { state.requireRecovery() }
                else if !current.running && !state.uncertainMutation && state.phase != .recoveryRequired { state.disconnected() }
                // A recovered process may have a new port. Explicit reconnect also
                // reloads the window; a poll does not discard an in-progress form.
            }
        } catch {
            if initial { errorMessage = safeMessage(error) }
            if state.connection != nil && !state.uncertainMutation && state.phase != .recoveryRequired { state.disconnected() }
        }
    }

    func begin() { state.chooseDestination() }
    func changeDestination() { plan = nil; hostFingerprint = nil; approvedFingerprint = nil; approvedHostConfiguration = nil; clearUpdateReview(); state.chooseDestination(); showControls = false }

    func prepareLocal() async {
        await perform("Conferindo este Mac…") {
            self.plan = try ReviewPlan(await self.call("local_plan"))
        }
    }

    func installReviewedPlan() async {
        guard let plan else { return }
        let action = choice == .server ? "remote_install" : "local_install"
        var payload = choice == .server ? (pendingRemotePayload ?? [:]) : [:]
        payload["approve_sha256"] = .string(plan.id)
        if choice == .server { guard let approvedFingerprint else { return }; payload["approved_host_fingerprint"] = .string(approvedFingerprint) }
        await perform("Preparando sua instalação privada…", mutation: true) {
            let result = try await self.call(action, payload)
            self.select(try MiaConnection(result["local"]?.object ?? result["connection"]?.object ?? result, local: action == "local_install"))
            self.plan = nil
        }
    }

    func inspectServer() async {
        await perform("Conferindo a identidade do servidor…") {
            guard let port = Int(self.serverPort), (1...65535).contains(port), !self.serverHost.trimmingCharacters(in: .whitespaces).isEmpty, !self.serverUser.trimmingCharacters(in: .whitespaces).isEmpty else {
                throw BridgeFailure.backend("Informe endereço, usuário e uma porta SSH válida.")
            }
            var payload: [String: JSONValue] = ["host": .string(self.serverHost.trimmingCharacters(in: .whitespaces)), "user": .string(self.serverUser.trimmingCharacters(in: .whitespaces)), "port": .number(Double(port)), "remote_port": .number(8123)]
            if let key = self.serverKey { payload["key_path"] = .string(key.path) }
            let configuration = payload
            if self.approvedHostConfiguration != configuration { self.approvedFingerprint = nil; self.hostFingerprint = nil }
            if let approved = self.approvedFingerprint { payload["approved_host_fingerprint"] = .string(approved) }
            self.pendingRemotePayload = payload
            let result = try await self.call("remote_preflight", payload)
            guard let fingerprint = result["host_key_fingerprint"]?.string, !fingerprint.isEmpty else { throw BridgeFailure.invalidResponse }
            if result["host_key_known"]?.bool != true && self.approvedFingerprint != fingerprint {
                self.hostFingerprint = fingerprint; return
            }
            self.approvedFingerprint = fingerprint
            self.approvedHostConfiguration = configuration
            self.hostFingerprint = nil
            if self.serverConnectOnly {
                payload["approved_host_fingerprint"] = .string(fingerprint)
                let connected = try await self.call("remote_connect", payload)
                self.select(try MiaConnection(connected["connection"]?.object ?? connected))
                return
            }
            if result["supported"]?.bool != true || result["install_ready"]?.bool != true {
                let reasons = result["summary"]?.array?.compactMap(\.string).joined(separator: "\n") ?? result["summary"]?.string
                throw BridgeFailure.backend(reasons ?? "Esta plataforma de servidor ainda não é oferecida pela demonstração.")
            }
            self.plan = try ReviewPlan(result["plan"]?.object ?? result, hashKey: result["plan"] == nil ? "plan_sha256" : "sha256")
        }
    }

    func approveHostIdentity() async {
        guard let fingerprint = hostFingerprint else { return }
        approvedHostConfiguration = pendingRemotePayload?.filter { $0.key != "approved_host_fingerprint" }
        approvedFingerprint = fingerprint; hostFingerprint = nil
        await inspectServer()
    }

    func connectExisting() async {
        await perform("Conectando à sua Mia…") {
            guard let url = URL(string: self.existingURL.trimmingCharacters(in: .whitespaces)), url.scheme == "https", WebOrigin(url) != nil else { throw BridgeFailure.backend("Informe o endereço HTTPS da sua instalação, sem usuário ou senha no endereço.") }
            let result = try await self.call("https_connect", ["url": .string(url.absoluteString)])
            self.select(try MiaConnection(result["connection"]?.object ?? result))
        }
    }

    func connectSaved(_ connection: MiaConnection) async {
        clearUpdateReview()
        state.show(connection)
        if connection.metadata["recovery_required"]?.bool == true { state.requireRecovery(); showControls = true; return }
        if connection.metadata["paused"]?.bool == true { showControls = true; return }
        await reconnect()
    }

    func reconnect() async {
        guard let connection = state.connection else { return }
        guard !state.uncertainMutation && state.phase != .recoveryRequired else {
            showControls = true
            notice = "Confira a recuperação desta instalação antes de retomar. Uma conexão ativa não confirma o resultado da operação anterior."
            return
        }
        await perform("Reconectando à sua instalação…") {
            let result: [String: JSONValue]
            if connection.mode == "local" { result = try await self.call("local_start") }
            else if connection.mode == "https" { result = try await self.call("https_connect", ["url": .string(connection.url.absoluteString)]) }
            else {
                // Retrieve the previously pinned host and key from private state.
                result = try await self.call("remote_connect", ["connection_id": .string(connection.id)])
            }
            let restored = try MiaConnection(result["local"]?.object ?? result["connection"]?.object ?? result, local: connection.mode == "local")
            try self.verifyRestored(restored, expected: connection)
            self.select(restored)
            if restored.metadata["recovery_required"]?.bool == true { self.state.requireRecovery() }
            self.webReloadID = UUID()
        }
    }

    func stopLocal() async {
        guard state.connection?.mode == "local" else { return }
        await perform("Parando a Mia neste Mac…", mutation: true) {
            _ = try await self.call("local_stop")
            self.state.disconnected(); self.notice = "Mia parada neste Mac. Seus dados permanecem guardados. Escolha Retomar para iniciá-la."
        }
    }

    func recoverLocal() async {
        await perform("Conferindo e recuperando a instalação…", mutation: true) {
            let result = try await self.call("local_recover")
            if let connection = try? MiaConnection(result["local"]?.object ?? result, local: true) { self.select(connection) }
            else { self.state.chooseDestination(); self.notice = "Recuperação concluída. Selecione sua instalação para retomar." }
        }
    }

    func snapshot() async {
        guard state.connection?.mode == "local" else { return }
        await perform("Criando e verificando uma cópia de recuperação…", mutation: true) {
            let result = try await self.call("local_snapshot")
            guard result["verified"]?.bool == true else { throw BridgeFailure.invalidResponse }
            self.notice = result["summary"]?.array?.compactMap(\.string).joined(separator: "\n") ?? "Cópia de recuperação criada e verificada."
        }
    }

    func inspectRemoteOperation(_ operation: RemoteOperation) async {
        guard !busy, let connection = state.connection, connection.mode == "ssh" else { return }
        if state.phase == .recoveryRequired && operation != .recovery {
            notice = "Confira a recuperação do servidor antes de iniciar outra operação."
            return
        }
        clearRemoteReview()
        await perform("Conferindo sua instalação no servidor…") {
            let result = try await self.call(operation.planAction, ["connection_id": .string(connection.id)])
            guard self.state.connection.map(OperationScope.init) == OperationScope(connection),
                  result["connection_id"]?.string == connection.id,
                  result["installation_id"]?.string == connection.installationID,
                  let fingerprint = result["host_key_fingerprint"]?.string, !fingerprint.isEmpty else { throw BridgeFailure.invalidResponse }
            if let pinned = connection.metadata["host_key_fingerprint"]?.string, pinned != fingerprint {
                throw BridgeFailure.backend("A identidade do servidor mudou. A operação foi interrompida; confira esta conexão antes de continuar.")
            }
            if operation == .bundledUpdate && result["update_available"]?.bool == false {
                self.notice = "O servidor já usa a versão incluída no app. Sua biblioteca permanece no destino."
                return
            }
            self.remotePlan = try ReviewPlan(result)
            self.remoteOperation = operation
            self.remotePlanScope = OperationScope(connection)
            self.remotePlanValues = result
        }
    }

    func applyRemoteOperation() async {
        guard let connection = state.connection, connection.mode == "ssh",
              let operation = remoteOperation, let plan = remotePlan,
              OperationScope(connection) == remotePlanScope,
              operation == .recovery || state.phase != .recoveryRequired else { return }
        let values = remotePlanValues
        await perform(operation.progress, mutation: true) {
            let result = try await self.call(operation.action, ["connection_id": .string(connection.id), "approve_sha256": .string(plan.id)])
            guard self.state.connection.map(OperationScope.init) == OperationScope(connection),
                  result["connection_id"]?.string == connection.id,
                  result["installation_id"]?.string == connection.installationID,
                  result["host_key_fingerprint"]?.string == values["host_key_fingerprint"]?.string else { throw BridgeFailure.invalidResponse }
            if operation == .snapshot {
                guard result["verified"]?.bool == true, let snapshotID = result["snapshot_id"]?.string, !snapshotID.isEmpty else { throw BridgeFailure.invalidResponse }
                self.clearRemoteReview()
                self.notice = "Cópia de recuperação criada e verificada no servidor. Ela fica no mesmo destino; exporte sua biblioteca para manter outra cópia fora dele."
                return
            }
            let restored = try MiaConnection(result["connection"]?.object ?? result)
            try self.verifyRestored(restored, expected: connection, fingerprint: values["host_key_fingerprint"]?.string)
            guard restored.metadata["recovery_required"]?.bool == false,
                  let version = restored.version, !version.isEmpty else { throw BridgeFailure.invalidResponse }
            if operation == .bundledUpdate {
                guard result["updated"]?.bool == true, version == values["candidate_version"]?.string else { throw BridgeFailure.invalidResponse }
            } else { guard result["recovery_confirmed"]?.bool == true else { throw BridgeFailure.invalidResponse } }
            let paused = restored.metadata["paused"]?.bool == true
            guard !paused || !restored.running else { throw BridgeFailure.invalidResponse }
            if operation == .bundledUpdate { guard paused || restored.running else { throw BridgeFailure.invalidResponse } }
            // The bridge reconnects and checks the backend only when it was active.
            // Selecting a paused result never issues remote_connect or starts it.
            self.select(restored)
            self.showControls = true
            self.webReloadID = UUID()
            self.notice = operation == .bundledUpdate ? "Servidor atualizado e verificado. Sua biblioteca foi preservada." : "Estado da instalação confirmado. Sua biblioteca permanece no servidor."
            if paused { self.notice = (self.notice ?? "") + " A instalação continua pausada." }
            else if !restored.running { self.notice = (self.notice ?? "") + " O backend está parado; esta confirmação não o iniciou." }
        }
    }

    func cancelRemoteReview() { clearRemoteReview() }

    func inspectBundledUpdate() async {
        guard let connection = state.connection, connection.mode == "local" else { return }
        await perform("Conferindo a versão incluída neste app…") {
            let result = try await self.call("local_bundle_plan")
            if result["update_available"]?.bool == false {
                self.notice = "Esta instalação já usa a versão incluída no app. Sua biblioteca permanece disponível."
                self.updatePlan = nil; return
            }
            self.updatePlan = try ReviewPlan(result)
            self.backendRefreshPlan = true
            self.updatePlanScope = OperationScope(connection)
        }
    }

    func applyBundledUpdate() async {
        guard let plan = updatePlan, let connection = state.connection, connection.mode == "local", OperationScope(connection) == updatePlanScope else { return }
        await perform("Atualizando a instalação deste Mac com recuperação…", mutation: true) {
            let result = try await self.call("local_bundle_update", ["approve_sha256": .string(plan.id)])
            let restored = try MiaConnection(result["local"]?.object ?? result, local: true)
            try self.verifyRestored(restored, expected: connection)
            self.select(restored)
            self.updatePlan = nil; self.backendRefreshPlan = false; self.webReloadID = UUID()
            self.notice = "Instalação atualizada e verificada. Sua biblioteca foi preservada."
        }
        await refresh()
    }

    func loadUpdates(check: Bool = false) async {
        guard state.connection?.mode == "local" else { updates = [:]; return }
        await perform(check ? "Buscando atualização do destino…" : "Conferindo atualizações…") {
            self.updates = try await self.call(check ? "updates_check" : "updates_status")
        }
    }
    func prepareUpdate() async {
        guard let connection = state.connection, connection.mode == "local" else { return }
        guard let id = (updates["release"]?.object ?? updates["releases"]?.array?.first?.object)?["id"]?.string else { return }
        await perform("Baixando e verificando a atualização…", mutation: true) {
            self.updates = try await self.call("updates_prepare", ["release_id": .string(id)])
            self.updatePlan = try ReviewPlan(self.updates, hashKey: "plan_sha256")
            self.backendRefreshPlan = false
            self.updatePlanScope = OperationScope(connection)
        }
    }
    func discardUpdatePreparation() async {
        guard state.connection?.mode == "local" else { return }
        let id = updates["release"]?.object?["id"]?.string ?? ""
        await perform("Descartando somente a preparação da atualização…", mutation: true) {
            self.updates = try await self.call("updates_prepare", ["release_id": .string(id), "discard": .bool(true)])
            self.updatePlan = nil
        }
    }
    func applyUpdate() async {
        guard let plan = updatePlan, let connection = state.connection, connection.mode == "local", OperationScope(connection) == updatePlanScope else { return }
        await perform("Aplicando atualização com recuperação…", mutation: true) {
            self.updates = try await self.call("updates_apply", ["approve_sha256": .string(plan.id)])
            self.updatePlan = nil
            self.notice = self.updates["summary"]?.string
            self.webReloadID = UUID()
        }
        await refresh()
    }
    func recoverUpdate() async {
        guard state.connection?.mode == "local" else { return }
        await perform("Recuperando a atualização…", mutation: true) {
            self.updates = try await self.call("updates_recover")
            self.updatePlan = nil; self.notice = self.updates["summary"]?.string
            self.webReloadID = UUID()
        }
        await refresh()
    }

    func pageDisconnected() { if !busy && !state.uncertainMutation && state.phase != .recoveryRequired { state.disconnected() } }
    func pageConnected() { if state.connection != nil && state.phase != .recoveryRequired { state.phase = .ready } }
    func webNotice(_ message: String) { notice = message }

    func disconnectClientsBeforeQuit() async {
        pollTask?.cancel()
        for connection in connections where connection.mode == "ssh" {
            _ = try? await call("remote_disconnect", ["connection_id": .string(connection.id)])
        }
    }
    private func select(_ connection: MiaConnection) {
        clearUpdateReview()
        state.show(connection); preferences.set(connection.id, forKey: "Mia.selectedConnection")
        if let index = connections.firstIndex(where: { $0.id == connection.id }) { connections[index] = connection } else { connections.append(connection) }
        showControls = false
    }
    func reviewPreparedUpdate() {
        guard let connection = state.connection, connection.mode == "local", let plan = try? ReviewPlan(updates, hashKey: "plan_sha256") else { return }
        updatePlan = plan; backendRefreshPlan = false; updatePlanScope = OperationScope(connection)
    }
    private func clearRemoteReview() { remotePlan = nil; remoteOperation = nil; remotePlanScope = nil; remotePlanValues = [:] }
    private func invalidateReviewedOperations() { updatePlan = nil; updatePlanScope = nil; backendRefreshPlan = false; clearRemoteReview() }
    private func clearUpdateReview() { invalidateReviewedOperations(); updates = [:] }
    private func verifyRestored(_ restored: MiaConnection, expected: MiaConnection, fingerprint: String? = nil) throws {
        guard restored.id == expected.id, restored.installationID == expected.installationID, restored.mode == expected.mode else { throw BridgeFailure.invalidResponse }
        for field in ["host", "user", "port", "remote_port"] where expected.metadata[field] != nil {
            guard restored.metadata[field] == expected.metadata[field] else { throw BridgeFailure.invalidResponse }
        }
        if let pinned = fingerprint ?? expected.metadata["host_key_fingerprint"]?.string {
            guard restored.metadata["host_key_fingerprint"]?.string == pinned else { throw BridgeFailure.invalidResponse }
        }
        if expected.mode == "https" { guard WebOrigin(restored.url) == WebOrigin(expected.url) else { throw BridgeFailure.invalidResponse } }
    }
    private func call(_ action: String, _ payload: [String: JSONValue] = [:]) async throws -> [String: JSONValue] { try await bridge.call(BridgeRequest(action: action, payload: payload)) }
    private func perform(_ message: String, mutation: Bool = false, operation: () async throws -> Void) async {
        guard !busy else { return }
        busy = true; progress = message; errorMessage = nil; notice = nil
        defer { busy = false; progress = "" }
        do { try await operation() }
        catch { errorMessage = safeMessage(error); if mutation { invalidateReviewedOperations(); state.mutationFailed() } }
    }
    private func safeMessage(_ error: Error) -> String { (error as? BridgeFailure)?.errorDescription ?? "Não foi possível concluir. Confira o estado da instalação antes de tentar novamente." }
}
#endif
