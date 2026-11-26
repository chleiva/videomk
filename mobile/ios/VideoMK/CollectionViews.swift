import SwiftUI
import VideoMKCore

struct CollectionsStrip: View {
    let media: MediaModel
    let onNew: () -> Void
    @State private var renaming: LibraryCollection?
    @State private var renameText = ""
    @State private var deleting: LibraryCollection?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
        if !media.collections.isEmpty {
            HStack {
                Text(tr("viewer.collections")).font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader)
                Spacer()
                Button(tr("collections.see_all")) { media.showCollectionsList = true }.font(.system(size: 14.5, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("seeAllCollections")
            }.padding(.horizontal, 16)
        }
        ScrollView(.horizontal, showsIndicators: false) {
            LazyHStack(spacing: 10) {
                Button(action: onNew) {
                    VStack(spacing: 6) {
                        RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Theme.surface).frame(width: 104, height: 104)
                            .overlay { Image(systemName: "plus").font(.title2).foregroundStyle(Theme.primary) }
                        Text(tr("collections.new")).font(.caption).foregroundStyle(Theme.textSecondary)
                    }
                }
                .accessibilityLabel(tr("media.new_collection")).accessibilityIdentifier("newCollection")
                ForEach(media.collections) { c in
                    NavigationLink(value: c) { CollectionCard(media: media, collection: c) }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button { renameText = c.name; renaming = c } label: { Label(tr("collections.rename"), systemImage: "pencil") }
                            Button(role: .destructive) { deleting = c } label: { Label(tr("collections.delete_collection"), systemImage: "trash") }
                        }
                        .accessibilityLabel(tr(c.auto ? "collections.row_a11y_auto" : "collections.row_a11y", c.name, tr("photos.count", c.count)))
                        .accessibilityHint(tr("collections.opens_the_collection_actions_rename"))
                        .accessibilityAction(named: tr("collections.rename")) { renameText = c.name; renaming = c }
                        .accessibilityAction(named: tr("collections.delete_collection")) { deleting = c }
                }
            }
            .padding(.horizontal, 16).padding(.bottom, 6)
        }
        .frame(minHeight: 148)
        }
        .alert(tr("collections.rename_collection"), isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField(tr("media.name"), text: $renameText)
            Button(tr("collections.save")) { if let c = renaming { let t = renameText; Task { await media.rename(c, to: t) } } }
            Button(tr("common.cancel"), role: .cancel) {}
        }
        .confirmationDialog(tr("collections.delete_title", deleting?.name ?? ""), isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button(tr("collections.delete_collection"), role: .destructive) { if let c = deleting { Task { await media.deleteCollection(c) } } }
        } message: { Text(tr("collections.the_photos_stay_in_your")) }
    }
}

