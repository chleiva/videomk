import PhotosUI
import SwiftUI
import VideoMKCore

/// ONE sheet for adding photos to the video (docs/UI_DESIGN.md f): "This phone" | "My media" over the same selection bar.
///
/// How "This phone" behaves: a button opens the system photo picker (`PhotosPicker`, ordered selection). It runs in a separate process, so videomk
/// never asks for photo-library permission and only receives the photos you tap. The remaining room is passed as its selection limit, so the system
/// dims everything else at 100 in total. The picker closes on confirm and this sheet counts the photos with those from My media: one selection.
/// (The inline style, `.photosPickerStyle(.inline)`, was tried: on iOS 26 it draws its own full-height chrome with Cancel and Done buttons and pushed
/// this sheet under the status bar, so it is not used.)
struct AddPhotosSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let attached: Int
    let minutes: Double
    let onAdd: ([PhotosPickerItem], [LibraryPhoto]) -> Void

    enum Source: Int { case phone, library }
    @State private var source: Source
    @State private var phoneItems: [PhotosPickerItem] = []
    @State private var librarySelection = PhotoSelection()
    @State private var feeds: [String: PhotoFeed] = [:]
    @State private var collectionID: String?
    @State private var toast: String?
    @State private var addingToLibrary: [PhotosPickerItem] = []

    init(attached: Int, minutes: Double, startOnLibrary: Bool, onAdd: @escaping ([PhotosPickerItem], [LibraryPhoto]) -> Void) {
        self.attached = attached; self.minutes = minutes; self.onAdd = onAdd
        _source = State(initialValue: startOnLibrary ? .library : .phone)
    }

    private var phoneIDs: [String] { phoneItems.map { $0.itemIdentifier ?? "\($0.hashValue)" } }
    private var selection: AttachSelection {
        AttachSelection(attached: attached, phone: phoneIDs, library: librarySelection.ordered)
    }
    private var media: MediaModel? { model.media }
    private var currentFeed: PhotoFeed? { feeds[collectionID ?? "all"] }

    /// The control next to the count: select everything in view (All photos, a collection, search results), loading more pages up to the limit.
    private var selectAllLabel: String? {
        guard source == .library, let feed = currentFeed, !feed.photos.isEmpty else { return nil }
        return SelectAll.label(viewCount: feed.photos.count, hasMore: feed.canLoadMore, allSelected: SelectAll.allSelected(view: feed.photos.map(\.id), selected: librarySelection.ordered), limit: selection.libraryCap)
    }

    private func selectAllTapped() {
        guard let feed = currentFeed else { return }
        UISelectionFeedbackGenerator().selectionChanged()
        Task {
            if SelectAll.allSelected(view: feed.photos.map(\.id), selected: librarySelection.ordered) { librarySelection.set(SelectAll.clear(view: feed.photos.map(\.id), selected: librarySelection.ordered)); return }
            let cap = selection.libraryCap
            await feed.loadAll(upTo: cap)
            let r = SelectAll.apply(view: feed.photos.map(\.id), selected: librarySelection.ordered, room: cap - librarySelection.count)
            librarySelection.set(r.selected)
            if r.limited || (feed.canLoadMore && librarySelection.count >= cap) { showToast(SelectAll.limitNote) }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Picker("Source", selection: $source.animation(reduceMotion ? nil : .easeInOut(duration: 0.2))) {
                Text("This phone").tag(Source.phone)
                Text("My media").tag(Source.library)
            }
            .pickerStyle(.segmented).padding(.horizontal, 20).padding(.bottom, 10)
            .accessibilityIdentifier("sourcePicker")
            Group {
                switch source {
                case .phone: phoneTab
                case .library: libraryTab
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            selectionBar
        }
        .presentationBackground(Theme.surface)
        .overlay(alignment: .bottom) { toastView }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .onChange(of: phoneItems.count) { _, _ in syncLimits() }
        .onChange(of: librarySelection.count) { _, _ in syncLimits() }
        .onAppear { syncLimits() }
        .onChange(of: addingToLibrary) { _, items in
            guard !items.isEmpty, let media else { return }
            let picked = items; addingToLibrary = []
            Task { await media.add(picked) }
        }
    }

    private func syncLimits() { librarySelection.limit = selection.libraryCap; librarySelection.active = true }

    // MARK: header and bar

    private var header: some View {
        HStack {
            Text("Add photos").font(.system(size: 19, weight: .bold)).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader)
            Spacer()
            Button("Cancel") { dismiss() }.font(.system(size: 17)).frame(minWidth: 44, minHeight: 44).accessibilityIdentifier("addCancel")
        }
        .padding(.horizontal, 20).padding(.top, 14)
    }

    private var selectionBar: some View {
        let sel = selection
        return VStack(spacing: 0) {
            Divider()
            Text("Location data is removed from your photos, and the originals are deleted once your video is made.")
                .font(.system(size: 11.5)).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20).padding(.top, 8)
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(sel.selected == 0 ? "Choose photos" : sel.title()).font(.system(size: 15, weight: .bold)).foregroundStyle(Theme.text)
                        if let label = selectAllLabel {
                            Text("·").foregroundStyle(Theme.textSecondary)
                            Button(label) { selectAllTapped() }.font(.system(size: 15, weight: .semibold)).frame(minHeight: 32).accessibilityIdentifier("selectAll")
                        }
                    }
                    Text(sel.subline(minutes: minutes)).font(.system(size: 12.5)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(.updatesFrequently)
                .accessibilityIdentifier("selectionSummary")
                Spacer(minLength: 8)
                Button { commit() } label: {
                    Text(sel.buttonTitle()).font(.system(size: 17, weight: .semibold)).foregroundStyle(sel.selected == 0 ? Theme.textTertiary : .white)
                        .padding(.horizontal, 28).frame(minWidth: 96, minHeight: 48)
                        .background(sel.selected == 0 ? AnyShapeStyle(Theme.surface3) : AnyShapeStyle(Theme.gradient), in: Capsule())
                }
                .buttonStyle(.plain).disabled(sel.selected == 0)
                .accessibilityIdentifier("addSelected")
            }
            .padding(.horizontal, 20).padding(.vertical, 10)
        }
        .background(Theme.surface)
    }

    private func commit() {
        var chosen: [LibraryPhoto] = []
        if source == .library || !librarySelection.ordered.isEmpty {
            let all = feeds.values.flatMap(\.photos)
            let lookup = Dictionary(all.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
            chosen = librarySelection.ordered.compactMap { lookup[$0] }
        }
        onAdd(phoneItems, chosen)
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        dismiss()
    }

    // MARK: tabs

    @ViewBuilder private var phoneTab: some View {
        if selection.phoneCap == 0 && phoneItems.isEmpty {
            MediaMessage(symbol: "photo.stack", title: "100 photos chosen", text: "You have chosen the most a video can use, from My media. Deselect some there to pick from this phone.", button: "Open My media") { source = .library }
        } else {
            VStack(spacing: 14) {
                Image(systemName: "iphone.gen3").font(.system(size: 44)).foregroundStyle(Theme.gradient).accessibilityHidden(true)
                Text(phoneItems.isEmpty ? "Pick from this phone" : "\(ComposerPlan.plural(phoneItems.count, "photo")) chosen from this phone")
                    .font(.system(size: 18, weight: .semibold)).foregroundStyle(Theme.text)
                Text("videomk only sees the photos you pick. Nothing else in your library is read, and no permission is needed.")
                    .font(.system(size: 15)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
                PhotosPicker(selection: $phoneItems, maxSelectionCount: max(1, selection.phoneCap), selectionBehavior: .ordered, matching: .images, photoLibrary: .shared()) {
                    Text(phoneItems.isEmpty ? "Choose photos" : "Change selection").font(.headline).frame(maxWidth: 260, minHeight: 48)
                }
                .buttonStyle(.borderedProminent).tint(Theme.primary)
                .accessibilityIdentifier("phonePicker")
                Text("Choosing here adds to the same selection as My media. The most a video can use is \(PhotoLimits.maxPhotos).")
                    .font(.system(size: 13)).foregroundStyle(Theme.textTertiary).multilineTextAlignment(.center)
            }
            .padding(32).frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder private var libraryTab: some View {
        if let media {
            LibraryChooser(media: media, selection: librarySelection, collectionID: $collectionID, feeds: $feeds, onLimit: { showToast("You can add up to \(PhotoLimits.maxPhotos) photos. Remove one to choose another.") }, addingToLibrary: $addingToLibrary)
        } else {
            MediaMessage(symbol: "photo.on.rectangle", title: "My media isn't available", text: "Sign in again to use your private library.", button: nil) {}
        }
    }

    private func showToast(_ text: String) {
        UINotificationFeedbackGenerator().notificationOccurred(.warning)
        withAnimation(reduceMotion ? nil : .snappy) { toast = text }
        UIAccessibility.post(notification: .announcement, argument: text)
        Task { try? await Task.sleep(for: .seconds(4)); withAnimation { if toast == text { toast = nil } } }
    }

    @ViewBuilder private var toastView: some View {
        if let toast {
            Text(toast).font(.system(size: 14.5)).foregroundStyle(.white).padding(.horizontal, 16).padding(.vertical, 14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(hex: 0x23263F), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .padding(.horizontal, 16).padding(.bottom, 130).transition(.move(edge: .bottom).combined(with: .opacity))
                .accessibilityIdentifier("limitToast")
        }
    }
}

/// The "My media" tab of the sheet: search, collection chips and the same grid, read-only (it chooses; the Media tab manages).
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
            VStack(spacing: 10) {
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
        if !feed.isSearching, !media.collections.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    chip("All photos", selected: collectionID == nil) { collectionID = nil }
                    ForEach(media.collections) { c in chip(c.name, selected: collectionID == c.id) { collectionID = c.id } }
                }.padding(.horizontal, 20)
            }
        }
    }

    private func chip(_ title: String, selected: Bool, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(selected ? Theme.primary : Theme.text).lineLimit(1)
                .padding(.horizontal, 14).frame(height: 34)
                .background(selected ? Theme.primaryContainer : .clear, in: Capsule())
                .overlay(Capsule().stroke(Theme.outline, lineWidth: selected ? 0 : 1))
                .frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }

    @ViewBuilder private func content(_ feed: PhotoFeed) -> some View {
        if feed.offline && feed.photos.isEmpty {
            MediaMessage(symbol: "icloud.slash", title: "You're offline", text: "Your library is not available. This phone stays usable.", button: nil) {}
        } else {
            switch feed.state {
            case .loading: SkeletonGrid()
            case .failed(let m): MediaMessage(symbol: "wifi.exclamationmark", title: "Couldn't load your photos", text: m, button: "Try again") { Task { await feed.reload() } }
            case .loaded:
                if feed.photos.isEmpty {
                    if feed.isSearching { MediaMessage(symbol: "magnifyingglass", title: "Nothing matches '\(feed.text)'", text: "Try fewer words, like 'beach'.", button: nil) {} }
                    else if media.summary?.readOnly == true { MediaMessage(symbol: "lock", title: "Your library is read only", text: "Free up storage in the Media tab to add photos.", button: nil) {} }
                    else {
                        VStack(spacing: 14) {
                            Image(systemName: "icloud.and.arrow.up").font(.system(size: 44)).foregroundStyle(Theme.gradient).accessibilityHidden(true)
                            Text("Your private library is empty").font(.system(size: 18, weight: .semibold)).foregroundStyle(Theme.text)
                            Text("Photos you add here can be reused in any video.").font(.system(size: 15)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
                            PhotosPicker(selection: $addingToLibrary, maxSelectionCount: nil, matching: .images) { Text("Add photos to My media").font(.headline).frame(maxWidth: 260, minHeight: 48) }
                                .buttonStyle(.borderedProminent).accessibilityIdentifier("emptyAddToLibrary")
                        }.padding(32).frame(maxWidth: .infinity)
                    }
                } else {
                    PhotoGrid(feed: feed, media: media, selection: selection, onOpen: { if !selection.toggle($0.id) { onLimit() } }, onLimit: onLimit)
                }
            }
        }
    }
}
