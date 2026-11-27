import Observation
import SwiftUI
import VideoMKCore

/// The Create screen's state: the form, what the server offers, and the steps after the button (check, questions, summary, kind answers).
@MainActor @Observable
final class CreateModel {
    enum Stage: Equatable {
        case form
        case questions(IntakeFlow)
        case summary(IntakeFlow, brief: [String: String]?)
        case notSupported(message: String?, suggestion: String?)
        case blocked(String?)
        case paused(message: String?, retryAfter: Int?)
    }

    var form = CreateForm()
    private(set) var caps = CreateCapabilities.fallback
    var stage: Stage = .form
    /// After the Create tap: the button becomes a live capsule ("Checking your request", then "Starting your video") and the form is locked.
    private(set) var capsule = CreateCapsule()
    /// One line under the button when the video could not be started: the form is back exactly as it was.
    var startError: String?
    /// An example chosen on the home screen: Create types it into the prompt when it opens.
    var typeIn: String?
    var showMore = false
    /// "My holiday in Thailand" opens Add photos straight away, on My media when the library has photos.
    var autoOpenPhotos: AutoOpen?
    struct AutoOpen: Equatable { var library: Bool }
    let photos = PhotoAttachments()
    /// "Add a presentation": the deck being uploaded and read. A video is made from a deck or from photos, never both.
    let deck: DeckJourney
    private let api: (any CreateServing)?
    private(set) var userID: String?
    private var loaded = false
    private var openedMinutes: Double?     // a length chosen when the screen opened (an example's) survives the capabilities arriving

    init(api: (any CreateServing)?, deckUploader: (any DeckUploading)? = nil, deckStore: DeckTempStore = DeckTempStore()) {
        self.api = api
        let fake = api is FakeCreateAPI
        var timing = DeckTiming()
        if fake { timing.intervals = [(.infinity, 0.4)] }
        deck = DeckJourney(api: api as? any DeckServing, uploader: deckUploader ?? (fake ? FakeDeckUploader(Self.fakeScript) : DeckS3Uploader()), store: deckStore, timing: timing)
    }

    /// The fake server's script for the fake upload (debug runs only; production never reads it).
    nonisolated static var fakeScript: FakeDeckScript {
        #if DEBUG
        FakeDeckScript.parse(ProcessInfo.processInfo.environment["VMK_DEBUG_DECK"] ?? "ok")
        #else
        FakeDeckScript()
        #endif
    }

    /// Capabilities from the server; any failure (not deployed yet, offline) falls back to 16:9 and 1080p with no request check.
    func loadCapabilities(userID: String?) async {
        self.userID = userID
        let first = !loaded
        if let api, let c = try? await api.capabilities() { caps = c } else if first { caps = .fallback }
        loaded = true
        // The stored choices are applied once, when the capabilities first arrive. Later loads (each time the screen opens) only keep the form inside
        // what the server lists: a chip the person already tapped is never reset.
        if first, stage == .form, !form.hasContent, !form.userTouched {
            form = CreateDefaults.load(userID: userID).form(caps)
            if let m = openedMinutes { form.minutes = m }
            #if DEBUG
            if let m = ProcessInfo.processInfo.environment["VMK_DEBUG_DEFAULT_MINUTES"].flatMap(Double.init) { form.minutes = m }
            #endif
        } else { form.normalize(caps) }
    }

    /// A fresh Create screen with the last used choices (the prompt and the photos are never remembered).
    /// `platformChip` and `language`: "Make another" on a finished video opens the same sentence with one choice changed (a Short, another language, a shorter cut).
    func open(prefill: String? = nil, minutes: Double? = nil, platformChip: String? = nil, language: String? = nil) {
        stage = .form; showMore = false; capsule.reset(); startError = nil; typeIn = nil; checkRun = nil
        form = CreateDefaults.load(userID: userID).form(caps)
        if let prefill { form.text = prefill }
        if let platformChip, let chip = PlatformChips.make(caps).first(where: { $0.id == platformChip && $0.supported }) { form.select(chip) }
        if let language, caps.languages.contains(where: { $0.id == language }) { form.language = language }
        openedMinutes = minutes
        if let minutes { form.setMinutes(minutes) }          // an example's length counts as chosen
        #if DEBUG
        if let m = ProcessInfo.processInfo.environment["VMK_DEBUG_DEFAULT_MINUTES"].flatMap(Double.init) { form.minutes = m }
        #endif
    }

