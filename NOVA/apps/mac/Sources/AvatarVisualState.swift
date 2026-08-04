import SwiftUI

enum AvatarVisualState: String {
    case idle
    case listening
    case thinking
    case speaking
    case error

    var color: Color {
        switch self {
        case .idle:
            return Color(red: 0.0, green: 0.86, blue: 1.0)
        case .listening:
            return Color(red: 0.0, green: 0.72, blue: 1.0)
        case .thinking:
            return Color(red: 1.0, green: 0.77, blue: 0.28)
        case .speaking:
            return Color(red: 1.0, green: 0.45, blue: 0.56)
        case .error:
            return Color(red: 0.92, green: 0.29, blue: 0.4)
        }
    }

    static func from(event: String, fallbackState: String) -> AvatarVisualState {
        switch event {
        case "listening_started":
            return .listening
        case "listening_completed", "thinking_completed", "speaking_completed", "idle":
            return .idle
        case "thinking_started":
            return .thinking
        case "speaking_started":
            return .speaking
        default:
            return AvatarVisualState(rawValue: fallbackState.lowercased()) ?? .idle
        }
    }
}
