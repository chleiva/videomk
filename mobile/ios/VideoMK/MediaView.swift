import PhotosUI
import SwiftUI
import VideoMKCore

struct MediaView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase
    let media: MediaModel
    @State private var feed: PhotoFeed
    @State private var selection = PhotoSelection()
    @State private var pickerItems: [PhotosPickerItem] = []
    @State private var showStorage = false
    @State private var viewing: ViewerContext?
    @State private var showAddToCollection = false
    @State private var path: [MediaRoute] = []
    @State private var newCollection = false
    @FocusState private var searchFocused: Bool
    @State private var confirmCancelUploads = false
    @State private var tabVisible = false
    @State private var newName = ""
    @AppStorage("mediaPrivacyNoteSeen") private var privacySeen = false

    init(media: MediaModel) { self.media = media; _feed = State(initialValue: PhotoFeed(kind: .timeline, media: media)) }

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
            topBar
            SparkleRefreshScroll(action: { await media.loadSummary(); await feed.reload() }) {
                VStack(spacing: Theme.Space.m) {
                    if !privacySeen { PrivacyNote { withAnimation(reduceMotion ? nil : .snappy) { privacySeen = true } } }
                    MediaHeader(media: media) { showStorage = true }
                    if media.summary?.readOnly == true {
                        Label(tr("media.read_only_until_you_are"), systemImage: "lock.fill")
                            .font(.role(.footnote)).foregroundStyle(Theme.warning).padding(.horizontal, Theme.gutter).frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityIdentifier("readOnlyNote")
                    }
                    SearchBar(feed: feed, focused: $searchFocused)
                    if media.summary?.readOnly != true, !selection.active, !feed.isSearching, !(feed.photos.isEmpty && !showBatch) { AddPhotosButton(pickerItems: $pickerItems) }
                    ChipsRow(feed: feed)
                    content         // straight to the month grid: Collections live behind More, and "Select" in the bar needs no coach line
                }
                .padding(.top, Theme.Space.xs)
                .padding(.bottom, Theme.Space.l)
            }
            .scrollDismissesKeyboard(.interactively)
            }
            .background(Theme.background.ignoresSafeArea())
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: MediaRoute.self) { route in
                switch route {
                case .collections: CollectionsListView(media: media, onNew: { newCollection = true })
                case .collection(let c): CollectionDetailView(media: media, collection: c)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                TabBarRoom(reserve: !selection.active) {
                    if model.selectedTab == 1 { UndoToastHost() }
                    if let toast = media.toast { UploadToast(toast: toast, onAction: { media.dismissToast(); if toast.action == tr("org.view") { media.showCollectionsList = true } else { withAnimation(.snappy) { media.barExpanded = true } } }, onDismiss: { media.dismissToast() }) }
                    UploadBar(media: media, onManageStorage: { showStorage = true })
                    if media.bar == nil || media.bar?.kind == .finished { OrganizeBar(media: media) }
                    if showNextStep { NextStepBar(count: justAdded.count, onMake: { model.startVideo(with: justAdded) }, onDismiss: { withAnimation(reduceMotion ? nil : .snappy) { media.clearLastBatch() } }) }
                    if selection.active { SelectionBar(selection: selection, onVideo: makeVideo, icons: [.init(id: "addToCollection", symbol: "folder.badge.plus", label: tr("collections.add_to_collection")) { showAddToCollection = true }, .init(id: "deleteSelection", symbol: "trash", label: tr("common.delete"), danger: true) { deleteSelected() }]) }
                }
                .animation(reduceMotion ? nil : .snappy, value: media.toast)
                .animation(reduceMotion ? nil : .snappy, value: media.bar?.kind)
                .animation(reduceMotion ? nil : .snappy, value: media.organizeBar?.kind)
            }

        }
        .overlay { expandedPanel }
        .task { await media.start() }
        .onChange(of: selection.ordered) { _, ids in model.mediaSelection = ids.compactMap { id in feed.photos.first { $0.id == id } } }
        .onChange(of: selection.active) { _, on in model.mediaSelecting = on; if on { searchFocused = false } }      // Select puts the keyboard away: the selection bar sits at the bottom
        .onChange(of: path) { _, p in model.mediaPushed = !p.isEmpty }                                                // the tab bar steps aside on every pushed page
        .onChange(of: media.showCollectionsList, initial: true) { _, show in if show { media.showCollectionsList = false; if path.last != .collections { path.append(.collections) } } }
        .onChange(of: model.submitted) { _, _ in withAnimation(.snappy) { selection.clear() }; media.clearLastBatch() }
        .onDisappear { model.mediaSelecting = false }
        .onChange(of: settleKey) { _, _ in settleBatchIfDone() }
        .onAppear { tabVisible = true; media.setWatching("tab", true); Task { await media.refreshNow() } }      // the tab is shown again: look at the server now
        .onDisappear { tabVisible = false; media.setWatching("tab", false) }
        .sheet(item: Binding(get: { tabVisible ? media.pendingOrganize : nil }, set: { if $0 == nil { media.pendingOrganize = nil } })) { OrganizeSheet(media: media, request: $0) }
        .onChange(of: scenePhase) { _, phase in if phase == .active { Task { await media.refreshNow() } } }
        .task(id: media.version) { await feed.refreshIfNeeded() }
        .onChange(of: pickerItems) { _, items in
            guard !items.isEmpty else { return }
            let picked = items; pickerItems = []
            Task { await media.add(picked) }
        }
        .sheet(isPresented: $showStorage) { StorageSheet(media: media) }
        .sheet(isPresented: $showAddToCollection) {
            AddToCollectionSheet(media: media, photoIDs: selection.ordered) { selection.clear() }
        }
        .fullScreenCover(item: $viewing) { ctx in
            PhotoViewer(media: media, photos: ctx.photos, start: ctx.index, onDeleted: { feed.remove([$0]) }, onMakeVideo: { photo in viewing = nil; send([photo]) })
        }

        .alert(tr("media.new_collection"), isPresented: $newCollection) {
            TextField(tr("media.name"), text: $newName)
            Button(tr("media.create")) { let n = newName; newName = ""; Task { _ = await media.createCollection(name: n) } }
            Button(tr("common.cancel"), role: .cancel) { newName = "" }
        }
        .alert(tr("media.heads_up"), isPresented: Binding(get: { media.notice != nil }, set: { if !$0 { media.notice = nil } })) {
            Button(tr("media.ok"), role: .cancel) {}
        } message: { Text(media.notice ?? "") }
    }

    @ViewBuilder private var content: some View {
        switch feed.state {
        case .loading: SkeletonGrid()
        case .failed(let message):
            MediaMessage(symbol: "wifi.exclamationmark", title: tr("add.couldnt_load_your_photos"), text: message, button: tr("common.try_again")) { Task { await feed.reload() } }
        case .loaded:
            if showBatch { UploadBatchSection(media: media, listed: listed).padding(.bottom, 4) }
            if feed.photos.isEmpty {
                if showBatch { EmptyView() }
                else if feed.isSearching && !feed.searching {
                    MediaMessage(symbol: "magnifyingglass", title: tr("media.no_photos_match"), text: tr("media.try_fewer_words_or_remove"), button: nil) {}
                } else if !feed.isSearching {
                    EmptyLibrary(pickerItems: $pickerItems, readOnly: media.summary?.readOnly == true)
                }
            } else {
                if feed.offline { Label(tr("media.offline_showing_whats_saved_on"), systemImage: "icloud.slash").font(.role(.caption)).foregroundStyle(Theme.textSecondary) }
                PhotoGrid(feed: feed, media: media, selection: selection, onOpen: { open($0) }, hidden: batchIDs.union(media.hiddenPhotos))
            }
        }
    }

    /// The one top bar: the large title with Select and one overflow (Add photos is the labelled button under the search field).
    /// While selecting: Cancel, how many are selected, Select all.
    @ViewBuilder private var topBar: some View {
        if selection.active {
            ZStack {
                Text(selection.count == 0 ? tr("media.select_photos") : tr("attach.selected", selection.count)).font(.role(.headline)).monospacedDigit().foregroundStyle(Theme.text).lineLimit(1).minimumScaleFactor(0.7)
                    .padding(.horizontal, 96).accessibilityAddTraits(.isHeader).accessibilityIdentifier("selectionTitle")
                HStack {
                    Button(tr("common.cancel")) { withAnimation(.snappy) { selection.clear() } }.buttonStyle(TextButtonStyle()).accessibilityIdentifier("selectCancel")
                    Spacer(minLength: Theme.Space.s)
                    if !feed.photos.isEmpty {
                        let all = SelectAll.allSelected(view: feed.photos.map(\.id), selected: selection.ordered)
                        Button(all ? tr("select_all.clear") : tr("media.all_short")) {
                            Haptics.play(.selection)
                            Task { await SelectionActions.toggleAll(feed: feed, selection: selection, limit: PhotoLimits.maxPhotos) }
                        }
                        .buttonStyle(TextButtonStyle())
                        .accessibilityLabel(SelectAll.label(viewCount: feed.photos.count, hasMore: feed.canLoadMore, allSelected: all)).accessibilityIdentifier("selectAll")
                    }
                }
            }
            .padding(.horizontal, Theme.gutter).frame(minHeight: 56).vmkOneLineCap()
        } else {
            TopBar(title: tr("media.media")) {
                if !feed.photos.isEmpty {
                    Button(tr("media.select")) { searchFocused = false; withAnimation(.snappy) { selection.active = true } }.buttonStyle(TextButtonStyle()).accessibilityIdentifier("selectButton")
                }
                Menu {
                    if !media.shownCollections.isEmpty { Button { path.append(.collections) } label: { Label(tr("viewer.collections"), systemImage: "folder") }.accessibilityIdentifier("seeAllCollections") }
                    Button { newCollection = true } label: { Label(tr("media.new_collection"), systemImage: "folder.badge.plus") }.accessibilityIdentifier("newCollectionMenu")
                    Button { media.organizeLibrary() } label: { Label(tr("media.organize_my_library"), systemImage: "sparkles") }.accessibilityIdentifier("organizeLibrary")
                    Button { showStorage = true } label: { Label(tr("media.storage"), systemImage: "externaldrive") }
                } label: { IconButtonFace(symbol: "ellipsis") }
                    .menuOrder(.fixed).accessibilityLabel(tr("media.more")).accessibilityIdentifier("mediaMore")
            }
        }
    }

    // MARK: next step

    /// The photos of the last upload batch that the server already lists: "Make a video from these" is offered until it is used or dismissed.
    private var justAdded: [LibraryPhoto] {
        let ids = Set(media.lastBatchIDs)
        return ids.isEmpty ? [] : feed.photos.filter { ids.contains($0.id) }
    }
    private var showNextStep: Bool { !selection.active && !justAdded.isEmpty && !feed.isSearching && (media.bar == nil || media.bar?.kind == .finished) }


    // MARK: the upload batch in the grid

    private var showBatch: Bool { !feed.isSearching && !media.queueItems.isEmpty }
    /// Photos of the batch that the server already lists: shown in the batch section, so the timeline skips them (no duplicate squares).
    private var batchIDs: Set<String> { showBatch ? Set(media.queueItems.compactMap(\.libraryID)) : [] }
    private var listed: [String: LibraryPhoto] { Dictionary(feed.photos.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a }) }
    private var settleKey: String { "\(media.queueItems.map { "\($0.state.rawValue)" }.joined())|\(feed.photos.count)" }

    /// Everything uploaded is listed: after a beat the "Adding" section folds into the month header (the queue entries are cleared).
    private func settleBatchIfDone() {
        let items = media.queueItems
        guard !items.isEmpty, items.allSatisfy({ $0.state == .done || $0.state == .duplicate }),
              UploadTiles.isSettled(items, listedIDs: Set(feed.photos.map(\.id))) else { return }
        Task {
            try? await Task.sleep(for: .milliseconds(1400))
            let again = media.queueItems
            if !again.isEmpty, again.allSatisfy({ $0.state == .done || $0.state == .duplicate }) { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { media.dismissUploads() } }
        }
    }

    @ViewBuilder private var expandedPanel: some View {
        if media.barExpanded, media.bar != nil {
            ZStack(alignment: .bottom) {
                Theme.mediaInk.opacity(0.18).ignoresSafeArea().onTapGesture { withAnimation(.snappy) { media.barExpanded = false } }.accessibilityHidden(true)
                UploadPanel(media: media, onClose: { withAnimation(.snappy) { media.barExpanded = false } }, cancel: { confirmCancelUploads = true })
                    .padding(.bottom, Theme.floatingBarHeight + Theme.Space.s)
            }
            .transition(.opacity)
            .confirmationDialog(tr("media.cancel_remaining_uploads"), isPresented: $confirmCancelUploads, titleVisibility: .visible) {
                Button(tr("media.cancel_remaining"), role: .destructive) { media.cancelUploads() }
                Button(tr("media.keep_uploading"), role: .cancel) {}
            } message: { Text(tr("media.photos_already_added_stay")) }
        }
    }

    private func open(_ photo: LibraryPhoto) {
        let list = feed.photos
        viewing = ViewerContext(photos: list, index: list.firstIndex(of: photo) ?? 0)
    }

    /// Create opens over Media with the ticked photos attached. The selection stays ticked: closing Create brings the person back to it,
    /// and it clears itself once the video is sent.
    private func makeVideo() {
        let chosen = selection.ordered.compactMap { id in feed.photos.first { $0.id == id } }
        model.startVideo(with: chosen)
    }

    private func send(_ photos: [LibraryPhoto]) { model.startVideo(with: photos) }

    /// No question: the photos leave the grid at once and "Deleted · Undo" shows for six seconds.
    private func deleteSelected() {
        let ids = Array(selection.ids), feed = feed
        withAnimation(.snappy) { selection.clear() }
        media.deletePhotos(ids, undo: model.undo) { feed.remove($0) }
    }
}

