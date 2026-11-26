import Foundation

/// The day groups of the video list (Today / Yesterday / Earlier). Pure, so it is tested with fixed dates and calendars.
public enum DayGroup: Int, Sendable, CaseIterable, Comparable {
    case today, yesterday, earlier
    public static func < (a: DayGroup, b: DayGroup) -> Bool { a.rawValue < b.rawValue }

    /// A video without a date goes to Earlier.
    public static func of(_ date: Date?, now: Date = .now, calendar: Calendar = .current) -> DayGroup {
        guard let date else { return .earlier }
        if calendar.isDate(date, inSameDayAs: now) { return .today }
        if let y = calendar.date(byAdding: .day, value: -1, to: now), calendar.isDate(date, inSameDayAs: y) { return .yesterday }
        return .earlier
    }

    /// Keeps the input order inside each group; empty groups are dropped.
    public static func grouped<T>(_ items: [T], date: (T) -> Date?, now: Date = .now, calendar: Calendar = .current) -> [(group: DayGroup, items: [T])] {
        allCases.compactMap { g in
            let part = items.filter { of(date($0), now: now, calendar: calendar) == g }
            return part.isEmpty ? nil : (g, part)
        }
    }
}
