import SwiftUI
import VideoMKCore

/// The app's colours, spacing, radii and motion: `DesignTokens` (docs/DESIGN_BAR_2026.md section 4) turned into SwiftUI values. Semantic names only;
/// a view never writes a hex value, a point size or a margin of its own.
enum Theme {
    static func dyn(_ light: UInt32, _ dark: UInt32) -> Color { Color(light: .init(hex: light), dark: .init(hex: dark)) }

    private static func role(_ r: DesignTokens.Role) -> Color { dyn(r.light, r.dark) }
    static let background = role(DesignTokens.background)
    static let surface = role(DesignTokens.surface)                 // cards, sheets
    static let surfaceRaised = role(DesignTokens.surface2)          // surface2: fields, pills, quiet icon buttons
    static let surface3 = role(DesignTokens.surface3)               // tracks, pressed
    static let outline = role(DesignTokens.outline)
    static let text = role(DesignTokens.text)
    static let textSecondary = role(DesignTokens.textSecondary)
    static let textTertiary = role(DesignTokens.textTertiary)       // placeholders and decoration only, never essential text
    static let primary = role(DesignTokens.primary)
    static let onPrimary = role(DesignTokens.onPrimary)
    static let primaryContainer = role(DesignTokens.primaryContainer)
    /// The one "it is alive" accent: the sparkle and the live ring, on the gradient or on dark only.
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
    static let toastSurface = Color(hex: DesignTokens.surface2.dark)
    static let toastAccent = Color(hex: DesignTokens.primary.dark)
    static let toastSuccess = Color(hex: DesignTokens.success.dark)
    /// The solid red of the one destructive confirm button (white text).
    static let dangerSolid = Color(hex: DesignTokens.danger.light)
    static let makingStart = Color(hex: DesignTokens.makingStart)
    static let makingEnd = Color(hex: DesignTokens.makingEnd)
    /// Scrims and chips that sit on pictures and video: always dark, whatever the appearance.
    static let mediaInk = Color(hex: DesignTokens.background.dark)
    static let onMedia = Color.white

    // Spacing, radii, sizes (one place: DesignTokens).
    enum Space { static let xs = CGFloat(DesignTokens.Space.xs), s = CGFloat(DesignTokens.Space.s), m = CGFloat(DesignTokens.Space.m), l = CGFloat(DesignTokens.Space.l), xl = CGFloat(DesignTokens.Space.xl), xxl = CGFloat(DesignTokens.Space.xxl), xxxl = CGFloat(DesignTokens.Space.xxxl) }
    /// The screen gutter: 20 pt, one value, everywhere.
    static let gutter = CGFloat(DesignTokens.Space.gutter)
    enum Radii { static let field = CGFloat(DesignTokens.Radius.field), thumb = CGFloat(DesignTokens.Radius.thumb), card = CGFloat(DesignTokens.Radius.card), videoCard = CGFloat(DesignTokens.Radius.videoCard), hero = CGFloat(DesignTokens.Radius.hero), composer = CGFloat(DesignTokens.Radius.composer), sheet = CGFloat(DesignTokens.Radius.sheet) }
    static let minTouch = CGFloat(DesignTokens.Size.minTouch)
    static let primaryHeight = CGFloat(DesignTokens.Size.primaryHeight)
    static let iconButton = CGFloat(DesignTokens.Size.iconButton)
    static let fab = CGFloat(DesignTokens.Size.fab)
    static let sceneTile = CGFloat(DesignTokens.Size.sceneTile)
    /// The floating tab bar (two tabs and the round New video button) and its margins: the room screens leave at the bottom so nothing hides under it.
    static let floatingBarHeight = CGFloat(84)
    /// Motion tokens; `Motion.animation(_, reduced:)` gives a short fade under Reduce Motion.
    enum Motion {
        static let press = Animation.easeOut(duration: DesignTokens.Motion.press)
        static let select = Animation.easeOut(duration: DesignTokens.Motion.select)
        static let insert = Animation.easeOut(duration: DesignTokens.Motion.insert)
        static let fade = Animation.easeOut(duration: DesignTokens.Motion.reducedFade)
        /// The one spring of the app (response 0.35, damping 0.86): things that move or change shape.
        static let spring = Animation.spring(response: DesignTokens.Motion.springResponse, dampingFraction: DesignTokens.Motion.springDamping)
        static let tile = Animation.easeOut(duration: DesignTokens.Motion.tileFill)
        static let reveal = Animation.easeOut(duration: DesignTokens.Motion.reveal)
        static func animation(_ a: Animation, reduced: Bool) -> Animation { reduced ? fade : a }
    }

    static let radius: CGFloat = Radii.card
    /// The action gradient: the ONE primary button of a screen.
    static let gradient = LinearGradient(colors: [gradientStart, gradientEnd], startPoint: .topLeading, endPoint: .bottomTrailing)
    /// The brand gradient: the logo tile and the Making card.
    static let makingGradient = LinearGradient(colors: [makingStart, makingEnd], startPoint: .topLeading, endPoint: .bottomTrailing)
    /// The colours of the live ring, in the order they turn.
    static let ringColors = [live, gradientEnd, gradientStart, live]
    /// Always dark, under white text on pictures.
    static let mediaScrim = LinearGradient(stops: [.init(color: .clear, location: 0.46), .init(color: mediaInk.opacity(0.78), location: 1)], startPoint: .top, endPoint: .bottom)
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
    init(light: Color, dark: Color) {
        self.init(UIColor { $0.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light) })
    }
}

/// Shadow levels 2 and 3 (one soft shadow per card; never a border and a shadow together).
struct Elevation: ViewModifier {
    let level: Int
    @Environment(\.colorScheme) private var scheme
    func body(content: Content) -> some View {
        let s = level == 3 ? DesignTokens.elevation3 : DesignTokens.elevation2
        content.shadow(color: scheme == .dark ? .black.opacity(s.alphaDark) : Theme.gradientStart.opacity(s.alphaLight), radius: s.radius, y: s.y)
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
            chipLabel.font(.role(.footnote, weight: .bold)).foregroundStyle(tint).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true).padding(.horizontal, 12).padding(.vertical, 7)
                .frame(minHeight: 32).background(Theme.primaryContainer, in: Capsule())
                .frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain).layoutPriority(1).accessibilityLabel(title.replacingOccurrences(of: " · ⚡", with: ", ").replacingOccurrences(of: "⚡", with: tr("a11y.credits_word")))
    }

    /// "Use 1 min · ⚡1": the bolt is the app's own symbol, not the emoji.
    @ViewBuilder private var chipLabel: some View {
        let parts = title.components(separatedBy: " · ⚡")
        if parts.count == 2 { HStack(spacing: 3) { Text(parts[0] + " ·"); Image(systemName: "bolt.fill").font(.role(.caption, weight: .regular)); Text(parts[1]) } }
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

/// The only moments that vibrate (DesignTokens.Haptic, section 4 of the design bar). System patterns only, so the system setting silences all of them.
@MainActor enum Haptics {
    static func play(_ h: DesignTokens.Haptic) {
        switch h.kind {
        case .light: UIImpactFeedbackGenerator(style: .light).impactOccurred()
        case .medium: UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        case .warning: UINotificationFeedbackGenerator().notificationOccurred(.warning)
        case .success: UINotificationFeedbackGenerator().notificationOccurred(.success)
        }
    }
}
