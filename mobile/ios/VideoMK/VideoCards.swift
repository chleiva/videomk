import SwiftUI
import VideoMKCore

/// The rows of the video list (docs/UX_REVIEW.md, mockup 01): thumbnail rows for ready videos, the one MakingCard for videos in progress,
/// a calm danger-container row for ones that did not finish. Layouts switch to a stacked form at accessibility text sizes.

struct GlassChip: View {
    let text: String
    var dot: Color?
    var symbol: String?
    var fill: Color = .black.opacity(0.38)
    var body: some View {
        HStack(spacing: 6) {
            if let dot { Circle().fill(dot).frame(width: 8, height: 8) }
            if let symbol { Image(systemName: symbol).font(.vmk(12, weight: .bold)) }
            Text(text).font(.vmk(14, weight: .semibold)).lineLimit(2)
        }
        .foregroundStyle(.white).padding(.horizontal, 11).frame(minHeight: 28)
        .background(fill, in: Capsule())
    }
}

/// A video's picture at 16:9: a vertical or square picture is shown whole over a soft copy of itself, never stretched or cropped to a strip.
struct VideoThumb: View {
    let video: VideoItem
    var showsDuration = true
    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            Theme.makingGradient.opacity(0.55)
            if let url = video.previewGifURL {
                CachedImage(url: url) { image in
                    if abs(video.aspectRatio - 16.0 / 9.0) < 0.15 { image.resizable().scaledToFill() }
                    else { ZStack { image.resizable().scaledToFill().blur(radius: 18).opacity(0.7); image.resizable().scaledToFit() } }
                }
            } else {
                Image(systemName: "play.fill").font(.vmk(20)).foregroundStyle(.white.opacity(0.9)).frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            if showsDuration, let d = video.durationSeconds {
                Text(VideoRow.duration(d)).font(.vmk(12, weight: .semibold).monospacedDigit()).foregroundStyle(.white)
                    .padding(.horizontal, 7).frame(height: 20).background(.black.opacity(0.55), in: Capsule()).padding(6)
            }
        }
        .aspectRatio(16.0 / 9.0, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
    }
}

