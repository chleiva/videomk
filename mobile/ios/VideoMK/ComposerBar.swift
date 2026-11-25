import SwiftUI
import VideoMKCore

/// The composer card, docked above the tab bar (docs/UI_DESIGN.md section e): photo strip, a 2-line field, ONE status line (price, reason and fix),
/// and the toolbar row: attach, options pill, mic, send. The send button is always drawn: tonal when it cannot act, never hidden.
struct ComposerBar: View {
    @Binding var text: String
    @Binding var options: CreateOptions
    @Bindable var dictation: Dictation
    @Bindable var photos: PhotoAttachments
    var focus: FocusState<Bool>.Binding
    let balance: Int?           // nil until the wallet has loaded (or unlimited)
    let onSend: () -> Void
    let onAttach: () -> Void
    let onOptions: () -> Void
    let onAddCredits: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(AppModel.self) private var model
    @State private var shake = 0
    @State private var flash = false

    private var totalPhotos: Int { ComposerPhotos.total(phone: photos.items.count + photos.loading, library: model.composerLibrary.count) }
    private var status: ComposerStatus {
        ComposerPlan.status(text: text, balance: balance, options: options, photos: totalPhotos, dictating: dictation.isListening)
    }
    private var unaffordable: Bool { status.kind == .notAffordable || status.kind == .noCredits }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            dictationHints
            if totalPhotos > 0 || photos.notice != nil { AttachedPhotosStrip(photos: photos, library: model.composerLibrary, media: model.media) { id in model.composerLibrary.removeAll { $0.id == id } }.padding(.bottom, 8) }
            TextField(totalPhotos == 0 ? "Describe your video…" : "What should the video be about?", text: $text, axis: .vertical)
                .focused(focus)
                .lineLimit(2...6)
                .font(.system(.body, design: .default))
                .tint(Theme.primary)
                .textInputAutocapitalization(.sentences)
                .foregroundStyle(dictation.isListening ? Theme.textSecondary : Theme.text)
                .frame(minHeight: 48, alignment: .topLeading)
                .accessibilityIdentifier("composerField")
            statusLine.padding(.top, 4).padding(.bottom, 8)
            toolbarRow
        }
        .padding(.top, 14).padding(.leading, 16).padding(.trailing, 12).padding(.bottom, 10)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous).stroke(dictation.isListening ? Theme.danger.opacity(0.6) : Theme.outline, lineWidth: 1))
        .elevation(3)
        .padding(.horizontal, 12).padding(.top, 6).padding(.bottom, 8)
        .animation(reduceMotion ? nil : .snappy, value: totalPhotos)
        .animation(reduceMotion ? nil : .snappy, value: status)
        .animation(.snappy, value: dictation.state)
        .onChange(of: model.composerLibrary.count, initial: true) { _, n in photos.libraryCount = n }
    }

    // MARK: status line

    private var statusLine: some View {
        let s = status
        let tint: Color = s.isProblem && s.kind != .tooShort ? (s.kind == .tooLong ? Theme.danger : Theme.warning) : s.kind == .photoHint ? Theme.text : Theme.textSecondary
        return VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 8) {
                Image(systemName: s.isProblem && s.kind != .tooShort ? "exclamationmark.triangle" : "bolt.fill").font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(s.isProblem && s.kind != .tooShort ? tint : Theme.primary).accessibilityHidden(true)
                Text(s.message).font(.system(size: 13, weight: .medium)).foregroundStyle(tint)
                    .fixedSize(horizontal: false, vertical: true)
                    .modifier(Shake(travel: reduceMotion ? 0 : 4, value: CGFloat(shake)))
                    .accessibilityIdentifier(unaffordable ? "notEnoughCredits" : s.kind == .photoHint ? "photoCapacityHint" : "costLine")
                Spacer(minLength: 4)
                if let fix = s.fix, s.kind != .photoHint { fixChip(fix) }
            }
            if let fix = s.fix, s.kind == .photoHint { fixChip(fix).padding(.leading, 21) }
        }
        .frame(minHeight: 28, alignment: .topLeading)
        .padding(.horizontal, flash ? 6 : 0).background(flash ? Theme.warningContainer : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("statusLine")
    }

    private func fixChip(_ fix: ComposerStatus.Fix) -> some View {
        FixChip(title: fix.title) { apply(fix) }
            .accessibilityLabel(fixLabel(fix))
            .accessibilityIdentifier("fixChip")
    }

    private func fixLabel(_ fix: ComposerStatus.Fix) -> String {
        switch fix {
        case .useMinutes(let m, let c): "Use \(ComposerPlan.plural(Int(m), "minute")) instead, \(ComposerPlan.plural(c, "credit"))"
        case .addCredits: "Add credits"
        }
    }

    private func apply(_ fix: ComposerStatus.Fix) {
        switch fix {
        case .useMinutes(let m, _): options.minutes = m; UISelectionFeedbackGenerator().selectionChanged()
        case .addCredits: onAddCredits()
        }
    }

    // MARK: toolbar row

    private var toolbarRow: some View {
        Group {
            if typeSize.isAccessibilitySize {
                VStack(spacing: 8) {
                    HStack(spacing: 8) { attachButton; optionsPill }
                    HStack(spacing: 8) { Spacer(); micButton; sendButton }
                }
            } else {
                HStack(spacing: 8) { attachButton; optionsPill; micButton; sendButton }
            }
        }
    }

    private var attachButton: some View {
        Button(action: onAttach) {
            Image(systemName: "photo.badge.plus").font(.system(size: 19, weight: .regular)).foregroundStyle(Theme.text)
                .frame(width: 44, height: 44).background(Theme.surfaceRaised, in: Circle())
                .overlay(alignment: .topTrailing) {
                    if totalPhotos > 0 {
                        Text("\(totalPhotos)").font(.system(size: 11, weight: .bold).monospacedDigit()).foregroundStyle(.white)
                            .padding(.horizontal, 6).frame(minWidth: 20, minHeight: 20).background(Theme.gradient, in: Capsule())
                            .overlay(Capsule().stroke(Theme.surface, lineWidth: 2)).offset(x: 8, y: -6)
                    }
                }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(dictation.isListening)
        .opacity(dictation.isListening ? 0.4 : 1)
        .accessibilityLabel("Add photos")
        .accessibilityValue(totalPhotos == 0 ? "" : "\(totalPhotos) selected")
        .accessibilityHint("Choose photos from this phone or My media")
        .accessibilityIdentifier("photoButton")
    }

    private var optionsPill: some View {
        Button(action: onOptions) {
            HStack(spacing: 8) {
                Image(systemName: "slider.horizontal.3").font(.system(size: 16, weight: .medium)).foregroundStyle(Theme.textSecondary)
                Text("\(Int(options.minutes)) min").font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.text)
                Text("·").foregroundStyle(Theme.textTertiary)
                HStack(spacing: 2) { Image(systemName: "bolt.fill").font(.system(size: 12)); Text("\(options.credits)").font(.system(size: 16, weight: .semibold).monospacedDigit()) }
                    .foregroundStyle(unaffordable ? Theme.warning : Theme.primary)
            }
            .lineLimit(1).minimumScaleFactor(0.8)
            .frame(maxWidth: .infinity, minHeight: 44)
            .background(unaffordable ? Theme.warningContainer : Theme.surfaceRaised, in: Capsule())
            .overlay(Capsule().stroke(Theme.warning, lineWidth: unaffordable ? 1.5 : 0))
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(dictation.isListening)
        .opacity(dictation.isListening ? 0.4 : 1)
        .accessibilityLabel("Video options")
        .accessibilityValue("\(ComposerPlan.plural(Int(options.minutes), "minute")), \(ComposerPlan.plural(options.credits, "credit")), \(options.look?.title ?? "Producer decides the look"), subtitles \(options.captions ? "on" : "off")")
        .accessibilityHint("Opens options")
        .accessibilityIdentifier("optionsMenu")
    }

    private var micButton: some View {
        Button {
            Task { await dictation.toggle(currentText: text) }
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        } label: {
            ZStack {
                if dictation.isListening {
                    Circle().fill(Theme.danger).frame(width: 44, height: 44)
                    Image(systemName: "stop.fill").font(.system(size: 16, weight: .bold)).foregroundStyle(.white)
                } else {
                    Image(systemName: "mic").font(.system(size: 20, weight: .regular)).foregroundStyle(Theme.textSecondary)
                }
            }
            .frame(width: 44, height: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(dictation.isListening ? "Stop dictation" : "Dictate")
        .accessibilityHint("Say what video you want instead of typing")
        .accessibilityAddTraits(.isToggle)
        .accessibilityIdentifier("micButton")
    }

    /// Always drawn: 52 pt circle, filled gradient when it can send, tonal when not. A tonal tap explains why.
    private var sendButton: some View {
        let ready = status.canSend
        return Button {
            if ready {
                UIImpactFeedbackGenerator(style: .medium).impactOccurred()
                onSend()
            } else {
                notReady()
            }
        } label: {
            Image(systemName: "arrow.up").font(.system(size: 21, weight: .semibold))
                .foregroundStyle(ready ? Color.white : Theme.textTertiary)
                .frame(width: 52, height: 52)
                .background { Circle().fill(Theme.surface3).opacity(ready ? 0 : 1); Circle().fill(Theme.gradient).opacity(ready ? 1 : 0) }
                .shadow(color: Theme.gradientStart.opacity(ready ? 0.35 : 0), radius: 10, y: 4)
                .contentShape(Circle())
        }
        .buttonStyle(SendPressStyle(reduceMotion: reduceMotion))
        .animation(reduceMotion ? nil : .easeOut(duration: 0.18), value: ready)
        .accessibilityLabel("Make video")
        .accessibilityValue(ready ? "Ready, costs \(ComposerPlan.plural(options.credits, "credit"))" : "Not ready. \(status.message)")
        .accessibilityHint(ready ? "Starts your video" : "Tells you what is missing")
        .accessibilityIdentifier("sendButton")
    }

    private func notReady() {
        UINotificationFeedbackGenerator().notificationOccurred(.warning)
        withAnimation(.linear(duration: 0.28)) { shake += 1 }
        withAnimation(.easeOut(duration: 0.15)) { flash = true }
        Task { try? await Task.sleep(for: .milliseconds(450)); withAnimation(.easeOut(duration: 0.2)) { flash = false } }
        UIAccessibility.post(notification: .announcement, argument: status.announcement)
    }

    // MARK: dictation hints (unchanged behaviour)

    @ViewBuilder private var dictationHints: some View {
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
            .padding(.bottom, 6)
            .transition(.opacity)
            .task(id: message) { try? await Task.sleep(for: .seconds(12)); dictation.clearHint() }
        }
        if case .keyboardHint(let message) = dictation.state {
            Label(message, systemImage: "keyboard").font(.footnote).foregroundStyle(Theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.bottom, 6)
                .transition(.opacity)
                .accessibilityIdentifier("dictationKeyboardHint")
                .task { try? await Task.sleep(for: .seconds(8)); dictation.clearHint() }
        }
        if dictation.isListening {
            Label("Listening… tap stop when you're done", systemImage: "waveform").font(.footnote).foregroundStyle(Theme.textSecondary)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.bottom, 6)
                .accessibilityIdentifier("listeningHint")
        }
    }
}

private struct SendPressStyle: ButtonStyle {
    let reduceMotion: Bool
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.scaleEffect(configuration.isPressed && !reduceMotion ? 0.94 : 1)
            .animation(reduceMotion ? nil : .spring(response: 0.25, dampingFraction: 0.6), value: configuration.isPressed)
    }
}

/// A short horizontal shake each time `value` goes up by one (animate the change with withAnimation).
struct Shake: GeometryEffect {
    var travel: CGFloat
    var value: CGFloat
    var animatableData: CGFloat {
        get { value }
        set { value = newValue }
    }
    func effectValue(size: CGSize) -> ProjectionTransform {
        let phase = value - value.rounded(.down)
        return ProjectionTransform(CGAffineTransform(translationX: travel * sin(phase * .pi * 4), y: 0))
    }
}
