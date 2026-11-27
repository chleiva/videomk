import SwiftUI
import VideoMKCore

/// The sheet that opens over Create after the button: the questions one at a time, the summary, or a kind "we can't make this".
/// One look for all of them: the opaque surface, as tall as what it holds, the app's chips and the ONE primary button.
struct CreateStageSheet: View {
    @Bindable var create: CreateModel
    let balance: Int?
    let mediaCount: Int
    let onSubmit: ([String: String]?) -> Void
    let onEdit: () -> Void

    var body: some View {
        FittedSheet {
            switch create.stage {
            case .questions(let flow): QuestionStep(create: create, flow: flow, mediaCount: mediaCount, onSubmit: onSubmit)
            case .summary(let flow, let brief): SummaryStep(create: create, flow: flow, brief: brief, balance: balance, onSubmit: onSubmit, onEdit: onEdit)
            case .notSupported(let m, let s): KindStep(kind: .refused, message: m ?? tr("create.unsupported_fallback"), suggestion: s, retryAfter: nil, onUse: { create.form.text = $0; create.dismissOverlay() }, onClose: { create.dismissOverlay() }, onEdit: onEdit)
            case .blocked(let m): KindStep(kind: .refused, message: m ?? tr("create.unsupported_fallback"), suggestion: nil, retryAfter: nil, onUse: { _ in }, onClose: { create.dismissOverlay() }, onEdit: onEdit)
            case .paused(let m, let t): KindStep(kind: .paused, message: m, suggestion: nil, retryAfter: t, onUse: { _ in }, onClose: { create.dismissOverlay() }, onEdit: onEdit)
            case .form: Color.clear.frame(height: 1)
            }
        }
    }
}

private struct QuestionStep: View {
    @Bindable var create: CreateModel
    let flow: IntakeFlow
    let mediaCount: Int
    let onSubmit: ([String: String]?) -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var picked: String?
    @State private var otherText = ""
    @State private var other = false
    @State private var forward = true
    @FocusState private var otherFocused: Bool

