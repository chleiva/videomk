import SwiftUI
import VideoMKCore

/// Credits: the balance, when the next free ones arrive, and (only when there is something to list) where the credits came from.
/// There is nothing to buy yet, so the sheet answers "when do I get more?" in one line instead of offering a dead end.
struct WalletView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        FittedSheet {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                SheetHeader(title: tr("wallet.title"), closeID: "walletClose") { dismiss() }
                if let w = model.wallet {
                    WalletHero(balance: w.balance, unlimited: w.unlimited)
                    if !w.unlimited, let next = Self.nextLine(w) {
                        Label { Text(next).font(.role(.headline)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: "gift").font(.role(.headline)).foregroundStyle(Theme.primary) }
                            .accessibilityIdentifier("walletNextFree")
                    }
                    if !w.buckets.isEmpty {
                        VStack(spacing: 0) {
                            ForEach(Array(w.buckets.enumerated()), id: \.offset) { i, b in
                                if i > 0 { Divider().overlay(Theme.outline) }
                                bucketRow(b)
                            }
                        }
                    }
                    Text(tr("wallet.rules_short")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("walletInfo")
                } else {
                    LiveSpinner().frame(maxWidth: .infinity).padding(.vertical, Theme.Space.xxxl)
                }
            }
        }
        .task { await model.refreshWallet() }
    }

    /// "1 free credit tomorrow". Without a date from the server: what arrives every day. Nothing when the account gets no free credits.
    static func nextLine(_ w: WalletInfo) -> String? {
        guard w.dailyCredits > 0 else { return w.balance > 0 ? nil : tr("wallet.none") }
        if let at = w.nextFreeAt { return tr("wallet.next_free_n", w.dailyCredits, Localization.shared.nextFree(at)) }
        return tr("wallet.daily_short", w.dailyCredits)
    }

    private func bucketRow(_ b: WalletBucket) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Space.m) {
            VStack(alignment: .leading, spacing: 2) {
                Text(Self.title(b.kind)).font(.role(.body)).foregroundStyle(Theme.text)
                if let d = Self.expiry(b) { Text(d).font(.role(.footnote)).foregroundStyle(Theme.textSecondary) }
            }
            Spacer(minLength: Theme.Space.s)
            Text(Localization.shared.number(b.remaining)).font(.role(.headline).monospacedDigit()).foregroundStyle(Theme.text)
        }
        .padding(.vertical, Theme.Space.m).frame(minHeight: Theme.minTouch).accessibilityElement(children: .combine)
    }

    static func title(_ k: WalletBucket.Kind) -> String {
        switch k {
        case .daily: tr("wallet.bucket.daily")
        case .signup: tr("wallet.bucket.signup")
        case .paid: tr("wallet.bucket.paid")
        case .refund: tr("wallet.bucket.refund")
        case .other: tr("wallet.bucket.other")
        }
    }

    static func expiry(_ b: WalletBucket) -> String? {
        guard let d = b.expiresAt else { return tr("wallet.never_expire") }
        if b.kind == .daily { return tr("wallet.expire_tonight") }
        return tr("wallet.expire_on", Localization.shared.abbreviatedDate(d))
    }
}
