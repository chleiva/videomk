import PhotosUI
import SwiftUI
import VideoMKCore

/// The home screen (docs/UI_DESIGN.md d, o): top bar, the "Your videos" feed (or the empty hero with examples) and one clear entry: "New video".
/// There is no text input on this screen; making a video happens on the Create sheet.
struct LibraryView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var path: [String] = []
    @State private var showingSettings = false
    @State private var showingWallet = false
    @State private var showingCreate = false
    @State private var showingRating = false
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var balance: Int? { model.wallet.flatMap { $0.unlimited ? nil : $0.balance } }

    var body: some View {
        @Bindable var model = model
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
            .safeAreaInset(edge: .bottom, spacing: 0) { uploadStrip }       // an inset, not an overlay: the last row always scrolls clear
        }
        .onChange(of: path) { _, p in model.tabBarHidden = !p.isEmpty }
        .task { await model.refresh() }
        .task { await model.createModel.loadCapabilities(userID: model.userID) }       // ready before the sheet opens
        #if DEBUG
        .task { await debugSetup() }
        #endif
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
        .sheet(isPresented: $showingSettings) { SettingsView() }
        .sheet(isPresented: $showingWallet) { WalletView() }
        .sheet(isPresented: $showingRating) { RatingPromptView() }
        .task(id: "\(path.isEmpty)-\(scenePhase == .active)") { await considerRatingPrompt() }
        .sheet(isPresented: $showingCreate) { CreateView(create: model.createModel) }
        .sheet(item: $model.createProblem) { CreateProblemSheet(problem: $0) { model.createProblem = nil; model.createModel.open(prefill: $0.prompt); showingCreate = true } }
        .sensoryFeedback(.success, trigger: model.completions)
        .onChange(of: model.createRequested) { _, v in if v { model.createRequested = false; openCreate() } }
        .onChange(of: model.composerDraft) { _, draft in if let draft { model.composerDraft = nil; openCreate(prefill: draft) } }
        .onChange(of: model.requestCredits) { _, v in if v { model.requestCredits = false; showingCreate = false; Task { try? await Task.sleep(for: .milliseconds(400)); showingWallet = true } } }
    }

    /// Only when the person is calmly back on the home screen (not on a video, not creating), a moment after arriving.
    private func considerRatingPrompt() async {
        guard path.isEmpty, scenePhase == .active else { return }
        try? await Task.sleep(for: .seconds(1.5))
        guard !Task.isCancelled, path.isEmpty else { return }
        let env = ProcessInfo.processInfo.environment
        let context = RatingContext(isPlaying: model.isPlayingVideo, isCreating: showingCreate || model.pending.contains { if case .sending = $0.state { true } else if case .uploading = $0.state { true } else { false } },
                                    sheetOpen: showingSettings || showingWallet || showingRating || model.createProblem != nil,
                                    suppressed: RatingPrompt.isSuppressed(environment: env))
        if model.rating.shouldPrompt(context) { model.rating.didShow(); showingRating = true }
    }

    private func openCreate(prefill: String? = nil, minutes: Double? = nil, photos: Bool = false) {
        model.createModel.open(prefill: prefill, minutes: minutes)
        showingCreate = true
    }

    // MARK: upload progress (the only thing that floats above the tab bar, and only while photos are being uploaded)

    @ViewBuilder private var uploadStrip: some View {
        if let media = model.media {
            UploadPill(media: media) { model.selectedTab = 1 }.frame(maxWidth: .infinity, alignment: .trailing).padding(.horizontal, 16).padding(.top, 4).vmkOneLineCap()
        }
    }

    // MARK: top bar

    private var topBar: some View {
        HStack(spacing: 8) {
            BrandMark(size: 32)
            Spacer()
            if let wallet = model.wallet {
                Button { showingWallet = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "bolt.fill").font(.vmk(13)).foregroundStyle(Theme.primary)
                        Text(wallet.unlimited ? "∞" : "\(wallet.balance)").font(.vmk(17, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.text)
                    }
                    .padding(.horizontal, 14).frame(height: 38).vmkGlass(in: Capsule()).frame(minHeight: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(wallet.unlimited ? tr("videos.unlimited_credits") : tr("credits.count", wallet.balance))
                .accessibilityHint(tr("videos.shows_your_credits"))
                .accessibilityIdentifier("balanceChip")
            }
            GlassIconButton(symbol: "person", label: tr("videos.settings"), identifier: "settingsButton") { showingSettings = true }
        }
        .padding(.leading, 20).padding(.trailing, 12).frame(minHeight: 52).vmkOneLineCap()      // mark, credits and account stay on one row; the page below scrolls and wraps
    }

    // MARK: feed

    /// In progress or still being sent: always on top, under no heading.
    private var activeEntries: [LibraryEntry] {
        model.entries.filter { e in
            switch e { case .pending: true; case .video(let v): v.status.isRunning }
        }
    }

    private var finishedGroups: [(group: DayGroup, items: [VideoItem])] {
        let finished = model.entries.compactMap { e -> VideoItem? in if case .video(let v) = e, !v.status.isRunning { v } else { nil } }
        return DayGroup.grouped(finished, date: \.createdAt)
    }

    private var statusKeys: [String] { model.entries.map { e in if case .video(let v) = e { "\(v.id)-\(v.status.isRunning)-\(v.status == .complete)" } else { e.id } } }

    private var feed: some View {
        let columns = Array(repeating: GridItem(.flexible(), spacing: 14, alignment: .top), count: sizeClass == .regular ? 2 : 1)
        return ScrollView {
            LazyVStack(alignment: .leading, spacing: 14) {
                Text(tr("videos.your_videos")).font(.vmk(30, weight: .bold)).tracking(-0.6).foregroundStyle(Theme.text).padding(.top, 2).accessibilityAddTraits(.isHeader)
                LazyVGrid(columns: columns, spacing: 14) { ForEach(activeEntries) { entry in card(entry).transition(.opacity) } }
                ForEach(finishedGroups, id: \.group) { section in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(Self.title(section.group).uppercased()).font(.vmk(12, weight: .bold)).tracking(0.8).foregroundStyle(Theme.textTertiary).padding(.top, 8).accessibilityAddTraits(.isHeader)
                        LazyVGrid(columns: columns, spacing: 6) { ForEach(section.items) { v in card(.video(v)).transition(.opacity) } }
                    }
                }
            }
            .padding(.horizontal, Theme.Space.l).padding(.bottom, Theme.Space.l)
            .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.insert, value: statusKeys)
        }
        .scrollDismissesKeyboard(.interactively)
        .refreshable { await model.refresh() }
    }

    static func title(_ g: DayGroup) -> String {
        switch g { case .today: tr("videos.group_today"); case .yesterday: tr("videos.group_yesterday"); case .earlier: tr("videos.group_earlier") }
    }

    @ViewBuilder private func card(_ entry: LibraryEntry) -> some View {
        switch entry {
        case .pending(let p):
            PendingCard(pending: p, onRetry: { model.retry(p.id) }, onDismiss: { model.dismissPending(p.id) })
        case .video(let v):
            switch v.status {
            case .running: NavigationLink(value: v.id) { RunningCard(video: v) }.buttonStyle(.plain)
            case .complete: NavigationLink(value: v.id) { VideoRow(video: v) }.buttonStyle(.plain)
            case .failed:
                FailedRow(title: model.brief(for: v.id) ?? v.displayTitle, message: nil, retry: { model.tryAgain(v) })
                    .accessibilityIdentifier("failedVideo")
            case .rejected:
                FailedRow(title: model.brief(for: v.id) ?? v.displayTitle, message: v.rejectReason ?? tr("detail.rejected_body"), rejected: true)
            }
        }
    }

    private var loadingState: some View {
        ScrollView { VStack(spacing: 18) { SkeletonCard(); SkeletonCard(); SkeletonCard() }.padding(.horizontal, 16).padding(.top, 40) }
            .accessibilityElement(children: .ignore).accessibilityLabel(tr("videos.loading_your_videos"))
    }

    // MARK: empty

    /// First run: the headline, a real prompt field (a tap opens Create with the keyboard up) and three example chips. Nothing else.
    private var emptyState: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text(tr("videos.describe_itnwell_make_the_video")).font(.vmk(34, weight: .bold)).tracking(-1).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, 36).accessibilityAddTraits(.isHeader)
                Button { openCreate(prefill: nil, minutes: 0.5) } label: {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(tr("create.describe_your_video_for_example")).font(.vmk(19)).foregroundStyle(Theme.textTertiary)
                        Spacer(minLength: 0)
                        HStack { Spacer(); Image(systemName: "mic").font(.vmk(18)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44).background(Theme.surfaceRaised, in: Circle()).accessibilityHidden(true) }
                    }
                    .padding(16).frame(maxWidth: .infinity, minHeight: 132, alignment: .topLeading)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous).stroke(Theme.outline, lineWidth: 1))
                }
                .buttonStyle(.plain).padding(.top, 24).accessibilityLabel(tr("create.describe_your_video_for_example")).accessibilityIdentifier("firstVideoButton")
                WrapLayout(spacing: 8) { ForEach(ExamplePrompt.all) { example in exampleChip(example) } }.padding(.top, 14)
            }
            .padding(.horizontal, Theme.Space.l).padding(.bottom, Theme.Space.l)
        }
        .scrollDismissesKeyboard(.interactively)
        .refreshable { await model.refresh() }
    }

    private func exampleChip(_ e: ExamplePrompt) -> some View {
        Button { use(e) } label: {
            HStack(spacing: 6) {
                if e.usesPhotos { Image(systemName: "photo").font(.vmk(13)).accessibilityHidden(true) }
                Text(e.label).font(.vmk(15, weight: .semibold)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(Theme.text).padding(.horizontal, 14).padding(.vertical, 8).frame(minHeight: 44)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous).stroke(Theme.outline, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityHint(tr("videos.fills_in_the_description_it"))
        .accessibilityIdentifier("example")
    }

    /// Tapping an example fills the composer, sets its length and does not send. The photo example also opens Add photos.
    private func use(_ e: ExamplePrompt) {
        openCreate(prefill: e.text, minutes: e.minutes)
        if e.usesPhotos { model.createModel.autoOpenPhotos = .init(library: (model.media?.summary?.count ?? 0) > 0) }
    }

    private func errorState(_ message: String) -> some View {
        ContentUnavailableView {
            Label(tr("videos.couldnt_load_your_videos"), systemImage: "wifi.exclamationmark")
        } description: { Text(message) } actions: {
            Button(tr("common.try_again")) { Task { await model.refresh() } }.buttonStyle(.borderedProminent)
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
    let text: String, label: String, tag: String, symbol: String
    var minutes: Double?
    var usesPhotos = false
    var id: String { text }
    static let all = [
        ExamplePrompt(text: tr("videos.a_calm_oneminute_story_about"), label: tr("videos.chip_story"), tag: LengthLabel.chip(1), symbol: "film", minutes: 1),
        ExamplePrompt(text: tr("videos.how_bees_make_honey_explained"), label: tr("videos.chip_bees"), tag: LengthLabel.chip(3), symbol: "sparkles", minutes: 3),
        ExamplePrompt(text: tr("videos.my_holiday_in_thailand_told"), label: tr("videos.chip_holiday"), tag: tr("videos.tag_photos"), symbol: "photo", minutes: nil, usesPhotos: true),
    ]
}

struct RoundRectangle: Shape {
    let radius: CGFloat
    func path(in rect: CGRect) -> Path { RoundedRectangle(cornerRadius: radius, style: .continuous).path(in: rect) }
}

#if DEBUG
extension LibraryView {
    /// Screenshots: `VMK_DEBUG_CREATE=empty|filled|photos|options|notaffordable|q1|q2|summary|checking|unsupported|blocked|paused` opens Create in that state.
    @MainActor func debugSetup() async {
        let env = ProcessInfo.processInfo.environment
        await model.createModel.photos.loadDebugFiles()      // VMK_DEBUG_PHOTO_FILES / VMK_DEBUG_FAKE_PHOTOS attach to the Create screen
        switch env["VMK_DEBUG_SHEET"] { case "settings", "delete", "feedback": showingSettings = true; case "wallet": showingWallet = true; case "rating": showingRating = true; default: break }
        if let id = env["VMK_DEBUG_OPEN"] { try? await Task.sleep(for: .milliseconds(400)); path = [id] }       // v1 making, v2 failed, v3 ready (VMK_DEBUG_FAKE_VIDEOS=1)
        guard let state = env["VMK_DEBUG_CREATE"] else { return }
        let c = model.createModel
        await c.loadCapabilities(userID: model.userID)
        c.open()
        let text = state == "photos" || state == "shortphotos" ? "My holiday in Thailand: beaches, street food and the night market" : state == "unsupported" ? "A scene from a famous actor’s new movie" : "How bees make honey, explained for kids"
        if state != "empty" { c.form.text = text }
        if state == "photos" || state == "shortphotos" {
            if state == "photos" { c.form.setMinutes(1) }
            for i in 0..<100 { let img = MediaModel.fakeImage(seed: "attached\(i)", size: CGSize(width: 112, height: 112)); c.photos.debugAppend(AttachedPhoto(data: img.jpegData(compressionQuality: 0.7) ?? Data(), thumbnail: img)) }
        }
        if state == "options" { c.showMore = true }
        if let spec = env["VMK_DEBUG_DECK_FILE"] { c.debugPickDeck(spec) }       // before the platform pick: a vertical pick after a deck shows the warning
        c.debugPick(state)
        c.debugStage(state)
        showingCreate = true
    }
}
#endif

/// Generate answered "blocked" or "paused" after Create had closed: the same kind sheet, with Edit request.
struct CreateProblemSheet: View {
    let problem: AppModel.CreateProblem
    let onEdit: (AppModel.CreateProblem) -> Void
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top) {
                Image(systemName: "exclamationmark.triangle").font(.vmk(34)).foregroundStyle(Theme.warning).frame(width: 56, height: 56).background(Theme.warningContainer, in: Circle()).accessibilityHidden(true)
                Spacer()
                GlassIconButton(symbol: "xmark", label: tr("common.close"), identifier: "kindClose") { dismiss() }
            }.padding(.top, 14)
            Text(problem.paused ? tr("videos.creating_videos_is_paused") : tr("videos.we_cant_make_this_one")).font(.vmk(30, weight: .bold)).foregroundStyle(Theme.text).padding(.top, 16).accessibilityAddTraits(.isHeader)
            Text(problem.message).font(.vmk(17)).foregroundStyle(Theme.textSecondary).padding(.top, 8)
            if problem.paused, let retry = RetryText.make(problem.retryAfter) { Text(retry).font(.vmk(17, weight: .semibold)).foregroundStyle(Theme.text).padding(.top, 6) }
            Spacer()
            Text(tr("create.nothing_was_charged")).font(.vmk(15)).foregroundStyle(Theme.textSecondary)
            Button { onEdit(problem) } label: { Text(tr("create.edit_request")).font(.vmk(19, weight: .bold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 54).background(Theme.gradient, in: Capsule()) }.buttonStyle(.plain).padding(.top, 8).accessibilityIdentifier("editRequest")
        }
        .padding(.horizontal, 20).padding(.bottom, 6)
        .presentationBackground(Theme.surface).presentationDetents([.height(420), .large]).presentationDragIndicator(.visible)
    }
}
