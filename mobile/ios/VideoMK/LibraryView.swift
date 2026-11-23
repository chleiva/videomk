import SwiftUI
import VideoMKCore

struct LibraryView: View {
    @Environment(AppModel.self) private var model
    @State private var path: [String] = []
    @State private var showingSettings = false
    @State private var text = ""
    @State private var options = LibraryView.defaultOptions()
    @State private var dictation = Dictation()
    @FocusState private var composerFocused: Bool

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                switch (model.loadState, model.entries.isEmpty) {
                case (.loading, true), (.idle, true): ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                case (.failed(let message), true): errorState(message)
                case (_, true): emptyState
                default: list
                }
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("Videos")
            .navigationDestination(for: String.self) { VideoDetailView(videoID: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showingSettings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Settings").accessibilityIdentifier("settingsButton")
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                ComposerBar(text: $text, options: $options, dictation: dictation, focus: $composerFocused, onSend: send)
            }
        }
        .task { await model.refresh() }
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
        .sheet(isPresented: $showingSettings) { SettingsView() }
        .sensoryFeedback(.success, trigger: model.completions)
        .onAppear { dictation.onText = { text = $0 } }
        .onDisappear { dictation.stop() }
    }

    private func send() {
        dictation.stop()
        model.submit(brief: text, options: options)
        text = ""
        composerFocused = false
    }

    private var list: some View {
        List {
            ForEach(model.entries) { entry in
                switch entry {
                case .pending(let p):
                    PendingRow(pending: p, onRetry: { model.retry(p.id) }, onDismiss: { model.dismissPending(p.id) })
                        .listRowBackground(Theme.surface)
                        .swipeActions(edge: .trailing) { Button("Remove", role: .destructive) { model.dismissPending(p.id) } }
                case .video(let v) where v.status.isRunning:
                    NavigationLink(value: v.id) { RunningRow(video: v) }
                        .listRowBackground(Theme.surface)
                case .video(let v):
                    NavigationLink(value: v.id) { VideoRow(video: v) }
                        .listRowBackground(Theme.surface)
                        .accessibilityIdentifier("videoRow")
                }
            }
        }
        .scrollContentBackground(.hidden)
        .scrollDismissesKeyboard(.interactively)
        .animation(.snappy, value: model.entries.map(\.id))
        .refreshable { await model.refresh() }
    }

    private var emptyState: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(systemName: "sparkles.tv").font(.system(size: 52)).foregroundStyle(Theme.gradient).accessibilityHidden(true)
                Text("Make your first video").font(.title2.bold()).foregroundStyle(Theme.text)
                Text("Type or tap the microphone and say what you want. It appears here while it's made, and you can ask for more.")
                    .multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
                VStack(spacing: 10) {
                    ForEach(ExampleBriefs.all, id: \.self) { example in
                        Button { text = example; composerFocused = true } label: {
                            Text(example).font(.callout).foregroundStyle(Theme.text).multilineTextAlignment(.leading)
                                .frame(maxWidth: .infinity, alignment: .leading).padding(14)
                                .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                        }
                    }
                }
            }
            .padding(24)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func errorState(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Couldn't load your videos", systemImage: "wifi.exclamationmark")
        } description: { Text(message) } actions: {
            Button("Try again") { Task { await model.refresh() } }.buttonStyle(.borderedProminent)
        }
    }

    /// Debug builds can shorten the default video (UI tests); release builds always start at the product default.
    static func defaultOptions() -> CreateOptions {
        #if DEBUG
        if let m = ProcessInfo.processInfo.environment["VMK_DEBUG_DEFAULT_MINUTES"].flatMap(Double.init) { return CreateOptions(minutes: m) }
        #endif
        return CreateOptions()
    }
}

enum ExampleBriefs {
    static let all = [
        "How a bill becomes law in the United States, explained for teenagers.",
        "A visual tour of the most famous landmarks of Paris.",
        "Why the sky is blue, with a simple diagram.",
    ]
}

// MARK: - rows

struct VideoRow: View {
    let video: VideoItem

