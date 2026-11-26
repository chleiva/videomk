import Foundation

/// The canonical design tokens (docs/UX_REVIEW.md section 6, `docs/ux_review/tokens_v2.css`), with no UI framework so they are unit-tested:
/// the contrast test below the package walks `DesignTokens.colorPairs`. `Theme.swift` in the app only turns these numbers into `Color`s.
/// Android (`Theme.kt`) and web (`tokens.css`) mirror the same values: see "Token mirror" in mobile/ios/README.md.
public enum DesignTokens {
    /// One role: a light and a dark sRGB hex value.
    public struct Role: Sendable { public let light: UInt32; public let dark: UInt32
        public init(_ light: UInt32, _ dark: UInt32) { self.light = light; self.dark = dark }
        public func hex(dark isDark: Bool) -> UInt32 { isDark ? dark : light }
    }

    // MARK: colour (same names as Theme.swift / Theme.kt)
    public static let background = Role(0xF6F7FC, 0x0A0D1F)
    public static let surface = Role(0xFFFFFF, 0x11152B)
    public static let surface2 = Role(0xEEF0F9, 0x1A1F3B)
    public static let surface3 = Role(0xE2E5F4, 0x252B4D)
    public static let outline = Role(0xDADDEE, 0x2A3157)
    public static let text = Role(0x11142B, 0xF3F4FB)
    public static let textSecondary = Role(0x565D78, 0xA2A9C5)
    /// v2: was 6C7290 / 7C84A3, which failed AA on background and surface2.
    public static let textTertiary = Role(0x5F6585, 0x8A92B0)
    public static let primary = Role(0x4F52E0, 0x9EA0FF)
    public static let onPrimary = Role(0xFFFFFF, 0x0A0D1F)
    public static let primaryContainer = Role(0xE8E9FF, 0x25295A)
    public static let success = Role(0x127035, 0x4ADE80)
    public static let successContainer = Role(0xDDF3E4, 0x12301F)
    public static let warning = Role(0x9A4A06, 0xFBBF24)
    public static let warningContainer = Role(0xFDF0DA, 0x3A2B0C)
    public static let danger = Role(0xB91C1C, 0xF87171)
    public static let dangerContainer = Role(0xFCE4E4, 0x3B1517)
    public static let gradientStart = Role(0x5B5EF0, 0x8F92FF)
    public static let gradientEnd = Role(0x8452F4, 0xAE8AFF)
    public static let makingStart: UInt32 = 0x2B2F9A
    public static let makingEnd: UInt32 = 0x6A3FC4
    /// v2: the one "it is alive" accent (the former `secondary`), only for live progress.
    public static let live: UInt32 = 0x22D3EE

    // MARK: spacing (4 pt base), radii, sizes
    public enum Space { public static let xs: Double = 4, s: Double = 8, m: Double = 12, l: Double = 16, xl: Double = 20, xxl: Double = 24, xxxl: Double = 32
        public static let screenMargin: Double = 16, sheetMargin: Double = 20 }
    public enum Radius { public static let field: Double = 12, thumb: Double = 14, card: Double = 16, videoCard: Double = 22, composer: Double = 28, sheet: Double = 30 }
    public enum Size { public static let minTouch: Double = 44, thumbWidth: Double = 128, thumbHeight: Double = 72 }

    // MARK: elevation (level 2 and 3): colour alpha, blur radius, y offset; dark uses darker alphas
    public struct Shadow: Sendable { public let alphaLight: Double, alphaDark: Double, radius: Double, y: Double }
    public static let elevation2 = Shadow(alphaLight: 0.10, alphaDark: 0.45, radius: 12, y: 6)
    public static let elevation3 = Shadow(alphaLight: 0.18, alphaDark: 0.60, radius: 24, y: 10)

    // MARK: motion (seconds). Reduced motion: fades up to `reducedFade`, no scale, no shimmer.
    public enum Motion { public static let press: Double = 0.12, select: Double = 0.2, sheet: Double = 0.38, insert: Double = 0.28, shimmer: Double = 2.4, reducedFade: Double = 0.12 }

    // MARK: haptics: the only moments that vibrate
    public enum Haptic: String, CaseIterable, Sendable { case send, selection, warning, videoReady, uploadDone }

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
        Pair(name: "textSecondary/background", fg: textSecondary, bg: background, minimum: 4.5),
        Pair(name: "textSecondary/surface", fg: textSecondary, bg: surface, minimum: 4.5),
        Pair(name: "textSecondary/surface2", fg: textSecondary, bg: surface2, minimum: 4.5),
        Pair(name: "textTertiary/background", fg: textTertiary, bg: background, minimum: 4.5),
        Pair(name: "textTertiary/surface", fg: textTertiary, bg: surface, minimum: 4.5),
        Pair(name: "textTertiary/surface2", fg: textTertiary, bg: surface2, minimum: 4.5),
        Pair(name: "primary/background", fg: primary, bg: background, minimum: 4.5),
        Pair(name: "primary/surface", fg: primary, bg: surface, minimum: 4.5),
        Pair(name: "primary/primaryContainer", fg: primary, bg: primaryContainer, minimum: 4.5),
        Pair(name: "success/successContainer", fg: success, bg: successContainer, minimum: 4.5),
        Pair(name: "warning/warningContainer", fg: warning, bg: warningContainer, minimum: 4.5),
        Pair(name: "danger/dangerContainer", fg: danger, bg: dangerContainer, minimum: 4.5),
        Pair(name: "danger/surface", fg: danger, bg: surface, minimum: 4.5),
        Pair(name: "danger/background", fg: danger, bg: background, minimum: 4.5),
        Pair(name: "onPrimary/gradientStart", fg: onPrimary, bg: gradientStart, minimum: 4.5),
        Pair(name: "onPrimary/gradientEnd", fg: onPrimary, bg: gradientEnd, minimum: 4.5),
    ]
}
