import SceneKit
import SwiftUI
import Combine

class AnimationController: NSObject, ObservableObject {
    @Published var currentState: AvatarState = .idle
    @Published var currentSpeech: String = ""
    @Published var isConnected: Bool = false
    
    let catScene = SCNScene()
    private var catNode: SCNNode?
    private var idleAnimationTimer: Timer?
    private var stateChangeTimer: Timer?
    private var backendTask: URLSessionWebSocketTask?
    
    private var lastIdleAnimations: [String] = []
    
    override init() {
        super.init()
        setupScene()
    }
    
    // MARK: - Scene Setup
    
    func setupScene() {
        // Clear background
        catScene.background.contents = NSColor.clear
        
        // Create cat node
        let catNodeGeom = SCNNode()
        catNode = catNodeGeom
        catScene.rootNode.addChildNode(catNodeGeom)
        
        // Try to load USDZ model if available
        if let catModel = loadCatModel() {
            catNodeGeom.addChildNode(catModel)
        } else {
            // Fallback: procedural cat geometry
            setupProceduralCat(node: catNodeGeom)
        }
        
        // Setup lighting
        setupLighting()
        
        // Setup camera
        setupCamera()
    }
    
    private func loadCatModel() -> SCNNode? {
        // Try to load from Bundle
        guard let modelPath = Bundle.main.path(forResource: "cat", ofType: "usdz") else {
            print("⚠️  Cat model not found in bundle. Using procedural fallback.")
            return nil
        }
        
        do {
            let scene = try SCNScene(url: URL(fileURLWithPath: modelPath), options: [:])
            return scene.rootNode
        } catch {
            print("❌ Error loading cat model: \(error)")
            return nil
        }
    }
    
    private func setupProceduralCat(node: SCNNode) {
        // Simple cat head
        let head = SCNSphere(radius: 0.3)
        head.firstMaterial?.diffuse.contents = NSColor(red: 1.0, green: 0.65, blue: 0.0, alpha: 1.0) // Orange
        
        let headNode = SCNNode(geometry: head)
        headNode.position = SCNVector3(0, 0.2, 0)
        node.addChildNode(headNode)
        
        // Ears
        let earGeometry = SCNCone(topRadius: 0.1, bottomRadius: 0.15, height: 0.3)
        earGeometry.firstMaterial?.diffuse.contents = NSColor(red: 1.0, green: 0.65, blue: 0.0, alpha: 1.0)
        
        let leftEar = SCNNode(geometry: earGeometry)
        leftEar.position = SCNVector3(-0.2, 0.5, 0)
        leftEar.eulerAngles.z = -0.3
        headNode.addChildNode(leftEar)
        
        let rightEar = SCNNode(geometry: earGeometry)
        rightEar.position = SCNVector3(0.2, 0.5, 0)
        rightEar.eulerAngles.z = 0.3
        headNode.addChildNode(rightEar)
        
        // Eyes
        let eyeGeometry = SCNSphere(radius: 0.08)
        eyeGeometry.firstMaterial?.diffuse.contents = NSColor.yellow
        
        let leftEye = SCNNode(geometry: eyeGeometry)
        leftEye.position = SCNVector3(-0.1, 0.1, 0.25)
        headNode.addChildNode(leftEye)
        
        let rightEye = SCNNode(geometry: eyeGeometry)
        rightEye.position = SCNVector3(0.1, 0.1, 0.25)
        headNode.addChildNode(rightEye)
        
        // Body
        let bodyGeometry = SCNCapsule(capRadius: 0.2, height: 0.5)
        bodyGeometry.firstMaterial?.diffuse.contents = NSColor(red: 1.0, green: 0.65, blue: 0.0, alpha: 1.0)
        
        let bodyNode = SCNNode(geometry: bodyGeometry)
        bodyNode.position = SCNVector3(0, -0.3, 0)
        node.addChildNode(bodyNode)
        
        // Tail
        let tailGeometry = SCNCone(topRadius: 0.05, bottomRadius: 0.08, height: 0.6)
        tailGeometry.firstMaterial?.diffuse.contents = NSColor(red: 1.0, green: 0.65, blue: 0.0, alpha: 1.0)
        
        let tailNode = SCNNode(geometry: tailGeometry)
        tailNode.position = SCNVector3(0, -0.5, -0.3)
        tailNode.eulerAngles.z = 0.5
        bodyNode.addChildNode(tailNode)
    }
    
