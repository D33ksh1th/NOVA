import SwiftUI

@main
struct NOVACompanionApp: App {
    @StateObject private var viewModel = CompanionViewModel()

    var body: some Scene {
        WindowGroup("NOVA Companion") {
            CompanionRootView(viewModel: viewModel)
                .floatingCompanionWindow()
                .frame(minWidth: 420, minHeight: 520)
                .background(.clear)
        }
        .windowStyle(.hiddenTitleBar)
    }
}
