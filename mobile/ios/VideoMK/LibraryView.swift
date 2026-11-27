import PhotosUI
import SwiftUI
import VideoMKCore

/// Videos, the home screen (docs/DESIGN_BAR_2026.md, `phone_2_videos`): the large title with the credits and the account, the Making card on top while
/// something is being made, then the posters (the newest one large). One way to make a video: the round New video button of the tab bar.
struct LibraryView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var path: [String] = []
    @State private var showingSettings = false
    @State private var showingWallet = false
    @State private var showingCreate = false
    @State private var showingRating = false
    @Environment(\.scenePhase) private var scenePhase
    @Namespace private var reveal

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
        .task { await model.createModel.loadCapabilities(userID: model.userID) }       // ready before the screen opens
        #if DEBUG
        .task { await debugSetup() }
        #endif
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
        .sheet(isPresented: $showingSettings) { SettingsView() }
        .sheet(isPresented: $showingWallet) { WalletView() }
        .sheet(isPresented: $showingRating) { RatingPromptView() }
        .task(id: "\(path.isEmpty)-\(scenePhase == .active)") { await considerRatingPrompt() }
        .fullScreenCover(isPresented: $showingCreate) { CreateView(create: model.createModel) }
        .alert(item: $model.retryNotice) { Alert(title: Text(tr("retry.notice_title")), message: Text($0.message), dismissButton: .default(Text(tr("common.ok")))) }
        .sheet(item: $model.createProblem) { CreateProblemSheet(problem: $0) { model.createProblem = nil; model.createModel.open(prefill: $0.prompt); showingCreate = true } }
        .sensoryFeedback(.success, trigger: model.completions)                       // one success haptic when a video becomes ready
        .onChange(of: model.completions) { _, _ in if let id = model.revealing, let v = model.video(id) { UIAccessibility.post(notification: .announcement, argument: tr("making.ready_announce", v.displayTitle)) } }
        .onChange(of: model.createRequested) { _, v in if v { model.createRequested = false; openCreate() } }
        .onChange(of: model.composerDraft) { _, draft in if let draft { model.composerDraft = nil; openCreate(prefill: draft) } }
        .onChange(of: model.createPrefill) { _, p in
            guard let p else { return }
            model.createPrefill = nil
            model.createModel.open(prefill: p.text, minutes: p.minutes, platformChip: p.platformChip, language: p.language)
            showingCreate = true
        }
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

    private func openCreate(prefill: String? = nil, minutes: Double? = nil) {
        model.createModel.open(prefill: prefill, minutes: minutes)
        showingCreate = true
    }

    // MARK: upload progress (the only thing that floats above the tab bar, and only while photos are being uploaded)

    @ViewBuilder private var uploadStrip: some View {
        if let media = model.media {
            UploadPill(media: media) { model.selectedTab = 1 }.frame(maxWidth: .infinity, alignment: .trailing).padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.xs).vmkOneLineCap()
        }
    }

    // MARK: top bar

    private var topBar: some View {
        TopBar(title: tr("videos.your_videos")) {
            if let wallet = model.wallet {
                Button { showingWallet = true } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "bolt.fill").font(.role(.footnote)).foregroundStyle(Theme.primary)
                        Text(wallet.unlimited ? "∞" : "\(wallet.balance)").font(.role(.subhead, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.text)
                    }
                    .padding(.horizontal, Theme.Space.m).frame(height: 36).background(Theme.surfaceRaised, in: Capsule()).frame(minHeight: Theme.minTouch).contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(wallet.unlimited ? tr("videos.unlimited_credits") : tr("credits.count", wallet.balance))
                .accessibilityHint(tr("videos.shows_your_credits"))
                .accessibilityIdentifier("balanceChip")
            }
            Button { showingSettings = true } label: {
                Group {
                    if let initial { Text(initial).font(.role(.subhead, weight: .semibold)) } else { Image(systemName: "person.fill").font(.role(.subhead)) }
                }
                .foregroundStyle(Theme.textSecondary).frame(width: 36, height: 36).background(Theme.surface3, in: Circle())
                .frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Circle())
            }
            .buttonStyle(.plain).accessibilityLabel(tr("videos.settings")).accessibilityIdentifier("settingsButton")
        }
    }

    /// The first letter of the account, for the round account button.
    private var initial: String? {
        if case .signedIn(let email?) = model.phase, let first = email.first, first.isLetter || first.isNumber { return String(first).uppercased() }
        return nil
    }

    // MARK: feed

    /// In progress or still being sent: always on top.
    private var activeEntries: [LibraryEntry] {
        model.entries.filter { e in
            switch e { case .pending: true; case .video(let v): v.status.isRunning }
        }
    }

    private var finished: [VideoItem] { model.entries.compactMap { e in if case .video(let v) = e, !v.status.isRunning { v } else { nil } } }

    private var statusKeys: [String] { model.entries.map { e in if case .video(let v) = e { "\(v.id)-\(v.status.isRunning)-\(v.status == .complete)" } else { e.id } } }

    private var feed: some View {
        let blocks = VideoFeed.blocks(finished, singleColumn: typeSize.isAccessibilitySize)
        return ScrollView {
            LazyVStack(alignment: .leading, spacing: Theme.Space.xl) {
                ForEach(activeEntries) { entry in card(entry).transition(.opacity) }
                ForEach(blocks) { block in
                    switch block {
                    case .hero(let v): link(v) { VideoRow(video: v, meta: Self.when(v.createdAt), note: firstVideoNote(v)) }.matchedGeometryEffect(id: v.id, in: reveal, properties: .position, isSource: false)
                    case .pair(let a, let b): PairRow(a: a, b: b) { v in link(v) { VideoRow(video: v, posterHeight: VideoFeed.pairHeight(a, b)) } }
                    case .problem(let v): card(.video(v))
                    }
                }
            }
            .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s).padding(.bottom, Theme.Space.xxl)
            .frame(maxWidth: 640).frame(maxWidth: .infinity)
            .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: statusKeys)
        }
        .scrollDismissesKeyboard(.interactively)
        .refreshable { await model.refresh() }
    }

    private func link<Label: View>(_ v: VideoItem, @ViewBuilder label: () -> Label) -> some View {
        NavigationLink(value: v.id) { label() }.buttonStyle(PressScale())
    }

    /// "Your first video.": one line, on the first video only, while it is being revealed.
    private func firstVideoNote(_ v: VideoItem) -> String? {
        model.revealing == v.id && model.videos.filter { $0.status == .complete }.count == 1 ? tr("videos.first_video") : nil
    }

    /// "Today", "Yesterday", or the date.
    static func when(_ date: Date?) -> String? {
        guard let date else { return nil }
        switch DayGroup.of(date) { case .today: return tr("videos.group_today"); case .yesterday: return tr("videos.group_yesterday"); case .earlier: return Localization.shared.abbreviatedDate(date) }
    }

    @ViewBuilder private func card(_ entry: LibraryEntry) -> some View {
        switch entry {
        case .pending(let p):
            PendingCard(pending: p, onRetry: { model.retry(p.id) }, onDismiss: { model.dismissPending(p.id) })
        case .video(let v):
            switch v.status {
            case .running: NavigationLink(value: v.id) { RunningCard(video: v) }.buttonStyle(PressScale()).matchedGeometryEffect(id: v.id, in: reveal, properties: .position)
            case .complete: link(v) { VideoRow(video: v) }
            case .failed:
                // "Try again" starts THIS video again on the server (all its photos and options): no new row. Not offered for a used-up presentation or one out of retries.
                FailedRow(title: model.brief(for: v.id) ?? v.displayTitle, message: tr("videos.no_credits_were_used"), retry: v.canRetry == false || model.retrying.contains(v.id) ? nil : { model.tryAgain(v) }, onRemove: { model.removeFailed(v) })
                    .accessibilityIdentifier("failedVideo")
            case .rejected:
                FailedRow(title: model.brief(for: v.id) ?? v.displayTitle, message: v.rejectReason ?? tr("detail.rejected_body"), onRemove: { model.removeFailed(v) }, rejected: true)
            }
        }
    }

    private var loadingState: some View {
        ScrollView { VideosSkeleton().padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s) }
            .scrollDisabled(true)
            .accessibilityElement(children: .ignore).accessibilityLabel(tr("videos.loading_your_videos"))
    }

    // MARK: empty

    /// First run: one line, a prompt that opens Create with the caret ready, and the three examples. Nothing else.
    private var emptyState: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text(tr("videos.describe_itnwell_make_the_video")).textRole(.largeTitle).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, Theme.Space.xxl).accessibilityAddTraits(.isHeader)
                Button { openCreate() } label: {
                    HStack(spacing: Theme.Space.s) {
                        Text(tr("create.describe_your_video_for_example")).textRole(.title, weight: .semibold).foregroundStyle(Theme.textSecondary)
                        Spacer(minLength: 0)
                        PlaySparkle(scale: 0.8).foregroundStyle(Theme.primary)
                    }
                    .padding(.horizontal, Theme.Space.xl).frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous)).elevation(2)
                }
                .buttonStyle(PressScale()).padding(.top, Theme.Space.xxl).accessibilityLabel(tr("create.new_video")).accessibilityHint(tr("videos.opens_the_screen_where_you")).accessibilityIdentifier("firstVideoButton")
                WrapLayout(spacing: Theme.Space.s) {
                    ForEach(ExamplePrompt.all) { e in
                        SparkleChip(title: e.label, identifier: "example", hint: tr("videos.fills_in_the_description_it")) { Haptics.play(.selection); openCreate(); model.createModel.typeIn = e.text }
                    }
                }
                .padding(.top, Theme.Space.l)
            }
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.xxl)
            .frame(maxWidth: 640).frame(maxWidth: .infinity)
        }
        .refreshable { await model.refresh() }
    }

    /// The list could not be loaded: what happened in one line, and one action.
    private func errorState(_ message: String) -> some View {
        VStack(spacing: Theme.Space.l) {
            Image(systemName: "wifi.exclamationmark").font(.role(.largeTitle, weight: .regular)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            Text(tr("videos.couldnt_load_your_videos")).textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center)
            Text(message).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
            Button(tr("common.try_again")) { Task { await model.refresh() } }.buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("reloadVideos")
        }
        .padding(.horizontal, Theme.gutter).frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// Debug builds can shorten the default video (UI tests); release builds always start at the product default.
    static func defaultOptions() -> CreateOptions {
        #if DEBUG
        if let m = ProcessInfo.processInfo.environment["VMK_DEBUG_DEFAULT_MINUTES"].flatMap(Double.init) { return CreateOptions(minutes: m) }
        #endif
        return CreateOptions()
    }
}