struct ViewerContext: Identifiable { let id = UUID(); let photos: [LibraryPhoto]; let index: Int }

// MARK: header, search, chips

struct MediaHeader: View {
    let media: MediaModel
    let onTap: () -> Void
    var body: some View {
        if let meter = media.meter, meter.state != .ok || meter.fraction >= 0.5 {      // a thin line at 5% tells nobody anything: it shows from half full (Storage is always in the More menu)
            Button(action: onTap) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(meter.label).font(.role(.footnote, weight: .medium)).foregroundStyle(meter.state == .ok ? Theme.textSecondary : tint(meter))
                        if meter.state != .ok { Text(meter.state == .full ? tr("media.full") : tr("media.almost_full")).font(.role(.footnote, weight: .semibold)).foregroundStyle(tint(meter)) }
                        Spacer()
                        Image(systemName: "chevron.right").font(.role(.caption)).foregroundStyle(Theme.textSecondary)
                    }
                    ProgressView(value: meter.fraction).tint(tint(meter)).scaleEffect(x: 1, y: 0.7)
                }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, Theme.gutter)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(tr(meter.state == .full ? "media.storage_a11y_full" : meter.state == .warning ? "media.storage_a11y_warning" : "media.storage_a11y", meter.label))
            .accessibilityHint(tr("media.shows_your_storage"))
            .accessibilityIdentifier("storageMeter")
        } else if media.summaryError != nil {
            EmptyView()
        }
    }
    private func tint(_ m: StorageMeter) -> Color { m.state == .full ? Theme.danger : m.state == .warning ? Theme.warning : Theme.primary }
}

