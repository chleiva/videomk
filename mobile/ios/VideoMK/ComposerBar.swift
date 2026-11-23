import SwiftUI
import VideoMKCore

/// The "ask for a video" bar pinned to the bottom of the home screen: type or dictate, optionally set length and look, send.
/// Sending never leaves the screen; the new video appears as a row in the list above.
struct ComposerBar: View {
    @Binding var text: String
    @Binding var options: CreateOptions
    @Bindable var dictation: Dictation
    var focus: FocusState<Bool>.Binding
    let onSend: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var canSend: Bool { Brief.isValid(text) }
    private var count: Int { Brief.normalized(text).count }

    var body: some View {
        VStack(spacing: 6) {
            if case .unavailable(let message) = dictation.state {
                Label(message, systemImage: "mic.slash").font(.footnote).foregroundStyle(Theme.warning)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
                    .transition(.opacity)
                    .task { try? await Task.sleep(for: .seconds(4)); dictation.clearUnavailable() }
            }
            if dictation.isListening {
                Label("Listening… tap the microphone when you're done", systemImage: "waveform").font(.footnote).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
                    .accessibilityIdentifier("listeningHint")
            } else if !text.isEmpty && !canSend {
                Text("A few more words, please (\(Brief.minLength - count) to go).").font(.footnote).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 20)
            } else if count > Brief.maxLength - 200 {
                Text("\(count) / \(Brief.maxLength)").font(.footnote).foregroundStyle(count > Brief.maxLength ? Theme.danger : Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .trailing).padding(.horizontal, 20)
            }

            HStack(alignment: .bottom, spacing: 8) {
                optionsMenu
                HStack(alignment: .bottom, spacing: 4) {
                    TextField("Describe a video…", text: $text, axis: .vertical)
                        .focused(focus)
                        .lineLimit(1...5)
                        .textInputAutocapitalization(.sentences)
                        .padding(.leading, 14).padding(.vertical, 10)
                        .accessibilityIdentifier("composerField")
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
        .animation(.snappy, value: dictation.state)
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
        .accessibilityValue("\(Int(options.minutes)) minutes, \(options.look?.title ?? "Producer decides the look")")
        .accessibilityIdentifier("optionsMenu")
    }
}
