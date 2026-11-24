import AVKit
import SwiftUI
import VideoMKCore

struct EditorView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var model: EditorModel?
    @State private var editMode: EditMode = .inactive
    @State private var selected: String?
    @State private var confirmDiscard = false
    let videoID: String

    var body: some View {
        NavigationStack {
            Group {
                if let model {
                    content(model)
                } else { ProgressView() }
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("Edit video")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { if model?.isDirty == true { confirmDiscard = true } else { dismiss() } }
                        .disabled(model?.isLocked == true).accessibilityIdentifier("closeEditor")
                }
                ToolbarItem(placement: .confirmationAction) { if model?.phase == .editing { EditButton() } }
            }
            .confirmationDialog("Discard your changes?", isPresented: $confirmDiscard, titleVisibility: .visible) {
                Button("Discard changes", role: .destructive) { dismiss() }
            }
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
        case .loading: ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .failed(let message):
            ContentUnavailableView {
                Label("Can't edit right now", systemImage: "exclamationmark.triangle")
            } description: { Text(message) } actions: {
                Button("Reload") { Task { await model.load() } }.buttonStyle(.borderedProminent)
            }
        case .rendering(let mode): RenderingView(mode: mode)
        case .done(let mode): DoneView(mode: mode, url: model.resultURL, onKeepEditing: { model.keepEditing() }, onClose: { dismiss() })
        case .editing: editor(model)
        }
    }

    private func editor(_ model: EditorModel) -> some View {
        @Bindable var model = model
        return List {
            if let banner = model.banner {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(banner).font(.callout).foregroundStyle(Theme.danger).accessibilityIdentifier("editorBanner")
                        Button("Reload and discard my changes") { Task { await model.load() } }.font(.callout)
                    }
                }
            }
            Section("Title") {
                TextField("Title", text: $model.title).accessibilityIdentifier("titleField")
                Toggle("Subtitles", isOn: $model.captions).accessibilityIdentifier("captionsToggle")
            }
            Section {
                ForEach(model.beats) { beat in
                    Button { selected = beat.id } label: { BeatRow(beat: beat, edited: model.isEdited(beat.id), error: model.narrationError(for: beat.id)) }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("beatRow")
                }
                .onMove { model.move(from: $0, to: $1) }
                .onDelete { model.delete(at: $0) }
            } header: { Text("Scenes (\(model.beats.count))") } footer: {
                Text("Tap a scene to change its narration or photo. Use Edit to reorder or delete.")
            }
        }
        .scrollContentBackground(.hidden)
        .safeAreaInset(edge: .bottom) { actionBar(model) }
        .sheet(item: Binding(get: { selected.map(SceneRef.init) }, set: { selected = $0?.id })) { ref in
            BeatEditorView(model: model, beatID: ref.id)
        }
    }

    private func actionBar(_ model: EditorModel) -> some View {
        VStack(spacing: 8) {
            HStack(spacing: 12) {
                Button { Task { await model.submit(.preview) } } label: { Text("Preview").frame(maxWidth: .infinity, minHeight: 44) }
                    .buttonStyle(.bordered).disabled(!model.isDirty).accessibilityIdentifier("previewButton")
                Button { Task { await model.submit(.final) } } label: { Text("Publish").frame(maxWidth: .infinity) }
                    .buttonStyle(PrimaryButtonStyle()).disabled(!model.isDirty && !model.canPublishWithoutChanges).accessibilityIdentifier("publishButton")
            }
            Text(model.isDirty ? "Preview is a quick draft. Publish makes the full-quality video and replaces the current one." : "Make a change to enable Preview and Publish.")
                .font(.caption).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
        }
        .padding(.horizontal, 20).padding(.vertical, 10).background(.bar)
    }
}

private struct SceneRef: Identifiable { let id: String }

struct BeatRow: View {
    let beat: EditorBeat
    let edited: Bool
    let error: String?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous).fill(Theme.surfaceRaised)
                if beat.kind == .image, let url = beat.photo?.url {
                    AsyncImage(url: url) { $0.resizable().scaledToFill() } placeholder: { Image(systemName: "photo").foregroundStyle(Theme.textSecondary) }
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                } else {
                    Image(systemName: beat.kind?.symbol ?? "square").foregroundStyle(Theme.primary)
                }
            }
            .frame(width: 64, height: 44)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(beat.kind?.label ?? "Scene").font(.caption.weight(.semibold)).foregroundStyle(Theme.primary)
                    if let d = beat.duration { Text("\(Int(d.rounded())) s").font(.caption).foregroundStyle(Theme.textSecondary) }
                    if edited { Text("Edited").font(.caption.weight(.semibold)).foregroundStyle(Theme.warning) }
                    else if beat.stale { Text("Will be re-made").font(.caption).foregroundStyle(Theme.textSecondary) }
                }
                if beat.silent && beat.narration.isEmpty {
                    Label("Silent pause" + (beat.hold.map { ", \(Int($0.rounded())) s" } ?? ""), systemImage: "speaker.slash").font(.callout).foregroundStyle(Theme.textSecondary)
                        .accessibilityIdentifier("silentBeatLabel")
                } else {
                    Text(beat.narration).font(.callout).foregroundStyle(Theme.text).lineLimit(2)
                }
                if let error { Text(error).font(.caption).foregroundStyle(Theme.danger) }
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }
}

struct RenderingView: View {
    let mode: RenderMode
    var body: some View {
        VStack(spacing: 18) {
            ProgressView().controlSize(.large)
            Text(mode == .final ? "Publishing your video" : "Making your preview").font(.title3.bold()).foregroundStyle(Theme.text)
            Text("Only the scenes you changed are re-made, so this is usually quick. You can't edit while it renders.")
                .font(.callout).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
        }
        .padding(32).frame(maxWidth: .infinity, maxHeight: .infinity)
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
            VStack(spacing: 16) {
                Text(mode == .final ? "Published" : "Preview ready").font(.title2.bold()).foregroundStyle(Theme.text).accessibilityIdentifier("doneTitle")
                if let player {
                    InlinePlayer(player: player).aspectRatio(16 / 9, contentMode: .fit)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                }
                if mode == .preview { Text("This is a draft. Publish from the editor to make the full-quality video.").font(.callout).foregroundStyle(Theme.textSecondary) }
                Button(mode == .final ? "Done" : "Back to editing") { mode == .final ? onClose() : onKeepEditing() }
                    .buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("doneButton")
            }.padding(20)
        }
        .onAppear { if let url, player == nil { player = AVPlayer(url: url) } }
        .onDisappear { player?.pause() }
    }
}
