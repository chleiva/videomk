package com.videomk.app.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.RowScope
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp

/** Brand tokens (from the "Midnight" look in docs/mobile/DESIGN_BRIEF.md), the same values as the iOS Theme.swift. */
@Immutable
data class VmkColors(
    val background: Color, val surface: Color, val surfaceRaised: Color, val text: Color, val textSecondary: Color,
    val primary: Color, val secondary: Color, val success: Color, val warning: Color, val danger: Color,
    // design tokens (docs/UI_DESIGN.md section g)
    val surface3: Color, val outline: Color, val textTertiary: Color, val primaryContainer: Color, val onPrimary: Color,
    val gradientStart: Color, val gradientEnd: Color, val successContainer: Color, val warningContainer: Color, val dangerContainer: Color,
    val dark: Boolean,
)

private val Light = VmkColors(
    background = Color(0xFFF6F7FC), surface = Color(0xFFFFFFFF), surfaceRaised = Color(0xFFEEF0F9), text = Color(0xFF11142B), textSecondary = Color(0xFF565D78),
    primary = Color(0xFF4F52E0), secondary = Color(0xFF22D3EE), success = Color(0xFF127035), warning = Color(0xFF9A4A06), danger = Color(0xFFB91C1C),
    surface3 = Color(0xFFE2E5F4), outline = Color(0xFFDADDEE), textTertiary = Color(0xFF6C7290), primaryContainer = Color(0xFFE8E9FF), onPrimary = Color.White,
    gradientStart = Color(0xFF5B5EF0), gradientEnd = Color(0xFF8452F4),
    successContainer = Color(0xFFDDF3E4), warningContainer = Color(0xFFFDF0DA), dangerContainer = Color(0xFFFCE4E4), dark = false,
)
private val Dark = VmkColors(
    background = Color(0xFF0A0D1F), surface = Color(0xFF11152B), surfaceRaised = Color(0xFF1A1F3B), text = Color(0xFFF3F4FB), textSecondary = Color(0xFFA2A9C5),
    primary = Color(0xFF9EA0FF), secondary = Color(0xFF22D3EE), success = Color(0xFF4ADE80), warning = Color(0xFFFBBF24), danger = Color(0xFFF87171),
    surface3 = Color(0xFF252B4D), outline = Color(0xFF2A3157), textTertiary = Color(0xFF7C84A3), primaryContainer = Color(0xFF25295A), onPrimary = Color(0xFF0A0D1F),
    gradientStart = Color(0xFF8F92FF), gradientEnd = Color(0xFFAE8AFF),
    successContainer = Color(0xFF12301F), warningContainer = Color(0xFF3A2B0C), dangerContainer = Color(0xFF3B1517), dark = true,
)

val LocalVmkColors = compositionLocalOf { Light }

object Vmk {
    val colors: VmkColors @Composable @ReadOnlyComposable get() = LocalVmkColors.current
    val radius = 16.dp
    val gradient = Brush.linearGradient(listOf(Color(0xFF5B5EF0), Color(0xFF8452F4)))
    /** The brand gradient for the current theme (lighter in dark mode). */
    val gradientNow: Brush @Composable get() = Brush.linearGradient(listOf(colors.gradientStart, colors.gradientEnd))
    val makingGradient = Brush.linearGradient(listOf(Color(0xFF2B2F9A), Color(0xFF6A3FC4)))
}

private fun scheme(c: VmkColors, dark: Boolean): ColorScheme {
    // the primary buttons are filled with a gradient that is always dark enough for white text; the M3 role colours follow the brand
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = c.primary, onPrimary = c.onPrimary,
        primaryContainer = c.primaryContainer, onPrimaryContainer = c.text,
        secondary = c.secondary, background = c.background, onBackground = c.text,
        surface = c.surface, onSurface = c.text, surfaceVariant = c.surfaceRaised, onSurfaceVariant = c.textSecondary,
        surfaceContainer = c.surface, surfaceContainerHigh = c.surfaceRaised, surfaceContainerHighest = c.surfaceRaised, surfaceContainerLow = c.background,
        error = c.danger, outline = c.textTertiary, outlineVariant = c.outline,
    )
}

@Composable
fun VideoMkTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val c = if (dark) Dark else Light
    CompositionLocalProvider(LocalVmkColors provides c) {
        MaterialTheme(colorScheme = scheme(c, dark), content = content)
    }
}

/** A filled gradient button with a 52dp touch target (at least 48dp everywhere). */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: (@Composable RowScope.() -> Unit)? = null) {
    val shape = RoundedCornerShape(Vmk.radius)
    Box(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = 52.dp)
            .alpha(if (enabled) 1f else 0.4f)
            .background(Vmk.gradientNow, shape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
        contentAlignment = Alignment.Center,
    ) {
        CompositionLocalProvider(LocalContentColor provides Color.White) {
            if (content != null) androidx.compose.foundation.layout.Row(verticalAlignment = Alignment.CenterVertically) { content() }
            else Text(text, style = MaterialTheme.typography.titleMedium, color = Color.White.copy(alpha = if (enabled) 1f else 0.6f))
        }
    }
}

@Composable
fun Card(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(Vmk.radius), color = Vmk.colors.surface) {
        Column(Modifier.padding(PaddingValues(16.dp))) { content() }
    }
}
