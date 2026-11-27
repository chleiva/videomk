import AVKit
import SwiftUI
import VideoMKCore

/// Edit a finished video: its title, subtitles and scenes (reorder, delete, change the narration or the photo), then Preview (a quick draft)
/// or Publish. The same top bar, buttons and cards as the rest of the app; every wait says what is happening and can be left.
struct EditorView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var model: EditorModel?
    @State private var editMode: EditMode = .inactive
    @State private var selected: String?
    @State private var confirmDiscard = false
    let videoID: String

    var body: some View {
        VStack(spacing: 0) {
            TopBar(title: nil, leading: {
                IconButton(symbol: "xmark", label: tr("common.close"), identifier: "closeEditor") { if model?.isDirty == true { confirmDiscard = true } else { dismiss() } }
                Text(tr("editor.edit_video")).font(.role(.headline)).foregroundStyle(Theme.text).lineLimit(1).accessibilityAddTraits(.isHeader)
            }, trailing: {
                if model?.phase == .editing {
                    Button(editMode.isEditing ? tr("common.done") : tr("editor.reorder")) { withAnimation(Theme.Motion.spring) { editMode = editMode.isEditing ? .inactive : .active } }
                        .buttonStyle(TextButtonStyle()).accessibilityIdentifier("reorderScenes")
                }
            })
            Group {
                if let model { content(model) } else { EditorWait(title: tr("editor.loading")) }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Theme.background.ignoresSafeArea())
        .confirmationDialog(tr("editor.discard_your_changes"), isPresented: $confirmDiscard, titleVisibility: .visible) {
            Button(tr("editor.discard_changes"), role: .destructive) { dismiss() }
        }
        .environment(\.editMode, $editMode)
        .task {
            let m = EditorModel(videoID: videoID, app: app)
            model = m
            await m.load()
        }
    }

    @ViewBuilder private func content(_ model: EditorModel) -> some View {
        switch model.phase {
        case .loading: EditorWait(title: tr("editor.loading"))
        case .failed(let message):
            VStack(spacing: Theme.Space.l) {
                Image(systemName: "exclamationmark.triangle").font(.role(.title, weight: .regular)).foregroundStyle(Theme.warning).frame(width: 56, height: 56).background(Theme.warningContainer, in: Circle()).accessibilityHidden(true)
                Text(tr("editor.cant_edit_right_now")).textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center)
                Text(message).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                Button(tr("editor.reload")) { Task { await model.load() } }.buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("editorReload")
            }
            .padding(.horizontal, Theme.gutter).frame(maxWidth: .infinity, maxHeight: .infinity)
        case .rendering(let mode): RenderingView(mode: mode) { dismiss() }
        case .done(let mode): DoneView(mode: mode, url: model.resultURL, onKeepEditing: { model.keepEditing() }, onClose: { dismiss() })
        case .editing: editor(model)
        }
    }

    private func editor(_ model: EditorModel) -> some View {
        @Bindable var model = model
        return List {
            Group {
                if let banner = model.banner {
                    VStack(alignment: .leading, spacing: Theme.Space.s) {
                        Label(banner, systemImage: "exclamationmark.circle").labelStyle(DangerMarkLabel()).font(.role(.subhead)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("editorBanner")
                        Button(tr("editor.reload_and_discard_my_changes")) { Task { await model.load() } }.buttonStyle(TextButtonStyle())
                    }
                    .padding(Theme.Space.l).frame(maxWidth: .infinity, alignment: .leading).background(Theme.dangerContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                }
                VStack(alignment: .leading, spacing: Theme.Space.s) {
                    SectionLabel(tr("editor.title"))
                    SettingsCard {
                        TextField(tr("editor.title"), text: $model.title, axis: .vertical).font(.role(.body)).foregroundStyle(Theme.text).padding(.horizontal, Theme.Space.l).frame(minHeight: 52).accessibilityIdentifier("titleField")
                        SettingsDivider()
                        Toggle(isOn: $model.captions) { Label(tr("create.subtitles"), systemImage: "captions.bubble").font(.role(.body)).foregroundStyle(Theme.text) }
                            .tint(Theme.primary).padding(.horizontal, Theme.Space.l).frame(minHeight: 52).accessibilityIdentifier("captionsToggle")
                    }
                }
                SectionLabel(tr("editor.scenes_title", model.beats.count)).padding(.top, Theme.Space.s)
            }
            .listRowSeparator(.hidden).listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: Theme.Space.s, leading: Theme.gutter, bottom: Theme.Space.s, trailing: Theme.gutter))
            ForEach(model.beats) { beat in
                Button { selected = beat.id } label: { BeatRow(beat: beat, edited: model.isEdited(beat.id), error: model.narrationError(for: beat.id)) }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("beatRow")
                    .listRowSeparator(.hidden).listRowBackground(Color.clear).listRowInsets(EdgeInsets(top: Theme.Space.xs, leading: Theme.gutter, bottom: Theme.Space.xs, trailing: Theme.gutter))
            }
            .onMove { model.move(from: $0, to: $1) }
            .onDelete { model.delete(at: $0) }
        }
        .listStyle(.plain).scrollContentBackground(.hidden).environment(\.defaultMinListRowHeight, 1)
        .safeAreaInset(edge: .bottom, spacing: 0) { actionBar(model) }
        .sheet(item: Binding(get: { selected.map(SceneRef.init) }, set: { selected = $0?.id })) { ref in
            BeatEditorView(model: model, beatID: ref.id)
        }
    }

    /// Publish is the one primary; Preview is the labelled secondary. One line says what each needs.
    private func actionBar(_ model: EditorModel) -> some View {
        VStack(spacing: Theme.Space.s) {
            HStack(spacing: Theme.Space.s) {
                Button(tr("editor.preview")) { Task { await model.submit(.preview) } }
                    .buttonStyle(TonalButtonStyle()).disabled(!model.isDirty).accessibilityIdentifier("previewButton")
                Button(tr("editor.publish")) { Task { await model.submit(.final) } }
                    .buttonStyle(PrimaryButtonStyle()).disabled(!model.isDirty && !model.canPublishWithoutChanges).accessibilityIdentifier("publishButton")
            }
            Text(model.isDirty ? tr("editor.preview_is_a_quick_draft") : tr("editor.make_a_change_to_enable"))
                .font(.role(.caption)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.m).padding(.bottom, Theme.Space.s)
        .background(Theme.background.ignoresSafeArea(edges: .bottom))
        .dynamicTypeSize(...DynamicTypeSize.accessibility1)
    }
}

