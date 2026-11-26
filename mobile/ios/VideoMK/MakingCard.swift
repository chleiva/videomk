import SwiftUI
import VideoMKCore

/// A scene counter ("Scene 3 of 7"). The server reports stages, not scenes, so this stays nil until the backend sends it; the card already
/// lays it out (seam for docs/UX_REVIEW.md section 4, "per-scene progress").
struct MakingScene: Equatable { var index: Int; var total: Int }

/// Everything the one waiting component needs. Built by `AppModel.makingSnapshot`; the list card and the detail screen render the same value.
struct MakingSnapshot: Equatable {
    var title: String
    var stageLine: String            // "Recording the voice and drawing the pictures."
    var eta: String?                 // "about 2 min left"; nil while the request is still being sent
    var segments: [Double] = [0, 0, 0, 0]
    var current = 0
    var scene: MakingScene?          // seam: per-scene progress from the backend
    var thumbnails: [URL] = []       // seam: poster frames of scenes as they are found (rendered as a strip when present)

    static func make(title: String, info: MakingProgress.Info, minutesLeft: Int?) -> MakingSnapshot {
        MakingSnapshot(title: title, stageLine: info.what, eta: minutesLeft.map { tr("making.eta_short", $0) } ?? tr("making.eta_under_minute"), segments: info.segments, current: info.current)
    }

    /// What VoiceOver reads for the whole card.
    var spoken: String { tr("videos.making_row_a11y", title, [stageLine, scene.map { tr("making.scene_counter", $0.index, $0.total) }, eta].compactMap { $0 }.joined(separator: " ")) }
}

/// The one "making" component. `.list` is the compact card on the home screen, `.detail` the roomier version at the top of the video screen
/// (adds the step checklist and the "you can leave" promise). Same gradient, same stage verbs, same segments: nothing differs between the two
/// but the amount of room.
struct MakingCard: View {
    enum Layout { case list, detail }
    let snapshot: MakingSnapshot
    var layout: Layout = .list
    var onRemove: (() -> Void)?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize

    private var detail: Bool { layout == .detail }
    private var steps: [String] { MakingProgress.steps }