struct CollectionCard: View {
    let media: MediaModel
    let collection: LibraryCollection
    @State private var cover: UIImage?
    var body: some View {
        VStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Theme.surfaceRaised).frame(width: 104, height: 104)
                .overlay { if let cover { Image(uiImage: cover).resizable().scaledToFill() } else { Text(collection.emoji ?? "").font(.largeTitle) } }
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .overlay(alignment: .topLeading) { if collection.auto { AutoBadge().padding(6) } }
            VStack(spacing: 0) {
                Text(collection.name).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                Text("\(collection.count)").font(.system(size: 12)).foregroundStyle(Theme.textSecondary)
            }.frame(width: 104)
        }
        .task(id: collection.coverID) {
            guard let id = collection.coverID else { cover = nil; return }
            // The collection carries its cover's thumbnail link: no extra request per cover (cached by the cover's photo id).
            cover = await media.thumbnail(for: LibraryPhoto(id: id, thumbURL: collection.coverThumbURL))
        }
    }
}

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
    @State private var confirmDelete = false

    init(media: MediaModel, collection: LibraryCollection) {
        self.media = media; self.collection = collection
        _feed = State(initialValue: PhotoFeed(kind: .collection(collection.id), media: media))
    }

    private var current: LibraryCollection { media.collections.first { $0.id == collection.id } ?? collection }

    var body: some View {
        ScrollView {
            switch feed.state {
            case .loading: SkeletonGrid()
            case .failed(let m): MediaMessage(symbol: "wifi.exclamationmark", title: tr("collections.couldnt_load_this_collection"), text: m, button: tr("common.try_again")) { Task { await feed.reload() } }
            case .loaded:
                if feed.photos.isEmpty { MediaMessage(symbol: "photo.on.rectangle", title: tr("collections.nothing_here_yet"), text: tr("collections.select_photos_in_your_library"), button: nil) {} }
                else { PhotoGrid(feed: feed, media: media, selection: selection) { photo in viewing = ViewerContext(photos: feed.photos, index: feed.photos.firstIndex(of: photo) ?? 0) } }
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("\(current.emoji.map { $0 + " " } ?? "")\(current.name)")   // i18n-ok
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if !feed.photos.isEmpty { Button(selection.active ? tr("common.done") : tr("media.select")) { if selection.active { selection.clear() } else { selection.active = true } } }
                Menu {
                    Button { name = current.name; renaming = true } label: { Label(tr("collections.rename"), systemImage: "pencil") }
                    Button(role: .destructive) { confirmDelete = true } label: { Label(tr("collections.delete_collection"), systemImage: "trash") }
                } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel(tr("collections.collection_actions"))
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if selection.active {
                VStack(spacing: 0) {
                    HStack {
                        Text(selection.count == 0 ? tr("media.select_photos") : tr("attach.selected", selection.count)).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.text)
                        Spacer()
                        if !feed.photos.isEmpty {
                            Button(SelectAll.label(viewCount: feed.photos.count, hasMore: feed.canLoadMore, allSelected: SelectAll.allSelected(view: feed.photos.map(\.id), selected: selection.ordered))) {
                                UISelectionFeedbackGenerator().selectionChanged()
                                Task { await SelectionActions.toggleAll(feed: feed, selection: selection, limit: PhotoLimits.maxPhotos) }
                            }.font(.system(size: 15, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("selectAll")
                        }
                    }.padding(.horizontal, 16).padding(.top, 6)
                HStack {
                    Button { model.composerLibrary = Array(feed.photos.filter { selection.contains($0.id) }.prefix(100)); model.selectedTab = 0; model.createRequested = true; selection.clear() } label: { Label(tr("collections.make_a_video"), systemImage: "sparkles.tv") }
                    Spacer()
                    Button(role: .destructive) { let ids = selection.ids; Task { if await media.edit(current, remove: Array(ids)) { feed.remove(ids); selection.clear() } } } label: { Label(tr("collections.remove_from_collection"), systemImage: "minus.circle") }
                }
                .disabled(selection.count == 0).padding(.horizontal, 16).padding(.vertical, 12)
                }
                .background(.bar)
            }
        }
        .task(id: media.version) { await feed.refreshIfNeeded() }
        .refreshable { await feed.reload() }
        .fullScreenCover(item: $viewing) { ctx in
            PhotoViewer(media: media, photos: ctx.photos, start: ctx.index, onDeleted: { feed.remove([$0]) }, onMakeVideo: { p in viewing = nil; model.composerLibrary = [p]; model.selectedTab = 0; model.createRequested = true })
        }
        .alert(tr("collections.rename_collection"), isPresented: $renaming) {
            TextField(tr("media.name"), text: $name)
            Button(tr("collections.save")) { let n = name; Task { await media.rename(current, to: n) } }
            Button(tr("common.cancel"), role: .cancel) {}
        }
        .confirmationDialog(tr("collections.delete_title", current.name), isPresented: $confirmDelete, titleVisibility: .visible) {
            Button(tr("collections.delete_collection"), role: .destructive) { Task { await media.deleteCollection(current); dismiss() } }
        } message: { Text(tr("collections.the_photos_stay_in_your")) }
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
        NavigationStack {
            List {
                Section {
                    Button { creating = true } label: { Label(tr("media.new_collection"), systemImage: "plus.circle.fill") }
                }
                Section {
                    ForEach(media.collections) { c in
                        Button { add(to: c) } label: {
                            HStack { Text(verbatim: "\(c.emoji ?? "") \(c.name)").foregroundStyle(Theme.text); Spacer(); Text(verbatim: "\(c.count)").foregroundStyle(Theme.textSecondary) }
                        }
                        .accessibilityLabel(tr("collections.add_to_named", c.name))
                    }
                }
            }
            .disabled(working)
            .navigationTitle(tr("collections.add_to_collection")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(tr("common.cancel")) { dismiss() } } }
            .alert(tr("media.new_collection"), isPresented: $creating) {
                TextField(tr("media.name"), text: $name)
                Button(tr("collections.create_and_add")) { let n = name; name = ""; Task { working = true; if let c = await media.createCollection(name: n) { await finish(c) }; working = false } }
                Button(tr("common.cancel"), role: .cancel) { name = "" }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func add(to c: LibraryCollection) { Task { working = true; await finish(c); working = false } }
    private func finish(_ c: LibraryCollection) async { if await media.edit(c, add: photoIDs) { onDone(); dismiss() } }
}

/// "See all": every collection, newest first, with the Auto chip and a menu (docs/UI_DESIGN.md n.3).
struct CollectionsListView: View {
    let media: MediaModel
    @State private var renaming: LibraryCollection?
    @State private var renameText = ""
    @State private var deleting: LibraryCollection?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 4) {
                accentText(tr("collections.auto_note"), accent: Theme.primary, base: Theme.textSecondary)
                ForEach(media.collections) { c in row(c) }
            }
            .font(.system(size: 14.5)).padding(.horizontal, 16).padding(.bottom, 24)
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle(tr("viewer.collections")).navigationBarTitleDisplayMode(.large)
        .navigationDestination(for: LibraryCollection.self) { CollectionDetailView(media: media, collection: $0) }
        .alert(tr("collections.rename_collection"), isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField(tr("media.name"), text: $renameText)
            Button(tr("collections.save")) { if let c = renaming { let t = renameText; Task { await media.rename(c, to: t) } } }
            Button(tr("common.cancel"), role: .cancel) {}
        }
        .confirmationDialog(tr("collections.delete_title", deleting?.name ?? ""), isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button(tr("collections.delete"), role: .destructive) { if let c = deleting { withAnimation(.easeOut(duration: 0.2)) { Task { await media.deleteCollection(c) } } } }
            Button(tr("common.cancel"), role: .cancel) {}
        } message: {
            Text(tr("collections.delete_msg", deleting?.count ?? 0) + (media.organizePref == .always && deleting?.auto == true ? " " + tr("collections.recreate_note") : ""))
        }
    }

    private func row(_ c: LibraryCollection) -> some View {
        HStack(spacing: 14) {
            NavigationLink(value: c) {
                HStack(spacing: 14) {
                    CoverThumb(media: media, collection: c)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(c.name).font(.system(size: 16.5, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(2)
                        HStack(spacing: 8) {
                            if c.auto { AutoChip() }
                            Text(tr("photos.count", c.count)).font(.system(size: 14)).foregroundStyle(Theme.textSecondary)
                        }
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }.buttonStyle(.plain)
            Menu {
                Button { renameText = c.name; renaming = c } label: { Label(tr("collections.rename"), systemImage: "pencil") }
                Button(role: .destructive) { deleting = c } label: { Label(tr("collections.delete_collection"), systemImage: "xmark") }
                Section { Button(tr("collections.photos_stay_in_my_media")) {}.disabled(true) }
            } label: { Image(systemName: "ellipsis").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44) }
                .accessibilityLabel(tr("collections.actions_for", c.name))
        }
        .frame(minHeight: 80)
        .accessibilityElement(children: .contain)
        .accessibilityAction(named: tr("collections.rename")) { renameText = c.name; renaming = c }
        .accessibilityAction(named: tr("collections.delete_collection")) { deleting = c }
    }
}

struct CoverThumb: View {
    let media: MediaModel
    let collection: LibraryCollection
    @State private var image: UIImage?
    var body: some View {
        RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Theme.surfaceRaised).frame(width: 60, height: 60)
            .overlay { if let image { Image(uiImage: image).resizable().scaledToFill() } else { Text(collection.emoji ?? "").font(.title2) } }
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .task(id: collection.coverID) {
                guard let id = collection.coverID else { return }
                image = await media.thumbnail(for: LibraryPhoto(id: id, thumbURL: collection.coverThumbURL))
            }
    }
}
