import SwiftUI
import VideoMKCore

/// The feed cards of docs/UI_DESIGN.md (d): one vertical card type, the picture leads. Ready, Making and Didn’t finish.
private let cardRadius: CGFloat = 22
private let cardHeight: CGFloat = 190

private struct GlassChip: View {
    let text: String
    var dot: Color?
    var symbol: String?
    var fill: Color = .black.opacity(0.38)
    var body: some View {
        HStack(spacing: 6) {
            if let dot { Circle().fill(dot).frame(width: 8, height: 8) }
            if let symbol { Image(systemName: symbol).font(.system(size: 12, weight: .bold)) }
            Text(text).font(.system(size: 14, weight: .semibold))
        }
        .foregroundStyle(.white).padding(.horizontal, 11).frame(height: 28)
        .background(fill, in: Capsule())
    }
}

struct ReadyCard: View {
    let video: VideoItem
    var body: some View {
        ZStack {
            Theme.makingGradient.opacity(0.55)
            if let url = video.previewGifURL {
                CachedImage(url: url) { image in
                    if abs(video.aspectRatio - 16.0 / 9.0) < 0.15 { image.resizable().scaledToFill() }
                    else {   // a vertical or square picture is shown whole, over a soft copy of itself: never stretched, never cropped to a strip
                        ZStack { image.resizable().scaledToFill().blur(radius: 24).opacity(0.7); image.resizable().scaledToFit() }
                    }
                }
            }
            Theme.mediaScrim
            VStack(alignment: .leading, spacing: 0) {
                HStack { GlassChip(text: "Ready", dot: Color(hex: 0x4ADE80)); Spacer() }
                Spacer()
                HStack(alignment: .bottom) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(video.displayTitle).font(.system(size: 18, weight: .semibold)).foregroundStyle(.white).lineLimit(2)
                        if let created = video.createdAt { Text(VideoRow.relative.localizedString(for: created, relativeTo: .now)).font(.system(size: 13, weight: .medium)).foregroundStyle(.white.opacity(0.78)) }
                    }
                    Spacer(minLength: 8)
                    if let d = video.durationSeconds {
                        Text(VideoRow.duration(d)).font(.system(size: 13, weight: .semibold).monospacedDigit()).foregroundStyle(.white)
                            .padding(.horizontal, 9).frame(height: 26).background(.black.opacity(0.4), in: Capsule())
                    }
                }
            }
            .padding(14)
            Image(systemName: "play.fill").font(.system(size: 20)).foregroundStyle(.white).frame(width: 52, height: 52).background(.ultraThinMaterial, in: Circle()).environment(\.colorScheme, .dark)
        }
        .frame(height: cardHeight).frame(maxWidth: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: cardRadius, style: .continuous))
        .elevation(2)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(video.displayTitle). Ready.\(video.isPortrait ? " Vertical." : "")\(video.durationSeconds.map { " \(VideoRow.duration($0))." } ?? "")")
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("videoRow")
    }
}

/// In progress: named steps, an honest line, no percent and no spinner.
struct MakingCard: View {
    let title: String
    let line: String
    let segments: [Double]
    let current: Int
    var onRemove: (() -> Void)?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        ZStack(alignment: .topLeading) {
            Theme.makingGradient
            if !reduceMotion {
                TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                    let t = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.4) / 2.4
                    GeometryReader { geo in
                        LinearGradient(colors: [.clear, .white.opacity(0.28), .clear], startPoint: .leading, endPoint: .trailing)
                            .frame(width: geo.size.width * 0.5).rotationEffect(.degrees(10)).offset(x: -geo.size.width * 0.5 + geo.size.width * 1.5 * t)
                    }
                }
                .allowsHitTesting(false)
            } else { Color.white.opacity(0.08) }
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    GlassChip(text: "Making", dot: Color(hex: 0xC9CBFF))
                    Spacer()
                    if let onRemove { Menu { Button("Remove", role: .destructive, action: onRemove) } label: { Image(systemName: "ellipsis").font(.system(size: 18, weight: .bold)).foregroundStyle(.white).frame(width: 44, height: 44) }.accessibilityLabel("More") }
                }
                Text(title).font(.system(size: 19, weight: .semibold)).foregroundStyle(.white).lineLimit(typeSize.isAccessibilitySize ? 4 : 2).padding(.top, 10)
                Text(line).font(.system(size: 15)).foregroundStyle(.white.opacity(0.82)).padding(.top, 4).lineLimit(typeSize.isAccessibilitySize ? nil : 2)
                Spacer(minLength: 12)
                HStack(spacing: 8) {
                    ForEach(Array(MakingProgress.steps.enumerated()), id: \.offset) { i, name in
                        VStack(alignment: .leading, spacing: 8) {
                            GeometryReader { g in
                                ZStack(alignment: .leading) {
                                    Capsule().fill(.white.opacity(0.22))
                                    Capsule().fill(Color(hex: 0xC9CBFF)).frame(width: g.size.width * (segments.indices.contains(i) ? segments[i] : 0))
                                        .animation(reduceMotion ? nil : .linear(duration: 1), value: segments)       // continuous between the one-second ticks
                                }
                            }.frame(height: 4)
                            Text(name).font(.system(size: 12.5, weight: i == current ? .bold : .regular)).foregroundStyle(i == current ? .white : .white.opacity(0.72)).lineLimit(1).minimumScaleFactor(0.8)
                        }
                    }
                }
            }
            .padding(14)
        }
        .frame(height: typeSize.isAccessibilitySize ? nil : cardHeight).frame(minHeight: typeSize.isAccessibilitySize ? cardHeight : nil).frame(maxWidth: .infinity)    // fixed from data: text changing between polls never moves the list
        .clipShape(RoundRectangle(radius: cardRadius))
        .elevation(2)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title). Making. \(line)")
    }
}

