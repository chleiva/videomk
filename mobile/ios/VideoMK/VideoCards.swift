import SwiftUI
import VideoMKCore

/// The cards of the Videos list (docs/DESIGN_BAR_2026.md, `phone_2_videos`): the Making card (MakingCard.swift), posters for finished videos (the first
/// one large), and one calm card for a video that did not finish. Content is the colour; the cards themselves are neutral.

/// A small dark chip on a picture (the duration, the frame shape).
struct GlassChip: View {
    let text: String
    var symbol: String?
    var body: some View {
        HStack(spacing: 4) {
            if let symbol { Image(systemName: symbol).font(.role(.caption, weight: .bold)).accessibilityHidden(true) }
            Text(text).font(.role(.caption, weight: .semibold)).monospacedDigit().lineLimit(1)
        }
        .foregroundStyle(Theme.onMedia).padding(.horizontal, 8).frame(minHeight: 24)
        .background(Theme.mediaInk.opacity(0.6), in: Capsule())
    }
}

/// A video's picture, filling the frame it is given (the caller decides the shape). A vertical or square picture in a wide frame is shown whole over a
/// soft copy of itself, never stretched. The duration sits on the picture.
struct Poster: View {
    let video: VideoItem
    var radius: CGFloat = Theme.Radii.videoCard
    /// The frame is close to the video's own shape, or a crop is fine (grid tiles): fill it.
    var fill = true

    var body: some View {
        Theme.surfaceRaised
            .overlay {       // an overlay: a picture of another shape never changes the frame it is given
                if let url = video.previewGifURL {
                    CachedImage(url: url) { image in
                        if fill { image.resizable().scaledToFill() }
                        else { ZStack { Color.clear.overlay { image.resizable().scaledToFill().blur(radius: 18).opacity(0.7) }; image.resizable().scaledToFit() } }
                    }
                } else {
                    Theme.makingGradient.opacity(0.9)
                    Image(systemName: "play.fill").font(.role(.title)).foregroundStyle(Theme.onPrimary.opacity(0.92)).accessibilityHidden(true)
                }
            }
            .clipped()
            .overlay(alignment: .bottomTrailing) { if let d = video.durationSeconds { GlassChip(text: VideoRow.duration(d)).padding(10) } }
        .overlay(alignment: .topLeading) { if video.aspect != nil, video.isPortrait { GlassChip(text: video.aspect ?? "").padding(10) } }
        .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
    }
}

/// A finished video: its poster with the title beneath (two lines) and, on the large first one, when it was made.
struct VideoRow: View {
    let video: VideoItem
    /// The poster's height; nil keeps the video's own shape at full width (the large first poster).
    var posterHeight: CGFloat?
    var meta: String?
    var note: String?           // "Your first video."

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Group {
                if let posterHeight { Poster(video: video, radius: Theme.Radii.card).frame(height: posterHeight) }
                else { Poster(video: video, fill: abs(video.aspectRatio - 16.0 / 9.0) < 0.15).aspectRatio(16.0 / 9.0, contentMode: .fit) }
            }
            .frame(maxWidth: .infinity)
            Text(video.displayTitle).font(.role(.headline)).foregroundStyle(Theme.text).lineLimit(2).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true).padding(.top, posterHeight == nil ? 12 : 10)
            if let note { Text(note).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.primary).padding(.top, 2).accessibilityIdentifier("firstVideoNote") }
            else if let meta { Text(meta).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).padding(.top, 1) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([tr("videos.ready_a11y", video.displayTitle), video.isPortrait ? tr("videos.vertical_a11y") : nil, video.durationSeconds.map { tr("videos.duration_a11y", Self.duration($0)) }, meta].compactMap { $0 }.joined(separator: " "))
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("videoRow")
    }

    static func formatName(_ aspect: String?) -> String {
        switch aspect { case "9:16": tr("aspect.vertical"); case "1:1": tr("aspect.square"); case "4:5": tr("aspect.portrait"); default: tr("aspect.landscape") }
    }

    static func duration(_ s: Double) -> String { Localization.shared.clock(seconds: s) }
}

/// Did not finish (or was not allowed): one calm card. The mark carries the colour; the words stay in the text colours. One action (Try again) and
/// Remove in the menu. Nothing was lost: Try again restarts the same video with everything it was made with.
struct FailedRow: View {
    let title: String
    var message: String?
    var retry: (() -> Void)?
    var onRemove: (() -> Void)?
    var rejected = false
    var cancelled = false       // the person stopped it: a calm mark and its own word, not an error
    var onPage = false          // on the video's own page: Remove is a labelled button beside Try again (no menu), and the card has no shadow of its own

