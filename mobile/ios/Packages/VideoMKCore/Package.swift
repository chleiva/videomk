// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "VideoMKCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "VideoMKCore", targets: ["VideoMKCore"])],
    targets: [
        .target(name: "VideoMKCore"),
        .testTarget(name: "VideoMKCoreTests", dependencies: ["VideoMKCore"]),
    ]
)
