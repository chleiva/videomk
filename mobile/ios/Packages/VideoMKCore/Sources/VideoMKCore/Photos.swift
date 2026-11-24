import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Photos the user attaches to a video (up to 100).
public enum PhotoLimits {
    public static let maxPhotos = 100
    public static let maxUploadBytes = 10_000_000
    public static let prepareParallelism = 3     // originals are big: only a few are decoded at a time
    public static let uploadParallelism = 4
    public static let uploadAttempts = 3         // per photo
    public static let slotChunk = 25             // presigned posts requested per call

    /// Splits a selection into what fits and what is left out, keeping the first ones.
    public static func fit(selected: Int, attached: Int, loading: Int = 0) -> (keep: Int, leftOut: Int) {
        let room = max(0, maxPhotos - attached - loading)
        let keep = min(max(0, selected), room)
        return (keep, max(0, selected) - keep)
    }

    public static func leftOutMessage(_ n: Int) -> String? {
        n > 0 ? "\(n) \(n == 1 ? "photo was" : "photos were") left out: you can attach up to \(maxPhotos)." : nil
    }
}

/// Runs `op` over `items` with at most `concurrency` in flight. Results come back in input order; `onEach` is called on the caller's
/// isolation as each one finishes (for progress).
public func boundedMap<T: Sendable, R: Sendable>(_ items: [T], concurrency: Int, onEach: (Int, R) -> Void = { _, _ in }, isolation: isolated (any Actor)? = #isolation, _ op: @escaping @Sendable (Int, T) async -> R) async -> [R] {
    var results = [R?](repeating: nil, count: items.count)
    await withTaskGroup(of: (Int, R).self) { group in
        var next = 0
        func launch() {
            guard next < items.count else { return }
            let i = next, item = items[i]; next += 1
            group.addTask { (i, await op(i, item)) }
        }
        for _ in 0..<max(1, concurrency) { launch() }
        while let (i, r) = await group.next() {
            results[i] = r; onEach(i, r)
            if !Task.isCancelled { launch() }
        }
    }
    return results.compactMap { $0 }
}

/// Prepares a photo on the phone before it is uploaded: upright, at most 2048 px on its longest side, and with **no metadata at all**
/// (no GPS, camera or date), because only the pixels are re-encoded. The server cleans every upload again, so this is for privacy and speed.
public enum PhotoPrep {
    public static func jpeg(from data: Data, maxPixel: Int = 2048) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        let opts: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,   // applies the orientation tag, so the pixels are upright
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixel,
        ]
        guard let image = CGImageSourceCreateThumbnailAtIndex(source, 0, opts as CFDictionary) else { return nil }
        for quality in [0.85, 0.7, 0.55] {
            let out = NSMutableData()
            guard let dest = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil) else { return nil }
            CGImageDestinationAddImage(dest, image, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)  // no source properties: nothing else survives
            guard CGImageDestinationFinalize(dest) else { return nil }
            if out.length <= PhotoLimits.maxUploadBytes { return out as Data }
        }
        return nil
    }
}

public struct UploadSlot: Sendable, Equatable, Decodable {
    public let id: String
    public let url: URL
    public let fields: [String: String]
}

struct UploadSlotsResponse: Decodable { let uploads: [UploadSlot] }

/// A multipart/form-data body for S3's presigned POST: the signed fields first, the file last (S3 requires that order).
public enum MultipartForm {
    public static func body(fields: [String: String], file: Data, fileName: String = "photo.jpg", mimeType: String = "image/jpeg", boundary: String = UUID().uuidString) -> (body: Data, contentType: String) {
        var out = Data()
        for (name, value) in fields.sorted(by: { $0.key < $1.key }) {
            out.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
        }
        out.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(fileName)\"\r\nContent-Type: \(mimeType)\r\n\r\n".utf8))
        out.append(file)
        out.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return (out, "multipart/form-data; boundary=\(boundary)")
    }
}

