import PhotosUI
import SwiftUI
import VideoMKCore

/// The main screen (docs/UI_DESIGN.md d): top bar, "Your videos" feed of picture-first cards (or the empty hero with examples) and the
/// docked composer above the tab bar.
struct LibraryView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var path: [String] = []
    @State private var showingSettings = false
    @State private var showingWallet = false
    @State private var showingOptions = false
    @State private var showingAdd = false
    @State private var addStartsOnLibrary = false
    @State private var text = ""
    @State private var options = LibraryView.defaultOptions()
    @State private var dictation = Dictation()
    @State private var photos = PhotoAttachments()
    @FocusState private var composerFocused: Bool

    private var balance: Int? { model.wallet.flatMap { $0.unlimited ? nil : $0.balance } }

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                topBar
                Group {
                    switch (model.loadState, model.entries.isEmpty) {
                    case (.loading, true), (.idle, true): loadingState
                    case (.failed(let message), true): errorState(message)
                    case (_, true): emptyState
                    default: feed
                    }
                }
            }
            .background(Theme.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: String.self) { VideoDetailView(videoID: $0) }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                VStack(spacing: 0) {
                if let media = model.media, !composerFocused { UploadPill(media: media) { model.selectedTab = 1 } }
                ComposerBar(text: $text, options: $options, dictation: dictation, photos: photos, focus: $composerFocused, balance: balance, onSend: send,
                            onAttach: { addStartsOnLibrary = false; composerFocused = false; showingAdd = true }, onOptions: { composerFocused = false; showingOptions = true }, onAddCredits: { showingWallet = true })
                }
            }
        }
        .task { await model.refresh() }
        #if DEBUG
        .task {
            await photos.loadDebugFiles()
            let env = ProcessInfo.processInfo.environment
            if let t = env["VMK_DEBUG_TEXT"] { text = t }
            if env["VMK_DEBUG_FOCUS"] == "1" { try? await Task.sleep(for: .milliseconds(600)); composerFocused = true }
            switch env["VMK_DEBUG_SHEET"] {
            case "options": showingOptions = true
            case "addphone": showingAdd = true
            case "addmedia": addStartsOnLibrary = true; showingAdd = true
            default: break
            }
        }
        #endif
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
        .sheet(isPresented: $showingSettings) { SettingsView() }
        .sheet(isPresented: $showingWallet) { WalletView() }
        .sheet(isPresented: $showingOptions) { OptionsSheet(options: $options, balance: balance) }
        .sheet(isPresented: $showingAdd) {
            AddPhotosSheet(attached: photos.items.count + photos.loading + model.composerLibrary.count, minutes: options.minutes, startOnLibrary: addStartsOnLibrary) { phone, library in
                photos.add(phone)
                let known = Set(model.composerLibrary.map(\.id))
                model.composerLibrary += library.filter { !known.contains($0.id) }
                photos.libraryCount = model.composerLibrary.count
            }
        }
        .sensoryFeedback(.success, trigger: model.completions)
        .onAppear { dictation.onText = { text = $0 }; dictation.onKeyboardFallback = { composerFocused = true } }
        .onDisappear { dictation.stop() }
        .onChange(of: model.composerDraft) { _, draft in
            guard let draft else { return }
            text = draft; model.composerDraft = nil; composerFocused = true
        }
    }

    private func send() {
        dictation.cancel()   // not stop(): a final transcript arriving after this would put the sent text back in the field, and a second tap would send it again
        model.submit(brief: text, options: options, photos: photos.items.map(\.data), meta: photos.items.map(\.meta), libraryMedia: model.composerLibrary.map(\.id))
        photos.clear()
        model.composerLibrary = []
        text = ""
        composerFocused = false
    }

    // MARK: top bar

    private var topBar: some View {
        HStack(spacing: 10) {
            HStack(spacing: 10) {
                Image(systemName: "play.fill").font(.system(size: 13, weight: .bold)).foregroundStyle(.white).frame(width: 30, height: 30)
                    .background(Theme.gradient, in: RoundedRectangle(cornerRadius: 9, style: .continuous)).accessibilityHidden(true)
                Text("videomk").font(.system(size: 21, weight: .bold)).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader)
            }
            Spacer()
            if let wallet = model.wallet {
                Button { showingWallet = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "bolt.fill").font(.system(size: 13)).foregroundStyle(Theme.primary)
                        Text(wallet.unlimited ? "∞" : "\(wallet.balance)").font(.system(size: 17, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.text)
                    }
                    .padding(.horizontal, 14).frame(height: 36).background(Theme.surface, in: Capsule()).overlay(Capsule().stroke(Theme.outline, lineWidth: 1)).frame(minHeight: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(wallet.unlimited ? "Unlimited credits" : ComposerPlan.plural(wallet.balance, "credit"))
                .accessibilityHint("Shows your credits")
                .accessibilityIdentifier("balanceChip")
            }
            Button { showingSettings = true } label: { Image(systemName: "gearshape").font(.system(size: 20)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44) }
                .accessibilityLabel("Settings").accessibilityIdentifier("settingsButton")
        }
        .padding(.leading, 16).padding(.trailing, 8).frame(minHeight: 52)
    }

    // MARK: feed

    private var feed: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                Text("Your videos").font(.system(size: 30, weight: .bold)).tracking(-0.6).foregroundStyle(Theme.text).padding(.top, 2).accessibilityAddTraits(.isHeader)
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 340), spacing: 14, alignment: .top)], spacing: 14) {
                    ForEach(model.entries) { entry in card(entry) }
                }
            }
            .padding(.horizontal, 16).padding(.bottom, 12)
            .animation(reduceMotion ? nil : .snappy, value: model.entries.map(\.id))
        }
        .scrollDismissesKeyboard(.interactively)
        .refreshable { await model.refresh() }
    }

    @ViewBuilder private func card(_ entry: LibraryEntry) -> some View {
        switch entry {
        case .pending(let p):
            PendingCard(pending: p, onRetry: { model.retry(p.id) }, onDismiss: { model.dismissPending(p.id) })
        case .video(let v):
            switch v.status {
            case .running: NavigationLink(value: v.id) { RunningCard(video: v) }.buttonStyle(.plain)
            case .complete: NavigationLink(value: v.id) { ReadyCard(video: v) }.buttonStyle(.plain)
            case .failed:
                FailedCard(title: model.brief(for: v.id) ?? v.displayTitle, message: "No credits were used.", retry: { model.tryAgain(v) })
                    .accessibilityIdentifier("failedVideo")
            case .rejected:
                FailedCard(title: model.brief(for: v.id) ?? v.displayTitle, message: v.rejectReason ?? "Try describing something different.", rejected: true)
            }
        }
    }

    private var loadingState: some View {
        ScrollView { VStack(spacing: 14) { SkeletonCard(); SkeletonCard() }.padding(.horizontal, 16).padding(.top, 40) }
            .accessibilityElement(children: .ignore).accessibilityLabel("Loading your videos")
    }

    // MARK: empty

    private var emptyState: some View {
        ScrollView {
            VStack(spacing: 0) {
                FilmFrames().frame(height: 120).padding(.top, 6).accessibilityHidden(true)
                Text("Describe it.\nWe’ll make the video.").font(.system(size: 28, weight: .bold)).tracking(-0.8).multilineTextAlignment(.center).foregroundStyle(Theme.text).padding(.top, 8)
                    .accessibilityAddTraits(.isHeader)
                Text("Narrated and illustrated in minutes. Add your own photos if you like.").font(.system(size: 15.5)).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary).padding(.top, 8).padding(.horizontal, 24)
                Text("TRY ONE").font(.system(size: 13, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, alignment: .leading).padding(.top, 20).padding(.bottom, 8)
                VStack(spacing: 10) { ForEach(ExamplePrompt.all) { example in exampleCard(example) } }
            }
            .padding(.horizontal, 16).padding(.bottom, 12)
        }
        .scrollDismissesKeyboard(.interactively)
        .refreshable { await model.refresh() }
    }

    private func exampleCard(_ e: ExamplePrompt) -> some View {
        Button { use(e) } label: {
            HStack(spacing: 14) {
                Image(systemName: e.symbol).font(.system(size: 18)).foregroundStyle(Theme.primary).frame(width: 40, height: 40).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                Text(e.text).font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.text).multilineTextAlignment(.leading).frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: 4) {
                    if e.usesPhotos { Image(systemName: "photo").font(.system(size: 12)) }
                    Text(e.tag).font(.system(size: 12.5, weight: .semibold)).lineLimit(1).fixedSize()
                }
                .foregroundStyle(Theme.primary).padding(.horizontal, 10).frame(height: 30).background(Theme.primaryContainer, in: Capsule())
            }
            .padding(.horizontal, 14).frame(minHeight: 64)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(Theme.outline, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(e.text), \(e.tag)")
        .accessibilityHint("Fills in the description. It does not send.")
        .accessibilityIdentifier("example")
    }

    /// Tapping an example fills the composer, sets its length and does not send. The photo example also opens Add photos.
    private func use(_ e: ExamplePrompt) {
        text = e.text
        if let m = e.minutes { options.minutes = m }
        if e.usesPhotos {
            composerFocused = false
            addStartsOnLibrary = (model.media?.summary?.count ?? 0) > 0
            showingAdd = true
        } else { composerFocused = true }
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

struct ExamplePrompt: Identifiable {
    let text: String, tag: String, symbol: String
    var minutes: Double?
    var usesPhotos = false
    var id: String { text }
    static let all = [
        ExamplePrompt(text: "A calm one-minute story about a lighthouse keeper", tag: "1 min", symbol: "film", minutes: 1),
        ExamplePrompt(text: "How bees make honey, explained for kids", tag: "3 min", symbol: "sparkles", minutes: 3),
        ExamplePrompt(text: "My holiday in Thailand, told from my photos", tag: "Your photos", symbol: "photo", minutes: nil, usesPhotos: true),
    ]
}

/// Three overlapping film frames: a quiet picture for the empty state.
struct FilmFrames: View {
    var body: some View {
        ZStack {
            frame([Color(hex: 0xF5C9A8), Color(hex: 0xB8734F)], -7).offset(x: -78, y: 8)
            frame([Color(hex: 0x4C3B8F), Color(hex: 0x1F1740)], 7).offset(x: 80, y: 6)
            frame([Color(hex: 0xFFC77A), Color(hex: 0x7A3E66)], 0).offset(y: -4)
        }
    }
    private func frame(_ colors: [Color], _ angle: Double) -> some View {
        RoundedRectangle(cornerRadius: 14, style: .continuous).fill(LinearGradient(colors: colors, startPoint: .top, endPoint: .bottom))
            .frame(width: 104, height: 66).overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.white, lineWidth: 2.5))
            .shadow(color: .black.opacity(0.12), radius: 8, y: 4).rotationEffect(.degrees(angle))
    }
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
            ShimmerThumb(symbol: failed != nil ? "exclamationmark.triangle.fill" : pending.photoCount > 0 ? "photo.stack.fill" : "paperplane.fill", animate: failed == nil && !reduceMotion)
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
                } else if case .uploading(let done, let total) = pending.state {
                    ProgressView(value: Double(done), total: Double(max(total, 1))).tint(Theme.primary).animation(.smooth, value: done)
                    Text("Uploading \(done) of \(total)").font(.caption).foregroundStyle(Theme.textSecondary)
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
