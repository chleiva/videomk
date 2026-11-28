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

    // Visible feedback (docs/DICTATION_FEEDBACK_2026-11-28.md): the phase machine, the real mic level, the clip kept for Retry.
    private(set) var feedback = VoiceFeedback()
    @ObservationIgnored var debugBetter: Bool?
    private(set) var meter = LevelMeter()
    /// The limit shown in the countdown: the nearer of the clip limit and what is left of today.
    private(set) var limitSeconds: Double = DictationCapabilities.hardMaxSeconds
    @ObservationIgnored private var meterTask: Task<Void, Never>?
    @ObservationIgnored private var pendingClip: (data: Data, seconds: Double)?
    @ObservationIgnored private var attempt = 0
    @ObservationIgnored private var timeoutTask: Task<Void, Never>?
    @ObservationIgnored private var limitFlag = false
    /// Which engine feeds the panel: the paid clip (real level) or the phone's own recognizer (no level: a pulsing mic).
    var engineIsBetter: Bool { debugBetter ?? false || recorder != nil || pendingClip != nil || feedback.phase == .transcribing }
    var showsPanel: Bool { [.recording, .transcribing, .failed].contains(feedback.phase) }
    @ObservationIgnored var announce: ((String) -> Void)?
    private static func nowMs() -> Double { Date().timeIntervalSinceReferenceDate * 1000 }

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
        feedback.apply(.request); meter.reset()
        guard useBetter, let caps else {
            await native.start(currentText: currentText)
            if native.isListening { limitSeconds = 300.0; feedback.apply(.granted(now: Self.nowMs(), limit: 300)); startClock() } else { feedback.apply(.denied) }
            return
        }
        var mic = Dictation.microphonePermission()
        if mic == .undetermined { mic = await Dictation.requestMicrophone() }
        guard mic == .granted else { await native.start(currentText: currentText); feedback.apply(.denied); return }      // the native path explains the denied permission

        await native.start(currentText: currentText)        // live preview; it also sets up the audio session
        if !native.isListening {                            // no speech permission or recognizer: record anyway, without a preview
            native.clearHint()
            let session = AVAudioSession.sharedInstance()
            guard (try? session.setCategory(.record, mode: .default, options: .duckOthers)) != nil, (try? session.setActive(true)) != nil else { feedback.apply(.denied); return }
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("dictation-\(UUID().uuidString).m4a")
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 16_000, AVNumberOfChannelsKey: 1, AVEncoderBitRateKey: 32_000, AVEncoderAudioQualityKey: AVAudioQuality.medium.rawValue]
        guard let r = try? AVAudioRecorder(url: url, settings: settings), r.record() else {   // could not record: the native engine alone carries on (with the native panel)
            if native.isListening { limitSeconds = 300.0; feedback.apply(.granted(now: Self.nowMs(), limit: 300)); startClock() } else { feedback.apply(.denied) }
            return
        }
        r.isMeteringEnabled = true                          // the level comes from the recorder itself: no second microphone consumer
        recorder = r; file = url; startedAt = Date(); isRecording = true
        let limit = DictationFeedback.effectiveLimit(maxClip: Int(caps.maxClipSeconds), secondsLeft: caps.secondsLeft)
        limitSeconds = Double(limit); feedback.apply(.granted(now: Self.nowMs(), limit: limit)); startClock()
        Haptics.play(.selection); announceCurrent()
        limitTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(limit))
            guard !Task.isCancelled else { return }
            self?.limitHit = true; self?.stop()
        }
    }

    func stop() {
        guard let r = recorder, let url = file else { native.stop(); if feedback.phase == .recording { feedback.apply(.cancel); stopClock() }; return }
        limitTask?.cancel(); limitTask = nil
        r.stop(); recorder = nil; file = nil; isRecording = false
        native.stop()
        let seconds = min(Date().timeIntervalSince(startedAt), caps?.maxClipSeconds ?? DictationCapabilities.hardMaxSeconds)
        isWorking = true; limitFlag = limitHit
        feedback.apply(.stop(now: Self.nowMs()))
        // read the clip into memory and delete the file at once (whatever happens); the bytes stay only until the upload ends, or Retry
        let data = try? Data(contentsOf: url); try? FileManager.default.removeItem(at: url)
        guard let data, !data.isEmpty, data.count <= (caps?.maxClipBytes ?? DictationCapabilities.hardMaxBytes), service != nil else { finish(.failure(data == nil || data!.isEmpty ? .failed : .tooLong), base: base, limitHit: limitHit); return }
        pendingClip = (data, seconds)
        Haptics.play(.selection); announceCurrent()
        send()
    }

    /// Sends the kept clip. A hiccup (network, server, 60 s without an answer) shows Retry; other failures end as before.
    private func send() {
        guard let clip = pendingClip else { return }
        attempt += 1; let mine = attempt
        let (base, limit) = (self.base, limitFlag)
        upload?.cancel(); timeoutTask?.cancel()
        timeoutTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(DictationFeedback.timeoutAfter))
            guard !Task.isCancelled, let self, mine == self.attempt, self.feedback.phase == .transcribing else { return }
            self.attempt += 1; self.upload?.cancel(); self.failedRetryable()
        }
        upload = Task { [weak self] in
            let result = await Self.send(data: clip.data, seconds: clip.seconds, prompt: base, service: self?.service)
            guard let self, !Task.isCancelled, mine == self.attempt else { return }
            self.timeoutTask?.cancel()
            if case .failure(let f) = result, f.isRetryable { self.failedRetryable(); return }
            self.finish(result, base: base, limitHit: limit)
        }
    }

    private func failedRetryable() {
        feedback.apply(.fail("network")); Haptics.play(.warning); announceCurrent()
    }
    /// "Retry" on the failed panel: the same clip goes up again.
    func retry() {
        guard feedback.phase == .failed, pendingClip != nil else { return }
        feedback.apply(.retry(now: Self.nowMs())); Haptics.play(.selection); announceCurrent(); send()
    }
    /// "Use iPhone dictation": give up on the clip; the words the phone heard stay and the usual line says so.
    func useDeviceDictation() {
        guard feedback.phase == .failed else { return }
        finish(.failure(.failed), base: base, limitHit: limitFlag)
    }

    /// The person's Cancel. Recording: the clip is thrown away and the field goes back to what it was. Transcribing: stop waiting, the phone's words stay.
    func discard() {
        let wasRecording = recorder != nil
        limitTask?.cancel(); limitTask = nil; timeoutTask?.cancel(); timeoutTask = nil; upload?.cancel(); upload = nil; attempt += 1
        if let r = recorder { r.stop() }
        if let file { try? FileManager.default.removeItem(at: file) }
        recorder = nil; file = nil; pendingClip = nil; isRecording = false; isWorking = false
        native.cancel()
        if wasRecording { onText?(base) }
        feedback.apply(.cancel); stopClock(); announce?(tr("voice.cancelled_a11y"))
    }

    /// The text was sent or the screen closed: throw the clip away, upload nothing.
    func cancel() {
        limitTask?.cancel(); limitTask = nil; upload?.cancel(); upload = nil; timeoutTask?.cancel(); timeoutTask = nil; attempt += 1
        if let r = recorder { r.stop() }
        if let file { try? FileManager.default.removeItem(at: file) }
        recorder = nil; file = nil; pendingClip = nil; isRecording = false; isWorking = false
        native.cancel()
        feedback.apply(.cancel); feedback.apply(.dismiss); stopClock()
    }

    private func finish(_ result: Result<DictationAnswer, BetterDictationFailure>, base: String, limitHit: Bool) {
        isWorking = false; upload = nil; timeoutTask?.cancel(); timeoutTask = nil; pendingClip = nil
        let r = BetterDictationResolution.resolve(base: base, native: nativeWrote, field: textProvider?() ?? nativeWrote, result: result, limitHit: limitHit)
        if let id = r.id { ids.add(id) }
        if let text = r.write { onText?(text) }
        native.cancel()                                     // a late transcript of the preview must not overwrite the better text
        note = r.noteKey.map { tr($0) }
        if r.id != nil {
            feedback.apply(.ok); Haptics.play(.selection); announceCurrent(); inserted = true
            Task { [weak self] in try? await Task.sleep(for: .seconds(1.3)); self?.inserted = false; self?.feedback.apply(.dismiss); self?.stopClock() }
        } else if feedback.phase == .transcribing || feedback.phase == .failed {
            if feedback.phase == .failed { feedback.apply(.dismiss) } else { feedback.apply(.cancel) }
            stopClock()
        }
    }
    /// The inserted text is highlighted for a moment (the screen reads this).
    private(set) var inserted = false
    #if DEBUG
    func debugSet(feedback f: VoiceFeedback, meter m: LevelMeter, better: Bool) { feedback = f; meter = m; debugBetter = better }
    #endif

    // MARK: the clock: level at 25 fps while recording, seconds at 4 Hz while recording or waiting
    private func startClock() {
        meterTask?.cancel()
        meterTask = Task { [weak self] in
            var frame = 0
            while !Task.isCancelled {
                try? await Task.sleep(for: .milliseconds(1000 / DictationFeedback.meterFPS))
                guard let self else { return }
                frame += 1
                if let r = self.recorder { r.updateMeters(); self.meter.push(DictationFeedback.level(fromDecibels: r.averagePower(forChannel: 0))) }
                if frame % (DictationFeedback.meterFPS / 4) == 0 {
                    let before = self.feedback.announcement
                    self.feedback.apply(.tick(now: Self.nowMs()))
                    if self.feedback.announcement != before { self.announceCurrent() }
                }
            }
        }
    }
    private func stopClock() { if feedback.phase == .idle || feedback.phase == .inserted { meterTask?.cancel(); meterTask = nil } }

    private func announceCurrent() {
        let f = feedback
        let text: String?
        switch f.announcement {
        case "listening": text = tr("voice.listening")
        case "warn_soon": text = tr("voice.soon_a11y", f.warning.remaining)
        case "warn_final": text = tr("voice.final_a11y")
        case "transcribing": text = tr("voice.wait_a11y")
        case "slow": text = tr("voice.slow_a11y")
        case "failed": text = tr("voice.failed_a11y")
        case "inserted": text = tr("voice.inserted_a11y")
        default: text = nil
        }
        if let text { announce?(text) }
    }

    func clearIDs() { ids.clear() }

    /// Uploads the clip held in memory. Nothing is logged.
    private nonisolated static func send(data: Data, seconds: Double, prompt: String, service: (any DictationServing)?) async -> Result<DictationAnswer, BetterDictationFailure> {
        guard let service else { return .failure(.failed) }
        return await service.dictate(DictationClip(audio: data, seconds: seconds, languages: [Localization.shared.language.rawValue], prompt: prompt))
    }
}

