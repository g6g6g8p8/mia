#if os(macOS)
import AppKit
import SwiftUI
import UniformTypeIdentifiers
import MiaCore

@MainActor struct MiaWindow: View {
    @ObservedObject var model: MiaModel
    @ObservedObject var updater: AppUpdater
    let delegate: MiaApplicationDelegate
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        VStack(spacing: 0) {
            if model.busy { HStack { ProgressView().controlSize(.small); Text(model.progress); Spacer() }.padding(12).background(Color.accentColor.opacity(0.08)) }
            if let error = model.errorMessage { statusBanner(error, error: true) }
            if let notice = model.notice { statusBanner(notice) }
            switch model.state.phase {
            case .welcome: welcome
            case .choosing, .preparing: destinations
            case .recoveryRequired: recovery
            case .ready, .offline:
                if let connection = model.state.connection {
                    ZStack(alignment: .top) {
                        MiaWebView(connection: connection, reloadID: model.webReloadID, disconnected: model.pageDisconnected, connected: model.pageConnected, notice: model.webNotice).id(connection.id + ":" + connection.installationID)
                        if model.state.phase == .offline { offline(connection) }
                    }
                } else { destinations }
            }
        }
        .frame(minWidth: 760, minHeight: 560)
        .toolbar {
            ToolbarItem(placement: .navigation) { Text("Mia").font(.headline) }
            ToolbarItem { if let connection = model.state.connection { Text(connection.title).font(.subheadline).foregroundStyle(.secondary) } }
            ToolbarItem { Button { model.showControls = true } label: { Label("Minha instalação", systemImage: "slider.horizontal.3") } }
        }
        .sheet(isPresented: $model.showControls) { InstallationControls(model: model, updater: updater) }
        .task { updater.model = model; await model.start() }
        .onAppear { delegate.model = model; let action = openWindow; delegate.reopen = { action(id: "mia") } }
        .disabled(model.busy || updater.updating)
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 24) {
            Text("Mia Demo").font(.subheadline).foregroundStyle(.secondary)
            Text("Seu trabalho tem uma história.\nContinue de onde parou.").font(.system(size: 36, weight: .semibold))
            Text("Reúna suas notas e conversas para retomar projetos, encontrar decisões e avançar com fontes.").font(.title3).foregroundStyle(.secondary)
            Text("Esta Mia será sua: escolha onde guardar o contexto, crie seu acesso e confira o material antes de importar. Você pode começar sem configurar IA.")
            Button("Começar", action: model.begin).buttonStyle(.borderedProminent).controlSize(.large)
            if !model.connections.isEmpty {
                Divider(); Text("Ou retome uma instalação sua:").foregroundStyle(.secondary)
                ForEach(model.connections) { connection in Button(connection.title) { Task { await model.connectSaved(connection) } } }
            }
            Text("App \(MiaModel.appVersion) · distribuição da demonstração por convite · código Apache-2.0").font(.caption).foregroundStyle(.secondary)
        }.padding(48).frame(maxWidth: 820, maxHeight: .infinity, alignment: .leading)
    }
    private var destinations: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                Text("Onde você quer guardar seu contexto?").font(.largeTitle).fontWeight(.semibold)
                Picker("Destino", selection: $model.choice) { ForEach(DestinationChoice.allCases) { Text($0.rawValue).tag($0) } }.pickerStyle(.segmented)
                    .onChange(of: model.choice) { _ in model.plan = nil; model.hostFingerprint = nil }
                if let plan = model.plan {
                    PlanReview(plan: plan, title: "Confira sua instalação", actionTitle: "Preparar minha Mia", approve: { Task { await model.installReviewedPlan() } }, cancel: { model.plan = nil })
                } else {
                    switch model.choice {
                    case .local: localChoice
                    case .server: serverChoice
                    case .existing: existingChoice
                    }
                }
                if !model.connections.isEmpty { Divider(); Text("Instalações salvas").font(.headline); ForEach(model.connections) { connection in Button(connection.title) { Task { await model.connectSaved(connection) } } } }
            }.padding(40).frame(maxWidth: 820, alignment: .leading)
        }
    }
    private var localChoice: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label("Recomendado para começar", systemImage: "laptopcomputer").font(.headline)
            Text("A Mia prepara uma instalação privada neste Mac, sem Terminal ou Python instalado por você. Sua biblioteca fica fora do aplicativo e acompanha as atualizações.")
            Text("Disponível enquanto este Mac estiver ligado e acordado. Fechar a janela mantém a Mia ativa; sair do app não apaga nem para sua instalação.").foregroundStyle(.secondary)
            if let local = model.connections.first(where: { $0.mode == "local" }) {
                Button("Abrir minha Mia neste Mac") { Task { await model.connectSaved(local) } }.buttonStyle(.borderedProminent)
            } else { Button("Conferir este Mac") { Task { await model.prepareLocal() } }.buttonStyle(.borderedProminent) }
        }
    }
    private var serverChoice: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("O contexto fica no seu servidor; a Mia conecta por SSH sem Terminal aberto. Seu servidor precisa estar disponível para usar esta instalação.")
            Text("Primeira modalidade de instalação: Ubuntu 24.04 LTS amd64, quando o artefato correspondente estiver incluído e validado. A Mia informa antes de alterar o servidor se ele não for compatível.").foregroundStyle(.secondary)
            TextField("Endereço do servidor", text: $model.serverHost)
            HStack { TextField("Usuário SSH", text: $model.serverUser); TextField("Porta SSH", text: $model.serverPort).frame(width: 130) }
            HStack { Button("Escolher chave SSH…", action: chooseSSHKey); Text(model.serverKey?.lastPathComponent ?? "Usar agente SSH ou chave existente").foregroundStyle(.secondary); if model.serverKey != nil { Button("Usar padrão") { model.serverKey = nil } } }
            Text("A chave permanece neste Mac. A Mia usa autenticação SSH existente e não pede sua senha SSH na página web.").font(.caption).foregroundStyle(.secondary)
            Toggle("Já tenho uma Mia neste servidor; apenas conectar", isOn: $model.serverConnectOnly)
            if let fingerprint = model.hostFingerprint {
                GroupBox("Confira a identidade do servidor") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Este servidor ainda não tem uma identidade confiada pela Mia. Compare esta impressão digital com a fornecida pelo administrador antes de continuar.")
                        Text(fingerprint).font(.system(.body, design: .monospaced)).textSelection(.enabled)
                        HStack { Button("Confirmar identidade") { Task { await model.approveHostIdentity() } }.buttonStyle(.borderedProminent); Button("Cancelar") { model.hostFingerprint = nil } }
                    }.padding(8)
                }
            } else { Button("Conferir servidor") { Task { await model.inspectServer() } }.buttonStyle(.borderedProminent) }
            Text("Acesso no iPhone exige um endereço HTTPS persistente, preparado depois. O túnel deste app atende ao Mac.").font(.caption).foregroundStyle(.secondary)
        }.textFieldStyle(.roundedBorder)
    }
    private var existingChoice: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Abra uma instalação sua já disponível por HTTPS. Seus dados permanecem naquele destino; o login acontece dentro da janela da Mia.")
            TextField("https://minha-mia.exemplo", text: $model.existingURL).textFieldStyle(.roundedBorder)
            Button("Conectar à minha Mia") { Task { await model.connectExisting() } }.buttonStyle(.borderedProminent)
            Text("Para uma instalação acessível somente por SSH, escolha No meu servidor e marque que ela já existe.").foregroundStyle(.secondary)
        }
    }
    private var recovery: some View {
        VStack(alignment: .leading, spacing: 20) {
            Label("Confira sua instalação antes de continuar", systemImage: "arrow.clockwise.circle").font(.title)
            Text("Uma operação não foi concluída ou seu resultado não foi confirmado. O app preserva o destino e não cria uma biblioteca vazia no lugar da anterior.")
            HStack {
                Button("Conferir estado") { Task { await model.refresh(initial: true) } }.buttonStyle(.borderedProminent)
                if model.state.connection?.mode == "local" || model.choice == .local { Button("Recuperar instalação neste Mac") { Task { await model.recoverLocal() } } }
                Button("Escolher outro destino", action: model.changeDestination)
            }
            Text("Se a operação foi no servidor, reconecte ao mesmo destino antes de repetir uma instalação.").foregroundStyle(.secondary)
        }.padding(48).frame(maxWidth: 820, maxHeight: .infinity, alignment: .leading)
    }
    private func offline(_ connection: MiaConnection) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Label("Conexão interrompida", systemImage: "wifi.slash").font(.title2)
            Text("Sua biblioteca permanece no destino. Reconectar retoma esta instalação sem reinstalar ou substituir dados.")
            HStack { Button("Reconectar") { Task { await model.reconnect() } }.buttonStyle(.borderedProminent); Button("Minha instalação") { model.showControls = true } }
        }.padding(24).background(.regularMaterial).cornerRadius(14).padding(24).frame(maxWidth: 680)
    }
    private func statusBanner(_ text: String, error: Bool = false) -> some View {
        HStack(alignment: .top) { Image(systemName: error ? "exclamationmark.circle" : "info.circle"); Text(text).textSelection(.enabled); Spacer(); Button { if error { model.errorMessage = nil } else { model.notice = nil } } label: { Image(systemName: "xmark") }.buttonStyle(.plain) }.font(.callout).padding(12).background(error ? Color.orange.opacity(0.12) : Color.blue.opacity(0.08))
    }
    private func chooseSSHKey() {
        let panel = NSOpenPanel(); panel.title = "Escolher chave SSH privada"; panel.prompt = "Usar esta chave"; panel.canChooseFiles = true; panel.canChooseDirectories = false; panel.allowsMultipleSelection = false; panel.showsHiddenFiles = true; panel.resolvesAliases = false
        panel.begin { if $0 == .OK { model.serverKey = panel.url } }
    }
}

