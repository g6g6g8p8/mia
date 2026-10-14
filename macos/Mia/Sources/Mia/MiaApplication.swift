#if os(macOS)
import AppKit
import CryptoKit
import Foundation
import SwiftUI
import MiaCore

/// Public feed-verification helper only. No privileged command line operations.
private func runSignatureHelperIfRequested() {
    let arguments = CommandLine.arguments
    guard arguments.dropFirst().first == "--verify-ed25519" else { return }
    guard arguments.count == 5, let key = Data(base64Encoded: arguments[2]), key.count == 32,
          let signature = Data(base64Encoded: arguments[3]), signature.count == 64 else { exit(2) }
    let path = URL(fileURLWithPath: arguments[4])
    guard let size = try? path.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey]), size.isRegularFile == true,
          let bytes = size.fileSize, bytes <= 2_097_152,
          let data = try? Data(contentsOf: path), data.count <= 2_097_152,
          let publicKey = try? Curve25519.Signing.PublicKey(rawRepresentation: key), publicKey.isValidSignature(signature, for: data) else { exit(1) }
    exit(0)
}

@MainActor final class MiaApplicationDelegate: NSObject, NSApplicationDelegate {
    weak var model: MiaModel?
    var reopen: (() -> Void)?
    private var quitting = false
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { reopen?() }
        return true
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if quitting { return .terminateNow }
        guard let model else { return .terminateNow }
        if model.busy {
            let alert = NSAlert(); alert.messageText = "Uma operação da Mia está em andamento"; alert.informativeText = "Aguarde a conclusão antes de sair. Sua instalação e seus dados precisam terminar esta etapa com segurança."; alert.addButton(withTitle: "Continuar aguardando"); alert.runModal()
            return .terminateCancel
        }
        quitting = true
        Task { await model.disconnectClientsBeforeQuit(); sender.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }
}

@main @MainActor struct MiaApplication: App {
    @NSApplicationDelegateAdaptor(MiaApplicationDelegate.self) private var delegate
    @StateObject private var model: MiaModel
    @StateObject private var updater: AppUpdater
    init() {
        runSignatureHelperIfRequested()
        let resources = Bundle.main.resourceURL ?? Bundle.main.bundleURL.appendingPathComponent("Contents/Resources")
        _model = StateObject(wrappedValue: MiaModel(bridge: BridgeRunner(resources: resources)))
        _updater = StateObject(wrappedValue: AppUpdater())
    }
    var body: some Scene {
        Window("Mia", id: "mia") {
            MiaWindow(model: model, updater: updater, delegate: delegate)
        }.defaultSize(width: 1040, height: 780)
        .commands { MiaCommands(model: model, updater: updater) }
    }
}

@MainActor private struct MiaCommands: Commands {
    @ObservedObject var model: MiaModel
    @ObservedObject var updater: AppUpdater
    @Environment(\.openWindow) private var openWindow
    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Button("Minha instalação…") { openWindow(id: "mia"); model.showControls = true }.keyboardShortcut(",")
            Button("Buscar atualização do app…") { updater.check() }.disabled(!updater.configured || updater.updating || model.busy)
        }
        CommandGroup(before: .windowArrangement) { Button("Mostrar Mia") { openWindow(id: "mia") }.keyboardShortcut("1") }
    }
}
#else
import Foundation
@main struct UnsupportedPlatform {
    static func main() { FileHandle.standardError.write(Data("Mia requer macOS 13 ou posterior. Este executável de desenvolvimento não inicia a interface neste sistema.\n".utf8)); exit(2) }
}
#endif
