import SwiftUI
import UniformTypeIdentifiers
import VideoMKCore

/// The file types the Files picker offers: the formats the server lists (pptx and pdf today).
func deckContentTypes(_ caps: DeckCapabilities?) -> [UTType] {
    (caps?.formats ?? ["pptx", "pdf"]).compactMap { UTType(filenameExtension: $0, conformingTo: .data) ?? UTType(filenameExtension: $0) }
}

/// "Add a presentation": one quiet row that looks like the photos row. Only drawn when the server has the feature on.

/// The attached presentation, in whatever state the journey is in: uploading (progress, cancel), reading (spinner), ready (name, slides, length, credits,
/// the promise) or a calm problem with the right action. The price follows the length chosen below.
struct DeckCard: View {
    let create: CreateModel
    let onPick: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize

    private var deck: DeckJourney { create.deck }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            switch deck.state {
            case .idle: EmptyView()
            case .uploading(let f): uploading(f)
            case .processing: processing
            case .ready(let r): ready(r)
            case .failed(let p): failed(p)
            }
        }
        .padding(14).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous).stroke(isProblem ? Theme.warning.opacity(0.7) : Theme.outline, lineWidth: 1))
        .accessibilityElement(children: .contain).accessibilityIdentifier("deckCard")
    }

    private var isProblem: Bool { if case .failed = deck.state { true } else { false } }

    private func header(_ symbol: String, tint: Color = Theme.primary, container: Color = Theme.primaryContainer) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).font(.role(.headline, weight: .regular)).foregroundStyle(tint).dynamicTypeSize(...DynamicTypeSize.xxxLarge).frame(width: 40, height: 40).background(container, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous)).accessibilityHidden(true)
            if let name = deck.fileName {
                Text(name).font(.role(.body, weight: .bold)).foregroundStyle(Theme.text).lineLimit(typeSize.isAccessibilitySize ? 4 : 2).truncationMode(.middle).fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("deckName")
            }
            Spacer(minLength: 0)
        }
    }

    // uploading

    private func uploading(_ fraction: Double) -> some View {
        let pct = Int((fraction * 100).rounded())
        return VStack(alignment: .leading, spacing: 10) {
            header("doc.richtext")
            ProgressView(value: fraction).tint(Theme.primary).accessibilityHidden(true)
            HStack(alignment: .firstTextBaseline) {
                Text(tr("deck.uploading")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityLabel(tr("deck.uploading_a11y", pct)).accessibilityIdentifier("deckUploading")
                Spacer(minLength: 8)
                Text(tr("deck.uploading_percent", pct)).font(.role(.subhead, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            }
            Text(tr("deck.keep_open")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            quietButton(tr("common.cancel"), id: "deckCancel") { create.removeDeck() }
        }
        
    }

    // reading

    private var processing: some View {
        VStack(alignment: .leading, spacing: 10) {
            header("doc.richtext")
            HStack(alignment: .top, spacing: 10) {
                ProgressView().padding(.top, 2)
                VStack(alignment: .leading, spacing: 2) {
                    Text(tr("deck.processing")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("deckProcessing")
                    Text(tr("deck.processing_sub")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                }
            }
            quietButton(tr("common.cancel"), id: "deckCancel") { create.removeDeck() }
        }
        
    }

    // ready

    private func ready(_ r: DeckReady) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            header("checkmark.circle.fill", tint: Theme.success, container: Theme.successContainer)
            Text(tr("deck.ready_line", tr("deck.slides", r.slides), LengthLabel.spoken(r.suggestedMinutes))).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("deckSummary")
            CostLine(text: create.deckCostText).accessibilityElement(children: .ignore).accessibilityLabel(create.deckCostText).accessibilityIdentifier("deckCost")
            Text(tr("deck.promise")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("deckPromise")
            Text(tr("deck.length_hint")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 4) {
                quietButton(tr("deck.choose_another"), id: "deckChoose", action: onPick)
                Spacer(minLength: 0)
                quietButton(tr("deck.remove"), id: "deckRemove", role: .destructive) { create.removeDeck() }
            }
        }
        
    }

    // problem

    private func failed(_ p: DeckProblem) -> some View {
        let action = p.action(hasLocalFile: deck.hasLocalFile)
        return VStack(alignment: .leading, spacing: 10) {
            header("exclamationmark.triangle", tint: Theme.warning, container: Theme.warningContainer)
            Text(p.title).font(.role(.body, weight: .semibold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader).accessibilityIdentifier("deckErrorTitle")
            Text(p.message).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("deckErrorMessage")
            Button(label(action)) { tap(action) }.buttonStyle(TonalButtonStyle()).accessibilityIdentifier("deckAction")       // tonal: Create stays the one gradient button of the screen
            HStack(spacing: 4) {
                if action != .pickAnother { quietButton(tr("deck.choose_another"), id: "deckChoose", action: onPick) }
                Spacer(minLength: 0)
                quietButton(tr("deck.remove"), id: "deckRemove", role: .destructive) { create.removeDeck() }
            }
        }
        
    }

    private func label(_ a: DeckAction) -> String {
        switch a {
        case .pickAnother: tr("deck.action.pick_another")
        case .chooseAgain: tr("deck.action.choose_again")
        case .retry: tr("common.try_again")
        case .checkAgain: tr("deck.action.check_again")
        }
    }

    private func tap(_ a: DeckAction) {
        Haptics.play(.selection)
        switch a {
        case .pickAnother, .chooseAgain: onPick()
        case .retry, .checkAgain: deck.perform(a)
        }
    }

    private func quietButton(_ title: String, id: String, role: ButtonRole? = nil, action: @escaping () -> Void) -> some View {
        Button(role: role, action: action) {
            Text(title).font(.role(.subhead, weight: .semibold)).foregroundStyle(role == .destructive ? Theme.danger : Theme.primary).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                .frame(minHeight: Theme.minTouch, alignment: .leading).contentShape(Rectangle())
        }
        .buttonStyle(.plain).accessibilityIdentifier(id)
    }
}
