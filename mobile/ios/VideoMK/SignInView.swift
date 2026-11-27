import AVFoundation
import SwiftUI
import VideoMKCore

/// Sign in (docs/DESIGN_BAR_2026.md, `phone_1_signin`): a full-bleed sample picture with the sentence that made it, the mark, the line, and the ways in.
/// Apple and Google are shown only when the build has them switched on; email is always there ("Use email", or the one primary button when it is the only way).
struct SignInView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @ScaledMetric(relativeTo: .body) private var logoSize: CGFloat = 20

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .top) {
                Theme.background.ignoresSafeArea()
                sample(height: (geo.size.height + geo.safeAreaInsets.top) * 0.62, top: geo.safeAreaInsets.top)
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        BrandMark(size: 56).shadow(color: Theme.gradientStart.opacity(0.4), radius: 14, y: 8)
                            .accessibilityElement().accessibilityLabel(tr("videos.videomk")).accessibilityAddTraits(.isImage)        // the mark names the app for VoiceOver
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
                            .frame(maxWidth: .infinity, minHeight: Theme.minTouch).padding(.top, Theme.Space.m)      // a 44 pt row: the two links are easy to hit
                            .accessibilityIdentifier("signInLegal")
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
            .overlay { Image("SignInSample").resizable().scaledToFill() }       // the still: what shows first, and all that shows with Reduce Motion
            .overlay { if !reduceMotion { SampleLoop().transition(.opacity) } }   // six silent seconds of a video videomk made, looping
            .clipped()
            .overlay { LinearGradient(stops: [.init(color: Theme.mediaInk.opacity(0.3), location: 0), .init(color: .clear, location: 0.22), .init(color: .clear, location: 0.46), .init(color: Theme.background, location: 0.96)], startPoint: .top, endPoint: .bottom) }
            .ignoresSafeArea(edges: .top)
            // the footage speaks for itself (the screen's budget is 12 words plus the buttons); VoiceOver still hears what it is
            .accessibilityElement().accessibilityLabel(tr("signin.sample_a11y", tr("signin.sample_title"))).accessibilityAddTraits(.isImage)
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

    /// Sign in with Apple, drawn to Apple's rules for a custom button (the logo and "Continue with Apple" in the system font, black on light and
    /// white on dark, never smaller than the other buttons) so its words grow with the text size like the Google button's. The system button's
    /// text does not scale; and its native flow could not be used anyway: Cognito takes the hosted-page flow, not a native Apple token.
    private var appleButton: some View {
        Button { Task { await model.signIn(.apple) } } label: {
            HStack(spacing: 8) {
                if busy(.apple) { ProgressView().tint(AppleBrand.text) } else { Image(systemName: "apple.logo").font(.role(.headline)).accessibilityHidden(true) }
                Text(tr("signin.apple")).font(.role(.headline)).fixedSize(horizontal: false, vertical: true)
            }
            .multilineTextAlignment(.center)
            .foregroundStyle(AppleBrand.text)
            .frame(maxWidth: .infinity, minHeight: Theme.primaryHeight)
            .padding(.horizontal, Theme.Space.m)
            .background(AppleBrand.surface, in: Capsule())
            .contentShape(Capsule())
        }
        .buttonStyle(PressScale())
        .disabled(model.isSigningIn)
        .accessibilityLabel(tr("signin.apple"))
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

/// Apple's sign-in button colours: black with white words in the light appearance, white with black words in the dark one.
private enum AppleBrand {
    static let surface = Theme.dyn(0x000000, 0xFFFFFF)
    static let text = Theme.dyn(0xFFFFFF, 0x000000)
}

/// The sample footage of the sign-in screen: `sample_signin.mp4` from the app bundle (six seconds, no sound track), filling its frame and looping.
/// It has no audio, so music playing on the phone is never interrupted. Nothing is drawn if the file is missing: the still underneath stays.
struct SampleLoop: UIViewRepresentable {
    func makeUIView(context: Context) -> LoopView { LoopView() }
    func updateUIView(_ view: LoopView, context: Context) {}
    static func dismantleUIView(_ view: LoopView, coordinator: ()) { view.stop() }

    final class LoopView: UIView {
        override class var layerClass: AnyClass { AVPlayerLayer.self }
        private var player: AVQueuePlayer?
        private var looper: AVPlayerLooper?
        private var observers: [NSObjectProtocol] = []

        override init(frame: CGRect) {
            super.init(frame: frame)
            isUserInteractionEnabled = false; isAccessibilityElement = false; alpha = 0
            guard let url = Bundle.main.url(forResource: "sample_signin", withExtension: "mp4") else { return }
            let item = AVPlayerItem(url: url)
            let p = AVQueuePlayer()
            p.isMuted = true; p.preventsDisplaySleepDuringVideoPlayback = false; p.allowsExternalPlayback = false
            looper = AVPlayerLooper(player: p, templateItem: item)
            (layer as? AVPlayerLayer)?.player = p
            (layer as? AVPlayerLayer)?.videoGravity = .resizeAspectFill
            player = p
            p.play()
            UIView.animate(withDuration: 0.6, delay: 0.3) { self.alpha = 1 }       // it fades in over the still
            observers.append(NotificationCenter.default.addObserver(forName: UIApplication.didBecomeActiveNotification, object: nil, queue: .main) { [weak self] _ in MainActor.assumeIsolated { self?.player?.play() } })
        }
        required init?(coder: NSCoder) { fatalError("not used") }

        func stop() { player?.pause(); looper = nil; player = nil; observers.forEach(NotificationCenter.default.removeObserver); observers = [] }
    }
}
