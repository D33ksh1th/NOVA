import Foundation

// MARK: - Avatar State Machine

enum AvatarState: Equatable {
    case idle
    case listening(duration: Double = 3.0)
    case thinking(duration: Double = 2.0)
    case speaking(text: String, duration: Double = 4.0)
    case sleeping
    case happy
    case confused
    
    var description: String {
        switch self {
        case .idle: return "Idle"
        case .listening: return "Listening"
        case .thinking: return "Thinking"
        case .speaking(let text, _): return "Speaking: \(text.prefix(20))..."
        case .sleeping: return "Sleeping"
        case .happy: return "Happy"
        case .confused: return "Confused"
        }
    }
}

// MARK: - Backend Events

enum BackendEvent: Codable {
    case startedListening
    case startedThinking
    case startedSpeaking(text: String)
    case listeningComplete
    case thinkingComplete
    case speakingComplete
    case recognized(user: String)
    case error(message: String)
    
    enum CodingKeys: String, CodingKey {
        case event, text, user, message
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let event = try container.decode(String.self, forKey: .event)
        
        switch event {
        case "listening_started":
            self = .startedListening
        case "thinking_started":
            self = .startedThinking
        case "speaking_started":
            let text = try container.decodeIfPresent(String.self, forKey: .text) ?? ""
            self = .startedSpeaking(text: text)
        case "listening_complete":
            self = .listeningComplete
        case "thinking_complete":
            self = .thinkingComplete
        case "speaking_complete":
            self = .speakingComplete
        case "user_recognized":
            let user = try container.decodeIfPresent(String.self, forKey: .user) ?? "User"
            self = .recognized(user: user)
        case "error":
            let msg = try container.decodeIfPresent(String.self, forKey: .message) ?? "Unknown error"
            self = .error(message: msg)
        default:
            throw DecodingError.dataCorruptedError(forKey: .event, in: container, debugDescription: "Unknown event: \(event)")
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        
        switch self {
        case .startedListening:
            try container.encode("listening_started", forKey: .event)
        case .startedThinking:
            try container.encode("thinking_started", forKey: .event)
        case .startedSpeaking(let text):
            try container.encode("speaking_started", forKey: .event)
            try container.encode(text, forKey: .text)
        case .listeningComplete:
            try container.encode("listening_complete", forKey: .event)
        case .thinkingComplete:
            try container.encode("thinking_complete", forKey: .event)
        case .speakingComplete:
            try container.encode("speaking_complete", forKey: .event)
        case .recognized(let user):
            try container.encode("user_recognized", forKey: .event)
            try container.encode(user, forKey: .user)
        case .error(let message):
            try container.encode("error", forKey: .event)
            try container.encode(message, forKey: .message)
        }
    }
}

// MARK: - Animation Configuration

struct AnimationConfig {
    static let idleAnimationDuration: Double = 0.8
    static let listeningAnimationDuration: Double = 0.5
    static let thinkingAnimationDuration: Double = 1.0
    static let speakingAnimationDuration: Double = 0.4
    
    // Cat model scale
    static let catScale: Float = 1.0
    
    // Window settings
    static let windowWidth: CGFloat = 450
    static let windowHeight: CGFloat = 500
    static let transparency: Double = 0.95
    
    // Speech bubble
    static let speechBubbleDuration: Double = 3.0
    
    // Backend
    static let backendURL = URL(string: "http://127.0.0.1:8000")!
    static let eventListenerPath = "/events/subscribe"
}

// MARK: - Idle Behavior Configuration

struct IdleAnimationVariation {
    let name: String
    let duration: Double
    let frequency: Double // How often (seconds between occurrences)
    
    static let all = [
        IdleAnimationVariation(name: "blink", duration: 0.3, frequency: 3.0),
        IdleAnimationVariation(name: "tail_wag", duration: 1.0, frequency: 5.0),
        IdleAnimationVariation(name: "head_tilt", duration: 0.8, frequency: 7.0),
        IdleAnimationVariation(name: "paw_lick", duration: 1.2, frequency: 10.0),
        IdleAnimationVariation(name: "stretch", duration: 1.5, frequency: 15.0),
        IdleAnimationVariation(name: "yawn", duration: 0.9, frequency: 20.0),
    ]
}