    var body: some View {
        HStack(spacing: 12) {
            Thumbnail(url: video.previewGifURL, status: video.status)
                .frame(width: 112, height: 63)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(video.displayTitle).font(.headline).foregroundStyle(Theme.text).lineLimit(2)
                HStack(spacing: 8) {
                    StatusChip(status: video.status)
                    if let d = video.durationSeconds, video.status == .complete { Text(Self.duration(d)).font(.caption).foregroundStyle(Theme.textSecondary) }
                }
                if let created = video.createdAt { Text(Self.relative.localizedString(for: created, relativeTo: .now)).font(.caption).foregroundStyle(Theme.textSecondary) }
                if video.status == .rejected, let r = video.rejectReason { Text(r).font(.caption).foregroundStyle(Theme.warning).lineLimit(2) }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    static let relative: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .short; return f
    }()

    static func duration(_ s: Double) -> String { String(format: "%d:%02d", Int(s) / 60, Int(s) % 60) }
}

/// A video being made: live stage, an honest estimate bar and elapsed time, in the list next to finished videos.
struct RunningRow: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let video: VideoItem

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let info = model.stage(for: video.id)
            let stage: VideoStatus.Stage = { if case .running(let s) = video.status { s } else { .starting } }()
            let inStage = info.map { context.date.timeIntervalSince($0.since) } ?? 0
            let fraction = ProgressEstimator.fraction(stage: stage, secondsInStage: inStage, minutes: model.requestedMinutes(for: video.id))
            HStack(spacing: 12) {
                ShimmerThumb(symbol: "wand.and.stars", animate: !reduceMotion)
                    .frame(width: 112, height: 63)
                    .clipShape(RoundRectangle(radius: 10))
                VStack(alignment: .leading, spacing: 6) {
                    Text(model.brief(for: video.id) ?? (video.title.flatMap { $0.isEmpty ? nil : $0 } ?? "Making your video"))
                        .font(.headline).foregroundStyle(Theme.text).lineLimit(2)
                    ProgressView(value: fraction).tint(Theme.primary).animation(.smooth(duration: 0.8), value: fraction)
                    HStack {
                        Text(stage.shortTitle).font(.caption).foregroundStyle(Theme.textSecondary).lineLimit(1)
                            .contentTransition(.opacity).animation(.snappy, value: stage)
                        Spacer(minLength: 4)
                        if let created = video.createdAt {
                            Text(Self.elapsed(context.date.timeIntervalSince(created))).font(.caption.monospacedDigit()).foregroundStyle(Theme.textSecondary)
                        }
                    }
                }
            }
            .padding(.vertical, 4)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Making video: \(model.brief(for: video.id) ?? video.displayTitle)")
            .accessibilityValue("\(stage.title), about \(Int(fraction * 100)) percent")
        }
        .accessibilityIdentifier("runningRow")
    }

    static func elapsed(_ s: TimeInterval) -> String { let t = max(0, Int(s)); return String(format: "%d:%02d", t / 60, t % 60) }
}

/// The request is on its way (or failed before the server answered). Same shape as a running row so the list doesn't jump.
struct PendingRow: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let pending: PendingVideo
    let onRetry: () -> Void
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            ShimmerThumb(symbol: failed == nil ? "paperplane.fill" : "exclamationmark.triangle.fill", animate: failed == nil && !reduceMotion)
                .frame(width: 112, height: 63)
                .clipShape(RoundRectangle(radius: 10))
            VStack(alignment: .leading, spacing: 6) {
                Text(pending.brief).font(.headline).foregroundStyle(Theme.text).lineLimit(2)
                if let message = failed {
                    Text(message).font(.caption).foregroundStyle(Theme.danger).lineLimit(2)
                    HStack(spacing: 16) {
                        Button("Try again", action: onRetry).font(.caption.weight(.semibold))
                        Button("Remove", role: .destructive, action: onDismiss).font(.caption)
                    }.buttonStyle(.borderless)
                } else {
                    ProgressView().controlSize(.small)
                    Text("Sending your request…").font(.caption).foregroundStyle(Theme.textSecondary)
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: failed == nil ? .combine : .contain)
        .accessibilityIdentifier(failed == nil ? "pendingRow" : "failedRow")
    }

    private var failed: String? { if case .failed(let m) = pending.state { m } else { nil } }
}

struct RoundRectangle: Shape {
    let radius: CGFloat
    func path(in rect: CGRect) -> Path { RoundedRectangle(cornerRadius: radius, style: .continuous).path(in: rect) }
}

/// A calm moving highlight on a placeholder thumbnail. Static when Reduce Motion is on.
struct ShimmerThumb: View {
    let symbol: String
    let animate: Bool

    var body: some View {
        ZStack {
            Theme.surfaceRaised
            if animate {
                TimelineView(.animation) { ctx in
                    let t = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.8) / 1.8
                    GeometryReader { geo in
                        LinearGradient(colors: [.clear, Theme.primary.opacity(0.22), .clear], startPoint: .leading, endPoint: .trailing)
                            .frame(width: geo.size.width * 0.6)
                            .offset(x: -geo.size.width * 0.6 + (geo.size.width * 1.6) * t)
                    }
                }
            }
            Image(systemName: symbol).font(.title3).foregroundStyle(Theme.primary)
        }
        .clipped()
    }
}

struct Thumbnail: View {
    let url: URL?
    let status: VideoStatus

    var body: some View {
        ZStack {
            Theme.surfaceRaised
            if let url {
                AsyncImage(url: url) { phase in
                    if let image = phase.image { image.resizable().scaledToFill() } else { placeholder }
                }
            } else { placeholder }
        }
    }

    private var placeholder: some View {
        Image(systemName: status.isRunning ? "hourglass" : status == .complete ? "play.fill" : "exclamationmark.triangle")
            .foregroundStyle(Theme.textSecondary)
    }
}

struct StatusChip: View {
    let status: VideoStatus

    var body: some View {
        Text(label)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .foregroundStyle(color)
            .background(color.opacity(0.15), in: Capsule())
    }

    private var label: String {
        switch status {
        case .running: "Making"
        case .complete: "Ready"
        case .failed: "Failed"
        case .rejected: "Not allowed"
        }
    }

    private var color: Color {
        switch status {
        case .running: Theme.primary
        case .complete: Theme.success
        case .failed: Theme.danger
        case .rejected: Theme.warning
        }
    }
}
