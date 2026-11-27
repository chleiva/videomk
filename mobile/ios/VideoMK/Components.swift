import SwiftUI
import VideoMKCore

// The shared pieces of docs/UX_REVIEW.md section 6.2 item 8 that are not the Making card (MakingCard.swift) or the rows (VideoCards.swift).

/// Bolt + the receipt line ("3 credits · you'll have 39 left") + a quiet "What does this cost?" link. One component for Create and any future paywall.
struct CostLine: View {
    let text: String
    var tint: Color = Theme.textSecondary
    var symbol = "bolt.fill"
    var fourKNote = false
    var onExplain: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: symbol).font(.role(.subhead, weight: .semibold)).foregroundStyle(symbol == "bolt.fill" ? Theme.primary : tint).accessibilityHidden(true)
                Text(text).font(.role(.subhead, weight: .medium)).foregroundStyle(tint).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
            }
            if fourKNote { Text(tr("create.cost_4k_double")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).padding(.leading, 22).fixedSize(horizontal: false, vertical: true) }
            if let onExplain {
                Button(action: onExplain) { Text(tr("create.cost_why")).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.primary).frame(minHeight: Theme.minTouch, alignment: .leading) }
                    .buttonStyle(.plain).padding(.leading, 22).accessibilityIdentifier("costWhy")
            }
        }
    }
}

/// The balance, large, on the one gradient surface of the wallet.
struct WalletHero: View {
    let balance: Int
    let unlimited: Bool

    var body: some View {
        VStack(spacing: 6) {
            Text(unlimited ? "∞" : Localization.shared.number(balance))
                .font(.vmk(56, weight: .bold, design: .rounded).monospacedDigit()).foregroundStyle(Theme.onMedia).minimumScaleFactor(0.5).lineLimit(1)
            Text(unlimited ? Self.unlimitedLabel : tr("wallet.unit", balance)).font(.role(.headline)).foregroundStyle(Theme.onMedia)
        }
        .frame(maxWidth: .infinity).padding(.vertical, Theme.Space.xl).padding(.horizontal, Theme.gutter)
        .background(Theme.makingGradient, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
        .elevation(2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(unlimited ? Self.unlimitedLabel : tr("wallet.balance_a11y", tr("credits.count", balance)))
        .accessibilityIdentifier("walletHero")
    }

    /// "unlimited (test account)" exists only in debug builds; a release build never says it.
    static var unlimitedLabel: String {
        #if DEBUG
        tr("wallet.unlimited")
        #else
        tr("videos.unlimited_credits")
        #endif
    }
}
