import AuthenticationServices
import SwiftUI
import VideoMKCore

struct SignInView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    @ScaledMetric(relativeTo: .body) private var buttonHeight: CGFloat = 52
    @ScaledMetric(relativeTo: .body) private var logoSize: CGFloat = 20

    var body: some View {
        GeometryReader { geo in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 24)
                    VStack(spacing: 20) {
                        Image(systemName: "play.rectangle.fill")
                            .font(.system(size: 64))
                            .foregroundStyle(Theme.gradient)
                            .accessibilityHidden(true)
                        Text("videomk")
                            .font(.system(size: 40, weight: .bold, design: .rounded))
                            .foregroundStyle(Theme.text)
                        Text("Describe a video. We write it, voice it and draw it.")
                            .font(.title3)
                            .multilineTextAlignment(.center)
                            .foregroundStyle(Theme.textSecondary)
                            .padding(.horizontal, 32)
                    }
                    Spacer(minLength: 24)
                    VStack(spacing: 12) {
                        if let error = model.signInError {
                            Text(error).font(.footnote).foregroundStyle(Theme.danger).multilineTextAlignment(.center)
                                .accessibilityIdentifier("signInError")
                        }
                        ForEach(model.authOptions.choices, id: \.self) { choice in
                            button(for: choice).dynamicTypeSize(...DynamicTypeSize.accessibility1)   // buttons stay readable; the page scrolls
                        }
                        Text("By continuing you agree to the [Terms](https://videomk.com/terms) and [Privacy Policy](https://videomk.com/privacy).")
                            .font(.caption)
                            .foregroundStyle(Theme.textSecondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.horizontal, 24)
                    .padding(.bottom, 24)
                }
                .frame(maxWidth: 560)
                .frame(maxWidth: .infinity, minHeight: geo.size.height)
            }
        }
        .background(Theme.background.ignoresSafeArea())
    }

    @ViewBuilder private func button(for choice: SignInChoice) -> some View {
        switch choice {
        case .apple: appleButton
        case .google: googleButton
        case .email: emailButton
        }
    }

    private func busy(_ c: SignInChoice) -> Bool { model.signingInWith == c }

    /// The system's own Sign in with Apple button (exact HIG styling and wording). Its native flow is not used: the button is only drawn,
    /// and a transparent button on top starts the hosted-UI flow, because Cognito cannot take a native Apple token.
    private var appleButton: some View {
        ZStack {
            SignInWithAppleButton(.continue, onRequest: { _ in }, onCompletion: { _ in })
                .signInWithAppleButtonStyle(scheme == .dark ? .white : .black)
                .allowsHitTesting(false)
                .accessibilityHidden(true)
                .opacity(busy(.apple) ? 0.4 : 1)
            if busy(.apple) { ProgressView().tint(scheme == .dark ? .black : .white) }
            Button { Task { await model.signIn(.apple) } } label: { Color.clear }
                .accessibilityLabel("Continue with Apple")
        }
        .frame(maxWidth: .infinity, minHeight: min(buttonHeight, 64), maxHeight: min(buttonHeight, 64))   // the system button's text does not grow, so its height is capped
        .clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .disabled(model.isSigningIn)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("signInApple")
    }

    /// Google's branding: the four-colour "G" on a light (dark mode: #131314) surface with a hairline, "Continue with Google" in the system font.
    private var googleButton: some View {
        Button { Task { await model.signIn(.google) } } label: {
            HStack(spacing: 10) {
                if busy(.google) { ProgressView() } else { Image("GoogleG").resizable().scaledToFit().frame(width: logoSize, height: logoSize).accessibilityHidden(true) }
                Text("Continue with Google").font(.headline).fixedSize(horizontal: false, vertical: true)
            }
            .multilineTextAlignment(.center)
            .foregroundStyle(scheme == .dark ? Color(hex: 0xE3E3E3) : Color(hex: 0x1F1F1F))
            .frame(maxWidth: .infinity, minHeight: buttonHeight)
            .padding(.horizontal, 12)
            .background(scheme == .dark ? Color(hex: 0x131314) : .white, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(scheme == .dark ? Color(hex: 0x8E918F) : Color(hex: 0x747775), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(model.isSigningIn)
        .accessibilityLabel("Continue with Google")
        .accessibilityIdentifier("signInGoogle")
    }

    @ViewBuilder private var emailButton: some View {
        let only = model.authOptions.emailIsOnlyOption
        Button { Task { await model.signIn() } } label: {
            if busy(.email) { ProgressView().tint(only ? .white : Theme.primary) }
            else { Text(only ? "Sign in or create account" : "Continue with email").multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true) }
        }
        .buttonStyle(EmailButtonStyle(primary: only))
        .disabled(model.isSigningIn)
        .accessibilityIdentifier("signInButton")
    }
}

/// Primary look when email is the only way in (unchanged from before); a quiet outlined button next to Apple and Google.
private struct EmailButtonStyle: ButtonStyle {
    let primary: Bool
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(primary ? Color.white : Theme.primary)
            .frame(maxWidth: .infinity, minHeight: 52)
            .padding(.horizontal, 12)
            .background {
                if primary { RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).fill(Theme.gradient.opacity(isEnabled ? 1 : 0.4)) }
            }
            .overlay { if !primary { RoundedRectangle(cornerRadius: Theme.radius, style: .continuous).stroke(Theme.outline, lineWidth: 1) } }
            .opacity(configuration.isPressed ? 0.85 : 1)
    }
}