/// The search field. While it has the focus a Cancel text button sits beside it (it clears the words and puts the keyboard away).
struct SearchBar: View {
    @Bindable var feed: PhotoFeed
    var focused: FocusState<Bool>.Binding?
    @FocusState private var ownFocus: Bool
    private var isFocused: Bool { focused?.wrappedValue ?? ownFocus }
    var body: some View {
        HStack(spacing: Theme.Space.s) {
            HStack(spacing: Theme.Space.s) {
                Image(systemName: "magnifyingglass").foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                TextField(tr("media.search_your_photos_try_beach"), text: $feed.text).font(.role(.body))
                    .focused(focused ?? $ownFocus).submitLabel(.search).textInputAutocapitalization(.never).autocorrectionDisabled()
                    .accessibilityIdentifier("mediaSearch")
                if feed.searching { ProgressView().controlSize(.small) }
                else if !feed.text.isEmpty {
                    Button { feed.text = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.textSecondary).frame(width: Theme.minTouch, height: Theme.minTouch).contentShape(Rectangle()) }
                        .buttonStyle(.plain).padding(.trailing, -Theme.Space.m).accessibilityLabel(tr("media.clear_search")).accessibilityIdentifier("clearSearch")
                }
            }
            .padding(.horizontal, Theme.Space.l).frame(minHeight: 48)
            .background(Theme.surfaceRaised, in: Capsule())
            if isFocused {
                Button(tr("common.cancel")) { feed.text = ""; if let focused { focused.wrappedValue = false } else { ownFocus = false } }
                    .buttonStyle(TextButtonStyle()).transition(.move(edge: .trailing).combined(with: .opacity)).accessibilityIdentifier("searchCancel")
            }
        }
        .padding(.horizontal, Theme.gutter)
        .animation(Theme.Motion.select, value: isFocused)
    }
}

