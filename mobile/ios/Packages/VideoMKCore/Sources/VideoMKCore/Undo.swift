import Foundation
import Observation

/// Undo over confirm (docs/DESIGN_BAR_2026.md rule 8): a delete hides the thing at once and shows "Deleted · Undo" for six seconds. The server is
/// only told when the time is up (or when something else is deleted, or the app is left): until then Undo simply brings it back.
/// One pending delete at a time; offering a second one sends the first.
@MainActor @Observable
public final class UndoCenter {
    public struct Pending: Identifiable {
        public let id = UUID()
        public let text: String
        let undo: @MainActor () -> Void
        let commit: @MainActor () async -> Void
    }

    public static let window: Duration = .seconds(6)
    public private(set) var current: Pending?
    @ObservationIgnored private var timer: Task<Void, Never>?
    @ObservationIgnored private let window: Duration

    public init(window: Duration = UndoCenter.window) { self.window = window }

    /// The thing is already hidden by the caller. `undo` shows it again; `commit` tells the server (and shows it again itself if that fails).
    public func offer(_ text: String, undo: @escaping @MainActor () -> Void, commit: @escaping @MainActor () async -> Void) {
        flush()
        let p = Pending(text: text, undo: undo, commit: commit)
        current = p
        timer = Task { [weak self, window] in
            try? await Task.sleep(for: window)
            guard !Task.isCancelled, let self, self.current?.id == p.id else { return }
            self.current = nil
            await p.commit()
        }
    }

    /// The person tapped Undo: nothing was sent, the thing is back.
    public func undo() {
        timer?.cancel(); timer = nil
        guard let p = current else { return }
        current = nil
        p.undo()
    }

    /// Sends the pending delete now (another delete, the app going to the background, signing out).
    public func flush() {
        timer?.cancel(); timer = nil
        guard let p = current else { return }
        current = nil
        Task { await p.commit() }
    }
}

/// The video's description as the server writes it (chapters, sources, photo credits in one text), split into titled groups for the Info sheet.
/// A paragraph whose first line is a short label ("Chapters", "Sources:", "Photo credits: …") becomes a group with that title; anything else stays
/// an untitled paragraph. Nothing is dropped or reworded.
public enum VideoInfoText {
    public struct Group: Equatable, Sendable, Identifiable {
        public let title: String?
        public let body: String
        public var id: String { (title ?? "") + "|" + body }
    }

    public static func groups(_ description: String) -> [Group] {
        let paragraphs = description.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n\n").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        return paragraphs.map { p in
            let lines = p.components(separatedBy: "\n")
            let first = lines[0].trimmingCharacters(in: .whitespaces)
            if lines.count > 1, isLabel(first) { return Group(title: clean(first), body: lines.dropFirst().joined(separator: "\n")) }
            if let colon = first.firstIndex(of: ":"), lines.count == 1 || true {
                let head = String(first[..<colon]), rest = String(first[first.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
                if isLabel(head), !head.contains("http"), !rest.isEmpty, !rest.hasPrefix("//") {
                    return Group(title: clean(head), body: ([rest] + lines.dropFirst()).joined(separator: "\n"))
                }
            }
            return Group(title: nil, body: p)
        }
    }

    /// A short line of words (no sentence, no time code, no link) reads as a label.
    private static func isLabel(_ s: String) -> Bool {
        let t = clean(s)
        guard !t.isEmpty, t.count <= 28, t.first?.isLetter == true, !t.contains("."), !t.contains("http") else { return false }
        return t.split(separator: " ").count <= 4
    }

    private static func clean(_ s: String) -> String { s.trimmingCharacters(in: CharacterSet(charactersIn: ": ").union(.whitespaces)) }
}
