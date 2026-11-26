import Foundation
import Observation

/// The two languages the app speaks (docs/I18N.md). English is the default and the fallback for any missing Spanish text.
public enum AppLanguage: String, CaseIterable, Sendable {
    case en, es

    /// Any `es-*` is Spanish, any `en-*` English; other languages are skipped (never guess a third one). Empty or unknown: English.
    public static func resolve(preferred: [String]) -> AppLanguage {
        for id in preferred {
            let code = id.lowercased().split(whereSeparator: { $0 == "-" || $0 == "_" }).first.map(String.init) ?? ""
            if code == "es" { return .es }
            if code == "en" { return .en }
        }
        return .en
    }

    /// The language's own name, written in that language in both locales ("English", "Español").
    public var nativeName: String { self == .en ? "English" : "Español" }
}

/// The explicit choice in Settings: `system` follows the device (or the per-app language of iOS Settings).
public enum LanguageChoice: String, CaseIterable, Sendable { case system, en, es }

/// Which language the app shows right now. Observable: any view that calls `tr(...)` while building its body redraws when the choice changes,
/// so a language switch needs no restart. Order (docs/I18N.md): explicit choice, then device language, then English.
@Observable public final class Localization: @unchecked Sendable {
    public static let shared = Localization()
    public static let defaultsKey = "vmk_locale"

    private let defaults: UserDefaults
    /// The device's preferred languages. Injectable for tests.
    public var preferred: [String]
    public private(set) var choice: LanguageChoice

    /// Tests: `Localization.$override.withValue(.es) { ... }` runs a block in Spanish without touching the shared state (parallel-safe).
    @TaskLocal public static var override: AppLanguage?

    /// `VMK_FORCE_LANG=en|es` in the environment replaces the device language (tests and screenshots); the explicit choice still wins.
    public static var devicePreferred: [String] {
        if let f = ProcessInfo.processInfo.environment["VMK_FORCE_LANG"], !f.isEmpty { return [f] }
        return Locale.preferredLanguages
    }

    public init(defaults: UserDefaults = .standard, preferred: [String] = Localization.devicePreferred) {
        self.defaults = defaults; self.preferred = preferred
        choice = defaults.string(forKey: Self.defaultsKey).flatMap(LanguageChoice.init(rawValue:)) ?? .system
    }

    public func setChoice(_ c: LanguageChoice) {
        choice = c
        if c == .system { defaults.removeObject(forKey: Self.defaultsKey) } else { defaults.set(c.rawValue, forKey: Self.defaultsKey) }
    }

    public var language: AppLanguage {
        if let o = Self.override { return o }
        switch choice {
        case .en: return .en
        case .es: return .es
        case .system: return AppLanguage.resolve(preferred: preferred)
        }
    }

    /// The value of the `X-Locale` header: `en` or `es`.
    public var headerValue: String { language.rawValue }

    /// For dates, numbers, durations and sizes. Keeps the device's region (es_MX, en_GB) when the language matches the device.
    public var locale: Locale {
        let current = Locale.current
        if current.language.languageCode?.identifier == language.rawValue { return current }
        return Locale(identifier: language.rawValue)
    }

    /// Text for `key` in the current language; missing Spanish falls back to English, a missing key to the key itself.
    /// Arguments fill `%@`, `%lld` or positional `%1$lld`. A plural entry picks its form from the FIRST integer argument.
    public func string(_ key: String, _ args: [CVarArg] = []) -> String {
        let fmt = LocalizationCatalog.shared.format(key, language: language, plural: Self.firstCount(args))
        return args.isEmpty ? fmt : String(format: fmt, locale: locale, arguments: args)
    }

    static func firstCount(_ args: [CVarArg]) -> Int? {
        for a in args {
            if let i = a as? Int { return i }
            if let i = a as? Int64 { return Int(i) }
            if let i = a as? Int32 { return Int(i) }
        }
        return nil
    }
}

/// `tr("credits.count", 3)`: the single way the app asks for user-visible text (docs/I18N.md keys, `Strings/Localizable.xcstrings`).
public func tr(_ key: String, _ args: CVarArg...) -> String { Localization.shared.string(key, args) }

/// The catalog file read directly (it ships as a plain resource, so the same code runs in the app and in `swift test`).
public struct LocalizationCatalog: Sendable {
    public struct Entry: Sendable {
        public var value: String?
        public var plural: [String: String] = [:]
    }
    public let entries: [String: [String: Entry]]

    public static let shared: LocalizationCatalog = {
        guard let url = Bundle.module.url(forResource: "Localizable", withExtension: "xcstrings", subdirectory: "Strings"),
              let data = try? Data(contentsOf: url), let c = try? LocalizationCatalog(json: data) else { return LocalizationCatalog(entries: [:]) }
        return c
    }()

    init(entries: [String: [String: Entry]]) { self.entries = entries }

    public init(json: Data) throws {
        guard let root = try JSONSerialization.jsonObject(with: json) as? [String: Any], let strings = root["strings"] as? [String: Any] else {
            throw CocoaError(.coderReadCorrupt)
        }
        var out: [String: [String: Entry]] = [:]
        for (key, v) in strings {
            guard let locs = (v as? [String: Any])?["localizations"] as? [String: Any] else { continue }
            var byLang: [String: Entry] = [:]
            for (lang, lv) in locs {
                guard let d = lv as? [String: Any] else { continue }
                var e = Entry()
                e.value = (d["stringUnit"] as? [String: Any])?["value"] as? String
                if let plural = (d["variations"] as? [String: Any])?["plural"] as? [String: Any] {
                    for (form, fv) in plural { if let s = (fv as? [String: Any])?["stringUnit"] as? [String: Any], let val = s["value"] as? String { e.plural[form] = val } }
                }
                byLang[lang] = e
            }
            out[key] = byLang
        }
        entries = out
    }

    /// English and Spanish both use `one` for exactly 1 and `other` for everything else (0 included).
    static func form(_ n: Int) -> String { n == 1 ? "one" : "other" }

    public func format(_ key: String, language: AppLanguage, plural: Int?) -> String {
        guard let byLang = entries[key] else { return key }
        for lang in [language.rawValue, "en"] {
            guard let e = byLang[lang] else { continue }
            if !e.plural.isEmpty {
                let want = plural.map(Self.form) ?? "other"
                if let s = e.plural[want] ?? e.plural["other"] { return s }
            }
            if let v = e.value { return v }
        }
        return key
    }
}

/// Dates, numbers and durations in the app language (never hand-written strings, docs/I18N.md rule 7).
public extension Localization {
    func abbreviatedDate(_ d: Date) -> String { d.formatted(Date.FormatStyle(date: .abbreviated, time: .omitted).locale(locale)) }
    func mediumDateTime(_ d: Date) -> String { d.formatted(Date.FormatStyle(date: .abbreviated, time: .shortened).locale(locale)) }
    func relative(_ d: Date) -> String { d.formatted(.relative(presentation: .named).locale(locale)) }
    func number(_ n: Int) -> String { n.formatted(.number.locale(locale)) }
    /// "1:05" or "1:02:03" for a video length in seconds.
    func clock(seconds: Double) -> String {
        let s = max(0, Int(seconds.rounded()))
        return s >= 3600 ? String(format: "%d:%02d:%02d", s / 3600, s % 3600 / 60, s % 60) : String(format: "%d:%02d", s / 60, s % 60)
    }
}

public extension Localization {
    /// "2 hr. ago", "hace 2 h": a short relative time for list rows.
    func relativeShort(_ d: Date) -> String {
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .short; f.locale = locale
        return f.localizedString(for: d, relativeTo: .now)
    }
}