/// The three examples of Create (and of the first run): a few words on the chip, a whole sentence in the prompt.
struct ExamplePrompt: Identifiable {
    let text: String, label: String
    var id: String { label }
    static var all: [ExamplePrompt] {
        [ExamplePrompt(text: tr("create.example1_text"), label: tr("create.example1_label")),
         ExamplePrompt(text: tr("create.example2_text"), label: tr("create.example2_label")),
         ExamplePrompt(text: tr("create.example3_text"), label: tr("create.example3_label"))]
    }
}

/// A pressed card gives a little (a spring; Reduce Motion: it only dims).
struct PressScale: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1).opacity(configuration.isPressed ? 0.9 : 1)
            .animation(Theme.Motion.spring, value: configuration.isPressed)
    }
}

/// How the finished videos are laid out: the newest one large, then two side by side (a vertical one keeps a narrow column), and a video that did not
/// finish as a full-width card where it belongs in time. Pure layout rules, no views.
enum VideoFeed {
    enum Block: Identifiable {
        case hero(VideoItem), pair(VideoItem, VideoItem), problem(VideoItem)
        var id: String { switch self { case .hero(let v): "h-\(v.id)"; case .pair(let a, let b): "p-\(a.id)-\(b.id)"; case .problem(let v): "x-\(v.id)" } }
    }

