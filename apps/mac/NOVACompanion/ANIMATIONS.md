# NOVA Cat Avatar — Animation Reference

A complete guide to the 3D Persian cat companion animations and state machine.

## State Machine

```
┌─────────────┐
│    IDLE     │◄─────────────────────┐
└──────┬──────┘                       │
       │                              │
       ├─► LISTENING ────►IDLE ───────┤
       │                              │
       ├─► THINKING ─────►IDLE ───────┤
       │                              │
       ├─► SPEAKING ─────►IDLE ───────┤
       │                              │
       ├─► SLEEPING                   │
       │                              │
       ├─► HAPPY ───────►IDLE ───────┤
       │                              │
       └─► CONFUSED ────►IDLE ────────┘
```

## Animation Catalog

### 1. IDLE (Default State)

Randomly plays ambient animations:

| Animation | Duration | Frequency | Description |
|-----------|----------|-----------|-------------|
| **Blink** | 0.3s | 3s | Eyes close and open (natural blinking) |
| **Tail Wag** | 1.0s | 5s | Tail swishes left-right-center |
| **Head Tilt** | 0.8s | 7s | Head tilts side to side (curious) |
| **Paw Lick** | 1.2s | 10s | Lifts paw and licks (grooming) |
| **Stretch** | 1.5s | 15s | Full body stretch (yawning) |
| **Yawn** | 0.9s | 20s | Opens mouth wide |

**Behavior**: No animation repeats consecutively. Smooth transitions between variations.

**Audio Cue** (optional): Soft purring sound

### 2. LISTENING

Cat pays attention when user is speaking.

**Animations**:
- Head tilts toward voice source
- Eyes widen (engaged)
- Ears perk up
- Slight body lean

**Duration**: Until `listening_complete` event

**Visual**: Cat looks directly at camera/microphone

### 3. THINKING

Cat processes user input or LLM inference.

**Animations**:
- Slow tail swish (left-right, slower than idle)
- Head tilt with slight rotation
- Eyes look upward
- Ears twitch occasionally
- Subtle breathing motion

**Duration**: Until `thinking_complete` event

**Audio Cue** (optional): Soft thinking sound (film strip sound)

**Variations**:
- **Quick think** (< 1s): Smaller head movements
- **Long think** (> 3s): More elaborate tail and ear movements

### 4. SPEAKING

Cat "talks" while delivering response.

**Animations**:
- Mouth movement (jaw bobbing with speech)
- Ear twitches synchronized to speech rhythm
- Eye blinks timed to sentence breaks
- Occasional head tilts for emphasis
- Tail gentle swish

**Duration**: Driven by TTS audio duration

**Speech Bubble**: Text appears above head

**Audio Cue**: TTS voice output

**Lip-Sync** (future): Mouth opens/closes with phonemes

### 5. SLEEPING

Cat rests (triggered by idle timeout or user action).

**Animations**:
- Body curls up (scale down slightly)
- Eyes close (subtle animation)
- Tail wraps around body
- Gentle breathing motion
- Head rests on body

**Duration**: Until user interaction or `wake_up` event

**Audio Cue** (optional): Soft snoring

**Exit**: Any loud sound or user interaction wakes cat

### 6. HAPPY

Cat celebrates achievements or recognizes user.

**Animations**:
- Jump up (upward movement + scale)
- Spin mid-air (360° rotation)
- Land softly
- Tail wag intensely
- Full-body wiggle

**Duration**: 1-2 seconds

**Audio Cue**: Excited "meow" sound

**Triggers**:
- User recognized
- Task completed
- User says praise ("Good job!", "Thank you!")

### 7. CONFUSED

Cat shows puzzlement or error state.

**Animations**:
- Head shakes (side-to-side)
- Ears flatten (uncertain)
- Eyes squint/blink rapidly
- Tail droops slightly
- Slight step backward

**Duration**: 1-2 seconds

**Audio Cue** (optional): Confused "chirp" sound

**Triggers**:
- Backend error
- Command not understood
- API failure

---

## Animation Properties

### Head Movements
```swift
// Tilt left/right (in radians)
eulerAngles.y = ±0.2 to 0.3

// Look up/down
eulerAngles.x = ±0.1 to 0.2

// Head roll
eulerAngles.z = ±0.1 to 0.15
```

### Body Scaling
```swift
// Stretch
scale = 1.15 (up) → 1.0 (down)

// Curl
scale = 0.95 (down) → 1.0 (normal)

// Crouch
moveBy(x: 0, y: -0.1, z: 0)
```

### Tail Rotation
```swift
// Wag (side-to-side)
eulerAngles.z = -0.3 to 0.3

// Curl (up)
eulerAngles.x = 0.5 to 0.8

// Drop (sad)
eulerAngles.x = -0.3 to -0.1
```

### Eye Expressions
```
Open:  Scale = 1.0 (normal geometry)
Blink: Scale = 0.1 to 0.0 (close) then back to 1.0
Happy: Scale = 1.2 (eyes bigger, more expressive)
Sad:   Scale = 0.8 (eyes smaller, droopy)
```

---

## Animation Timing

### Fast Animations (User Feedback)
- Blink: 0.3s
- Ear twitch: 0.2s
- Eye open/close: 0.2s

### Medium Animations (Ambient)
- Head tilt: 0.4-0.8s
- Tail wag: 0.8-1.2s
- Paw lick: 1.2s

### Slow Animations (State Change)
- Stretch/yawn: 1.5s
- Sleep curl: 1.0s
- Happy spin: 0.5s + movement

