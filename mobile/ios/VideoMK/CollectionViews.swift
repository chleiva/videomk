import SwiftUI
import VideoMKCore

/// Where the Media tab can go: the list of collections (from More), and one collection. Both are pushed pages with the app's own top bar; the
/// floating tab bar steps aside on every pushed page.
enum MediaRoute: Hashable { case collections, collection(LibraryCollection) }

/// One collection: its photos in the same grid, the same Select and "Make a video · N" as the Media tab, and Rename / Delete behind More.
struct CollectionDetailView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let media: MediaModel
    let collection: LibraryCollection
    @State private var feed: PhotoFeed
    @State private var selection = PhotoSelection()
    @State private var viewing: ViewerContext?
    @State private var renaming = false
    @State private var name = ""
    @State private var adding = false

    init(media: MediaModel, collection: LibraryCollection) {
        self.media = media; self.collection = collection
        _feed = State(initialValue: PhotoFeed(kind: .collection(collection.id), media: media))
    }

    private var current: LibraryCollection { media.collections.first { $0.id == collection.id } ?? collection }

    var body: some View {
        VStack(spacing: 0) {
            topBar
            ScrollView {
                switch feed.state {
                case .loading: SkeletonGrid()
                case .failed(let m): MediaMessage(symbol: "wifi.exclamationmark", title: tr("collections.couldnt_load_this_collection"), text: m, button: tr("common.try_again")) { Task { await feed.reload() } }
                case .loaded:
                    if feed.photos.isEmpty {
                        // an empty collection has one obvious next step
                        VStack(spacing: Theme.Space.l) {
                            Image(systemName: "photo.on.rectangle").font(.vmk(40)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                            Text(tr("collections.nothing_here_yet")).textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center)
                            Button { adding = true } label: { Label(tr("media.add_photos"), systemImage: "photo.badge.plus") }.buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("collectionAddPhotos")
                        }
                        .padding(Theme.Space.xxl).frame(maxWidth: .infinity)
                    } else {
                        PhotoGrid(feed: feed, media: media, selection: selection, onOpen: { photo in viewing = ViewerContext(photos: feed.photos, index: feed.photos.firstIndex(of: photo) ?? 0) }, hidden: media.hiddenPhotos)
                    }
                }
            }
            .refreshable { await feed.reload() }
        }
        .background(Theme.background.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .onChange(of: selection.active) { _, on in model.mediaSelecting = on }
        .onChange(of: model.submitted) { _, _ in selection.clear() }
        .onDisappear { model.mediaSelecting = false }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                UndoToastHost()
                if selection.active {
                    SelectionBar(selection: selection, onVideo: { model.startVideo(with: selection.ordered.compactMap { id in feed.photos.first { $0.id == id } }) },
                                 icons: [.init(id: "removeFromCollection", symbol: "minus.circle", label: tr("collections.remove_from_collection"), danger: true) {
                                     let ids = selection.ids; Task { if await media.edit(current, remove: Array(ids)) { feed.remove(ids); selection.clear() } } }])
                }
            }
        }
        .task(id: media.version) { await feed.refreshIfNeeded() }
        .fullScreenCover(item: $viewing) { ctx in
            PhotoViewer(media: media, photos: ctx.photos, start: ctx.index, onDeleted: { feed.remove([$0]) }, onMakeVideo: { p in viewing = nil; model.startVideo(with: [p]) })
        }
        .sheet(isPresented: $adding) {
            LibraryPickerSheet(attached: 0) { photos in
                let c = current
                Task { if await media.edit(c, add: photos.map(\.id)) { await feed.reload() } }
            }
        }
        .alert(tr("collections.rename_collection"), isPresented: $renaming) {
            TextField(tr("media.name"), text: $name)
            Button(tr("collections.save")) { let n = name; Task { await media.rename(current, to: n) } }
            Button(tr("common.cancel"), role: .cancel) {}
        }
    }

    /// The same bar as the Media tab: back and the name; while selecting, Cancel, the count and Select all.
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
            TopBar(title: nil, leading: {
                IconButton(symbol: "chevron.left", label: tr("common.back"), identifier: "backButton") { dismiss() }
                Text(verbatim: "\(current.emoji.map { $0 + " " } ?? "")\(current.name)").font(.role(.headline)).foregroundStyle(Theme.text).lineLimit(1).accessibilityAddTraits(.isHeader).accessibilityIdentifier("collectionTitle")
            }, trailing: {
                if !feed.photos.isEmpty { Button(tr("media.select")) { withAnimation(.snappy) { selection.active = true } }.buttonStyle(TextButtonStyle()).accessibilityIdentifier("selectButton") }
                Menu {
                    Button { name = current.name; renaming = true } label: { Label(tr("collections.rename"), systemImage: "pencil") }
                    Button(role: .destructive) { media.deleteCollection(current, undo: model.undo); dismiss() } label: { Label(tr("collections.delete_collection"), systemImage: "trash") }.accessibilityIdentifier("deleteCollection")
                } label: { IconButtonFace(symbol: "ellipsis") }
                    .accessibilityLabel(tr("collections.collection_actions")).accessibilityIdentifier("collectionMore")
            })
        }
    }
}

/// Pick a collection (or make one) for the given photos. A photo can be in several collections.
struct AddToCollectionSheet: View {
    let media: MediaModel
    let photoIDs: [String]
    var onDone: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var creating = false
    @State private var name = ""
    @State private var working = false

