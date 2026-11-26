import SwiftUI
import VideoMKCore

/// Length, look and subtitles (docs/UI_DESIGN.md "Video options"). The price is always visible: on each length card and on the Done button.
struct OptionsSheet: View {
    @Binding var options: CreateOptions
    let balance: Int?
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize

    private var affordable: Bool { balance.map { options.credits <= $0 } ?? true }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(tr("options.video_options")).font(.system(size: 19, weight: .bold)).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader)
                Spacer()
                Button(tr("common.done")) { dismiss() }.font(.system(size: 17, weight: .semibold)).frame(minWidth: 44, minHeight: 44)
            }
            .padding(.horizontal, 20).padding(.top, 12)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    overline(tr("create.length"))
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: typeSize.isAccessibilitySize ? 1 : 3), spacing: 10) {
                        ForEach(CreateOptions.lengths, id: \.self) { lengthCard($0) }
                    }
                    Text(balance.map { tr("options.cost_note_balance", $0) } ?? tr("options.cost_note")).font(.system(size: 14)).foregroundStyle(Theme.textSecondary).padding(.top, 2)
                    overline(tr("create.look")).padding(.top, 18)
                    HStack(alignment: .top, spacing: 10) {
                        swatch(nil, title: tr("create.look_auto"))
                        ForEach(VideoLook.allCases) { swatch($0, title: $0.title) }
                    }
                    Divider().padding(.top, 14)
                    Toggle(isOn: $options.captions) {
                        Label(tr("create.subtitles"), systemImage: "captions.bubble").font(.system(size: 17)).foregroundStyle(Theme.text)
                    }
                    .tint(Theme.primary).frame(minHeight: 56)
                    .accessibilityIdentifier("subtitlesToggle")
                }
                .padding(.horizontal, 20).padding(.top, 14).padding(.bottom, 8)
            }
            Button { dismiss() } label: {
                HStack(spacing: 6) {
                    Text(tr("common.done") + " ·"); Image(systemName: "bolt.fill").font(.system(size: 14)); Text(tr("credits.count", options.credits))
                }
                .font(.system(size: 17, weight: .semibold)).foregroundStyle(affordable ? Theme.onPrimary : Theme.warning)
                .frame(maxWidth: .infinity, minHeight: 52)
                .background(affordable ? AnyShapeStyle(Theme.gradient) : AnyShapeStyle(Theme.warningContainer), in: Capsule())
                .overlay(Capsule().stroke(Theme.warning, lineWidth: affordable ? 0 : 1.5))
            }
            .buttonStyle(.plain).padding(.horizontal, 20).padding(.bottom, 8).padding(.top, 6)
            .accessibilityLabel(tr("options.done_a11y", tr("credits.count", options.credits)))
            .accessibilityIdentifier("optionsDone")
        }
        .presentationBackground(Theme.surface)
        .presentationDetents([.height(640), .large])
        .presentationDragIndicator(.visible)
    }

    private func overline(_ t: String) -> some View {
        Text(t.uppercased()).font(.system(size: 13, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary).accessibilityAddTraits(.isHeader)
    }

    private func lengthCard(_ m: Double) -> some View {
        let selected = options.minutes == m
        let credits = ComposerPlan.credits(forMinutes: m)
        let costly = balance.map { credits > $0 } ?? false
        return Button { options.minutes = m; UISelectionFeedbackGenerator().selectionChanged() } label: {
            VStack(spacing: 2) {
                Text(LengthLabel.chip(m)).font(.system(size: 17, weight: .semibold)).foregroundStyle(selected ? Theme.primary : Theme.text)
                HStack(spacing: 2) { Image(systemName: "bolt.fill").font(.system(size: 10)); Text("\(credits)").font(.system(size: 12.5).monospacedDigit()) }
                    .foregroundStyle(costly ? Theme.warning : selected ? Theme.primary : Theme.textSecondary)
            }
            .frame(maxWidth: .infinity, minHeight: 62)
            .background(selected ? Theme.primaryContainer : (costly ? Theme.warningContainer.opacity(0.7) : Theme.surfaceRaised), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.primary, lineWidth: selected ? 1.5 : 0))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(tr("create.length_a11y", LengthLabel.spoken(m), tr("credits.count", credits)))
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("length-\(Int(m))")
    }

    private func swatch(_ look: VideoLook?, title: String) -> some View {
        let selected = options.look == look
        return Button { options.look = look; UISelectionFeedbackGenerator().selectionChanged() } label: {
            VStack(spacing: 6) {
                LookSwatch(look: look).aspectRatio(3 / 3.6, contentMode: .fit)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.primary, lineWidth: selected ? 2 : 0))
                    .padding(selected ? 3 : 0)
                    .background(selected ? Theme.primaryContainer : .clear, in: RoundedRectangle(cornerRadius: 19, style: .continuous))
                Text(title).font(.system(size: 15, weight: selected ? .semibold : .regular)).foregroundStyle(selected ? Theme.primary : Theme.text).lineLimit(1).minimumScaleFactor(0.7)
            }
        }
        .buttonStyle(.plain)
        .frame(maxWidth: .infinity)
        .accessibilityLabel(look == nil ? tr("create.look_auto_a11y") : look!.title)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("look-\(look?.rawValue ?? "auto")")
    }
}

/// The little preview of a look: abstract, drawn, no assets.
struct LookSwatch: View {
    let look: VideoLook?
    var body: some View {
        ZStack {
            switch look {
            case nil:
                Theme.primaryContainer
                Image(systemName: "sparkles").font(.system(size: 26)).foregroundStyle(Theme.primary)
            case .midnight?:
                LinearGradient(colors: [Color(hex: 0x1C2150), Color(hex: 0x0C0F28)], startPoint: .top, endPoint: .bottom)
                lines([Color(hex: 0xB9BBFF), Color(hex: 0x7C80FF), Color(hex: 0x5F63F0)])
            case .paper?:
                Color(hex: 0xF6EEE2)
                lines([Color(hex: 0x3B3226), Color(hex: 0x8C7F66), Color(hex: 0xB9AC92)])
            case .sunrise?:
                LinearGradient(colors: [Color(hex: 0xFFA763), Color(hex: 0xF0506E)], startPoint: .top, endPoint: .bottom)
                lines([.white, .white.opacity(0.7), .white.opacity(0.45)])
            }
        }
    }
    private func lines(_ colors: [Color]) -> some View {
        VStack(spacing: 6) { ForEach(Array(colors.enumerated()), id: \.offset) { _, c in Capsule().fill(c).frame(height: 3).padding(.horizontal, 18) } }
    }
}