struct ChipsRow: View {
    let feed: PhotoFeed
    var body: some View {
        if feed.isSearching, !feed.chips.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(feed.chips, id: \.self) { chip in
                        Button { Task { await feed.drop(chip) } } label: {
                            HStack(spacing: 4) {
                                Image(systemName: chip.kind == "place" ? "mappin.and.ellipse" : chip.kind == "date" ? "calendar" : "tag").font(.role(.caption))
                                Text(chip.label).font(.role(.footnote, weight: .medium)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                                Image(systemName: "xmark").font(.role(.caption, weight: .bold))
                            }
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Theme.primary.opacity(0.15), in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous)).foregroundStyle(Theme.primary)
                        }
                        .accessibilityLabel(tr("media.chip_a11y", chip.label))
                        .accessibilityHint(tr("media.double_tap_to_remove_this"))
                        .accessibilityIdentifier("searchChip")
                    }
                }
                .padding(.horizontal, Theme.gutter)
            }
        }
    }
}

// MARK: banners, messages, empty

struct PrivacyNote: View {
    let onDismiss: () -> Void
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "lock.shield.fill").foregroundStyle(Theme.primary).accessibilityHidden(true)
            Text(MediaCopy.privacy).font(.role(.footnote)).foregroundStyle(Theme.text)
            Button(action: onDismiss) { Image(systemName: "xmark").font(.role(.footnote, weight: .semibold)).frame(width: Theme.minTouch, height: Theme.minTouch).contentShape(Rectangle()) }.buttonStyle(.plain).padding(.top, -Theme.Space.m).padding(.trailing, -Theme.Space.m)
                .accessibilityLabel(tr("media.dismiss_privacy_note")).foregroundStyle(Theme.textSecondary)
        }
        .padding(12).background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .padding(.horizontal, Theme.gutter).accessibilityIdentifier("mediaPrivacyNote")
    }
}