    private func setupLighting() {
        // Ambient light
        let ambientLight = SCNLight()
        ambientLight.type = .ambient
        ambientLight.intensity = 600
        let ambientLightNode = SCNNode()
        ambientLightNode.light = ambientLight
        catScene.rootNode.addChildNode(ambientLightNode)
        
        // Directional light
        let sunLight = SCNLight()
        sunLight.type = .directional
        sunLight.intensity = 1000
        sunLight.castsShadow = true
        let sunLightNode = SCNNode()
        sunLightNode.light = sunLight
        sunLightNode.position = SCNVector3(5, 10, 5)
        catScene.rootNode.addChildNode(sunLightNode)
    }
    
    private func setupCamera() {
        let camera = SCNCamera()
        camera.zFar = 1000
        camera.zNear = 0.1
        
        let cameraNode = SCNNode()
        cameraNode.camera = camera
        cameraNode.position = SCNVector3(0, 0.1, 1.2)
        catScene.rootNode.addChildNode(cameraNode)
    }
    
    // MARK: - Animation Control
    
    func transitionTo(_ newState: AvatarState) {
        DispatchQueue.main.async {
            self.currentState = newState
            print("🐱 Avatar state: \(newState.description)")
            
            switch newState {
            case .idle:
                self.playIdleAnimation()
                
            case .listening:
                self.playListeningAnimation()
                
            case .thinking:
                self.playThinkingAnimation()
                
            case .speaking(let text, let duration):
                self.currentSpeech = text
                self.playSpeakingAnimation()
                
                // Auto-hide speech bubble after duration
                DispatchQueue.main.asyncAfter(deadline: .now() + duration) {
                    if case .speaking = self.currentState {
                        self.currentSpeech = ""
                    }
                }
                
            case .sleeping:
                self.playSleepingAnimation()
                
            case .happy:
                self.playHappyAnimation()
                
            case .confused:
                self.playConfusedAnimation()
            }
        }
    }
    
    // MARK: - Individual Animations
    
    private func playIdleAnimation() {
        guard let catNode = catNode else { return }
        
        let randomVariation = IdleAnimationVariation.all.randomElement()!
        
        // Avoid repeating same animation twice in a row
        while lastIdleAnimations.count > 0 && lastIdleAnimations.last == randomVariation.name {
            let newVariation = IdleAnimationVariation.all.randomElement()!
            if lastIdleAnimations.last != newVariation.name {
                playIdleAnimation()
                return
            }
        }
        
        lastIdleAnimations.append(randomVariation.name)
        if lastIdleAnimations.count > 3 {
            lastIdleAnimations.removeFirst()
        }
        
        let animation = SCNAction()
        
        switch randomVariation.name {
        case "blink":
            playBlink(node: catNode)
            
        case "tail_wag":
            playTailWag(node: catNode)
            
        case "head_tilt":
            playHeadTilt(node: catNode)
            
        case "paw_lick":
            playPawLick(node: catNode)
            
        case "stretch":
            playStretch(node: catNode)
            
        case "yawn":
            playYawn(node: catNode)
            
        default:
            break
        }
    }
    
    private func playBlink(node: SCNNode) {
        let blinkAction = SCNAction.sequence([
            SCNAction.moveBy(x: 0, y: 0.02, z: 0, duration: 0.15),
            SCNAction.moveBy(x: 0, y: -0.02, z: 0, duration: 0.15)
        ])
        node.runAction(blinkAction)
    }
    
    private func playTailWag(node: SCNNode) {
        let rotateLeft = SCNAction.rotateTo(x: 0, y: 0, z: 0.3, duration: 0.3)
        let rotateRight = SCNAction.rotateTo(x: 0, y: 0, z: -0.3, duration: 0.3)
        let rotateCenter = SCNAction.rotateTo(x: 0, y: 0, z: 0, duration: 0.3)
        
        let wagSequence = SCNAction.sequence([rotateLeft, rotateRight, rotateCenter])
        node.runAction(SCNAction.repeat(wagSequence, count: 2))
    }
    
