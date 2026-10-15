#if os(macOS)
import Foundation
import Security
import Sparkle
import SwiftUI

/// Sparkle owns signed app replacement. This client never overwrites its own bundle.
@MainActor final class AppUpdater: NSObject, ObservableObject, SPUUpdaterDelegate {
    @Published private(set) var configured = false
    @Published private(set) var updating = false
    @Published private(set) var explanation = "O canal oficial de atualização do app ainda não está configurado neste pacote."
    @Published private(set) var betaAccess = BetaAccess(policy: nil)
    private var controller: SPUStandardUpdaterController?
    private var channel: String?
    private var policy: BetaDistributionPolicy?
    weak var model: MiaModel?

    override init() { super.init(); configure() }
    func check() {
        guard configured, model?.busy != true, !updating else { return }
        guard let policy else { return }
        do { controller?.updater.httpHeaders = ["Authorization": try betaAccess.authorization(for: policy.feedURL)] }
        catch {
            explanation = (error as? BetaAccessFailure)?.localizedDescription ?? BetaAccessFailure.activationRequired.localizedDescription
            betaAccess.showActivation = true
            model?.showControls = true
            return
        }
        updating = true
        controller?.checkForUpdates(nil)
    }
    private func configure() {
        guard let resources = Bundle.main.resourceURL,
              let input = try? FileHandle(forReadingFrom: resources.appendingPathComponent("release-channel.json")) else { return }
        defer { try? input.close() }
        guard let data = try? input.read(upToCount: 65_537), data.count <= 65_536,
              let config = try? JSONSerialization.jsonObject(with: data) as? [String: Any], config["protocol"] as? Int == 1,
              let rawURL = config["appcast_url"] as? String, let url = URL(string: rawURL), url.scheme == "https", url.host != nil, url.user == nil, url.password == nil, url.fragment == nil,
              let key = config["sparkle_public_key"] as? String, Data(base64Encoded: key)?.count == 32,
              Bundle.main.object(forInfoDictionaryKey: "SUFeedURL") as? String == rawURL,
              Bundle.main.object(forInfoDictionaryKey: "SUPublicEDKey") as? String == key,
              config["beta_access_required"] as? Bool == true,
              let distributionURL = config["distribution_url"] as? String,
              signedApplication() else { return }
        #if arch(arm64)
        let architecture = "arm64"
        #else
        let architecture = "x86_64"
        #endif
        guard let policy = try? BetaDistributionPolicy(distributionURL: distributionURL, feedURL: rawURL, architecture: architecture) else { return }
        self.policy = policy
        betaAccess = BetaAccess(policy: policy)
        channel = config["channel"] as? String
        let controller = SPUStandardUpdaterController(startingUpdater: false, updaterDelegate: self, userDriverDelegate: nil)
        controller.updater.automaticallyChecksForUpdates = false
        controller.updater.automaticallyDownloadsUpdates = false
        controller.updater.sendsSystemProfile = false
        do {
            try controller.updater.start()
            self.controller = controller; configured = true
            explanation = "Atualizações oficiais da demonstração por convite, guardado no Chaves deste Mac. Essa autorização não controla seu acesso nem sua biblioteca. A instalação no servidor tem sua própria versão."
        } catch { explanation = "O canal de atualização do app não pôde ser iniciado. Este pacote continua disponível para uso e exportação." }
    }
    private func signedApplication() -> Bool {
        var code: SecStaticCode?
        guard SecStaticCodeCreateWithPath(Bundle.main.bundleURL as CFURL, [], &code) == errSecSuccess, let code,
              SecStaticCodeCheckValidity(code, SecCSFlags(rawValue: kSecCSCheckAllArchitectures), nil) == errSecSuccess else { return false }
        var information: CFDictionary?
        guard SecCodeCopySigningInformation(code, SecCSFlags(rawValue: kSecCSSigningInformation), &information) == errSecSuccess,
              let info = information as? [String: Any], let team = info[kSecCodeInfoTeamIdentifier as String] as? String, !team.isEmpty else { return false }
        return true
    }
    func updater(_ updater: SPUUpdater, mayPerform updateCheck: SPUUpdateCheck) throws {
        if model?.busy == true { throw NSError(domain: "Mia.AppUpdate", code: 1, userInfo: [NSLocalizedDescriptionKey: "Conclua a operação da instalação antes de atualizar o app."]) }
        guard let policy else { throw BetaAccessFailure.unconfigured }
        _ = try betaAccess.authorization(for: policy.feedURL)
    }
    // Ignore any Sparkle feed preference changed outside the reviewed bundle.
    func feedURLString(for updater: SPUUpdater) -> String? { policy?.feedURL.absoluteString }
    func updater(_ updater: SPUUpdater, didFinishLoadingAppcast appcast: SUAppcast) { updater.httpHeaders = nil }
    @objc(updater:shouldProceedWithUpdate:updateCheck:error:)
    func updater(_ updater: SPUUpdater, shouldProceedWithUpdate item: SUAppcastItem, updateCheck: SPUUpdateCheck) throws {
        guard let policy, let url = item.fileURL, policy.allowsDownload(url),
              item.deltaUpdates?.isEmpty != false,
              item.releaseNotesURL == nil, item.fullReleaseNotesURL == nil, item.infoURL == nil else { throw BetaAccessFailure.unsafeURL }
        _ = try betaAccess.authorization(for: url, download: true)
    }
    @objc(updater:shouldDownloadReleaseNotesForUpdate:)
    func updater(_ updater: SPUUpdater, shouldDownloadReleaseNotesForUpdate item: SUAppcastItem) -> Bool { false }
    @objc(updater:willDownloadUpdate:withRequest:)
    func updater(_ updater: SPUUpdater, willDownloadUpdate item: SUAppcastItem, with request: NSMutableURLRequest) {
        // Sparkle captures the original headers before delegate callbacks. Clear
        // them on this concrete request, then authorize only the reviewed route.
        request.setValue(nil, forHTTPHeaderField: "Authorization")
        guard let url = request.url, let authorization = try? betaAccess.authorization(for: url, download: true) else {
            request.url = URL(fileURLWithPath: "/dev/null") // Sparkle refuses non-HTTP downloads before network I/O.
            return
        }
        request.setValue(authorization, forHTTPHeaderField: "Authorization")
    }
    func allowedChannels(for updater: SPUUpdater) -> Set<String> { channel.map { [$0] } ?? [] }
    func updaterShouldRelaunchApplication(_ updater: SPUUpdater) -> Bool { model?.busy != true }
    func updater(_ updater: SPUUpdater, didFinishUpdateCycleFor updateCheck: SPUUpdateCheck, error: Error?) { updating = false; updater.httpHeaders = nil }
    func updater(_ updater: SPUUpdater, didAbortWithError error: Error) { updating = false; updater.httpHeaders = nil }
}
#endif