@MainActor struct PlanReview: View {
    let plan: ReviewPlan
    let title: String
    let actionTitle: String
    var approve: () -> Void
    var cancel: () -> Void
    var body: some View {
        GroupBox(title) {
            VStack(alignment: .leading, spacing: 14) {
                ForEach(Array(plan.summary.enumerated()), id: \.offset) { _, line in Label(line, systemImage: "checkmark.circle").fixedSize(horizontal: false, vertical: true) }
                DisclosureGroup("Detalhes técnicos") { ScrollView { Text("Plano: \(plan.id)\n\(plan.technicalDetails)").font(.system(.caption, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }.frame(maxHeight: 180) }
                HStack { Button(actionTitle, action: approve).buttonStyle(.borderedProminent); Button("Voltar", action: cancel) }
            }.padding(12)
        }
    }
}

@MainActor struct InstallationControls: View {
    @ObservedObject var model: MiaModel
    @ObservedObject var updater: AppUpdater
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack { Text("Minha instalação").font(.largeTitle); Spacer(); Button("Concluído") { dismiss() } }
                if model.busy { HStack { ProgressView(); Text(model.progress) } }
                if let message = model.errorMessage { Text(message).foregroundStyle(.orange) }
                if let message = model.notice { Text(message).foregroundStyle(.secondary) }
                if let connection = model.state.connection {
                    Text(connection.title).font(.title2); Text(connection.storageDescription)
                    Text("App \(MiaModel.appVersion) · instalação \(connection.version ?? "não confirmada")").font(.caption).foregroundStyle(.secondary)
                    if #unavailable(macOS 14.0) { Text("Neste macOS, sua sessão é isolada e temporária. Após sair do app, entre novamente; a biblioteca permanece no destino.").font(.caption).foregroundStyle(.secondary) }
                    HStack { Button("Reconectar") { Task { await model.reconnect() } }; Button("Trocar destino") { model.changeDestination(); dismiss() } }
                    if connection.mode == "local" {
                        Divider(); Text("Operação neste Mac").font(.headline)
                        HStack { Button("Cópia de recuperação") { Task { await model.snapshot() } }; Button("Parar Mia") { confirmStop() }; Button("Recuperar") { Task { await model.recoverLocal() } } }
                        Text("Cópias de recuperação ficam nesta instalação. Exporte pela Biblioteca para guardar outra cópia fora deste Mac.").font(.caption).foregroundStyle(.secondary)
                        Button("Conferir versão incluída no app") { Task { await model.inspectBundledUpdate() } }
                    } else { Text("Atualizar o app não atualiza seu servidor. Backup e recuperação do destino seguem as permissões daquela instalação.").font(.caption).foregroundStyle(.secondary) }
                } else { Text("Nenhuma instalação selecionada."); Button("Escolher destino") { model.begin(); dismiss() } }
                Divider(); Text("Atualizações do app").font(.headline)
                Text(updater.explanation).foregroundStyle(.secondary)
                Button("Buscar atualização do app") { updater.check() }.disabled(!updater.configured || updater.updating || model.busy)
                Divider(); Text("Atualização da instalação neste Mac").font(.headline)
                if model.state.connection?.mode == "local" {
                    Text(model.updates["summary"]?.string ?? "Confira o canal de atualização do destino antes de alterar sua instalação.").foregroundStyle(.secondary)
                    if let release = model.updates["release"]?.object ?? model.updates["releases"]?.array?.first?.object { Text("Versão \(release["version"]?.string ?? "")").font(.headline); Text(release["notes"]?.string ?? "") }
                    HStack { Button("Buscar atualização do destino") { Task { await model.loadUpdates(check: true) } }; if model.updates["state"]?.string == "available" { Button("Preparar atualização") { Task { await model.prepareUpdate() } } }; if model.updates["state"]?.string == "recovery_required" { Button("Recuperar atualização") { Task { await model.recoverUpdate() } } } }
                    if ["interrupted", "prepared"].contains(model.updates["state"]?.string ?? "") { Button("Descartar preparação da atualização") { Task { await model.discardUpdatePreparation() } } }
                    if model.updates["state"]?.string == "prepared", model.updatePlan == nil { Button("Revisar atualização preparada") { if let plan = try? ReviewPlan(model.updates, hashKey: "plan_sha256") { model.updatePlan = plan; model.backendRefreshPlan = false } } }
                } else { Text("Este app preserva a versão do seu servidor. Atualização remota pelo assistente ainda não está disponível.").foregroundStyle(.secondary) }
                if let plan = model.updatePlan {
                    PlanReview(plan: plan, title: "Confira a atualização", actionTitle: "Atualizar com recuperação", approve: { Task { if model.backendRefreshPlan { await model.applyBundledUpdate() } else { await model.applyUpdate() } } }, cancel: { model.updatePlan = nil })
                }
            }.padding(28)
        }.frame(width: 690, height: 620).disabled(model.busy || updater.updating).task { await model.loadUpdates() }
    }
    private func confirmStop() {
        let alert = NSAlert(); alert.messageText = "Parar Mia neste Mac?"; alert.informativeText = "Seus dados permanecem guardados. A Mia ficará indisponível até você escolher Retomar ou Reconectar."; alert.addButton(withTitle: "Parar Mia"); alert.addButton(withTitle: "Cancelar")
        if alert.runModal() == .alertFirstButtonReturn { Task { await model.stopLocal() } }
    }
}
#endif