    private func playHeadTilt(node: SCNNode) {
        let tiltLeft = SCNAction.rotateTo(x: 0, y: -0.2, z: 0, duration: 0.4)
        let tiltRight = SCNAction.rotateTo(x: 0, y: 0.2, z: 0, duration: 0.4)
        let tiltCenter = SCNAction.rotateTo(x: 0, y: 0, z: 0, duration: 0.4)
        
        let tiltSequence = SCNAction.sequence([tiltLeft, tiltRight, tiltCenter])
        node.runAction(tiltSequence)
    }
    
    private func playPawLick(node: SCNNode) {
        let moveUp = SCNAction.moveBy(x: 0.1, y: 0.1, z: 0, duration: 0.3)
        let moveDown = SCNAction.moveBy(x: -0.1, y: -0.1, z: 0, duration: 0.3)
        let sequence = SCNAction.sequence([moveUp, moveDown, moveDown, moveUp])
        node.runAction(SCNAction.repeat(sequence, count: 3))
    }
    
    private func playStretch(node: SCNNode) {
        let scaleUp = SCNAction.scaleTo(1.15, duration: 0.5)
        let scaleDown = SCNAction.scaleTo(1.0, duration: 0.5)
        let sequence = SCNAction.sequence([scaleUp, scaleDown])
        node.runAction(sequence)
    }
    
    private func playYawn(node: SCNNode) {
        let moveUp = SCNAction.moveBy(x: 0, y: 0.1, z: 0, duration: 0.3)
        let moveDown = SCNAction.moveBy(x: 0, y: -0.1, z: 0, duration: 0.3)
        let sequence = SCNAction.sequence([moveUp, moveDown])
        node.runAction(sequence)
    }
    
    private func playListeningAnimation() {
        guard let catNode = catNode else { return }
        
        // Slight head tilt + eyes focused
        let tiltAction = SCNAction.rotateTo(x: 0, y: -0.15, z: 0.1, duration: 0.5)
        catNode.runAction(tiltAction)
    }
    
    private func playThinkingAnimation() {
        guard let catNode = catNode else { return }
        
        // Slow tail wag + head tilt
        let rotateLeft = SCNAction.rotateTo(x: 0.1, y: 0, z: 0.2, duration: 0.8)
        let rotateCenter = SCNAction.rotateTo(x: 0, y: 0, z: 0, duration: 0.8)
        
        let thinkSequence = SCNAction.sequence([rotateLeft, rotateCenter])
        catNode.runAction(SCNAction.repeat(thinkSequence, count: 2))
    }
    
    private func playSpeakingAnimation() {
        guard let catNode = catNode else { return }
        
        // Mouth movement + ear twitches
        let earTwitch = SCNAction.rotateTo(x: 0.1, y: 0, z: 0, duration: 0.2)
        let earReset = SCNAction.rotateTo(x: 0, y: 0, z: 0, duration: 0.2)
        
        let speakSequence = SCNAction.sequence([earTwitch, earReset])
        catNode.runAction(SCNAction.repeat(speakSequence, count: 3))
    }
    
    private func playSleepingAnimation() {
        guard let catNode = catNode else { return }
        
        // Close eyes (scale down slightly) + gentle tail curl
        let sleepScale = SCNAction.scaleTo(0.95, duration: 1.0)
        catNode.runAction(sleepScale)
    }
    
    private func playHappyAnimation() {
        guard let catNode = catNode else { return }
        
        // Jump + spin
        let jump = SCNAction.moveBy(x: 0, y: 0.3, z: 0, duration: 0.3)
        let land = SCNAction.moveBy(x: 0, y: -0.3, z: 0, duration: 0.3)
        let spin = SCNAction.rotateBy(x: 0, y: CGFloat.pi, z: 0, duration: 0.5)
        
        let sequence = SCNAction.sequence([jump, land])
        catNode.runAction(sequence)
        catNode.runAction(spin)
    }
    
