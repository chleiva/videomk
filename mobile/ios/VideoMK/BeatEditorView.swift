import SwiftUI
import VideoMKCore

struct BeatEditorView: View {
    @Bindable var model: EditorModel
    let beatID: String
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    private var beat: EditorBeat? { model.beats.first { $0.id == beatID } }

    var body: some View {
        NavigationStack {
            if let beat {
                Form {
                    Section {
                        TextEditor(text: Binding(get: { beat.narration }, set: { model.setNarration(beatID, $0) }))
                            .focused($focused)
                            .frame(minHeight: 140)
                            .accessibilityIdentifier("narrationField")
                    } header: { Text(tr("editor.narration")) } footer: {
                        VStack(alignment: .leading, spacing: 4) {
                            let words = EditorDiff.wordCount(beat.narration)
                            if beat.silent && words == 0 {
                                Text(tr("editor.silent_note", Int((beat.hold ?? 0).rounded())))
                            } else {
                                Text(tr("editor.word_stats", words, Int(EditorDiff.spokenSeconds(beat.narration).rounded()), model.limits.minWords, model.limits.maxWords))
                            }
                            if let error = model.narrationError(for: beatID) { Text(error).foregroundStyle(Theme.danger) }
                        }
                    }
                    Section(tr("editor.visual")) {
                        Label {
                            VStack(alignment: .leading) {
                                Text(beat.kind?.label ?? tr("editor.scene")).font(.headline)
                                if !beat.summary.isEmpty { Text(beat.summary).font(.callout).foregroundStyle(Theme.textSecondary) }
                            }
                        } icon: { Image(systemName: beat.kind?.symbol ?? "square") }
                        if beat.kind != .image {
                            Text(tr("editor.charts_diagrams_and_other_scenes"))
                                .font(.footnote).foregroundStyle(Theme.textSecondary)
                        }
                    }
                    if beat.kind == .image { photoSection(beat) }
                }
                .navigationTitle(tr("editor.scene"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() }.disabled(model.narrationError(for: beatID) != nil) } }
                .interactiveDismissDisabled(model.narrationError(for: beatID) != nil)
            } else { ContentUnavailableView(tr("editor.scene_not_found"), systemImage: "questionmark") }
        }
        .presentationDetents([.large])
    }

    @ViewBuilder private func photoSection(_ beat: EditorBeat) -> some View {
        Section {
            if let photo = beat.photo, let url = photo.url, model.picks[beatID] == nil {
                AsyncImage(url: url) { $0.resizable().scaledToFill() } placeholder: { ProgressView() }
                    .frame(height: 180).frame(maxWidth: .infinity).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous))
                if let credit = photo.credit { Text(credit).font(.footnote).foregroundStyle(Theme.textSecondary) }
            } else if beat.photo?.noPhoto == true, model.picks[beatID] == nil {
                Label(tr("editor.no_suitable_photo_was_found"), systemImage: "photo.badge.exclamationmark")
                    .font(.callout).foregroundStyle(Theme.warning)
            }
            if let picked = model.picks[beatID], let c = beat.candidates.first(where: { $0.key == picked }) {
                Label(tr("editor.will_use_photo", c.creator), systemImage: "checkmark.circle.fill").foregroundStyle(Theme.success)
                Button(tr("editor.undo_photo_change")) { model.clearPick(for: beatID) }
            }
        } header: { Text(tr("editor.photo")) }
        if !beat.candidates.isEmpty {
            Section {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 10)], spacing: 10) {
                    ForEach(beat.candidates) { c in
                        let chosen = model.picks[beatID] == c.key || (model.picks[beatID] == nil && beat.photo?.chosen == c.key)
                        Button { model.pick(c, for: beatID) } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                AsyncImage(url: c.thumbURL) { $0.resizable().scaledToFill() } placeholder: { Theme.surfaceRaised }
                                    .frame(height: 90).frame(maxWidth: .infinity).clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                                    .overlay(alignment: .topTrailing) { if chosen { Image(systemName: "checkmark.circle.fill").foregroundStyle(.white, Theme.primary).padding(6) } }
                                Text(c.creator).font(.caption).foregroundStyle(Theme.text).lineLimit(1)
                                Text(c.provider == "unsplash" ? "Unsplash" : c.license.uppercased()).font(.caption2).foregroundStyle(Theme.textSecondary)
                            }
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(tr(chosen ? "editor.photo_by_selected" : "editor.photo_by", c.creator))
                    }
                }
            } header: { Text(tr("editor.other_photos")) } footer: { Text(tr("editor.credit_for_the_chosen_photo")) }
        }
    }
}