/// Some photos could not be uploaded even after retries. `uploaded` (index to media id) is kept by the caller so a retry only sends the rest.
public struct PhotoUploadFailure: Error, Sendable {
    public let uploaded: [Int: String]
    public let total: Int
    public var failed: Int { total - uploaded.count }
    public var message: String {
        "\(failed) of \(total) photos couldn't be uploaded. Check your connection and tap Try again: the \(uploaded.count) already uploaded won't be sent again."
    }
}

/// Uploads the prepared photos and returns their ids in the same order. Up to `uploadParallelism` at a time, each photo tried up to
/// `uploadAttempts` times, presigned posts requested `slotChunk` at a time. If some still fail it throws `PhotoUploadFailure`
/// (carrying what was uploaded) and the caller keeps the photos; passing that back as `already` resumes with only the missing ones.
public struct PhotoUploader: Sendable {
    let api: APIClient
    let session: URLSession
    let backoff: [Duration]     // wait before attempt 2, 3, ...

    public init(api: APIClient, session: URLSession = .shared, backoff: [Duration] = [.milliseconds(600), .seconds(2)]) {
        self.api = api; self.session = session; self.backoff = backoff
    }

    public func upload(_ photos: [Data], already: [Int: String] = [:], progress: @Sendable (Int, Int) -> Void = { _, _ in }) async throws -> [String] {
        guard !photos.isEmpty, photos.count <= PhotoLimits.maxPhotos else { throw APIError.invalid("Choose between 1 and \(PhotoLimits.maxPhotos) photos.") }
        let total = photos.count
        var done = already.filter { $0.key >= 0 && $0.key < total }
        progress(done.count, total)
        let todo = (0..<total).filter { done[$0] == nil }
        var start = 0
        while start < todo.count {
            try Task.checkCancellation()
            let chunk = Array(todo[start..<min(start + PhotoLimits.slotChunk, todo.count)]); start += chunk.count
            let slots = try await api.requestUploads(count: chunk.count)
            guard slots.count == chunk.count else { throw APIError.server }
            let work = zip(chunk, slots).map { (index: $0, slot: $1) }
            var completed = done.count
            let outcomes = await boundedMap(work, concurrency: PhotoLimits.uploadParallelism, onEach: { _, ok in
                if ok { completed += 1; progress(completed, total) }
            }) { _, w in await self.postWithRetry(photos[w.index], to: w.slot) }
            for (w, ok) in zip(work, outcomes) where ok { done[w.index] = w.slot.id }
            try Task.checkCancellation()
            if outcomes.contains(false) { throw PhotoUploadFailure(uploaded: done, total: total) }
        }
        return (0..<total).compactMap { done[$0] }
    }

    private func postWithRetry(_ photo: Data, to slot: UploadSlot) async -> Bool {
        for attempt in 0..<PhotoLimits.uploadAttempts {
            if attempt > 0 {
                let wait = backoff.isEmpty ? Duration.zero : backoff[min(attempt - 1, backoff.count - 1)]
                try? await Task.sleep(for: wait)
            }
            if Task.isCancelled { return false }
            if (try? await post(photo, to: slot)) != nil { return true }
        }
        return false
    }

    private func post(_ photo: Data, to slot: UploadSlot) async throws {
        var req = URLRequest(url: slot.url, timeoutInterval: 120)
        req.httpMethod = "POST"
        let form = MultipartForm.body(fields: slot.fields, file: photo)
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        // deliberately no Authorization header: the presigned fields are the credential, and the login token must never go to storage
        do {
            let (_, resp) = try await session.upload(for: req, from: form.body)
            guard let code = (resp as? HTTPURLResponse)?.statusCode, (200..<300).contains(code) else { throw APIError.invalid("A photo couldn't be uploaded. Please try again.") }
        } catch let e as APIError { throw e }
        catch is CancellationError { throw CancellationError() }
        catch { throw APIError.network }
    }
}