    func clearPhotos(library: inout [LibraryPhoto]) { photos.clear(); library = [] }

    var hasEdits: Bool { form.hasContent || !photos.isEmpty || deck.isActive }

    // MARK: presentation

    var deckAvailable: Bool { caps.deck != nil }

    /// A file from the Files app: any photos are dropped (the caller confirmed), 16:9 becomes the default, and the upload journey starts.
    func pickDeck(_ url: URL) {
        guard let d = caps.deck else { return }
        photos.clear()
        form.startDeck(caps)
        deck.pick(url, caps: d)
    }

    /// A file that could not even be read: shown as a problem card like any other.
    func rejectDeck(name: String, problem: DeckProblem) { photos.clear(); form.startDeck(caps); deck.reject(name: name, problem: problem) }

    func removeDeck() { deck.discard(); form.clearDeck() }

    /// Keeps the form in step with the journey: the deck's own length and price once it is ready.
    func syncDeck() {
        switch deck.state {
        case .ready(let r): form.deckReady(r.price)
        case .idle: if form.hasDeck { form.clearDeck() }
        default: break
        }
    }

    var deckComposer: DeckComposer {
        switch deck.state {
        case .idle: .none
        case .uploading, .processing: .working
        case .failed: .problem
        case .ready: .ready
        }
    }

    /// The price line of the ready card: "4 credits for about 4 minutes", for the length chosen now.
    var deckCostText: String { tr("deck.cost", tr("credits.count", form.options.credits), LengthLabel.spoken(form.minutes)) }

    // MARK: status

    func totalPhotos(library: Int) -> Int { ComposerPlan.photosTotal(phone: photos.items.count + photos.loading, library: library) }

    /// The bottom status line: price, reason and fix (the photo hint has its own place under the lengths).
    func status(balance: Int?, dictating: Bool) -> ComposerStatus {
        ComposerPlan.status(text: form.text, balance: balance, options: form.options, photos: 0, dictating: dictating, sending: capsule.isLocked, lengths: caps.lengthPresets, deck: deckComposer)
    }

    // MARK: Create

    @ObservationIgnored private var checkRun: UUID?               // which request check may still answer

    var checker: CreateChecker? { api.map { CreateChecker(api: $0) } }

    private func request(answers: [IntakeAnswer], mediaCount: Int) -> BriefRequest { BriefRequest(prompt: form.text, options: form.options, mediaCount: mediaCount, answers: answers) }

    /// Taps Create: the form locks at once and the button becomes the capsule. The request check runs (skipped when the server has none), then it ends in
    /// exactly one of: questions, a kind refusal, the start of the video (`submit`), or, on Cancel, the form as it was.
    func create(mediaCount: Int, submit: @escaping ([String: String]?) -> Void) {
        guard stage == .form, !capsule.isLocked else { return }
        startError = nil
        let needsCheck = caps.intake && !form.hasDeck && checker != nil       // a presentation skips the request check: its prompt is only a tone hint
        capsule.handle(.tapCreate(needsCheck: needsCheck))
        guard needsCheck, let checker else { submit(nil); return }
        let req = request(answers: [], mediaCount: mediaCount)
        let run = UUID(); checkRun = run                                      // a cancelled call's late answer must never start a video
        Task {
            let outcome = await checker.check(req) { Task { @MainActor in if self.checkRun == run { self.capsule.handle(.slow) } } }
            guard checkRun == run, capsule.canCancel else { return }          // cancelled meanwhile
            checkRun = nil
            switch outcome {
            case .proceed(let brief): capsule.handle(.checkPassed); submit(brief)
            case .questions(let q): capsule.handle(.needsQuestions); stage = .questions(IntakeFlow(q))
            case .notSupported(let m, let s): capsule.handle(.refused); stage = .notSupported(message: m, suggestion: s)
            case .blocked(let m): capsule.handle(.refused); stage = .blocked(m)
            case .paused(let m, let t): capsule.handle(.refused); stage = .paused(message: m, retryAfter: t)
            }
        }
    }

