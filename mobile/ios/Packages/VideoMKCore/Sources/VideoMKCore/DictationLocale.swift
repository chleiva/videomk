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
            let why = microphone == .denied ? tr("dictation.mic_off_keyboard")
                : speech == .denied ? tr("dictation.speech_off_keyboard")
                : tr("dictation.tap_keyboard_mic")
            return .useKeyboard(why)
        }
        if microphone == .denied { return .blocked(tr("dictation.allow_mic")) }
        if speech == .denied { return .blocked(tr("dictation.allow_speech")) }
        return .blocked(tr("dictation.unavailable"))
    }
}

/// What to do when Apple's recognizer reports an error. Silent failure was the bug: a phone with Dictation switched off, or without the on-device model,
/// made the microphone button look dead. Every outcome is now either quiet (the normal end of a phrase) or a message that says what to do.
public enum DictationFailure: Equatable, Sendable {
    case finishQuietly                 // normal end: text arrived, or we cancelled it ourselves
    case retryOnServer                 // on-device recognition failed before any text: try Apple's server recognizer
    case message(String)

    public static func classify(domain: String, code: Int, gotText: Bool, onDevice: Bool, dictationEnabled: Bool) -> DictationFailure {
        if gotText { return .finishQuietly }                                   // errors after speech are how a session normally ends
        if code == 216 || code == 301 { return .finishQuietly }                // cancelled
        if code == 1110 || code == 1107 && domain.contains("Assistant") { return .message(tr("dictation.heard_nothing")) }
        if onDevice { return .retryOnServer }                                  // always try the server recognizer first: our reading of the Dictation setting must never block a working microphone
        if !dictationEnabled { return .message(tr("dictation.turned_off")) }
        if domain == "NSURLErrorDomain" || code == 1100 || code == 203 { return .message(tr("dictation.needs_internet")) }
        return .message(tr("dictation.stopped", domain, String(code)))
    }
}
