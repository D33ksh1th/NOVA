import Foundation
import SwiftUI

@MainActor
final class CompanionViewModel: ObservableObject {
    @Published var state: AvatarVisualState = .idle
    @Published var lastEvent: String = "snapshot"
    @Published var connectionText: String = "Connecting to avatar stream..."

    let sceneController = CompanionSceneController()
    private let eventClient = AvatarEventClient()

    func start() {
        eventClient.start(
            onEvent: { [weak self] envelope in
                Task { @MainActor in
                    self?.apply(envelope: envelope)
                }
            },
            onConnectionChange: { [weak self] connected in
                Task { @MainActor in
                    self?.connectionText = connected ? "Connected to http://127.0.0.1:8000/avatar/events" : "Reconnecting to avatar stream..."
                }
            }
        )
    }

    func stop() {
        eventClient.stop()
        connectionText = "Disconnected"
    }

    func preview(state nextState: AvatarVisualState) {
        state = nextState
        lastEvent = "preview_\(nextState.rawValue)"
        sceneController.setState(nextState)
    }

    func loadModelFromDisk() {
        sceneController.promptForModelImport()
    }

    private func apply(envelope: AvatarEnvelope) {
        lastEvent = envelope.event

        let mapped = AvatarVisualState.from(event: envelope.event, fallbackState: envelope.state)
        state = mapped
        sceneController.setState(mapped)
    }
}