enum MediaCopy {
    /// Where "Get more storage" goes. None is configured yet, so the button stays hidden even when the server says `can_upgrade`.
    static let upgradeURL: URL? = nil
    static var privacy: String { tr("media.privacy_note") }
}

struct MediaMessage: View {
    let symbol: String, title: String, text: String, button: String?
    let action: () -> Void
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: symbol).font(.vmk(40)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            Text(title).font(.role(.headline)).foregroundStyle(Theme.text)
            Text(text).font(.role(.subhead)).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
            if let button { Button(button, action: action).buttonStyle(TonalButtonStyle(fullWidth: false)) }
        }
        .padding(32).frame(maxWidth: .infinity)
    }
}

struct EmptyLibrary: View {
    @Binding var pickerItems: [PhotosPickerItem]
    var readOnly = false
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "photo.stack").font(.vmk(48)).foregroundStyle(Theme.gradient).accessibilityHidden(true)
            Text(tr("media.your_photos_in_one_private")).font(.role(.title)).foregroundStyle(Theme.text).multilineTextAlignment(.center)
            Text(tr("media.add_photos_once_find_them"))
                .font(.role(.subhead)).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
            if !readOnly {
                PhotosPicker(selection: $pickerItems, maxSelectionCount: nil, matching: .images) { Label(tr("media.add_photos"), systemImage: "photo.badge.plus") }
                    .buttonStyle(PrimaryButtonStyle(fullWidth: false)).accessibilityIdentifier("emptyAddPhotos")
            }
        }
        .padding(32).frame(maxWidth: .infinity)
    }
}