    /// Cancel while the request is checked: the call is dropped (a late answer starts nothing) and the form is back exactly as it was.
    func cancelCheck() { checkRun = nil; capsule.handle(.cancel) }

    /// The questions were answered or skipped (or there was nothing to check): the capsule says "Starting your video". False when it is already starting.
    func beginStart() -> Bool { capsule.handle(.confirmed); return capsule.phase == .starting && capsule.ending == nil }
    /// The server took the video (or the list took over while photos upload): the screen closes onto the Making card.
    func started() { capsule.handle(.started) }
    /// The start did not work: everything is given back, with one line saying what happened.
    func startFailed(_ message: String) { capsule.handle(.failed); startError = message }
    /// The start was refused (the safety check, or a pause): the kind sheet explains; the form stays as it was underneath.
    func startRefused(message: String?, paused: Bool, retryAfter: Int?) {
        capsule.handle(.refused)
        stage = paused ? .paused(message: message, retryAfter: retryAfter) : .blocked(message)
    }

    // MARK: questions

    func answer(_ f: IntakeFlow, mediaCount: Int, submit: @escaping ([String: String]?) -> Void) {
        guard f.isComplete else { stage = .questions(f); return }
        guard f.needsSummary else { stage = .form; submit(nil); return }             // everything skipped: nothing to confirm
        stage = .summary(f, brief: Self.localBrief(f))
        guard caps.intake, let checker else { return }
        let req = request(answers: f.payload, mediaCount: mediaCount)
        Task {                                                                         // the server's own brief (and its words for the chips)
            if case .proceed(let brief?) = await checker.check(req), case .summary(let cur, _) = stage, cur == f { stage = .summary(f, brief: brief) }
        }
    }

    /// What goes in `brief` when the server did not send one: the answers, one short string each.
    static func localBrief(_ f: IntakeFlow) -> [String: String] {
        var out: [String: String] = [:]
        for a in f.realAnswers { out[a.id] = a.option ?? a.text ?? "" }
        out["summary"] = f.realAnswers.compactMap { $0.label ?? $0.text }.joined(separator: " · ")
        return out
    }

    func dismissOverlay() { stage = .form }

    // MARK: after Create

    func remember() { CreateDefaults(form).save(userID: userID) }

    #if DEBUG
    /// Screenshots: `VMK_DEBUG_CREATE=linkedin|x|shorts|overmax|shortphotos` picks that platform / length the way a tap would.
    func debugPick(_ name: String) {
        func pick(_ id: String) { if let c = PlatformChips.make(caps).first(where: { $0.members.contains(id) }) { form.select(c) } }
        switch name {
        case "linkedin": pick("linkedin")
        case "x": pick("x")
        case "shorts": pick("shorts")
        case "overmax": pick("x"); form.setMinutes(3)
        case "shortphotos": form.setMinutes(0.25)
        case "4k": pick("youtube"); form.setResolution("2160p"); showMore = true        // YouTube at 4K: the chip, its mark and the note, price doubled
        case "4ktiktok": pick("shorts"); form.setResolution("2160p")                    // 4K where it is not delivered: the recommendation and "Use 1080p"
        case "4klinkedin": pick("linkedin"); form.setResolution("2160p"); showMore = true
        case "4koff": pick("youtube"); showMore = true                                 // 4K listed but not chosen
        case "4ksummary": pick("youtube"); form.setResolution("2160p")
        default: break
        }
    }

