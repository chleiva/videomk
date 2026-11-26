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

struct DeleteAccountView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.dismiss) private var dismiss
    @State private var model = DeletionModel()
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            Group {
                if case .working(let stage) = model.state { progress(stage) } else { details }
            }
            .navigationTitle(tr("settings.delete_account"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { if !model.isWorking { Button(tr("common.cancel")) { dismiss() }.accessibilityIdentifier("deleteCancel") } } }
        }
        .interactiveDismissDisabled(model.isWorking)
    }

    // MARK: the confirmation page

    private var details: some View {
        ScrollViewReader { proxy in
        List {
            Section {
                Text(tr("delete.warning")).font(.headline).foregroundStyle(Theme.text)
            }
            Section(tr("delete.what_deleted")) {
                item("play.rectangle.on.rectangle", tr("delete.item.videos"), tr("delete.item.videos_sub"))
                item("photo.on.rectangle", tr("delete.item.media"), tr("delete.item.media_sub"))
                item("bolt.fill", tr("delete.item.credits"), tr("delete.item.credits_sub"))
                item("person.crop.circle", tr("delete.item.signin"), tr("delete.item.signin_sub"))
            }
            Section {
                Text(tr("delete.next.reauth"))
                Text(tr("delete.next.data"))
                Text(tr("delete.next.signin"))
            } header: { Text(tr("delete.what_next")) } footer: {
                markdown(tr("delete.footer_md"))
            }
            Section {
                TextField(tr("delete.word"), text: $model.typed)
                    .textInputAutocapitalization(.characters).autocorrectionDisabled().focused($focused)
                    .accessibilityLabel(tr("delete.type_a11y", tr("delete.word"))).accessibilityIdentifier("deleteConfirmField")
                if case .failed(let e) = model.state { errorBox(e).id("deleteErrorBox") }
            } header: { Text(tr("delete.type_header", tr("delete.word"))) }
            Section {
                Button { focused = false; Task { await model.delete(app: app) } } label: {
                    Text(isFailed ? tr("common.try_again") : tr("delete.confirm_button")).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                }
                .buttonStyle(DestructiveButtonStyle()).disabled(!model.canDelete).listRowInsets(.init(top: 8, leading: 16, bottom: 4, trailing: 16)).listRowBackground(Color.clear).listRowSeparator(.hidden)
                .accessibilityIdentifier("deleteConfirmButton")
                Button { dismiss() } label: { Text(tr("delete.keep")).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true) }
                    .buttonStyle(KeepButtonStyle()).listRowInsets(.init(top: 4, leading: 16, bottom: 8, trailing: 16)).listRowBackground(Color.clear).listRowSeparator(.hidden)
                    .accessibilityIdentifier("deleteKeepButton")
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .onAppear { if isFailed { scrollToError(proxy) } }          // the page is rebuilt after progress: bring the message into view
        .onChange(of: model.state) { if isFailed { scrollToError(proxy) } }
        }
    }

    private func scrollToError(_ proxy: ScrollViewProxy) {
        Task { try? await Task.sleep(for: .milliseconds(150)); withAnimation { proxy.scrollTo("deleteErrorBox", anchor: .center) } }
    }

    private func markdown(_ s: String) -> Text { Text((try? AttributedString(markdown: s)) ?? AttributedString(s)) }

    private var isFailed: Bool { if case .failed = model.state { true } else { false } }

    private func item(_ icon: String, _ title: String, _ detail: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).foregroundStyle(Theme.danger).frame(width: 26).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.body.weight(.semibold))
                Text(detail).font(.subheadline).foregroundStyle(Theme.textSecondary)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func errorBox(_ e: AccountError) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label { Text(e.message).fixedSize(horizontal: false, vertical: true) } icon: { Image(systemName: "exclamationmark.triangle.fill") }
                .font(.subheadline).foregroundStyle(Theme.danger)
            if e.offersEmail { Link(tr("delete.email_support"), destination: URL(string: "mailto:support@plorer.ai?subject=Delete%20my%20videomk%20account")!).font(.subheadline.weight(.semibold)) }
            if e == .uncertain || e == .network || e == .server || e == .reauthFailed || e == .reauthNotAccepted {
                Text(tr("delete.still_signed_in")).font(.footnote).foregroundStyle(Theme.textSecondary)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine).accessibilityIdentifier("deleteError")
    }

    // MARK: progress

    private func progress(_ stage: DeletionStage) -> some View {
        VStack(spacing: 16) {
            ProgressView().controlSize(.large)
            Text(stage == .checking ? tr("delete.progress.checking") : stage == .signingIn ? tr("delete.progress.signing_in") : tr("delete.progress.deleting"))
                .font(.title3.weight(.semibold)).multilineTextAlignment(.center).accessibilityIdentifier("deleteProgress")
            Text(tr("delete.progress.keep_open")).font(.subheadline).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
        }
        .padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
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
            VStack(spacing: 20) {
                Image(systemName: "checkmark.circle.fill").font(.vmk(64)).foregroundStyle(Theme.success).accessibilityHidden(true).padding(.top, 32)
                Text(tr("deleted.title")).font(.title.bold()).multilineTextAlignment(.center).foregroundStyle(Theme.text)
                    .accessibilityAddTraits(.isHeader).accessibilityIdentifier("deletedTitle")
                Text(tr("deleted.body"))
                    .font(.body).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
                if notice.assumed {
                    Text(tr("deleted.assumed"))
                        .font(.footnote).multilineTextAlignment(.center).foregroundStyle(Theme.textSecondary)
                }
                apple
                Button(tr("common.done")) { app.dismissDeletionNotice() }.buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("deletedDone").padding(.top, 8)
            }
            .padding(.horizontal, 24).padding(.bottom, 24).frame(maxWidth: 560).frame(maxWidth: .infinity)
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
                Text(tr("deleted.apple_step")).font(.headline)
                switch revoke {
                case .done:
                    Label(tr("deleted.apple_done"), systemImage: "checkmark.circle.fill").foregroundStyle(Theme.success).font(.subheadline)
                case .manual(let why):
                    Text(why == .cancelled ? tr("deleted.apple_closed") : tr("deleted.apple_failed")).font(.subheadline)
                    Text(AppleRevoke.manualSteps).font(.subheadline).foregroundStyle(Theme.textSecondary)
                    if notice.revokeToken != nil { revokeButton(tr("common.try_again")) }
                default:
                    Text(tr("deleted.apple_explain"))
                        .font(.subheadline).foregroundStyle(Theme.textSecondary)
                    revokeButton(tr("deleted.apple_remove"))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading).padding(16)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        }
    }

    private func revokeButton(_ title: String) -> some View {
        Button { Task { await runRevoke() } } label: {
            if revoke == .working { ProgressView() } else { Text(title).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true) }
        }
        .buttonStyle(KeepButtonStyle()).disabled(revoke == .working).accessibilityIdentifier("appleRevokeButton")
    }

    private func card(_ title: String, _ text: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.headline)
            Text(text).font(.subheadline).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(16)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .accessibilityElement(children: .combine).accessibilityIdentifier("appleManualCard")
    }

    private func runRevoke() async {
        revoke = .working
        let status = await app.revokeApple()
        revoke = status == .ok ? .done : .manual(status)
    }
}

private struct DestructiveButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.headline).foregroundStyle(.white).frame(maxWidth: .infinity, minHeight: 50).padding(.horizontal, 12)
            .background(Color(hex: 0xB91C1C).opacity(isEnabled ? 1 : 0.35), in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}

private struct KeepButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.headline).foregroundStyle(Theme.primary).frame(maxWidth: .infinity, minHeight: 50).padding(.horizontal, 12)
            .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.outline, lineWidth: 1))
            .contentShape(Rectangle()).opacity(configuration.isPressed ? 0.85 : 1)
    }
}
