# NOVA Companion Character Specification v1.0

## 1) Project Intent
Design a production-ready companion character named NOVA: a realistic yet expressive light-orange Persian cat that serves as the permanent visual identity of the NOVA AI assistant.

This character must sustain long-term user engagement across desktop, web, mobile, and future robotics interfaces.

## 2) Creative North Star
NOVA should feel:
- Warm
- Intelligent
- Trustworthy
- Curious
- Emotionally expressive
- Calm and gently confident

NOVA should not feel:
- Aggressive
- Angry
- Overly cute
- Cartoon mascot-like
- Robotic
- Uncanny

Reference quality target:
- Pixar / DreamWorks readability and emotional clarity
- Riot / high-end real-time game production quality
- Realistic feline anatomy, stylized polish

## 3) Visual Design Language
### Core appearance
- Species: Persian cat
- Fur color: light orange primary coat
- Undercoat: soft cream
- Secondary pattern: subtle tabby flow (very low contrast)
- Chest: white patch
- Paws: white socks
- Tail: thick, fluffy, full volume silhouette
- Face: rounded cheeks, compact muzzle, soft profile arc
- Eyes: large, expressive, green iris with high-spec corneal reflections
- Nose: pink, realistic albedo variation
- Ears: rounded soft triangles with subtle internal peach fur
- Mouth line: faint, neutral-positive expression (not smiling cartoon)

### Accessory design
- Collar: dark navy matte leather/fabric hybrid
- Pendant: small cyan emissive core with restrained glow
- Tag: brushed metal, engraved "NOVA"
- Constraint: no armor, no heavy sci-fi attachments

## 4) Character Personality Through Form
Visual cues to embed:
- Intelligence: focused eye tracking, deliberate head orientation
- Loyalty: attentive sit posture, return-to-user idle behavior
- Calmness: smooth breath rhythm, low-jerk motion arcs
- Curiosity: ear-led direction changes, subtle weight shifts
- Warmth: soft fur breakup, non-threatening gaze
- Gentle humor: occasional micro-tilt and blink timing

## 5) Anatomy and Proportion Targets
- Preserve believable feline skeletal mass distribution
- Slightly enlarged eye region for readability at small viewport sizes
- Head-to-body ratio: realistic Persian bias (compact head, broad chest)
- Shoulder and hip articulation must support sit, lie, walk, stretch, and paw-cleaning poses
- Tail root volume must remain consistent during bends

## 6) Modeling and Topology Requirements
### Geometry constraints
- Topology: quads preferred for deforming areas
- Clean edge loops around:
  - Eyes and eyelids
  - Muzzle / mouth / jaw
  - Shoulder, elbow, wrist
  - Hip, knee, ankle
  - Tail chain joints
- No ngons in deform-critical zones
- Avoid long thin triangles around face and joints

### Poly budget
- LOD0: 50,000 to 100,000 triangles (target hero: ~80,000)
- LOD1: 25,000 to 45,000 triangles
- LOD2: 8,000 to 18,000 triangles

### Groom strategy
- Desktop/console-quality: fur cards + shell breakup where needed
- Web fallback: simplified fur card clusters or baked silhouette normals
- Keep shader and draw-call budget WebGL-friendly

## 7) UV and Texture Specification
### UV
- UV set 0: primary body and accessories
- UV set 1 (optional): lightmap / special masks
- Texel density consistency within visibility tiers
- Symmetry allowed where expressive asymmetry is not required

### PBR texture set (4K master, scalable)
Per material group (body, eyes, nose, collar, pendant, tag):
- BaseColor
- Normal
- Roughness
- Metallic
- AO
- Emissive (pendant only)
- Optional masks: cavity, fuzz, wetness, fur variation

### Eye shading requirements
- Separate cornea and iris geometry/material where possible
- High-frequency normal detail for iris depth
- Physically plausible Fresnel and highlight response

## 8) Rigging Specification
### Skeleton
- Full body hierarchy with stable naming
- Spine chain suitable for breathing and pose offsets
- Neck, head, jaw
- Eye controls (L/R)
- Eyelids (L/R)
- Ears with independent controls (L/R)
- Tail with multi-bone chain (minimum 6 controls, preferred 8 to 12)
- Forelegs/hindlegs with IK/FK compatibility
- Paws and toe controls (simplified acceptable on LODs)
- Optional whisker controls

### Deformation quality
- Preserve cheek volume in jaw open/close
- Prevent shoulder collapse in walk and stretch
- Maintain paw pad silhouette under compression poses
- Tail twist should not candy-wrap

## 9) Facial Blend Shape Set
Required blend shapes:
- Smile
- Frown
- Concern
- Surprised
- Thinking
- Sleepy
- Happy
- Curious
- Blink_Left
- Blink_Right
- Eye_Squint
- Mouth_Open
- Mouth_Closed

Speech visemes (minimum set):
- AA
- E
- I
- O
- U
- FV
- MBP
- L
- WQ
- Rest