    /// `VMK_DEBUG_DECK_FILE=Quarterly review.pptx[:megabytes]` picks that file the way the Files app would (a sparse file of that size, never any content).
    /// Needs `VMK_DEBUG_FAKE_LIBRARY=1`, `VMK_DEBUG_DECK=<script>` and `VMK_DEBUG_CREATE=<state>`.
    func debugPickDeck(_ spec: String) {
        let parts = spec.split(separator: ":", maxSplits: 1).map(String.init)
        guard let name = parts.first, !name.isEmpty else { return }
        let mb = parts.count > 1 ? Int(parts[1]) ?? 3 : 3
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("VMKDebugDecks", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent(name)
        FileManager.default.createFile(atPath: url.path, contents: Data("debug".utf8))
        if let h = try? FileHandle(forWritingTo: url) { try? h.truncate(atOffset: UInt64(mb) * 1024 * 1024); try? h.close() }
        if caps.deck == nil { return }
        pickDeck(url)
    }

    func debugStage(_ name: String) {
        let q = [IntakeQuestion(id: "audience", title: "Who is this for?", helper: "Helps us pick the right words and pace.", options: ["Kids", "Beginners", "Experts", "Everyone"].map { IntakeOption(id: $0.lowercased(), label: $0) }),
                 IntakeQuestion(id: "tone", title: "What tone?", helper: "One word is enough.", options: ["Calm", "Energetic", "Funny", "Serious"].map { IntakeOption(id: $0.lowercased(), label: $0) }),
                 IntakeQuestion(id: "focus", title: "What should it focus on?", helper: "Pick the part you care about most.", options: ["Making honey", "Life in the hive", "Pollination", "Fun facts"].map { IntakeOption(id: $0.lowercased(), label: $0) })]
        switch name {
        case "longlabels":      // the server's longest labels (36+ characters), in Spanish and English, in one question and in the summary
            let long = [IntakeQuestion(id: "focus", title: "¿Qué parte de la historia quieres destacar?", helper: "Elige la que más te interesa.", options: ["Evolución biológica y primeros homínidos", "Civilizaciones antiguas hasta la edad media", "From the first farms to the first cities and empires", "Arte", "Guerras"].map { IntakeOption(id: $0.lowercased(), label: $0) }, allowOther: true)]
            stage = .questions(IntakeFlow(long))
        case "longsummary":
            let long = [IntakeQuestion(id: "focus", title: "¿Qué parte?", helper: nil, options: ["Evolución biológica y primeros homínidos"].map { IntakeOption(id: $0.lowercased(), label: $0) }),
                        IntakeQuestion(id: "tone", title: "¿Tono?", helper: nil, options: ["Civilizaciones antiguas hasta la edad media"].map { IntakeOption(id: $0.lowercased(), label: $0) })]
            var f = IntakeFlow(long); f.choose(long[0].options[0]); f.choose(long[1].options[0])
            stage = .summary(f, brief: nil)
        case "q1": stage = .questions(IntakeFlow(q))
        case "q2": var f = IntakeFlow(q); f.choose(q[0].options[0]); stage = .questions(f)
        case "summary", "4ksummary":
            var f = IntakeFlow(q); f.choose(q[0].options[0]); f.choose(q[1].options[0]); f.choose(q[2].options[0])
            stage = .summary(f, brief: ["summary": "For kids · Calm · Focus: Making honey"])
        case "checking": capsule.handle(.tapCreate(needsCheck: true)); capsule.handle(.slow)      // a check that takes longer: the capsule says so
        case "checkingfast": capsule.handle(.tapCreate(needsCheck: true))                         // the first moments: the form is locked, the capsule says what happens
        case "starting": capsule.handle(.tapCreate(needsCheck: false))
        case "startfailed": startError = APIError.network.message
        case "unsupported": stage = .notSupported(message: "This request is outside what videomk can make. Try describing the topic in a different way.", suggestion: "A calm story about a lighthouse keeper")
        case "blocked": stage = .blocked("We can’t make this one. Try describing something different.")
        case "paused": stage = .paused(message: "Creating videos is paused for this account for now.", retryAfter: 3600)
        default: break
        }
    }
    #endif
}
