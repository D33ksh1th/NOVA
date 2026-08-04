# NOVA Companion — macOS 3D Avatar

A floating 3D Persian cat companion for your Mac that responds to NOVA backend events.

## Features

- **Floating transparent window** with draggable 3D cat
- **Event-driven animations** (Idle, Listening, Thinking, Speaking)
- **Real-time sync** with Python/FastAPI backend
- **Speech bubbles** with text responses
- **Ambient animations** (blinking, tail wag, head tilt)

## Getting Started

### Requirements

- macOS 11.0+
- Xcode 13+
- Swift 5.5+

### Setup

1. **Install dependencies** (via SPM, managed in Xcode)
2. **Add 3D model**:
   - Recommended: [Sketchfab Persian Cat Model](https://sketchfab.com/search?q=persian+cat&type=models)
   - Format: `.glb` or `.usdz`
   - Place in: `NOVACompanion/Assets/Models/cat.usdz`
3. **Build & Run**: `Cmd+R` in Xcode

### 3D Model Recommendations

#### Free/OpenSource:
- **Sketchfab** (https://sketchfab.com)
  - Search: "Persian cat" or "orange cat"
  - License: CC0 or CC-BY
  - Download as `.glb` → Convert to `.usdz` using Xcode preview

- **Poly Haven** (https://polyhaven.com)
  - Free 3D models, good Persian cat options

- **TurboSquid Free** (https://www.turbosquid.com/Search/3D-Models/free)
  - Filter by animal → cat

#### Commercial (if you want custom):
- **CGTrader** (~$20-50 for rigged Persian cat)
- **Artstation** (marketplace)
- **Quaternius** (low-poly cartoon cats, free)

#### AI Generated:
- **Meshy.ai** or **Tripo3D** (AI 3D generation)
- Describe: "Orange fluffy Persian cat sitting, rigged for animation"

### Model Format

1. Download as `.glb`
2. Convert to `.usdz` (Apple's format):
   ```bash
   # Using Reality Composer (Xcode tool)
   # Or open .glb in Preview → Export as .usdz
   ```
3. Place in `Assets/Models/cat.usdz`

### Architecture

```
NOVACompanion/
├── NOVACompanionApp.swift           # Entry point, window setup
├── Models/
│   ├── AvatarState.swift            # State machine (Idle, Listening, Thinking, Speaking)
│   ├── BackendEvent.swift           # Event types from NOVA backend
│   └── AnimationConfig.swift        # Animation parameters
├── Views/
│   ├── CatWindowView.swift          # Main window view (transparent, draggable)
│   └── SpeechBubbleView.swift       # Text bubble overlay
├── Controllers/
│   ├── SceneController.swift        # SceneKit scene setup
│   ├── AnimationController.swift    # Animation state machine & logic
│   └── BackendConnector.swift       # WebSocket/HTTP to NOVA backend
├── Assets/
│   ├── Models/
│   │   └── cat.usdz                 # 3D Persian cat model
│   └── Sounds/
│       └── notification.wav         # Optional bell sound
└── README.md

```

### Event Flow

```
NOVA Backend (Python)
    ↓
REST/WebSocket Event
    ↓
BackendConnector (Swift)
    ↓
AvatarState updates
    ↓
AnimationController
    ↓
SceneKit animations
    ↓
Cat moves/animates
```

### Running

```bash
xcodebuild -project NOVACompanion.xcodeproj -scheme NOVACompanion
```

Or: **Cmd+R** in Xcode.

### Configuration

Edit `AnimationConfig.swift`:
- Animation durations
- Cat size/position
- Window transparency
- Speech bubble duration
- Backend URL (default: http://127.0.0.1:8000)

### Next Steps

- [x] Project structure
- [x] Window & scene setup
- [x] State machine
- [x] Animation controller
- [ ] Backend event listener
- [ ] Polish animations
- [ ] Add more states (Sleeping, Happy, Hungry)
- [ ] Integrate lip-sync with TTS

---

**Author:** NOVA Team  
**Status:** Phase 2 Development  
**Last Updated:** 2026-07-31
