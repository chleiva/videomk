import Observation
import SwiftUI
import VideoMKCore

/// The Create screen's state: the form, what the server offers, and the steps after the button (check, questions, summary, kind answers).
@MainActor @Observable
final class CreateModel {
    enum Stage: Equatable {
        case form
        case checking(slow: Bool)
        case questions(IntakeFlow)
        case summary(IntakeFlow, brief: [String: String]?)
        case notSupported(message: String?, suggestion: String?)
        case blocked(String?)
        case paused(message: String?, retryAfter: Int?)
    }

    var form = CreateForm()
    private(set) var caps = CreateCapabilities.fallback
    var stage: Stage = .form
    var showMore = false
    /// "My holiday in Thailand" opens Add photos straight away, on My media when the library has photos.
    var autoOpenPhotos: AutoOpen?
    struct AutoOpen: Equatable { var library: Bool }
    let photos = PhotoAttachments()
    private let api: (any CreateServing)?
    private(set) var userID: String?
    private var loaded = false
    private var openedMinutes: Double?     // a length chosen when the screen opened (an example's) survives the capabilities arriving

    init(api: (any CreateServing)?) { self.api = api }

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
    func open(prefill: String? = nil, minutes: Double? = nil) {
        stage = .form; showMore = false
        form = CreateDefaults.load(userID: userID).form(caps)
        if let prefill { form.text = prefill }
        openedMinutes = minutes
        if let minutes { form.setMinutes(minutes) }          // an example's length counts as chosen
        #if DEBUG
        if let m = ProcessInfo.processInfo.environment["VMK_DEBUG_DEFAULT_MINUTES"].flatMap(Double.init) { form.minutes = m }
        #endif
    }

    func clearPhotos(library: inout [LibraryPhoto]) { photos.clear(); library = [] }

    var hasEdits: Bool { form.hasContent || !photos.isEmpty }

    // MARK: status

    func totalPhotos(library: Int) -> Int { ComposerPlan.photosTotal(phone: photos.items.count + photos.loading, library: library) }

    /// The bottom status line: price, reason and fix (the photo hint has its own place under the lengths).
    func status(balance: Int?, dictating: Bool, checking: Bool = false) -> ComposerStatus {
        ComposerPlan.status(text: form.text, balance: balance, options: form.options, photos: 0, dictating: dictating, sending: checking, lengths: caps.lengthPresets)
    }

    // MARK: Create

    var checker: CreateChecker? { api.map { CreateChecker(api: $0) } }

    private func request(answers: [IntakeAnswer], mediaCount: Int) -> BriefRequest { BriefRequest(prompt: form.text, options: form.options, mediaCount: mediaCount, answers: answers) }

    /// Taps Create: the request check (skipped when the server has none), then questions, then the video.
    func create(mediaCount: Int, submit: @escaping ([String: String]?) -> Void) {
        guard stage == .form else { return }
        guard caps.intake, let checker else { submit(nil); return }
        stage = .checking(slow: false)
        let req = request(answers: [], mediaCount: mediaCount)
        Task {
            let outcome = await checker.check(req) { Task { @MainActor in if self.stage == .checking(slow: false) { self.stage = .checking(slow: true) } } }
            guard case .checking = stage else { return }                      // cancelled or made it now meanwhile
            switch outcome {
            case .proceed(let brief): stage = .form; submit(brief)
            case .questions(let q): stage = .questions(IntakeFlow(q))
            case .notSupported(let m, let s): stage = .notSupported(message: m, suggestion: s)
            case .blocked(let m): stage = .blocked(m)
            case .paused(let m, let t): stage = .paused(message: m, retryAfter: t)
            }
        }
    }

    /// "Make it now" while the check is still running: stop waiting and go.
    func skipCheck(submit: ([String: String]?) -> Void) { if case .checking = stage { stage = .form; submit(nil) } }
    func cancelCheck() { if case .checking = stage { stage = .form } }

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
        case "checking": stage = .checking(slow: true)
        case "unsupported": stage = .notSupported(message: "This request is outside what videomk can make. Try describing the topic in a different way.", suggestion: "A calm story about a lighthouse keeper")
        case "blocked": stage = .blocked("We can’t make this one. Try describing something different.")
        case "paused": stage = .paused(message: "Creating videos is paused for this account for now.", retryAfter: 3600)
        default: break
        }
    }
    #endif
}
