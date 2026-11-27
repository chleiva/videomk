import SwiftUI
import VideoMKCore

/// Everything the Making card (list) and the Making screen need. Built by `AppModel.makingSnapshot`, so the two can never disagree.
/// Making is a story, not a progress bar (docs/DESIGN_BAR_2026.md, signature 3): scenes, one live line, the narration line. No step names, no percentages.
struct MakingSnapshot: Equatable {
    var title: String
    /// The one live line: the server's ("Adding footage of sunlit canopies"), else one plain line from the status.
    var line: String
    /// Whole minutes left (estimate); nil under a minute. `timed` is false while the request is still being sent (no estimate yet).
    var minutesLeft: Int?
    var timed = true
    /// Scenes, lines and pictures from the server; nil until it reports them (the calm indeterminate state).
    var info: MakingInfo?

    var sceneLine: String? {
        guard let info, let total = info.sceneTotal, let current = info.currentScene else { return nil }
        return tr("making.scene_counter", current, total)
    }
    var narration: String? { info?.narrationLine }
    /// "2 min left" on the card; "About 2 min" on the screen.
    var timeLeft: String? { timed ? (minutesLeft.map { tr("making.min_left", $0) } ?? tr("making.almost_ready")) : nil }
    var timeAbout: String? { timed ? (minutesLeft.map { tr("making.about_min", $0) } ?? tr("making.almost_ready")) : nil }
    /// "Scene 5 of 9 · Finding the right footage".
    var cardLine: String { [sceneLine, line].compactMap { $0 }.joined(separator: " · ") }
    /// What VoiceOver reads for the whole card.
    var spoken: String { tr("videos.making_row_a11y", title, [cardLine, timeLeft].compactMap { $0 }.joined(separator: ". ")) }
}

/// The Making card of the Videos list: the brand gradient, the title, the time left, the scene tiles filling one by one, one live line.
struct MakingCard: View {
    let snapshot: MakingSnapshot
    var onRemove: (() -> Void)?
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline, spacing: Theme.Space.s) {
                Text(snapshot.title).font(.role(.headline)).foregroundStyle(Theme.onPrimary).lineLimit(typeSize.isAccessibilitySize ? 4 : 2).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: Theme.Space.xs)
                if let time = snapshot.timeLeft, !typeSize.isAccessibilitySize { Text(time).font(.role(.footnote, weight: .medium)).monospacedDigit().foregroundStyle(Theme.onPrimary.opacity(0.84)).lineLimit(1).fixedSize() }
                if let onRemove {
                    Menu { Button(tr("videos.remove"), role: .destructive, action: onRemove) } label: { Image(systemName: "ellipsis").font(.role(.headline)).foregroundStyle(Theme.onPrimary).frame(width: Theme.minTouch, height: 24) }
                        .accessibilityLabel(tr("media.more"))
                }
            }
            if let info = snapshot.info, !info.tiles.isEmpty { SceneTiles(tiles: info.window(7), surface: .gradient, size: 46) }
            else { CalmTrack() }
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "sparkle").font(.role(.caption, weight: .bold)).foregroundStyle(Theme.live).accessibilityHidden(true)
                Text(snapshot.cardLine).font(.role(.footnote, weight: .medium)).monospacedDigit().foregroundStyle(Theme.onPrimary.opacity(0.9))
                    .lineLimit(typeSize.isAccessibilitySize ? nil : 2).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            }
            if let time = snapshot.timeLeft, typeSize.isAccessibilitySize { Text(time).font(.role(.footnote, weight: .medium)).foregroundStyle(Theme.onPrimary.opacity(0.84)) }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.makingGradient, in: RoundedRectangle(cornerRadius: Theme.Radii.hero, style: .continuous))
        .shadow(color: Theme.makingStart.opacity(0.3), radius: 18, y: 10)
        .contentShape(RoundedRectangle(cornerRadius: Theme.Radii.hero, style: .continuous))
        .accessibilityElement(children: onRemove == nil ? .ignore : .contain)
        .accessibilityLabel(snapshot.spoken)
    }
}

