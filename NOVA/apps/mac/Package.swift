// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NOVACompanion",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(name: "NOVACompanion", targets: ["NOVACompanion"]),
    ],
    targets: [
        .executableTarget(
            name: "NOVACompanion",
            path: "Sources"
        ),
    ]
)
