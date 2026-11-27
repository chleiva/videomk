package com.videomk.app

import com.videomk.app.core.DesignTokens
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DesignTokensTest {
    @Test fun everyColourPairMeetsAA_inLightAndDark() {
        val failures = mutableListOf<String>()
        for (dark in listOf(false, true)) for (p in DesignTokens.colorPairs) {
            val r = DesignTokens.contrast(p.fg.hex(dark), p.bg.hex(dark))
            if (r < p.minimum) failures += "${p.name} ${if (dark) "dark" else "light"} = ${"%.2f".format(r)} < ${p.minimum}"
        }
        assertTrue(failures.joinToString("\n"), failures.isEmpty())
    }

    @Test fun contrastMathMatchesKnownValues() {
        assertEquals(21.0, DesignTokens.contrast(0x000000, 0xFFFFFF), 0.01)
        assertEquals(1.0, DesignTokens.contrast(0x123456, 0x123456), 0.001)
    }

    /** The table of docs/DESIGN_BAR_2026.md section 4, value by value: a token that drifts fails here. */
    @Test fun coloursAreTheDesignBarTable() {
        fun eq(light: Int, dark: Int, r: DesignTokens.Role) { assertEquals(light, r.light); assertEquals(dark, r.dark) }
        eq(0xF7F7FA, 0x06070D, DesignTokens.background)
        eq(0xFFFFFF, 0x11131D, DesignTokens.surface); eq(0xEEEFF4, 0x1A1D2B, DesignTokens.surface2); eq(0xE4E6EE, 0x242838, DesignTokens.surface3)
        eq(0x0B0C14, 0xF4F5FA, DesignTokens.text); eq(0x5C6175, 0xA2A8BC, DesignTokens.textSecondary); eq(0x8B90A3, 0x70768C, DesignTokens.textTertiary)
        eq(0x4B45E0, 0xAAA8FF, DesignTokens.primary); eq(0xECEBFF, 0x22224A, DesignTokens.primaryContainer)
        eq(0x3B36C8, 0x3B36C8, DesignTokens.gradientStart); eq(0x7A4BE6, 0x7A4BE6, DesignTokens.gradientEnd)
        eq(0xD92D20, 0xFF6B5E, DesignTokens.danger)
        assertEquals(0x2B2F9A, DesignTokens.makingStart); assertEquals(0x6A3FC4, DesignTokens.makingEnd)
        assertEquals(0x22D3EE, DesignTokens.live)
    }

    @Test fun whiteOnTheActionGradientHolds4_6AtItsLightestPoint() {
        assertTrue(DesignTokens.contrast(0xFFFFFF, DesignTokens.gradientEnd.light) >= 4.6)
        assertTrue(DesignTokens.contrast(0xFFFFFF, DesignTokens.gradientStart.light) > DesignTokens.contrast(0xFFFFFF, DesignTokens.gradientEnd.light))
    }

    @Test fun theGutterIsTwentyEverywhere() {
        assertEquals(20, DesignTokens.Space.screenMargin); assertEquals(20, DesignTokens.Space.sheetMargin)
    }

    @Test fun touchTargetIs48AndSpacingIsOnTheFourGrid() {
        assertEquals(48, DesignTokens.Size.minTouch)
        listOf(DesignTokens.Space.xs, DesignTokens.Space.s, DesignTokens.Space.m, DesignTokens.Space.l, DesignTokens.Space.xl, DesignTokens.Space.xxl, DesignTokens.Space.xxxl)
            .forEach { assertEquals(0, it % 4) }
    }
}
