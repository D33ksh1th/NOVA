import AppKit
import SceneKit
import SwiftUI
import UniformTypeIdentifiers

struct CompanionSceneView: View {
    @ObservedObject var sceneController: CompanionSceneController

    var body: some View {
        SceneView(
            scene: sceneController.scene,
            pointOfView: sceneController.cameraNode,
            options: [.allowsCameraControl],
            preferredFramesPerSecond: 60,
            antialiasingMode: .multisampling4X,
            delegate: nil,
            technique: nil
        )
        .background(Color.clear)
    }
}

@MainActor
final class CompanionSceneController: ObservableObject {
    @Published var modelStatus: String = "Using procedural fallback model"
    @Published var hasExternalModel: Bool = false

    let scene = SCNScene()
    let cameraNode = SCNNode()

    private let catRoot = SCNNode()
    private let headNode = SCNNode()
    private let tailNode = SCNNode()
    private let earLeftNode = SCNNode()
    private let earRightNode = SCNNode()
    private let whiskerRoot = SCNNode()
    private var externalModelNode: SCNNode?

    private var cameraBasePosition = SCNVector3(0.0, 1.25, 5.6)

    init() {
        buildScene()
        setState(.idle)
    }

    func setState(_ state: AvatarVisualState) {
        catRoot.removeAction(forKey: "body")
        headNode.removeAction(forKey: "head")
        tailNode.removeAction(forKey: "tail")
        earLeftNode.removeAction(forKey: "ears")
        earRightNode.removeAction(forKey: "ears")

        let baseRotation = SCNAction.rotateTo(x: 0, y: 0, z: 0, duration: 0.2)
        catRoot.runAction(baseRotation)

        switch state {
        case .idle:
            runIdleAnimation()
        case .listening:
            runListeningAnimation()
        case .thinking:
            runThinkingAnimation()
        case .speaking:
            runSpeakingAnimation()
        case .error:
            runErrorAnimation()
        }
    }

    private func buildScene() {
        scene.background.contents = NSColor.clear

        let floor = SCNFloor()
        floor.reflectivity = 0.08
        floor.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.05, green: 0.09, blue: 0.16, alpha: 1.0)
        let floorNode = SCNNode(geometry: floor)
        floorNode.position = SCNVector3(0, -0.9, 0)
        scene.rootNode.addChildNode(floorNode)

        let ambient = SCNLight()
        ambient.type = .ambient
        ambient.intensity = 420
        ambient.color = NSColor(calibratedWhite: 0.9, alpha: 1.0)
        let ambientNode = SCNNode()
        ambientNode.light = ambient
        scene.rootNode.addChildNode(ambientNode)

        let keyLight = SCNLight()
        keyLight.type = .omni
        keyLight.intensity = 1150
        keyLight.color = NSColor(calibratedRed: 0.72, green: 0.83, blue: 1.0, alpha: 1.0)
        let keyNode = SCNNode()
        keyNode.position = SCNVector3(2.5, 3.2, 4.0)
        keyNode.light = keyLight
        scene.rootNode.addChildNode(keyNode)

        let fillLight = SCNLight()
        fillLight.type = .omni
        fillLight.intensity = 450
        fillLight.color = NSColor(calibratedRed: 1.0, green: 0.9, blue: 0.78, alpha: 1.0)
        let fillNode = SCNNode()
        fillNode.position = SCNVector3(-2.5, 2.0, -2.0)
        fillNode.light = fillLight
        scene.rootNode.addChildNode(fillNode)

        cameraNode.camera = SCNCamera()
        cameraNode.camera?.fieldOfView = 42
        cameraNode.position = cameraBasePosition
        scene.rootNode.addChildNode(cameraNode)

