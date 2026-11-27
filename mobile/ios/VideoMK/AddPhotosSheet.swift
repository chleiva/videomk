import PhotosUI
import SwiftUI
import VideoMKCore

/// Photos for the video come from two places, each one tap from the photo icon of Create (a two-item menu, no explainer in between):
/// "Photo library" opens the system picker directly (it runs in its own process: videomk only receives the photos that are tapped, and no permission
/// is asked), and "Media" opens this sheet, the person's own library with the same top bar and one primary button as the Media tab ("Add · 3").
struct LibraryPickerSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let attached: Int
    let onAdd: ([LibraryPhoto]) -> Void

    @State private var selection = PhotoSelection()
    @State private var feeds: [String: PhotoFeed] = [:]
    @State private var collectionID: String?
    @State private var toast: String?
    @State private var addingToLibrary: [PhotosPickerItem] = []

    private var media: MediaModel? { model.media }
    private var currentFeed: PhotoFeed? { feeds[collectionID ?? "all"] }
    private var cap: Int { AttachSelection(attached: attached, phone: [], library: selection.ordered).libraryCap }
    private var allSelected: Bool { currentFeed.map { SelectAll.allSelected(view: $0.photos.map(\.id), selected: selection.ordered) } ?? false }

    var body: some View {
        VStack(spacing: 0) {
            topBar
            Group {
                if let media {
                    LibraryChooser(media: media, selection: selection, collectionID: $collectionID, feeds: $feeds, onLimit: { showToast(tr("add.limit_toast", PhotoLimits.maxPhotos)) }, addingToLibrary: $addingToLibrary)
                } else {
                    MediaMessage(symbol: "photo.on.rectangle", title: tr("add.my_media_isnt_available"), text: tr("add.sign_in_again_to_use"), button: nil) {}
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                if let toast { ToastBar(text: toast, symbol: "info.circle", identifier: "limitToast") }
                Button { commit() } label: {
                    HStack(spacing: Theme.Space.s) { Image(systemName: "photo.badge.plus").accessibilityHidden(true); Text(selection.count == 0 ? tr("attach.add") : tr("attach.add_dot_n", selection.count)).monospacedDigit() }
                }
                .buttonStyle(PrimaryButtonStyle()).disabled(selection.count == 0)
                .accessibilityIdentifier("addSelected")
                .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.xl).padding(.bottom, Theme.Space.s)
                .background { LinearGradient(colors: [Theme.surface.opacity(0), Theme.surface], startPoint: .top, endPoint: .center).ignoresSafeArea(edges: .bottom).allowsHitTesting(false) }
            }
        }
        .presentationBackground(Theme.surface)
        .presentationDetents([.large]).presentationDragIndicator(.visible)
        .onChange(of: selection.count, initial: true) { _, _ in selection.limit = cap; selection.active = true }
        .onChange(of: addingToLibrary) { _, items in
            guard !items.isEmpty, let media else { return }
            let picked = items; addingToLibrary = []
            Task { await media.add(picked) }
        }
    }

    /// The Media tab's selecting bar: Cancel, how many are selected, Select all.
    private var topBar: some View {
        ZStack {
            Text(selection.count == 0 ? tr("media.media") : tr("attach.selected", selection.count)).font(.role(.headline)).monospacedDigit().foregroundStyle(Theme.text).lineLimit(1).minimumScaleFactor(0.7)
                .padding(.horizontal, 96).accessibilityAddTraits(.isHeader).accessibilityIdentifier("pickerTitle")
            HStack {
                Button(tr("common.cancel")) { dismiss() }.buttonStyle(TextButtonStyle()).accessibilityIdentifier("addCancel")
                Spacer(minLength: Theme.Space.s)
                if let feed = currentFeed, !feed.photos.isEmpty {
                    Button(allSelected ? tr("select_all.clear") : tr("media.all_short")) { selectAllTapped(feed) }.buttonStyle(TextButtonStyle())
                        .accessibilityLabel(SelectAll.label(viewCount: feed.photos.count, hasMore: feed.canLoadMore, allSelected: allSelected, limit: cap)).accessibilityIdentifier("selectAll")
                }
            }
        }
        .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.m).frame(minHeight: 56).vmkOneLineCap()
    }

    private func selectAllTapped(_ feed: PhotoFeed) {
        Haptics.play(.selection)
        Task {
            if SelectAll.allSelected(view: feed.photos.map(\.id), selected: selection.ordered) { selection.set(SelectAll.clear(view: feed.photos.map(\.id), selected: selection.ordered)); return }
            let cap = cap
            await feed.loadAll(upTo: cap)
            let r = SelectAll.apply(view: feed.photos.map(\.id), selected: selection.ordered, room: cap - selection.count)
            selection.set(r.selected)
            if r.limited || (feed.canLoadMore && selection.count >= cap) { showToast(SelectAll.limitNote) }
        }
    }

    private func commit() {
        let all = feeds.values.flatMap(\.photos)
        let lookup = Dictionary(all.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        onAdd(selection.ordered.compactMap { lookup[$0] })
        Haptics.play(.selection)
        dismiss()
    }

    private func showToast(_ text: String) {
        Haptics.play(.warning)
        withAnimation(reduceMotion ? nil : .snappy) { toast = text }
        UIAccessibility.post(notification: .announcement, argument: text)
        Task { try? await Task.sleep(for: .seconds(4)); withAnimation { if toast == text { toast = nil } } }
    }
}

