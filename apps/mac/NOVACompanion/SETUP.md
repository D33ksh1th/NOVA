# NOVA Companion Setup Guide (Xcode)

## Quick Setup (5 minutes)

### Step 1: Create Xcode Project

```bash
cd /Users/Deekshith.Kr/Downloads/api\ test/NOVA/apps/mac/NOVACompanion

# Create folder structure if needed
mkdir -p Models Controllers Views Assets/Models Assets/Sounds
```

### Step 2: In Xcode

1. **File → New → Project**
2. Select: **macOS → App**
3. Configure:
   - Product Name: `NOVACompanion`
   - Team: (your team or None)
   - Organization Identifier: `com.nova.companion`
   - Language: **Swift**
   - SwiftUI: **Yes**
   - Core Data: **No**
   - Tests: **No**

4. Save to: `/Users/Deekshith.Kr/Downloads/api\ test/NOVA/apps/mac/NOVACompanion`

### Step 3: File Structure

```
NOVACompanion/
├── NOVACompanionApp.swift
├── Models/
│   └── AvatarState.swift
├── Controllers/
│   └── AnimationController.swift
├── Views/
├── Assets/
│   └── Models/
│       └── cat.usdz  (⬅️ ADD YOUR 3D MODEL HERE)
└── Info.plist
```

### Step 4: Add Files to Xcode

1. In Xcode: **File → Add Files to Project**
2. Select:
   - `Models/AvatarState.swift`
   - `Controllers/AnimationController.swift`
3. ✅ Copy if needed
4. Add to target: ✅ `NOVACompanion`

### Step 5: Get a Cat Model

#### Option A: Download from Sketchfab (Free)

1. Go to https://sketchfab.com
2. Search: "Persian cat" or "orange cat"
3. Filter by: **Downloadable** 
4. Download as **.glb**

#### Option B: AI Generated Model

Use **Meshy.ai** or **Tripo3D**:
- Prompt: "Orange fluffy Persian cat sitting, rigged for animation, cute style"
- Download as `.glb`

#### Option C: Quick Test Model

If no model available, the app has a **procedural cat fallback** (geometric shapes). It still animates!

### Step 6: Convert Model to USDZ

If you have a `.glb` file:

**Method 1: Xcode Preview (Easiest)**
```bash
# In Terminal, place .glb file in Assets/Models/
cd "/Users/Deekshith.Kr/Downloads/api test/NOVA/apps/mac/NOVACompanion/Assets/Models"

# Convert .glb to .usdz using a Python script or online tool:
# https://product.vimeo.com/tools/web-glb-viewer → Export → .usdz
```

**Method 2: Command Line (if you have conversion tools)**
```bash
# Using Blender (if installed)
blender --background cat.glb --python-script convert_to_usdz.py

# Or online: https://convertio.co/glb-usdz/
```

**Method 3: Reality Composer (Xcode Tool)**
- Xcode 12+ has built-in .glb → .usdz conversion
- Drag .glb into Reality Composer
- Export as .usdz

### Step 7: Add Model to Xcode

1. In Finder: Drag `cat.usdz` into Xcode project
2. Options:
   - ✅ Copy if needed
   - ✅ Add to target: `NOVACompanion`

### Step 8: Update Info.plist

Add these keys:

```xml
<key>NSWindowStyleMaskKey</key>
<true/>
<key>NSHighResolutionCapable</key>
<true/>
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsArbitraryLoads</key>
    <true/>
    <key>NSExceptionDomains</key>
    <dict>
        <key>127.0.0.1</key>
        <dict>
            <key>NSIncludesSubdomains</key>
            <true/>
            <key>NSTemporaryExceptionAllowsInsecureHTTPLoads</key>
            <true/>
        </dict>
    </dict>
</dict>
```

### Step 9: Build & Run

```bash
# In Terminal
cd "/Users/Deekshith.Kr/Downloads/api test/NOVA/apps/mac/NOVACompanion"
xcodebuild -scheme NOVACompanion
```

Or: **Cmd+R** in Xcode

## Troubleshooting

### ❌ "cat.usdz not found"

The app will use a **procedural fallback cat** (geometric shapes). It still animates perfectly!

To add a model later:
1. Get a model from Sketchfab
2. Convert to .usdz
3. Add to Xcode Assets
4. Rebuild

### ❌ "Backend connection failed"

The app will show **"Offline"** indicator but still work! You can:

1. Click **Voice Type dropdown** in Flutter panel → Select "Cat"
2. Cat will respond to voice events
3. To enable real-time animation: Make sure NOVA backend is running
   ```bash
   cd /Users/Deekshith.Kr/Downloads/api\ test/NOVA
   source venv/bin/activate
   python3 scripts/run.py
   ```

### ❌ "Crash on launch"

Check:
1. macOS 11.0+ (Xcode will warn if too old)
2. Swift 5.5+ (Xcode has this by default)
3. Console.app shows details (Cmd+Space → Console)

## Testing the Cat

### Without Backend

The cat will still animate in idle mode:
- ✅ Blink
- ✅ Tail wag
- ✅ Head tilt
- ✅ Stretch
- ✅ Yawn

### With Backend Running

Edit `AnimationController.swift` to test events manually:

```swift
// Add this in startIdleAnimation() for testing:
DispatchQueue.main.asyncAfter(deadline: .now() + 3.0) {
    self.transitionTo(.thinking(duration: 2.0))
}

DispatchQueue.main.asyncAfter(deadline: .now() + 6.0) {
    self.transitionTo(.speaking(text: "Hello! I'm your NOVA companion.", duration: 4.0))
}
```

Then rebuild (Cmd+R).

## Next Steps

- [ ] Download a Persian cat model from Sketchfab
- [ ] Convert to .usdz
- [ ] Add to Xcode project
- [ ] Build & run
- [ ] Test animations by triggering backend events
- [ ] Add more animations (sleeping, happy, hungry)
- [ ] Integrate with Flutter panel (window communication)
- [ ] Add lip-sync with TTS

## Tips

1. **Window stays on top**: Edit `NOVACompanionApp.swift` → `window.level = .floating`
2. **Draggable**: Already enabled via `isMovableByWindowBackground = true`
3. **Transparent**: Background is `.clear` (no white window)
4. **Model quality**: Anything 5k–50k triangles works well (50k+ might be slow)

---

**Questions?** Check `README.md` or `AnimationController.swift` comments.
