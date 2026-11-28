import SwiftUI
import VideoMKCore

/// The one Options sheet of Create (docs/UX_2026_REDESIGN.md 4.2): everything the pills do not carry. Quality, Subtitles, Language and the Format tiles.
/// The platform and the look are the pills on the dock and are not repeated here (two ways to set one thing is how "Auto" gets confusing).
/// Formats the account cannot use are hidden, not dimmed.
struct CreateOptionsSheet: View {
    @Bindable var create: CreateModel
    @Environment(\.dismiss) private var dismiss
    private var form: CreateForm { create.form }

    var body: some View {
        FittedSheet {
            VStack(alignment: .leading, spacing: Theme.Space.xl) {
                SheetHeader(title: tr("create.options"), closeLabel: tr("common.done"), closeID: "optionsDone") { dismiss() }
                resolutionControl
                VStack(spacing: 0) {
                    Toggle(isOn: $create.form.captions) { Label(tr("create.subtitles"), systemImage: "captions.bubble").font(.role(.body)).foregroundStyle(Theme.text) }
                        .tint(Theme.primary).frame(minHeight: 52).accessibilityIdentifier("subtitlesToggle")
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
    var line: CGFloat = 2
    var radius: CGFloat = 4
    var body: some View {
        let parts = ratio.split(separator: ":").compactMap { Double($0) }
        let r = parts.count == 2 && parts[1] > 0 ? parts[0] / parts[1] : 16.0 / 9.0
        RoundedRectangle(cornerRadius: radius, style: .continuous).strokeBorder(lineWidth: line).aspectRatio(r, contentMode: .fit).accessibilityHidden(true)
    }
}
