import AVFoundation
import SwiftUI
import VideoMKCore

/// The friendly rating question, in a soft sheet. Swipe down or tap outside means "later" with no consequence (docs/FEEDBACK.md, "Rating prompt").
/// Why a store link and not `SKStoreReviewController`: Apple says the system prompt must not be tied to a button (it is rate limited and often shows
/// nothing, so a "Rate" button would silently do nothing), and the write-review page is the one reliable way to take someone to the review box.
/// So "Yes" shows our own warm ask and "Rate videomk" opens `AppStoreInfo.writeReviewURL()`; we never call `requestReview`.
struct RatingPromptView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var stage = Stage.question
    enum Stage { case question, ask, feedback }

    var body: some View {
        Group {
            switch stage {
            case .question: FittedSheet { content(title: tr("rating.question"), body: nil) {
                Button(tr("rating.yes")) { go(.ask) }.buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("ratingYes")
                Button(tr("rating.not_really")) { model.rating.resolve(.notReally); go(.feedback) }.buttonStyle(TonalButtonStyle()).accessibilityIdentifier("ratingNotReally")
            } }
            case .ask: FittedSheet { content(title: tr("rating.ask_title"), body: tr("rating.ask_body")) {
                Button(tr("rating.rate")) { model.rating.resolve(.rate); openURL(AppStoreInfo.writeReviewURL()); dismiss() }.buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("ratingRate")
                Button(tr("rating.later")) { model.rating.resolve(.maybeLater); dismiss() }.buttonStyle(TonalButtonStyle()).accessibilityIdentifier("ratingLater")
                Button(tr("rating.already")) { model.rating.resolve(.alreadyRated); dismiss() }.buttonStyle(TextButtonStyle(tint: Theme.textSecondary)).frame(maxWidth: .infinity).accessibilityIdentifier("ratingAlready")
            } }
            case .feedback: FeedbackSheet(composer: model.makeFeedback(.ratingPrompt), intro: tr("rating.sorry")).presentationDetents([.large]).presentationDragIndicator(.visible)
            }
        }
    }

    private func go(_ s: Stage) { withAnimation(reduceMotion ? nil : Theme.Motion.insert) { stage = s } }

    /// As tall as its words and buttons (never a half-empty sheet): the question, then the app's own pills.
    private func content(title: String, body: String?, @ViewBuilder buttons: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.m) {
            Text(title).textRole(.title).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, Theme.Space.xxl).accessibilityAddTraits(.isHeader)
            if let body { Text(body).font(.role(.body)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true) }
            VStack(spacing: Theme.Space.s) { buttons() }.padding(.top, Theme.Space.s)
        }
    }
}

/// Watches one AVPlayer and tells the rating logic when the video was really watched to the end (rule in `PlaybackCompletion`).
/// Also keeps `model.isPlayingVideo` honest so the prompt never opens over playback.
@MainActor final class PlaybackWatcher {
    private weak var player: AVPlayer?
    private var token: Any?
    private var endObserver: NSObjectProtocol?
    private var statusObserver: NSKeyValueObservation?
    private var completion = PlaybackCompletion()
    private let onComplete: () -> Void
    private let onPlaying: (Bool) -> Void

    init(player: AVPlayer, onPlaying: @escaping (Bool) -> Void, onComplete: @escaping () -> Void) {
        self.player = player; self.onComplete = onComplete; self.onPlaying = onPlaying
        token = player.addPeriodicTimeObserver(forInterval: CMTime(seconds: 0.5, preferredTimescale: 600), queue: .main) { [weak self] time in
            MainActor.assumeIsolated { self?.sample(time.seconds) }
        }
        endObserver = NotificationCenter.default.addObserver(forName: .AVPlayerItemDidPlayToEndTime, object: player.currentItem, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { if let d = self?.duration { self?.sample(d) } }
        }
        statusObserver = player.observe(\.timeControlStatus, options: [.initial, .new]) { [weak self] p, _ in
            let playing = p.timeControlStatus != .paused
            Task { @MainActor in self?.onPlaying(playing) }
        }
    }

    private var duration: Double? { player?.currentItem?.duration.seconds }

    private func sample(_ position: Double) {
        guard !completion.isComplete, let d = duration else { return }
        if completion.observe(position: position, duration: d) { onComplete() }
    }

    func stop() {
        if let token, let player { player.removeTimeObserver(token) }
        token = nil
        if let endObserver { NotificationCenter.default.removeObserver(endObserver) }
        endObserver = nil; statusObserver = nil
        onPlaying(false)
    }
}
