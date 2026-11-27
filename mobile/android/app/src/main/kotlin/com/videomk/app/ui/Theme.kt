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
import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.videomk.app.core.DesignTokens
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

/** Brand colours as Compose values. The numbers live in core/DesignTokens.kt (unit tested for contrast); same names as the iOS Theme.swift. */
@Immutable
data class VmkColors(
    val background: Color, val surface: Color, val surfaceRaised: Color, val text: Color, val textSecondary: Color,
    val primary: Color, val secondary: Color, val success: Color, val warning: Color, val danger: Color,
    val surface3: Color, val outline: Color, val textTertiary: Color, val primaryContainer: Color, val onPrimary: Color,
    val gradientStart: Color, val gradientEnd: Color, val successContainer: Color, val warningContainer: Color, val dangerContainer: Color,
    /** The one "it is alive" accent: live progress only. */
    val live: Color,
    /** Toasts and snackbars: the inverse of the page (dark on light, light on dark). */
    val inverseSurface: Color, val inverseOnSurface: Color,
    val dark: Boolean,
)

private fun tokenColors(dark: Boolean): VmkColors {
    fun c(r: DesignTokens.Role) = Color(0xFF000000L or r.hex(dark).toLong())
    return VmkColors(
        background = c(DesignTokens.background), surface = c(DesignTokens.surface), surfaceRaised = c(DesignTokens.surface2), text = c(DesignTokens.text), textSecondary = c(DesignTokens.textSecondary),
        primary = c(DesignTokens.primary), secondary = Color(0xFF000000L or DesignTokens.live.toLong()), success = c(DesignTokens.success), warning = c(DesignTokens.warning), danger = c(DesignTokens.danger),
        surface3 = c(DesignTokens.surface3), outline = c(DesignTokens.outline), textTertiary = c(DesignTokens.textTertiary), primaryContainer = c(DesignTokens.primaryContainer), onPrimary = c(DesignTokens.onPrimary),
        gradientStart = c(DesignTokens.gradientStart), gradientEnd = c(DesignTokens.gradientEnd),
        successContainer = c(DesignTokens.successContainer), warningContainer = c(DesignTokens.warningContainer), dangerContainer = c(DesignTokens.dangerContainer),
        live = Color(0xFF000000L or DesignTokens.live.toLong()),
        inverseSurface = if (dark) Color(0xFFE9EAF6) else Color(0xFF23263F), inverseOnSurface = if (dark) Color(0xFF23263F) else Color.White, dark = dark,
    )
}

private val Light = tokenColors(false)
private val Dark = tokenColors(true)

val LocalVmkColors = compositionLocalOf { Light }

/** The type scale (docs/UX_REVIEW.md 6.2 item 2) as M3 roles. Sizes are `sp` with explicit line heights, so text and its leading scale together with the font size setting. */
object VmkType {
    val typography = Typography(
        headlineLarge = TextStyle(fontSize = 34.sp, lineHeight = 40.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.9).sp),
        headlineMedium = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.8).sp),
        headlineSmall = TextStyle(fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold),
        titleLarge = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.SemiBold),
        titleMedium = TextStyle(fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold),
        titleSmall = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
        bodyLarge = TextStyle(fontSize = 17.sp, lineHeight = 24.sp),
        bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 21.sp),
        bodySmall = TextStyle(fontSize = 13.sp, lineHeight = 18.sp),
        labelLarge = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium),
        labelMedium = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium),
        labelSmall = TextStyle(fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium),
    )
    /** Roles outside M3: the prompt field, the question title, the big balance and the sign-in wordmark. */
    val prompt = TextStyle(fontSize = 24.sp, lineHeight = 32.sp)
    /** The title on the Making card (a little larger than titleMedium). */
    val makingTitle = TextStyle(fontSize = 19.sp, lineHeight = 26.sp, fontWeight = FontWeight.SemiBold)
    val question = TextStyle(fontSize = 27.sp, lineHeight = 33.sp, fontWeight = FontWeight.Bold)
    val cta = TextStyle(fontSize = 19.sp, lineHeight = 24.sp, fontWeight = FontWeight.Bold)
    val hero = TextStyle(fontSize = 56.sp, lineHeight = 60.sp, fontWeight = FontWeight.Bold, fontFeatureSettings = "tnum")
    val wordmark = TextStyle(fontSize = 40.sp, lineHeight = 46.sp, fontWeight = FontWeight.Bold)
}

/** Spacing (4 dp base), radii, elevation and motion tokens in dp / ms, from core/DesignTokens.kt. */
object Vmk {
    val colors: VmkColors @Composable @ReadOnlyComposable get() = LocalVmkColors.current
    val radius = DesignTokens.Radius.card.dp
    val space = Spaces
    val radii = Radii
    object Spaces { val xs = 4.dp; val s = 8.dp; val m = 12.dp; val l = 16.dp; val xl = 20.dp; val xxl = 24.dp; val xxxl = 32.dp; val screen = 16.dp; val sheet = 20.dp }
    object Radii { val field = 12.dp; val thumb = 14.dp; val card = 16.dp; val videoCard = 22.dp; val composer = 28.dp; val sheet = 30.dp }
    val minTouch = DesignTokens.Size.minTouch.dp
    val gradient = Brush.linearGradient(listOf(Color(0xFF5B5EF0), Color(0xFF8452F4)))
    /** The brand gradient for the current theme (lighter in dark mode). */
    val gradientNow: Brush @Composable get() = Brush.linearGradient(listOf(colors.gradientStart, colors.gradientEnd))
    val makingGradient = Brush.linearGradient(listOf(Color(0xFF000000L or DesignTokens.makingStart.toLong()).let { it }, Color(0xFF000000L or DesignTokens.makingEnd.toLong())))
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
        error = c.danger, onError = c.onPrimary, errorContainer = c.dangerContainer, onErrorContainer = c.danger,
        secondaryContainer = c.primaryContainer, onSecondaryContainer = c.text, tertiary = c.live,
        outline = c.textTertiary, outlineVariant = c.outline,
    )
}

@Composable
fun VideoMkTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val c = if (dark) Dark else Light
    CompositionLocalProvider(LocalVmkColors provides c) {
        MaterialTheme(colorScheme = scheme(c, dark), typography = VmkType.typography, content = content)
    }
}

/** A filled gradient button with a 52dp touch target (at least 48dp everywhere). */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, content: (@Composable RowScope.() -> Unit)? = null) {
    val shape = androidx.compose.foundation.shape.CircleShape   // primary actions are pills everywhere (Create, Share, Continue)
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
        CompositionLocalProvider(LocalContentColor provides Vmk.colors.onPrimary) {
            if (content != null) androidx.compose.foundation.layout.Row(verticalAlignment = Alignment.CenterVertically) { content() }
            else Text(text, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.onPrimary.copy(alpha = if (enabled) 1f else 0.6f))
        }
    }
}

@Composable
fun Card(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(Vmk.radius), color = Vmk.colors.surface) {
        Column(Modifier.padding(PaddingValues(16.dp))) { content() }
    }
}
