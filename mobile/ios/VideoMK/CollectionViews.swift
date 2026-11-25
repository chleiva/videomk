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
                Text("Collections").font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("See all") { media.showCollectionsList = true }.font(.system(size: 14.5, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("seeAllCollections")
            }.padding(.horizontal, 16)
        }
        ScrollView(.horizontal, showsIndicators: false) {
            LazyHStack(spacing: 10) {
                Button(action: onNew) {
                    VStack(spacing: 6) {
                        RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Theme.surface).frame(width: 104, height: 104)
                            .overlay { Image(systemName: "plus").font(.title2).foregroundStyle(Theme.primary) }
                        Text("New").font(.caption).foregroundStyle(Theme.textSecondary)
                    }
                }
                .accessibilityLabel("New collection").accessibilityIdentifier("newCollection")
                ForEach(media.collections) { c in
                    NavigationLink(value: c) { CollectionCard(media: media, collection: c) }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button { renameText = c.name; renaming = c } label: { Label("Rename", systemImage: "pencil") }
                            Button(role: .destructive) { deleting = c } label: { Label("Delete collection", systemImage: "trash") }
                        }
                        .accessibilityLabel("\(c.name), \(c.count) \(c.count == 1 ? "photo" : "photos")\(c.auto ? ", automatic collection" : "")")
                        .accessibilityHint("Opens the collection. Actions: rename, delete.")
                        .accessibilityAction(named: "Rename") { renameText = c.name; renaming = c }
                        .accessibilityAction(named: "Delete collection") { deleting = c }
                }
            }
            .padding(.horizontal, 16).padding(.bottom, 6)
        }
        .frame(minHeight: 148)
        }
        .alert("Rename collection", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("Name", text: $renameText)
            Button("Save") { if let c = renaming { let t = renameText; Task { await media.rename(c, to: t) } } }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Delete \"\(deleting?.name ?? "")\"?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button("Delete collection", role: .destructive) { if let c = deleting { Task { await media.deleteCollection(c) } } }
        } message: { Text("The photos stay in your library.") }
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
                Text(collection.name).font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
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
            case .failed(let m): MediaMessage(symbol: "wifi.exclamationmark", title: "Couldn't load this collection", text: m, button: "Try again") { Task { await feed.reload() } }
            case .loaded:
                if feed.photos.isEmpty { MediaMessage(symbol: "photo.on.rectangle", title: "Nothing here yet", text: "Select photos in your library and choose Add to collection.", button: nil) {} }
                else { PhotoGrid(feed: feed, media: media, selection: selection) { photo in viewing = ViewerContext(photos: feed.photos, index: feed.photos.firstIndex(of: photo) ?? 0) } }
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("\(current.emoji.map { $0 + " " } ?? "")\(current.name)")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if !feed.photos.isEmpty { Button(selection.active ? "Done" : "Select") { if selection.active { selection.clear() } else { selection.active = true } } }
                Menu {
                    Button { name = current.name; renaming = true } label: { Label("Rename", systemImage: "pencil") }
                    Button(role: .destructive) { confirmDelete = true } label: { Label("Delete collection", systemImage: "trash") }
                } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel("Collection actions")
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if selection.active {
                VStack(spacing: 0) {
                    HStack {
                        Text(selection.count == 0 ? "Select photos" : "\(selection.count) selected").font(.subheadline.weight(.semibold)).foregroundStyle(Theme.text)
                        Spacer()
                        if !feed.photos.isEmpty {
                            Button(SelectAll.label(viewCount: feed.photos.count, hasMore: feed.canLoadMore, allSelected: SelectAll.allSelected(view: feed.photos.map(\.id), selected: selection.ordered))) {
                                UISelectionFeedbackGenerator().selectionChanged()
                                Task { await SelectionActions.toggleAll(feed: feed, selection: selection, limit: PhotoLimits.maxPhotos) }
                            }.font(.system(size: 15, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("selectAll")
                        }
                    }.padding(.horizontal, 16).padding(.top, 6)
                HStack {
                    Button { model.composerLibrary = Array(feed.photos.filter { selection.contains($0.id) }.prefix(100)); model.selectedTab = 0; model.createRequested = true; selection.clear() } label: { Label("Make a video", systemImage: "sparkles.tv") }
                    Spacer()
                    Button(role: .destructive) { let ids = selection.ids; Task { if await media.edit(current, remove: Array(ids)) { feed.remove(ids); selection.clear() } } } label: { Label("Remove from collection", systemImage: "minus.circle") }
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
        .alert("Rename collection", isPresented: $renaming) {
            TextField("Name", text: $name)
            Button("Save") { let n = name; Task { await media.rename(current, to: n) } }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Delete \"\(current.name)\"?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete collection", role: .destructive) { Task { await media.deleteCollection(current); dismiss() } }
        } message: { Text("The photos stay in your library.") }
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
                    Button { creating = true } label: { Label("New collection", systemImage: "plus.circle.fill") }
                }
                Section {
                    ForEach(media.collections) { c in
                        Button { add(to: c) } label: {
                            HStack { Text("\(c.emoji ?? "") \(c.name)").foregroundStyle(Theme.text); Spacer(); Text("\(c.count)").foregroundStyle(Theme.textSecondary) }
                        }
                        .accessibilityLabel("Add to \(c.name)")
                    }
                }
            }
            .disabled(working)
            .navigationTitle("Add to collection").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .alert("New collection", isPresented: $creating) {
                TextField("Name", text: $name)
                Button("Create and add") { let n = name; name = ""; Task { working = true; if let c = await media.createCollection(name: n) { await finish(c) }; working = false } }
                Button("Cancel", role: .cancel) { name = "" }
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
                Text("Newest first. ").foregroundStyle(Theme.textSecondary) + Text("Auto").foregroundStyle(Theme.primary).fontWeight(.semibold) + Text(" collections are made for you.").foregroundStyle(Theme.textSecondary)
                ForEach(media.collections) { c in row(c) }
            }
            .font(.system(size: 14.5)).padding(.horizontal, 16).padding(.bottom, 24)
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Collections").navigationBarTitleDisplayMode(.large)
        .navigationDestination(for: LibraryCollection.self) { CollectionDetailView(media: media, collection: $0) }
        .alert("Rename collection", isPresented: Binding(get: { renaming != nil }, set: { if !$0 { renaming = nil } })) {
            TextField("Name", text: $renameText)
            Button("Save") { if let c = renaming { let t = renameText; Task { await media.rename(c, to: t) } } }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Delete “\(deleting?.name ?? "")”?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button("Delete", role: .destructive) { if let c = deleting { withAnimation(.easeOut(duration: 0.2)) { Task { await media.deleteCollection(c) } } } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("The collection is removed. Its \(deleting?.count ?? 0) photos stay in My media.\(media.organizePref == .always && deleting?.auto == true ? " New uploads from that month may create it again." : "")")
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
                            Text("\(c.count.formatted()) \(c.count == 1 ? "photo" : "photos")").font(.system(size: 14)).foregroundStyle(Theme.textSecondary)
                        }
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }.buttonStyle(.plain)
            Menu {
                Button { renameText = c.name; renaming = c } label: { Label("Rename", systemImage: "pencil") }
                Button(role: .destructive) { deleting = c } label: { Label("Delete collection", systemImage: "xmark") }
                Section { Button("Photos stay in My media. Only the collection is removed.") {}.disabled(true) }
            } label: { Image(systemName: "ellipsis").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44) }
                .accessibilityLabel("Actions for \(c.name)")
        }
        .frame(minHeight: 80)
        .accessibilityElement(children: .contain)
        .accessibilityAction(named: "Rename") { renameText = c.name; renaming = c }
        .accessibilityAction(named: "Delete collection") { deleting = c }
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
