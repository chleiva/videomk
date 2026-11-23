import Foundation
import Observation
import VideoMKCore

@MainActor @Observable
final class EditorModel {
    enum Phase: Equatable { case loading, editing, rendering(RenderMode), done(RenderMode), failed(String) }

    let videoID: String
    private let app: AppModel
    private(set) var phase: Phase = .loading
    private(set) var snapshot: EditorSnapshot?
    var title = ""
    var beats: [EditorBeat] = []
    private(set) var picks: [String: String] = [:]
    var banner: String?          // conflict / validation / network message the user can act on
    private(set) var resultURL: URL?

    init(videoID: String, app: AppModel) { self.videoID = videoID; self.app = app }

    var limits: EditorLimits { snapshot?.limits ?? EditorLimits() }
    var ops: [EditOp] {
        guard let s = snapshot else { return [] }
        return EditorDiff.ops(serverTitle: s.title, server: s.beats, localTitle: title, local: beats, picks: picks)
    }
    var isDirty: Bool { !ops.isEmpty }
    var canPublishWithoutChanges: Bool { snapshot?.previewRev == snapshot?.rev && snapshot?.previewRev != nil && snapshot?.finalRev != snapshot?.rev }
    var isLocked: Bool { if case .rendering = phase { true } else { false } }

    func isEdited(_ id: String) -> Bool {
        guard let s = snapshot, let server = s.beats.first(where: { $0.id == id }), let local = beats.first(where: { $0.id == id }) else { return false }
        return EditorDiff.normalize(server.narration) != EditorDiff.normalize(local.narration) || picks[id] != nil
    }

    func narrationError(for id: String) -> String? {
        beats.first { $0.id == id }.flatMap { EditorDiff.narrationError($0.narration, limits: limits) }
    }

    // MARK: load

    func load() async {
        phase = .loading; banner = nil
        do {
            let s = try await app.editorSnapshot(videoID)
            adopt(s)
            phase = s.editState == .rendering ? .rendering(RenderMode(rawValue: s.editMode ?? "") ?? .preview) : .editing
            if case .rendering(let mode) = phase { await waitForRender(mode) }
        } catch let e as APIError { phase = .failed(e.message) } catch { phase = .failed(APIError.server.message) }
    }

    private func adopt(_ s: EditorSnapshot) {
        snapshot = s; title = s.title; beats = s.beats; picks = [:]
    }

    // MARK: edit

    func setNarration(_ id: String, _ text: String) {
        guard let i = beats.firstIndex(where: { $0.id == id }) else { return }
        beats[i].narration = text
    }

    func pick(_ candidate: PhotoCandidate, for id: String) { picks[id] = candidate.key }
    func clearPick(for id: String) { picks[id] = nil }
    func move(from: IndexSet, to: Int) { beats.move(fromOffsets: from, toOffset: to) }
    func delete(at offsets: IndexSet) {
        guard beats.count - offsets.count >= 1 else { banner = "A video needs at least one scene."; return }
        beats.remove(atOffsets: offsets)
    }
    func discard() { if let s = snapshot { adopt(s); banner = nil } }

    // MARK: render

    /// Preview renders a quick draft; final renders the full-quality version and replaces the published video.
    func submit(_ mode: RenderMode) async {
        guard let s = snapshot, !isLocked else { return }
        let bad = beats.first { narrationError(for: $0.id) != nil }
        if let bad { banner = narrationError(for: bad.id); return }
        banner = nil
        do {
            _ = try await app.applyEdits(videoID, baseRev: s.rev, ops: ops, mode: mode)
            phase = .rendering(mode)
            await waitForRender(mode)
        } catch let e as APIError {
            if case .conflict = e { banner = e.message + " Your edits on this screen are kept until you reload." } else { banner = e.message }
        } catch { banner = APIError.server.message }
    }

    private func waitForRender(_ mode: RenderMode) async {
        for _ in 0..<150 {  // about 10 minutes
            try? await Task.sleep(for: .seconds(4))
            if Task.isCancelled { return }
            guard let s = try? await app.editorSnapshot(videoID), s.editState != .rendering else { continue }
            adopt(s)
            if s.editState == .failed { phase = .failed("The render didn't finish. Your changes are saved; try again."); return }
            resultURL = mode == .final ? s.finalURL : s.previewURL
            phase = .done(mode)
            return
        }
        phase = .failed("This is taking longer than usual. Close the editor and check back in a few minutes.")
    }

    func keepEditing() { phase = .editing }
}
