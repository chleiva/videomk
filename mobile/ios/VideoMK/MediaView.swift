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
    @State private var confirmDelete = false
    @State private var newCollection = false
    @State private var confirmCancelUploads = false
    @State private var tabVisible = false
    @State private var newName = ""
    @AppStorage("mediaPrivacyNoteSeen") private var privacySeen = false

    init(media: MediaModel) { self.media = media; _feed = State(initialValue: PhotoFeed(kind: .timeline, media: media)) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    if !privacySeen { PrivacyNote { withAnimation(reduceMotion ? nil : .snappy) { privacySeen = true } } }
                    MediaHeader(media: media) { showStorage = true }
                    if media.summary?.readOnly == true {
                        Label(tr("media.read_only_until_you_are"), systemImage: "lock.fill")
                            .font(.footnote).foregroundStyle(Theme.warning).padding(.horizontal, 16).frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityIdentifier("readOnlyNote")
                    }
                    SearchBar(feed: feed)
                    ChipsRow(feed: feed)
                    if !feed.isSearching { CollectionsStrip(media: media, onNew: { newCollection = true }) }
                    content
                }
                .padding(.top, 4)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle(tr("media.media"))
            .navigationBarTitleDisplayMode(.large)
            .navigationDestination(for: LibraryCollection.self) { CollectionDetailView(media: media, collection: $0) }
            .navigationDestination(isPresented: Binding(get: { media.showCollectionsList }, set: { media.showCollectionsList = $0 })) { CollectionsListView(media: media) }
            .toolbar { toolbar }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                VStack(spacing: 0) {
                    if let toast = media.toast { UploadToast(toast: toast, onAction: { media.dismissToast(); if toast.action == tr("org.view") { media.showCollectionsList = true } else { withAnimation(.snappy) { media.barExpanded = true } } }, onDismiss: { media.dismissToast() }) }
                    UploadBar(media: media, onManageStorage: { showStorage = true })
                    if media.bar == nil || media.bar?.kind == .finished { OrganizeBar(media: media) }
                    if selection.active { SelectionBar(selection: selection, feed: feed, onCollection: { showAddToCollection = true }, onVideo: makeVideo, onDelete: { confirmDelete = true }) }
                }
                .animation(reduceMotion ? nil : .snappy, value: media.toast)
                .animation(reduceMotion ? nil : .snappy, value: media.bar?.kind)
                .animation(reduceMotion ? nil : .snappy, value: media.organizeBar?.kind)
            }
            .refreshable { await media.loadSummary(); await feed.reload() }
        }
        .overlay { expandedPanel }
        .task { await media.start() }
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
        .confirmationDialog(tr("media.delete_title", selection.count), isPresented: $confirmDelete, titleVisibility: .visible) {
            Button(tr("media.delete_button", selection.count), role: .destructive) {
                let ids = selection.ids
                Task { if await media.delete(Array(ids)) { feed.remove(ids); selection.clear() } }
            }
        } message: { Text(tr("media.they_are_removed_from_your")) }
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
                if feed.offline { Label(tr("media.offline_showing_whats_saved_on"), systemImage: "icloud.slash").font(.caption).foregroundStyle(Theme.textSecondary) }
                PhotoGrid(feed: feed, media: media, selection: selection, onOpen: { open($0) }, hidden: batchIDs)
            }
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .topBarLeading) {
            if selection.active { Button(tr("common.cancel")) { withAnimation(.snappy) { selection.clear() } } }
        }
        ToolbarItemGroup(placement: .topBarTrailing) {
            if !feed.photos.isEmpty {
                Button(selection.active ? tr("common.done") : tr("media.select")) { withAnimation(.snappy) { if selection.active { selection.clear() } else { selection.active = true } } }
                    .accessibilityIdentifier("selectButton")
            }
            if media.summary?.readOnly != true {
                PhotosPicker(selection: $pickerItems, maxSelectionCount: nil, matching: .images) { Image(systemName: "plus") }
                    .accessibilityLabel(tr("media.add_photos_to_your_library")).accessibilityIdentifier("addToLibraryButton")
            }
            Menu {
                Button { media.organizeLibrary() } label: { Label(tr("media.organize_my_library"), systemImage: "sparkles") }.accessibilityIdentifier("organizeLibrary")
                Button { showStorage = true } label: { Label(tr("media.storage"), systemImage: "externaldrive") }
            } label: { Image(systemName: "ellipsis") }
                .accessibilityLabel(tr("media.more")).accessibilityIdentifier("mediaMore")
        }
    }

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
                Color.black.opacity(0.18).ignoresSafeArea().onTapGesture { withAnimation(.snappy) { media.barExpanded = false } }.accessibilityHidden(true)
                UploadPanel(media: media, onClose: { withAnimation(.snappy) { media.barExpanded = false } }, cancel: { confirmCancelUploads = true })
                    .padding(.bottom, 70)
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

    private func makeVideo() {
        let chosen = feed.photos.filter { selection.contains($0.id) }
        send(chosen)
        selection.clear()
    }

    private func send(_ photos: [LibraryPhoto]) {
        model.composerLibrary = Array(photos.prefix(PhotoLimits.maxPhotos))
        model.selectedTab = 0
        model.createRequested = true
    }
}

