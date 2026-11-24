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

/// What the mic button should do, decided from what the phone allows. Pure, so every combination is tested.
/// Order of preference: our own recognizer (live text, on device when possible) → the keyboard's built-in dictation → a clear way to turn one on.
public enum DictationPlan: Equatable, Sendable {
    public enum Permission: Sendable, Equatable { case undetermined, granted, denied }
    case useApp                       // our recognizer (the system asks for any missing permission first)
    case useKeyboard(String)          // focus the text field and point at the keyboard's own mic key
    case blocked(String)              // nothing usable: say how to fix it

    public static func decide(speech: Permission, microphone: Permission, recognizerAvailable: Bool, keyboardDictationEnabled: Bool) -> DictationPlan {
        let appCanWork = speech != .denied && microphone != .denied && recognizerAvailable
        if appCanWork { return .useApp }
        if keyboardDictationEnabled {
            let why = microphone == .denied ? "Microphone access is off for videomk, so use the microphone key on your keyboard instead."
                : speech == .denied ? "Speech recognition is off for videomk, so use the microphone key on your keyboard instead."
                : "Tap the microphone key on your keyboard to dictate."
            return .useKeyboard(why)
        }
        if microphone == .denied { return .blocked("Allow microphone access for videomk in Settings, or turn on Dictation in Settings › General › Keyboard.") }
        if speech == .denied { return .blocked("Allow speech recognition for videomk in Settings, or turn on Dictation in Settings › General › Keyboard.") }
        return .blocked("Dictation isn't available right now. You can turn it on in Settings › General › Keyboard, or type your idea.")
    }
}
