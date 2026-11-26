// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VideoMKCore",
    defaultLocalization: "en",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "VideoMKCore", targets: ["VideoMKCore"])],
    targets: [
        .target(name: "VideoMKCore", resources: [.copy("Strings")]),
        .testTarget(name: "VideoMKCoreTests", dependencies: ["VideoMKCore"]),
    ]
)