struct FailedCard: View {
    let title: String
    let message: String
    var retry: (() -> Void)?
    var onRemove: (() -> Void)?
    var rejected = false
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        ZStack(alignment: .topLeading) {
            LinearGradient(colors: [Color(hex: 0x4A3F42), Color(hex: 0x2A2124)], startPoint: .top, endPoint: .bottom)
            Color(red: 0.15, green: 0.03, blue: 0.04).opacity(0.5)
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    GlassChip(text: rejected ? "Not allowed" : "Didn’t finish", symbol: "exclamationmark.triangle", fill: Color(hex: 0xB91C1C).opacity(0.9))
                    Spacer()
                    if let onRemove { Menu { Button("Remove", role: .destructive, action: onRemove) } label: { Image(systemName: "ellipsis").font(.system(size: 18, weight: .bold)).foregroundStyle(.white).frame(width: 44, height: 44) }.accessibilityLabel("More") }
                }
                Spacer(minLength: 10)
                Text(title).font(.system(size: 19, weight: .semibold)).foregroundStyle(.white).lineLimit(typeSize.isAccessibilitySize ? 4 : 2)
                HStack(spacing: 12) {
                    if let retry {
                        Button(action: retry) {
                            Label("Try again", systemImage: "arrow.clockwise").font(.system(size: 16, weight: .semibold)).foregroundStyle(Color(hex: 0x11142B))
                                .padding(.horizontal, 16).frame(height: 44).background(.white, in: Capsule())
                        }.buttonStyle(.plain).accessibilityIdentifier("tryAgain")
                    }
                    Text(message).font(.system(size: 15)).foregroundStyle(.white.opacity(0.86)).lineLimit(2)
                }.padding(.top, 10)
            }
            .padding(14)
        }
        .frame(height: typeSize.isAccessibilitySize ? nil : cardHeight).frame(minHeight: typeSize.isAccessibilitySize ? cardHeight : nil).frame(maxWidth: .infinity)
        .clipShape(RoundRectangle(radius: cardRadius))
        .elevation(2)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(title). \(rejected ? "Not allowed" : "Didn’t finish"). \(message)")
    }
}

/// Placeholder card with the final size while the list loads.
struct SkeletonCard: View {
    @State private var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        RoundedRectangle(cornerRadius: cardRadius, style: .continuous).fill(Theme.surfaceRaised).frame(height: cardHeight)
            .opacity(pulse && !reduceMotion ? 0.55 : 1)
            .onAppear { if !reduceMotion { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { pulse = true } } }
            .accessibilityHidden(true)
    }
}

/// Card for a video the server is making (live stage) or that has not been listed yet.
struct RunningCard: View {
    @Environment(AppModel.self) private var model
    let video: VideoItem

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let info = model.stage(for: video.id)
            let stage: VideoStatus.Stage = { if case .running(let s) = video.status { s } else { .starting } }()
            let p = MakingProgress.info(stage: stage, secondsInStage: info.map { context.date.timeIntervalSince($0.since) } ?? 0, minutes: model.requestedMinutes(for: video.id))
            MakingCard(title: model.brief(for: video.id) ?? (video.title.flatMap { $0.isEmpty ? nil : $0 } ?? "Making your video"), line: p.line, segments: p.segments, current: p.current)
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
                FailedCard(title: pending.brief, message: message.isEmpty ? "No credits were used." : "\(message) No credits were used.", retry: onRetry, onRemove: onDismiss)
                    .accessibilityIdentifier("failedRow")
            } else {
                MakingCard(title: pending.brief, line: line, segments: [0, 0, 0, 0], current: 0, onRemove: nil)
                    .accessibilityIdentifier("pendingRow")
            }
        }
    }

    private var line: String {
        if case .uploading(let done, let total) = pending.state { return "Uploading \(done) of \(total) photos." }
        return "Starting your video…"
    }
}
