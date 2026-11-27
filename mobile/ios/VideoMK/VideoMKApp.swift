import SwiftUI
import VideoMKCore

@main
struct VideoMKApp: App {
    @State private var model = AppModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .tint(Theme.primary)
                .modifier(LocalizedRoot())
                .dynamicTypeSize(...DynamicTypeSize.appMax)
                .task { await model.start() }
        }
        .onChange(of: scenePhase) { _, phase in
            // "Tell me when it's ready": keep checking for a while after the app is left, and ask iOS for a later look
            if phase == .background { ReadyNotifier.shared.appDidEnterBackground(hasRunning: model.hasRunningVideos); if ReadyNotifier.shared.enabled { Task { await model.pollWhileRunning() } } }
            if phase == .active { ReadyNotifier.shared.appDidBecomeActive() }
        }
        .backgroundTask(.appRefresh(ReadyNotifier.refreshTask)) { await model.backgroundCheck() }
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
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private var barShown: Bool { !model.tabBarHidden && !(model.mediaSelecting && model.selectedTab == 1) }

    var body: some View {
        @Bindable var model = model
        ZStack {
            LibraryView().opacity(model.selectedTab == 0 ? 1 : 0).allowsHitTesting(model.selectedTab == 0).accessibilityHidden(model.selectedTab != 0)
            Group {
                if let media = model.media { MediaView(media: media) } else { ContentUnavailableView(tr("app.not_available"), systemImage: "photo.on.rectangle") }
            }
            .opacity(model.selectedTab == 1 ? 1 : 0).allowsHitTesting(model.selectedTab == 1).accessibilityHidden(model.selectedTab != 1)
        }
        .overlay(alignment: .bottom) { if barShown { TabBarFade().ignoresSafeArea(edges: .bottom).transition(.opacity) } }       // the page fades out under the floating bar
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if barShown { FloatingTabBar(selection: $model.selectedTab) { model.requestCreate() }.transition(reduceMotion ? .opacity : .move(edge: .bottom).combined(with: .opacity)) }
        }
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: model.tabBarHidden)
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: model.mediaSelecting)
        .background(Theme.background.ignoresSafeArea())
    }
}

/// The top bar is ours on every screen (`TopBar`), so the system navigation bar is hidden; this keeps the swipe from the left edge that goes back.
extension UINavigationController: @retroactive UIGestureRecognizerDelegate {
    override open func viewDidLoad() {
        super.viewDidLoad()
        interactivePopGestureRecognizer?.delegate = self
    }
    public func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool { viewControllers.count > 1 }
}
