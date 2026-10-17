// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "Mia",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "Mia", targets: ["Mia"]), .library(name: "MiaCore", targets: ["MiaCore"])],
    dependencies: [.package(url: "https://github.com/sparkle-project/Sparkle", exact: "2.10.0")],
    targets: [
        .target(name: "MiaCore"),
        .executableTarget(name: "Mia", dependencies: ["MiaCore", .product(name: "Sparkle", package: "Sparkle", condition: .when(platforms: [.macOS]))], linkerSettings: [.unsafeFlags(["-Xlinker", "-rpath", "-Xlinker", "@executable_path/../Frameworks"], .when(platforms: [.macOS]))]),
        .testTarget(name: "MiaCoreTests", dependencies: ["MiaCore"]),
        .testTarget(name: "MiaClientTests", dependencies: ["Mia", "MiaCore"])
    ]
)
