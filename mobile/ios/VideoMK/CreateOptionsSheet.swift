import SwiftUI
import VideoMKCore

/// The one Options sheet of Create (docs/UX_2026_REDESIGN.md 4.2): everything the three pills do not carry. For (all platforms, so VoiceOver users have
/// every choice in one place), Look swatches, Quality, Subtitles, Language and the Format tiles. Formats the account cannot use are hidden, not dimmed.
struct CreateOptionsSheet: View {
    @Bindable var create: CreateModel
    @Environment(\.dismiss) private var dismiss
    private var form: CreateForm { create.form }

    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        FittedSheet {
            VStack(alignment: .leading, spacing: Theme.Space.xl) {
                SheetHeader(title: tr("create.options"), closeLabel: tr("common.done"), closeID: "optionsDone") { dismiss() }
                group(tr("create.what_is_it_for")) { forChips }
                group(create.caps.looks == nil ? tr("create.look") : tr("create.colours")) { looks }      // with the look picker, "Look" is the pill's word: these are the colours
                resolutionControl
                VStack(spacing: 0) {
                    Toggle(isOn: $create.form.captions) { Label(tr("create.subtitles"), systemImage: "captions.bubble").font(.role(.body)).foregroundStyle(Theme.text) }
                        .tint(Theme.success).frame(minHeight: 52).accessibilityIdentifier("subtitlesToggle")
                    Divider().overlay(Theme.outline)
                    languageRow
                }
                if readyFormats.count > 1 { group(tr("create.format")) { formatTiles }.id("format") }
            }
        }
    }

    private func group<C: View>(_ title: String, @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) { SectionLabel(title); content() }
    }

    // for

    private var forChips: some View {
        WrapLayout(spacing: Theme.Space.s) {
            ForEach(PlatformChips.make(create.caps)) { chip in
                let selected = form.chip(create.caps)?.id == chip.id && !form.isCustom(create.caps)
                ChoiceChip(title: chip.id == "other" ? tr("pill.video") : chip.label, selected: selected, spoken: chip.supported ? chip.label : tr("create.chip_soon_a11y", chip.label, create.caps.aspectName(chip.aspect)), identifier: "optPlatform-\(chip.id)") {
                    create.form.select(chip); Haptics.play(.selection)
                }
                .disabled(!chip.supported)
            }
        }
        .accessibilityElement(children: .contain)
    }

    // look

    /// Four swatches in a row; at the largest text sizes two rows of two, so every name is whole and the same size.
    @ViewBuilder private var looks: some View {
        let all: [VideoLook?] = [nil] + VideoLook.allCases.map { Optional($0) }
        if typeSize.isAccessibilitySize {
            VStack(spacing: Theme.Space.m) {
                HStack(alignment: .top, spacing: Theme.Space.m) { ForEach(all.prefix(2), id: \.self) { look($0) } }
                HStack(alignment: .top, spacing: Theme.Space.m) { ForEach(all.suffix(2), id: \.self) { look($0) } }
            }
        } else {
            HStack(alignment: .top, spacing: Theme.Space.m) { ForEach(all, id: \.self) { look($0) } }
        }
    }

    private func look(_ look: VideoLook?) -> some View {
        let selected = form.look == look
        let title = look?.title ?? tr("create.look_auto")
        return Button { create.form.look = look; Haptics.play(.selection) } label: {
            VStack(spacing: 6) {
                LookSwatch(look: look).aspectRatio(typeSize.isAccessibilitySize ? 2 : 3 / 3.6, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
                    .padding(3).overlay(RoundedRectangle(cornerRadius: Theme.Radii.thumb + 3, style: .continuous).strokeBorder(Theme.primary, lineWidth: selected ? 2 : 0))
                HStack(spacing: 3) {
                    if selected { Image(systemName: "checkmark").font(.role(.caption, weight: .bold)).accessibilityHidden(true) }
                    Text(title).font(.role(.footnote, weight: selected ? .semibold : .regular)).lineLimit(typeSize.isAccessibilitySize ? 2 : 1).multilineTextAlignment(.center)
                }
                .foregroundStyle(selected ? Theme.primary : Theme.text)
            }
        }
        .buttonStyle(.plain).frame(maxWidth: .infinity)
        .accessibilityLabel(look == nil ? tr("create.look_auto_a11y") : title).accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("look-\(look?.rawValue ?? "auto")")
    }

    // quality

    /// 720p, 1080p, 4K as chips; 4K says what it costs, and its one sentence sits under the row while it is chosen.
    @ViewBuilder private var resolutionControl: some View {
        let choices = form.resolutionChoices(create.caps)
        if choices.count > 1 {
            group(tr("create.quality")) {
                WrapLayout(spacing: Theme.Space.s) {
                    ForEach(choices, id: \.id) { r in
                        ChoiceChip(title: r.creditsMultiplier > 1 ? "\(r.label) · \(tr("create.credits_multiplier", r.creditsMultiplier))" : r.label, selected: form.resolution == r.id,
                                   spoken: r.creditsMultiplier > 1 ? tr("create.credits_multiplier_a11y", r.label, r.creditsMultiplier) : r.label, identifier: "resolution-\(r.id)") { create.form.setResolution(r.id); Haptics.play(.selection) }
                    }
                }
                if let note = form.resolutionNote(create.caps), form.creditsMultiplier > 1 {
                    Text(note).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("resolutionNote")
                }
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
                Label(tr("create.language"), systemImage: "globe").font(.role(.body)).foregroundStyle(Theme.text)
                Spacer(minLength: Theme.Space.s)
                Text(form.language == "auto" ? tr("create.look_auto") : (create.caps.languages.first { $0.id == form.language }?.label ?? form.language)).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).lineLimit(1)
                Image(systemName: "chevron.up.chevron.down").font(.role(.caption, weight: .semibold)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            }.frame(minHeight: 52).contentShape(Rectangle())
        }
        .accessibilityIdentifier("languageRow")
    }

    // format: the shape is the label

    private var readyFormats: [(id: String, name: String, symbol: String)] {
        [("16:9", tr("aspect.landscape"), "rectangle"), ("9:16", tr("aspect.vertical"), "rectangle.portrait"), ("1:1", tr("aspect.square"), "square"), ("4:5", tr("aspect.portrait"), "rectangle.portrait")]
            .filter { f in create.caps.readyAspects.contains { $0.id == f.0 } }.map { (id: $0.0, name: $0.1, symbol: $0.2) }
    }

    /// Every tile always says its ratio (two upright rectangles look alike without it); a format that is still in beta says "Beta" in words.
    private var formatTiles: some View {
        HStack(alignment: .top, spacing: Theme.Space.s) {
            ForEach(readyFormats, id: \.id) { f in
                let selected = form.aspect == f.id
                let beta = create.caps.aspect(f.id)?.beta == true
                Button { create.form.aspect = f.id; create.form.normalize(create.caps); Haptics.play(.selection) } label: {
                    VStack(spacing: Theme.Space.xs) {
                        AspectGlyph(ratio: f.id).foregroundStyle(selected ? Theme.primary : Theme.textSecondary).frame(width: 30, height: 30)
                        Text(f.id).font(.role(.footnote, weight: .semibold).monospacedDigit()).foregroundStyle(selected ? Theme.primary : Theme.text).lineLimit(1)
                        Text(beta ? tr("create.beta") : " ").font(.role(.caption)).foregroundStyle(Theme.textSecondary).lineLimit(1)
                    }
                    .padding(.vertical, Theme.Space.m).frame(maxWidth: .infinity, minHeight: 88)
                    .background(selected ? Theme.primaryContainer : Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
                    .overlay(alignment: .topTrailing) { if selected { Image(systemName: "checkmark.circle.fill").font(.role(.footnote)).foregroundStyle(Theme.primary).padding(6).accessibilityHidden(true) } }
                }
                .buttonStyle(.plain)
                .accessibilityLabel(beta ? tr("create.aspect_a11y_beta", f.name, f.id) : "\(f.name) \(f.id)").accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("aspect-\(f.id)")
            }
        }
        .dynamicTypeSize(...DynamicTypeSize.accessibility1)
    }
}

/// The frame shape, drawn to its real proportions (16:9, 9:16, 1:1 and 4:5 are told apart at a glance).
struct AspectGlyph: View {
    let ratio: String
    var body: some View {
        let parts = ratio.split(separator: ":").compactMap { Double($0) }
        let r = parts.count == 2 && parts[1] > 0 ? parts[0] / parts[1] : 16.0 / 9.0
        RoundedRectangle(cornerRadius: 4, style: .continuous).strokeBorder(lineWidth: 2).aspectRatio(r, contentMode: .fit).accessibilityHidden(true)
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
                Image(systemName: "sparkles").font(.role(.title, weight: .regular)).foregroundStyle(Theme.primary)
            case .midnight?:
                LinearGradient(colors: [Color(hex: 0x1C2150), Color(hex: 0x0C0F28)], startPoint: .top, endPoint: .bottom)
                lines([Theme.toastAccent, Color(hex: 0x7C80FF), Color(hex: 0x5F63F0)])
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
