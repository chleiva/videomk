import AVFoundation
import Observation
import Speech
import UIKit
import VideoMKCore

/// Speech to text for the brief. Our own recognizer gives live text (on the device when the iPhone supports it). If it can't be used
/// (permission off, no recognizer, no usable microphone) we fall back to the keyboard's built-in dictation, or say how to turn one on.
///
/// How it keeps everything the person says (docs/DICTATION_FIXES_2026-11-28.md): the text in the field when dictation starts is the base; the field is
/// always `base + transcript of the running task`. Apple ends a recognition task after about a minute, after a long silence, or on an error; when that
/// happens the finished transcript is folded into the base and a NEW task starts on the SAME running audio engine (audio arriving in the gap is queued, not lost).
/// Dictation only ends when the person taps Stop, after 5 minutes, after a minute of silence, or when the recognizer keeps failing at once.
/// The rules for text, restarts and language are pure and tested in VideoMKCore (`DictationText`, `DictationRestartPolicy`, `DictationLocaleChoice`).
///
/// IMPORTANT (Swift 6): every callback the system invokes on its own thread (permission replies, the audio tap, the recognizer) is created
/// in a `nonisolated` helper below. A closure written inside this `@MainActor` class is main-actor-isolated, and iOS aborts the app
/// the moment it is called from another thread: that was the crash on the first tap of the microphone.
@MainActor @Observable
final class Dictation: DictationEngine {
    enum State: Equatable { case idle, starting, listening, unavailable(String), keyboardHint(String) }

    private(set) var state: State = .idle
    /// A short line to show while listening (the recognizer does not have the app's language and we are using another). Cleared when dictation ends.
    private(set) var notice: String?
    /// Called with the full text (what was already typed plus what was said) every time the recognizer updates.
    var onText: ((String) -> Void)?
    /// What the text field holds right now. Lets us notice that the person typed while listening, and never overwrite it.
    var textProvider: (() -> String)?
    /// Called when we hand over to the keyboard's own dictation: the screen focuses the text field.
    var onKeyboardFallback: (() -> Void)?

    private let engine = AVAudioEngine()
    private let relay = AudioRelay()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var text = DictationText(startingWith: "")
    private var policy = DictationRestartPolicy()
    private var lastWritten = ""
    private var segment = ""            // transcript of the running task
    private var generation = 0          // results of an older task are ignored
    private var taskHadText = false
    private var gotText = false
    private var onDevice = false
    private var retriedOnServer = false
    private var interrupted = false
    private var rotation: Task<Void, Never>?
    private var recognizer: SFSpeechRecognizer?
    private var observers: [NSObjectProtocol] = []
    private var discarding = false      // after sending: a transcript that arrives late must not write the sent text back into the field

    var isListening: Bool { state == .listening || state == .starting }

    func toggle(currentText: String) async {
        if isListening { stop() } else { await start(currentText: currentText) }
    }

    func start(currentText: String) async {
        guard !isListening else { return }
        discarding = false
        notice = nil
        #if DEBUG
        if ProcessInfo.processInfo.environment["VMK_DEBUG_LISTENING"] == "1" { state = .listening; return }      // screenshots and UI tests: the recording state without a microphone
        #endif
        state = .starting

        // 1. What does the phone allow? Ask for what is still undecided; a denial is not an error, it switches to the fallback.
        var speech = Self.speechPermission()
        var mic = Self.microphonePermission()
        if speech == .undetermined { speech = await Self.requestSpeech() }
        if mic == .undetermined, speech != .denied { mic = await Self.requestMicrophone() }

        // 2. Is there a recognizer for this language? The app's language decides; the phone's languages are only the fallback, and a fallback is said out loud.
        let supported = SFSpeechRecognizer.supportedLocales().map(\.identifier)
        let choice = DictationLocaleChoice.resolve(app: Localization.shared.language, deviceLanguages: Locale.preferredLanguages, region: Locale.current.region?.identifier, supported: supported)
        let recognizer = SFSpeechRecognizer(locale: Locale(identifier: choice.tag)) ?? SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
        let plan = DictationPlan.decide(speech: speech, microphone: mic, recognizerAvailable: recognizer?.isAvailable ?? false, keyboardDictationEnabled: Self.keyboardDictationEnabled)
        switch plan {
        case .blocked(let message): state = .unavailable(message); return
        case .useKeyboard(let message): fallBackToKeyboard(message); return
        case .useApp: break
        }
        guard let recognizer else { return }
        self.recognizer = recognizer
        if choice.fellBack {
            let asked = Localization.shared.language.nativeName
            let using = Locale.current.localizedString(forIdentifier: choice.tag) ?? choice.tag
            notice = tr("dictation.language_fallback", asked, using)
        }
        text = DictationText(startingWith: currentText)
        lastWritten = currentText
        segment = ""
        gotText = false
        retriedOnServer = false
        interrupted = false
        policy = DictationRestartPolicy()
        policy.sessionStarted(now: Self.now)
        onDevice = recognizer.supportsOnDeviceRecognition      // on the device when the language model is there, otherwise Apple's server
        do { try startEngine() } catch {
            teardown()
            Self.keyboardDictationEnabled ? fallBackToKeyboard(tr("dictation.mic_unavailable_keyboard")) : (state = .unavailable(tr("dictation.mic_start_failed")))
            return
        }
        observeSession()
        beginTask()
        state = .listening
    }

