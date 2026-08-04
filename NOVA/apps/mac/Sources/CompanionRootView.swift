import SwiftUI

struct CompanionRootView: View {
    @ObservedObject var viewModel: CompanionViewModel

    var body: some View {
        ZStack {
            Color.clear
                .ignoresSafeArea()

            VStack(spacing: 14) {
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("NOVA Companion")
                            .font(.system(size: 22, weight: .bold, design: .rounded))
                            .foregroundColor(.white)
                        Text(viewModel.connectionText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundColor(Color.white.opacity(0.7))
                    }
                    Spacer()
                    StatePill(state: viewModel.state)
                }
                .padding(.horizontal, 16)
                .padding(.top, 14)

                CompanionSceneView(sceneController: viewModel.sceneController)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 18, style: .continuous)
                            .stroke(Color.white.opacity(0.14), lineWidth: 1)
                    )
                    .padding(.horizontal, 16)

                VStack(spacing: 8) {
                    HStack(spacing: 8) {
                        MiniControlButton(title: "Load Model") {
                            viewModel.loadModelFromDisk()
                        }
                        MiniControlButton(title: "Reset Cam") {
                            viewModel.sceneController.resetCamera()
                        }
                        MiniControlButton(title: "Zoom +") {
                            viewModel.sceneController.zoomCamera(delta: -0.45)
                        }
                        MiniControlButton(title: "Zoom -") {
                            viewModel.sceneController.zoomCamera(delta: 0.45)
                        }
                    }

                    HStack(spacing: 8) {
                        MiniControlButton(title: "Rotate <-") {
                            viewModel.sceneController.rotateCat(by: 0.25)
                        }
                        MiniControlButton(title: "Rotate ->") {
                            viewModel.sceneController.rotateCat(by: -0.25)
                        }
                        MiniControlButton(title: "Idle") {
                            viewModel.preview(state: .idle)
                        }
                        MiniControlButton(title: "Listen") {
                            viewModel.preview(state: .listening)
                        }
                        MiniControlButton(title: "Think") {
                            viewModel.preview(state: .thinking)
                        }
                        MiniControlButton(title: "Speak") {
                            viewModel.preview(state: .speaking)
                        }
                    }

                    HStack {
                        Text(viewModel.sceneController.modelStatus)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundColor(Color.white.opacity(0.72))
                        Spacer()
                    }
                }
                .padding(.horizontal, 16)

                HStack {
                    Text("Event: \(viewModel.lastEvent)")
                        .font(.system(size: 12, weight: .regular, design: .monospaced))
                        .foregroundColor(Color.white.opacity(0.75))
                    Spacer()
                    Text("State: \(viewModel.state.rawValue)")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundColor(Color.white.opacity(0.85))
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [Color(red: 0.04, green: 0.08, blue: 0.16).opacity(0.94), Color(red: 0.01, green: 0.03, blue: 0.07).opacity(0.92)],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.35), radius: 28, x: 0, y: 12)
            .padding(16)
        }
        .onAppear {
            viewModel.start()
        }
        .onDisappear {
            viewModel.stop()
        }
    }
}

private struct MiniControlButton: View {
    let title: String
    let action: () -> Void

    var body: some View {
        Button(title, action: action)
            .buttonStyle(.plain)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .foregroundColor(.white)
            .background(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .fill(Color.white.opacity(0.12))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 9, style: .continuous)
                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
            )
    }
}

private struct StatePill: View {
    let state: AvatarVisualState

    var body: some View {
        Text(state.rawValue.capitalized)
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .foregroundColor(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(state.color.opacity(0.85), in: Capsule())
            .overlay(Capsule().stroke(Color.white.opacity(0.28), lineWidth: 1))
    }
}
