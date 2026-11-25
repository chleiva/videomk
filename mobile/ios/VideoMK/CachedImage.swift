import CryptoKit
import SwiftUI
import VideoMKCore

/// Pictures of the video list, in memory and on disk, keyed by where they live (`ImageKey`), never by their signed link: the server signs every link anew
/// on every list call, and a picture must not be fetched, or flash, because its signature changed.
@MainActor
final class StableImageStore {
    static let shared = StableImageStore()
    private let memory = NSCache<NSString, UIImage>()
    private let directory: URL
    private var inFlight: [String: Task<UIImage?, Never>] = [:]

    init() {
        directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("VideoMKVideoImages", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        memory.countLimit = 200
    }

    /// Instant, no waiting: what is already in memory.
    func cached(_ url: URL?) -> UIImage? { url.flatMap { memory.object(forKey: ImageKey.stable($0) as NSString) } }

    /// Memory, then disk, then the network (with the freshly signed link). A failed fetch leaves what the caller already shows.
    func image(for url: URL) async -> UIImage? {
        let key = ImageKey.stable(url)
        if let hit = memory.object(forKey: key as NSString) { return hit }
        let file = fileURL(key)
        if let data = try? Data(contentsOf: file), let img = UIImage(data: data) { memory.setObject(img, forKey: key as NSString); return img }
        #if DEBUG
        if url.scheme == "fake" {      // screenshots and jitter checks: drawn pictures, portrait or landscape
            let size = url.host == "portrait" ? CGSize(width: 270, height: 480) : CGSize(width: 480, height: 270)
            let img = MediaModel.fakeImage(seed: url.lastPathComponent, size: size)
            memory.setObject(img, forKey: key as NSString); return img
        }
        #endif
        if let running = inFlight[key] { return await running.value }
        let task = Task<UIImage?, Never> {
            guard let (data, resp) = try? await URLSession.shared.data(from: url), (resp as? HTTPURLResponse).map({ (200..<300).contains($0.statusCode) }) ?? true, let img = UIImage(data: data) else { return nil }
            try? data.write(to: file, options: .atomic)
            return img
        }
        inFlight[key] = task
        let img = await task.value
        inFlight[key] = nil
        if let img { memory.setObject(img, forKey: key as NSString) }
        return img
    }

    func removeAll() { memory.removeAllObjects(); try? FileManager.default.removeItem(at: directory); try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true) }

    private func fileURL(_ key: String) -> URL { directory.appendingPathComponent(SHA256.hash(data: Data(key.utf8)).map { String(format: "%02x", $0) }.joined() + ".img") }
}

/// A picture that never flashes: it shows what the store has at once, fetches only a picture it has never seen, and fades in only that first time.
/// The image is identified by `ImageKey`, so a new signature on the same link does nothing at all.
struct CachedImage<Content: View>: View {
    let url: URL?
    @ViewBuilder let content: (Image) -> Content
    @State private var image: UIImage?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init(url: URL?, @ViewBuilder content: @escaping (Image) -> Content) {
        self.url = url; self.content = content
        _image = State(initialValue: StableImageStore.shared.cached(url))       // already known: first frame is the picture, no placeholder
    }

    var body: some View {
        Group { if let image { content(Image(uiImage: image)).transition(.opacity) } else { Color.clear } }
            .task(id: ImageKey.stable(url)) {
                guard let url, image == nil else { return }       // a picture we already show is never fetched again, whatever its new signature says
                if let img = await StableImageStore.shared.image(for: url) { withAnimation(reduceMotion ? nil : .easeOut(duration: 0.25)) { image = img } }
            }
    }
}
