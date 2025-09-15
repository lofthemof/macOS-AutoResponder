// swift-tools-version: 6.1
// The swift-tools-version declares the minimum version of Swift required to build this package.

import PackageDescription

let package = Package(
    name: "AutoResponder",
    platforms: [
        .macOS(.v13)
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "AutoResponder",
            dependencies: [],
            linkerSettings: [
                .linkedLibrary("sqlite3")
            ]
        )
    ]
)
