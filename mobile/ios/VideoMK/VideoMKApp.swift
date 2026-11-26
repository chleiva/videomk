import SwiftUI
import VideoMKCore

@main
struct VideoMKApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(Theme.primary)
                .modifier(LocalizedRoot())
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
            ContentUnavailableView(tr("app.not_configured"), systemImage: "gearshape.2",
                                   description: Text(tr("app.not_configured_sub")))
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
            LibraryView().tabItem { Label(tr("tab.videos"), systemImage: "play.rectangle.on.rectangle") }.tag(0)
            Group {
                if let media = model.media { MediaView(media: media) } else { ContentUnavailableView(tr("app.not_available"), systemImage: "photo.on.rectangle") }
            }
            .tabItem { Label(tr("tab.media"), systemImage: "photo.on.rectangle") }.tag(1)
        }
    }
}
