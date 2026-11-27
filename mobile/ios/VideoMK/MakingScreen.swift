import BackgroundTasks
import SwiftUI
import UserNotifications
import VideoMKCore

/// The Making screen (docs/DESIGN_BAR_2026.md signature 3, `phone_4_making`): the scene being built shown large inside the live ring, the title, one live
/// line, the film strip filling scene by scene, the sentence being narrated. No step names, no percentages.
/// Without pictures from the server the tiles fill with the brand gradient; without scenes at all it is a calm, indeterminate state with one line.
struct MakingScreen: View {
    let snapshot: MakingSnapshot
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize

    private var heroShape: RoundedRectangle { RoundedRectangle(cornerRadius: Theme.Radii.hero, style: .continuous) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            hero.padding(.top, Theme.Space.s)
            Text(snapshot.title).textRole(.title).foregroundStyle(Theme.text).lineLimit(typeSize.isAccessibilitySize ? 6 : 3).fixedSize(horizontal: false, vertical: true).padding(.top, 26)
                .accessibilityAddTraits(.isHeader).accessibilityIdentifier("makingTitle")
            HStack(alignment: .firstTextBaseline, spacing: 7) {
                Image(systemName: "sparkle").font(.role(.footnote, weight: .bold)).foregroundStyle(Theme.primary).accessibilityHidden(true)
                Text(snapshot.line).font(.role(.subhead, weight: .medium)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                    .contentTransition(.opacity).accessibilityIdentifier("liveLine")
            }
            .padding(.top, Theme.Space.s)
            .animation(Theme.Motion.select, value: snapshot.line)
            if let note = snapshot.note {       // the chosen look was adapted: the server's one sentence, quietly
                HStack(alignment: .firstTextBaseline, spacing: 7) {
                    Image(systemName: "info.circle").font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                    Text(note).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("lookNote")
                }
                .padding(.top, Theme.Space.s)
            }
            strip.padding(.top, 26)
            if snapshot.sceneLine != nil || snapshot.timeAbout != nil {
                ViewThatFits(in: .horizontal) {
                    HStack { counter; Spacer(minLength: Theme.Space.s); about }
                    VStack(alignment: .leading, spacing: 2) { counter; about }
                }
                .font(.role(.footnote)).monospacedDigit().foregroundStyle(Theme.textSecondary).padding(.top, Theme.Space.m)
            }
            if let narration = snapshot.narration {
                Text(tr("making.quote", narration)).textRole(.title, weight: .medium).foregroundStyle(Theme.textSecondary).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 40).id(narration).transition(.opacity).accessibilityIdentifier("narrationLine")
            }
        }
        .padding(.bottom, Theme.Space.xxl)
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.reveal, value: snapshot.narration)
        .onChange(of: snapshot.sceneLine) { _, line in if let line { UIAccessibility.post(notification: .announcement, argument: line) } }     // announced when the scene changes, not on every tick
    }

    @ViewBuilder private var counter: some View { if let s = snapshot.sceneLine { Text(s).accessibilityIdentifier("sceneCounter") } }
    @ViewBuilder private var about: some View { if let t = snapshot.timeAbout { Text(t).accessibilityIdentifier("timeAbout") } }

    /// The scene being built, large. Its picture when the server has one (else the last finished scene's); else the brand gradient, quietly alive.
    private var hero: some View {
        Rectangle().fill(Theme.makingGradient).overlay {
            if let url = snapshot.info?.heroThumb {
                CachedImage(url: url) { $0.resizable().scaledToFill() }.id(ImageKey.stable(url)).transition(.opacity)
            } else {
                Image(systemName: "sparkle").font(.role(.largeTitle)).foregroundStyle(Theme.live).symbolEffect(.pulse, options: .repeating, isActive: !reduceMotion).accessibilityHidden(true)
            }
        }
        .aspectRatio(16.0 / 9.0, contentMode: .fit).frame(maxWidth: .infinity)
        .clipShape(heroShape)
        .overlay(LiveRing(shape: heroShape, lineWidth: 3))
        .elevation(3)
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.reveal, value: ImageKey.stable(snapshot.info?.heroThumb))
        .accessibilityElement().accessibilityLabel(snapshot.spoken).accessibilityAddTraits(.updatesFrequently)
    }

    @ViewBuilder private var strip: some View {
        if let info = snapshot.info, !info.tiles.isEmpty {
            let tiles = info.tiles
            ScrollViewReader { proxy in
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(tiles) { tile in SceneTiles(tiles: [tile], surface: .page, size: 38).frame(width: 38, height: 38).id(tile.index) }
                    }
                }
                .padding(.horizontal, -Theme.gutter).contentMargins(.horizontal, Theme.gutter, for: .scrollContent)       // a long strip runs off the edge and scrolls
                .onChange(of: info.currentScene, initial: true) { _, c in if let c { withAnimation(reduceMotion ? nil : Theme.Motion.spring) { proxy.scrollTo(c, anchor: .center) } } }
            }
            .frame(height: 38)
        } else {
            CalmTrack(onGradient: false).frame(height: 38).accessibilityIdentifier("calmTrack")
        }
    }
}

