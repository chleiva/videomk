import SwiftUI

/// Brand tokens (from the "Midnight" look in docs/mobile/DESIGN_BRIEF.md). Semantic names only; views never use raw colours.
enum Theme {
    static let background = Color(light: .init(hex: 0xF6F7FB), dark: .init(hex: 0x0A0E20))
    static let surface = Color(light: .white, dark: .init(hex: 0x151A35))
    static let surfaceRaised = Color(light: .init(hex: 0xECEEF7), dark: .init(hex: 0x1E2347))
    static let text = Color(light: .init(hex: 0x111827), dark: .init(hex: 0xF8FAFC))
    static let textSecondary = Color(light: .init(hex: 0x5B6478), dark: .init(hex: 0xA5ADC4))
    static let primary = Color(hex: 0x6366F1)
    static let secondary = Color(hex: 0x22D3EE)
    static let success = Color(light: .init(hex: 0x15803D), dark: .init(hex: 0x4ADE80))
    static let warning = Color(light: .init(hex: 0xB45309), dark: .init(hex: 0xFBBF24))
    static let danger = Color(light: .init(hex: 0xB91C1C), dark: .init(hex: 0xF87171))

    static let radius: CGFloat = 16
    static let gradient = LinearGradient(colors: [primary, Color(hex: 0x8B5CF6)], startPoint: .topLeading, endPoint: .bottomTrailing)
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
    init(light: Color, dark: Color) {
        self.init(UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(Theme.gradient.opacity(isEnabled ? 1 : 0.4), in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.99 : 1)
    }
}

struct Card<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        content
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
    }
}
