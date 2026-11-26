package com.videomk.app.core

import kotlin.math.pow

/**
 * The canonical design tokens (docs/UX_REVIEW.md section 6, docs/ux_review/tokens_v2.css), with no UI framework so they are unit tested:
 * `DesignTokensTest` walks [colorPairs]. `ui/Theme.kt` only turns these numbers into Compose `Color`s and M3 roles.
 * Same values as iOS `DesignTokens.swift` (core package); web mirrors them in `tokens.css`. Colours are 0xRRGGBB.
 */
object DesignTokens {
    class Role(val light: Int, val dark: Int) { fun hex(dark: Boolean) = if (dark) this.dark else light }

    // colour (same names as Theme.kt / Theme.swift)
    val background = Role(0xF6F7FC, 0x0A0D1F)
    val surface = Role(0xFFFFFF, 0x11152B)
    val surface2 = Role(0xEEF0F9, 0x1A1F3B)
    val surface3 = Role(0xE2E5F4, 0x252B4D)
    val outline = Role(0xDADDEE, 0x2A3157)
    val text = Role(0x11142B, 0xF3F4FB)
    val textSecondary = Role(0x565D78, 0xA2A9C5)
    /** v2: was 6C7290 / 7C84A3, which failed AA on background and surface2. */
    val textTertiary = Role(0x5F6585, 0x8A92B0)
    val primary = Role(0x4F52E0, 0x9EA0FF)
    val onPrimary = Role(0xFFFFFF, 0x0A0D1F)
    val primaryContainer = Role(0xE8E9FF, 0x25295A)
    val success = Role(0x127035, 0x4ADE80)
    val successContainer = Role(0xDDF3E4, 0x12301F)
    val warning = Role(0x9A4A06, 0xFBBF24)
    val warningContainer = Role(0xFDF0DA, 0x3A2B0C)
    val danger = Role(0xB91C1C, 0xF87171)
    val dangerContainer = Role(0xFCE4E4, 0x3B1517)
    val gradientStart = Role(0x5B5EF0, 0x8F92FF)
    val gradientEnd = Role(0x8452F4, 0xAE8AFF)
    const val makingStart = 0x2B2F9A
    const val makingEnd = 0x6A3FC4
    /** The one "it is alive" accent (the former `secondary`), only for live progress. */
    const val live = 0x22D3EE

    /** Spacing, 4 dp base. */
    object Space { const val xs = 4; const val s = 8; const val m = 12; const val l = 16; const val xl = 20; const val xxl = 24; const val xxxl = 32; const val screenMargin = 16; const val sheetMargin = 20 }
    object Radius { const val field = 12; const val thumb = 14; const val card = 16; const val videoCard = 22; const val composer = 28; const val sheet = 30 }
    object Size { const val minTouch = 48; const val thumbWidth = 128; const val thumbHeight = 72 }

    /** Elevation 2 and 3: shadow alpha (light / dark), blur and y offset in dp. */
    class Shadow(val alphaLight: Double, val alphaDark: Double, val radius: Int, val y: Int)
    val elevation2 = Shadow(0.10, 0.45, 12, 6)
    val elevation3 = Shadow(0.18, 0.60, 24, 10)

    /** Motion in milliseconds. Reduced motion: fades up to [Motion.reducedFade], no scale, no shimmer. */
    object Motion { const val press = 120; const val select = 200; const val sheet = 380; const val insert = 280; const val shimmer = 2400; const val reducedFade = 120 }

    /** The only moments that vibrate. */
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
        Pair("textTertiary/background", textTertiary, background, 4.5), Pair("textTertiary/surface", textTertiary, surface, 4.5), Pair("textTertiary/surface2", textTertiary, surface2, 4.5),
        Pair("primary/background", primary, background, 4.5), Pair("primary/surface", primary, surface, 4.5), Pair("primary/primaryContainer", primary, primaryContainer, 4.5),
        Pair("success/successContainer", success, successContainer, 4.5), Pair("warning/warningContainer", warning, warningContainer, 4.5),
        Pair("danger/dangerContainer", danger, dangerContainer, 4.5), Pair("danger/surface", danger, surface, 4.5), Pair("danger/background", danger, background, 4.5),
        Pair("onPrimary/gradientStart", onPrimary, gradientStart, 4.5), Pair("onPrimary/gradientEnd", onPrimary, gradientEnd, 4.5),
    )
}
