import ImageIO
import Observation
import PhotosUI
import SwiftUI
import VideoMKCore

struct AttachedPhoto: Identifiable, @unchecked Sendable {   // immutable after creation
    let id = UUID()
    let data: Data          // upright, at most 2048 px, no metadata
    let thumbnail: UIImage
    var meta: PhotoMeta? = nil   // capture time / approximate place from the original; travels only in the generate request
}

/// The photos attached to the video being composed (up to `PhotoLimits.maxPhotos`). The system photo picker needs no permission prompt:
/// the app only ever receives the photos the user taps. Originals are loaded and prepared a few at a time (never all at once); only the
/// prepared JPEG (at most 2048 px) and a small thumbnail stay in memory.
@MainActor @Observable
final class PhotoAttachments {
    private(set) var items: [AttachedPhoto] = []
    private(set) var loading = 0            // selected photos not prepared yet
    private(set) var batchTotal = 0         // size of the batch being prepared, for "Preparing 37 of 100"
    var libraryCount = 0                // photos chosen from My media: they share the limit of 100
    private(set) var notice: String?        // left out / unreadable photos, shown under the strip
    var picked: [PhotosPickerItem] = [] {
        didSet { if !picked.isEmpty { Task { await ingest() } } }
    }

    var remaining: Int { ComposerPhotos.room(phone: items.count + loading, library: libraryCount) }
    var isEmpty: Bool { items.isEmpty && loading == 0 }
    var preparingText: String? { loading > 0 ? "Preparing \(batchTotal - loading + 1) of \(batchTotal)" : nil }

    func remove(_ id: UUID) { items.removeAll { $0.id == id } }
    func clear() { items = []; notice = nil }

    private func ingest() async {
        guard loading == 0 else { picked = []; return }       // the picker is disabled while preparing; ignore a late selection
        let fit = PhotoLimits.fit(selected: picked.count, attached: items.count + libraryCount)
        let batch = Array(picked.prefix(fit.keep))
        picked = []
        notice = PhotoLimits.leftOutMessage(fit.leftOut)
        guard !batch.isEmpty else { return }
        batchTotal = batch.count; loading = batch.count
        var unreadable = 0
        let prepared: [AttachedPhoto?] = await boundedMap(batch, concurrency: PhotoLimits.prepareParallelism, onEach: { [self] _, photo in
            loading -= 1
            if let photo, items.count < PhotoLimits.maxPhotos { items.append(photo) }   // appended as each finishes: the strip fills while preparing
        }) { (_, item) async -> AttachedPhoto? in
            guard let raw = try? await item.loadTransferable(type: Data.self) else { return nil }
            return await Self.prepare(raw)
        }
        unreadable = prepared.count - prepared.filter { $0 != nil }.count
        if unreadable > 0 {
            let msg = "\(unreadable) \(unreadable == 1 ? "photo" : "photos") couldn't be read."
            notice = [notice, msg].compactMap { $0 }.joined(separator: " ")
        }
        batchTotal = 0
    }

    nonisolated static func prepare(_ raw: Data, dates: Bool = PhotoMetaSettings.dates(), locations: Bool = PhotoMetaSettings.locations()) async -> AttachedPhoto? {
        await Task.detached(priority: .userInitiated) {
            let meta = PhotoMetaReader.read(from: raw, dates: dates, locations: locations)   // before the metadata is stripped
            guard let jpeg = PhotoPrep.jpeg(from: raw), let thumb = thumbnail(of: jpeg) else { return nil }
            return AttachedPhoto(data: jpeg, thumbnail: thumb, meta: meta)
        }.value
    }

    /// A small preview (112 px, enough for a 56 pt tile at 2x) decoded straight from the JPEG without inflating the full image.
    nonisolated static func thumbnail(of jpeg: Data, maxPixel: Int = 112) -> UIImage? {
        guard let src = CGImageSourceCreateWithData(jpeg as CFData, nil) else { return nil }
        let opts: [CFString: Any] = [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceCreateThumbnailWithTransform: true,
                                     kCGImageSourceShouldCacheImmediately: true, kCGImageSourceThumbnailMaxPixelSize: maxPixel]
        return CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary).map { UIImage(cgImage: $0) }
    }

    #if DEBUG
    /// UI tests: `VMK_DEBUG_PHOTO_FILES=/path/a.jpg:/path/b.jpg` attaches those files at launch (the system picker can't be driven from a test).
    func loadDebugFiles() async {
        guard items.isEmpty, let paths = ProcessInfo.processInfo.environment["VMK_DEBUG_PHOTO_FILES"], !paths.isEmpty else { return }
        for path in paths.split(separator: ":").prefix(PhotoLimits.maxPhotos) {
            if let raw = FileManager.default.contents(atPath: String(path)), let photo = await Self.prepare(raw) { items.append(photo) }
        }
    }
    #endif
}