#if DEBUG
extension BetterDictation {
    /// Screenshots and UI checks without a microphone: `VMK_DEBUG_DICTATION=recording|soon|final|transcribing|slow|failed|native|inserted` shows that state with a fixed, speech-like level history.
    func debugShow(_ name: String) {
        var f = VoiceFeedback(); f.apply(.request)
        let t0 = 1_000_000.0
        func recording(_ elapsed: Double, limit: Int = 360) { f.apply(.granted(now: t0, limit: limit)); f.apply(.tick(now: t0 + elapsed * 1000)) }
        switch name {
        case "recording": recording(47)
        case "soon": recording(335)
        case "final": recording(352)
        case "native": recording(12, limit: 300)
        case "transcribing", "slow", "failed":
            recording(47); f.apply(.stop(now: t0 + 47_000)); f.apply(.tick(now: t0 + 47_000 + (name == "slow" ? 12_000 : 1_000)))
            if name == "failed" { f.apply(.fail("network")) }
        default: return
        }
        var m = LevelMeter()
        for i in 0..<80 { let env = max(0, sin(Double(i) / 5.3) * 0.5 + sin(Double(i) / 1.7) * 0.25 + 0.15); m.push(env * 0.22) }
        debugSet(feedback: f, meter: m, better: name != "native")
    }
}
#endif
