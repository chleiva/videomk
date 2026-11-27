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
                .dynamicTypeSize(...DynamicTypeSize.appMax)
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

/// The floating tab bar (Videos, Media) with the round (+) beside it. Both tabs stay alive underneath, so a pushed video, a scroll position or an open
/// sheet survives a switch. The bar hides while a video is open (the video screen is a full page).
struct MainTabs: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        @Bindable var model = model
        ZStack {
            LibraryView().opacity(model.selectedTab == 0 ? 1 : 0).allowsHitTesting(model.selectedTab == 0).accessibilityHidden(model.selectedTab != 0)
            Group {
                if let media = model.media { MediaView(media: media) } else { ContentUnavailableView(tr("app.not_available"), systemImage: "photo.on.rectangle") }
            }
            .opacity(model.selectedTab == 1 ? 1 : 0).allowsHitTesting(model.selectedTab == 1).accessibilityHidden(model.selectedTab != 1)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if !model.tabBarHidden, !(model.mediaSelecting && model.selectedTab == 1) { FloatingTabBar(selection: $model.selectedTab) { model.requestCreate() }.transition(.move(edge: .bottom).combined(with: .opacity)) }
        }
        .animation(.easeOut(duration: 0.22), value: model.tabBarHidden)
        .animation(.easeOut(duration: 0.22), value: model.mediaSelecting)
        .background(Theme.background.ignoresSafeArea())
    }
}