/// The strip of attached photos above the text field.
struct AttachedPhotosStrip: View {
    @Bindable var photos: PhotoAttachments
    let minutes: Double
    var library: [LibraryPhoto] = []
    var media: MediaModel?
    var onRemoveLibrary: (String) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(spacing: 8) {
                    ForEach(Array(library.enumerated()), id: \.element.id) { index, photo in
                        LibraryStripTile(photo: photo, media: media, label: "My media photo \(index + 1) of \(library.count)") { withAnimation(.snappy) { onRemoveLibrary(photo.id) } }
                    }
                    ForEach(Array(photos.items.enumerated()), id: \.element.id) { index, photo in
                        Image(uiImage: photo.thumbnail)
                            .resizable().scaledToFill()
                            .frame(width: 56, height: 56)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .overlay(alignment: .topTrailing) {
                                Button { withAnimation(.snappy) { photos.remove(photo.id) } } label: {
                                    Image(systemName: "xmark.circle.fill").font(.system(size: 20)).symbolRenderingMode(.palette).foregroundStyle(.white, Color.black.opacity(0.65))
                                }
                                .padding(2)
                                .accessibilityLabel("Remove photo \(index + 1)")
                            }
                            .accessibilityElement(children: .contain)
                            .accessibilityLabel("Photo \(index + 1) of \(photos.items.count)")
                            .accessibilityIdentifier("attachedPhoto")
                    }
                    if photos.loading > 0 {   // one spinner tile, however many are still being prepared
                        ProgressView().frame(width: 56, height: 56).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                }
                .padding(.horizontal, 20)
            }
            if let preparing = photos.preparingText {
                Text(preparing).font(.caption.weight(.semibold)).foregroundStyle(Theme.primary).padding(.horizontal, 20)
                    .accessibilityIdentifier("photosPreparing")
            }
            if let notice = photos.notice {
                Text(notice).font(.caption).foregroundStyle(Theme.danger).padding(.horizontal, 20)
                    .accessibilityIdentifier("photosNotice")
            }
            Text("\(photos.items.count + library.count) of \(PhotoLimits.maxPhotos) photos. Tell me what to do with them. Location data is removed, and the originals are deleted once your video is made.")
                .font(.caption).foregroundStyle(Theme.textSecondary).padding(.horizontal, 20)
                .accessibilityIdentifier("photosNote")
            if let hint = PhotoCapacity.hint(photos: ComposerPhotos.total(phone: photos.items.count + photos.loading, library: library.count), minutes: minutes) {
                Text(hint)
                    .font(.caption).foregroundStyle(Theme.warning).padding(.horizontal, 20)
                    .accessibilityLabel("Length warning. \(hint)")
                    .accessibilityIdentifier("photosLengthHint")
            }
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}

/// A photo chosen from My media, in the composer strip. Same size as a phone photo, with a small library badge.
struct LibraryStripTile: View {
    let photo: LibraryPhoto
    let media: MediaModel?
    let label: String
    let onRemove: () -> Void
    @State private var image: UIImage?
    var body: some View {
        Group { if let image { Image(uiImage: image).resizable().scaledToFill() } else { Theme.surfaceRaised } }
            .frame(width: 56, height: 56)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(alignment: .bottomLeading) { Image(systemName: "photo.stack.fill").font(.system(size: 10)).padding(3).foregroundStyle(.white).background(Theme.primary, in: Circle()).padding(2).accessibilityHidden(true) }
            .overlay(alignment: .topTrailing) {
                Button(action: onRemove) { Image(systemName: "xmark.circle.fill").font(.system(size: 20)).symbolRenderingMode(.palette).foregroundStyle(.white, Color.black.opacity(0.65)) }
                    .padding(2).accessibilityLabel("Remove \(label)")
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel("\(label). \(MediaGrouping.accessibilityLabel(photo))")
            .accessibilityIdentifier("attachedLibraryPhoto")
            .task(id: photo.id) { if image == nil { image = await media?.thumbnail(for: photo) } }
    }
}
