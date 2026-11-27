import Foundation

/// What happens after the Create tap (docs/DESIGN_BAR_2026.md, signature 2 and rule 7). The button becomes a live capsule: "Checking your request",
/// then "Starting your video". The form is locked the whole time, and it ends in exactly one of four ways: a question, a refusal, the Making screen,
/// or the form restored intact. Pure logic: the screen only draws `phase` and reacts to `ending`.
public struct CreateCapsule: Equatable, Sendable {
    public enum Phase: Equatable, Sendable {
        case button                    // the form is editable, the Create button is a button
        case checking(slow: Bool)      // "Checking your request"; Cancel gives the form back
        case starting                  // "Starting your video": the request is on its way, nothing can be taken back
    }

    public enum Event: Equatable, Sendable {
        case tapCreate(needsCheck: Bool)   // the server has a request check, or not
        case slow                          // the check is taking longer than usual
        case checkPassed                   // go on to start the video
        case needsQuestions                // the check came back with questions
        case refused                       // the check (or the start) said no
        case cancel                        // the person tapped Cancel
        case confirmed                     // questions answered or skipped: start the video
        case started                       // the server accepted it, or the start was handed to the list (photos still uploading)
        case failed                        // the start did not work: everything is given back
    }

    public enum Ending: Equatable, Sendable { case question, refusal, making, restored }

    public private(set) var phase: Phase = .button
    /// How the last run ended; nil while it runs and before the first tap.
    public private(set) var ending: Ending?

    public init() {}

    /// The form cannot be changed and nothing can be sent a second time.
    public var isLocked: Bool { phase != .button }
    /// Cancel is honest only while the request is being checked: once it is starting, it is already on its way.
    public var canCancel: Bool { if case .checking = phase { true } else { false } }
    public var isSlow: Bool { phase == .checking(slow: true) }

    /// Applies an event. Returns false (and changes nothing) when the event makes no sense in the current phase: a second tap, a late answer after Cancel.
    @discardableResult public mutating func handle(_ event: Event) -> Bool {
        switch (phase, event) {
        case (.button, .tapCreate(let needsCheck)):
            phase = needsCheck ? .checking(slow: false) : .starting; ending = nil
        case (.button, .confirmed):
            phase = .starting; ending = nil
        case (.checking(false), .slow):
            phase = .checking(slow: true)
        case (.checking, .checkPassed):
            phase = .starting
        case (.checking, .needsQuestions):
            phase = .button; ending = .question
        case (.checking, .refused), (.starting, .refused):
            phase = .button; ending = .refusal
        case (.checking, .cancel):
            phase = .button; ending = .restored
        case (.starting, .started):
            ending = .making               // stays a capsule until the screen closes: the button never flashes back
        case (.starting, .failed):
            phase = .button; ending = .restored
        default:
            return false
        }
        return true
    }

    /// A fresh screen.
    public mutating func reset() { self = CreateCapsule() }
}
