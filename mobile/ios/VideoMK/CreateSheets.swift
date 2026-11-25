import SwiftUI
import VideoMKCore

/// The sheet that opens over Create after the button: the request check, the questions one at a time, the summary, or a kind "we can't make this".
struct CreateStageSheet: View {
    @Bindable var create: CreateModel
    let balance: Int?
    let mediaCount: Int
    let onSubmit: ([String: String]?) -> Void
    let onEdit: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        Group {
            switch create.stage {
            case .checking: skeleton
            case .questions(let flow): QuestionStep(create: create, flow: flow, mediaCount: mediaCount, onSubmit: onSubmit)
            case .summary(let flow, let brief): SummaryStep(create: create, flow: flow, brief: brief, balance: balance, onSubmit: onSubmit, onEdit: onEdit)
            case .notSupported(let m, let s): KindStep(title: "We can’t make this one", message: m ?? "This request is outside what videomk can make. Try describing the topic in a different way.", suggestion: s, retry: nil, create: create, onEdit: onEdit)
            case .blocked(let m): KindStep(title: "We can’t make this one", message: m ?? "This request is outside what videomk can make. Try describing the topic in a different way.", suggestion: nil, retry: nil, create: create, onEdit: onEdit)
            case .paused(let m, let t): KindStep(title: "Creating videos is paused", message: m ?? "Creating videos is paused for this account for now.", suggestion: nil, retry: RetryText.make(t), create: create, onEdit: onEdit)
            case .form: Color.clear
            }
        }
        .presentationBackground(Theme.surface)
        .presentationDetents(typeSize.isAccessibilitySize ? [.large] : [.height(470), .height(640), .large], selection: $detent)
        .onChange(of: create.stage, initial: true) { _, _ in detent = typeSize.isAccessibilitySize || hasLongLabels ? .large : .height(isSummary ? 640 : 470) }
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(isChecking)
    }

    @State private var detent: PresentationDetent = .height(470)
    /// Long answers wrap onto two lines, so the sheet opens at full height instead of hiding the buttons below them.
    private var hasLongLabels: Bool {
        let longest: Int
        switch create.stage {
        case .questions(let f): longest = f.current?.options.map(\.label.count).max() ?? 0
        case .summary(let f, let b): longest = f.chips(briefSummary: b?["summary"]).map(\.text.count).max() ?? 0
        default: longest = 0
        }
        return longest > 24
    }

    private var isSummary: Bool { if case .summary = create.stage { true } else { false } }
    private var isChecking: Bool { if case .checking = create.stage { true } else { false } }

    private var skeleton: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack { Spacer(); Button("Make it now") { create.skipCheck(submit: onSubmit) }.font(.system(size: 17, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("makeItNow") }
            RoundedRectangle(cornerRadius: 8).fill(Theme.surfaceRaised).frame(width: 220, height: 28)
            RoundedRectangle(cornerRadius: 8).fill(Theme.surfaceRaised).frame(width: 150, height: 16)
            HStack(spacing: 10) { ForEach(0..<3, id: \.self) { _ in Capsule().fill(Theme.surfaceRaised).frame(height: 50) } }
            Text("Checking your request…").font(.system(size: 15)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("checkingText")
            Spacer()
        }
        .padding(.horizontal, 20).padding(.top, 12)
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
        guard let q = flow.current else { return AnyView(EmptyView()) }
        return AnyView(
            VStack(alignment: .leading, spacing: 0) {
                header
                ScrollView {
                    content(q).id(flow.index)
                        .transition(reduceMotion ? .identity : .asymmetric(insertion: .offset(x: forward ? 24 : -24).combined(with: .opacity), removal: .opacity))
                }.scrollBounceBehavior(.basedOnSize).scrollIndicators(.hidden)
                Spacer(minLength: 0)
                HStack { Spacer(); Button("Skip") { advance { $0.skip() } }.font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(minHeight: 44).accessibilityIdentifier("skipQuestion"); Spacer() }
            }
            .padding(.horizontal, 20).padding(.top, 10).padding(.bottom, 6)
        )
    }

    private var header: some View {
        HStack {
            if flow.canGoBack { Button { forward = false; withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.28)) { var f = flow; f.back(); create.stage = .questions(f) } } label: { Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold)).frame(width: 44, height: 44) }.accessibilityLabel("Back") }
            else { Spacer().frame(width: 44) }
            Spacer()
            HStack(spacing: 6) { ForEach(0..<flow.questions.count, id: \.self) { i in Capsule().fill(i == flow.index ? Theme.primary : Theme.surface3).frame(width: i == flow.index ? 22 : 8, height: 8) } }.accessibilityHidden(true)
            Spacer()
            Button("Make it now") { var f = flow; f.makeItNow(); create.answer(f, mediaCount: mediaCount, submit: onSubmit) }.font(.system(size: 17, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("makeItNow")
        }
    }

    private func content(_ q: IntakeQuestion) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(flow.progressText.uppercased()).font(.system(size: 13, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary).padding(.top, 14)
            Text(q.title).font(.system(size: 27, weight: .bold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, 6).accessibilityAddTraits(.isHeader).accessibilityIdentifier("questionTitle")
            if let h = q.helper { Text(h).font(.system(size: 15)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).padding(.top, 4) }
            if other {
                HStack(spacing: 10) {
                    TextField("Type your answer", text: $otherText).focused($otherFocused).padding(.horizontal, 14).frame(height: 50).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.primary, lineWidth: 2)).submitLabel(.done).onSubmit { submitOther() }.accessibilityIdentifier("otherField")
                    Button("Done") { submitOther() }.font(.system(size: 17, weight: .semibold)).frame(minHeight: 44).disabled(otherText.trimmingCharacters(in: .whitespaces).isEmpty)
                }.padding(.top, 18)
            } else {
                let items = q.options.map { opt in Chip(id: opt.id, label: opt.label, symbol: nil, dashed: false) } + (q.allowOther ? [Chip(id: "__other", label: "Other…", symbol: nil, dashed: true)] : []) + [Chip(id: "__decide", label: "You decide", symbol: "sparkles", dashed: false)]
                Group {
                    if typeSize >= .accessibility1 { VStack(spacing: 10) { ForEach(items) { chip($0, q) } } }
                    else { WrapLayout(spacing: 10) { ForEach(items) { chip($0, q) } } }
                }.padding(.top, 18).accessibilityElement(children: .contain).accessibilityLabel("Answers")
            }
        }
    }

    private struct Chip: Identifiable { let id: String; let label: String; let symbol: String?; let dashed: Bool }

    private func chip(_ c: Chip, _ q: IntakeQuestion) -> some View {
        let selected = picked == c.id
        return Button {
            UISelectionFeedbackGenerator().selectionChanged()
            if c.id == "__other" { other = true; otherFocused = true; return }
            picked = c.id
            Task {
                try? await Task.sleep(for: .milliseconds(250))
                advance { f in if c.id == "__decide" { f.youDecide() } else if let o = q.options.first(where: { $0.id == c.id }) { f.choose(o) } }
            }
        } label: {
            HStack(spacing: 8) {
                if let s = c.symbol { Image(systemName: s).font(.system(size: 15)) }
                Text(c.label).font(.system(size: 17, weight: .semibold)).multilineTextAlignment(.leading).lineLimit(nil).fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(c.dashed ? Theme.textSecondary : selected ? Theme.primary : Theme.text).padding(.horizontal, 20).padding(.vertical, 12)
            .frame(maxWidth: typeSize >= .accessibility1 ? .infinity : nil, minHeight: 50, alignment: .leading)
            .background(selected ? Theme.primaryContainer : (c.dashed ? .clear : Theme.surfaceRaised), in: RoundedRectangle(cornerRadius: 25, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 25, style: .continuous).stroke(selected ? Theme.primary : Theme.outline, style: StrokeStyle(lineWidth: selected ? 2 : 1.5, dash: c.dashed ? [4, 4] : [])))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(c.label).accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("answer-\(c.id)")
    }

    private func submitOther() {
        let t = otherText
        advance { $0.other(t) }
    }

    private func advance(_ change: (inout IntakeFlow) -> Void) {
        var f = flow
        change(&f)
        picked = nil; other = false; otherText = ""; forward = true
        withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.28)) {
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
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        let status = ComposerPlan.status(text: create.form.text, balance: balance, options: create.form.options, photos: 0, lengths: create.caps.lengthPresets)
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Ready when you are").font(.system(size: 23, weight: .bold)).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("Close") { create.dismissOverlay() }.font(.system(size: 17, weight: .medium)).foregroundStyle(Theme.textSecondary).frame(minHeight: 44)
            }.padding(.top, 18)
            VStack(alignment: .leading, spacing: 4) {
                Text("YOUR REQUEST").font(.system(size: 12.5, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary)
                Text(create.form.text).font(.system(size: 17)).foregroundStyle(Theme.text).lineLimit(3)
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(16).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 20, style: .continuous)).padding(.top, 10)
            WrapLayout(spacing: 10) {
                ForEach(Array(flow.chips(briefSummary: brief?["summary"]).enumerated()), id: \.offset) { _, c in
                    Button { var f = flow; f.edit(c.questionID); create.stage = .questions(f) } label: {
                        HStack(spacing: 6) { Text(c.text).font(.system(size: 17, weight: .semibold)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true); Image(systemName: "pencil").font(.system(size: 13)) }
                            .foregroundStyle(Theme.primary).padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 44).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                    }.buttonStyle(.plain).accessibilityLabel("\(c.text). Double tap to change.").accessibilityIdentifier("summaryChip")
                }
            }.padding(.top, 14)
            Text("Tap an answer to change it.").font(.system(size: 14)).foregroundStyle(Theme.textSecondary).padding(.top, 8)
            Divider().padding(.vertical, 12)
            HStack(spacing: 8) { Image(systemName: create.form.aspect == "16:9" ? "rectangle" : "rectangle.portrait").font(.system(size: 14)); Text("\(create.form.recommendation(create.caps)) · \(LengthLabel.chip(create.form.minutes))").font(.system(size: 15)).lineLimit(2) }.foregroundStyle(Theme.textSecondary)
            Spacer(minLength: 8)
            HStack(spacing: 8) {
                Image(systemName: "bolt.fill").font(.system(size: 14)).foregroundStyle(Theme.primary)
                Text(status.message).font(.system(size: 14, weight: .medium)).foregroundStyle(status.isProblem ? Theme.warning : Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
                if let fix = status.fix, status.isProblem { FixChip(title: fix.title) { if case .useMinutes(let m, _) = fix { create.form.setMinutes(m) } } }
            }
            Button { create.dismissOverlay(); onSubmit(brief) } label: {
                HStack(spacing: 8) { Text("Create video ·").font(.system(size: 19, weight: .bold)); HStack(spacing: 3) { Image(systemName: "bolt.fill").font(.system(size: 15)); Text("\(create.form.options.credits)").font(.system(size: 19, weight: .bold).monospacedDigit()) } }
                    .foregroundStyle(status.canSend ? Color.white : Theme.textTertiary).frame(maxWidth: .infinity, minHeight: 54).background(status.canSend ? AnyShapeStyle(Theme.gradient) : AnyShapeStyle(Theme.surface3), in: Capsule())
            }.buttonStyle(.plain).disabled(!status.canSend).padding(.top, 10).accessibilityIdentifier("summaryCreate")
            Button("Edit request") { onEdit() }.font(.system(size: 17, weight: .semibold)).frame(maxWidth: .infinity, minHeight: 44).accessibilityIdentifier("editRequest")
        }
        .padding(.horizontal, 20).padding(.bottom, 6)
    }
}

