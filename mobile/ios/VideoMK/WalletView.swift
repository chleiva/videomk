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
                            Text(w.unlimited ? "∞" : "\(w.balance)").font(.system(size: 56, weight: .bold, design: .rounded).monospacedDigit()).foregroundStyle(Theme.text)
                            Text(w.unlimited ? "unlimited (test account)" : w.balance == 1 ? "credit" : "credits").foregroundStyle(Theme.textSecondary)
                        }
                        .frame(maxWidth: .infinity).padding(.vertical, 8)
                        .accessibilityElement(children: .combine)
                    }
                    Section("What you have") {
                        ForEach(Array(w.buckets.enumerated()), id: \.offset) { _, b in
                            LabeledContent {
                                Text("\(b.remaining)").font(.body.monospacedDigit())
                            } label: {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(Self.title(b.kind))
                                    if let d = Self.expiry(b) { Text(d).font(.caption).foregroundStyle(Theme.textSecondary) }
                                }
                            }
                        }
                        if w.buckets.isEmpty { Text("No credits right now.").foregroundStyle(Theme.textSecondary) }
                    }
                    Section {
                        if let next = w.nextFreeAt {
                            Label("Next free credits: \(next.formatted(.relative(presentation: .named)))", systemImage: "clock")
                        }
                        Label(w.dailyCredits == 1 ? "1 free credit every day. It expires that night." : "\(w.dailyCredits) free credits every day. They expire that night.", systemImage: "gift")
                    } footer: {
                        Text("1 credit makes up to 1 minute of video, rounded up: a 10-second video and a 60-second video cost 1 credit, a 61-second video costs 2. Free credits expire; credits you buy never do.")
                    }
                    Section { Button("Get more credits") {}.disabled(true) } footer: { Text("Buying credits is coming soon.") }
                } else {
                    ProgressView().frame(maxWidth: .infinity)
                }
            }
            .navigationTitle("Credits")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .task { await model.refreshWallet() }
        }
        .presentationDetents([.medium, .large])
    }

    static func title(_ k: WalletBucket.Kind) -> String {
        switch k {
        case .daily: "Free today"
        case .signup: "Welcome credits"
        case .paid: "Purchased"
        case .refund: "Returned credits"
        case .other: "Credits"
        }
    }

    static func expiry(_ b: WalletBucket) -> String? {
        guard let d = b.expiresAt else { return "Never expire" }
        if b.kind == .daily { return "Expire tonight" }
        return "Expire \(d.formatted(date: .abbreviated, time: .omitted))"
    }
}
