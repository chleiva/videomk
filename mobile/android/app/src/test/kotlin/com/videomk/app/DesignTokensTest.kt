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

    @Test fun tertiaryTextUsesTheV2Values() {
        assertEquals(0x5F6585, DesignTokens.textTertiary.light)
        assertEquals(0x8A92B0, DesignTokens.textTertiary.dark)
        assertEquals(0x22D3EE, DesignTokens.live)
    }

    @Test fun touchTargetIs48AndSpacingIsOnTheFourGrid() {
        assertEquals(48, DesignTokens.Size.minTouch)
        listOf(DesignTokens.Space.xs, DesignTokens.Space.s, DesignTokens.Space.m, DesignTokens.Space.l, DesignTokens.Space.xl, DesignTokens.Space.xxl, DesignTokens.Space.xxxl)
            .forEach { assertEquals(0, it % 4) }
    }
}