private struct KindStep: View {
    let title: String
    let message: String
    let suggestion: String?
    let retry: String?
    @Bindable var create: CreateModel
    let onEdit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Image(systemName: "exclamationmark.triangle").font(.system(size: 34)).foregroundStyle(Theme.warning).frame(width: 56, height: 56).background(Theme.warningContainer, in: Circle()).padding(.top, 22).accessibilityHidden(true)
            Text(title).font(.system(size: 30, weight: .bold)).foregroundStyle(Theme.text).padding(.top, 16).accessibilityAddTraits(.isHeader).accessibilityIdentifier("kindTitle")
            Text(message).font(.system(size: 17)).foregroundStyle(Theme.textSecondary).padding(.top, 8).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("kindMessage")
            if let retry { Text(retry).font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.text).padding(.top, 6) }
            if let suggestion, !suggestion.isEmpty {
                HStack(alignment: .center, spacing: 10) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("FOR EXAMPLE").font(.system(size: 12.5, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary)
                        Text(suggestion).font(.system(size: 16)).foregroundStyle(Theme.text)
                    }
                    Spacer(minLength: 4)
                    Button("Use this") { create.form.text = suggestion; create.dismissOverlay() }.font(.system(size: 15, weight: .bold)).foregroundStyle(Theme.primary).padding(.horizontal, 14).frame(minHeight: 44).background(Theme.primaryContainer, in: Capsule()).accessibilityIdentifier("useSuggestion")
                }.padding(16).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 20, style: .continuous)).padding(.top, 16)
            }
            Spacer(minLength: 8)
            Text("Nothing was charged.").font(.system(size: 15)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("nothingCharged")
            Button { onEdit() } label: { Text("Edit request").font(.system(size: 19, weight: .bold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 54).background(Theme.gradient, in: Capsule()) }.buttonStyle(.plain).padding(.top, 8).accessibilityIdentifier("editRequest")
            Button("Close") { create.dismissOverlay() }.font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, minHeight: 44)
        }
        .padding(.horizontal, 20).padding(.bottom, 6)
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