/// A wait inside the editor: what is happening, in words, beside the turning arc.
private struct EditorWait: View {
    let title: String
    var body: some View {
        HStack(spacing: Theme.Space.m) { LiveSpinner(); Text(title).font(.role(.headline)).foregroundStyle(Theme.text) }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .accessibilityElement(children: .combine).accessibilityIdentifier("editorWait")
    }
}

private struct SceneRef: Identifiable { let id: String }

/// One scene in the list: its picture or kind, how long it is, and the first lines of what is said. Read as one thing by VoiceOver:
/// kind, seconds, narration, and "edited" when it was changed.
struct BeatRow: View {
    let beat: EditorBeat
    let edited: Bool
    let error: String?

    private var kindName: String { beat.kind?.label ?? tr("editor.scene") }
    private var seconds: Int? { beat.duration.map { Int($0.rounded()) } }
    private var silent: Bool { beat.silent && beat.narration.isEmpty }
    private var silentText: String { tr("editor.silent_pause") + (beat.hold.map { ", \(Int($0.rounded())) s" } ?? "") }

    var body: some View {
        HStack(alignment: .top, spacing: Theme.Space.m) {
            ZStack {
                RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous).fill(Theme.surfaceRaised)
                if beat.kind == .image, let url = beat.photo?.url {
                    AsyncImage(url: url) { $0.resizable().scaledToFill() } placeholder: { Image(systemName: "photo").foregroundStyle(Theme.textSecondary) }
                        .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
                } else {
                    Image(systemName: beat.kind?.symbol ?? "square").font(.role(.headline)).foregroundStyle(Theme.primary)
                }
            }
            .frame(width: 72, height: 48)
            VStack(alignment: .leading, spacing: Theme.Space.xs) {
                HStack(spacing: Theme.Space.s) {
                    Text(kindName).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.text)
                    if let seconds { Text(verbatim: "\(seconds) s").font(.role(.footnote).monospacedDigit()).foregroundStyle(Theme.textSecondary) }
                    if edited { Label(tr("editor.edited"), systemImage: "pencil").font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.primary) }
                    else if beat.stale { Text(tr("editor.will_be_remade")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary) }
                }
                if silent {
                    Label(silentText, systemImage: "speaker.slash").font(.role(.subhead)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("silentBeatLabel")
                } else {
                    Text(beat.narration).font(.role(.subhead)).foregroundStyle(Theme.text).lineLimit(2).multilineTextAlignment(.leading)
                }
                if let error { Label(error, systemImage: "exclamationmark.circle").labelStyle(DangerMarkLabel()).font(.role(.footnote)).foregroundStyle(Theme.text) }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.textSecondary).padding(.top, Theme.Space.xs).accessibilityHidden(true)
        }
        .padding(Theme.Space.m)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken)
    }

    /// "Photo, 6 seconds. Sunlight pours through the canopy. Edited."
    private var spoken: String {
        var parts = [seconds.map { tr("editor.row_kind_seconds", $0, kindName) } ?? kindName, silent ? silentText : beat.narration]
        if edited { parts.append(tr("editor.edited")) } else if beat.stale { parts.append(tr("editor.will_be_remade")) }
        if let error { parts.append(error) }
        return parts.filter { !$0.isEmpty }.joined(separator: ". ")
    }
}

/// Publishing or making the preview: what is happening in words, and a way out (it keeps going on the server).
struct RenderingView: View {
    let mode: RenderMode
    var onClose: () -> Void = {}
    var body: some View {
        VStack(spacing: Theme.Space.l) {
            LiveSpinner(size: 34)
            Text(mode == .final ? tr("editor.publishing_your_video") : tr("editor.making_your_preview")).textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center)
            Text(tr("editor.only_the_scenes_you_changed")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            Button(tr("common.close"), action: onClose).buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("renderingClose")
            Text(tr("making.leave_promise")).font(.role(.caption)).foregroundStyle(Theme.textSecondary)
        }
        .padding(Theme.Space.xxl).frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityIdentifier("renderingView")
    }
}

struct DoneView: View {
    let mode: RenderMode
    let url: URL?
    let onKeepEditing: () -> Void
    let onClose: () -> Void
    @State private var player: AVPlayer?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                if let player {
                    InlinePlayer(player: player).aspectRatio(16 / 9, contentMode: .fit)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.hero, style: .continuous))
                }
                Text(mode == .final ? tr("editor.published") : tr("editor.preview_ready")).textRole(.title).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader).accessibilityIdentifier("doneTitle")
                if mode == .preview { Text(tr("editor.this_is_a_draft_publish")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true) }
                Button(mode == .final ? tr("common.done") : tr("editor.back_to_editing")) { mode == .final ? onClose() : onKeepEditing() }
                    .buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("doneButton")
            }
            .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s)
        }
        .onAppear { if let url, player == nil { player = AVPlayer(url: url) } }
        .onDisappear { player?.pause() }
    }
}
