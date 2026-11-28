import AVFoundation
import Observation
import UIKit
import VideoMKCore

/// "Better dictation" (Pro and Max). The Create screen talks to this instead of `Dictation`; it has the same surface.
///
/// While recording, the native recognizer (`Dictation`) keeps running as a live preview and as the fallback. A clip (mono AAC, 16 kHz, 32 kbps, m4a) is recorded next to it.
/// On Stop the clip is uploaded; the returned text replaces the preview on top of the text that was there before (or is appended when there was no preview), never over
/// a field the person edited. Any error leaves the native text in the field. The audio lives in one temp file that is deleted as soon as the upload ends; it is never
/// logged. Pure rules: `BetterDictationResolution`, `placeBetterText`, `DictationIDs` in VideoMKCore (tested). Not testable in a simulator: the real microphone.
@MainActor @Observable
final class BetterDictation: DictationEngine {
    let native = Dictation()
    /// Every clip that produced text; sent as `dictation_ids` with the next create and cleared when the video starts.
    private(set) var ids = DictationIDs()
    /// The clip is being turned into text.
    private(set) var isWorking = false
    /// One line after a fallback or the 6 minute stop (the screen shows it for a few seconds, then calls `clearNote`).
    private(set) var note: String?

    @ObservationIgnored var onText: ((String) -> Void)?
    @ObservationIgnored var textProvider: (() -> String)?
    @ObservationIgnored var onKeyboardFallback: (() -> Void)? { didSet { native.onKeyboardFallback = onKeyboardFallback } }

    @ObservationIgnored private var service: (any DictationServing)?
    @ObservationIgnored private var caps: DictationCapabilities?
    @ObservationIgnored private var recorder: AVAudioRecorder?
    @ObservationIgnored private var file: URL?
    @ObservationIgnored private var startedAt = Date()
    @ObservationIgnored private var base = ""
    @ObservationIgnored private var nativeWrote = ""
    @ObservationIgnored private var limitHit = false
    @ObservationIgnored private var limitTask: Task<Void, Never>?
    @ObservationIgnored private var upload: Task<Void, Never>?
    private(set) var isRecording = false

    init() {
        native.onText = { [weak self] text in guard let self else { return }; self.nativeWrote = text; self.onText?(text) }
        native.textProvider = { [weak self] in self?.textProvider?() ?? "" }
    }

    /// What the server offers and the call that sends a clip. Set when the screen appears and whenever the capabilities change.
    func configure(service: (any DictationServing)?, caps: DictationCapabilities?) { self.service = service; self.caps = caps }
    private var useBetter: Bool { service != nil && BetterDictationPreference.uses(caps, preferred: BetterDictationPreference.isOn()) }

    // The surface `CreateView` already uses.
    var state: Dictation.State { isRecording ? .listening : native.state }
    var notice: String? { native.notice }
    var isListening: Bool { isRecording || native.isListening }
    func clearHint() { native.clearHint() }
    func clearNote() { note = nil }

    func toggle(currentText: String) async {
        if isWorking { return }
        if isListening { stop() } else { await start(currentText: currentText) }
    }

    func start(currentText: String) async {
        guard !isListening, !isWorking else { return }
        note = nil; limitHit = false
        base = currentText; nativeWrote = currentText
        guard useBetter, let caps else { await native.start(currentText: currentText); return }
        var mic = Dictation.microphonePermission()
        if mic == .undetermined { mic = await Dictation.requestMicrophone() }
        guard mic == .granted else { await native.start(currentText: currentText); return }      // the native path explains the denied permission

        await native.start(currentText: currentText)        // live preview; it also sets up the audio session
        if !native.isListening {                            // no speech permission or recognizer: record anyway, without a preview
            native.clearHint()
            let session = AVAudioSession.sharedInstance()
            guard (try? session.setCategory(.record, mode: .default, options: .duckOthers)) != nil, (try? session.setActive(true)) != nil else { return }
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("dictation-\(UUID().uuidString).m4a")
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 16_000, AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 32_000, AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue]
        guard let r = try? AVAudioRecorder(url: url, settings: settings), r.record() else { native.stop(); return }   // could not record: the native engine alone carries on
        recorder = r; file = url; startedAt = Date(); isRecording = true
        let limit = caps.maxClipSeconds
        limitTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(limit))
            guard !Task.isCancelled else { return }
            self?.limitHit = true; self?.stop()
        }
    }

    func stop() {
        guard let r = recorder, let url = file else { native.stop(); return }
        limitTask?.cancel(); limitTask = nil
        r.stop(); recorder = nil; file = nil; isRecording = false
        native.stop()
        let seconds = min(Date().timeIntervalSince(startedAt), caps?.maxClipSeconds ?? DictationCapabilities.hardMaxSeconds)
        isWorking = true
        let (base, limit) = (self.base, limitHit)
        upload = Task { [weak self] in
            let result = await Self.send(url: url, seconds: seconds, prompt: base, service: self?.service, maxBytes: self?.caps?.maxClipBytes ?? DictationCapabilities.hardMaxBytes)
            guard let self, !Task.isCancelled else { return }
            self.finish(result, base: base, limitHit: limit)
        }
    }

    /// The text was sent or the screen closed: throw the clip away, upload nothing.
    func cancel() {
        limitTask?.cancel(); limitTask = nil; upload?.cancel(); upload = nil
        if let r = recorder { r.stop() }
        if let file { try? FileManager.default.removeItem(at: file) }
        recorder = nil; file = nil; isRecording = false; isWorking = false
        native.cancel()
    }

    private func finish(_ result: Result<DictationAnswer, BetterDictationFailure>, base: String, limitHit: Bool) {
        isWorking = false; upload = nil
        let r = BetterDictationResolution.resolve(base: base, native: nativeWrote, field: textProvider?() ?? nativeWrote, result: result, limitHit: limitHit)
        if let id = r.id { ids.add(id) }
        if let text = r.write { onText?(text) }
        native.cancel()                                     // a late transcript of the preview must not overwrite the better text
        note = r.noteKey.map { tr($0) }
    }

    func clearIDs() { ids.clear() }

    /// Reads the clip, deletes the file at once (whatever happens), and uploads. Nothing is logged.
    private nonisolated static func send(url: URL, seconds: Double, prompt: String, service: (any DictationServing)?, maxBytes: Int) async -> Result<DictationAnswer, BetterDictationFailure> {
        let data = try? Data(contentsOf: url)
        try? FileManager.default.removeItem(at: url)
        guard let data, !data.isEmpty, data.count <= maxBytes, let service else { return .failure(.failed) }
        return await service.dictate(DictationClip(audio: data, seconds: seconds, languages: [Localization.shared.language.rawValue], prompt: prompt))
    }
}
