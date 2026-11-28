import Foundation

/// How dictated text joins what is already in the field. Pure (no microphone), so the append and rebase rules are unit tested.
///
/// Rules: the text in the field when dictation starts is the BASE. The field always shows `base + separator + current transcript`; a recognition task that
/// ends is folded into the base (`fold`) and the next task starts empty, so nothing said is lost and nothing typed is overwritten. If the field no longer holds
/// what we last wrote, the person edited it by hand while listening: the field becomes the new base (`.rebased`) and the caller restarts the recognizer so its
/// transcript starts again from nothing.
public struct DictationText: Sendable, Equatable {
    public private(set) var base: String
    private var expected: String

    public enum Step: Equatable, Sendable {
        /// Set the field to this text.
        case write(String)
        /// The person changed the field by hand. The field is the new base; drop the running transcript and restart the recognizer. Write nothing now.
        case rebased
    }

    public init(startingWith field: String) { base = field; expected = field }

    /// `base + " " + segment`: one space unless the base is empty, already ends with a new line, or the segment is blank. Trailing spaces of the base are not doubled.
    public static func compose(_ base: String, _ segment: String) -> String {
        let seg = segment.trimmingCharacters(in: .whitespacesAndNewlines)
        if seg.isEmpty { return base }
        var b = base
        while let last = b.last, last == " " || last == "\t" { b.removeLast() }
        if b.isEmpty || b.hasSuffix("\n") { return b + seg }
        return b + " " + seg
    }

    /// A live (partial) transcript of the running task. `field` is what the text field holds right now.
    public mutating func hear(_ segment: String, field: String) -> Step {
        if field != expected { base = field; expected = field; return .rebased }
        let text = Self.compose(base, segment)
        expected = text
        return .write(text)
    }

    /// The task finished: its transcript becomes part of the base.
    public mutating func fold(_ segment: String, field: String) -> Step {
        let step = hear(segment, field: field)
        if case .write(let text) = step { base = text }
        return step
    }
}

/// When a dictation session may start another recognition task, and when it must stop. Pure and clock-free (the caller passes seconds).
/// A task ends by itself after about a minute, after a long silence, or with an error; none of that may end the dictation. Only the person's Stop,
/// the hard maximum, a long stretch with nothing said, or a task that keeps failing at once may.
public struct DictationRestartPolicy: Sendable, Equatable {
    public enum Action: Equatable, Sendable { case restart, stopTimeLimit, stopIdle, stopFailing }

    public let maxSeconds: Double, idleSeconds: Double, maxRapidFailures: Int
    private var sessionStart: Double = 0, lastText: Double = 0, taskStart: Double = 0
    private var rapid = 0

    public init(maxSeconds: Double = 300, idleSeconds: Double = 60, maxRapidFailures: Int = 3) {
        self.maxSeconds = maxSeconds; self.idleSeconds = idleSeconds; self.maxRapidFailures = maxRapidFailures
    }

    public mutating func sessionStarted(now: Double) { sessionStart = now; lastText = now; taskStart = now; rapid = 0 }
    public mutating func taskStarted(now: Double) { taskStart = now }
    public mutating func textArrived(now: Double) { lastText = now; rapid = 0 }

    /// `hadText`: this task produced any text. A task that ends under a second with no text counts as a quick failure (so a broken recognizer cannot loop).
    public mutating func taskEnded(hadText: Bool, now: Double) -> Action {
        if now - sessionStart >= maxSeconds { return .stopTimeLimit }
        if hadText { rapid = 0; return .restart }
        if now - taskStart < 1 { rapid += 1; if rapid >= maxRapidFailures { return .stopFailing } } else { rapid = 0 }
        if now - lastText >= idleSeconds { return .stopIdle }
        return .restart
    }
}

/// What the recognizer should be told about language. The app's own language wins (the person reads and writes the Create screen in it, and the server is told
/// the same one); the phone's preferred languages are only the fallback, and a fallback is always reported so it is never silently the wrong one.
public struct DictationLocaleChoice: Equatable, Sendable {
    public let tag: String
    /// True when the app language is not offered by the recognizer on this device and `tag` is something else.
    public let fellBack: Bool

    public static func resolve(app: AppLanguage, deviceLanguages: [String], region: String?, supported: [String]) -> DictationLocaleChoice {
        let language = DictationLanguage(rawValue: app.rawValue) ?? .english
        let mine = supported.filter { $0.lowercased().hasPrefix(language.rawValue + "-") || $0.lowercased() == language.rawValue }
        if supported.isEmpty || !mine.isEmpty { return DictationLocaleChoice(tag: language.locale(region: region, supported: supported), fellBack: false) }
        for tag in deviceLanguages {
            let code = String(tag.split(whereSeparator: { $0 == "-" || $0 == "_" }).first ?? "").lowercased()
            if code == language.rawValue { continue }
            let normal = tag.replacingOccurrences(of: "_", with: "-")
            if let exact = supported.first(where: { $0.replacingOccurrences(of: "_", with: "-").lowercased() == normal.lowercased() }) { return DictationLocaleChoice(tag: exact, fellBack: true) }
            if let any = supported.first(where: { $0.lowercased().hasPrefix(code + "-") }) { return DictationLocaleChoice(tag: any, fellBack: true) }
        }
        return DictationLocaleChoice(tag: supported.first(where: { $0 == "en-US" }) ?? supported[0], fellBack: true)
    }
}

/// The seam for a different engine (the paid "Better dictation" mode will plug in here). The Create screen only talks to this.
@MainActor public protocol DictationEngine: AnyObject {
    var isListening: Bool { get }
    /// Called with the whole field text every time dictation changes it.
    var onText: ((String) -> Void)? { get set }
    /// What the field holds right now; lets the engine notice hand edits and rebase.
    var textProvider: (() -> String)? { get set }
    func stop()
    func cancel()
}
