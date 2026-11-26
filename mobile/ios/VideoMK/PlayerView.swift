import AVKit
import SwiftUI
import VideoMKCore

/// The system player (scrubbing, captions, AirPlay, Picture in Picture) wrapped directly.
struct PlayerController: UIViewControllerRepresentable {
    let player: AVPlayer?

    func makeUIViewController(context: Context) -> AVPlayerViewController {
        let vc = AVPlayerViewController()
        vc.allowsPictureInPicturePlayback = true
        vc.showsPlaybackControls = true
        vc.videoGravity = .resizeAspect
        vc.player = player
        return vc
    }

    func updateUIViewController(_ vc: AVPlayerViewController, context: Context) {
        if vc.player !== player { vc.player = player }
    }
}

enum PlaybackAudio {
    /// Narration must be heard with the silent switch on (the video is the content, like a movie), and other audio gives way to it.
    static func prepare() {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
        try? AVAudioSession.sharedInstance().setActive(true)
    }
}

/// Full screen is a plain UIKit modal presentation that declares itself landscape-only, so UIKit itself rotates the phone and lays the video out
/// (SwiftUI covers and geometry requests left the content stuck at the portrait size). It keeps playing from the same moment.
final class LandscapePlayerController: AVPlayerViewController {
    var onClose: (() -> Void)?

    override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .landscape }
    override var preferredInterfaceOrientationForPresentation: UIInterfaceOrientation { .landscapeRight }
    override var prefersStatusBarHidden: Bool { true }
    override var prefersHomeIndicatorAutoHidden: Bool { true }

    override func viewDidLoad() {
        super.viewDidLoad()
        let close = UIButton(type: .system)
        close.setImage(UIImage(systemName: "xmark", withConfiguration: UIImage.SymbolConfiguration(pointSize: 15, weight: .bold)), for: .normal)
        close.tintColor = .white
        close.backgroundColor = UIColor.black.withAlphaComponent(0.55)
        close.layer.cornerRadius = 20
        close.accessibilityLabel = tr("player.close_full_screen")
        close.accessibilityIdentifier = "closeFullScreenButton"
        close.translatesAutoresizingMaskIntoConstraints = false
        close.addAction(UIAction { [weak self] _ in self?.dismiss(animated: true) }, for: .touchUpInside)
        contentOverlayView?.addSubview(close)
        if let overlay = contentOverlayView {
            NSLayoutConstraint.activate([
                close.widthAnchor.constraint(equalToConstant: 40), close.heightAnchor.constraint(equalToConstant: 40),
                close.topAnchor.constraint(equalTo: overlay.safeAreaLayoutGuide.topAnchor, constant: 12),
                close.leadingAnchor.constraint(equalTo: overlay.safeAreaLayoutGuide.leadingAnchor, constant: 16),
            ])
        }
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isBeingDismissed { onClose?() }
    }
}

/// Vertical and square videos open full screen in portrait (the phone is not turned sideways for them).
final class PortraitPlayerController: AVPlayerViewController {
    var onClose: (() -> Void)?
    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isBeingDismissed { onClose?() }
    }
}

@MainActor enum FullScreen {
    static func present(_ player: AVPlayer, landscape: Bool = true, onClose: @escaping () -> Void) {
        guard let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first(where: { $0.activationState == .foregroundActive }) ?? UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first,
              var top = scene.keyWindow?.rootViewController else { onClose(); return }
        while let next = top.presentedViewController { top = next }
        PlaybackAudio.prepare()
        if landscape {
            let vc = LandscapePlayerController()
            vc.player = player
            vc.allowsPictureInPicturePlayback = true
            vc.modalPresentationStyle = .fullScreen
            vc.onClose = onClose
            top.present(vc, animated: true) { player.play() }
        } else {
            let vc = PortraitPlayerController()
            vc.player = player
            vc.videoGravity = .resizeAspect
            vc.allowsPictureInPicturePlayback = true
            vc.modalPresentationStyle = .fullScreen
            vc.onClose = onClose
            top.present(vc, animated: true) { player.play() }
        }
    }
}

/// An inline player with a full screen button. It fills the frame it is given; the caller sizes it to the video's own shape.
struct InlinePlayer: View {
    let player: AVPlayer
    var landscape = true
    @State private var fullScreen = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            PlayerController(player: fullScreen ? nil : player)   // one screen owns the player at a time
            Button {
                fullScreen = true
                FullScreen.present(player, landscape: landscape) { fullScreen = false }
            } label: {
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.system(size: 15, weight: .bold)).foregroundStyle(.white)
                    .frame(width: 40, height: 40)
                    .background(.black.opacity(0.55), in: Circle())
            }
            .padding(10)
            .accessibilityLabel(tr("player.full_screen"))
            .accessibilityIdentifier("fullScreenButton")
        }
        .onAppear { PlaybackAudio.prepare() }
    }
}
