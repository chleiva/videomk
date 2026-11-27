import SwiftUI
import VideoMKCore

/// Full-screen viewer: swipe between photos, pinch or double-tap to zoom. The same controls as the rest of the app, over the picture:
/// one close button, ONE primary ("Make a video", with the play-sparkle), and quiet icons for info, collections, share and delete (with Undo).
struct PhotoViewer: View {
    @Environment(AppModel.self) private var model
    let media: MediaModel
    let photos: [LibraryPhoto]
    @State private var index: Int
    let onDeleted: (String) -> Void
    let onMakeVideo: (LibraryPhoto) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var showInfo = false
    @State private var showCollections = false
    @State private var shareImage: Image?

    init(media: MediaModel, photos: [LibraryPhoto], start: Int, onDeleted: @escaping (String) -> Void, onMakeVideo: @escaping (LibraryPhoto) -> Void) {
        self.media = media; self.photos = photos; _index = State(initialValue: min(max(0, start), max(0, photos.count - 1)))
        self.onDeleted = onDeleted; self.onMakeVideo = onMakeVideo
    }

    /// Without the photos whose delete can still be undone (Undo brings them back into the pages).
    private var shown: [LibraryPhoto] { photos.filter { !media.hiddenPhotos.contains($0.id) } }
    private var current: LibraryPhoto? { let s = shown; return s.isEmpty ? nil : s[min(index, s.count - 1)] }

    var body: some View {
        let shown = self.shown
        ZStack {
            Theme.mediaInk.ignoresSafeArea()
            TabView(selection: $index) {
                ForEach(Array(shown.enumerated()), id: \.element.id) { i, photo in
                    ZoomablePhoto(media: media, photo: photo).tag(i)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never)).ignoresSafeArea()
        }
        .overlay(alignment: .top) {
            HStack {
                IconButton(symbol: "xmark", label: tr("common.close"), style: .onMedia, identifier: "viewerClose") { dismiss() }
                Spacer()
                if shown.count > 1 {
                    Text(tr("viewer.position", min(index, shown.count - 1) + 1, shown.count)).font(.role(.footnote, weight: .medium).monospacedDigit()).foregroundStyle(Theme.onMedia)
                        .padding(.horizontal, Theme.Space.m).frame(minHeight: 32).background(Theme.mediaInk.opacity(0.55), in: Capsule()).accessibilityIdentifier("viewerPosition")
                }
            }
            .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s)
        }
        .overlay(alignment: .bottom) {
            VStack(spacing: Theme.Space.m) {
                UndoToastHost().padding(.horizontal, -Theme.gutter)
                if let p = current {
                    HStack(spacing: Theme.Space.s) {
                        Button { onMakeVideo(p) } label: { HStack(spacing: Theme.Space.s) { PlaySparkle(scale: 0.7); Text(tr("collections.make_a_video")).lineLimit(1).minimumScaleFactor(0.8) } }
                            .buttonStyle(PrimaryButtonStyle()).accessibilityHint(tr("viewer.make_video")).accessibilityIdentifier("viewerMakeVideo")
                        Menu {
                            Button { showInfo = true } label: { Label(tr("viewer.info"), systemImage: "info.circle") }.accessibilityIdentifier("viewerInfo")
                            Button { showCollections = true } label: { Label(tr("collections.add_to_collection"), systemImage: "folder.badge.plus") }
                            if let image = shareImage { ShareLink(item: image, preview: SharePreview(tr("viewer.share"), image: image)) { Label(tr("viewer.share"), systemImage: "square.and.arrow.up") }.accessibilityIdentifier("viewerShare") }
                        } label: { IconButtonFace(symbol: "ellipsis", style: .onMedia, size: Theme.primaryHeight) }
                            .menuOrder(.fixed).accessibilityLabel(tr("media.more")).accessibilityIdentifier("viewerMore")
                        IconButton(symbol: "trash", label: tr("common.delete"), style: .onMedia, size: Theme.primaryHeight, identifier: "viewerDelete") { deleteCurrent() }
                    }
                    .vmkOneLineCap()
                }
            }
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.s)
        }
        .preferredColorScheme(.dark)
        .task(id: current?.id) {
            shareImage = nil
            guard let p = current, let full = await media.fullImage(for: p) else { return }
            shareImage = Image(uiImage: full)
        }
        .onChange(of: index) { _, i in       // swiping pages says where you are (VoiceOver reads nothing by itself)
            let n = self.shown.count
            if n > 1 { UIAccessibility.post(notification: .pageScrolled, argument: tr("viewer.position", min(i, n - 1) + 1, n)) }
        }
        .onChange(of: shown.count) { _, n in if n == 0 { dismiss() } else if index > n - 1 { index = n - 1 } }
        .sheet(isPresented: $showInfo) { if let p = current { PhotoInfoSheet(media: media, photo: p) } }
        .sheet(isPresented: $showCollections) { if let p = current { AddToCollectionSheet(media: media, photoIDs: [p.id]) {} } }
    }

    /// No question: the photo leaves at once and "Deleted · Undo" shows for six seconds.
    private func deleteCurrent() {
        guard let p = current else { return }
        Haptics.play(.selection)
        let gone = onDeleted
        media.deletePhotos([p.id], undo: model.undo) { ids in ids.forEach(gone) }
    }
}

