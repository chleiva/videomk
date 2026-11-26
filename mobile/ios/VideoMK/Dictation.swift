import AVFoundation
import Observation
import Speech
import UIKit
import VideoMKCore

/// Speech to text for the brief. Our own recognizer gives live text (on the device when the iPhone supports it). If it can't be used
/// (permission off, no recognizer, no usable microphone) we fall back to the keyboard's built-in dictation, or say how to turn one on.
///
/// IMPORTANT (Swift 6): every callback the system invokes on its own thread (permission replies, the audio tap, the recognizer) is created
/// in a `nonisolated` helper below. A closure written inside this `@MainActor` class is main-actor-isolated, and iOS aborts the app
/// the moment it is called from another thread: that was the crash on the first tap of the microphone.
@MainActor @Observable
final class Dictation {
    enum State: Equatable { case idle, starting, listening, unavailable(String), keyboardHint(String) }

    private(set) var state: State = .idle
    /// No language menu: dictation follows the phone's first preferred language we support (English or Spanish).
    private var language: DictationLanguage { DictationLanguage.initial(saved: nil, preferred: Locale.preferredLanguages) }
    /// Called with the full text (what was already typed plus what was said) every time the recognizer updates.
    var onText: ((String) -> Void)?
    /// Called when we hand over to the keyboard's own dictation: the screen focuses the text field.
    var onKeyboardFallback: (() -> Void)?

    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var base = ""
    private var gotText = false
    private var onDevice = false
    private var retriedOnServer = false
    private var recognizer: SFSpeechRecognizer?
    private var discarding = false      // after sending: a transcript that arrives late must not write the sent text back into the field

    var isListening: Bool { state == .listening || state == .starting }

    func toggle(currentText: String) async {
        if isListening { stop() } else { await start(currentText: currentText) }
    }

    func start(currentText: String) async {
        guard !isListening else { return }
        discarding = false
        state = .starting

        // 1. What does the phone allow? Ask for what is still undecided; a denial is not an error, it switches to the fallback.
        var speech = Self.speechPermission()
        var mic = Self.microphonePermission()
        if speech == .undetermined { speech = await Self.requestSpeech() }
        if mic == .undetermined, speech != .denied { mic = await Self.requestMicrophone() }

        // 2. Is there a recognizer for this language?
        let supported = SFSpeechRecognizer.supportedLocales().map(\.identifier)
        let id = language.locale(region: Locale.current.region?.identifier, supported: supported)
        let recognizer = SFSpeechRecognizer(locale: Locale(identifier: id)) ?? SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
        let plan = DictationPlan.decide(speech: speech, microphone: mic, recognizerAvailable: recognizer?.isAvailable ?? false, keyboardDictationEnabled: Self.keyboardDictationEnabled)
        switch plan {
        case .blocked(let message): state = .unavailable(message); return
        case .useKeyboard(let message): fallBackToKeyboard(message); return
        case .useApp: break
        }
        guard let recognizer else { return }
        self.recognizer = recognizer
        base = currentText.isEmpty || currentText.hasSuffix(" ") ? currentText : currentText + " "
        gotText = false
        retriedOnServer = false
        listen(onDevice: recognizer.supportsOnDeviceRecognition)
    }

