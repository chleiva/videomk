import Foundation

/// The server signs every picture link anew on every list call (same path, new signature). A picture is identified by where it lives, never by
/// its signature, so a poll that brings new links changes nothing on screen.
public enum ImageKey {
    /// host + path, without the query string (the signature and its date).
    public static func stable(_ url: URL) -> String { "\(url.host ?? "")\(url.path)" }
    public static func stable(_ url: URL?) -> String? { url.map(stable) }
}

public extension VideoItem {
    /// Equal in everything the person can see: the signed links only count by their stable key.
    func visiblyEqual(_ o: VideoItem) -> Bool {
        id == o.id && status == o.status && title == o.title && durationSeconds == o.durationSeconds && createdAt == o.createdAt
            && rejectReason == o.rejectReason && editable == o.editable && aspect == o.aspect && resolution == o.resolution
            && ImageKey.stable(previewGifURL) == ImageKey.stable(o.previewGifURL) && ImageKey.stable(videoURL) == ImageKey.stable(o.videoURL)
    }
}

/// Merges a fresh list into the one on screen without replacing what did not visibly change: same instances, same order, so nothing re-renders.
public enum VideoListMerge {
    public struct Result: Equatable, Sendable { public let items: [VideoItem]; public let changed: Bool }

    /// - Parameters:
    ///   - linkStamp: when the links of each video were last taken; older than `refreshLinksAfter` they are replaced (they expire), silently.
    public static func merge(old: [VideoItem], fresh: [VideoItem], linkStamp: inout [String: Date], now: Date = .now, refreshLinksAfter: TimeInterval = 30 * 60) -> Result {
        let byID = Dictionary(old.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        var out: [VideoItem] = []
        var changed = old.count != fresh.count
        for f in fresh {
            if let o = byID[f.id], o.visiblyEqual(f) {
                let stale = now.timeIntervalSince(linkStamp[f.id] ?? .distantPast) > refreshLinksAfter
                if stale { linkStamp[f.id] = now; out.append(f); changed = true }       // new links, same picture: swapped once in a while
                else { out.append(o) }
            } else { linkStamp[f.id] = now; out.append(f); changed = true }
        }
        if !changed { changed = zip(old, out).contains { $0.id != $1.id } }
        return Result(items: changed ? out : old, changed: changed)
    }
}