    var body: some View {
        ZStack(alignment: .topLeading) {
            Theme.makingGradient
            shimmer
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .center, spacing: 8) {
                    GlassChip(text: tr("videos.making"), dot: Theme.live)
                    Spacer(minLength: 8)
                    if let eta = snapshot.eta, !typeSize.isAccessibilitySize { Text(eta).font(.vmk(13, weight: .medium)).foregroundStyle(.white.opacity(0.86)).multilineTextAlignment(.trailing) }
                    if let onRemove { Menu { Button(tr("videos.remove"), role: .destructive, action: onRemove) } label: { Image(systemName: "ellipsis").font(.vmk(18, weight: .bold)).foregroundStyle(.white).frame(width: Theme.minTouch, height: Theme.minTouch) }.accessibilityLabel(tr("media.more")) }
                }
                if typeSize.isAccessibilitySize, let eta = snapshot.eta { Text(eta).font(.vmk(13, weight: .medium)).foregroundStyle(.white.opacity(0.86)).padding(.top, 6) }
                if !detail {
                    Text(snapshot.title).font(.vmk(19, weight: .semibold)).foregroundStyle(.white).lineLimit(typeSize.isAccessibilitySize ? 4 : 2).padding(.top, 10)
                }
                Text(snapshot.stageLine).font(.vmk(detail ? 19 : 15, weight: detail ? .semibold : .regular)).foregroundStyle(.white.opacity(detail ? 1 : 0.88)).padding(.top, detail ? 22 : 4)
                    .lineLimit(typeSize.isAccessibilitySize ? nil : 2).fixedSize(horizontal: false, vertical: true)
                if let scene = snapshot.scene {
                    Text(tr("making.scene_counter", scene.index, scene.total)).font(.vmk(15, weight: .medium).monospacedDigit()).foregroundStyle(.white.opacity(0.86)).padding(.top, 2)
                }
                if !snapshot.thumbnails.isEmpty { thumbnailStrip.padding(.top, 12) }
                if detail { checklist.padding(.top, 18) }
                Spacer(minLength: 14)
                segmentBar
            }
            .padding(detail ? 20 : 14)
        }
        .frame(maxWidth: .infinity, minHeight: detail ? 240 : 168)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
        .elevation(2)
        .transition(.opacity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(snapshot.spoken)
    }

    @ViewBuilder private var shimmer: some View {
        if !reduceMotion {
            TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                let t = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: DesignTokens.Motion.shimmer) / DesignTokens.Motion.shimmer
                GeometryReader { geo in
                    LinearGradient(colors: [.clear, .white.opacity(0.22), .clear], startPoint: .leading, endPoint: .trailing)
                        .frame(width: geo.size.width * 0.5).rotationEffect(.degrees(10)).offset(x: -geo.size.width * 0.5 + geo.size.width * 1.5 * t)
                }
            }
            .allowsHitTesting(false)
        } else { Color.white.opacity(0.06) }
    }

    /// Seam: small posters of the scenes found so far (the current one ringed in the live accent).
    private var thumbnailStrip: some View {
        HStack(spacing: 8) {
            ForEach(Array(snapshot.thumbnails.prefix(5).enumerated()), id: \.offset) { i, url in
                CachedImage(url: url) { $0.resizable().scaledToFill() }
                    .frame(maxWidth: .infinity).aspectRatio(16 / 10, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(Theme.live, lineWidth: i == snapshot.thumbnails.count - 1 ? 2 : 0))
            }
        }
        .accessibilityHidden(true)
    }

    private var checklist: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(steps.enumerated()), id: \.offset) { i, name in
                HStack(spacing: 10) {
                    if snapshot.segments.indices.contains(i), snapshot.segments[i] >= 1 { Image(systemName: "checkmark.circle.fill").foregroundStyle(.white) }
                    else if i == snapshot.current { Image(systemName: "circle.lefthalf.filled").foregroundStyle(Theme.live) }
                    else { Image(systemName: "circle").foregroundStyle(.white.opacity(0.6)) }
                    Text(name).font(.vmk(16, weight: i == snapshot.current ? .semibold : .regular)).foregroundStyle(.white.opacity(i <= snapshot.current ? 1 : 0.72))
                }
            }
        }
    }

    private var segmentBar: some View {
        HStack(alignment: .top, spacing: 8) {
            ForEach(Array(steps.enumerated()), id: \.offset) { i, name in
                VStack(alignment: .leading, spacing: 8) {
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            Capsule().fill(.white.opacity(0.24))
                            Capsule().fill(.white).frame(width: g.size.width * (snapshot.segments.indices.contains(i) ? snapshot.segments[i] : 0))
                                .animation(reduceMotion ? nil : .linear(duration: 1), value: snapshot.segments)       // continuous between the one-second ticks
                        }
                    }.frame(height: 4)
                    if !detail && (!typeSize.isAccessibilitySize || i == snapshot.current) {
                        Text(name).font(.vmk(12, weight: i == snapshot.current ? .bold : .regular)).foregroundStyle(i == snapshot.current ? .white : .white.opacity(0.8)).lineLimit(typeSize.isAccessibilitySize ? 2 : 1).minimumScaleFactor(0.8)
                    }
                }
                .frame(maxWidth: typeSize.isAccessibilitySize && i != snapshot.current ? 24 : .infinity, alignment: .leading)
            }
        }
    }
}

extension AppModel {
    /// The snapshot of a running video (list card and detail screen both call this, so they can never disagree).
    func makingSnapshot(for video: VideoItem, now: Date) -> MakingSnapshot {
        let info = stage(for: video.id)
        let stage: VideoStatus.Stage = { if case .running(let s) = video.status { s } else { .starting } }()
        let inStage = info.map { now.timeIntervalSince($0.since) } ?? 0
        let minutes = requestedMinutes(for: video.id)
        let progress = MakingProgress.info(stage: stage, secondsInStage: inStage, minutes: minutes)
        let title = brief(for: video.id) ?? (video.title.flatMap { $0.isEmpty ? nil : $0 } ?? tr("detail.making"))
        var snapshot = MakingSnapshot.make(title: title, info: progress, minutesLeft: MakingProgress.minutesLeft(stage: stage, secondsInStage: inStage, minutes: minutes))
        // a video made from a presentation: the deck's own two stages come first, in the same stage line
        if case .running(.writing) = video.status, let deck = video.deckStage { snapshot.stageLine = tr(deck == .reading ? "making.line.deck_reading" : "making.line.deck_writing") }
        return snapshot
    }
}