/// A finished video: 128 x 72 thumbnail with the duration on the picture, a two-line title and a quiet meta line.
struct VideoRow: View {
    let video: VideoItem
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let stacked = typeSize.isAccessibilitySize
        let layout = stacked ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10)) : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
        layout {
            VideoThumb(video: video).frame(maxWidth: stacked ? .infinity : CGFloat(DesignTokens.Size.thumbWidth))
            VStack(alignment: .leading, spacing: 3) {
                Text(video.displayTitle).font(.vmk(16, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(stacked ? 4 : 2).multilineTextAlignment(.leading)
                Text(meta).font(.vmk(13)).foregroundStyle(Theme.textSecondary).lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 6).frame(minHeight: Theme.minTouch).contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([tr("videos.ready_a11y", video.displayTitle), video.isPortrait ? tr("videos.vertical_a11y") : nil, video.durationSeconds.map { tr("videos.duration_a11y", Self.duration($0)) }].compactMap { $0 }.joined(separator: " "))
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("videoRow")
    }

    /// "Landscape · 2 hr. ago", one localized format string (never a sentence glued from parts).
    private var meta: String {
        let format = video.aspect == nil ? nil : Self.formatName(video.aspect)
        let when = video.createdAt.map { Localization.shared.relativeShort($0) }
        switch (format, when) {
        case let (f?, w?): return tr("videos.row_meta", f, w)
        case let (f?, nil): return f
        case let (nil, w?): return w
        default: return ""
        }
    }

    static func formatName(_ aspect: String?) -> String {
        switch aspect { case "9:16": tr("aspect.vertical"); case "1:1": tr("aspect.square"); case "4:5": tr("aspect.portrait"); default: tr("aspect.landscape") }
    }

    static func duration(_ s: Double) -> String { Localization.shared.clock(seconds: s) }
}

/// Did not finish (or was not allowed): the same row shape, in the danger (or warning) container, with the one action and the reassurance.
struct FailedRow: View {
    let title: String
    let message: String
    var retry: (() -> Void)?
    var onRemove: (() -> Void)?
    var rejected = false
    @Environment(\.dynamicTypeSize) private var typeSize

    private var tint: Color { rejected ? Theme.warning : Theme.danger }
    private var container: Color { rejected ? Theme.warningContainer : Theme.dangerContainer }
    private var status: String { rejected ? tr("videos.not_allowed") : tr("videos.didnt_finish") }

    var body: some View {
        let stacked = typeSize.isAccessibilitySize
        let layout = stacked ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10)) : AnyLayout(HStackLayout(alignment: .top, spacing: 12))
        layout {
            Image(systemName: rejected ? "hand.raised" : "exclamationmark").font(.vmk(24, weight: .semibold)).foregroundStyle(tint)
                .frame(maxWidth: stacked ? .infinity : CGFloat(DesignTokens.Size.thumbWidth), minHeight: CGFloat(DesignTokens.Size.thumbHeight), maxHeight: stacked ? 72 : CGFloat(DesignTokens.Size.thumbHeight))
                .background(tint.opacity(0.14), in: RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous)).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top) {
                    Text(title).font(.vmk(16, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(stacked ? 4 : 2).frame(maxWidth: .infinity, alignment: .leading)
                    if let onRemove { Menu { Button(tr("videos.remove"), role: .destructive, action: onRemove) } label: { Image(systemName: "ellipsis").font(.vmk(16, weight: .bold)).foregroundStyle(Theme.textSecondary).frame(width: Theme.minTouch, height: Theme.minTouch) }.accessibilityLabel(tr("media.more")).padding(.top, -10).padding(.trailing, -10) }
                }
                Text(tr("videos.row_meta", status, message)).font(.vmk(13, weight: .medium)).foregroundStyle(tint).fixedSize(horizontal: false, vertical: true)
                if let retry {
                    Button(action: retry) {
                        Label(tr("common.try_again"), systemImage: "arrow.clockwise").font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.primary).frame(minHeight: Theme.minTouch)
                    }.buttonStyle(.plain).accessibilityIdentifier("tryAgain")
                }
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(container, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(tr("videos.failed_row_a11y", title, status, message))
    }
}

/// Placeholder row with the final size while the list loads.
struct SkeletonCard: View {
    @State private var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous).fill(Theme.surfaceRaised).frame(width: CGFloat(DesignTokens.Size.thumbWidth), height: CGFloat(DesignTokens.Size.thumbHeight))
            VStack(alignment: .leading, spacing: 8) {
                RoundedRectangle(cornerRadius: 6).fill(Theme.surfaceRaised).frame(height: 16)
                RoundedRectangle(cornerRadius: 6).fill(Theme.surfaceRaised).frame(width: 90, height: 12)
            }
        }
        .opacity(pulse && !reduceMotion ? 0.55 : 1)
        .onAppear { if !reduceMotion { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { pulse = true } } }
        .accessibilityHidden(true)
    }
}

/// A video the server is making (live stage) or that has not been listed yet: the shared MakingCard in its list form.
struct RunningCard: View {
    @Environment(AppModel.self) private var model
    let video: VideoItem

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            MakingCard(snapshot: model.makingSnapshot(for: video, now: context.date))
        }
        .accessibilityIdentifier("runningRow")
    }
}

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
                MakingCard(snapshot: MakingSnapshot(title: pending.brief, stageLine: line, eta: nil))
                    .accessibilityIdentifier("pendingRow")
            }
        }
    }

    private var line: String {
        if case .uploading(let done, let total) = pending.state { return tr("videos.uploading_photos", done, total) }
        return tr("composer.sending")
    }
}
