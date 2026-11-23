import Observation
import PhotosUI
import SwiftUI
import VideoMKCore

struct AttachedPhoto: Identifiable {
    let id = UUID()
    let data: Data          // upright, at most 2048 px, no metadata
    let thumbnail: UIImage
}

/// The photos attached to the video being composed (up to 10). The system photo picker needs no permission prompt: the app only
/// ever receives the photos the user taps.
@MainActor @Observable
final class PhotoAttachments {
    private(set) var items: [AttachedPhoto] = []
    private(set) var loading = 0
    var picked: [PhotosPickerItem] = [] {
        didSet { if !picked.isEmpty { Task { await ingest() } } }
    }

    var remaining: Int { max(0, PhotoLimits.maxPhotos - items.count - loading) }
    var isEmpty: Bool { items.isEmpty && loading == 0 }

    func remove(_ id: UUID) { items.removeAll { $0.id == id } }
    func clear() { items = [] }

    private func ingest() async {
        let batch = Array(picked.prefix(max(0, PhotoLimits.maxPhotos - items.count - loading)))
        picked = []
        loading += batch.count
        for item in batch {
            if let raw = try? await item.loadTransferable(type: Data.self), let photo = await Self.prepare(raw), items.count < PhotoLimits.maxPhotos { items.append(photo) }
            loading -= 1
        }
    }

    nonisolated static func prepare(_ raw: Data) async -> AttachedPhoto? {
        await Task.detached(priority: .userInitiated) {
            guard let jpeg = PhotoPrep.jpeg(from: raw), let image = UIImage(data: jpeg), let thumb = image.preparingThumbnail(of: CGSize(width: 240, height: 240)) else { return nil }
            return AttachedPhoto(data: jpeg, thumbnail: thumb)
        }.value
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

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
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
                    ForEach(0..<photos.loading, id: \.self) { _ in
                        ProgressView().frame(width: 56, height: 56).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                }
                .padding(.horizontal, 20)
            }
            Text("\(photos.items.count) of \(PhotoLimits.maxPhotos) photos. Tell me what to do with them. Location data is removed, and the originals are deleted once your video is made.")
                .font(.caption).foregroundStyle(Theme.textSecondary).padding(.horizontal, 20)
                .accessibilityIdentifier("photosNote")
        }
        .transition(.opacity.combined(with: .move(edge: .bottom)))
    }
}