Blend shape requirements:
- Additive-safe where possible
- Clean neutral return
- No mesh penetration on eyelids and lips

## 10) Animation Library Requirements
Deliver reusable clips with clean in/out poses.

### Idle and micro-life
- Idle_01
- Idle_02
- Idle_03
- Idle_04
- Blink
- Ear_Twitch
- Tail_Movement
- Look_Around

### Body actions
- Stretch
- Yawn
- Sit
- Lie_Down
- Sleep
- Wake_Up
- Walk
- Run
- Eat
- Drink
- Scratch_Ear
- Clean_Paw

### Interactive / emotion
- Observe_User
- Listen
- Thinking
- Talking
- Celebrate
- Happy_Jump
- Confused
- Concerned
- Tail_Wag

### Clip standards
- Preferred sample rate: 30 fps
- Root motion policy: explicit (in-place + root-motion variant for locomotion)
- Loopable idles must match first/last pose velocity
- Naming convention: NOVA_<Action>_<Variant>

## 11) Emotion System Compatibility
NOVA must support these runtime states:
- Happy
- Concerned
- Curious
- Excited
- Focused
- Listening
- Thinking
- Speaking
- Sleeping
- Relaxed
- Proud
- Shy

Each state should modulate:
- Ear pose and twitch rate
- Tail amplitude and frequency
- Blink cadence
- Head tilt bias
- Eye aperture
- Breathing amplitude
- Voice pacing compatibility hooks

## 12) Behavior Compatibility Contracts
Character must support runtime behaviors:
- Walk toward user focus point
- Cursor-driven eye tracking
- Head tracking (camera/mic target)
- Desktop observation idles
- Sleep at cushion/bowl area
- Eat + post-sleep stretch
- Speak-reactive micro motions

Motion quality target:
- Non-repetitive timing offsets
- Layered subtle loops over base states
- No deterministic robotic cycle feel

## 13) Environment Prop Set
Create matching assets:
- Cat bowl
- Sleeping cushion
- Small rug
- Minimal wooden platform
- Small holographic projector

Constraints:
- Cohesive style with NOVA character
- PBR-ready, low-overdraw, game-friendly topology

## 14) Rendering Targets
- PBR-compliant materials
- Soft global illumination compatibility
- Natural contact shadows
- Eye reflections preserved in real-time
- Fur readability in both HDR and LDR displays
- Subsurface scattering approximation for ears/nose where available

## 15) Export Deliverables
Provide:
- GLTF 2.0 (.glb preferred)
- FBX
- Blender source (.blend)
- Texture maps (organized per material)
- Rig and skeleton
- Animation clips (separate actions + optional packed file)

Engine compatibility targets:
- Three.js
- React Three Fiber
- Unity
- Unreal-compatible FBX baseline
- Desktop and Web runtime

## 16) File and Naming Convention
Suggested package structure:
- Character/NOVA_Cat_LOD0.glb
- Character/NOVA_Cat_LOD1.glb
- Character/NOVA_Cat_LOD2.glb
- Character/NOVA_Cat_Rig.fbx
- Character/NOVA_Cat_Master.blend
- Animations/NOVA_<Action>_<Variant>.fbx
- Textures/<Material>/<MapType>_4k.png
- Props/<PropName>_LOD0.glb

## 17) Performance and Technical Acceptance
### Runtime budgets (guideline)
- Desktop target: 60 FPS at 1080p with active idle behaviors
- Web target: 30 to 60 FPS depending device class with LOD adaptation
- Material count minimized, texture atlasing preferred where practical

### Validation checklist
- Clean import in Blender, Unity, and Three.js
- No broken tangents or flipped normals
- No skin weight explosions under extreme poses
- Blend shapes functional and combinable
- LODs switch without visual popping (cross-fade or hysteresis recommended)

## 18) Identity Rules
- Character must be original and ownable IP
- Do not clone existing famous cat character silhouettes
- Keep design memorable enough to become NOVA brand icon
- Must remain visually pleasant over thousands of interaction hours

## 19) Final Quality Bar
NOVA should read as a believable companion pet first, AI symbol second.

When idle, the character must feel alive through:
- Breathing
- Blink timing variation
- Ear micro-adjustments
- Tail secondary motion
- Context-aware posture shifts

No stiff loops, no mascot stiffness, no uncanny spikes.

---

## 20) Prompt Snippet for AI 3D Generation Agent
Design an original production-quality Persian companion cat named NOVA: light orange coat, cream undercoat, white chest and paws, fluffy tail, green expressive eyes, pink nose, dark navy collar with cyan pendant and NOVA metal tag. Preserve realistic feline anatomy with premium stylization, quad topology, animation-ready rig, clean edge loops, 4K PBR textures, and reusable clip library for idle, emotion, speech, and interaction states. Export GLTF/FBX/BLEND with LOD0-2 and ensure compatibility with Three.js, React Three Fiber, Unity, and desktop/web real-time rendering.
