# NOVA Avatar Engine — Phase B

This phase intentionally shifts from geometry-first work to character-system architecture.

## Goal

Build a production-style avatar engine that can host the final Blender character without refactoring core runtime behavior.

## Character Bible Anchors

- Name: NOVA
- Species: Persian Cat
- Personality ratio: 80% calm, 10% playful, 10% humorous
- Emotional style: body-language first, no exaggerated cartoon facial spam
- Runtime mood baseline: respectful, confident, supportive, curious

## Implemented In This Phase

### 1) Controller Architecture

Implemented under src/avatar/controller:

- AvatarEngine.ts: top-level orchestrator
- AvatarController.ts: reducer that merges all controller outputs
- EventBus.ts: typed event dispatch
- StateMachine.ts: event to state transitions
- AnimationController.ts: clip override resolver
- BehaviorController.ts: idle behavior scheduling decisions
- EmotionController.ts: event to emotion mapping
- SpeechBubbleController.ts: speech lifecycle
- LipSyncController.ts: viseme frame scaffolding
- EyeTrackingController.ts: target routing
- IdleScheduler.ts: periodic idle ticks

### 2) Stream Integration

useAvatarStream now routes SSE events into AvatarEngine.

- Incoming events feed engine.ingest(event, payload)
- Engine emits snapshots containing:
  - state
  - emotion
  - speechText
  - animationOverride
  - eyeTarget
- Snapshot fields are written to avatar store in one flow

### 3) Character and Shader Stubs

Implemented module placeholders for the final rigged model integration:

- src/avatar/Character/Materials.ts
- src/avatar/Character/Eyes.ts
- src/avatar/Character/Face.ts
- src/avatar/Character/Tail.ts
- src/avatar/Character/Accessories.ts
- src/avatar/Animations/*.ts
- src/avatar/Shaders/*.ts

These are intentionally lightweight and define contracts, not final visuals.

## Event Contract (Current)

Engine supports:

- snapshot
- thinking_started / thinking_finished
- listening_started / listening_finished
- response_started / response_finished
- speaking_started / speaking_finished
- sleep_started / sleep_finished
- user_arrived
- task_completed
- good_morning
- good_night
- idle_tick

Legacy aliases are normalized:

- thinking_completed -> thinking_finished
- listening_completed -> listening_finished
- speaking_completed -> speaking_finished

## Why This Phase Matters

With this architecture in place, Blender and animation work can progress independently:

- Model/rig team can iterate without touching event plumbing.
- Voice/lip-sync can evolve without changing viewport logic.
- Behavior can become advanced (behavior tree) without store rewrites.

## Next Phase (Recommended)

Phase C: Character Bible + Concept Turnarounds + Rig Contracts

1. Lock final NOVA concept (front, side, back, 3/4).
2. Finalize rig hierarchy and blendshape naming contract.
3. Export first rigged GLB with partial animation set.
4. Bind shader/material pipeline to final mesh slots.
5. Connect lip-sync from real audio visemes, replacing placeholder mapping.
