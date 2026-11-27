import SwiftUI
import VideoMKCore

/// Re-authentication for account deletion (docs/ACCOUNT_DELETION.md section 2): end the hosted-UI session, then a normal authorize with
/// `prompt=login&max_age=0` in a private web session. The stored tokens are replaced only after a successful sign-in of the SAME account.
struct LiveDeletionAuth: DeletionAuth {
    let auth: AuthService
    let web: WebAuthenticator
    let config: AppConfig

    func authorization() async throws -> (idToken: String, userID: String) { try await auth.authorization() }

    func reauthenticate(expectedSub: String) async throws {
        do { _ = try await web.authenticate(url: await auth.logoutURL(), callbackScheme: config.callbackScheme, ephemeral: false) }
        catch AuthError.cancelled { throw AuthError.cancelled }     // the person closed the sheet: stop, nothing was sent
        catch { }                                                    // any other hiccup of the sign-out page: the private sign-in below does not need it
        try await SignInFlow.run {
            let callback = try await web.authenticate(url: await auth.beginReauth(), callbackScheme: config.callbackScheme, ephemeral: true)
            try await auth.completeReauth(callback: callback, expectedSub: expectedSub)
        }
    }
}

/// State of the confirmation sheet. The request itself runs in the flow (`AccountDeletionFlow`); this only mirrors it for the screen.
@MainActor @Observable
final class DeletionModel {
    enum State: Equatable { case confirm, working(DeletionStage), failed(AccountError) }
    var state: State = .confirm
    var typed = ""
    private var outcomeUnknown = false     // a request was sent and its answer never came: the retry goes straight to the server
    private var running = false

    var isWorking: Bool { if case .working = state { true } else { false } }
    var canDelete: Bool { AccountDeletionFlow.isConfirmation(typed) && !isWorking && !running }

    init() {
        #if DEBUG
        let env = ProcessInfo.processInfo.environment
        switch env["VMK_DEBUG_DELETE_STATE"] {
        case "typed": typed = "DELETE"
        case "working": typed = "DELETE"; state = .working(.sending)
        case "signingin": typed = "DELETE"; state = .working(.signingIn)
        case let s? where s.hasPrefix("error_"):
            typed = "DELETE"
            let map: [String: AccountError] = ["network": .network, "uncertain": .uncertain, "server": .server, "forbidden": .forbidden, "cancelled": .reauthCancelled,
                                               "stuck": .reauthNotAccepted, "wrong": .wrongAccount, "reauthfailed": .reauthFailed, "rejected": .requestRejected]
            state = .failed(map[String(s.dropFirst(6))] ?? .server)
        default: break
        }
        #endif
    }

    func delete(app: AppModel) async {
        guard canDelete, let flow = app.makeDeletionFlow() else { return }
        running = true; defer { running = false }
        state = .working(.checking)
        do {
            let accepted = try await flow.run(outcomeUnknown: outcomeUnknown) { [weak self] in self?.state = .working($0) }
            await app.finishDeletion(accepted)           // the screen is replaced by "Your account is being deleted"
        } catch let e as AccountError {
            if e == .uncertain { outcomeUnknown = true }
            if e == .signedOut { await app.signOut(); return }
            state = .failed(e)
            AccessibilityNotification.Announcement(e.message).post()
        } catch {
            state = .confirm
        }
    }
}

