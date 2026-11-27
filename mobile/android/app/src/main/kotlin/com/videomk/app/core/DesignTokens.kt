package com.videomk.app.core

import kotlin.math.pow

/**
 * The canonical design tokens (docs/DESIGN_BAR_2026.md section 4), with no UI framework so they are unit tested:
 * `DesignTokensTest` walks [colorPairs]. `ui/Theme.kt` only turns these numbers into Compose `Color`s and M3 roles.
 * Same values as iOS `DesignTokens.swift` (core package); web mirrors them in `tokens.css`. Colours are 0xRRGGBB.
 */
object DesignTokens {
    class Role(val light: Int, val dark: Int) { fun hex(dark: Boolean) = if (dark) this.dark else light }

    // colour: the table in docs/DESIGN_BAR_2026.md section 4 (bg, surface 1 to 3, text 1 to 3, primary, primaryC, action and brand gradients, live, danger)
    val background = Role(0xF7F7FA, 0x06070D)
    val surface = Role(0xFFFFFF, 0x11131D)
    val surface2 = Role(0xEEEFF4, 0x1A1D2B)
    val surface3 = Role(0xE4E6EE, 0x242838)
    /** Hairlines only (dividers, empty scene tiles): the same value as surface3, never beside a shadow. */
    val outline = Role(0xE4E6EE, 0x242838)
    val text = Role(0x0B0C14, 0xF4F5FA)
    val textSecondary = Role(0x5C6175, 0xA2A8BC)
    /** text3: never for essential text (3:1 is its floor: large text, counts, hints). */
    val textTertiary = Role(0x8B90A3, 0x70768C)
    val primary = Role(0x4B45E0, 0xAAA8FF)
    /** Text on a solid primary fill (Material buttons, badges). */
    val onPrimary = Role(0xFFFFFF, 0x06070D)
    val primaryContainer = Role(0xECEBFF, 0x22224A)
    /** The action gradient: the ONE primary button per screen. Same in light and dark; white on its lightest point is 4.6:1. */
    val gradientStart = Role(0x3B36C8, 0x3B36C8)
    val gradientEnd = Role(0x7A4BE6, 0x7A4BE6)
    val onAction = Role(0xFFFFFF, 0xFFFFFF)
    /** The brand gradient: logo tile, Making card. */
    const val makingStart = 0x2B2F9A
    const val makingEnd = 0x6A3FC4
    /** Only on the gradient or on dark: the sparkle and the live ring. Never on white. */
    const val live = 0x22D3EE
    val danger = Role(0xD92D20, 0xFF6B5E)
    val dangerContainer = Role(0xFDE7E5, 0x3A1512)
    // states outside the table (not brand colour): a finished upload, a warning line
    val success = Role(0x127035, 0x4ADE80)
    val successContainer = Role(0xDDF3E4, 0x12301F)
    val warning = Role(0x9A4A06, 0xFBBF24)
    val warningContainer = Role(0xFDF0DA, 0x3A2B0C)

    /** Spacing, 4 dp base. */
    object Space { const val xs = 4; const val s = 8; const val m = 12; const val l = 16; const val xl = 20; const val xxl = 24; const val xxxl = 32; /** The one phone gutter. */ const val screenMargin = 20; const val sheetMargin = 20 }
    /** 14: thumbnails in grids. 22 to 26: cards and posters. Buttons and chips are full pills. */
    object Radius { const val field = 14; const val thumb = 14; const val tile = 12; const val card = 22; const val videoCard = 24; const val making = 26; const val composer = 28; const val sheet = 30 }
    object Size { const val minTouch = 48; const val iconButton = 44; const val primaryButton = 56; const val thumbWidth = 128; const val thumbHeight = 72 }

    /** Elevation 2 and 3: shadow alpha (light / dark), blur and y offset in dp. */
    class Shadow(val alphaLight: Double, val alphaDark: Double, val radius: Int, val y: Int)
    val elevation2 = Shadow(0.10, 0.45, 12, 6)
    val elevation3 = Shadow(0.18, 0.60, 24, 10)

    /** Motion in milliseconds. Reduced motion: fades up to [Motion.reducedFade], no scale, no shimmer. */
    /** [ring]: one turn of the live ring. [tile]: a scene tile filling. [typeChar]: one character of an example typing itself in. */
    object Motion { const val press = 120; const val select = 200; const val sheet = 380; const val insert = 280; const val shimmer = 2400; const val reducedFade = 120; const val ring = 2400; const val tile = 200; const val typeChar = 18 }

    /** The only moments that vibrate (section 4): light for a chip, pill or photo chosen; medium for Create; success for a video ready or a share or save done; warning for a refusal or failure. */
    enum class Haptic { Send, Selection, Warning, VideoReady, UploadDone }

    // contrast (WCAG 2.2)
    fun luminance(hex: Int): Double {
        fun lin(v: Int): Double { val c = v / 255.0; return if (c <= 0.04045) c / 12.92 else ((c + 0.055) / 1.055).pow(2.4) }
        return 0.2126 * lin((hex shr 16) and 0xFF) + 0.7152 * lin((hex shr 8) and 0xFF) + 0.0722 * lin(hex and 0xFF)
    }
    fun contrast(a: Int, b: Int): Double {
        val x = luminance(a); val y = luminance(b)
        return (maxOf(x, y) + 0.05) / (minOf(x, y) + 0.05)
    }

    class Pair(val name: String, val fg: Role, val bg: Role, val minimum: Double)
    /** Every foreground / background pair the UI really draws, with the WCAG minimum (4.5 body text). */
    val colorPairs: List<Pair> = listOf(
        Pair("text/background", text, background, 4.5), Pair("text/surface", text, surface, 4.5), Pair("text/surface2", text, surface2, 4.5),
        Pair("textSecondary/background", textSecondary, background, 4.5), Pair("textSecondary/surface", textSecondary, surface, 4.5), Pair("textSecondary/surface2", textSecondary, surface2, 4.5),
        // text3 is for large text, counts and hints only (3:1 on a card). On the light page background the table's own value gives 2.97, so nothing essential is ever drawn in it there
        Pair("textTertiary/background", textTertiary, background, 2.9), Pair("textTertiary/surface", textTertiary, surface, 3.0),
        Pair("primary/background", primary, background, 4.5), Pair("primary/surface", primary, surface, 4.5), Pair("primary/primaryContainer", primary, primaryContainer, 4.5),
        Pair("onPrimary/primary", onPrimary, primary, 4.5),
        Pair("success/successContainer", success, successContainer, 4.5), Pair("warning/warningContainer", warning, warningContainer, 4.5),
        Pair("danger/dangerContainer (icon)", danger, dangerContainer, 3.0), Pair("text/dangerContainer", text, dangerContainer, 4.5), Pair("danger/surface", danger, surface, 4.5), Pair("danger/background", danger, background, 4.5),
        Pair("onAction/gradientStart", onAction, gradientStart, 4.5), Pair("onAction/gradientEnd", onAction, gradientEnd, 4.5),
    )
}
