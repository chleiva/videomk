import Foundation

/// The slim storage meter in the Media header.
public struct StorageMeter: Sendable, Equatable {
    public enum State: Sendable, Equatable { case ok, warning, full }
    public let used: Int, limit: Int
    public init(used: Int, limit: Int) { self.used = max(0, used); self.limit = max(0, limit) }
    public var fraction: Double { limit > 0 ? min(1, Double(used) / Double(limit)) : (used > 0 ? 1 : 0) }
    /// ok below 85 %, warning from 85 %, full at 100 % (or no room at all).
    public var state: State { used >= limit && (limit > 0 || used > 0) ? .full : fraction >= 0.85 ? .warning : .ok }
    public var label: String { tr("storage.used_of", Self.format(used), Self.format(limit)) }
    public var remaining: Int { max(0, limit - used) }

    /// Decimal units (what storage plans use): "640 MB", "1.2 GB", "100 GB".
    public static func format(_ bytes: Int) -> String {
        let b = Double(max(0, bytes))
        let loc = Localization.shared.locale
        func whole(_ v: Double) -> String { Int(v.rounded()).formatted(.number.locale(loc)) }
        if b >= 1e9 { let g = b / 1e9; return g >= 10 || g == g.rounded() ? "\(whole(g)) GB" : "\(g.formatted(.number.precision(.fractionLength(1)).locale(loc))) GB" }
        if b >= 1e6 { return "\(whole(b / 1e6)) MB" }
        if b >= 1e3 { return "\(whole(b / 1e3)) KB" }
        return "\(whole(b)) B"
    }
}

/// Month (and, for busy months, day) sections of the timeline, newest first.
public enum MediaGrouping {
    public struct Section: Equatable, Identifiable, Sendable {
        public let id: String        // "2024-07" or "2024-07-12"
        public let title: String
        public let items: [LibraryPhoto]
        public init(id: String, title: String, items: [LibraryPhoto]) { self.id = id; self.title = title; self.items = items }
    }

    /// year, month, day of the photo: the capture time if known (wall-clock, as written), else the day it was added in the person's calendar.
    public static func day(of p: LibraryPhoto, calendar: Calendar) -> (y: Int, m: Int, d: Int)? {
        if let t = p.taken, let c = wallClock(t) { return (c.y, c.m, c.d) }
        guard let date = isoDate(p.added) else { return nil }
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        guard let y = c.year, let m = c.month, let d = c.day else { return nil }
        return (y, m, d)
    }

    static func wallClock(_ s: String) -> (y: Int, m: Int, d: Int, time: String)? {
        let parts = s.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3, (1...12).contains(parts[1]), (1...31).contains(parts[2]) else { return nil }
        return (parts[0], parts[1], parts[2], String(s.dropFirst(11)))
    }

    static func isoDate(_ s: String) -> Date? {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]
        if let d = f.date(from: s) { return d }
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.date(from: s)
    }

    /// Sort key: capture time (wall-clock) else added time converted to the calendar's wall-clock.
    static func sortKey(_ p: LibraryPhoto, calendar: Calendar) -> String {
        if let t = p.taken, wallClock(t) != nil { return t }
        guard let date = isoDate(p.added) else { return "" }
        let c = calendar.dateComponents([.year, .month, .day, .hour, .minute, .second], from: date)
        return String(format: "%04d-%02d-%02dT%02d:%02d:%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0, c.hour ?? 0, c.minute ?? 0, c.second ?? 0)
    }

    public static func sections(_ photos: [LibraryPhoto], calendar: Calendar = .current, dayThreshold: Int = 60) -> [Section] {
        let sorted = photos.enumerated().sorted { a, b in
            let ka = sortKey(a.element, calendar: calendar), kb = sortKey(b.element, calendar: calendar)
            return ka != kb ? ka > kb : a.offset < b.offset
        }.map(\.element)
        var months: [(key: String, y: Int, m: Int, items: [LibraryPhoto])] = []
        for p in sorted {
            let d = day(of: p, calendar: calendar)
            let key = d.map { String(format: "%04d-%02d", $0.y, $0.m) } ?? "unknown"
            if months.last?.key == key { months[months.count - 1].items.append(p) } else { months.append((key, d?.y ?? 0, d?.m ?? 0, [p])) }
        }
        var out: [Section] = []
        for month in months {
            if month.key == "unknown" { out.append(Section(id: "unknown", title: tr("media.undated"), items: month.items)); continue }
            if month.items.count > dayThreshold {
                var days: [(key: String, y: Int, m: Int, d: Int, items: [LibraryPhoto])] = []
                for p in month.items {
                    let d = day(of: p, calendar: calendar)!
                    let key = String(format: "%04d-%02d-%02d", d.y, d.m, d.d)
                    if days.last?.key == key { days[days.count - 1].items.append(p) } else { days.append((key, d.y, d.m, d.d, [p])) }
                }
                out += days.map { Section(id: $0.key, title: title(y: $0.y, m: $0.m, d: $0.d, calendar: calendar), items: $0.items) }
            } else {
                out.append(Section(id: month.key, title: title(y: month.y, m: month.m, d: nil, calendar: calendar), items: month.items))
            }
        }
        return out
    }

    public static func title(y: Int, m: Int, d: Int?, calendar: Calendar) -> String {
        let f = DateFormatter()
        f.calendar = calendar; f.timeZone = calendar.timeZone; f.locale = Localization.shared.locale
        f.setLocalizedDateFormatFromTemplate(d == nil ? "MMMMyyyy" : "EEEdMMMMyyyy")
        var c = DateComponents(); c.year = y; c.month = m; c.day = d ?? 1; c.hour = 12
        return calendar.date(from: c).map(f.string(from:)) ?? "\(y)-\(m)"
    }

    /// What VoiceOver reads for a photo: its date and place.
    public static func accessibilityLabel(_ p: LibraryPhoto, calendar: Calendar = .current) -> String {
        var parts = [tr("photo.a11y")]
        if let d = day(of: p, calendar: calendar) { parts.append(title(y: d.y, m: d.m, d: d.d, calendar: calendar)) }
        if let place = p.place, !place.isEmpty { parts.append(place) }
        return parts.joined(separator: ", ")
    }
}