    var body: some View {
        if let q = flow.current {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                header
                content(q).id(flow.index)
                    .transition(reduceMotion ? .identity : .asymmetric(insertion: .offset(x: forward ? 24 : -24).combined(with: .opacity), removal: .opacity))
            }
            .padding(.top, Theme.Space.m)
        }
    }

    /// Back (after the first question), where we are, and "Skip all": one tap starts the video with whatever was answered so far.
    private var header: some View {
        HStack(spacing: Theme.Space.s) {
            if flow.canGoBack {
                IconButton(symbol: "chevron.left", label: tr("create.back"), identifier: "questionBack") { forward = false; withAnimation(reduceMotion ? nil : Theme.Motion.spring) { var f = flow; f.back(); create.stage = .questions(f) } }
            }
            HStack(spacing: 6) { ForEach(0..<flow.questions.count, id: \.self) { i in Capsule().fill(i == flow.index ? Theme.primary : Theme.surface3).frame(width: i == flow.index ? 22 : 8, height: 8) } }
                .frame(minHeight: Theme.minTouch)
                .accessibilityElement().accessibilityLabel(flow.progressText).accessibilityIdentifier("questionProgress")
            Spacer(minLength: Theme.Space.s)
            Button(tr("create.skip_all")) { skipAll() }.buttonStyle(TextButtonStyle()).accessibilityHint(tr("create.skip_all_hint")).accessibilityIdentifier("skipQuestion")
        }
    }

    private func content(_ q: IntakeQuestion) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.l) {
            Text(q.title).textRole(.title).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader).accessibilityIdentifier("questionTitle")
                .accessibilityLabel("\(flow.progressText). \(q.title)")
            if other {
                HStack(spacing: Theme.Space.m) {
                    TextField(tr("create.type_your_answer"), text: $otherText).font(.role(.body)).focused($otherFocused).padding(.horizontal, Theme.Space.l).frame(minHeight: 48).background(Theme.surfaceRaised, in: Capsule())
                        .submitLabel(.done).onSubmit { submitOther() }.accessibilityIdentifier("otherField")
                    Button(tr("common.done")) { submitOther() }.buttonStyle(TextButtonStyle()).disabled(otherText.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            } else {
                let items = q.options.map { opt in Chip(id: opt.id, label: opt.label, symbol: nil, dashed: false) } + (q.allowOther ? [Chip(id: "__other", label: tr("create.other"), symbol: nil, dashed: true)] : []) + [Chip(id: "__decide", label: tr("create.you_decide"), symbol: "sparkle", dashed: false)]
                Group {
                    if typeSize >= .accessibility1 { VStack(spacing: Theme.Space.s) { ForEach(items) { chip($0, q) } } }
                    else { WrapLayout(spacing: Theme.Space.s) { ForEach(items) { chip($0, q) } } }
                }
                .accessibilityElement(children: .contain).accessibilityLabel(tr("create.answers"))
            }
        }
    }

    private struct Chip: Identifiable { let id: String; let label: String; let symbol: String?; let dashed: Bool }

    private func chip(_ c: Chip, _ q: IntakeQuestion) -> some View {
        ChoiceChip(title: c.label, symbol: c.symbol, selected: picked == c.id, dashed: c.dashed, fullWidth: typeSize >= .accessibility1, identifier: "answer-\(c.id)") {
            Haptics.play(.selection)
            if c.id == "__other" { other = true; otherFocused = true; return }
            picked = c.id
            Task {
                try? await Task.sleep(for: .milliseconds(250))
                advance { f in if c.id == "__decide" { f.youDecide() } else if let o = q.options.first(where: { $0.id == c.id }) { f.choose(o) } }
            }
        }
    }

    private func submitOther() {
        let t = otherText
        advance { $0.other(t) }
    }

    /// Every question that is still open is skipped at once. Nothing answered: the video starts. Something answered: the summary shows it first.
    private func skipAll() {
        Haptics.play(.selection)
        advance { f in f.skipRest() }
    }

    private func advance(_ change: (inout IntakeFlow) -> Void) {
        var f = flow
        change(&f)
        picked = nil; other = false; otherText = ""; forward = true
        withAnimation(reduceMotion ? nil : Theme.Motion.spring) {
            if f.isComplete { create.answer(f, mediaCount: mediaCount, submit: onSubmit) } else { create.stage = .questions(f) }
        }
    }
}

private struct SummaryStep: View {
    @Bindable var create: CreateModel
    let flow: IntakeFlow
    let brief: [String: String]?
    let balance: Int?
    let onSubmit: ([String: String]?) -> Void
    let onEdit: () -> Void

    var body: some View {
        let status = ComposerPlan.status(text: create.form.text, balance: balance, options: create.form.options, photos: 0, lengths: create.caps.lengthPresets)
        VStack(alignment: .leading, spacing: Theme.Space.l) {
            SheetHeader(title: tr("create.ready_when_you_are"), closeID: "summaryClose", onClose: onEdit)
            Text(create.form.text).font(.role(.body)).foregroundStyle(Theme.text).lineLimit(4)
                .frame(maxWidth: .infinity, alignment: .leading).padding(Theme.Space.l).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
            WrapLayout(spacing: Theme.Space.s) {
                ForEach(Array(flow.chips(briefSummary: brief?["summary"]).enumerated()), id: \.offset) { _, c in
                    ChoiceChip(title: c.text, selected: false, trailingSymbol: "pencil", spoken: tr("create.summary_chip_a11y", c.text), identifier: "summaryChip") { var f = flow; f.edit(c.questionID); create.stage = .questions(f) }
                }
            }
            if status.isProblem {
                HStack(spacing: Theme.Space.s) {
                    Image(systemName: "exclamationmark.circle").font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.warning).accessibilityHidden(true)
                    Text(status.message).font(.role(.footnote, weight: .medium)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: Theme.Space.xs)
                    if let fix = status.fix, case .useMinutes(let m, _) = fix { FixChip(title: fix.title) { create.form.setMinutes(m) } }
                }
            }
            Button { create.dismissOverlay(); onSubmit(brief) } label: {
                PrimaryLabel(title: tr("create.create_video"), spread: true) {
                    HStack(spacing: 4) { Image(systemName: "bolt.fill").font(.role(.subhead)); Text("\(create.form.options.credits)").monospacedDigit() }.accessibilityHidden(true)
                }
            }
            .buttonStyle(PrimaryButtonStyle()).disabled(!status.canSend)
            .accessibilityLabel(tr("create.create_a11y_credits", tr("credits.count", create.form.options.credits))).accessibilityIdentifier("summaryCreate")
        }
    }
}