struct ZoomablePhoto: View {
    let media: MediaModel
    let photo: LibraryPhoto
    @State private var image: UIImage?
    @State private var scale: CGFloat = 1
    @State private var base: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var dragBase: CGSize = .zero

    var body: some View {
        GeometryReader { geo in
            Group {
                if let image {
                    Image(uiImage: image).resizable().scaledToFit()
                        .scaleEffect(scale).offset(offset)
                        .frame(width: geo.size.width, height: geo.size.height)
                        .gesture(MagnifyGesture().onChanged { scale = max(1, min(6, base * $0.magnification)) }
                            .onEnded { _ in base = scale; if scale == 1 { offset = .zero; dragBase = .zero } })
                        .simultaneousGesture(DragGesture().onChanged { if scale > 1 { offset = CGSize(width: dragBase.width + $0.translation.width, height: dragBase.height + $0.translation.height) } }
                            .onEnded { _ in dragBase = offset })
                        .onTapGesture(count: 2) { withAnimation(.snappy) { if scale > 1 { scale = 1; base = 1; offset = .zero; dragBase = .zero } else { scale = 2.5; base = 2.5 } } }
                } else { ProgressView().tint(Theme.onMedia).frame(width: geo.size.width, height: geo.size.height) }
            }
        }
        .accessibilityLabel(MediaGrouping.accessibilityLabel(photo))
        .accessibilityAddTraits(.isImage)
        .task(id: photo.id) {
            image = await media.thumbnail(for: photo)          // instant, then the sharp one
            if let full = await media.fullImage(for: photo) { image = full }
        }
    }
}

struct PhotoInfoSheet: View {
    let media: MediaModel
    let photo: LibraryPhoto
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        FittedSheet {
            VStack(alignment: .leading, spacing: 0) {
                SheetHeader(title: tr("viewer.info"), closeID: "photoInfoClose") { dismiss() }.padding(.bottom, Theme.Space.s)
                if let d = MediaGrouping.day(of: photo, calendar: .current) { row(photo.taken == nil ? tr("viewer.added") : tr("viewer.taken"), MediaGrouping.title(y: d.y, m: d.m, d: d.d, calendar: .current)) }
                if let place = photo.place { row(tr("viewer.place"), place) }
                row(tr("viewer.size"), photo.w > 0 ? "\(photo.w) x \(photo.h) px, \(StorageMeter.format(photo.bytes))" : StorageMeter.format(photo.bytes))
                let names = media.shownCollections.filter { photo.collections.contains($0.id) }.map(\.name)
                row(tr("viewer.collections"), names.isEmpty ? tr("viewer.none") : names.joined(separator: ", "))
            }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: Theme.Space.m) { Text(label).foregroundStyle(Theme.textSecondary); Spacer(minLength: Theme.Space.s); Text(value).foregroundStyle(Theme.text).multilineTextAlignment(.trailing) }
            VStack(alignment: .leading, spacing: 2) { Text(label).foregroundStyle(Theme.textSecondary); Text(value).foregroundStyle(Theme.text) }.frame(maxWidth: .infinity, alignment: .leading)
        }
        .font(.role(.body)).frame(minHeight: Theme.minTouch).accessibilityElement(children: .combine)
    }
}