/// What to do with the text in the search bar.
public enum SearchPlan: Equatable, Sendable {
    case timeline
    case search(String)
    public static func decide(_ raw: String) -> SearchPlan {
        let q = raw.split(whereSeparator: \.isWhitespace).joined(separator: " ")
        return q.count < 2 ? .timeline : .search(String(q.prefix(300)))
    }
}

/// Runs only the last scheduled job once the pause has passed (typing in the search bar).
public final class SearchDebouncer: @unchecked Sendable {
    private let delay: Duration
    private let lock = NSLock()
    private var task: Task<Void, Never>?
    public init(delay: Duration = .milliseconds(450)) { self.delay = delay }
    public func schedule(_ job: @escaping @Sendable () async -> Void) {
        lock.lock(); task?.cancel()
        let d = delay
        task = Task { try? await Task.sleep(for: d); if !Task.isCancelled { await job() } }
        lock.unlock()
    }
    public func cancel() { lock.lock(); task?.cancel(); task = nil; lock.unlock() }
}

/// Does the video prompt itself describe photos from the library ("a video of my holidays in Thailand in 2024")?
public enum PromptPhotoIntent {
    static let subjects = ["photo", "photos", "picture", "pictures", "pics", "holiday", "holidays", "vacation", "vacations", "trip", "trips", "honeymoon", "wedding", "birthday",
                           "christmas", "kids", "children", "family", "pets", "travels", "journey", "weekend", "summer", "winter", "graduation", "party",
                           // Spanish (the description is in the person's language)
                           "foto", "fotos", "fotografías", "imágenes", "vacaciones", "viaje", "viajes", "boda", "cumpleaños", "navidad", "niños", "hijos", "familia",
                           "mascotas", "verano", "invierno", "graduación", "fiesta", "escapada"]
    public static func looksLikePhotoQuery(_ prompt: String) -> Bool {
        let words = prompt.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        guard words.count >= 2 else { return false }
        let set = Set(words)
        let lower = prompt.lowercased()
        if ["my library", "my media", "my gallery", "mi biblioteca", "mi galería", "mis fotos"].contains(where: lower.contains) { return true }
        let mine = !set.isDisjoint(with: ["my", "our", "mine", "mi", "mis", "nuestro", "nuestra", "nuestros", "nuestras"])
        let hasSubject = !set.isDisjoint(with: Set(subjects))
        let hasYear = words.contains { $0.count == 4 && ($0.hasPrefix("19") || $0.hasPrefix("20")) && Int($0) != nil }
        let photoWord = set.contains("photos") || set.contains("pictures") || set.contains("fotos") || set.contains("imágenes")
        return (mine && hasSubject) || photoWord && (mine || hasYear) || (mine && hasYear)
    }
}

/// How many photos the composer holds in total (phone photos plus library photos) and what is still allowed.
public enum ComposerPhotos {
    public static func total(phone: Int, library: Int) -> Int { phone + library }
    /// Room for photos from the phone given the library selection, and vice versa.
    public static func room(phone: Int, library: Int) -> Int { max(0, PhotoLimits.maxPhotos - phone - library) }
}

/// "Select all" in a list of photos: whatever is in view (All photos, a collection, search results), loading further pages when needed, up to what one
/// video can hold, counting photos already chosen elsewhere (from the phone).
public enum SelectAll {
    public static var limitNote: String { tr("select_all.limit_note", PhotoLimits.maxPhotos) }

    public static func allSelected(view: [String], selected: [String]) -> Bool {
        let s = Set(selected); return !view.isEmpty && view.allSatisfy(s.contains)
    }

    /// The label of the control: "Select all 38", "Select all (up to 100)" while more pages exist, "Clear" once everything in view is selected.
    public static func label(viewCount: Int, hasMore: Bool, allSelected: Bool, limit: Int = PhotoLimits.maxPhotos) -> String {
        if allSelected { return tr("select_all.clear") }
        return hasMore ? tr("select_all.up_to", limit) : tr("select_all.count", viewCount)
    }

    /// Adds what is in view, in order, until `room` more photos are chosen. `limited` says the limit stopped it.
    public static func apply(view: [String], selected: [String], room: Int) -> (selected: [String], limited: Bool) {
        var out = selected
        var s = Set(selected)
        var left = max(0, room)
        var limited = false
        for id in view where !s.contains(id) {
            guard left > 0 else { limited = true; break }
            out.append(id); s.insert(id); left -= 1
        }
        return (out, limited)
    }

    /// "Clear" takes back what is in view and keeps the rest.
    public static func clear(view: [String], selected: [String]) -> [String] { let v = Set(view); return selected.filter { !v.contains($0) } }
}
