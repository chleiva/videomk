import Foundation

/// The canonical design tokens: the table of docs/DESIGN_BAR_2026.md section 4 (the same numbers as `docs/design_bar/src/base.css`), with no UI
/// framework so they are unit-tested: the contrast test walks `DesignTokens.colorPairs`. `Theme.swift` in the app only turns these numbers into `Color`s.
public enum DesignTokens {
    /// One role: a light and a dark sRGB hex value.
    public struct Role: Sendable { public let light: UInt32; public let dark: UInt32
        public init(_ light: UInt32, _ dark: UInt32) { self.light = light; self.dark = dark }
        public func hex(dark isDark: Bool) -> UInt32 { isDark ? dark : light }
    }

    // MARK: colour. Content carries the colour; the interface is neutral; one accent.
    public static let background = Role(0xF7F7FA, 0x06070D)
    public static let surface = Role(0xFFFFFF, 0x11131D)
    public static let surface2 = Role(0xEEEFF4, 0x1A1D2B)
    public static let surface3 = Role(0xE4E6EE, 0x242838)
    /// The hairline (`--line`, 8% of the text colour) as a solid value on the page background.
    public static let outline = Role(0xE4E5EA, 0x1C1E2A)
    public static let text = Role(0x0B0C14, 0xF4F5FA)
    public static let textSecondary = Role(0x5C6175, 0xA2A8BC)
    /// Never for essential text (placeholders, decoration, a chevron): it is below 4.5:1 on purpose.
    public static let textTertiary = Role(0x8B90A3, 0x70768C)
    public static let primary = Role(0x4B45E0, 0xAAA8FF)
    /// On the action and brand gradients: white in both appearances (the gradients do not change with the appearance).
    public static let onPrimary = Role(0xFFFFFF, 0xFFFFFF)
    public static let primaryContainer = Role(0xECEBFF, 0x22224A)
    public static let success = Role(0x127035, 0x4ADE80)
    public static let successContainer = Role(0xDDF3E4, 0x12301F)
    public static let warning = Role(0x9A4A06, 0xFBBF24)
    public static let warningContainer = Role(0xFDF0DA, 0x3A2B0C)
    /// Delete only (and the mark of something that did not finish). Words next to it are in `text`.
    public static let danger = Role(0xD92D20, 0xFF6B5E)
    public static let dangerContainer = Role(0xFDECEA, 0x3A1512)
    /// The action gradient: the ONE primary button of a screen. Same in light and dark.
    public static let gradientStart = Role(0x3B36C8, 0x3B36C8)
    public static let gradientEnd = Role(0x7A4BE6, 0x7A4BE6)
    /// The brand gradient: the logo tile and the Making card.
    public static let makingStart: UInt32 = 0x2B2F9A
    public static let makingEnd: UInt32 = 0x6A3FC4
    /// The one "it is alive" accent, only on the gradient or on dark: the sparkle and the live ring. Never on white.
    public static let live: UInt32 = 0x22D3EE

    // MARK: type roles (platform text styles; a screen never names a point size)
    public enum TypeRole: String, CaseIterable, Sendable {
        case largeTitle, title, headline, body, subhead, footnote, caption
        /// The sentence on Create (the caret and "A video about…"): the one display size of the phone app, iOS Title 1. The mockup draws it at 26 to 30 pt.
        case prompt
        /// Point size and line height at the default text size (the table of section 4); the system scales both with Dynamic Type.
        public var size: Double { switch self { case .largeTitle: 34; case .prompt: 28; case .title: 22; case .headline, .body: 17; case .subhead: 15; case .footnote: 13; case .caption: 12 } }
        public var line: Double { switch self { case .largeTitle: 40; case .prompt: 34; case .title: 28; case .headline: 22; case .body: 24; case .subhead: 20; case .footnote: 18; case .caption: 16 } }
        public enum Weight: Sendable { case regular, medium, semibold, bold }
        public var weight: Weight { switch self { case .largeTitle, .title: .bold; case .headline, .prompt: .semibold; case .caption: .medium; default: .regular } }
        public var tracking: Double { self == .largeTitle ? -0.6 : self == .prompt ? -0.5 : self == .title ? -0.3 : 0 }
    }

    // MARK: spacing (4 pt base, 8 pt rhythm), radii, sizes
    public enum Space { public static let xs: Double = 4, s: Double = 8, m: Double = 12, l: Double = 16, xl: Double = 20, xxl: Double = 24, xxxl: Double = 32
        /// The screen gutter on a phone: one value, everywhere.
        public static let gutter: Double = 20
        public static let screenMargin: Double = gutter, sheetMargin: Double = gutter }
    /// 14 for thumbnails in grids, 22 to 26 for cards and posters, a full pill for buttons and chips.
    public enum Radius { public static let field: Double = 14, thumb: Double = 14, card: Double = 22, videoCard: Double = 24, hero: Double = 26, composer: Double = 28, sheet: Double = 30 }
    public enum Size { public static let minTouch: Double = 44, thumbWidth: Double = 128, thumbHeight: Double = 72
        /// The primary button and the live capsule; an icon button; the round New video button; a scene tile of the film strip.
        public static let primaryHeight: Double = 54, iconButton: Double = 44, fab: Double = 64, sceneTile: Double = 44 }

