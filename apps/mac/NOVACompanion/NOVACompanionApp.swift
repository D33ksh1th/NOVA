import SwiftUI

@main
struct NOVACompanionApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 400, minHeight: 400)
        }
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(replacing: .appSettings) {
                Button("Settings") {
                    // Open settings
                }
                .keyboardShortcut(",", modifiers: .command)
            }
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Allow app to run in background
        NSApp.setActivationPolicy(.regular)
    }
}

struct ContentView: View {
    @StateObject var animationController = AnimationController()
    @State var isDragging = false
    @State var dragOffset: CGSize = .zero
    
    var body: some View {
        ZStack {
            // Transparent background
            Color.clear
                .background(ClearWindowView())
            
            // Cat scene
            SceneView(scene: animationController.catScene)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .onContinuousHover { phase in
                    switch phase {
                    case .active:
                        NSCursor.openHand.push()
                    case .ended:
                        NSCursor.pop()
                    }
                }
            
            // Speech bubble
            if !animationController.currentSpeech.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text(animationController.currentSpeech)
                        .font(.system(size: 13, weight: .medium))
                        .padding(10)
                        .background(Color.white)
                        .cornerRadius(8)
                        .shadow(radius: 2)
                }
                .padding()
                .position(x: 100, y: 80)
            }
            
            // Status indicator (backend connection)
            HStack {
                Circle()
                    .fill(animationController.isConnected ? Color.green : Color.red)
                    .frame(width: 8, height: 8)
                Text(animationController.isConnected ? "Connected" : "Offline")
                    .font(.caption)
                    .foregroundColor(.gray)
            }
            .padding(8)
            .position(x: 50, y: 30)
        }
        .onAppear {
            animationController.startBackendListener()
            animationController.startIdleAnimation()
        }
    }
}

// Clear/transparent window background
struct ClearWindowView: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        
        if let window = NSApplication.shared.windows.first {
            window.isOpaque = false
            window.backgroundColor = NSColor.clear
            window.styleMask.insert(.fullSizeContentView)
            window.level = .floating
            window.isMovableByWindowBackground = true
            window.collectionBehavior = [.canJoinAllSpaces, .stationary]
        }
        
        return view
    }
    
    func updateNSView(_ nsView: NSView, context: Context) {}
}

#Preview {
    ContentView()
}
