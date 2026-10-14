import Foundation
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

public protocol BridgeCalling: Sendable {
    func call(_ request: BridgeRequest) async throws -> [String: JSONValue]
}

public struct BridgeRunner: BridgeCalling, Sendable {
    public static let maximumRequestBytes = 65_536
    public static let maximumResponseBytes = 1_048_576
    public let resources: URL
    private let testDeadline: TimeInterval?
    public init(resources: URL) { self.resources = resources; self.testDeadline = nil }
    internal init(resources: URL, testDeadline: TimeInterval) { self.resources = resources; self.testDeadline = testDeadline }
    public func call(_ request: BridgeRequest) async throws -> [String: JSONValue] {
        try await Task.detached(priority: .userInitiated) { try run(request) }.value
    }

    private func run(_ request: BridgeRequest) throws -> [String: JSONValue] {
        let executable = resources.appendingPathComponent("runtime/bin/python3")
        let script = resources.appendingPathComponent("desktop_bridge.py")
        let files = FileManager.default
        guard files.isExecutableFile(atPath: executable.path), files.fileExists(atPath: script.path),
              executable.resolvingSymlinksInPath().path.hasPrefix(resources.resolvingSymlinksInPath().path + "/"),
              script.resolvingSymlinksInPath().path.hasPrefix(resources.resolvingSymlinksInPath().path + "/") else { throw BridgeFailure.missingRuntime }
        let encoded = try JSONEncoder().encode(request)
        guard encoded.count <= Self.maximumRequestBytes else { throw BridgeFailure.requestTooLarge }
        let process = Process()
        process.executableURL = executable
        process.arguments = ["-I", "-B", script.path]
        var environment = ["HOME": NSHomeDirectory(), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": NSTemporaryDirectory(), "LANG": "en_US.UTF-8"]
        if let agent = ProcessInfo.processInfo.environment["SSH_AUTH_SOCK"] { environment["SSH_AUTH_SOCK"] = agent }
        process.environment = environment
        process.currentDirectoryURL = resources
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.standardInput = input; process.standardOutput = output; process.standardError = errors
        let terminated = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in terminated.signal() }
        try process.run()
        input.fileHandleForReading.closeFile()
        output.fileHandleForWriting.closeFile(); errors.fileHandleForWriting.closeFile()
        let collector = BoundedOutput(limit: Self.maximumResponseBytes)
        let readers = DispatchGroup()
        for (pipe, capture) in [(output, true), (errors, false)] {
            readers.enter()
            DispatchQueue.global(qos: .utility).async {
                defer { pipe.fileHandleForReading.closeFile(); readers.leave() }
                while true {
                    let data = pipe.fileHandleForReading.availableData
                    if data.isEmpty { break }
                    if capture && !collector.append(data) && process.isRunning { process.terminate() }
                    // stderr is drained without retaining or publishing private logs.
                }
            }
        }
        // Writing happens off the waiting thread: an unresponsive child that does
        // not consume stdin cannot defeat the operation deadline by filling a pipe.
        readers.enter()
        DispatchQueue.global(qos: .utility).async {
            defer { input.fileHandleForWriting.closeFile(); readers.leave() }
            do { try input.fileHandleForWriting.write(contentsOf: encoded) }
            catch { if process.isRunning { process.terminate() } }
        }
        let timeout: TimeInterval = testDeadline ?? (["local_install", "remote_install", "updates_prepare", "updates_apply", "local_recover", "updates_recover", "local_bundle_update"].contains(request.action) ? 900 : 90)
        if terminated.wait(timeout: .now() + timeout) == .timedOut {
            if process.isRunning { process.terminate() }
            if terminated.wait(timeout: .now() + 3) == .timedOut && process.isRunning { kill(process.processIdentifier, SIGKILL); _ = terminated.wait(timeout: .now() + 3) }
            throw BridgeFailure.timeout
        }
        guard readers.wait(timeout: .now() + 3) == .success else { throw BridgeFailure.invalidResponse }
        guard !collector.exceeded else { throw BridgeFailure.responseTooLarge }
        let data = collector.data
        guard !data.isEmpty, let response = try? JSONDecoder().decode(BridgeResponse.self, from: data) else { throw BridgeFailure.invalidResponse }
        // A structured safe failure can accompany a nonzero exit; no raw stderr leaks.
        guard process.terminationStatus == 0 || !response.ok else { throw BridgeFailure.processFailed }
        return try response.checkedResult()
    }
}

private final class BoundedOutput: @unchecked Sendable {
    private let lock = NSLock()
    private let limit: Int
    private var bytes = Data()
    private var overflow = false
    init(limit: Int) { self.limit = limit }
    func append(_ data: Data) -> Bool {
        lock.lock(); defer { lock.unlock() }
        guard !overflow, data.count <= limit - bytes.count else { overflow = true; return false }
        bytes.append(data); return true
    }
    var exceeded: Bool { lock.lock(); defer { lock.unlock() }; return overflow }
    var data: Data { lock.lock(); defer { lock.unlock() }; return bytes }
}