    /// The audio engine runs once for the whole dictation; only the recognition tasks come and go.
    private func startEngine() throws {
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .measurement, options: .duckOthers)
        try session.setActive(true, options: .notifyOthersOnDeactivation)
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { throw DictationError.noMicrophone }   // installTap would trap on an empty format (a call in progress, no input route)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format, block: Self.makeTap(for: relay))
        engine.prepare()
        try engine.start()
    }

    /// Starts one recognition task. Audio that arrived while there was none is handed to it first.
    private func beginTask() {
        guard let recognizer else { return }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.requiresOnDeviceRecognition = onDevice
        request.addsPunctuation = true
        request.contextualStrings = ["VideoMK", "Otto"]
        self.request = request
        generation += 1
        segment = ""
        taskHadText = false
        policy.taskStarted(now: Self.now)
        task = recognizer.recognitionTask(with: request, resultHandler: Self.makeResultHandler(for: self, generation: generation))
        relay.attach(request)
        scheduleRotation()
    }

    /// Apple stops a task after about a minute. Ending it ourselves a little earlier, while audio is queued, loses no words.
    private func scheduleRotation() {
        rotation?.cancel()
        let gen = generation
        rotation = Task { [weak self] in
            try? await Task.sleep(for: .seconds(50))
            guard !Task.isCancelled, let self, gen == self.generation, self.state == .listening else { return }
            self.relay.detach()
            self.request?.endAudio()
            try? await Task.sleep(for: .seconds(4))      // the final result normally arrives at once; if it does not, carry on
            guard !Task.isCancelled, gen == self.generation, self.state == .listening else { return }
            self.taskEnded(error: nil)
        }
    }

    func stop() {
        guard state != .idle else { return }
        rotation?.cancel()
        state = .idle
        notice = nil
        relay.detach()
        request?.endAudio()   // lets the recognizer deliver its final result, which still lands in the field
        stopEngine()
    }

    /// Stop and throw away anything still on its way: used when the text has been sent, so the final transcript cannot refill the field with the request just made.
    func cancel() {
        discarding = true
        stop()
    }

    func clearHint() {
        switch state { case .unavailable, .keyboardHint: state = .idle; default: break }
    }

    /// Puts base + transcript in the field. Returns false when the person typed in the field meanwhile (we rebase and start a fresh task instead of overwriting).
    @discardableResult
    private func write(final: Bool) -> Bool {
        guard !discarding else { return true }
        let field = textProvider?() ?? lastWritten
        let step = final ? text.fold(segment, field: field) : text.hear(segment, field: field)
        switch step {
        case .write(let t): lastWritten = t; onText?(t); return true
        case .rebased:
            lastWritten = field
            guard state == .listening else { return false }
            // what was said so far is already in the field the person edited: start again from nothing, on the same audio
            generation += 1
            task?.cancel(); task = nil
            relay.detach()
            beginTask()
            return false
        }
    }

    fileprivate func handle(generation gen: Int, text newText: String?, isFinal: Bool, error: NSError?) {
        guard gen == generation else { return }     // a task we already replaced
        if let newText, !newText.isEmpty, !discarding {
            segment = newText; taskHadText = true; gotText = true
            policy.textArrived(now: Self.now)
            if !write(final: false) { return }
        }
        if error != nil || isFinal { taskEnded(error: error) }
    }

    /// A task ended (final result, the one minute limit, an error, an interruption). Fold it into the base and carry on until the person stops.
    private func taskEnded(error: NSError?) {
        rotation?.cancel()
        if !segment.isEmpty, !write(final: true) { return }     // a hand edit started a new task already
        segment = ""
        guard state == .listening else { task = nil; return }    // the person stopped: the final text has landed
        if interrupted { return }                                  // resumed when the interruption ends
        if let error, !taskHadText {
            let noSpeech = error.code == 1110 || (error.code == 1107 && error.domain.contains("Assistant"))
            switch DictationFailure.classify(domain: error.domain, code: error.code, gotText: false, onDevice: onDevice, dictationEnabled: Self.keyboardDictationEnabled) {
            case .finishQuietly: break
            case .retryOnServer where !retriedOnServer: retriedOnServer = true; onDevice = false
            case .retryOnServer: finish(.unavailable(tr("dictation.stopped", error.domain, String(error.code)))); return
            case .message(let m): if !noSpeech { finish(.unavailable(m)); return }
            }
        }
        switch policy.taskEnded(hadText: taskHadText, now: Self.now) {
        case .restart: task = nil; beginTask()
        case .stopTimeLimit: finish(.idle)
        case .stopIdle: finish(gotText ? .idle : .unavailable(tr("dictation.heard_nothing")))
        case .stopFailing: finish(.unavailable(error.map { tr("dictation.stopped", $0.domain, String($0.code)) } ?? tr("dictation.mic_start_failed")))
        }
    }

    private func finish(_ end: State) {
        teardown()
        notice = nil
        state = end
    }

    private func fallBackToKeyboard(_ message: String) {
        state = .keyboardHint(message)
        onKeyboardFallback?()
    }

    private func stopEngine() {
        if engine.isRunning { engine.stop() }
        engine.inputNode.removeTap(onBus: 0)
        removeObservers()
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }

    private func teardown() {
        rotation?.cancel()
        relay.detach()
        stopEngine()
        generation += 1
        task?.cancel(); task = nil; request = nil
    }

    private enum DictationError: Error { case noMicrophone }

    // MARK: phone calls, Siri, route changes

    private func observeSession() {
        removeObservers()
        let center = NotificationCenter.default
        let me = WeakDictation(self)
        observers.append(center.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main, using: Self.makeInterruptionObserver(me)))
        observers.append(center.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: .main, using: Self.makeConfigObserver(me)))
    }

    private func removeObservers() { observers.forEach(NotificationCenter.default.removeObserver); observers = [] }

    fileprivate func interruption(began: Bool, shouldResume: Bool) {
        guard state == .listening else { return }
        if began {
            interrupted = true
            relay.detach()
            request?.endAudio()          // what was heard so far is folded in when the task ends
        } else if interrupted, shouldResume {
            interrupted = false
            do { try startEngine(); task = nil; beginTask() } catch { finish(.unavailable(tr("dictation.mic_start_failed"))) }
        } else if interrupted {
            finish(.idle)                 // the call took the microphone for good: stop cleanly, the text stays
        }
    }

    fileprivate func routeChanged() {
        guard state == .listening, !interrupted, !engine.isRunning else { return }
        do { try startEngine() } catch { finish(.unavailable(tr("dictation.mic_start_failed"))) }
    }

    nonisolated private static var now: Double { ProcessInfo.processInfo.systemUptime }

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

    nonisolated private static func makeTap(for relay: AudioRelay) -> AVAudioNodeTapBlock {
        return { buffer, _ in relay.append(buffer) }
    }

    nonisolated private static func makeResultHandler(for dictation: Dictation, generation: Int) -> @Sendable (SFSpeechRecognitionResult?, Error?) -> Void {
        let weakBox = WeakDictation(dictation)
        return { result, error in
            let text = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal ?? false
            let failure = error.map { $0 as NSError }
            Task { @MainActor in weakBox.value?.handle(generation: generation, text: text, isFinal: isFinal, error: failure) }
        }
    }

    nonisolated private static func makeInterruptionObserver(_ box: WeakDictation) -> @Sendable (Notification) -> Void {
        return { note in
            let type = (note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt).flatMap(AVAudioSession.InterruptionType.init(rawValue:))
            let options = AVAudioSession.InterruptionOptions(rawValue: (note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt) ?? 0)
            Task { @MainActor in box.value?.interruption(began: type == .began, shouldResume: options.contains(.shouldResume)) }
        }
    }

    nonisolated private static func makeConfigObserver(_ box: WeakDictation) -> @Sendable (Notification) -> Void {
        return { _ in Task { @MainActor in box.value?.routeChanged() } }
    }
}

/// The audio tap runs on a real-time thread and hands buffers to whichever recognition request is current. Between two tasks the buffers wait here
/// (a few seconds at most) and go to the next task first, so a restart loses no words.
private final class AudioRelay: @unchecked Sendable {
    private let lock = NSLock()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var queued: [AVAudioPCMBuffer] = []
    private let limit = 300

    func append(_ buffer: AVAudioPCMBuffer) {
        lock.lock(); defer { lock.unlock() }
        if let request { request.append(buffer) } else { queued.append(buffer); if queued.count > limit { queued.removeFirst() } }
    }

    func attach(_ request: SFSpeechAudioBufferRecognitionRequest) {
        lock.lock(); defer { lock.unlock() }
        self.request = request
        queued.forEach { request.append($0) }
        queued.removeAll()
    }

    func detach() { lock.lock(); request = nil; lock.unlock() }
}

private final class WeakDictation: @unchecked Sendable {
    weak var value: Dictation?
    init(_ d: Dictation) { value = d }
}