    // MARK: elevation (level 2 and 3): colour alpha, blur radius, y offset; dark uses darker alphas
    public struct Shadow: Sendable { public let alphaLight: Double, alphaDark: Double, radius: Double, y: Double }
    public static let elevation2 = Shadow(alphaLight: 0.07, alphaDark: 0.40, radius: 14, y: 4)
    public static let elevation3 = Shadow(alphaLight: 0.14, alphaDark: 0.60, radius: 40, y: 12)

    // MARK: motion (seconds). Springs, not linear tweens. Reduced motion: cross-fades up to `reducedFade`, no scale, the ring stands still.
    public enum Motion { public static let press: Double = 0.12, select: Double = 0.2, sheet: Double = 0.38, insert: Double = 0.28, shimmer: Double = 2.4, reducedFade: Double = 0.12
        public static let springResponse: Double = 0.35, springDamping: Double = 0.86
        /// The live ring turns once in this time; a scene tile fills in `tileFill`; the first play fades in over `reveal`.
        public static let ring: Double = 2.4, tileFill: Double = 0.2, reveal: Double = 0.3 }

    // MARK: haptics: the only moments that vibrate (section 4). Light: a chip, a pill or a photo chosen. Medium: Create. Success: video ready,
    // share completed, upload done. Warning: a refusal or a failure. Nothing for scrolling or typing.
    public enum Haptic: String, CaseIterable, Sendable { case send, selection, warning, videoReady, uploadDone, shareDone
        public enum Kind: Sendable { case light, medium, success, warning }
        public var kind: Kind { switch self { case .selection: .light; case .send: .medium; case .warning: .warning; case .videoReady, .uploadDone, .shareDone: .success } }
    }

    // MARK: contrast (WCAG 2.2)
    public static func luminance(_ hex: UInt32) -> Double {
        func lin(_ v: UInt32) -> Double { let c = Double(v) / 255; return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4) }
        return 0.2126 * lin((hex >> 16) & 0xFF) + 0.7152 * lin((hex >> 8) & 0xFF) + 0.0722 * lin(hex & 0xFF)
    }
    public static func contrast(_ a: UInt32, _ b: UInt32) -> Double {
        let (x, y) = (luminance(a), luminance(b)); return (max(x, y) + 0.05) / (min(x, y) + 0.05)
    }

    public struct Pair: Sendable { public let name: String, fg: Role, bg: Role, minimum: Double }
    /// Every foreground / background pair the UI really draws, with the WCAG minimum (4.5 body text, 3 large or graphical).
    public static let colorPairs: [Pair] = [
        Pair(name: "text/background", fg: text, bg: background, minimum: 4.5),
        Pair(name: "text/surface", fg: text, bg: surface, minimum: 4.5),
        Pair(name: "text/surface2", fg: text, bg: surface2, minimum: 4.5),
        Pair(name: "text/surface3", fg: text, bg: surface3, minimum: 4.5),
        Pair(name: "textSecondary/background", fg: textSecondary, bg: background, minimum: 4.5),
        Pair(name: "textSecondary/surface", fg: textSecondary, bg: surface, minimum: 4.5),
        Pair(name: "textSecondary/surface2", fg: textSecondary, bg: surface2, minimum: 4.5),
        Pair(name: "primary/background", fg: primary, bg: background, minimum: 4.5),
        Pair(name: "primary/surface", fg: primary, bg: surface, minimum: 4.5),
        Pair(name: "primary/surface2", fg: primary, bg: surface2, minimum: 4.5),
        Pair(name: "primary/primaryContainer", fg: primary, bg: primaryContainer, minimum: 4.5),
        Pair(name: "success/successContainer", fg: success, bg: successContainer, minimum: 4.5),
        Pair(name: "warning/warningContainer", fg: warning, bg: warningContainer, minimum: 4.5),
        Pair(name: "text/dangerContainer", fg: text, bg: dangerContainer, minimum: 4.5),
        Pair(name: "text/warningContainer", fg: text, bg: warningContainer, minimum: 4.5),
        Pair(name: "danger/surface", fg: danger, bg: surface, minimum: 4.5),
        Pair(name: "danger/background", fg: danger, bg: background, minimum: 4.5),
        // the danger mark (an icon) on its own container: graphical, 3:1. Words on that container are in `text`.
        Pair(name: "danger/dangerContainer", fg: danger, bg: dangerContainer, minimum: 3),
        Pair(name: "onPrimary/gradientStart", fg: onPrimary, bg: gradientStart, minimum: 4.5),
        // white on the lightest point of the action gradient: 4.6:1 is the bar of section 4
        Pair(name: "onPrimary/gradientEnd", fg: onPrimary, bg: gradientEnd, minimum: 4.6),
    ]
}
