import SwiftUI
import VideoMKCore

/// Full-screen viewer: swipe between photos, pinch or double-tap to zoom, info, collections, delete, make a video.
struct PhotoViewer: View {
    let media: MediaModel
    @State var photos: [LibraryPhoto]
    @State private var index: Int
    let onDeleted: (String) -> Void
    let onMakeVideo: (LibraryPhoto) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var showInfo = false
    @State private var showCollections = false
    @State private var confirmDelete = false
    @State private var shareImage: Image?

    init(media: MediaModel, photos: [LibraryPhoto], start: Int, onDeleted: @escaping (String) -> Void, onMakeVideo: @escaping (LibraryPhoto) -> Void) {
        self.media = media; _photos = State(initialValue: photos); _index = State(initialValue: min(max(0, start), max(0, photos.count - 1)))
        self.onDeleted = onDeleted; self.onMakeVideo = onMakeVideo
    }

    private var current: LibraryPhoto? { photos.indices.contains(index) ? photos[index] : nil }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            TabView(selection: $index) {
                ForEach(Array(photos.enumerated()), id: \.element.id) { i, photo in
                    ZoomablePhoto(media: media, photo: photo).tag(i)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never)).ignoresSafeArea()
        }
        .overlay(alignment: .top) {
            HStack {
                Button { dismiss() } label: { Image(systemName: "xmark.circle.fill").font(.title).symbolRenderingMode(.palette).foregroundStyle(.white, Color.white.opacity(0.25)) }
                    .accessibilityLabel(tr("common.close"))
                Spacer()
                if photos.count > 1 { Text(tr("viewer.position", index + 1, photos.count)).font(.footnote.monospacedDigit()).foregroundStyle(.white.opacity(0.8)) }
            }.padding()
        }
        .overlay(alignment: .bottom) {
            if let p = current {
                VStack(spacing: 12) {
                    Button { onMakeVideo(p) } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "sparkles").font(.vmk(17, weight: .semibold)).accessibilityHidden(true)
                            Text(tr("collections.make_a_video")).font(.vmk(17, weight: .semibold))
                        }
                        .foregroundStyle(Theme.onPrimary).frame(maxWidth: 320, minHeight: 52).frame(maxWidth: .infinity).background(Theme.gradient, in: Capsule())
                    }
                    .buttonStyle(.plain).accessibilityHint(tr("viewer.make_video")).accessibilityIdentifier("viewerMakeVideo")
                    HStack(spacing: 28) {
                        bar("info.circle", tr("viewer.info")) { showInfo = true }
                        bar("folder.badge.plus", tr("collections.add_to_collection")) { showCollections = true }
                        if let image = shareImage { ShareLink(item: image, preview: SharePreview(tr("viewer.share"), image: image)) { Image(systemName: "square.and.arrow.up").font(.title3).foregroundStyle(.white).frame(minWidth: 44, minHeight: 44) }.accessibilityLabel(tr("viewer.share")).accessibilityIdentifier("viewerShare") }
                        bar("trash", tr("common.delete")) { confirmDelete = true }
                    }
                    .padding(.vertical, 4).padding(.horizontal, 20).background(.ultraThinMaterial, in: Capsule())
                }
                .padding(.horizontal, 20).padding(.bottom, 16)
            }
        }
        .preferredColorScheme(.dark)
        .task(id: current?.id) {
            shareImage = nil
            guard let p = current, let full = await media.fullImage(for: p) else { return }
            shareImage = Image(uiImage: full)
        }
        .sheet(isPresented: $showInfo) { if let p = current { PhotoInfoSheet(media: media, photo: p) } }
        .sheet(isPresented: $showCollections) { if let p = current { AddToCollectionSheet(media: media, photoIDs: [p.id]) {} } }
        .confirmationDialog(tr("viewer.delete_this_photo"), isPresented: $confirmDelete, titleVisibility: .visible) {
            Button(tr("viewer.delete_photo"), role: .destructive) { deleteCurrent() }
        } message: { Text(tr("viewer.it_is_removed_from_your")) }
    }

    private func bar(_ symbol: String, _ label: String, _ run: @escaping () -> Void) -> some View {
        Button(action: run) { Image(systemName: symbol).font(.title3).foregroundStyle(.white).frame(minWidth: 44, minHeight: 44) }.accessibilityLabel(label)
    }

    private func deleteCurrent() {
        guard let p = current else { return }
        Task {
            guard await media.delete([p.id]) else { return }
            onDeleted(p.id)
            photos.removeAll { $0.id == p.id }
            if photos.isEmpty { dismiss() } else { index = min(index, photos.count - 1) }
        }
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
                } else { ProgressView().tint(.white).frame(width: geo.size.width, height: geo.size.height) }
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
        NavigationStack {
            List {
                if let d = MediaGrouping.day(of: photo, calendar: .current) { LabeledContent(photo.taken == nil ? tr("viewer.added") : tr("viewer.taken"), value: MediaGrouping.title(y: d.y, m: d.m, d: d.d, calendar: .current)) }
                if let place = photo.place { LabeledContent(tr("viewer.place"), value: place) }
                if photo.w > 0 { LabeledContent(tr("viewer.size"), value: "\(photo.w) x \(photo.h) px, \(StorageMeter.format(photo.bytes))") } else { LabeledContent(tr("viewer.size"), value: StorageMeter.format(photo.bytes)) }
                let names = media.collections.filter { photo.collections.contains($0.id) }.map(\.name)
                LabeledContent(tr("viewer.collections"), value: names.isEmpty ? tr("viewer.none") : names.joined(separator: ", "))
            }
            .navigationTitle(tr("viewer.info")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() } } }
        }
        .presentationDetents([.medium])
    }
}
