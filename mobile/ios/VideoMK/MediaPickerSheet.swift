import SwiftUI
import VideoMKCore

/// "My media" from the composer: the same grid, search and selection, up to the room left in the video (100 in total with phone photos).
struct MediaPickerSheet: View {
    let media: MediaModel
    let prompt: String
    let room: Int
    let initial: [LibraryPhoto]
    let onDone: ([LibraryPhoto]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var feed: PhotoFeed
    @State private var selection = PhotoSelection()
    @State private var preselecting = false
    private let promptLooksLikePhotos: Bool

    init(media: MediaModel, prompt: String, room: Int, initial: [LibraryPhoto], onDone: @escaping ([LibraryPhoto]) -> Void) {
        self.media = media; self.prompt = prompt; self.room = room; self.initial = initial; self.onDone = onDone
        _feed = State(initialValue: PhotoFeed(kind: .timeline, media: media))
        promptLooksLikePhotos = PromptPhotoIntent.looksLikePhotoQuery(prompt)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 12) {
                    SearchBar(feed: feed)
                    if promptLooksLikePhotos {
                        Button { fromPrompt() } label: {
                            Label(tr("picker.photos_from_your_prompt"), systemImage: "wand.and.stars").font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity, minHeight: 40)
                        }
                        .buttonStyle(.bordered).padding(.horizontal, 16).accessibilityIdentifier("photosFromPrompt")
                        .accessibilityHint(tr("picker.searches_your_library_with_what"))
                    }
                    ChipsRow(feed: feed)
                    switch feed.state {
                    case .loading: SkeletonGrid()
                    case .failed(let m): MediaMessage(symbol: "wifi.exclamationmark", title: tr("add.couldnt_load_your_photos"), text: m, button: tr("common.try_again")) { Task { await feed.reload() } }
                    case .loaded:
                        if feed.photos.isEmpty {
                            MediaMessage(symbol: "photo.on.rectangle", title: feed.isSearching ? tr("media.no_photos_match") : tr("picker.your_library_is_empty"), text: feed.isSearching ? tr("picker.try_fewer_words_or_remove") : tr("picker.add_photos_in_the_media"), button: nil) {}
                        } else { PhotoGrid(feed: feed, media: media, selection: selection) { selection.toggle($0.id) } }
                    }
                }
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle(tr("add.my_media")).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tr("common.cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { done() }.fontWeight(.semibold).accessibilityIdentifier("pickerDone") }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                HStack {
                    Text(tr("picker.selected_of", selection.count, room)).font(.subheadline.weight(.semibold).monospacedDigit()).foregroundStyle(Theme.text)
                    Spacer()
                    if feed.isSearching, !feed.photos.isEmpty { Button(feed.canLoadMore ? tr("select_all.up_to", room) : tr("select_all.count", min(feed.photos.count, room))) { Task { await feed.loadAll(upTo: room); selection.select(all: feed.photos.map(\.id)) } }.font(.footnote.weight(.semibold)) }
                    if selection.count > 0 { Button(tr("picker.clear")) { selection.set([]) }.font(.footnote) }
                }
                .padding(.horizontal, 16).padding(.vertical, 12).background(.bar)
                .accessibilityElement(children: .combine)
            }
        }
        .task {
            selection.active = true; selection.limit = room
            selection.set(initial.map(\.id))
            await media.store.remember(initial)
            await feed.refreshIfNeeded()
            if promptLooksLikePhotos && initial.isEmpty { fromPrompt() }      // opens already searched, preselected and with the chips visible
        }
        .task(id: media.version) { await feed.refreshIfNeeded() }      // photos uploaded a moment ago show up here too
        .onAppear { media.setWatching("picker", true); Task { await media.refreshNow() } }
        .onDisappear { media.setWatching("picker", false) }
        .onChange(of: feed.photos) { _, photos in
            guard preselecting, !feed.searching, !photos.isEmpty else { return }
            preselecting = false
            Task { await feed.loadAll(upTo: room); selection.set(feed.photos.map(\.id)) }
        }
        .presentationDetents([.large])
    }

    private func fromPrompt() { preselecting = true; feed.text = prompt }

    private func done() {
        var lookup = Dictionary(initial.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        for p in feed.photos { lookup[p.id] = p }
        onDone(selection.ordered.compactMap { lookup[$0] })
        dismiss()
    }
}
