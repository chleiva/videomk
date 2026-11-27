import SwiftUI
import VideoMKCore

struct WalletView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                if let w = model.wallet {
                    VStack(alignment: .leading, spacing: 16) {
                        WalletHero(balance: w.balance, unlimited: w.unlimited, nextFree: w.nextFreeAt.map { tr("wallet.next_free", Localization.shared.relative($0)) })
                        VStack(spacing: 0) {
                            ForEach(Array(w.buckets.enumerated()), id: \.offset) { i, b in
                                if i > 0 { Divider().padding(.leading, 16) }
                                bucketRow(b)
                            }
                            if w.buckets.isEmpty { Text(tr("wallet.none")).font(.vmk(15)).foregroundStyle(Theme.textSecondary).padding(16).frame(maxWidth: .infinity, alignment: .leading) }
                        }
                        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                        HStack(spacing: 2) {
                            Text(tr("wallet.cost_title")).font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                            InfoPopover(text: tr("wallet.rules_short") + "\n" + tr("wallet.daily_free", w.dailyCredits), spoken: tr("wallet.cost_title"), identifier: "walletInfo")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .padding(Theme.Space.l)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                }
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle(tr("wallet.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() } } }
            .task { await model.refreshWallet() }
        }
        .presentationDetents([.medium, .large])
    }

    private func heading(_ t: String) -> some View {
        Text(t.uppercased()).font(.vmk(12, weight: .bold)).tracking(0.8).foregroundStyle(Theme.textTertiary).accessibilityAddTraits(.isHeader)
    }

    private func bucketRow(_ b: WalletBucket) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(Self.title(b.kind)).font(.vmk(17)).foregroundStyle(Theme.text)
                if let d = Self.expiry(b) { Text(d).font(.vmk(13)).foregroundStyle(Theme.textSecondary) }
            }
            Spacer(minLength: 8)
            Text(Localization.shared.number(b.remaining)).font(.vmk(17, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.text)
        }
        .padding(16).frame(minHeight: Theme.minTouch).accessibilityElement(children: .combine)
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
