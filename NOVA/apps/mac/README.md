# NOVA mac Companion (Phase 2 Starter)

This folder now contains a macOS SwiftUI + SceneKit companion scaffold that subscribes to the backend avatar event stream and animates a 3D cat state machine.

## Included files

- Sources/NOVACompanionApp.swift: app entry point.
- Sources/CompanionRootView.swift: desktop companion shell UI.
- Sources/CompanionViewModel.swift: event-to-state orchestration.
- Sources/CompanionSceneView.swift: SceneKit renderer + animations.
- Sources/AvatarVisualState.swift: canonical runtime states.
- Sources/avatar_event_client.swift: SSE client with reconnect and snapshot support.

## Event mapping

- listening_started -> listening
- thinking_started -> thinking
- speaking_started -> speaking
- listening_completed/thinking_completed/speaking_completed/idle -> idle

## Persian cat model loading

The scene controller attempts to load a real model first, then falls back to a procedural placeholder cat if not found.

Supported model filenames:

- assets/character/persian_cat.usdz
- assets/character/persian_cat.scn
- assets/character/persian_cat.dae
- assets/character/cat.usdz
- assets/character/cat.scn
- assets/character/cat.dae

If needed, set NOVA_ROOT to your repository root so model lookup is deterministic.

## Backend dependency

The companion expects the stream endpoint to be live:

- http://127.0.0.1:8000/avatar/events

## Run locally

This folder is now a Swift Package with an executable target.

1. Open in Xcode:
	- From terminal: `open Package.swift`
	- Choose the `NOVACompanion` scheme and run.
2. Or run from terminal:
	- `swift run NOVACompanion`

If model auto-detection fails, set `NOVA_ROOT` to the repository root before launching.

## Floating window behavior

The companion now starts with desktop-assistant style window behavior:

- Transparent window background.
- Always-on-top level.
- Drag by background.
- Hidden traffic-light buttons.
- Visible across spaces and as fullscreen auxiliary.

## Better interaction (new)

If no Persian model is auto-detected, use the in-app controls:

- `Load Model`: pick any local `.usdz`, `.scn`, or `.dae` file.
- `Rotate <-` / `Rotate ->`: orbit the cat quickly.
- `Zoom +` / `Zoom -`: adjust view distance.
- `Reset Cam`: snap back to default framing.
- `Idle / Listen / Think / Speak`: preview animations without waiting for backend events.

The status line below controls shows whether a real model or fallback is active.

You can test transitions from terminal:

curl -X POST http://127.0.0.1:8000/avatar/emit -H "Content-Type: application/json" -d '{"event":"listening_started","payload":{"source":"manual"}}'
curl -X POST http://127.0.0.1:8000/avatar/emit -H "Content-Type: application/json" -d '{"event":"thinking_started","payload":{"source":"manual"}}'
curl -X POST http://127.0.0.1:8000/avatar/emit -H "Content-Type: application/json" -d '{"event":"speaking_started","payload":{"source":"manual"}}'
curl -X POST http://127.0.0.1:8000/avatar/emit -H "Content-Type: application/json" -d '{"event":"idle","payload":{"source":"manual"}}'
