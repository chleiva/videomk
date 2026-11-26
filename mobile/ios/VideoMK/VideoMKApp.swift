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
        if let notice = model.deletionNotice {
            AccountDeletedView(notice: notice)
        } else {
        switch model.phase {
        case .launching: Theme.background.ignoresSafeArea()
        case .notConfigured:
            ContentUnavailableView("Not configured", systemImage: "gearshape.2",
                                   description: Text("This build has no server address. Use the Debug build, or fill in the Release settings."))
        case .signedOut: SignInView()
        case .signedIn: MainTabs()
        }
        }
    }
}

/// The bottom tab bar: Videos (the home screen) and Media (the private photo library).
struct MainTabs: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        TabView(selection: $model.selectedTab) {
            LibraryView().tabItem { Label("Videos", systemImage: "play.rectangle.on.rectangle") }.tag(0)
            Group {
                if let media = model.media { MediaView(media: media) } else { ContentUnavailableView("Not available", systemImage: "photo.on.rectangle") }
            }
            .tabItem { Label("Media", systemImage: "photo.on.rectangle") }.tag(1)
        }
    }
}
