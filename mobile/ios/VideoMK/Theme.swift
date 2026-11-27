import SwiftUI
import VideoMKCore

/// Design tokens, exactly the numbers of docs/UI_DESIGN.md section (g). Semantic names only; views never use raw colours.
enum Theme {
    static func dyn(_ light: UInt32, _ dark: UInt32) -> Color { Color(light: .init(hex: light), dark: .init(hex: dark)) }

    private static func role(_ r: DesignTokens.Role) -> Color { dyn(r.light, r.dark) }
    static let background = role(DesignTokens.background)
    static let surface = role(DesignTokens.surface)                 // surface1: cards, composer, sheets
    static let surfaceRaised = role(DesignTokens.surface2)          // surface2: fields, pills, tonal controls
    static let surface3 = role(DesignTokens.surface3)               // disabled send, tracks, pressed
    static let outline = role(DesignTokens.outline)
    static let text = role(DesignTokens.text)
    static let textSecondary = role(DesignTokens.textSecondary)
    static let textTertiary = role(DesignTokens.textTertiary)       // v2: AA on background and surface2
    static let primary = role(DesignTokens.primary)
    static let onPrimary = role(DesignTokens.onPrimary)
    static let primaryContainer = role(DesignTokens.primaryContainer)
    /// The one "it is alive" accent: live progress only.
    static let live = Color(hex: DesignTokens.live)
    static let secondary = live
    static let success = role(DesignTokens.success)
    static let successContainer = role(DesignTokens.successContainer)
    static let warning = role(DesignTokens.warning)
    static let warningContainer = role(DesignTokens.warningContainer)
    static let danger = role(DesignTokens.danger)
    static let dangerContainer = role(DesignTokens.dangerContainer)
    static let gradientStart = role(DesignTokens.gradientStart)
    static let gradientEnd = role(DesignTokens.gradientEnd)
    /// Toasts and the "soon" tip: always dark, so the same in both appearances.
    static let toastSurface = Color(hex: 0x23263F)
    static let toastAccent = Color(hex: 0xB9BBFF)
    static let toastSuccess = Color(hex: 0x4ADE80)
    /// The solid red of the one destructive confirm button (white text, 6.5:1).
    static let dangerSolid = Color(hex: 0xB91C1C)
    static let makingStart = Color(hex: DesignTokens.makingStart)
    static let makingEnd = Color(hex: DesignTokens.makingEnd)

    // Spacing, radii, sizes (one place: DesignTokens).
    enum Space { static let xs = CGFloat(DesignTokens.Space.xs), s = CGFloat(DesignTokens.Space.s), m = CGFloat(DesignTokens.Space.m), l = CGFloat(DesignTokens.Space.l), xl = CGFloat(DesignTokens.Space.xl), xxl = CGFloat(DesignTokens.Space.xxl), xxxl = CGFloat(DesignTokens.Space.xxxl) }
    enum Radii { static let field = CGFloat(DesignTokens.Radius.field), thumb = CGFloat(DesignTokens.Radius.thumb), card = CGFloat(DesignTokens.Radius.card), videoCard = CGFloat(DesignTokens.Radius.videoCard), composer = CGFloat(DesignTokens.Radius.composer), sheet = CGFloat(DesignTokens.Radius.sheet) }
    static let minTouch = CGFloat(DesignTokens.Size.minTouch)
    /// The floating tab bar (two tabs and the round New video button) and its margins: the room screens leave at the bottom so nothing hides under it.
    static let floatingBarHeight = CGFloat(84)
    /// Motion tokens; `Motion.animation(_, reduced:)` gives nil under Reduce Motion for movement, a short fade otherwise.
    enum Motion {
        static let press = Animation.easeOut(duration: DesignTokens.Motion.press)
        static let select = Animation.easeOut(duration: DesignTokens.Motion.select)
        static let insert = Animation.easeOut(duration: DesignTokens.Motion.insert)
        static let fade = Animation.easeOut(duration: DesignTokens.Motion.reducedFade)
        static func animation(_ a: Animation, reduced: Bool) -> Animation { reduced ? fade : a }
    }

    static let radius: CGFloat = Radii.card
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
            .foregroundStyle(Theme.onPrimary)
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
            chipLabel.font(.vmk(13, weight: .bold)).foregroundStyle(tint).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true).padding(.horizontal, 12).padding(.vertical, 7)
                .frame(minHeight: 32).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain).layoutPriority(1).accessibilityLabel(title.replacingOccurrences(of: " · ⚡", with: ", ").replacingOccurrences(of: "⚡", with: tr("a11y.credits_word")))
    }

    /// "Use 1 min · ⚡1": the bolt is the app's own symbol, not the emoji.
    @ViewBuilder private var chipLabel: some View {
        let parts = title.components(separatedBy: " · ⚡")
        if parts.count == 2 { HStack(spacing: 3) { Text(parts[0] + " ·"); Image(systemName: "bolt.fill").font(.vmk(11)); Text(parts[1]) } }
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

/// The only moments that vibrate (DesignTokens.Haptic): send, selection, warning, video ready, upload done.
enum Haptics {
    static func play(_ h: DesignTokens.Haptic) {
        switch h {
        case .send: UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        case .selection: UISelectionFeedbackGenerator().selectionChanged()
        case .warning: UINotificationFeedbackGenerator().notificationOccurred(.warning)
        case .videoReady, .uploadDone: UINotificationFeedbackGenerator().notificationOccurred(.success)
        }
    }
}
