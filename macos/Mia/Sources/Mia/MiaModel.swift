#if os(macOS)
import Foundation
import SwiftUI
import MiaCore

enum DestinationChoice: String, CaseIterable, Identifiable {
    case local = "Neste Mac", server = "No meu servidor", existing = "Conectar à minha Mia"
    var id: String { rawValue }
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
    private var approvedFingerprint: String?
    private var pendingRemotePayload: [String: JSONValue]?
    private let bridge: any BridgeCalling
    private let preferences: UserDefaults
    private var pollTask: Task<Void, Never>?
    static let appVersion = "0.2.0a13"

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
            if initial {
                let remembered = preferences.string(forKey: "Mia.selectedConnection")
                if let selected = found.first(where: { $0.id == remembered }), !localRecoveryRequired {
                    state.show(selected)
                    if !selected.running && !(selected.mode == "local" && selected.metadata["paused"]?.bool == true) { await reconnect() }
                }
            } else if let selected = state.connection, let current = found.first(where: { $0.id == selected.id && $0.installationID == selected.installationID }) {
                if !current.running { state.disconnected() }
                // A recovered process may have a new port. Explicit reconnect also
                // reloads the window; a poll does not discard an in-progress form.
            }
        } catch {
            if initial { errorMessage = safeMessage(error) }
            if state.connection != nil { state.disconnected() }
        }
    }

    func begin() { state.chooseDestination() }
    func changeDestination() { plan = nil; hostFingerprint = nil; approvedFingerprint = nil; state.chooseDestination(); showControls = false }

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
            if let approved = self.approvedFingerprint { payload["approved_host_fingerprint"] = .string(approved) }
            self.pendingRemotePayload = payload
            let result = try await self.call("remote_preflight", payload)
            guard let fingerprint = result["host_key_fingerprint"]?.string, !fingerprint.isEmpty else { throw BridgeFailure.invalidResponse }
            if result["host_key_known"]?.bool != true && self.approvedFingerprint != fingerprint {
                self.hostFingerprint = fingerprint; return
            }
            self.approvedFingerprint = fingerprint
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
        state.show(connection)
        await reconnect()
    }

    func reconnect() async {
        guard let connection = state.connection else { return }
        await perform("Reconectando à sua instalação…") {
            let result: [String: JSONValue]
            if connection.mode == "local" { result = try await self.call("local_start") }
            else if connection.mode == "https" { result = try await self.call("https_connect", ["url": .string(connection.url.absoluteString)]) }
            else {
                // Retrieve the previously pinned host and key from private state.
                result = try await self.call("remote_connect", ["connection_id": .string(connection.id)])
            }
            self.select(try MiaConnection(result["local"]?.object ?? result["connection"]?.object ?? result, local: connection.mode == "local"))
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
        await perform("Criando e verificando uma cópia de recuperação…", mutation: true) {
            let result = try await self.call("local_snapshot")
            guard result["verified"]?.bool == true else { throw BridgeFailure.invalidResponse }
            self.notice = result["summary"]?.array?.compactMap(\.string).joined(separator: "\n") ?? "Cópia de recuperação criada e verificada."
        }
    }

    func inspectBundledUpdate() async {
        await perform("Conferindo a versão incluída neste app…") {
            let result = try await self.call("local_bundle_plan")
            if result["update_available"]?.bool == false {
                self.notice = "Esta instalação já usa a versão incluída no app. Sua biblioteca permanece disponível."
                self.updatePlan = nil; return
            }
            self.updatePlan = try ReviewPlan(result)
            self.backendRefreshPlan = true
        }
    }

    func applyBundledUpdate() async {
        guard let plan = updatePlan else { return }
        await perform("Atualizando a instalação deste Mac com recuperação…", mutation: true) {
            let result = try await self.call("local_bundle_update", ["approve_sha256": .string(plan.id)])
            if let connection = try? MiaConnection(result["local"]?.object ?? result, local: true) { self.select(connection) }
            self.updatePlan = nil; self.backendRefreshPlan = false; self.webReloadID = UUID()
            self.notice = "Instalação atualizada e verificada. Sua biblioteca foi preservada."
        }
        await refresh()
    }

    func loadUpdates(check: Bool = false) async {
        await perform(check ? "Buscando atualização do destino…" : "Conferindo atualizações…") {
            self.updates = try await self.call(check ? "updates_check" : "updates_status")
        }
    }
    func prepareUpdate() async {
        guard let id = (updates["release"]?.object ?? updates["releases"]?.array?.first?.object)?["id"]?.string else { return }
        await perform("Baixando e verificando a atualização…", mutation: true) {
            self.updates = try await self.call("updates_prepare", ["release_id": .string(id)])
            self.updatePlan = try ReviewPlan(self.updates, hashKey: "plan_sha256")
            self.backendRefreshPlan = false
        }
    }
    func discardUpdatePreparation() async {
        let id = updates["release"]?.object?["id"]?.string ?? ""
        await perform("Descartando somente a preparação da atualização…", mutation: true) {
            self.updates = try await self.call("updates_prepare", ["release_id": .string(id), "discard": .bool(true)])
            self.updatePlan = nil
        }
    }
    func applyUpdate() async {
        guard let plan = updatePlan else { return }
        await perform("Aplicando atualização com recuperação…", mutation: true) {
            self.updates = try await self.call("updates_apply", ["approve_sha256": .string(plan.id)])
            self.updatePlan = nil
            self.notice = self.updates["summary"]?.string
            self.webReloadID = UUID()
        }
        await refresh()
    }
    func recoverUpdate() async {
        await perform("Recuperando a atualização…", mutation: true) {
            self.updates = try await self.call("updates_recover")
            self.updatePlan = nil; self.notice = self.updates["summary"]?.string
            self.webReloadID = UUID()
        }
        await refresh()
    }

    func pageDisconnected() { if !busy { state.disconnected() } }
    func pageConnected() { if state.connection != nil && state.phase != .recoveryRequired { state.phase = .ready } }
    func webNotice(_ message: String) { notice = message }

    func disconnectClientsBeforeQuit() async {
        pollTask?.cancel()
        for connection in connections where connection.mode == "ssh" {
            _ = try? await call("remote_disconnect", ["connection_id": .string(connection.id)])
        }
    }
    private func select(_ connection: MiaConnection) {
        state.show(connection); preferences.set(connection.id, forKey: "Mia.selectedConnection")
        if let index = connections.firstIndex(where: { $0.id == connection.id }) { connections[index] = connection } else { connections.append(connection) }
        showControls = false
    }
    private func call(_ action: String, _ payload: [String: JSONValue] = [:]) async throws -> [String: JSONValue] { try await bridge.call(BridgeRequest(action: action, payload: payload)) }
    private func perform(_ message: String, mutation: Bool = false, operation: () async throws -> Void) async {
        guard !busy else { return }
        busy = true; progress = message; errorMessage = nil; notice = nil
        defer { busy = false; progress = "" }
        do { try await operation() }
        catch { errorMessage = safeMessage(error); if mutation { state.mutationFailed() } }
    }
    private func safeMessage(_ error: Error) -> String { (error as? BridgeFailure)?.errorDescription ?? "Não foi possível concluir. Confira o estado da instalação antes de tentar novamente." }
}
#endif