/// The one upload action: a labelled button right under the title (an icon alone in the bar was not found).
struct AddPhotosButton: View {
    @Binding var pickerItems: [PhotosPickerItem]
    var body: some View {
        PhotosPicker(selection: $pickerItems, maxSelectionCount: nil, matching: .images) { Label(tr("media.add_photos"), systemImage: "photo.badge.plus") }
            .buttonStyle(TonalButtonStyle())
            .accessibilityHint(tr("media.add_photos_to_your_library")).accessibilityIdentifier("addToLibraryButton")
            .padding(.horizontal, Theme.gutter)
    }
}

// MARK: selection bar, next step

/// While selecting: ONE primary button (Make a video with the count) and two quiet icons. "Select all" and Cancel live in the navigation bar.
struct SelectionBar: View {
    struct Icon: Identifiable { let id: String; let symbol: String; let label: String; var danger = false; let run: () -> Void }
    @Bindable var selection: PhotoSelection
    let onVideo: () -> Void
    let icons: [Icon]
    var body: some View {
        HStack(spacing: 10) {
            Button(action: onVideo) {
                HStack(spacing: Theme.Space.s) {
                    PlaySparkle(scale: 0.7)
                    Text(selection.count == 0 ? tr("collections.make_a_video") : tr("media.make_video_n", selection.count)).monospacedDigit().lineLimit(1).minimumScaleFactor(0.8)
                }
            }
            .buttonStyle(PrimaryButtonStyle()).disabled(selection.count == 0)
            .accessibilityLabel(selection.count == 0 ? tr("media.select_first") : tr("media.make_video_n", selection.count)).accessibilityIdentifier("makeVideoFromSelection")
            ForEach(icons) { i in icon(i.symbol, i.label, i.id, i.run, danger: i.danger) }
        }
        .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.xl).padding(.bottom, Theme.Space.s)
        .background { LinearGradient(colors: [Theme.background.opacity(0), Theme.background.opacity(0.92)], startPoint: .top, endPoint: .bottom).ignoresSafeArea(edges: .bottom).allowsHitTesting(false) }
        .vmkOneLineCap()
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }
    private func icon(_ symbol: String, _ label: String, _ id: String, _ run: @escaping () -> Void, danger: Bool = false) -> some View {
        Button(action: run) {
            IconButtonFace(symbol: symbol, style: .glass, size: Theme.primaryHeight, tint: danger ? Theme.danger : nil)
        }
        .buttonStyle(.plain).disabled(selection.count == 0).opacity(selection.count == 0 ? 0.45 : 1)
        .accessibilityLabel(label).accessibilityIdentifier(id)
    }
}