### Continuous Animations (During State)
- Thinking: 1.0s loop (repeats)
- Speaking: 0.4s loop (synced to speech)
- Listening: 0.5s loop (repeats)

---

## Blending & Transitions

### Smooth Transitions
All animations fade in/out smoothly using `SCNAction` sequences:

```swift
// Transition example
let transition = SCNAction.sequence([
    SCNAction.moveBy(x: 0, y: 0.05, z: 0, duration: 0.2),  // Ease in
    SCNAction.moveBy(x: 0, y: -0.05, z: 0, duration: 0.2)  // Ease out
])
```

### No Jarring Movements
- Always return to neutral position at animation end
- Movement + rotation happen simultaneously (natural)
- Never teleport or snap to position

---

## Integration Points

### From Voice Pipeline
```python
# services/voice/pipeline.py

async def process_audio(audio_frame):
    # User started speaking
    await cat_broadcaster.user_started_listening()
    
    # Transcribe
    text = stt(audio_frame)
    
    # User finished speaking
    await cat_broadcaster.user_stopped_listening()
    
    # Brain processing
    await cat_broadcaster.started_thinking()
    response = await brain.generate_response(text)
    await cat_broadcaster.finished_thinking()
    
    # Synthesize and speak
    await cat_broadcaster.started_speaking(response)
    await tts.speak(response)
    await cat_broadcaster.finished_speaking()
```

### From Brain/LLM
```python
# services/brain/engine.py

async def generate_response(self, query: str):
    await cat_broadcaster.started_thinking()
    
    try:
        response = await llm.generate(query)
        await cat_broadcaster.finished_thinking()
        return response
    except Exception as e:
        await cat_broadcaster.show_confusion(str(e))
        await cat_broadcaster.finished_thinking()
        return "I'm confused, could you repeat that?"
```

### From Recognition
```python
# services/gateway/routes.py

@router.post("/voice/recognize")
async def recognize(audio: bytes):
    await cat_broadcaster.user_started_listening()
    
    speaker_id = identify_speaker(audio)
    if speaker_id:
        await cat_broadcaster.user_recognized(speaker_id.name)
        await cat_broadcaster.show_happiness()
    
    await cat_broadcaster.user_stopped_listening()
```

---

## Customization

### Adjust Animation Speed
Edit `AnimationConfig.swift`:

```swift
struct AnimationConfig {
    static let idleAnimationDuration: Double = 0.8  // ← Change here
    static let speakingAnimationDuration: Double = 0.4  // ← Or here
}
```

### Add New Animation
Edit `AnimationController.swift`:

```swift
private func playCustomAnimation(node: SCNNode) {
    let moveUp = SCNAction.moveBy(x: 0, y: 0.1, z: 0, duration: 0.3)
    let moveDown = SCNAction.moveBy(x: 0, y: -0.1, z: 0, duration: 0.3)
    let sequence = SCNAction.sequence([moveUp, moveDown])
    node.runAction(sequence)
}

// Add to idle variations:
IdleAnimationVariation(name: "custom", duration: 0.6, frequency: 10.0)
```

### Change Cat Colors
Edit `setupProceduralCat()`:

```swift
// Original orange
head.firstMaterial?.diffuse.contents = NSColor(red: 1.0, green: 0.65, blue: 0.0, alpha: 1.0)

// Change to gray
head.firstMaterial?.diffuse.contents = NSColor(red: 0.5, green: 0.5, blue: 0.5, alpha: 1.0)

// Or load color from model
```

---

## Performance

### Frame Rate
- Target: 60 FPS (configurable)
- Animations run smooth even on older Macs

### Model Requirements
- **Polygon count**: 5k–50k triangles (optimal)
- **Bones/Rigging**: Not required (SceneKit handles transformations)
- **Texture resolution**: 1k–2k px (good balance)

### Optimization Tips
1. Use simplified models for idle animations
2. Reduce animation frequency if CPU is high
3. Cache animation sequences
4. Use LOD (Level of Detail) if available

---

## Audio Synchronization

### Speech Sync
```swift
// TTS drives animation duration
await cat_broadcaster.started_speaking(text: response, duration: audio_duration)

// Speaking animations loop for that duration
playSpeakingAnimation()
```

### Future: Lip-Sync
```swift
// Will analyze audio phonemes and sync mouth movement
// Requires: Audio analysis library + mouth bone rigging
```

---

## Testing Animations

### Manual Trigger (Development)
Edit `AnimationController.swift` in `startIdleAnimation()`:

```swift
// Uncomment to test specific animations:

// DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
//     self.transitionTo(.listening())
// }

// DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
//     self.transitionTo(.thinking())
// }

// DispatchQueue.main.asyncAfter(deadline: .now() + 8.0) {
//     self.transitionTo(.speaking(text: "Hello!", duration: 3.0))
// }
```

### API Trigger (Production)
```bash
# From Python backend or curl:

curl -X POST http://127.0.0.1:8000/avatar/animate \
  -H "Content-Type: application/json" \
  -d '{"event": "speaking_started", "text": "Hello friend!"}'
```

---

## Next Steps

1. ✅ Download Persian cat model
2. ✅ Add to Xcode project
3. ✅ Build & run
4. ⏳ Fine-tune animation timing
5. ⏳ Add sound effects (meow, purr, thinking sounds)
6. ⏳ Implement lip-sync
7. ⏳ Add emotions (not just states)
8. ⏳ Integrate with backend events

---

**Created**: 2026-07-31  
**Status**: Phase 2 — Avatar Engine  
**Next Review**: After first model integration
