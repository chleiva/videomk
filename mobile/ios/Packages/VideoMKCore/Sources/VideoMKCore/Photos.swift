import Foundation
import ImageIO
import UniformTypeIdentifiers

/// Photos the user attaches to a video (up to 10).
public enum PhotoLimits {
    public static let maxPhotos = 10
    public static let maxUploadBytes = 10_000_000
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

/// Uploads the prepared photos and returns their ids in the same order. Throws on the first failure (the caller keeps the photos and can retry).
public struct PhotoUploader: Sendable {
    let api: APIClient
    let session: URLSession

    public init(api: APIClient, session: URLSession = .shared) { self.api = api; self.session = session }

    public func upload(_ photos: [Data], progress: @Sendable (Int, Int) -> Void = { _, _ in }) async throws -> [String] {
        guard !photos.isEmpty, photos.count <= PhotoLimits.maxPhotos else { throw APIError.invalid("Choose between 1 and \(PhotoLimits.maxPhotos) photos.") }
        let slots = try await api.requestUploads(count: photos.count)
        guard slots.count == photos.count else { throw APIError.server }
        var ids: [String] = []
        progress(0, photos.count)
        for (photo, slot) in zip(photos, slots) {
            try Task.checkCancellation()
            try await post(photo, to: slot)
            ids.append(slot.id)
            progress(ids.count, photos.count)
        }
        return ids
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