    /// Anything that goes wrong here ends in a message or the keyboard fallback, never in a crash or in silence.
    private func listen(onDevice wantOnDevice: Bool) {
        guard let recognizer else { return }
        onDevice = wantOnDevice
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.requiresOnDeviceRecognition = wantOnDevice
        self.request = request
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true, options: .notifyOthersOnDeactivation)
            let input = engine.inputNode
            let format = input.outputFormat(forBus: 0)
            guard format.sampleRate > 0, format.channelCount > 0 else { throw DictationError.noMicrophone }   // installTap would trap on an empty format (a call in progress, no input route)
            input.removeTap(onBus: 0)
            input.installTap(onBus: 0, bufferSize: 1024, format: format, block: Self.makeTap(for: request))
            engine.prepare()
            try engine.start()
        } catch {
            teardown()
            Self.keyboardDictationEnabled ? fallBackToKeyboard(tr("dictation.mic_unavailable_keyboard")) : (state = .unavailable(tr("dictation.mic_start_failed")))
            return
        }
        task = recognizer.recognitionTask(with: request, resultHandler: Self.makeResultHandler(for: self))
        state = .listening
    }

    func stop() {
        guard state != .idle else { return }
        request?.endAudio()   // lets the recognizer deliver its final result
        teardown(keepTask: true)
        state = .idle
    }

    /// Stop and throw away anything still on its way: used when the text has been sent, so the final transcript cannot refill the field with the request just made.
    func cancel() {
        discarding = true
        stop()
    }

    func clearHint() {
        switch state { case .unavailable, .keyboardHint: state = .idle; default: break }
    }

    fileprivate func handle(text: String?, isFinal: Bool, error: NSError?) {
        if let text, !text.isEmpty, !discarding { gotText = true; onText?(base + text) }   // the final text of a phrase we just stopped still lands (unless it was cancelled)
        guard state != .idle else { return }
        if let error {
            switch DictationFailure.classify(domain: error.domain, code: error.code, gotText: gotText, onDevice: onDevice, dictationEnabled: Self.keyboardDictationEnabled) {
            case .finishQuietly: teardown(); state = .idle
            case .retryOnServer where !retriedOnServer:
                retriedOnServer = true
                teardown()
                listen(onDevice: false)
            case .retryOnServer: teardown(); state = .unavailable(tr("dictation.stopped", error.domain, String(error.code)))
            case .message(let m): teardown(); state = .unavailable(m)
            }
        } else if isFinal {
            teardown(); state = .idle
        }
    }

    private func fallBackToKeyboard(_ message: String) {
        state = .keyboardHint(message)
        onKeyboardFallback?()
    }

    private func teardown(keepTask: Bool = false) {
        if engine.isRunning { engine.stop() }
        engine.inputNode.removeTap(onBus: 0)
        if !keepTask { task?.cancel(); task = nil; request = nil }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private enum DictationError: Error { case noMicrophone }

    // MARK: system state (nonisolated: safe to call from anywhere)

    /// True when the keyboard's own dictation key is available (Settings › General › Keyboard › Enable Dictation).
    static var keyboardDictationEnabled: Bool { UITextInputMode.activeInputModes.contains { $0.primaryLanguage == "dictation" } }

    nonisolated static func speechPermission() -> DictationPlan.Permission {
        switch SFSpeechRecognizer.authorizationStatus() { case .authorized: .granted; case .notDetermined: .undetermined; default: .denied }
    }

    nonisolated static func microphonePermission() -> DictationPlan.Permission {
        switch AVAudioApplication.shared.recordPermission { case .granted: .granted; case .undetermined: .undetermined; default: .denied }
    }

    nonisolated static func requestSpeech() async -> DictationPlan.Permission {
        await withCheckedContinuation { (c: CheckedContinuation<DictationPlan.Permission, Never>) in
            SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0 == .authorized ? .granted : .denied) }
        }
    }

    nonisolated static func requestMicrophone() async -> DictationPlan.Permission {
        await withCheckedContinuation { (c: CheckedContinuation<DictationPlan.Permission, Never>) in
            AVAudioApplication.requestRecordPermission { c.resume(returning: $0 ? .granted : .denied) }
        }
    }

    // MARK: callbacks the system runs on its own threads (must be built outside the main actor)

    nonisolated private static func makeTap(for request: SFSpeechAudioBufferRecognitionRequest) -> AVAudioNodeTapBlock {
        let box = RequestBox(request)
        return { buffer, _ in box.request.append(buffer) }
    }

    nonisolated private static func makeResultHandler(for dictation: Dictation) -> @Sendable (SFSpeechRecognitionResult?, Error?) -> Void {
        let weakBox = WeakDictation(dictation)
        return { result, error in
            let text = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal ?? false
            let failure = error.map { $0 as NSError }
            Task { @MainActor in weakBox.value?.handle(text: text, isFinal: isFinal, error: failure) }
        }
    }
}

/// The audio tap runs on a real-time thread; the request is only ever appended to from there.
private final class RequestBox: @unchecked Sendable {
    let request: SFSpeechAudioBufferRecognitionRequest
    init(_ r: SFSpeechAudioBufferRecognitionRequest) { request = r }
}

private final class WeakDictation: @unchecked Sendable {
    weak var value: Dictation?
    init(_ d: Dictation) { value = d }
}
