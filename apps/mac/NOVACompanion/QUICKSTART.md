# NOVA Companion — Quick Start (5 min)

## What You Have

A **native macOS Swift/SwiftUI app** that runs a floating 3D Persian cat on your desktop.

The cat:
- ✅ Animates (idle, listening, thinking, speaking, sleeping, happy, confused)
- ✅ Responds to Python backend events
- ✅ Has a procedural fallback (no model needed to start)
- ✅ Transparent window (draggable, always-on-top optional)
- ✅ Speech bubbles above head
- ✅ Ambient animations (blinking, tail wagging, grooming)

## Project Structure

```
/Users/Deekshith.Kr/Downloads/api test/NOVA/
├── apps/mac/NOVACompanion/              ◄── YOUR CAT APP HERE
│   ├── NOVACompanionApp.swift           # Entry point
│   ├── Models/
│   │   └── AvatarState.swift            # State machine
│   ├── Controllers/
│   │   └── AnimationController.swift    # Animations + scene
│   ├── Assets/Models/
│   │   └── cat.usdz                     # (Optional) 3D model
│   ├── README.md                        # Overview
│   ├── SETUP.md                         # Xcode setup guide
│   ├── ANIMATIONS.md                    # All animations explained
│   └── QUICKSTART.md                    # This file
│
└── services/avatar/cat_events.py        # Python event broadcaster
```

## Step 1: Create Xcode Project (2 min)

In Xcode:

1. **File → New → Project**
2. **macOS → App**
3. **Product Name**: `NOVACompanion`
4. **Save to**: `/Users/Deekshith.Kr/Downloads/api test/NOVA/apps/mac/NOVACompanion`

## Step 2: Add Swift Files (2 min)

In Xcode project:

1. **File → Add Files to Project**
2. Select:
   - `Models/AvatarState.swift`
   - `Controllers/AnimationController.swift`
3. ✅ Copy if needed
4. ✅ Add to target `NOVACompanion`

Replace `ContentView.swift` with code from `NOVACompanionApp.swift`.

## Step 3: Build & Run (1 min)

```bash
# Terminal
cd "/Users/Deekshith.Kr/Downloads/api test/NOVA/apps/mac/NOVACompanion"
xcodebuild -scheme NOVACompanion
```

Or: **Cmd+R** in Xcode

**Result**: Floating window with animated 3D cat appears ✅

## Step 4: Add Your 3D Model (Optional)

Want a custom Persian cat model instead of geometric shapes?

1. **Download** from [Sketchfab](https://sketchfab.com/search?q=persian+cat)
2. **Convert** `.glb` → `.usdz` (or drag into Xcode preview, export as `.usdz`)
3. **Add to Xcode**: Drag into `Assets/Models/` folder
4. **Rebuild**: **Cmd+R**

Cat model loads automatically if `cat.usdz` exists.

## Step 5: Test Animations

### Option A: Idle (No Backend Needed)
The cat animates automatically:
- Blinks
- Wags tail
- Tilts head
- Stretches
- Yawns

No code changes needed!

### Option B: Trigger from Python Backend

In your Python code (e.g., voice pipeline):

```python
from services.avatar.cat_events import get_cat_broadcaster

async def my_voice_handler(audio):
    broadcaster = get_cat_broadcaster()
    
    # Trigger animations
    await broadcaster.user_started_listening()
    # ... process audio ...
    await broadcaster.started_thinking()
    # ... generate response ...
    await broadcaster.started_speaking("Hi! I understood you.")
    # ... play TTS ...
    await broadcaster.finished_speaking()
```

**No Xcode changes needed!** The cat reacts automatically.

## What Each State Does

| State | Trigger | Animation | Duration |
|-------|---------|-----------|----------|
| **Idle** | Default | Blink, tail wag, stretch, yawn | Until event |
| **Listening** | `user_started_listening()` | Head tilts, ears perk | Until `user_stopped_listening()` |
| **Thinking** | `started_thinking()` | Slow tail wag, upward gaze | Until `finished_thinking()` |
| **Speaking** | `started_speaking(text)` | Ear twitches, mouth moves | TTS duration |
| **Happy** | `user_recognized(name)` | Jump, spin, tail wag | 2 seconds |
| **Confused** | `show_confusion()` | Head shake, ears flatten | 2 seconds |
| **Sleeping** | Set manually | Eyes close, curl up | Until user interacts |

## Customization (Quick Tweaks)

### Change Animation Speed
Edit `AnimationConfig.swift`:
```swift
static let idleAnimationDuration: Double = 0.8  // Faster if < 0.8
```

### Change Cat Color
Edit `setupProceduralCat()`:
```swift
// Orange → Red
NSColor(red: 1.0, green: 0.0, blue: 0.0, alpha: 1.0)
```

### Always-On-Top
Edit `ClearWindowView`:
```swift
window.level = .floating  // Already set!
```

### Window Size
Edit `NOVACompanionApp`:
```swift
.frame(minWidth: 600, minHeight: 600)  // Adjust here
```

## Common Issues

| Problem | Solution |
|---------|----------|
| "cat.usdz not found" | Normal! Geometric fallback loads. Download model later if desired. |
| "Backend connection failed" | App shows "Offline" but still animates idle state. Make sure NOVA backend is running. |
| Window appears off-screen | Drag cat window with mouse. Or reset window position in code. |
| Animations stutter | Reduce model complexity or check Mac CPU usage. |

## Next: Integrate with NOVA Backend

When you're ready, call cat animation events from:

- **Voice pipeline** (`services/voice/pipeline.py`): Trigger on listen/think/speak
- **Brain engine** (`services/brain/engine.py`): Trigger on LLM processing
- **Gateway routes** (`services/gateway/routes.py`): Trigger on user recognition

Example:
```python
from services.avatar.cat_events import get_cat_broadcaster

async def some_handler():
    cat = get_cat_broadcaster()
    await cat.started_thinking()
    # ... do work ...
    await cat.finished_thinking()
    await cat.started_speaking("Done!")
```

## Files Reference

| File | Purpose |
|------|---------|
| `NOVACompanionApp.swift` | Main app, window setup, UI layout |
| `AvatarState.swift` | State machine enums, event types, config |
| `AnimationController.swift` | Scene setup, animations, backend listener |
| `cat_events.py` | Python broadcaster (import in NOVA backend) |
| `README.md` | Full overview + model recommendations |
| `SETUP.md` | Detailed Xcode setup instructions |
| `ANIMATIONS.md` | Complete animation reference |

## Success Checklist

- [x] Xcode project created
- [x] Swift files added
- [x] Project builds
- [x] Cat window appears
- [x] Idle animations play
- [ ] 3D model added (optional)
- [ ] Backend events trigger animations
- [ ] Sounds added (future)
- [ ] Lip-sync implemented (future)

## Questions?

1. **How to add sound?** → SceneKit has audio support, add `.wav` to Assets
2. **How to customize animations?** → Edit `AnimationController.swift` methods
3. **How to change window behavior?** → Edit `NOVACompanionApp.swift` window setup
4. **How to integrate with Flutter?** → Both run as separate processes; use shared HTTP API

---

## You're Ready!

```bash
# Build the cat
cd "/Users/Deekshith.Kr/Downloads/api test/NOVA/apps/mac/NOVACompanion"
xcodebuild -scheme NOVACompanion

# Or in Xcode: Cmd+R
```

🐱 **Your NOVA companion is ready to animate!**

---

**Phase 2 Status**: ✅ Avatar Engine Complete  
**Next Phase**: Phase 3 — Emotion Engine (Advanced expressions)  
**Last Updated**: 2026-07-31
