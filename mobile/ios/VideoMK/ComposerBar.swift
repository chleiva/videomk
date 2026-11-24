import PhotosUI
import SwiftUI
import VideoMKCore

/// The "ask for a video" bar pinned to the bottom of the home screen: type or dictate, optionally set length and look, send.
/// Sending never leaves the screen; the new video appears as a row in the list above.
struct ComposerBar: View {
    @Binding var text: String
    @Binding var options: CreateOptions
    @Bindable var dictation: Dictation
    @Bindable var photos: PhotoAttachments
    var focus: FocusState<Bool>.Binding
    let credits: Int            // what this video would cost
    let balance: Int?           // nil until the wallet has loaded
    let onSend: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var affordable: Bool { balance.map { credits <= $0 } ?? true }
    private var canSend: Bool { Brief.isValid(text) && affordable }
    private var count: Int { Brief.normalized(text).count }

    var body: some View {
        VStack(spacing: 6) {
            if case .unavailable(let message) = dictation.state {
                HStack(alignment: .top, spacing: 8) {
                    Label(message, systemImage: "mic.slash").font(.footnote).foregroundStyle(Theme.warning)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("dictationUnavailable")
                    if message.contains("Settings") {
                        Button("Open Settings") { if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) } }
                            .font(.footnote.weight(.semibold)).accessibilityIdentifier("openSettingsButton")
                    }
                }
                .padding(.horizontal, 20)
                .transition(.opacity)
                .task(id: message) { try? await Task.sleep(for: .seconds(12)); dictation.clearHint() }
            }
            if case .keyboardHint(let message) = dictation.state {
                Label(message, systemImage: "keyboard").font(.footnote).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
                    .transition(.opacity)
                    .accessibilityIdentifier("dictationKeyboardHint")
                    .task { try? await Task.sleep(for: .seconds(8)); dictation.clearHint() }
            }
            if dictation.isListening {
                Label("Listening… tap the microphone when you're done", systemImage: "waveform").font(.footnote).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
                    .accessibilityIdentifier("listeningHint")
            } else if Brief.isValid(text) && !affordable {
                Label("This video needs \(credits) credit\(credits == 1 ? "" : "s") and you have \(balance ?? 0). Choose a shorter length.", systemImage: "exclamationmark.circle")
                    .font(.footnote).foregroundStyle(Theme.warning)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
                    .accessibilityIdentifier("notEnoughCredits")
            } else if !text.isEmpty && !Brief.isValid(text) {
                Text("A few more words, please (\(Brief.minLength - count) to go).").font(.footnote).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
            } else if Brief.isValid(text) {
                Text("\(credits) credit\(credits == 1 ? "" : "s")\(balance.map { " · you have \($0)" } ?? "")")
                    .font(.footnote).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
                    .accessibilityIdentifier("costLine")
            } else if count > Brief.maxLength - 200 {
                Text("\(count) / \(Brief.maxLength)").font(.footnote).foregroundStyle(count > Brief.maxLength ? Theme.danger : Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .trailing).padding(.horizontal, 20)
            }

            if !photos.isEmpty { AttachedPhotosStrip(photos: photos) }
            HStack(alignment: .bottom, spacing: 8) {
                optionsMenu
                HStack(alignment: .bottom, spacing: 4) {
                    TextField(photos.isEmpty ? "Describe a video…" : "What should the video be about?", text: $text, axis: .vertical)
                        .focused(focus)
                        .lineLimit(1...5)
                        .textInputAutocapitalization(.sentences)
                        .padding(.leading, 14).padding(.vertical, 10)
                        .accessibilityIdentifier("composerField")
                    photoButton
                    micButton
                }
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(dictation.isListening ? Theme.danger.opacity(0.6) : Theme.textSecondary.opacity(0.18), lineWidth: 1))
                if canSend {
                    Button(action: onSend) {
                        Image(systemName: "arrow.up.circle.fill").font(.system(size: 38)).foregroundStyle(Theme.gradient)
                    }
                    .accessibilityLabel("Make video").accessibilityIdentifier("sendButton")
                    .transition(reduceMotion ? .opacity : .scale.combined(with: .opacity))
                }
            }
            .padding(.horizontal, 12)
        }
        .padding(.top, 8).padding(.bottom, 8)
        .background(.bar)
        .animation(.snappy, value: canSend)
        .animation(.snappy, value: photos.items.count)
        .animation(.snappy, value: dictation.state)
    }

    private var photoButton: some View {
        let full = photos.remaining == 0
        let busy = photos.loading > 0
        return PhotosPicker(selection: $photos.picked, maxSelectionCount: max(1, photos.remaining), matching: .images) {
            Image(systemName: "photo.on.rectangle.angled")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(full ? Theme.textSecondary : Theme.primary)
                .frame(width: 40, height: 44)
                .contentShape(Rectangle())
        }
        .disabled(full || busy)
        .accessibilityLabel("Add photos")
        .accessibilityHint("Choose up to \(PhotoLimits.maxPhotos) of your photos to use in the video")
        .accessibilityIdentifier("photoButton")
    }

    private var micButton: some View {
        Button {
            Task { await dictation.toggle(currentText: text) }
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        } label: {
            Image(systemName: dictation.isListening ? "waveform" : "mic.fill")
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(dictation.isListening ? Theme.danger : Theme.primary)
                .symbolEffect(.variableColor.iterative, isActive: dictation.isListening && !reduceMotion)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(dictation.isListening ? "Stop dictation" : "Dictate")
        .accessibilityHint("Say what video you want instead of typing")
        .accessibilityIdentifier("micButton")
    }

    private var optionsMenu: some View {
        Menu {
            Picker("Length", selection: $options.minutes) {
                ForEach(CreateOptions.lengths, id: \.self) { Text("\(Int($0)) minutes").tag($0) }
            }
            Picker("Look", selection: $options.look) {
                Text("Producer decides").tag(VideoLook?.none)
                ForEach(VideoLook.allCases) { Text($0.title).tag(VideoLook?.some($0)) }
            }
            Toggle(isOn: $options.captions) { Label("Subtitles", systemImage: "captions.bubble") }
        } label: {
            VStack(spacing: 1) {
                Image(systemName: "slider.horizontal.3").font(.system(size: 17, weight: .semibold))
                Text("\(Int(options.minutes)) min").font(.system(size: 10, weight: .medium))
            }
            .foregroundStyle(Theme.primary)
            .frame(width: 44, height: 44)
            .background(Theme.surface, in: Circle())
        }
        .accessibilityLabel("Video options")
        .accessibilityValue("\(Int(options.minutes)) minutes, \(options.credits) credits, \(options.look?.title ?? "Producer decides the look"), subtitles \(options.captions ? "on" : "off")")
        .accessibilityIdentifier("optionsMenu")
    }
}
