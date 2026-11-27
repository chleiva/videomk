import AuthenticationServices
import SwiftUI
import VideoMKCore

/// Sign in (docs/DESIGN_BAR_2026.md, `phone_1_signin`): a full-bleed sample picture with the sentence that made it, the mark, the line, and the ways in.
/// Apple and Google are shown only when the build has them switched on; email is always there ("Use email", or the one primary button when it is the only way).
struct SignInView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var logoSize: CGFloat = 20

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .top) {
                Theme.background.ignoresSafeArea()
                sample(height: (geo.size.height + geo.safeAreaInsets.top) * 0.62, top: geo.safeAreaInsets.top)
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        BrandMark(size: 56).shadow(color: Theme.gradientStart.opacity(0.4), radius: 14, y: 8)
                        Text(tr("signin.tagline")).textRole(.largeTitle).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, Theme.Space.xl)
                            .accessibilityAddTraits(.isHeader)
                        VStack(spacing: Theme.Space.m) {
                            if let error = model.signInError {
                                Label(error, systemImage: "exclamationmark.circle").labelStyle(DangerMarkLabel()).font(.role(.footnote)).foregroundStyle(Theme.text).multilineTextAlignment(.center)
                                    .accessibilityIdentifier("signInError")
                            }
                            ForEach(model.authOptions.choices, id: \.self) { choice in
                                button(for: choice).dynamicTypeSize(...DynamicTypeSize.accessibility1)   // buttons stay readable; the page scrolls
                            }
                        }
                        .padding(.top, 28)
                        md(tr("signin.terms_md")).font(.role(.caption)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity).padding(.top, 22)
                    }
                    .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.xxl)
                    .background { VStack(spacing: 0) { LinearGradient(colors: [Theme.background.opacity(0), Theme.background], startPoint: .top, endPoint: .bottom).frame(height: 96); Theme.background }.padding(.top, -28).padding(.bottom, -400) }
                    .frame(maxWidth: 560)
                    .frame(maxWidth: .infinity, minHeight: geo.size.height, alignment: .bottom)
                }
                .scrollBounceBehavior(.basedOnSize)
            }
        }
        .background(Theme.background.ignoresSafeArea())
    }

    /// The sample: one frame of a video videomk made, and the sentence it was made from. It fades into the page.
    private func sample(height: CGFloat, top: CGFloat) -> some View {
        Color.clear.frame(maxWidth: .infinity).frame(height: height)
            .overlay { Image("SignInSample").resizable().scaledToFill() }.clipped()
            .overlay { LinearGradient(stops: [.init(color: Theme.mediaInk.opacity(0.3), location: 0), .init(color: .clear, location: 0.22), .init(color: .clear, location: 0.46), .init(color: Theme.background, location: 0.96)], startPoint: .top, endPoint: .bottom) }
            .overlay(alignment: .top) {
                HStack(spacing: Theme.Space.s) {
                    Image(systemName: "sparkle").font(.role(.footnote, weight: .bold)).foregroundStyle(Theme.live).accessibilityHidden(true)
                    Text(tr("signin.sample_title")).font(.role(.subhead, weight: .medium)).foregroundStyle(Theme.onMedia).lineLimit(2).multilineTextAlignment(.center)
                }
                .padding(.horizontal, Theme.Space.l).frame(minHeight: 40).background(Theme.mediaInk.opacity(0.6), in: Capsule())
                .padding(.top, top + Theme.Space.xxl).padding(.horizontal, Theme.gutter)
                .dynamicTypeSize(...DynamicTypeSize.accessibility1)
            }
            .ignoresSafeArea(edges: .top)
            .accessibilityHidden(typeSize.isAccessibilitySize)        // at the largest sizes the page scrolls over it
    }

    @ViewBuilder private func button(for choice: SignInChoice) -> some View {
        switch choice {
        case .apple: appleButton
        case .google: googleButton
        case .email: emailButton
        }
    }

    private func busy(_ c: SignInChoice) -> Bool { model.signingInWith == c }

    /// The system's own Sign in with Apple button (exact HIG styling and wording), in the pill shape. Its native flow is not used: the button is only drawn,
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
                .accessibilityLabel(tr("signin.apple"))
        }
        .frame(maxWidth: .infinity, minHeight: Theme.primaryHeight, maxHeight: Theme.primaryHeight)   // the system button's text does not grow, so its height is fixed
        .clipShape(Capsule())
        .disabled(model.isSigningIn)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("signInApple")
    }

    /// Google's branding: the four-colour "G" on Google's own light and dark surfaces with a hairline, "Continue with Google" in the system font.
    private var googleButton: some View {
        Button { Task { await model.signIn(.google) } } label: {
            HStack(spacing: 10) {
                if busy(.google) { ProgressView() } else { Image("GoogleG").resizable().scaledToFit().frame(width: logoSize, height: logoSize).accessibilityHidden(true) }
                Text(tr("signin.google")).font(.role(.headline)).fixedSize(horizontal: false, vertical: true)
            }
            .multilineTextAlignment(.center)
            .foregroundStyle(GoogleBrand.text)
            .frame(maxWidth: .infinity, minHeight: Theme.primaryHeight)
            .padding(.horizontal, Theme.Space.m)
            .background(GoogleBrand.surface, in: Capsule())
            .overlay(Capsule().strokeBorder(GoogleBrand.stroke, lineWidth: 1))
            .contentShape(Capsule())
        }
        .buttonStyle(PressScale())
        .disabled(model.isSigningIn)
        .accessibilityLabel(tr("signin.google"))
        .accessibilityIdentifier("signInGoogle")
    }

    /// Email is the one primary action when it is the only way in; next to Apple and Google it is the quiet "Use email".
    @ViewBuilder private var emailButton: some View {
        if model.authOptions.emailIsOnlyOption {
            Button { Task { await model.signIn() } } label: { if busy(.email) { ProgressView().tint(Theme.onPrimary) } else { Text(tr("signin.email")) } }
                .buttonStyle(PrimaryButtonStyle()).disabled(model.isSigningIn).accessibilityIdentifier("signInButton")
        } else {
            Button { Task { await model.signIn() } } label: {
                Group { if busy(.email) { ProgressView() } else { Text(tr("signin.use_email")).font(.role(.headline)).foregroundStyle(Theme.primary) } }
                    .frame(maxWidth: .infinity, minHeight: Theme.minTouch).contentShape(Rectangle())
            }
            .buttonStyle(.plain).disabled(model.isSigningIn).accessibilityIdentifier("signInButton")
        }
    }
}

/// Google's sign-in button colours (their branding rules fix these values; they are not part of our palette).
private enum GoogleBrand {
    static let surface = Theme.dyn(0xFFFFFF, 0x131314)
    static let text = Theme.dyn(0x1F1F1F, 0xE3E3E3)
    static let stroke = Theme.dyn(0x747775, 0x8E918F)
}