/// Delete account: the one place the app asks to confirm (rule 8). The app's own header, opaque cards, and its own pills: one solid red
/// destructive button, and "Keep my account" as the labelled way back.
struct DeleteAccountView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var model = DeletionModel()
    @FocusState private var focused: Bool

    var body: some View {
        Group {
            if case .working(let stage) = model.state { progress(stage) } else { details }
        }
        .presentationBackground(Theme.background).presentationDragIndicator(.visible)
        .interactiveDismissDisabled(model.isWorking)
    }

    // MARK: the confirmation page

    private var details: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Space.xl) {
                SheetHeader(title: tr("settings.delete_account"), closeLabel: tr("common.cancel"), closeID: "deleteCancel") { dismiss() }
                Text(tr("delete.warning")).font(.role(.headline)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                group(tr("delete.what_deleted")) {
                    SettingsCard {
                        item("play.rectangle.on.rectangle", tr("delete.item.videos"), tr("delete.item.videos_sub")); SettingsDivider()
                        item("photo.on.rectangle", tr("delete.item.media"), tr("delete.item.media_sub")); SettingsDivider()
                        item("bolt.fill", tr("delete.item.credits"), tr("delete.item.credits_sub")); SettingsDivider()
                        item("person.crop.circle", tr("delete.item.signin"), tr("delete.item.signin_sub"))
                    }
                }
                group(tr("delete.what_next")) {
                    VStack(alignment: .leading, spacing: Theme.Space.s) {
                        ForEach([tr("delete.next.reauth"), tr("delete.next.data"), tr("delete.next.signin")], id: \.self) { line in
                            Text(line).font(.role(.subhead)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                        }
                        markdown(tr("delete.footer_md")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).tint(Theme.primary).fixedSize(horizontal: false, vertical: true)
                    }
                }
                group(tr("delete.type_header", tr("delete.word"))) {
                    TextField(tr("delete.word"), text: $model.typed)
                        .font(.role(.body)).textInputAutocapitalization(.characters).autocorrectionDisabled().focused($focused)
                        .padding(.horizontal, Theme.Space.l).frame(minHeight: 52).background(Theme.surface, in: Capsule())
                        .accessibilityLabel(tr("delete.type_a11y", tr("delete.word"))).accessibilityIdentifier("deleteConfirmField")
                    if case .failed(let e) = model.state { errorBox(e).id("deleteErrorBox") }
                }
                VStack(spacing: Theme.Space.s) {
                    Button { focused = false; Task { await model.delete(app: app) } } label: {
                        Text(isFailed ? tr("common.try_again") : tr("delete.confirm_button")).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                    }
                    .buttonStyle(DestructiveButtonStyle()).disabled(!model.canDelete).accessibilityIdentifier("deleteConfirmButton")
                    Button(tr("delete.keep")) { dismiss() }.buttonStyle(TonalButtonStyle()).accessibilityIdentifier("deleteKeepButton")
                }
                .id("deleteButtons")
            }
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.xxl)
            .frame(maxWidth: 640).frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        // the word is right: the two buttons come into view above the keyboard (the keyboard stays: the person may still be typing)
        .onChange(of: model.typed) { _, t in if AccountDeletionFlow.isConfirmation(t) { withAnimation { proxy.scrollTo("deleteButtons", anchor: .bottom) } } }
        .onAppear { if isFailed { scrollToError(proxy) } }          // the page is rebuilt after progress: bring the message into view
        .onChange(of: model.state) { if isFailed { scrollToError(proxy) } }
        }
    }

    private func group<C: View>(_ title: String, @ViewBuilder content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.s) { SectionLabel(title); content() }
    }

    private func scrollToError(_ proxy: ScrollViewProxy) {
        Task { try? await Task.sleep(for: .milliseconds(150)); withAnimation { proxy.scrollTo("deleteErrorBox", anchor: .center) } }
    }

    private func markdown(_ s: String) -> Text { Text((try? AttributedString(markdown: s)) ?? AttributedString(s)) }

    private var isFailed: Bool { if case .failed = model.state { true } else { false } }

    private func item(_ icon: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: Theme.Space.m) {
            Image(systemName: icon).font(.role(.body)).foregroundStyle(Theme.danger).frame(width: 28).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.role(.body, weight: .semibold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                Text(detail).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Theme.Space.l).padding(.vertical, Theme.Space.m)
        .accessibilityElement(children: .combine)
    }

    private func errorBox(_ e: AccountError) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label { Text(e.message).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: "exclamationmark.circle") }
                .labelStyle(DangerMarkLabel()).font(.role(.subhead)).foregroundStyle(Theme.text)
            if e.offersEmail { Link(tr("delete.email_support"), destination: URL(string: "mailto:hello@videomk.com?subject=Delete%20my%20videomk%20account")!).font(.role(.subhead, weight: .semibold)).frame(minHeight: Theme.minTouch) }
            if e == .uncertain || e == .network || e == .server || e == .reauthFailed || e == .reauthNotAccepted {
                Text(tr("delete.still_signed_in")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(Theme.Space.l).frame(maxWidth: .infinity, alignment: .leading).background(Theme.dangerContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
        .accessibilityElement(children: .combine).accessibilityIdentifier("deleteError")
    }

    // MARK: progress

    private func progress(_ stage: DeletionStage) -> some View {
        VStack(spacing: Theme.Space.l) {
            LiveSpinner(size: 34)
            Text(stage == .checking ? tr("delete.progress.checking") : stage == .signingIn ? tr("delete.progress.signing_in") : tr("delete.progress.deleting"))
                .textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center).accessibilityIdentifier("deleteProgress")
            Text(tr("delete.progress.keep_open")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
        }
        .padding(Theme.Space.xl).frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.background.ignoresSafeArea())
    }
}

