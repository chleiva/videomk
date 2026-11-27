import SwiftUI
import UIKit
import VideoMKCore

/// "Send feedback" sheet (docs/FEEDBACK.md). One multi-line field, optional kind chips, Send pinned above the keyboard (so nothing is covered on a small
/// phone), a calm thank-you, and failures that keep the text. Opened from Settings, after a video and from the rating prompt ("Not really").
struct FeedbackSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var composer: FeedbackComposer
    @FocusState private var focused: Bool
    private let intro: String

    init(composer: FeedbackComposer, intro: String? = nil) {
        _composer = State(initialValue: composer)
        self.intro = intro ?? tr("feedback.intro")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                // the app's own header: the title never sits against a Cancel button, in any language
                SheetHeader(title: tr("feedback.title"), closeLabel: composer.phase == .sent ? tr("common.close") : tr("common.cancel"), closeID: "feedbackCancel") { dismiss() }
                if composer.phase == .sent { thanks } else { form }
            }
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.l)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) { bottomBar }
        .sensoryFeedback(.success, trigger: composer.phase == .sent)       // the only haptic: a light success when it was sent
        .onChange(of: composer.phase) { _, phase in
            if case .failed(let e) = phase { AccessibilityNotification.Announcement(e.message).post() }
            if phase == .sent { AccessibilityNotification.Announcement(tr("feedback.thanks_title")).post() }
        }
        .presentationBackground(Theme.surface).presentationDragIndicator(.visible)
    }

    // MARK: form

    @ViewBuilder private var form: some View {
        Text(intro).font(.role(.body)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("feedbackIntro")
        VStack(alignment: .leading, spacing: 6) {
            ZStack(alignment: .topLeading) {
                TextEditor(text: $composer.text)
                    .font(.role(.body)).foregroundStyle(Theme.text)
                    .scrollContentBackground(.hidden)
                    .focused($focused)
                    .frame(minHeight: 140)
                    .padding(.horizontal, 10).padding(.vertical, 8)
                    .disabled(composer.isSending)
                    .accessibilityLabel(tr("feedback.field_label"))
                    .accessibilityIdentifier("feedbackField")
                if composer.text.isEmpty {
                    Text(tr("feedback.placeholder")).font(.role(.body)).foregroundStyle(Theme.textTertiary)
                        .padding(.horizontal, 15).padding(.vertical, 16).allowsHitTesting(false).accessibilityHidden(true)
                }
            }
            .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
            HStack(alignment: .firstTextBaseline) {
                if needsMore { Text(tr("feedback.min_hint")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true) }
                Spacer(minLength: 8)
                Text(tr("feedback.counter", composer.count, FeedbackRules.maxLength)).font(.role(.footnote)).monospacedDigit()
                    .foregroundStyle(composer.count >= FeedbackRules.maxLength - 100 ? Theme.warning : Theme.textSecondary)
                    .accessibilityLabel(tr("feedback.counter_a11y", composer.count, FeedbackRules.maxLength))
                    .accessibilityIdentifier("feedbackCounter")
            }
        }
        VStack(alignment: .leading, spacing: 8) {
            Text(tr("feedback.kind_label")).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.textSecondary)
            (typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8)) : AnyLayout(HStackLayout(spacing: 8))) {
                ForEach(FeedbackKind.allCases, id: \.self) { chip($0) }
            }
        }
        if case .failed(let e) = composer.phase {
            Label { Text(e.message).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: "exclamationmark.circle") }
                .font(.role(.subhead)).foregroundStyle(Theme.text)
                .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.warningContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                .accessibilityIdentifier("feedbackError")
        }
    }

    private var needsMore: Bool { let n = FeedbackRules.trimmed(composer.text).count; return n > 0 && n < FeedbackRules.minLength }

    private func label(_ k: FeedbackKind) -> String {
        switch k { case .idea: tr("feedback.kind.idea"); case .problem: tr("feedback.kind.problem"); case .other: tr("feedback.kind.other") }
    }

    private func chip(_ k: FeedbackKind) -> some View {
        ChoiceChip(title: label(k), selected: composer.kind == k, fullWidth: typeSize.isAccessibilitySize, identifier: "feedbackKind_\(k.rawValue)") { composer.choose(k); Haptics.play(.selection) }
            .disabled(composer.isSending)
    }

    // MARK: thanks

    private var thanks: some View {
        VStack(spacing: 14) {
            Image(systemName: "checkmark.circle.fill").font(.vmk(56)).foregroundStyle(Theme.success).accessibilityHidden(true)
                .transition(reduceMotion ? .opacity : .scale.combined(with: .opacity))
            Text(tr("feedback.thanks_title")).font(.role(.title, weight: .bold)).foregroundStyle(Theme.text).accessibilityAddTraits(.isHeader)
            Text(tr("feedback.thanks_body")).font(.role(.body)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity).padding(.top, 40)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("feedbackThanks")
    }

    // MARK: bottom

    private var bottomBar: some View {
        Group {
            if composer.phase == .sent {
                Button(tr("common.done")) { dismiss() }.buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("feedbackDone")
            } else {
                Button { Task { await composer.send() } } label: {
                    if composer.isSending { HStack(spacing: Theme.Space.s) { ProgressView().tint(Theme.textSecondary); Text(tr("feedback.sending")) } }
                    else { Text(retry ? tr("common.try_again") : tr("feedback.send")).multilineTextAlignment(.center) }
                }
                .buttonStyle(PrimaryButtonStyle()).disabled(!composer.canSend).accessibilityIdentifier("feedbackSend")
            }
        }
        .padding(.horizontal, Theme.gutter).padding(.vertical, Theme.Space.m)
        .background(Theme.surface)
    }

    private var retry: Bool { if case .failed = composer.phase { true } else { false } }
}