/// After an upload finishes: the obvious next step, one tap from the photos just added (stays until used or dismissed).
struct NextStepBar: View {
    let count: Int
    let onMake: () -> Void
    let onDismiss: () -> Void
    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.success).accessibilityHidden(true)
                Text(tr("upload.summary_added", count)).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text)
                Spacer(minLength: 4)
                Button(action: onDismiss) { Image(systemName: "xmark").font(.role(.footnote, weight: .bold)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44) }
                    .accessibilityLabel(tr("common.close")).accessibilityIdentifier("nextStepDismiss")
            }
            Button(action: onMake) {
                HStack(spacing: Theme.Space.s) { PlaySparkle(scale: 0.7); Text(tr("media.make_video_n", count)).monospacedDigit() }
            }
            .buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("makeVideoFromNew")
        }
        .padding(.horizontal, Theme.gutter).padding(.top, 6).padding(.bottom, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
        .elevation(3)
        .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.s)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .accessibilityElement(children: .contain).accessibilityIdentifier("nextStepBar")
    }
}

// MARK: storage

struct StorageSheet: View {
    let media: MediaModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    var body: some View {
        FittedSheet {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                SheetHeader(title: tr("media.storage"), closeID: "storageClose") { dismiss() }
                if let s = media.summary {
                    let meter = StorageMeter(used: s.usedBytes, limit: s.limitBytes)
                    let tint = meter.state == .full ? Theme.danger : meter.state == .warning ? Theme.warning : Theme.primary
                    VStack(alignment: .leading, spacing: Theme.Space.s) {
                        Text(meter.label).textRole(.title).foregroundStyle(Theme.text)
                        ProgressView(value: meter.fraction).tint(tint)
                            .accessibilityLabel(tr("media.storage")).accessibilityValue(meter.label)       // the bar says what it measures and how full it is
                        if meter.state != .ok { Label(meter.state == .full ? tr("media.full") : tr("media.almost_full"), systemImage: "exclamationmark.circle").font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.text) }
                    }
                    .accessibilityIdentifier("storageMeterDetail")
                    VStack(spacing: 0) {
                        row(tr("media.plan"), s.plan == "pro" ? tr("media.pro") : tr("media.free"))
                        Divider().overlay(Theme.outline)
                        row(tr("create.photos"), "\(s.count)")
                        Divider().overlay(Theme.outline)
                        row(tr("media.left"), StorageMeter.format(meter.remaining))
                    }
                    Text(tr("media.photos_that_fit_are_still")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                    if s.canUpgrade, let url = MediaCopy.upgradeURL { Button(tr("media.get_more_storage")) { openURL(url) }.buttonStyle(TonalButtonStyle()).accessibilityIdentifier("upgradeStorage") }
                } else { LiveSpinner().frame(maxWidth: .infinity).padding(.vertical, Theme.Space.xxl) }
                Label(MediaCopy.privacy, systemImage: "lock.shield").font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .task { await media.loadSummary() }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack { Text(label).foregroundStyle(Theme.text); Spacer(minLength: Theme.Space.s); Text(value).foregroundStyle(Theme.textSecondary).monospacedDigit() }
            .font(.role(.body)).frame(minHeight: Theme.minTouch).accessibilityElement(children: .combine)
    }
}

/// Select all / Clear on the Media tab and in a collection: everything in view, more pages loaded up to the limit one video can hold.
@MainActor enum SelectionActions {
    static func toggleAll(feed: PhotoFeed, selection: PhotoSelection, limit: Int) async {
        let view = feed.photos.map(\.id)
        if SelectAll.allSelected(view: view, selected: selection.ordered) { selection.set(SelectAll.clear(view: view, selected: selection.ordered)); return }
        await feed.loadAll(upTo: limit)
        let r = SelectAll.apply(view: feed.photos.map(\.id), selected: selection.ordered, room: limit - selection.count)
        selection.set(r.selected)
        if r.limited || (feed.canLoadMore && selection.count >= limit) { UIAccessibility.post(notification: .announcement, argument: SelectAll.limitNote) }
    }
}