/// The film strip: one tile per scene. Finished scenes show their picture (or fill with the brand gradient when the server sends none), the scene being made
/// wears the live ring, the rest are outlines. A tile fills with a 200 ms scale-and-fade (Reduce Motion: a fade).
struct SceneTiles: View {
    enum Surface { case gradient, page }      // on the Making card, or on the page
    let tiles: [MakingInfo.Tile]
    var surface: Surface = .page
    var size: CGFloat = Theme.sceneTile
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var radius: CGFloat { size >= 44 ? 12 : 10 }

    var body: some View {
        HStack(spacing: 6) {
            ForEach(tiles) { tile in
                SceneTile(tile: tile, surface: surface, radius: radius)
                    .aspectRatio(1, contentMode: .fit).frame(maxWidth: size, maxHeight: size)
            }
        }
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.tile, value: tiles.map(\.state))
        .accessibilityHidden(true)          // the live line and the scene counter say it in words
    }
}

private struct SceneTile: View {
    let tile: MakingInfo.Tile
    let surface: SceneTiles.Surface
    let radius: CGFloat
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var shape: RoundedRectangle { RoundedRectangle(cornerRadius: radius, style: .continuous) }

    var body: some View {
        ZStack {
            switch tile.state {
            case .upcoming:
                shape.strokeBorder(surface == .gradient ? Theme.onPrimary.opacity(0.24) : Theme.outline, lineWidth: 1.5)
            case .current:
                shape.fill(surface == .gradient ? Theme.onPrimary.opacity(0.22) : Theme.surface3)
                if let url = tile.thumbURL { CachedImage(url: url) { $0.resizable().scaledToFill() }.opacity(0.55) }
            case .done:
                Group {
                    if surface == .gradient { shape.fill(Theme.onPrimary.opacity(0.9)) } else { shape.fill(Theme.makingGradient) }
                    if let url = tile.thumbURL { CachedImage(url: url) { $0.resizable().scaledToFill() } }
                }
                .transition(reduceMotion ? .opacity : .scale(scale: 0.6).combined(with: .opacity))
            }
        }
        .clipShape(shape)
        .overlay { if tile.state == .current { LiveRing(shape: shape, lineWidth: 2) } }
    }
}

/// No scenes from the server (yet): a calm, indeterminate line of light. It never fills and never shows a number.
struct CalmTrack: View {
    var onGradient = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        Capsule().fill(onGradient ? Theme.onPrimary.opacity(0.2) : Theme.surface3)
            .frame(height: 6)
            .overlay {
                if !reduceMotion {
                    TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                        let t = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: DesignTokens.Motion.shimmer) / DesignTokens.Motion.shimmer
                        GeometryReader { geo in
                            Capsule().fill(LinearGradient(colors: [.clear, onGradient ? Theme.onPrimary.opacity(0.85) : Theme.primary.opacity(0.7), .clear], startPoint: .leading, endPoint: .trailing))
                                .frame(width: geo.size.width * 0.4).offset(x: -geo.size.width * 0.4 + geo.size.width * 1.4 * t)
                        }
                    }
                } else { Capsule().fill(onGradient ? Theme.onPrimary.opacity(0.5) : Theme.primary.opacity(0.5)).frame(maxWidth: .infinity).scaleEffect(x: 0.4, anchor: .leading) }
            }
            .clipShape(Capsule())
            .accessibilityHidden(true)
    }
}

extension AppModel {
    /// The snapshot of a running video (list card and Making screen both call this, so they can never disagree).
    func makingSnapshot(for video: VideoItem, now: Date) -> MakingSnapshot {
        let since = stage(for: video.id)
        let stage: VideoStatus.Stage = { if case .running(let s) = video.status { s } else { .starting } }()
        let inStage = since.map { now.timeIntervalSince($0.since) } ?? 0
        let minutes = requestedMinutes(for: video.id)
        let title = brief(for: video.id) ?? (video.title.flatMap { $0.isEmpty ? nil : $0 } ?? tr("detail.making"))
        let info = making(for: video)
        var line = info?.liveLine ?? MakingProgress.info(stage: stage, secondsInStage: inStage, minutes: minutes).what
        // a video made from a presentation: the deck's own two stages come first, in the same line
        if info?.liveLine == nil, case .running(.writing) = video.status, let deck = video.deckStage { line = tr(deck == .reading ? "making.line.deck_reading" : "making.line.deck_writing") }
        return MakingSnapshot(title: title, line: line, minutesLeft: MakingProgress.minutesLeft(stage: stage, secondsInStage: inStage, minutes: minutes), info: info)
    }
}
