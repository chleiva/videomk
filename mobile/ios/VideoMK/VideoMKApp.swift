import SwiftUI

@main
struct VideoMKApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(Theme.primary)
                .task { await model.start() }
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        switch model.phase {
        case .launching: Theme.background.ignoresSafeArea()
        case .notConfigured:
            ContentUnavailableView("Not configured", systemImage: "gearshape.2",
                                   description: Text("This build has no server address. Use the Debug build, or fill in the Release settings."))
        case .signedOut: SignInView()
        case .signedIn: LibraryView()
        }
    }
}
