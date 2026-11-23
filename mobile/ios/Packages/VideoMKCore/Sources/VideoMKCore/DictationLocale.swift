import Foundation

/// Which speech-recognition locale to use. The recognizer must match the language being spoken: a Spanish speaker on an English
/// iPhone would otherwise get a garbled English transcript, which the server then can't recognise as Spanish.
public enum DictationLanguage: String, CaseIterable, Sendable, Identifiable {
    case english = "en", spanish = "es"
    public var id: String { rawValue }
    public var title: String { self == .english ? "English" : "Español" }

    /// The saved choice if any, else the first supported language in the phone's preferred-language order, else English.
    public static func initial(saved: String?, preferred: [String]) -> DictationLanguage {
        if let saved, let l = DictationLanguage(rawValue: saved) { return l }
        for tag in preferred {
            let code = String(tag.prefix(2)).lowercased()
            if let l = DictationLanguage(rawValue: code) { return l }
        }
        return .english
    }

    /// The best supported recognizer locale for this language: same region as the phone when available, else the first one offered.
    public func locale(region: String?, supported: [String]) -> String {
        let mine = supported.filter { $0.lowercased().hasPrefix(rawValue + "-") || $0.lowercased() == rawValue }
        if let region, let exact = mine.first(where: { $0.uppercased().hasSuffix("-" + region.uppercased()) }) { return exact }
        let preferred = self == .english ? "en-US" : "es-MX"  // largest audience when the phone's region has no match
        return mine.first(where: { $0 == preferred }) ?? mine.first ?? preferred
    }
}
