import AppKit
import SwiftUI

private let companionWindowIdentifier = NSUserInterfaceItemIdentifier("nova.companion.floating")

struct WindowAccessor: NSViewRepresentable {
    let onResolve: (NSWindow) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = NSView(frame: .zero)
        DispatchQueue.main.async {
            if let window = view.window {
                onResolve(window)
            }
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async {
            if let window = nsView.window {
                onResolve(window)
            }
        }
    }
}

struct FloatingCompanionWindowModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(
                WindowAccessor { window in
                    configure(window)
                }
            )
    }

    private func configure(_ window: NSWindow) {
        guard window.identifier != companionWindowIdentifier else {
            return
        }

        window.identifier = companionWindowIdentifier
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.isMovableByWindowBackground = true
        window.level = .floating
        window.collectionBehavior.insert(.canJoinAllSpaces)
        window.collectionBehavior.insert(.fullScreenAuxiliary)

        if !window.styleMask.contains(.fullSizeContentView) {
            window.styleMask.insert(.fullSizeContentView)
        }

        window.standardWindowButton(.closeButton)?.isHidden = true
        window.standardWindowButton(.miniaturizeButton)?.isHidden = true
        window.standardWindowButton(.zoomButton)?.isHidden = true
    }
}

extension View {
    func floatingCompanionWindow() -> some View {
        modifier(FloatingCompanionWindowModifier())
    }
}