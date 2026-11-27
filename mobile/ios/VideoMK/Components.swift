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
                Image(systemName: symbol).font(.vmk(14, weight: .semibold)).foregroundStyle(symbol == "bolt.fill" ? Theme.primary : tint).accessibilityHidden(true)
                Text(text).font(.vmk(14, weight: .medium)).foregroundStyle(tint).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 4)
            }
            if fourKNote { Text(tr("create.cost_4k_double")).font(.vmk(13)).foregroundStyle(Theme.textSecondary).padding(.leading, 22).fixedSize(horizontal: false, vertical: true) }
            if let onExplain {
                Button(action: onExplain) { Text(tr("create.cost_why")).font(.vmk(13, weight: .semibold)).foregroundStyle(Theme.primary).frame(minHeight: Theme.minTouch, alignment: .leading) }
                    .buttonStyle(.plain).padding(.leading, 22).accessibilityIdentifier("costWhy")
            }
        }
    }
}

/// The balance, large, on the one gradient surface of the wallet.
struct WalletHero: View {
    let balance: Int
    let unlimited: Bool
    var nextFree: String?
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        VStack(spacing: 6) {
            Text(unlimited ? "∞" : Localization.shared.number(balance))
                .font(.vmk(56, weight: .bold, design: .rounded).monospacedDigit()).foregroundStyle(.white).minimumScaleFactor(0.5).lineLimit(1)
            Text(unlimited ? Self.unlimitedLabel : tr("wallet.unit", balance)).font(.vmk(17, weight: .semibold)).foregroundStyle(.white.opacity(0.9))
            if let nextFree { Text(nextFree).font(.vmk(13, weight: .medium)).foregroundStyle(.white.opacity(0.85)).multilineTextAlignment(.center).padding(.top, 4) }
        }
        .frame(maxWidth: .infinity).padding(.vertical, 28).padding(.horizontal, 16)
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

/// Art (or symbol), a 28 pt headline, 15 pt body and at most one action. Used by the empty home and any other empty list.
struct EmptyState<Art: View>: View {
    let title: String
    var message: String?
    @ViewBuilder var art: Art
    var body: some View {
        VStack(spacing: 0) {
            art.padding(.top, 6).accessibilityHidden(true)
            Text(title).font(.vmk(28, weight: .bold)).tracking(-0.8).multilineTextAlignment(.center).foregroundStyle(Theme.text).padding(.top, 8).accessibilityAddTraits(.isHeader)
            if let message { Text(message).font(.vmk(15)).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary).padding(.top, 8).padding(.horizontal, 24) }
        }
    }
}
