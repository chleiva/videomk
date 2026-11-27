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
    /// One bar for the whole job (the four stage segments averaged): the stage verb already says where it is.
    private var fraction: Double { let v = snapshot.segments; return v.isEmpty ? 0 : min(1, max(0, v.reduce(0, +) / Double(v.count))) }
    /// "Scene 3 of 7", else the estimate: one quiet second line.
    private var detailLine: String? {
        let parts = [snapshot.scene.map { tr("making.scene_counter", $0.index, $0.total) }, snapshot.eta].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    var body: some View {
        ZStack(alignment: .topLeading) {
            Theme.makingGradient
            shimmer
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 8) {
                    if detail {
                        Text(snapshot.stageLine).font(.vmk(22, weight: .bold)).foregroundStyle(.white).lineLimit(typeSize.isAccessibilitySize ? nil : 2).fixedSize(horizontal: false, vertical: true)
                    } else {
                        Text(snapshot.title).font(.vmk(19, weight: .semibold)).foregroundStyle(.white).lineLimit(typeSize.isAccessibilitySize ? 4 : 2).fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 4)
                    if onRemove != nil, let onRemove { Menu { Button(tr("videos.remove"), role: .destructive, action: onRemove) } label: { Image(systemName: "ellipsis").font(.vmk(18, weight: .bold)).foregroundStyle(.white).frame(width: Theme.minTouch, height: Theme.minTouch) }.accessibilityLabel(tr("media.more")).padding(.top, -10).padding(.trailing, -10) }
                }
                if detail {
                    if let line = detailLine { Text(line).font(.vmk(15, weight: .medium).monospacedDigit()).foregroundStyle(.white.opacity(0.88)).padding(.top, 6) }
                } else {
                    HStack(spacing: 6) {
                        Circle().fill(Theme.live).frame(width: 7, height: 7).accessibilityHidden(true)
                        Text([snapshot.stageLine, snapshot.scene.map { tr("making.scene_counter", $0.index, $0.total) }].compactMap { $0 }.joined(separator: " · "))
                            .font(.vmk(15)).foregroundStyle(.white.opacity(0.9)).lineLimit(typeSize.isAccessibilitySize ? nil : 1).fixedSize(horizontal: false, vertical: true)
                    }.padding(.top, 6)
                }
                if !snapshot.thumbnails.isEmpty { thumbnailStrip.padding(.top, 14) }
                Spacer(minLength: detail ? 22 : 12)
                progressBar
            }
            .padding(detail ? 20 : 16)
        }
        .frame(maxWidth: .infinity, minHeight: detail ? 150 : 108)
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

    private var progressBar: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(.white.opacity(0.24))
                Capsule().fill(.white).frame(width: max(6, g.size.width * fraction))
                    .animation(reduceMotion ? nil : .linear(duration: 1), value: fraction)       // continuous between the one-second ticks
            }
        }
        .frame(height: 4).accessibilityHidden(true)
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