    private func playConfusedAnimation() {
        guard let catNode = catNode else { return }
        
        // Head shake
        let shakeLeft = SCNAction.rotateTo(x: 0, y: -0.3, z: 0, duration: 0.2)
        let shakeRight = SCNAction.rotateTo(x: 0, y: 0.3, z: 0, duration: 0.2)
        let shakeCenter = SCNAction.rotateTo(x: 0, y: 0, z: 0, duration: 0.2)
        
        let shakeSequence = SCNAction.sequence([shakeLeft, shakeRight, shakeCenter])
        catNode.runAction(SCNAction.repeat(shakeSequence, count: 2))
    }
    
    // MARK: - Idle Loop
    
    func startIdleAnimation() {
        idleAnimationTimer?.invalidate()
        
        idleAnimationTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            guard self?.currentState.description == "Idle" else { return }
            self?.playIdleAnimation()
        }
    }
    
    // MARK: - Backend Communication
    
    func startBackendListener() {
        // Simulate backend event listener
        // In production: Use URLSessionWebSocketTask or EventSource for real WebSocket/SSE
        
        let url = AnimationConfig.backendURL.appendingPathComponent("/events/subscribe")
        var request = URLRequest(url: url)
        request.timeoutInterval = 60
        
        backendTask = URLSession.shared.webSocketTask(with: request)
        backendTask?.resume()
        
        DispatchQueue.main.async {
            self.isConnected = true
        }
        
        receiveBackendEvent()
    }
    
    private func receiveBackendEvent() {
        backendTask?.receive { [weak self] result in
            switch result {
            case .success(let message):
                switch message {
                case .string(let json):
                    self?.handleBackendEvent(json: json)
                case .data(let data):
                    if let json = String(data: data, encoding: .utf8) {
                        self?.handleBackendEvent(json: json)
                    }
                @unknown default:
                    break
                }
                
                // Continue listening
                self?.receiveBackendEvent()
                
            case .failure(let error):
                print("❌ WebSocket error: \(error)")
                DispatchQueue.main.async {
                    self?.isConnected = false
                }
                
                // Reconnect after delay
                DispatchQueue.main.asyncAfter(deadline: .now() + 5.0) {
                    self?.startBackendListener()
                }
            }
        }
    }
    
    private func handleBackendEvent(json: String) {
        guard let data = json.data(using: .utf8),
              let event = try? JSONDecoder().decode(BackendEvent.self, from: data) else {
            return
        }
        
        print("📡 Backend event: \(event)")
        
        switch event {
        case .startedListening:
            transitionTo(.listening(duration: 3.0))
            
        case .startedThinking:
            transitionTo(.thinking(duration: 2.0))
            
        case .startedSpeaking(let text):
            transitionTo(.speaking(text: text, duration: 4.0))
            
        case .listeningComplete:
            transitionTo(.idle)
            
        case .thinkingComplete:
            transitionTo(.idle)
            
        case .speakingComplete:
            transitionTo(.idle)
            
        case .recognized(let user):
            DispatchQueue.main.async {
                self.currentSpeech = "Hi \(user)! 👋"
            }
            transitionTo(.happy)
            
            // Return to idle after 2 seconds
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                self.transitionTo(.idle)
            }
            
        case .error:
            transitionTo(.confused)
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                self.transitionTo(.idle)
            }
        }
    }
    
    deinit {
        idleAnimationTimer?.invalidate()
        backendTask?.cancel(with: .goingAway, reason: nil)
    }
}

// MARK: - SceneView (SwiftUI)

struct SceneView: NSViewRepresentable {
    let scene: SCNScene
    
    func makeNSView(context: Context) -> SCNView {
        let sceneView = SCNView()
        sceneView.scene = scene
        sceneView.autoenablesDefaultLighting = true
        sceneView.allowsCameraControl = false
        sceneView.backgroundColor = NSColor.clear
        sceneView.preferredFramesPerSecond = 60
        return sceneView
    }
    
    func updateNSView(_ nsView: SCNView, context: Context) {}
}
