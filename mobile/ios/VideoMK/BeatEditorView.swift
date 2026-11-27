import SwiftUI
import VideoMKCore

struct BeatEditorView: View {
    @Bindable var model: EditorModel
    let beatID: String
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    private var beat: EditorBeat? { model.beats.first { $0.id == beatID } }

    var body: some View {
        Group {
            if let beat {
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Space.xl) {
                        SheetHeader(title: tr("editor.scene"), closeLabel: tr("common.done"), closeID: "sceneDone") { dismiss() }
                            .disabled(model.narrationError(for: beatID) != nil)
                        section(tr("editor.narration")) {
                            TextEditor(text: Binding(get: { beat.narration }, set: { model.setNarration(beatID, $0) }))
                                .font(.role(.body)).foregroundStyle(Theme.text).scrollContentBackground(.hidden)
                                .focused($focused)
                                .frame(minHeight: 140).padding(Theme.Space.m)
                                .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                                .accessibilityIdentifier("narrationField")
                            let words = EditorDiff.wordCount(beat.narration)
                            Text(beat.silent && words == 0 ? tr("editor.silent_note", Int((beat.hold ?? 0).rounded())) : tr("editor.word_stats", words, Int(EditorDiff.spokenSeconds(beat.narration).rounded()), model.limits.minWords, model.limits.maxWords))
                                .font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                            if let error = model.narrationError(for: beatID) { Label(error, systemImage: "exclamationmark.circle").labelStyle(DangerMarkLabel()).font(.role(.footnote)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true) }
                        }
                        section(tr("editor.visual")) {
                            HStack(alignment: .top, spacing: Theme.Space.m) {
                                Image(systemName: beat.kind?.symbol ?? "square").font(.role(.headline)).foregroundStyle(Theme.primary).frame(width: 28).accessibilityHidden(true)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(beat.kind?.label ?? tr("editor.scene")).font(.role(.headline)).foregroundStyle(Theme.text)
                                    if !beat.summary.isEmpty { Text(beat.summary).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true) }
                                }
                            }
                            if beat.kind != .image { Text(tr("editor.charts_diagrams_and_other_scenes")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true) }
                        }
                        if beat.kind == .image { photoSection(beat) }
                    }
                    .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.xxl)
                }
                .scrollDismissesKeyboard(.interactively)
                .interactiveDismissDisabled(model.narrationError(for: beatID) != nil)
            } else {
                VStack(spacing: Theme.Space.l) {
                    SheetHeader(title: tr("editor.scene_not_found")) { dismiss() }
                    Spacer()
                }.padding(.horizontal, Theme.gutter)
            }
        }
        .presentationBackground(Theme.surface).presentationDetents([.large]).presentationDragIndicator(.visible)
    }

    private func section<C: View>(_ title: String, @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) { SectionLabel(title); content() }
    }

    @ViewBuilder private func photoSection(_ beat: EditorBeat) -> some View {
        section(tr("editor.photo")) {
            if let photo = beat.photo, let url = photo.url, model.picks[beatID] == nil {
                AsyncImage(url: url) { $0.resizable().scaledToFill() } placeholder: { Theme.surfaceRaised }
                    .frame(height: 180).frame(maxWidth: .infinity).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                if let credit = photo.credit { Text(credit).font(.role(.footnote)).foregroundStyle(Theme.textSecondary) }
            } else if beat.photo?.noPhoto == true, model.picks[beatID] == nil {
                Label(tr("editor.no_suitable_photo_was_found"), systemImage: "photo.badge.exclamationmark").font(.role(.subhead)).foregroundStyle(Theme.text)
            }
            if let picked = model.picks[beatID], let c = beat.candidates.first(where: { $0.key == picked }) {
                Label(tr("editor.will_use_photo", c.creator), systemImage: "checkmark.circle.fill").font(.role(.subhead)).foregroundStyle(Theme.text)
                Button(tr("editor.undo_photo_change")) { model.clearPick(for: beatID) }.buttonStyle(TextButtonStyle())
            }
        }
        if !beat.candidates.isEmpty {
            section(tr("editor.other_photos")) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: Theme.Space.m)], spacing: Theme.Space.m) {
                    ForEach(beat.candidates) { c in
                        let chosen = model.picks[beatID] == c.key || (model.picks[beatID] == nil && beat.photo?.chosen == c.key)
                        Button { model.pick(c, for: beatID); Haptics.play(.selection) } label: {
                            VStack(alignment: .leading, spacing: Theme.Space.xs) {
                                AsyncImage(url: c.thumbURL) { $0.resizable().scaledToFill() } placeholder: { Theme.surfaceRaised }
                                    .frame(height: 90).frame(maxWidth: .infinity).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
                                    .overlay { if chosen { RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous).strokeBorder(Theme.primary, lineWidth: 3) } }
                                    .overlay(alignment: .bottomTrailing) { if chosen { Image(systemName: "checkmark.circle.fill").font(.role(.headline)).foregroundStyle(Theme.onPrimary, Theme.primary).padding(6) } }
                                Text(c.creator).font(.role(.footnote)).foregroundStyle(Theme.text).lineLimit(1)
                                Text(verbatim: c.provider == "unsplash" ? "Unsplash" : c.license.uppercased()).font(.role(.caption)).foregroundStyle(Theme.textSecondary)
                            }
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(tr(chosen ? "editor.photo_by_selected" : "editor.photo_by", c.creator))
                    }
                }
                Text(tr("editor.credit_for_the_chosen_photo")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}