// MARK: - after the 202

struct AccountDeletedView: View {
    @Environment(AppModel.self) private var app
    let notice: AppModel.DeletionNotice
    @State private var revoke: Revoke = .idle
    enum Revoke: Equatable { case idle, working, done, manual(AppleRevoke.Status) }

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Space.xl) {
                Image(systemName: "checkmark.circle.fill").font(.vmk(64)).foregroundStyle(Theme.success).accessibilityHidden(true).padding(.top, Theme.Space.xxxl)
                Text(tr("deleted.title")).textRole(.largeTitle).multilineTextAlignment(.center).foregroundStyle(Theme.text)
                    .accessibilityAddTraits(.isHeader).accessibilityIdentifier("deletedTitle")
                Text(tr("deleted.body"))
                    .font(.role(.body)).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
                if notice.assumed {
                    Text(tr("deleted.assumed"))
                        .font(.role(.footnote)).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
                }
                apple
                Button(tr("common.done")) { app.dismissDeletionNotice() }.buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("deletedDone").padding(.top, 8)
            }
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.xxl).frame(maxWidth: 560).frame(maxWidth: .infinity)
        }
        .background(Theme.background.ignoresSafeArea())
        .accessibilityIdentifier("deletedScreen")
    }

    @ViewBuilder private var apple: some View {
        switch notice.apple {
        case .notLinked: EmptyView()
        case .revokeOff: card(tr("deleted.apple_title"), AppleRevoke.manualSteps)
        case .unknown: card(tr("deleted.apple_title"), tr("deleted.apple_unknown", AppleRevoke.manualSteps))
        case .revokeAvailable:
            VStack(alignment: .leading, spacing: 12) {
                Text(tr("deleted.apple_step")).font(.role(.headline)).foregroundStyle(Theme.text)
                switch revoke {
                case .done:
                    Label(tr("deleted.apple_done"), systemImage: "checkmark.circle.fill").foregroundStyle(Theme.text).font(.role(.subhead))
                case .manual(let why):
                    Text(why == .cancelled ? tr("deleted.apple_closed") : tr("deleted.apple_failed")).font(.role(.subhead)).foregroundStyle(Theme.text)
                    Text(AppleRevoke.manualSteps).font(.role(.subhead)).foregroundStyle(Theme.textSecondary)
                    if notice.revokeToken != nil { revokeButton(tr("common.try_again")) }
                default:
                    Text(tr("deleted.apple_explain"))
                        .font(.role(.subhead)).foregroundStyle(Theme.textSecondary)
                    revokeButton(tr("deleted.apple_remove"))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(Theme.Space.l)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
        }
    }

    private func revokeButton(_ title: String) -> some View {
        Button { Task { await runRevoke() } } label: {
            if revoke == .working { LiveSpinner() } else { Text(title).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true) }
        }
        .buttonStyle(TonalButtonStyle()).disabled(revoke == .working).accessibilityIdentifier("appleRevokeButton")
    }

    private func card(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.role(.headline)).foregroundStyle(Theme.text)
            Text(text).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(Theme.Space.l)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
        .accessibilityElement(children: .combine).accessibilityIdentifier("appleManualCard")
    }

    private func runRevoke() async {
        revoke = .working
        let status = await app.revokeApple()
        revoke = status == .ok ? .done : .manual(status)
    }
}

/// The one destructive confirm of the app: the primary's shape (a full pill), solid red, white words. Disabled: the opaque fill, like every pill.
private struct DestructiveButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.role(.headline)).foregroundStyle(isEnabled ? Theme.onMedia : Theme.textSecondary).padding(.horizontal, Theme.Space.xxl).padding(.vertical, Theme.Space.s)
            .frame(maxWidth: .infinity, minHeight: Theme.primaryHeight)
            .background(isEnabled ? Theme.dangerSolid : Theme.surface3, in: Capsule())
            .opacity(configuration.isPressed ? 0.85 : 1).contentShape(Capsule())
    }
}
