import Foundation

/// What the composer's single status line says, and what it offers to fix. One message at a time, in this priority:
/// too long, not affordable, too short, photo length hint, price. Pure logic: the views only draw it.
public struct ComposerStatus: Equatable, Sendable {
    public enum Kind: Sendable, Equatable { case tooLong, notAffordable, noCredits, tooShort, photoHint, ready, price, dictating, sending, deckWorking, deckProblem, deckShortPrompt }
    public enum Fix: Sendable, Equatable {
        case useMinutes(Double, credits: Int)    // "Use 1 min · ⚡1"
        case addCredits
        public var title: String {
            switch self {
            case .useMinutes(let m, let c): tr("composer.fix.use_minutes", Int(m), c)
            case .addCredits: tr("composer.fix.add_credits")
            }
        }
    }
    public let kind: Kind
    public let message: String
    public let fix: Fix?
    public let canSend: Bool
    /// Not-ready sends read this out and pulse the line.
    public var isProblem: Bool { [.tooLong, .notAffordable, .noCredits, .tooShort, .deckProblem, .deckShortPrompt].contains(kind) }
    /// Spoken when a tonal send is tapped.
    public var announcement: String {
        switch kind {
        case .dictating: tr("composer.announce.dictating")
        case .sending: message
        default: fix.map { tr("composer.announce.fix", message, $0.title.replacingOccurrences(of: "⚡", with: "")) } ?? message
        }
    }
}

/// Where the attached presentation is, as far as the status line cares.
public enum DeckComposer: Sendable, Equatable { case none, working, problem, ready }

public enum ComposerPlan {
    public static func photosTotal(phone: Int, library: Int) -> Int { phone + library }

    public static func credits(forMinutes m: Double, multiplier: Int = 1) -> Int { CreateOptions(minutes: m, creditsMultiplier: multiplier).credits }

    public static func plural(_ n: Int, _ one: String, _ many: String? = nil) -> String { n == 1 ? "\(n) \(one)" : "\(n) \(many ?? one + "s")" }

    /// The longest length the balance allows (never 0 minutes); nil when the balance is 0.
    public static func affordableFix(balance: Int, lengths: [Double] = CreateOptions.lengths, multiplier: Int = 1) -> ComposerStatus.Fix? {
        guard balance > 0 else { return .addCredits }
        let best = lengths.sorted().last { credits(forMinutes: $0, multiplier: multiplier) <= balance }
        return best.map { .useMinutes($0, credits: credits(forMinutes: $0, multiplier: multiplier)) }
    }

    /// The length that shows every photo: the smallest option that is long enough and affordable.
    public static func photoFix(photos: Int, minutes: Double, balance: Int?, lengths: [Double] = CreateOptions.lengths, multiplier: Int = 1) -> ComposerStatus.Fix? {
        let need = PhotoCapacity.minimumMinutes(photos: photos)
        guard let m = lengths.sorted().first(where: { $0 >= need - 1e-9 && $0 > minutes }) else { return nil }
        if let balance, credits(forMinutes: m, multiplier: multiplier) > balance { return nil }
        return .useMinutes(m, credits: credits(forMinutes: m, multiplier: multiplier))
    }

