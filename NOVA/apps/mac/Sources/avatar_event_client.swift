import Foundation

enum JSONValue: Codable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .number(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .null:
            try container.encodeNil()
        }
    }
}

struct AvatarEnvelope: Codable {
    let event: String
    let state: String
    let timestamp: String
    let payload: [String: JSONValue]?
}

private struct AvatarSnapshot: Codable {
    let state: String
}

final class AvatarEventClient {
    private let url: URL
    private var task: Task<Void, Never>?
    private let decoder = JSONDecoder()

    init(streamURL: URL = URL(string: "http://127.0.0.1:8000/avatar/events")!) {
        self.url = streamURL
    }

    func start(
        onEvent: @escaping (AvatarEnvelope) -> Void,
        onConnectionChange: @escaping (Bool) -> Void = { _ in }
    ) {
        stop()
        task = Task {
            await runStreamLoop(onEvent: onEvent, onConnectionChange: onConnectionChange)
        }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    private func runStreamLoop(
        onEvent: @escaping (AvatarEnvelope) -> Void,
        onConnectionChange: @escaping (Bool) -> Void
    ) async {
        while !Task.isCancelled {
            onConnectionChange(false)
            await consumeSSE(onEvent: onEvent, onConnectionChange: onConnectionChange)

            if Task.isCancelled {
                return
            }

            // Keep reconnect delays short so the avatar state feels live.
            try? await Task.sleep(nanoseconds: 1_500_000_000)
        }
    }

    private func consumeSSE(
        onEvent: @escaping (AvatarEnvelope) -> Void,
        onConnectionChange: @escaping (Bool) -> Void
    ) async {
        var request = URLRequest(url: url)
        request.timeoutInterval = 300
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")

        do {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            guard let http = response as? HTTPURLResponse, (200 ... 299).contains(http.statusCode) else {
                print("AvatarEventClient unexpected response")
                return
            }

            onConnectionChange(true)
            var eventName: String?
            var dataLines: [String] = []

            for try await line in bytes.lines {
                if Task.isCancelled {
                    return
                }

                if line.isEmpty {
                    if let name = eventName, !dataLines.isEmpty {
                        let body = dataLines.joined(separator: "\n")
                        handleFrame(event: name, data: body, onEvent: onEvent)
                    }
                    eventName = nil
                    dataLines.removeAll(keepingCapacity: true)
                    continue
                }

                if line.hasPrefix("event: ") {
                    eventName = String(line.dropFirst(7))
                } else if line.hasPrefix("data: ") {
                    dataLines.append(String(line.dropFirst(6)))
                }
            }
        } catch {
            if !Task.isCancelled {
                print("AvatarEventClient stream ended: \(error)")
            }
        }
    }

    private func handleFrame(event: String, data: String, onEvent: (AvatarEnvelope) -> Void) {
        guard event != "ping", let payload = data.data(using: .utf8) else {
            return
        }

        if event == "snapshot" {
            do {
                let snapshot = try decoder.decode(AvatarSnapshot.self, from: payload)
                onEvent(
                    AvatarEnvelope(
                        event: "snapshot",
                        state: snapshot.state,
                        timestamp: ISO8601DateFormatter().string(from: Date()),
                        payload: nil
                    )
                )
            } catch {
                print("AvatarEventClient snapshot decode error: \(error)")
            }
            return
        }

        do {
            let envelope = try decoder.decode(AvatarEnvelope.self, from: payload)
            onEvent(envelope)
        } catch {
            print("AvatarEventClient decode error: \(error)")
        }
    }
}
