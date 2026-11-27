import SwiftUI
import VideoMKCore

/// The one Options sheet of Create (docs/UX_2026_REDESIGN.md 4.2): everything the three pills do not carry. For (all platforms, so VoiceOver users have
/// every choice in one place), Look swatches, Quality, Subtitles, Language and the Format tiles. Formats the account cannot use are hidden, not dimmed.
struct CreateOptionsSheet: View {
    @Bindable var create: CreateModel
    @Environment(\.dismiss) private var dismiss
    private var form: CreateForm { create.form }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    section(tr("create.what_is_it_for")).padding(.bottom, 8)
                    forChips
                    section(tr("create.look")).padding(.top, 20).padding(.bottom, 8)
                    HStack(alignment: .top, spacing: 10) { look(nil, tr("create.look_auto")); ForEach(VideoLook.allCases) { look($0, $0.title) } }
                    resolutionControl.padding(.top, 20)
                    VStack(spacing: 0) {
                        Toggle(isOn: $create.form.captions) { Label(tr("create.subtitles"), systemImage: "captions.bubble").font(.vmk(17)).foregroundStyle(Theme.text) }
                            .tint(Theme.primary).frame(minHeight: 52).padding(.horizontal, 16).accessibilityIdentifier("subtitlesToggle")
                        Divider().padding(.leading, 16)
                        languageRow.padding(.horizontal, 16)
                    }
                    .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous)).padding(.top, 20)
                    if readyFormats.count > 1 {
                        section(tr("create.format")).padding(.top, 20).padding(.bottom, 8).id("format")
                        formatTiles
                    }
                }
                .padding(.horizontal, 20).padding(.vertical, 12)
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle(tr("create.options")).navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() }.accessibilityIdentifier("optionsDone") } }
        }
        .presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
    }

    private func section(_ t: String) -> some View {
        Text(t.uppercased()).font(.vmk(12, weight: .bold)).tracking(0.8).foregroundStyle(Theme.textTertiary).accessibilityAddTraits(.isHeader)
    }

    // for

    private var forChips: some View {
        WrapLayout(spacing: 8) {
            ForEach(PlatformChips.make(create.caps)) { chip in
                let selected = form.chip(create.caps)?.id == chip.id && !form.isCustom(create.caps)
                Button {
                    if chip.supported { create.form.select(chip); Haptics.play(.selection) } else { Haptics.play(.warning) }
                } label: {
                    HStack(spacing: 6) {
                        if selected { Image(systemName: "checkmark").font(.vmk(13, weight: .bold)) }
                        Text(chip.label).font(.vmk(15, weight: .semibold)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                    }
                    .foregroundStyle(selected ? Theme.primary : Theme.text).padding(.horizontal, 14).padding(.vertical, 8).frame(minHeight: 44)
                    .background(selected ? Theme.primaryContainer : Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous).stroke(selected ? Theme.primary : Theme.outline, lineWidth: selected ? 1.5 : 1))
                    .opacity(chip.supported ? 1 : 0.5)
                }
                .buttonStyle(.plain).disabled(!chip.supported)
                .accessibilityLabel(chip.supported ? chip.label : tr("create.chip_soon_a11y", chip.label, create.caps.aspectName(chip.aspect)))
                .accessibilityAddTraits(selected ? .isSelected : [])
                .accessibilityIdentifier("optPlatform-\(chip.id)")
            }
        }
        .accessibilityElement(children: .contain)
    }

    // look

    private func look(_ look: VideoLook?, _ title: String) -> some View {
        let selected = form.look == look
        return Button { create.form.look = look; Haptics.play(.selection) } label: {
            VStack(spacing: 6) {
                LookSwatch(look: look).aspectRatio(3 / 3.6, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous).stroke(Theme.primary, lineWidth: selected ? 2 : 0))
                    .padding(selected ? 3 : 0).background(selected ? Theme.primaryContainer : .clear, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
                Text(title).font(.vmk(15, weight: selected ? .semibold : .regular)).foregroundStyle(selected ? Theme.primary : Theme.text).lineLimit(1).minimumScaleFactor(0.7).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }
        }
        .buttonStyle(.plain).frame(maxWidth: .infinity)
        .accessibilityLabel(look == nil ? tr("create.look_auto_a11y") : title).accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("look-\(look?.rawValue ?? "auto")")
    }

    // quality

    /// 720p | 1080p | 4K, with a small "2x" tag on 4K; the sentence about the price is behind an (i).
    @ViewBuilder private var resolutionControl: some View {
        let choices = form.resolutionChoices(create.caps)
        if choices.count > 1 {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 0) {
                    section(tr("create.quality"))
                    if let note = form.resolutionNote(create.caps), form.creditsMultiplier > 1 { InfoPopover(text: note, spoken: tr("create.cost_why"), identifier: "resolutionNote") }
                }
                HStack(spacing: 0) {
                    ForEach(choices, id: \.id) { r in
                        let selected = form.resolution == r.id
                        Button { create.form.setResolution(r.id); Haptics.play(.selection) } label: {
                            HStack(spacing: 4) {
                                Text(r.label).font(.vmk(17, weight: .semibold)).foregroundStyle(Theme.text)
                                if r.creditsMultiplier > 1 { Text(tr("create.credits_multiplier", r.creditsMultiplier)).font(.vmk(11, weight: .bold)).foregroundStyle(selected ? Theme.primary : Theme.textSecondary) }
                            }
                            .multilineTextAlignment(.center).padding(.vertical, 4).frame(maxWidth: .infinity, minHeight: 44)
                            .background(selected ? Theme.surface : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .shadow(color: .black.opacity(selected ? 0.08 : 0), radius: 3, y: 1)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(r.creditsMultiplier > 1 ? tr("create.credits_multiplier_a11y", r.label, r.creditsMultiplier) : r.label).accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("resolution-\(r.id)")
                    }
                }
                .padding(3).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous))
            }
        }
    }

    // language

    private var languageRow: some View {
        Menu {
            Button { create.form.language = "auto" } label: { if form.language == "auto" { Label(tr("create.same_as_my_description"), systemImage: "checkmark") } else { Text(tr("create.same_as_my_description")) } }
            ForEach(create.caps.languages, id: \.id) { l in Button { create.form.language = l.id } label: { if form.language == l.id { Label(l.label, systemImage: "checkmark") } else { Text(l.label) } } }
        } label: {
            HStack {
                Label(tr("create.language"), systemImage: "globe").font(.vmk(17)).foregroundStyle(Theme.text)
                Spacer(minLength: 8)
                Text(form.language == "auto" ? tr("look.auto") : (create.caps.languages.first { $0.id == form.language }?.label ?? form.language)).font(.vmk(15)).foregroundStyle(Theme.textSecondary).lineLimit(1)
                Image(systemName: "chevron.up.chevron.down").font(.vmk(12, weight: .semibold)).foregroundStyle(Theme.textTertiary)
            }.frame(minHeight: 52)
        }
        .accessibilityIdentifier("languageRow")
    }

    // format: the shape is the label

    private var readyFormats: [(id: String, name: String, symbol: String)] {
        [("16:9", tr("aspect.landscape"), "rectangle"), ("9:16", tr("aspect.vertical"), "rectangle.portrait"), ("1:1", tr("aspect.square"), "square"), ("4:5", tr("aspect.portrait"), "rectangle.portrait")]
            .filter { f in create.caps.readyAspects.contains { $0.id == f.0 } }.map { (id: $0.0, name: $0.1, symbol: $0.2) }
    }

    private var formatTiles: some View {
        HStack(spacing: 10) {
            ForEach(readyFormats, id: \.id) { f in
                let selected = form.aspect == f.id
                let beta = create.caps.aspect(f.id)?.beta == true
                Button { create.form.aspect = f.id; create.form.normalize(create.caps); Haptics.play(.selection) } label: {
                    VStack(spacing: 6) {
                        Image(systemName: f.symbol).font(.vmk(24)).dynamicTypeSize(...DynamicTypeSize.xxxLarge).foregroundStyle(selected ? Theme.primary : Theme.textSecondary)
                        Text(selected ? f.id : " ").font(.vmk(12, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.primary).lineLimit(1)
                    }
                    .padding(.vertical, 10).frame(maxWidth: .infinity, minHeight: 72)
                    .background(selected ? Theme.primaryContainer : Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous).stroke(Theme.primary, lineWidth: selected ? 1.5 : 0))
                    .overlay(alignment: .topTrailing) { if beta { Circle().fill(Theme.warning).frame(width: 7, height: 7).padding(8).accessibilityHidden(true) } }
                }
                .buttonStyle(.plain)
                .accessibilityLabel(beta ? tr("create.aspect_a11y_beta", f.name, f.id) : "\(f.name) \(f.id)").accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("aspect-\(f.id)")
            }
        }
    }
}