    var body: some View {
        FittedSheet {
            VStack(alignment: .leading, spacing: Theme.Space.m) {
                SheetHeader(title: tr("collections.add_to_collection"), closeID: "addToCollectionClose") { dismiss() }
                Button { creating = true } label: { Label(tr("media.new_collection"), systemImage: "folder.badge.plus") }.buttonStyle(TonalButtonStyle()).accessibilityIdentifier("newCollectionInSheet")
                VStack(spacing: 0) {
                    ForEach(media.shownCollections) { c in
                        Button { add(to: c) } label: {
                            HStack(spacing: Theme.Space.m) {
                                CoverThumb(media: media, collection: c, side: 44)
                                Text(c.name).font(.role(.body)).foregroundStyle(Theme.text).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: Theme.Space.s)
                                Text(verbatim: "\(c.count)").font(.role(.subhead).monospacedDigit()).foregroundStyle(Theme.textSecondary)
                            }
                            .frame(minHeight: 60).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(tr("collections.add_to_named", c.name))
                    }
                }
            }
            .disabled(working)
        }
        .alert(tr("media.new_collection"), isPresented: $creating) {
            TextField(tr("media.name"), text: $name)
            Button(tr("collections.create_and_add")) { let n = name; name = ""; Task { working = true; if let c = await media.createCollection(name: n) { await finish(c) }; working = false } }
            Button(tr("common.cancel"), role: .cancel) { name = "" }
        }
    }

    private func add(to c: LibraryCollection) { Task { working = true; await finish(c); working = false } }
    private func finish(_ c: LibraryCollection) async { if await media.edit(c, add: photoIDs) { onDone(); dismiss() } }
}

/// Collections (from More on the Media tab): every collection, newest first, with the Auto chip and a menu.
struct CollectionsListView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize
    let media: MediaModel
    let onNew: () -> Void
    @State private var renaming: LibraryCollection?
    @State private var renameText = ""

    var body: some View {
        VStack(spacing: 0) {
            TopBar(title: nil, leading: {
                IconButton(symbol: "chevron.left", label: tr("common.back"), identifier: "backButton") { dismiss() }
                Text(tr("viewer.collections")).font(.role(.headline)).foregroundStyle(Theme.text).lineLimit(1).accessibilityAddTraits(.isHeader)
            }, trailing: {
                IconButton(symbol: "folder.badge.plus", label: tr("media.new_collection"), identifier: "newCollection", action: onNew)
            })
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    ForEach(media.shownCollections) { c in row(c) }
                    if media.shownCollections.isEmpty {
                        Text(tr("collections.nothing_here_yet")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity).padding(.top, Theme.Space.xxxl)
                    }
                }
                .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.xl)
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .safeAreaInset(edge: .bottom, spacing: 0) { UndoToastHost() }
        .alert(tr("collections.rename_collection"), isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField(tr("media.name"), text: $renameText)
            Button(tr("collections.save")) { if let c = renaming { let t = renameText; Task { await media.rename(c, to: t) } } }
            Button(tr("common.cancel"), role: .cancel) {}
        }
    }

    private func row(_ c: LibraryCollection) -> some View {
        HStack(spacing: Theme.Space.m) {
            NavigationLink(value: MediaRoute.collection(c)) {
                HStack(spacing: Theme.Space.m) {
                    CoverThumb(media: media, collection: c, side: typeSize.isAccessibilitySize ? 48 : 60)
                    VStack(alignment: .leading, spacing: Theme.Space.xs) {
                        Text(c.name).font(.role(.headline)).foregroundStyle(Theme.text).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                        // at the largest sizes the count sits under the chip instead of beside it: names and counts are never squeezed or hyphenated
                        let meta = Group { if c.auto { AutoChip() }; Text(tr("photos.count", c.count)).font(.role(.footnote)).foregroundStyle(Theme.textSecondary) }
                        if typeSize.isAccessibilitySize { VStack(alignment: .leading, spacing: 2) { meta } } else { HStack(spacing: Theme.Space.s) { meta } }
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }.buttonStyle(.plain).accessibilityIdentifier("collectionRow")
            Menu {
                Button { renameText = c.name; renaming = c } label: { Label(tr("collections.rename"), systemImage: "pencil") }
                Button(role: .destructive) { withAnimation(Theme.Motion.spring) { media.deleteCollection(c, undo: model.undo) } } label: { Label(tr("collections.delete_collection"), systemImage: "trash") }
            } label: { IconButtonFace(symbol: "ellipsis") }
                .accessibilityLabel(tr("collections.actions_for", c.name)).accessibilityIdentifier("collectionRowMore")
        }
        .frame(minHeight: 80)
        .accessibilityElement(children: .contain)
        .accessibilityAction(named: tr("collections.rename")) { renameText = c.name; renaming = c }
        .accessibilityAction(named: tr("collections.delete_collection")) { media.deleteCollection(c, undo: model.undo) }
    }
}

struct CoverThumb: View {
    let media: MediaModel
    let collection: LibraryCollection
    var side: CGFloat = 60
    @State private var image: UIImage?
    var body: some View {
        RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous).fill(Theme.surfaceRaised).frame(width: side, height: side)
            .overlay { if let image { Image(uiImage: image).resizable().scaledToFill() } else { Text(collection.emoji ?? "").font(.role(.title)) } }
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
            .accessibilityHidden(true)
            .task(id: collection.coverID) {
                guard let id = collection.coverID else { return }
                // The collection carries its cover's thumbnail link: no extra request per cover (cached by the cover's photo id).
                image = await media.thumbnail(for: LibraryPhoto(id: id, thumbURL: collection.coverThumbURL))
            }
    }
}
