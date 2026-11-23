import AVFoundation
import Observation
import Speech
import VideoMKCore

/// Speech to text for the brief. Uses on-device recognition when the iPhone supports it, so audio stays on the phone.
@MainActor @Observable
final class Dictation {
    enum State: Equatable { case idle, starting, listening, unavailable(String) }

    private(set) var state: State = .idle
    /// Language being spoken. Remembered; defaults from the phone's preferred languages.
    var language: DictationLanguage = DictationLanguage.initial(saved: UserDefaults.standard.string(forKey: "dictationLanguage"), preferred: Locale.preferredLanguages) {
        didSet { UserDefaults.standard.set(language.rawValue, forKey: "dictationLanguage") }
    }
    /// Called with the full text (what was already typed plus what was said) every time the recognizer updates.
    var onText: ((String) -> Void)?

    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var base = ""

    var isListening: Bool { state == .listening || state == .starting }

    func toggle(currentText: String) async {
        if isListening { stop() } else { await start(currentText: currentText) }
    }

    func start(currentText: String) async {
        guard state != .starting, state != .listening else { return }
        state = .starting
        guard await authorized() else { return }
        let supported = SFSpeechRecognizer.supportedLocales().map(\.identifier)
        let id = language.locale(region: Locale.current.region?.identifier, supported: supported)
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: id)) ?? SFSpeechRecognizer(locale: Locale(identifier: "en-US")), recognizer.isAvailable else {
            state = .unavailable("Dictation isn't available right now.")
            return
        }
        base = currentText.isEmpty || currentText.hasSuffix(" ") ? currentText : currentText + " "
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.requiresOnDeviceRecognition = recognizer.supportsOnDeviceRecognition
        self.request = request

        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.record, mode: .measurement, options: .duckOthers)
            try session.setActive(true, options: .notifyOthersOnDeactivation)
            let input = engine.inputNode
            let box = RequestBox(request)
            input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buffer, _ in box.request.append(buffer) }
            engine.prepare()
            try engine.start()
        } catch {
            teardown()
            state = .unavailable("Couldn't start the microphone.")
            return
        }

        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            let text = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal ?? false
            let failed = error != nil
            Task { @MainActor in self?.handle(text: text, isFinal: isFinal, failed: failed) }
        }
        state = .listening
    }

    func stop() {
        guard state != .idle else { return }
        request?.endAudio()   // lets the recognizer deliver its final result
        teardown(keepTask: true)
        state = .idle
    }

    func clearUnavailable() { if case .unavailable = state { state = .idle } }

    private func handle(text: String?, isFinal: Bool, failed: Bool) {
        if let text { onText?(base + text) }
        if (isFinal || failed) && state != .idle { teardown(); state = .idle }
    }

    private func teardown(keepTask: Bool = false) {
        if engine.isRunning { engine.stop() }
        engine.inputNode.removeTap(onBus: 0)
        if !keepTask { task?.cancel(); task = nil; request = nil }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func authorized() async -> Bool {
        let speech = await withCheckedContinuation { (c: CheckedContinuation<SFSpeechRecognizerAuthorizationStatus, Never>) in
            SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0) }
        }
        guard speech == .authorized else {
            state = .unavailable("Allow speech recognition in Settings to dictate your brief.")
            return false
        }
        guard await AVAudioApplication.requestRecordPermission() else {
            state = .unavailable("Allow microphone access in Settings to dictate your brief.")
            return false
        }
        return true
    }
}

/// The audio tap runs on a real-time thread; the request is only ever appended to from there.
private final class RequestBox: @unchecked Sendable {
    let request: SFSpeechAudioBufferRecognitionRequest
    init(_ r: SFSpeechAudioBufferRecognitionRequest) { request = r }
}