struct ViewerContext: Identifiable { let id = UUID(); let photos: [LibraryPhoto]; let index: Int }

// MARK: header, search, chips

struct MediaHeader: View {
    let media: MediaModel
    let onTap: () -> Void
    var body: some View {
        if let meter = media.meter {
            Button(action: onTap) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(meter.label).font(.footnote.weight(.medium)).foregroundStyle(meter.state == .ok ? Theme.textSecondary : tint(meter))
                        if meter.state != .ok { Text(meter.state == .full ? tr("media.full") : tr("media.almost_full")).font(.footnote.weight(.semibold)).foregroundStyle(tint(meter)) }
                        Spacer()
                        Image(systemName: "chevron.right").font(.caption2).foregroundStyle(Theme.textSecondary)
                    }
                    ProgressView(value: meter.fraction).tint(tint(meter)).scaleEffect(x: 1, y: 0.7)
                }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
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

struct SearchBar: View {
    @Bindable var feed: PhotoFeed
    @FocusState private var focused: Bool
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            TextField(tr("media.search_your_photos_try_beach"), text: $feed.text).font(.system(size: 15))
                .focused($focused).submitLabel(.search).textInputAutocapitalization(.never).autocorrectionDisabled()
                .accessibilityIdentifier("mediaSearch")
            if feed.searching { ProgressView().controlSize(.small) }
            else if !feed.text.isEmpty { Button { feed.text = "" } label: { Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.textSecondary) }.accessibilityLabel(tr("media.clear_search")) }
        }
        .padding(.horizontal, 12).frame(minHeight: 40)
        .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .padding(.horizontal, 16)
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
                                Image(systemName: chip.kind == "place" ? "mappin.and.ellipse" : chip.kind == "date" ? "calendar" : "tag").font(.caption2)
                                Text(chip.label).font(.footnote.weight(.medium)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                                Image(systemName: "xmark").font(.system(size: 9, weight: .bold))
                            }
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Theme.primary.opacity(0.15), in: RoundedRectangle(cornerRadius: 16, style: .continuous)).foregroundStyle(Theme.primary)
                        }
                        .accessibilityLabel(tr("media.chip_a11y", chip.label))
                        .accessibilityHint(tr("media.double_tap_to_remove_this"))
                        .accessibilityIdentifier("searchChip")
                    }
                }
                .padding(.horizontal, 16)
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
            Text(MediaCopy.privacy).font(.footnote).foregroundStyle(Theme.text)
            Button(action: onDismiss) { Image(systemName: "xmark").font(.footnote.weight(.semibold)) }.accessibilityLabel(tr("media.dismiss_privacy_note")).foregroundStyle(Theme.textSecondary)
        }
        .padding(12).background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .padding(.horizontal, 16).accessibilityIdentifier("mediaPrivacyNote")
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
            Image(systemName: symbol).font(.system(size: 40)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            Text(title).font(.headline).foregroundStyle(Theme.text)
            Text(text).font(.subheadline).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
            if let button { Button(button, action: action).buttonStyle(.borderedProminent) }
        }
        .padding(32).frame(maxWidth: .infinity)
    }
}

