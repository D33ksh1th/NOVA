# NOVA Backend System Overview

This document explains what has been built so far in NOVA backend, why each technology is used, and how the major intelligence pipelines connect.

## 1. What NOVA Is

NOVA is a multi-service AI assistant stack with:
- conversational reasoning,
- voice input/output,
- system and device awareness,
- memory and planning support,
- real-time UI event streaming.

The backend is designed as service modules connected through a central registry and an event bus.

## 2. Core Architecture

Main layers:
- API Gateway: FastAPI routes for chat, voice, avatar events, settings, health.
- Service Registry: constructs and wires all singleton services.
- Brain/Conversation: intent understanding, planning, response generation.
- Voice Engine: wake/listen/think/speak orchestration.
- Tools + Skills: system actions, data lookup, terminal/file/vision capabilities.
- Event Stream: pushes state transitions to frontend avatar/UI.

Primary files:
- `services/gateway/routes.py`
- `packages/registry/registry.py`
- `services/brain/*`
- `services/voice/*`
- `services/tools/*`

## 3. Why These Technologies

- FastAPI:
  - clear async API layer,
  - strong schema validation with Pydantic,
  - easy integration with SSE and service methods.

- Pydantic models:
  - typed request/response contracts,
  - safer frontend-backend integration.

- Event bus + avatar stream:
  - decouples backend logic from rendering,
  - allows realtime UI transitions (`listening`, `thinking`, `speaking`, `idle`).

- Provider-pluggable voice stack:
  - supports different STT/TTS backends (Whisper, Piper, Kokoro, system),
  - keeps orchestration stable while swapping providers.

- Structured tool system:
  - enables deterministic capabilities (Bluetooth, files, terminal, weather, etc.),
  - lets reasoning layer delegate concrete tasks.

## 4. Request Flow (High Level)

### 4.1 Chat flow
1. Frontend calls `/chat`.
2. Gateway sends message to `ConversationService`.
3. Brain performs intent + strategy + optional planning.
4. Response payload is returned (`response`, `intent`, `action`, optional `steps`, `data`).
5. Frontend renders text + structured detail panels.

### 4.2 Voice text flow
1. Frontend calls `/voice/text`.
2. VoiceEngine resolves voice preferences.
3. VoicePipeline performs listening/recognition/wake handling and conversation handoff.
4. If enabled, TTS is synthesized and played.
5. Avatar events are published across the lifecycle.

### 4.3 Voice speak/stop flow
- `/voice/speak`: explicit speak command via selected TTS backend.
- `/voice/stop`: best-effort cancellation of active playback/TTS processes and avatar reset to `idle`.

## 5. Voice Subsystem Design

Key components:
- `VoiceEngine`: policy, preferences, lifecycle state.
- `VoicePipeline`: orchestrates VAD, STT, wakeword, conversation, speech plan, TTS.
- `SpeechSynthesizer` (and provider implementations): audio generation/playback.
- `WakeWordDetector`, `SpeechRecognizer`, `VoicePlayer`.

State progression:
- `idle -> listening -> thinking -> speaking -> idle`

Frontend and backend both reflect this lifecycle so the user can see and control voice behavior.

## 6. Device and Connectivity Telemetry

Endpoint:
- `/devices/connected`

Snapshot currently includes:
- `power`: charger source, charging state, battery percentage.
- `wifi`: connected/interface/SSID (or hidden state when macOS redacts SSID).
- `bluetooth`: connected devices + battery where available.
- `wired_external`: USB and wired audio external devices.

Why this exists:
- Allows dynamic right-panel telemetry in UI.
- Supports proactive assistant behavior based on machine context.

## 7. Memory and Knowledge Model

NOVA combines:
- memory services (`services/memory/*`) for persistent context,
- skill/tool execution for grounded responses,
- planner and reflection layers for multi-step quality.

Conceptually:
1. User input enters Brain.
2. Intent classifier and decision engine select strategy.
3. Planner and tool manager are invoked when needed.
4. Response synthesis combines model reasoning + tool outputs.
5. Memory updates and reflection can refine future behavior.

This is not a single monolithic "knowledge model"; it is an orchestrated reasoning pipeline over memory, tools, and model outputs.

### 7.1 Brief: How Memory, Context, and Information Are Structured

At runtime, NOVA treats data in three practical buckets:

- Memory (longer-lived):
  - user/project facts and prior useful outcomes,
  - stored so future turns can reuse decisions and reduce repetition.

- Context (turn-scoped + session-scoped):
  - current message, recent conversation, active page/task state, voice/device signals,
  - refreshed each turn and weighted more heavily than older memory.

- Information (grounded live data):
  - tool outputs such as system status, Bluetooth/Wi-Fi/power telemetry, files, terminal results,
  - treated as source-of-truth for operational answers.

How NOVA uses them per turn:
1. Build context package from current input + recent thread.
2. Pull relevant memory entries that match intent/goal.
3. Execute tools only when live information is needed.
4. Merge context + memory + tool evidence in Brain reasoning.
5. Return response and metadata; then persist useful outcomes back to memory.

In short: context drives the current turn, memory gives continuity, and tool information provides real-world accuracy.

## 8. "Neuron" Connectivity Mental Model

NOVA can be thought of as connected functional neurons:

- Input neurons:
  - HTTP requests, voice transcripts, system events.

- Perception neurons:
  - intent detection, wake detection, language/emotion/speaker cues.

- Reasoning neurons:
  - brain engine, planner, decision logic, reflection.

- Action neurons:
  - tools, terminal/file/vision/system actions.

- Expression neurons:
  - chat response text, TTS audio, avatar state events.

- Memory neurons:
  - context storage and recall that influence later turns.

Each neuron group is separated by service interfaces so the system stays maintainable and replaceable.

## 9. Current Frontend-Visible Behaviors Delivered

Implemented from this phase:
- manual mic listen path,
- wake listener stability improvements,
- speak-back and stop-speaking controls,
- global speech-text cleanup,
- structured details rendering for system responses,
- dynamic connections card (Wi-Fi/Bluetooth/wired/power),
- low battery warning in UI when below threshold.

## 10. Known Constraints

- macOS may redact SSID in CLI output (`<redacted>`) without required privacy permissions.
- Some device metadata (battery/vendor/transport) depends on what the OS exposes.
- TTS stop is best-effort because provider processes differ.

## 11. Recommended Next Backend Improvements

1. Add auth-safe system telemetry cache with timestamps and confidence flags.
2. Add dedicated diagnostics endpoint for voice pipeline component health.
3. Add explicit capability flags in `/devices/connected` response for UI certainty.
4. Add tests around parser edge cases (`pmset`, `system_profiler`, `ipconfig`).
5. Add uniform error envelopes for all gateway routes.
