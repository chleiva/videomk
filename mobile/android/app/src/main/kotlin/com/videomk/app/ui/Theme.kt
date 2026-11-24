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
)

private val Light = VmkColors(
    background = Color(0xFFF6F7FB), surface = Color.White, surfaceRaised = Color(0xFFECEEF7), text = Color(0xFF111827), textSecondary = Color(0xFF5B6478),
    primary = Color(0xFF6366F1), secondary = Color(0xFF22D3EE), success = Color(0xFF15803D), warning = Color(0xFFB45309), danger = Color(0xFFB91C1C),
)
private val Dark = VmkColors(
    background = Color(0xFF0A0E20), surface = Color(0xFF151A35), surfaceRaised = Color(0xFF1E2347), text = Color(0xFFF8FAFC), textSecondary = Color(0xFFA5ADC4),
    primary = Color(0xFF6366F1), secondary = Color(0xFF22D3EE), success = Color(0xFF4ADE80), warning = Color(0xFFFBBF24), danger = Color(0xFFF87171),
)

val LocalVmkColors = compositionLocalOf { Light }

object Vmk {
    val colors: VmkColors @Composable @ReadOnlyComposable get() = LocalVmkColors.current
    val radius = 16.dp
    val gradient = Brush.linearGradient(listOf(Color(0xFF6366F1), Color(0xFF8B5CF6)))
}

private fun scheme(c: VmkColors, dark: Boolean): ColorScheme {
    // the primary buttons are filled with a gradient that is always dark enough for white text; the M3 role colours follow the brand
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = if (dark) Color(0xFF8B8EF8) else c.primary, onPrimary = if (dark) Color(0xFF0A0E20) else Color.White,
        primaryContainer = c.surfaceRaised, onPrimaryContainer = c.text,
        secondary = c.secondary, background = c.background, onBackground = c.text,
        surface = c.surface, onSurface = c.text, surfaceVariant = c.surfaceRaised, onSurfaceVariant = c.textSecondary,
        surfaceContainer = c.surface, surfaceContainerHigh = c.surfaceRaised, surfaceContainerHighest = c.surfaceRaised, surfaceContainerLow = c.background,
        error = c.danger, outline = c.textSecondary.copy(alpha = 0.5f), outlineVariant = c.textSecondary.copy(alpha = 0.18f),
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
            .background(Vmk.gradient, shape)
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
