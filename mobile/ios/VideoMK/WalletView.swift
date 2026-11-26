import SwiftUI
import VideoMKCore

struct WalletView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                if let w = model.wallet {
                    Section {
                        VStack(spacing: 4) {
                            Text(w.unlimited ? "∞" : Localization.shared.number(w.balance)).font(.system(size: 56, weight: .bold, design: .rounded).monospacedDigit()).foregroundStyle(Theme.text)
                            Text(w.unlimited ? tr("wallet.unlimited") : tr("wallet.unit", w.balance)).foregroundStyle(Theme.textSecondary)
                        }
                        .frame(maxWidth: .infinity).padding(.vertical, 8)
                        .accessibilityElement(children: .combine)
                    }
                    Section(tr("wallet.what_you_have")) {
                        ForEach(Array(w.buckets.enumerated()), id: \.offset) { _, b in
                            LabeledContent {
                                Text(Localization.shared.number(b.remaining)).font(.body.monospacedDigit())
                            } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(Self.title(b.kind))
                                    if let d = Self.expiry(b) { Text(d).font(.caption).foregroundStyle(Theme.textSecondary) }
                                }
                            }
                        }
                        if w.buckets.isEmpty { Text(tr("wallet.none")).foregroundStyle(Theme.textSecondary) }
                    }
                    Section {
                        if let next = w.nextFreeAt {
                            Label(tr("wallet.next_free", Localization.shared.relative(next)), systemImage: "clock")
                        }
                        Label(tr("wallet.daily_free", w.dailyCredits), systemImage: "gift")
                    } footer: {
                        Text(tr("wallet.rules"))
                    }
                    Section { Button(tr("wallet.get_more")) {}.disabled(true) } footer: { Text(tr("wallet.coming_soon")) }
                } else {
                    ProgressView().frame(maxWidth: .infinity)
                }
            }
            .navigationTitle(tr("wallet.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() } } }
            .task { await model.refreshWallet() }
        }
        .presentationDetents([.medium, .large])
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