struct EmptyLibrary: View {
    @Binding var pickerItems: [PhotosPickerItem]
    var readOnly = false
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: "photo.stack").font(.system(size: 48)).foregroundStyle(Theme.gradient).accessibilityHidden(true)
            Text(tr("media.your_photos_in_one_private")).font(.title3.bold()).foregroundStyle(Theme.text).multilineTextAlignment(.center)
            Text(tr("media.add_photos_once_find_them"))
                .font(.subheadline).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
            if !readOnly {
                PhotosPicker(selection: $pickerItems, maxSelectionCount: nil, matching: .images) { Text(tr("create.add_photos")).font(.headline).frame(maxWidth: 240, minHeight: 48) }
                    .buttonStyle(.borderedProminent).accessibilityIdentifier("emptyAddPhotos")
            }
        }
        .padding(32).frame(maxWidth: .infinity)
    }
}

// MARK: selection bar

struct SelectionBar: View {
    @Bindable var selection: PhotoSelection
    let feed: PhotoFeed
    let onCollection: () -> Void, onVideo: () -> Void, onDelete: () -> Void
    var body: some View {
        VStack(spacing: 8) {
            HStack {
                Text(selection.count == 0 ? tr("media.select_photos") : tr("attach.selected", selection.count)).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.text)
                Spacer()
                if !feed.photos.isEmpty {
                    let all = SelectAll.allSelected(view: feed.photos.map(\.id), selected: selection.ordered)
                    Button(SelectAll.label(viewCount: feed.photos.count, hasMore: feed.canLoadMore, allSelected: all)) {
                        UISelectionFeedbackGenerator().selectionChanged()
                        Task { await SelectionActions.toggleAll(feed: feed, selection: selection, limit: PhotoLimits.maxPhotos) }
                    }.font(.system(size: 15, weight: .semibold)).frame(minHeight: 44)
                        .accessibilityIdentifier("selectAll")
                }
            }
            HStack {
                action("folder.badge.plus", tr("collections.add_to_collection"), onCollection)
                action("sparkles.tv", tr("collections.make_a_video"), onVideo)
                action("trash", tr("common.delete"), onDelete, role: .destructive)
            }
            .disabled(selection.count == 0)
        }
        .padding(.horizontal, 16).padding(.vertical, 10).background(.bar)
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }
    private func action(_ symbol: String, _ title: String, _ run: @escaping () -> Void, role: ButtonRole? = nil) -> some View {
        Button(role: role, action: run) {
            VStack(spacing: 2) { Image(systemName: symbol).font(.title3); Text(title).font(.caption2) }.frame(maxWidth: .infinity, minHeight: 44)
        }
        .accessibilityLabel(title)
    }
}

// MARK: storage

struct StorageSheet: View {
    let media: MediaModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    var body: some View {
        NavigationStack {
            List {
                if let s = media.summary {
                    let meter = StorageMeter(used: s.usedBytes, limit: s.limitBytes)
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(meter.label).font(.title3.weight(.semibold)).foregroundStyle(meter.state == .full ? Theme.danger : meter.state == .warning ? Theme.warning : Theme.text)
                            ProgressView(value: meter.fraction).tint(meter.state == .full ? Theme.danger : meter.state == .warning ? Theme.warning : Theme.primary)
                        }
                        LabeledContent(tr("media.plan"), value: s.plan == "pro" ? tr("media.pro") : tr("media.free"))
                        LabeledContent(tr("create.photos"), value: "\(s.count)")
                        LabeledContent(tr("media.left"), value: StorageMeter.format(meter.remaining))
                    }
                    Section(tr("media.when_it_is_full")) {
                        Text(tr("media.photos_that_fit_are_still"))
                            .font(.subheadline)
                    }
                    if s.canUpgrade, let url = MediaCopy.upgradeURL {
                        Section { Button(tr("media.get_more_storage")) { openURL(url) }.accessibilityIdentifier("upgradeStorage") }
                    }
                } else { ProgressView().frame(maxWidth: .infinity) }
                Section(tr("media.privacy")) { Text(MediaCopy.privacy).font(.subheadline) }
            }
            .navigationTitle(tr("media.storage")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
        .task { await media.loadSummary() }
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