    private var status: String { rejected ? tr("videos.not_allowed") : cancelled ? tr("videos.cancelled") : tr("videos.didnt_finish") }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.m) {
            HStack(alignment: .top, spacing: Theme.Space.m) {
                Image(systemName: rejected ? "hand.raised" : cancelled ? "xmark" : "exclamationmark").font(.role(.headline)).foregroundStyle(rejected ? Theme.warning : cancelled ? Theme.textSecondary : Theme.danger)
                    .frame(width: Theme.iconButton, height: Theme.iconButton).background(rejected ? Theme.warningContainer : cancelled ? Theme.surfaceRaised : Theme.dangerContainer, in: Circle()).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.role(.headline)).foregroundStyle(Theme.text).lineLimit(3).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                    Text(message.map { tr("videos.row_meta", status, $0) } ?? status).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let onRemove, !onPage {
                    Menu { Button(tr("videos.remove"), role: .destructive, action: onRemove) } label: { Image(systemName: "ellipsis").font(.role(.headline)).foregroundStyle(Theme.textSecondary).frame(width: Theme.minTouch, height: Theme.minTouch).contentShape(Rectangle()) }
                        .accessibilityLabel(tr("media.more")).accessibilityIdentifier("failedMore").padding(.top, -8).padding(.trailing, -10)
                }
            }
            if let retry {
                Button(action: retry) { Label(tr("common.try_again"), systemImage: "arrow.clockwise") }
                    .buttonStyle(TonalButtonStyle()).accessibilityIdentifier("tryAgain")
            }
            if onPage, let onRemove {
                Button(tr("videos.remove"), action: onRemove).buttonStyle(TextButtonStyle(tint: Theme.danger)).frame(maxWidth: .infinity).accessibilityIdentifier("removeVideo")
            }
        }
        .padding(Theme.Space.l).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
        .elevation(2)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(tr("videos.failed_row_a11y", title, status, message ?? tr("videos.no_credits_were_used")))
    }
}

/// The list while it loads: the shapes of what is coming (a large poster, then two side by side), softly breathing. Reduce Motion: still.
struct VideosSkeleton: View {
    @State private var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.xl) {
            VStack(alignment: .leading, spacing: Theme.Space.m) {
                block(Theme.Radii.videoCard).aspectRatio(16.0 / 9.0, contentMode: .fit)
                block(6).frame(width: 190, height: 16)
                block(6).frame(width: 70, height: 12)
            }
            HStack(alignment: .top, spacing: Theme.Space.m) {
                ForEach(0..<2, id: \.self) { _ in VStack(alignment: .leading, spacing: 10) { block(Theme.Radii.card).frame(height: 127); block(6).frame(width: 110, height: 16) } }
            }
        }
        .opacity(pulse && !reduceMotion ? 0.55 : 1)
        .onAppear { if !reduceMotion { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { pulse = true } } }
        .accessibilityHidden(true)
    }
    private func block(_ radius: CGFloat) -> some View { RoundedRectangle(cornerRadius: radius, style: .continuous).fill(Theme.surfaceRaised) }
}

/// A video the server is making: the Making card, ticking once a second.
struct RunningCard: View {
    @Environment(AppModel.self) private var model
    let video: VideoItem

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            MakingCard(snapshot: model.makingSnapshot(for: video, now: context.date), onCancel: model.cancelling.contains(video.id) ? nil : { model.cancelVideo(video) })
        }
        .accessibilityIdentifier("runningRow")
    }
}

/// A video that has just been asked for (the server has not listed it yet), or whose photos are still going up.
struct PendingCard: View {
    let pending: PendingVideo
    let onRetry: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        Group {
            if case .failed(let message) = pending.state {
                FailedRow(title: pending.brief, message: message.isEmpty ? tr("videos.no_credits_were_used") : tr("videos.message_no_credits", message), retry: onRetry, onRemove: onDismiss)
                    .accessibilityIdentifier("failedRow")
            } else {
                MakingCard(snapshot: MakingSnapshot(title: pending.brief, line: line, timed: false))
                    .accessibilityIdentifier("pendingRow")
            }
        }
    }

    private var line: String {
        if case .uploading(let done, let total) = pending.state { return tr("videos.uploading_photos", max(1, done), total) }      // no number starts at zero
        return tr("create.starting_your_video")
    }
}
