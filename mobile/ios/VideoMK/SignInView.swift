import SwiftUI

struct SignInView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(spacing: 0) {
            Spacer()
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
            Spacer()
            VStack(spacing: 12) {
                if let error = model.signInError {
                    Text(error).font(.footnote).foregroundStyle(Theme.danger).multilineTextAlignment(.center)
                }
                Button {
                    Task { await model.signIn() }
                } label: {
                    if model.isSigningIn { ProgressView().tint(.white) } else { Text("Sign in or create account") }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(model.isSigningIn)
                .accessibilityIdentifier("signInButton")
                Text("By continuing you agree to the [Terms](https://videomk.com/terms) and [Privacy Policy](https://videomk.com/privacy).")
                    .font(.caption)
                    .foregroundStyle(Theme.textSecondary)
                    .multilineTextAlignment(.center)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.background.ignoresSafeArea())
    }
}