    static func blocks(_ videos: [VideoItem], singleColumn: Bool) -> [Block] {
        var out: [Block] = [], run: [VideoItem] = [], heroDone = false
        func flush() {
            var rest = run[...]
            if !heroDone, let first = rest.first { out.append(.hero(first)); rest = rest.dropFirst(); heroDone = true }
            while let a = rest.first {
                rest = rest.dropFirst()
                if !singleColumn, let b = rest.first { out.append(.pair(a, b)); rest = rest.dropFirst() } else { out.append(.hero(a)) }
            }
            run = []
        }
        for v in videos {
            if v.status == .complete { run.append(v) } else { flush(); out.append(.problem(v)) }
        }
        flush()
        return out
    }

    /// The share of the row's width the first of a pair takes: a vertical video beside a wide one keeps a narrow column.
    static func share(_ a: VideoItem, _ b: VideoItem) -> Double { a.isPortrait == b.isPortrait ? 0.5 : (a.isPortrait ? 0.35 : 0.65) }
    /// Both posters of a pair have the same height: taller when one of them is vertical.
    static func pairHeight(_ a: VideoItem, _ b: VideoItem) -> CGFloat { a.isPortrait || b.isPortrait ? 172 : 127 }
}

/// Two posters side by side, sharing the row's width by `VideoFeed.share`.
struct PairRow<Cell: View>: View {
    let a: VideoItem, b: VideoItem
    @ViewBuilder var cell: (VideoItem) -> Cell
    var body: some View {
        PairLayout(share: VideoFeed.share(a, b), spacing: Theme.Space.m) { cell(a); cell(b) }
    }
}

