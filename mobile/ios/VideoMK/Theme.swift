import SwiftUI
import VideoMKCore

/// Design tokens, exactly the numbers of docs/UI_DESIGN.md section (g). Semantic names only; views never use raw colours.
enum Theme {
    static func dyn(_ light: UInt32, _ dark: UInt32) -> Color { Color(light: .init(hex: light), dark: .init(hex: dark)) }

    static let background = dyn(0xF6F7FC, 0x0A0D1F)
    static let surface = dyn(0xFFFFFF, 0x11152B)          // surface1: cards, composer, sheets
    static let surfaceRaised = dyn(0xEEF0F9, 0x1A1F3B)    // surface2: fields, pills, tonal controls
    static let surface3 = dyn(0xE2E5F4, 0x252B4D)         // disabled send, tracks, pressed
    static let outline = dyn(0xDADDEE, 0x2A3157)
    static let text = dyn(0x11142B, 0xF3F4FB)
    static let textSecondary = dyn(0x565D78, 0xA2A9C5)
    static let textTertiary = dyn(0x6C7290, 0x7C84A3)
    static let primary = dyn(0x4F52E0, 0x9EA0FF)
    static let onPrimary = dyn(0xFFFFFF, 0x0A0D1F)
    static let primaryContainer = dyn(0xE8E9FF, 0x25295A)
    static let secondary = Color(hex: 0x22D3EE)
    static let success = dyn(0x127035, 0x4ADE80)
    static let successContainer = dyn(0xDDF3E4, 0x12301F)
    static let warning = dyn(0x9A4A06, 0xFBBF24)
    static let warningContainer = dyn(0xFDF0DA, 0x3A2B0C)
    static let danger = dyn(0xB91C1C, 0xF87171)
    static let dangerContainer = dyn(0xFCE4E4, 0x3B1517)
    static let gradientStart = dyn(0x5B5EF0, 0x8F92FF)
    static let gradientEnd = dyn(0x8452F4, 0xAE8AFF)
    static let makingStart = Color(hex: 0x2B2F9A)
    static let makingEnd = Color(hex: 0x6A3FC4)

    static let radius: CGFloat = 16
    static let gradient = LinearGradient(colors: [gradientStart, gradientEnd], startPoint: .topLeading, endPoint: .bottomTrailing)
    static let makingGradient = LinearGradient(colors: [makingStart, makingEnd], startPoint: .topLeading, endPoint: .bottomTrailing)
    /// Always dark, under white text on pictures.
    static let mediaScrim = LinearGradient(stops: [.init(color: .clear, location: 0.46), .init(color: Color(red: 8/255, green: 10/255, blue: 28/255).opacity(0.78), location: 1)], startPoint: .top, endPoint: .bottom)
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


/// Shadow levels 2 and 3 of the spec (light: tinted and soft; dark: darker, with a hairline ring instead).
struct Elevation: ViewModifier {
    let level: Int
    @Environment(\.colorScheme) private var scheme
    func body(content: Content) -> some View {
        content
            .shadow(color: scheme == .dark ? .black.opacity(level == 3 ? 0.6 : 0.45) : Color(red: 40/255, green: 44/255, blue: 110/255).opacity(level == 3 ? 0.18 : 0.10), radius: level == 3 ? 24 : 12, y: level == 3 ? 10 : 6)
    }
}
extension View {
    func elevation(_ level: Int) -> some View { modifier(Elevation(level: level)) }
}

/// A fix chip / small tonal chip: 32 pt drawn, 44 pt hit area.
struct FixChip: View {
    let title: String
    var tint: Color = Theme.primary
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            chipLabel.font(.system(size: 13, weight: .bold)).foregroundStyle(tint).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true).padding(.horizontal, 12).padding(.vertical, 7)
                .frame(minHeight: 32).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain).layoutPriority(1).accessibilityLabel(title.replacingOccurrences(of: " · ⚡", with: ", ").replacingOccurrences(of: "⚡", with: tr("a11y.credits_word")))
    }

    /// "Use 1 min · ⚡1": the bolt is the app's own symbol, not the emoji.
    @ViewBuilder private var chipLabel: some View {
        let parts = title.components(separatedBy: " · ⚡")
        if parts.count == 2 { HStack(spacing: 3) { Text(parts[0] + " ·"); Image(systemName: "bolt.fill").font(.system(size: 11)); Text(parts[1]) } }
        else { Text(title) }
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