    public static func status(text: String, balance: Int?, options: CreateOptions, photos: Int = 0, dictating: Bool = false, sending: Bool = false, lengths: [Double] = CreateOptions.lengths, deck: DeckComposer = .none) -> ComposerStatus {
        let cost = options.credits
        let count = Brief.normalized(text).count
        let affordable = balance.map { cost <= $0 } ?? true
        let valid = Brief.isValid(text)
        if sending { return ComposerStatus(kind: .sending, message: tr("composer.sending"), fix: nil, canSend: false) }
        if dictating { return ComposerStatus(kind: .dictating, message: tr("composer.listening"), fix: nil, canSend: false) }
        if deck == .working { return ComposerStatus(kind: .deckWorking, message: tr("deck.status.preparing"), fix: nil, canSend: false) }
        if deck == .problem { return ComposerStatus(kind: .deckProblem, message: tr("deck.status.problem"), fix: nil, canSend: false) }
        if count > Brief.maxLength {
            return ComposerStatus(kind: .tooLong, message: tr("composer.too_long", count.formatted(), Brief.maxLength.formatted()), fix: nil, canSend: false)
        }
        if !affordable, let balance {
            if balance <= 0 { return ComposerStatus(kind: .noCredits, message: tr("composer.no_credits"), fix: .addCredits, canSend: false) }
            return ComposerStatus(kind: .notAffordable, message: tr("composer.not_affordable", cost, balance), fix: affordableFix(balance: balance, lengths: lengths, multiplier: options.creditsMultiplier), canSend: false)
        }
        if deck == .ready, count > 0, count < Brief.minLength {      // the server takes no description or one of 10+ characters, never 1 to 9
            return ComposerStatus(kind: .deckShortPrompt, message: tr("deck.prompt_short"), fix: nil, canSend: false)
        }
        if deck == .ready {         // the description is optional (who it is for): empty, or 10 characters or more
            let text = balance.map { tr("composer.ready_left", cost, $0 - cost) } ?? tr("credits.count", cost)
            return ComposerStatus(kind: .ready, message: text, fix: nil, canSend: true)
        }
        if count > 0 && !valid {
            return ComposerStatus(kind: .tooShort, message: tr("composer.too_short", Brief.minLength - count), fix: nil, canSend: false)
        }
        if let hint = PhotoCapacity.hint(photos: photos, minutes: options.minutes, options: lengths) {
            return ComposerStatus(kind: .photoHint, message: hint, fix: photoFix(photos: photos, minutes: options.minutes, balance: balance, lengths: lengths, multiplier: options.creditsMultiplier), canSend: valid)
        }
        if valid {
            let text = balance.map { tr("composer.ready_left", cost, $0 - cost) } ?? tr("credits.count", cost)
            return ComposerStatus(kind: .ready, message: text, fix: nil, canSend: true)
        }
        return ComposerStatus(kind: .price, message: tr("composer.price", Int(options.minutes), tr("credits.count", cost)), fix: nil, canSend: false)
    }
}

/// The photos chosen in the Add photos sheet, across both sources ("This phone" and "My media"), before they are added to the composer.
/// One selection, one limit: switching tabs keeps it, and the length hint counts both.
public struct AttachSelection: Equatable, Sendable {
    public var attached: Int            // photos already in the composer's strip
    public var phone: [String] = []     // identifiers in pick order
    public var library: [String] = []
    public var limit: Int

    public init(attached: Int = 0, phone: [String] = [], library: [String] = [], limit: Int = PhotoLimits.maxPhotos) {
        self.attached = attached; self.phone = phone; self.library = library; self.limit = limit
    }

    public var selected: Int { phone.count + library.count }
    public var total: Int { attached + selected }
    public var isFull: Bool { total >= limit }
    /// How many more phone photos the system picker may still select (it dims the rest at this number).
    public var phoneCap: Int { max(0, limit - attached - library.count) }
    public var libraryCap: Int { max(0, limit - attached - phone.count) }

    /// Toggles a My media photo; false when the limit blocked it.
    @discardableResult public mutating func toggleLibrary(_ id: String) -> Bool {
        if let i = library.firstIndex(of: id) { library.remove(at: i); return true }
        guard !isFull else { return false }
        library.append(id); return true
    }

    /// The system picker owns the phone selection; keep the first ones that fit.
    public mutating func setPhone(_ ids: [String]) { phone = Array(ids.prefix(max(0, limit - attached - library.count))) }

    /// "1", "2", ... on the tile: order within its own source, as the grids show it.
    public func libraryOrder(_ id: String) -> Int? { library.firstIndex(of: id).map { $0 + 1 } }

    public func title() -> String { selected == 0 ? tr("attach.nothing_selected") : tr("attach.selected", selected) }
    public func buttonTitle() -> String { selected == 0 ? tr("attach.add") : tr("attach.add_n", selected) }

    public func subline(minutes: Double) -> String {
        let fit = tr("attach.fit", PhotoCapacity.capacity(minutes: minutes), PhotoCapacity.length(minutes))
        if !phone.isEmpty && !library.isEmpty { return tr("attach.subline_both", phone.count, library.count, fit) }
        if total > 80 { return tr("attach.subline_total", total, limit, fit) }
        return tr("attach.subline_up_to", limit - attached, fit)
    }
}