/// "We can't make this one" and "Paused": what happened in the title, one honest line, nothing charged, and one action that can actually help.
/// Paused: OK (editing the request cannot lift a pause; the title says when to come back). Refused: Edit request.
struct KindStep: View {
    enum Kind { case refused, paused }
    let kind: Kind
    let message: String?
    let suggestion: String?
    let retryAfter: Int?
    let onUse: (String) -> Void
    let onClose: () -> Void
    let onEdit: () -> Void

    private var title: String {
        switch kind {
        case .refused: tr("create.cant_make_title")
        case .paused: RetryText.short(retryAfter).map { tr("create.paused_title_retry", $0) } ?? tr("create.paused_title")
        }
    }
    /// The server's line, unless it only repeats the title.
    private var shownMessage: String? { KindCopy.message(message, title: title, alsoNot: [tr("create.paused_title"), tr("create.paused_fallback")].filter { _ in kind == .paused }) }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.m) {
            HStack(alignment: .top) {
                Image(systemName: kind == .paused ? "pause.fill" : "exclamationmark.triangle").font(.role(.title, weight: .regular)).foregroundStyle(Theme.warning).frame(width: 56, height: 56).background(Theme.warningContainer, in: Circle()).accessibilityHidden(true)
                Spacer()
                IconButton(symbol: "xmark", label: tr("common.close"), identifier: "kindClose", action: onClose)
            }
            .padding(.top, Theme.Space.xl)
            Text(title).textRole(.title).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader).accessibilityIdentifier("kindTitle")
            if let shownMessage { Text(shownMessage).font(.role(.body)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("kindMessage") }
            if let suggestion, !suggestion.isEmpty {
                VStack(alignment: .leading, spacing: Theme.Space.s) {
                    SectionLabel(tr("create.for_example"))
                    SparkleChip(title: suggestion, identifier: "useSuggestion", hint: tr("create.use_this")) { onUse(suggestion) }
                }
                .padding(.top, Theme.Space.xs)
            }
            Text(tr("create.nothing_was_charged")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).padding(.top, Theme.Space.s).accessibilityIdentifier("nothingCharged")
            if kind == .paused { PrimaryButton(title: tr("common.ok"), identifier: "pausedOK", action: onClose) }
            else { PrimaryButton(title: tr("create.edit_request"), identifier: "editRequest", action: onEdit) }
        }
    }
}

/// Chips that wrap onto as many lines as they need.
/// Wraps its children into rows. A child wider than the row is measured at the container's width, so its text wraps instead of being cut;
/// a child that needs more than half the row takes a row of its own.
struct WrapLayout: Layout {
    var spacing: CGFloat = 8
    private func size(_ v: LayoutSubview, in width: CGFloat) -> CGSize {
        let natural = v.sizeThatFits(.unspecified)
        guard natural.width > width else { return natural }
        let fitted = v.sizeThatFits(ProposedViewSize(width: width, height: nil))
        return CGSize(width: min(width, max(fitted.width, 1)), height: fitted.height)
    }
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 320
        var x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0
        for v in subviews {
            let s = size(v, in: width)
            if x + s.width > width, x > 0 { y += row + spacing; x = 0; row = 0 }
            x += s.width + spacing; row = max(row, s.height)
        }
        return CGSize(width: width, height: y + row)
    }
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, row: CGFloat = 0
        for v in subviews {
            let s = size(v, in: bounds.width)
            if x + s.width > bounds.maxX, x > bounds.minX { y += row + spacing; x = bounds.minX; row = 0 }
            v.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(width: s.width, height: s.height))
            x += s.width + spacing; row = max(row, s.height)
        }
    }
}
