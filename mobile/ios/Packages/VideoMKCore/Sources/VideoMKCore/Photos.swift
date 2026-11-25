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

/// What the phone tells the server about one photo, read from the ORIGINAL bytes before they are stripped. It travels only in the
/// generate request (`media_meta`), never in the uploaded file. Coordinates are rounded to 2 decimals (about 1 km).
public struct PhotoMeta: Sendable, Equatable {
    public var taken: String?       // "YYYY-MM-DDTHH:MM:SS", local wall-clock time, no timezone
    public var lat: Double?
    public var lon: Double?
    public init(taken: String? = nil, lat: Double? = nil, lon: Double? = nil) { self.taken = taken; self.lat = lat; self.lon = lon }
    public var isEmpty: Bool { taken == nil && lat == nil && lon == nil }

    var json: [String: Any] {
        var out: [String: Any] = [:]
        if let taken { out["taken"] = taken }
        if let lat, let lon { out["lat"] = lat; out["lon"] = lon }
        return out
    }
}

/// The two Settings switches (default on).
public enum PhotoMetaSettings {
    public static let datesKey = "usePhotoDates"
    public static let locationsKey = "usePhotoLocations"
    public static func dates(_ d: UserDefaults = .standard) -> Bool { d.object(forKey: datesKey) as? Bool ?? true }
    public static func locations(_ d: UserDefaults = .standard) -> Bool { d.object(forKey: locationsKey) as? Bool ?? true }
}

public enum PhotoMetaReader {
    /// Reads capture time and approximate place from the original photo. A part whose switch is off is not read at all.
    public static func read(from data: Data, dates: Bool, locations: Bool) -> PhotoMeta? {
        guard dates || locations, let src = CGImageSourceCreateWithData(data as CFData, nil),
              let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any] else { return nil }
        var meta = PhotoMeta()
        if dates {
            let exif = props[kCGImagePropertyExifDictionary] as? [CFString: Any]
            let tiff = props[kCGImagePropertyTIFFDictionary] as? [CFString: Any]
            let raw = (exif?[kCGImagePropertyExifDateTimeOriginal] as? String) ?? (tiff?[kCGImagePropertyTIFFDateTime] as? String)
            meta.taken = raw.flatMap(isoDate)
        }
        if locations, let gps = props[kCGImagePropertyGPSDictionary] as? [CFString: Any] {
            if let lat = coordinate(gps[kCGImagePropertyGPSLatitude], gps[kCGImagePropertyGPSLatitudeRef], negative: "S", limit: 90),
               let lon = coordinate(gps[kCGImagePropertyGPSLongitude], gps[kCGImagePropertyGPSLongitudeRef], negative: "W", limit: 180) {
                meta.lat = lat; meta.lon = lon
            }
        }
        return meta.isEmpty ? nil : meta
    }

    /// "2026:07:12 18:30:00" to "2026-07-12T18:30:00"; anything else (including a zeroed date) is dropped.
    static func isoDate(_ exif: String) -> String? {
        let p = exif.trimmingCharacters(in: .whitespaces).split(whereSeparator: { ":- T".contains($0) }).map(String.init)
        guard p.count >= 6, p[0].count == 4, p[1...5].allSatisfy({ $0.count == 2 }), let y = Int(p[0]), let mo = Int(p[1]), let d = Int(p[2]),
              let h = Int(p[3]), let mi = Int(p[4]), let s = Int(p[5]), y >= 1900, (1...12).contains(mo), (1...31).contains(d), h < 24, mi < 60, s < 61 else { return nil }
        return "\(p[0])-\(p[1])-\(p[2])T\(p[3]):\(p[4]):\(p[5])"
    }

    static func coordinate(_ value: Any?, _ ref: Any?, negative: String, limit: Double) -> Double? {
        guard let v = (value as? NSNumber)?.doubleValue, v.isFinite, v >= 0 else { return nil }
        let signed = (ref as? String)?.uppercased() == negative ? -v : v
        let rounded = ((signed * 100).rounded() / 100) + 0   // + 0 turns -0.0 into 0.0
        return abs(rounded) <= limit ? rounded : nil
    }

    /// The `media_meta` object: keyed by media id, only photos that have something to say.
    public static func mediaMeta(ids: [String], metas: [PhotoMeta?]) -> [String: PhotoMeta] {
        var out: [String: PhotoMeta] = [:]
        for (id, meta) in zip(ids, metas) { if let meta, !meta.isEmpty { out[id] = meta } }
        return out
    }
}

/// How many photos fit in a video of a given length (the server shows several at once, 51 per minute: 100 photos fit in 2 minutes).
public enum PhotoCapacity {
    /// The server's rule: max_used(sec) = max(3, floor(sec * 0.85)). 15 s = 12 photos, 30 s = 25, 45 s = 38, 1 min = 51.
    public static func capacity(minutes: Double) -> Int { max(3, Int((minutes * 60 * 0.85 + 1e-9).rounded(.down))) }
    public static func minimumMinutes(photos: Int) -> Double { Double(photos) * 1.0 / 0.85 / 60 }

    /// A one-line warning when the chosen length is too short for the attached photos; nil when everything fits (or no photos).
    public static func hint(photos: Int, minutes: Double, options: [Double] = CreateOptions.lengths) -> String? {
        let fits = capacity(minutes: minutes)
        guard photos > fits else { return nil }
        let need = minimumMinutes(photos: photos)
        let sorted = options.sorted()
        let n = fits
        let intro = "About \(n) of your \(photos) \(photos == 1 ? "photo" : "photos") \(n == 1 ? "fits" : "fit") in \(length(minutes))"
        if let better = sorted.first(where: { $0 >= need - 1e-9 && $0 > minutes }) {
            return "\(intro) (the best ones, no duplicates). Choose \(length(better)) to show \(photos == 1 ? "it" : "them all")."
        }
        return "\(intro) (the best ones, no duplicates)."
    }

    /// "15 seconds", "1 minute", "3 minutes" (the words the hint uses).
    static func length(_ m: Double) -> String {
        if m < 1 { let sec = Int((m * 60).rounded()); return "\(sec) seconds" }
        let n = Int(m.rounded()); return n == 1 ? "1 minute" : "\(n) minutes"
    }
}
