import AVKit
import SwiftUI
import VideoMKCore

/// iPhone is a portrait app. The one exception is the system player's own full screen: while it is up, a wide video turns the screen sideways,
/// and leaving full screen turns it back. iPad keeps every orientation.
@MainActor enum OrientationLock {
    static let resting: UIInterfaceOrientationMask = UIDevice.current.userInterfaceIdiom == .pad ? .all : .portrait
    private(set) static var mask: UIInterfaceOrientationMask = resting

    /// The player went full screen: a wide video is shown sideways (the phone need not be turned), a vertical or square one stays upright.
    static func enterFullScreen(landscape: Bool) {
        guard UIDevice.current.userInterfaceIdiom != .pad else { return }
        apply(landscape ? .landscape : .portrait)
    }

    static func leaveFullScreen() { apply(resting) }

    static func reapply() { let m = mask; mask = []; apply(m) }

    private static func apply(_ new: UIInterfaceOrientationMask) {
        guard new != mask else { return }
        mask = new
        for scene in UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }) {
            scene.requestGeometryUpdate(.iOS(interfaceOrientations: new)) { _ in }
            for window in scene.windows {
                var vc = window.rootViewController
                while let v = vc { v.setNeedsUpdateOfSupportedInterfaceOrientations(); vc = v.presentedViewController }
            }
        }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication, supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask { OrientationLock.mask }
}

/// The system player (scrubbing, captions, AirPlay, Picture in Picture, and the ONE full-screen control: the system's own) wrapped directly.
struct PlayerController: UIViewControllerRepresentable {
    let player: AVPlayer?
    var landscape = true

    func makeCoordinator() -> Coordinator { Coordinator(landscape: landscape) }

    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let vc = AVPlayerViewController()
        vc.allowsPictureInPicturePlayback = true
        vc.showsPlaybackControls = true
        vc.videoGravity = .resizeAspect
        vc.delegate = context.coordinator
        vc.player = player
        return vc
    }

    func updateUIViewController(_ vc: AVPlayerViewController, context: Context) {
        context.coordinator.landscape = landscape
        if vc.player !== player { vc.player = player }
    }

    static func dismantleUIViewController(_ vc: AVPlayerViewController, coordinator: Coordinator) { OrientationLock.leaveFullScreen() }

    @MainActor final class Coordinator: NSObject, @preconcurrency AVPlayerViewControllerDelegate {
        var landscape: Bool
        init(landscape: Bool) { self.landscape = landscape }

        func playerViewController(_ playerViewController: AVPlayerViewController, willBeginFullScreenPresentationWithAnimationCoordinator coordinator: any UIViewControllerTransitionCoordinator) {
            let landscape = landscape
            OrientationLock.enterFullScreen(landscape: landscape)
            coordinator.animate(alongsideTransition: nil) { context in
                let cancelled = context.isCancelled
                Task { @MainActor in if cancelled { OrientationLock.leaveFullScreen() } else { OrientationLock.reapply() } }
            }
        }

        func playerViewController(_ playerViewController: AVPlayerViewController, willEndFullScreenPresentationWithAnimationCoordinator coordinator: any UIViewControllerTransitionCoordinator) {
            let landscape = landscape
            OrientationLock.leaveFullScreen()          // the page underneath is upright again while the player shrinks back into it
            coordinator.animate(alongsideTransition: nil) { context in
                if context.isCancelled { Task { @MainActor in OrientationLock.enterFullScreen(landscape: landscape) } }
            }
        }
    }
}

enum PlaybackAudio {
    /// Narration must be heard with the silent switch on (the video is the content, like a movie), and other audio gives way to it.
    static func prepare() {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        try? AVAudioSession.sharedInstance().setActive(true)
    }
}

/// The inline player. It fills the frame it is given; the caller sizes it to the video's own shape. Full screen is the system control's.
struct InlinePlayer: View {
    let player: AVPlayer
    var landscape = true

    var body: some View {
        PlayerController(player: player, landscape: landscape)
            .accessibilityIdentifier("player")
            .onAppear { PlaybackAudio.prepare() }
    }
}