/// "Tell me when it's ready": one switch. On: the app asks to send notifications and tells the person when the video is ready, if it is not on screen then.
struct NotifyCard: View {
    @State private var notifier = ReadyNotifier.shared
    @State private var denied = false

    var body: some View {
        VStack(spacing: Theme.Space.m) {
            Toggle(isOn: Binding(get: { notifier.enabled }, set: { on in Task { denied = !(await notifier.setEnabled(on)); if on, !denied { Haptics.play(.selection) } } })) {
                HStack(spacing: 14) {
                    Image(systemName: "bell").font(.role(.headline, weight: .regular)).foregroundStyle(Theme.primary).accessibilityHidden(true)
                    Text(tr("making.notify")).font(.role(.headline, weight: .medium)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                }
            }
            .tint(Theme.primary)
            .padding(.horizontal, 18).padding(.vertical, Theme.Space.m).frame(minHeight: 64)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
            .elevation(2)
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
            .onTapGesture { let on = !notifier.enabled; Task { denied = !(await notifier.setEnabled(on)); if on, !denied { Haptics.play(.selection) } } }      // the whole row is the switch
            .accessibilityIdentifier("notifySwitch")
            Text(denied ? tr("making.notify_denied") : tr("making.leave_promise")).font(.role(.caption)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("leavePromise")
        }
        .dynamicTypeSize(...DynamicTypeSize.accessibility2)
        .background(Theme.background)
    }
}

/// Tells the person a video is ready when they are not looking at the app. There is no push from the server yet, so this is what the phone can do by
/// itself: a local notification, posted when the app notices the video is ready while it is in the background (it keeps checking for as long as iOS
/// lets it, and again whenever iOS gives it a background refresh). It can therefore arrive late; it never claims a video is ready that is not.
@MainActor @Observable
final class ReadyNotifier {
    static let shared = ReadyNotifier()
    static let refreshTask = "com.videomk.app.ready"
    private static let key = "notifyWhenReady"

    private(set) var enabled = UserDefaults.standard.bool(forKey: ReadyNotifier.key)
    @ObservationIgnored private var background: UIBackgroundTaskIdentifier = .invalid

    /// Turns the switch on (asking for permission the first time) or off. False when notifications are not allowed: the switch stays off.
    func setEnabled(_ on: Bool) async -> Bool {
        guard on else { enabled = false; UserDefaults.standard.set(false, forKey: Self.key); return true }
        let granted = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])) ?? false
        enabled = granted; UserDefaults.standard.set(granted, forKey: Self.key)
        return granted
    }

    /// A video became ready. Nothing when the switch is off or the person is looking at the app (the list itself shows it, with the success haptic).
    func videoReady(title: String) {
        guard enabled, UIApplication.shared.applicationState != .active else { return }
        let content = UNMutableNotificationContent()
        content.title = tr("making.ready_title"); content.body = title; content.sound = .default
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
    }

    /// The app went to the background while a video is being made: keep checking for as long as iOS allows, and ask for a background refresh after that.
    func appDidEnterBackground(hasRunning: Bool) {
        guard enabled, hasRunning else { return }
        if background == .invalid {
            background = UIApplication.shared.beginBackgroundTask(withName: "videomk.ready") { [weak self] in Task { @MainActor in self?.endBackground() } }
        }
        let request = BGAppRefreshTaskRequest(identifier: Self.refreshTask)
        request.earliestBeginDate = Date().addingTimeInterval(60)
        try? BGTaskScheduler.shared.submit(request)
    }

    func appDidBecomeActive() { endBackground() }

    private func endBackground() {
        guard background != .invalid else { return }
        UIApplication.shared.endBackgroundTask(background); background = .invalid
    }
}