/// The library inside the picker: search, collection chips and the same grid, read-only (it chooses; the Media tab manages).
private struct LibraryChooser: View {
    let media: MediaModel
    @Bindable var selection: PhotoSelection
    @Binding var collectionID: String?
    @Binding var feeds: [String: PhotoFeed]
    let onLimit: () -> Void
    @Binding var addingToLibrary: [PhotosPickerItem]

    private var key: String { collectionID ?? "all" }
    private var feed: PhotoFeed {
        if let f = feeds[key] { return f }
        return PhotoFeed(kind: collectionID.map { .collection($0) } ?? .timeline, media: media)
    }

    var body: some View {
        let feed = self.feed
        ScrollView {
            VStack(spacing: Theme.Space.m) {
                if collectionID == nil { SearchBar(feed: feed) }
                chips(feed)
                ChipsRow(feed: feed)
                content(feed)
            }
            .padding(.top, 4)
        }
        .scrollDismissesKeyboard(.interactively)
        .task(id: key) {
            if feeds[key] == nil { feeds[key] = feed }
            await feed.refreshIfNeeded()
        }
        .task(id: media.version) { await feed.refreshIfNeeded() }
        .onAppear { media.setWatching("picker", true) }
        .onDisappear { media.setWatching("picker", false) }
    }

    @ViewBuilder private func chips(_ feed: PhotoFeed) -> some View {
        if !feed.isSearching, !media.shownCollections.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: Theme.Space.s) {
                    chip(tr("add.all_photos"), selected: collectionID == nil) { collectionID = nil }
                    ForEach(media.shownCollections) { c in chip(c.name, selected: collectionID == c.id) { collectionID = c.id } }
                }.padding(.horizontal, Theme.gutter)
            }
        }
    }

    private func chip(_ title: String, selected: Bool, _ action: @escaping () -> Void) -> some View {
        ChoiceChip(title: title, selected: selected, action: action)
    }

    @ViewBuilder private func content(_ feed: PhotoFeed) -> some View {
        if feed.offline && feed.photos.isEmpty {
            MediaMessage(symbol: "icloud.slash", title: tr("add.youre_offline"), text: tr("add.your_library_is_not_available"), button: nil) {}
        } else {
            switch feed.state {
            case .loading: SkeletonGrid()
            case .failed(let m): MediaMessage(symbol: "wifi.exclamationmark", title: tr("add.couldnt_load_your_photos"), text: m, button: tr("common.try_again")) { Task { await feed.reload() } }
            case .loaded:
                if feed.photos.isEmpty {
                    if feed.isSearching { MediaMessage(symbol: "magnifyingglass", title: tr("add.nothing_matches", feed.text), text: tr("add.try_fewer_words_like_beach"), button: nil) {} }
                    else if media.summary?.readOnly == true { MediaMessage(symbol: "lock", title: tr("add.your_library_is_read_only"), text: tr("add.free_up_storage_in_the"), button: nil) {} }
                    else {
                        VStack(spacing: Theme.Space.l) {
                            Image(systemName: "photo.stack").font(.vmk(44)).foregroundStyle(Theme.gradient).accessibilityHidden(true)
                            Text(tr("add.your_private_library_is_empty")).textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center)
                            PhotosPicker(selection: $addingToLibrary, maxSelectionCount: nil, matching: .images) { Label(tr("media.add_photos"), systemImage: "photo.badge.plus") }
                                .buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("emptyAddToLibrary")
                        }.padding(Theme.Space.xxl).frame(maxWidth: .infinity)
                    }
                } else {
                    PhotoGrid(feed: feed, media: media, selection: selection, onOpen: { if !selection.toggle($0.id) { onLimit() } }, onLimit: onLimit)
                }
            }
        }
    }
}