        if !loadExternalCatModel() {
            buildCatPlaceholder()
        }
        scene.rootNode.addChildNode(catRoot)
    }

    func promptForModelImport() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        var allowedTypes: [UTType] = [.usdz, .sceneKitScene]
        if let daeType = UTType(filenameExtension: "dae") {
            allowedTypes.append(daeType)
        }
        panel.allowedContentTypes = allowedTypes
        panel.title = "Select Persian Cat Model"
        panel.message = "Choose a .usdz, .scn, or .dae file"

        guard panel.runModal() == .OK, let url = panel.url else {
            return
        }

        if loadModel(from: url) {
            modelStatus = "Loaded model: \(url.lastPathComponent)"
        } else {
            modelStatus = "Failed to load: \(url.lastPathComponent)"
        }
    }

    func rotateCat(by radians: CGFloat) {
        catRoot.eulerAngles.y += radians
    }

    func resetCamera() {
        cameraNode.position = cameraBasePosition
        cameraNode.eulerAngles = SCNVector3Zero
    }

    func zoomCamera(delta: CGFloat) {
        let nextZ = max(3.2, min(8.2, cameraNode.position.z + delta))
        cameraNode.position.z = nextZ
    }

    private func loadExternalCatModel() -> Bool {
        let fileManager = FileManager.default
        let cwd = URL(fileURLWithPath: fileManager.currentDirectoryPath)

        var candidateURLs: [URL] = []
        if let bundleURL = Bundle.main.url(forResource: "persian_cat", withExtension: "usdz") {
            candidateURLs.append(bundleURL)
        }
        if let novaRoot = ProcessInfo.processInfo.environment["NOVA_ROOT"], !novaRoot.isEmpty {
            candidateURLs.append(URL(fileURLWithPath: novaRoot).appendingPathComponent("assets/character/persian_cat.usdz"))
            candidateURLs.append(URL(fileURLWithPath: novaRoot).appendingPathComponent("assets/character/persian_cat.scn"))
            candidateURLs.append(URL(fileURLWithPath: novaRoot).appendingPathComponent("assets/character/persian_cat.dae"))
        }

        let relativeCandidates = [
            "../../assets/character/persian_cat.usdz",
            "../../assets/character/persian_cat.scn",
            "../../assets/character/persian_cat.dae",
            "../../assets/character/cat.usdz",
            "../../assets/character/cat.scn",
            "../../assets/character/cat.dae",
            "../assets/character/persian_cat.usdz",
            "../assets/character/persian_cat.scn",
            "../assets/character/persian_cat.dae",
        ]
        for path in relativeCandidates {
            candidateURLs.append(cwd.appendingPathComponent(path).standardizedFileURL)
        }

        for url in candidateURLs {
            guard fileManager.fileExists(atPath: url.path) else {
                continue
            }
            if loadModel(from: url) {
                modelStatus = "Loaded model: \(url.lastPathComponent)"
                return true
            }
        }

        return false
    }

    private func loadModel(from url: URL) -> Bool {
        do {
            let externalScene = try SCNScene(url: url, options: nil)
            let wrapper = SCNNode()
            for child in externalScene.rootNode.childNodes {
                wrapper.addChildNode(child)
            }
            wrapper.scale = SCNVector3(1.2, 1.2, 1.2)
            wrapper.position = SCNVector3(0, -0.8, 0)

            externalModelNode?.removeFromParentNode()
            externalModelNode = wrapper
            catRoot.addChildNode(wrapper)

            hasExternalModel = true
            return true
        } catch {
            return false
        }
    }

    private func buildCatPlaceholder() {
        let fur = NSColor(calibratedRed: 0.80, green: 0.78, blue: 0.76, alpha: 1.0)
        let furDark = NSColor(calibratedRed: 0.46, green: 0.45, blue: 0.45, alpha: 1.0)
        let furLight = NSColor(calibratedRed: 0.93, green: 0.90, blue: 0.87, alpha: 1.0)

        let body = SCNSphere(radius: 0.9)
        body.firstMaterial?.diffuse.contents = fur
        body.firstMaterial?.roughness.contents = 0.78
        let bodyNode = SCNNode(geometry: body)
        bodyNode.scale = SCNVector3(1.02, 1.0, 1.06)
        bodyNode.position = SCNVector3(0, 0, 0)
        catRoot.addChildNode(bodyNode)

        let chest = SCNSphere(radius: 0.48)
        chest.firstMaterial?.diffuse.contents = furLight
        let chestNode = SCNNode(geometry: chest)
        chestNode.scale = SCNVector3(0.94, 1.22, 0.66)
        chestNode.position = SCNVector3(0, -0.16, 0.68)
        catRoot.addChildNode(chestNode)

        let legGeometry = SCNCapsule(capRadius: 0.17, height: 0.75)
        legGeometry.firstMaterial?.diffuse.contents = furLight
        let legLeft = SCNNode(geometry: legGeometry)
        legLeft.position = SCNVector3(-0.26, -0.58, 0.53)
        let legRight = SCNNode(geometry: legGeometry)
        legRight.position = SCNVector3(0.26, -0.58, 0.53)
        catRoot.addChildNode(legLeft)
        catRoot.addChildNode(legRight)

        let head = SCNSphere(radius: 0.55)
        head.firstMaterial?.diffuse.contents = fur
        head.firstMaterial?.roughness.contents = 0.72
        headNode.geometry = head
        headNode.position = SCNVector3(0, 0.72, 0.58)
        catRoot.addChildNode(headNode)

        let snout = SCNSphere(radius: 0.21)
        snout.firstMaterial?.diffuse.contents = furLight
        let snoutNode = SCNNode(geometry: snout)
        snoutNode.scale = SCNVector3(1.34, 0.8, 1.0)
        snoutNode.position = SCNVector3(0, -0.07, 0.44)
        headNode.addChildNode(snoutNode)

        let nose = SCNSphere(radius: 0.05)
        nose.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.86, green: 0.52, blue: 0.62, alpha: 1.0)
        let noseNode = SCNNode(geometry: nose)
        noseNode.scale = SCNVector3(1.2, 0.8, 1.0)
        noseNode.position = SCNVector3(0, 0.0, 0.62)
        headNode.addChildNode(noseNode)

        whiskerRoot.removeFromParentNode()
        whiskerRoot.childNodes.forEach { $0.removeFromParentNode() }
        for side in [-1.0, 1.0] {
            for y in [-0.03, 0.0, 0.03] {
                let whisker = SCNCylinder(radius: 0.008, height: 0.34)
                whisker.firstMaterial?.diffuse.contents = NSColor(calibratedWhite: 0.97, alpha: 0.95)
                let whiskerNode = SCNNode(geometry: whisker)
                whiskerNode.position = SCNVector3(Float(side * 0.18), Float(y), 0.5)
                whiskerNode.eulerAngles = SCNVector3(0.0, Float(side * .pi / 2.7), Float(side * 0.16))
                whiskerRoot.addChildNode(whiskerNode)
            }
        }
        headNode.addChildNode(whiskerRoot)

        earLeftNode.geometry = SCNCone(topRadius: 0.01, bottomRadius: 0.16, height: 0.28)
        earLeftNode.geometry?.firstMaterial?.diffuse.contents = furDark
        earLeftNode.position = SCNVector3(-0.28, 0.46, 0.0)
        earLeftNode.eulerAngles = SCNVector3(0.16, 0.03, 0.32)
        headNode.addChildNode(earLeftNode)

        earRightNode.geometry = SCNCone(topRadius: 0.01, bottomRadius: 0.16, height: 0.28)
        earRightNode.geometry?.firstMaterial?.diffuse.contents = furDark
        earRightNode.position = SCNVector3(0.28, 0.46, 0.0)
        earRightNode.eulerAngles = SCNVector3(0.16, -0.03, -0.32)
        headNode.addChildNode(earRightNode)

        let eyeLeft = SCNSphere(radius: 0.055)
        eyeLeft.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.46, green: 0.75, blue: 0.28, alpha: 1.0)
        let eyeLeftNode = SCNNode(geometry: eyeLeft)
        eyeLeftNode.position = SCNVector3(-0.16, 0.1, 0.44)
        headNode.addChildNode(eyeLeftNode)

        let eyeRight = SCNSphere(radius: 0.055)
        eyeRight.firstMaterial?.diffuse.contents = NSColor(calibratedRed: 0.46, green: 0.75, blue: 0.28, alpha: 1.0)
        let eyeRightNode = SCNNode(geometry: eyeRight)
        eyeRightNode.position = SCNVector3(0.16, 0.1, 0.44)
        headNode.addChildNode(eyeRightNode)

        let tail = SCNCylinder(radius: 0.075, height: 1.5)
        tail.firstMaterial?.diffuse.contents = furDark
        tailNode.geometry = tail
        tailNode.position = SCNVector3(-0.62, 0.24, -0.62)
        tailNode.eulerAngles = SCNVector3(0.2, 0.3, 1.15)
        catRoot.addChildNode(tailNode)

        hasExternalModel = false
        modelStatus = "Using procedural fallback model"
        catRoot.position = SCNVector3(0, -0.05, 0)
    }

    private func runIdleAnimation() {
        let bobDown = SCNAction.moveBy(x: 0, y: -0.025, z: 0, duration: 1.2)
        let bobUp = SCNAction.moveBy(x: 0, y: 0.025, z: 0, duration: 1.2)
        bobDown.timingMode = .easeInEaseOut
        bobUp.timingMode = .easeInEaseOut
        catRoot.runAction(.repeatForever(.sequence([bobDown, bobUp])), forKey: "body")

        let tailLeft = SCNAction.rotateBy(x: 0, y: 0, z: 0.18, duration: 1.0)
        let tailRight = SCNAction.rotateBy(x: 0, y: 0, z: -0.18, duration: 1.0)
        tailNode.runAction(.repeatForever(.sequence([tailLeft, tailRight])), forKey: "tail")
    }

    private func runListeningAnimation() {
        let lean = SCNAction.rotateTo(x: -0.08, y: 0.0, z: 0.0, duration: 0.22)
        lean.timingMode = .easeInEaseOut
        catRoot.runAction(lean, forKey: "body")

        let perkIn = SCNAction.scale(to: 1.11, duration: 0.18)
        let perkOut = SCNAction.scale(to: 1.0, duration: 0.42)
        let perk = SCNAction.sequence([perkIn, perkOut])
        earLeftNode.runAction(.repeatForever(perk), forKey: "ears")
        earRightNode.runAction(.repeatForever(perk), forKey: "ears")

        let nodDown = SCNAction.rotateTo(x: -0.14, y: 0.0, z: 0.0, duration: 0.5)
        let nodUp = SCNAction.rotateTo(x: 0.08, y: 0.0, z: 0.0, duration: 0.5)
        headNode.runAction(.repeatForever(.sequence([nodDown, nodUp])), forKey: "head")
    }

    private func runThinkingAnimation() {
        let tiltLeft = SCNAction.rotateTo(x: 0.03, y: 0.0, z: 0.17, duration: 0.8)
        let tiltRight = SCNAction.rotateTo(x: 0.03, y: 0.0, z: -0.17, duration: 0.8)
        tiltLeft.timingMode = .easeInEaseOut
        tiltRight.timingMode = .easeInEaseOut
        headNode.runAction(.repeatForever(.sequence([tiltLeft, tiltRight])), forKey: "head")

        let tailSlow = SCNAction.rotateBy(x: 0.0, y: 0.0, z: 0.1, duration: 1.3)
        let tailBack = SCNAction.rotateBy(x: 0.0, y: 0.0, z: -0.1, duration: 1.3)
        tailNode.runAction(.repeatForever(.sequence([tailSlow, tailBack])), forKey: "tail")
    }

    private func runSpeakingAnimation() {
        let pulseOut = SCNAction.scale(to: 1.06, duration: 0.18)
        let pulseIn = SCNAction.scale(to: 1.0, duration: 0.18)
        catRoot.runAction(.repeatForever(.sequence([pulseOut, pulseIn])), forKey: "body")

        let jawDown = SCNAction.moveBy(x: 0.0, y: -0.05, z: 0.03, duration: 0.14)
        let jawUp = SCNAction.moveBy(x: 0.0, y: 0.05, z: -0.03, duration: 0.14)
        headNode.runAction(.repeatForever(.sequence([jawDown, jawUp])), forKey: "head")

        let tailFast = SCNAction.rotateBy(x: 0.0, y: 0.0, z: 0.22, duration: 0.35)
        let tailFastBack = SCNAction.rotateBy(x: 0.0, y: 0.0, z: -0.22, duration: 0.35)
        tailNode.runAction(.repeatForever(.sequence([tailFast, tailFastBack])), forKey: "tail")
    }

    private func runErrorAnimation() {
        let shakeL = SCNAction.rotateTo(x: 0.0, y: 0.0, z: 0.16, duration: 0.1)
        let shakeR = SCNAction.rotateTo(x: 0.0, y: 0.0, z: -0.16, duration: 0.1)
        let settle = SCNAction.rotateTo(x: 0.0, y: 0.0, z: 0.0, duration: 0.2)
        catRoot.runAction(.repeatForever(.sequence([shakeL, shakeR, settle])), forKey: "body")
    }
}