/// A two-column row: the first column takes `share` of the width (after the spacing), the second the rest; both start at the top.
struct PairLayout: Layout {
    var share: Double
    var spacing: CGFloat
    private func widths(_ total: CGFloat) -> (CGFloat, CGFloat) { let w = max(0, total - spacing); let first = (w * share).rounded(); return (first, w - first) }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let total: CGFloat = proposal.width ?? 320
        let (w1, w2) = widths(total)
        var h: CGFloat = 0
        for (view, w) in zip(subviews, [w1, w2]) { h = max(h, view.sizeThatFits(ProposedViewSize(width: w, height: nil)).height) }
        return CGSize(width: total, height: h)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (w1, w2) = widths(bounds.width)
        var x = bounds.minX
        for (view, w) in zip(subviews, [w1, w2]) {
            view.place(at: CGPoint(x: x, y: bounds.minY), anchor: .topLeading, proposal: ProposedViewSize(width: w, height: nil))
            x += w + spacing
        }
    }
}

struct RoundRectangle: Shape {
    let radius: CGFloat
    func path(in rect: CGRect) -> Path { RoundedRectangle(cornerRadius: radius, style: .continuous).path(in: rect) }
}

#if DEBUG
extension LibraryView {
    /// Screenshots: `VMK_DEBUG_CREATE=empty|filled|photos|options|notaffordable|q1|q2|summary|checking|checkingfast|unsupported|blocked|paused` opens Create in that state.
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
                Image(systemName: "exclamationmark.triangle").font(.role(.title, weight: .regular)).foregroundStyle(Theme.warning).frame(width: 56, height: 56).background(Theme.warningContainer, in: Circle()).accessibilityHidden(true)
                Spacer()
                IconButton(symbol: "xmark", label: tr("common.close"), identifier: "kindClose") { dismiss() }
            }.padding(.top, 14)
            Text(problem.paused ? tr("videos.creating_videos_is_paused") : tr("videos.we_cant_make_this_one")).textRole(.title).foregroundStyle(Theme.text).padding(.top, Theme.Space.l).accessibilityAddTraits(.isHeader)
            Text(problem.message).font(.role(.body)).foregroundStyle(Theme.textSecondary).padding(.top, Theme.Space.s)
            if problem.paused, let retry = RetryText.make(problem.retryAfter) { Text(retry).font(.role(.headline)).foregroundStyle(Theme.text).padding(.top, 6) }
            Spacer()
            Text(tr("create.nothing_was_charged")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary)
            PrimaryButton(title: tr("create.edit_request"), identifier: "editRequest") { onEdit(problem) }.padding(.top, Theme.Space.s)
        }
        .padding(.horizontal, Theme.gutter).padding(.bottom, 6)
        .presentationBackground(Theme.surface).presentationDetents([.height(420), .large]).presentationDragIndicator(.visible)
    }
}
