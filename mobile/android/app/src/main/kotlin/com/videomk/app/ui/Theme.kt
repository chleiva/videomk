package com.videomk.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.videomk.app.core.DesignTokens

/**
 * The colours of docs/DESIGN_BAR_2026.md section 4 as Compose values. The numbers live in core/DesignTokens.kt (unit tested for contrast and against the table).
 * Content carries the colour; the interface is neutral; one accent.
 */
@Immutable
data class VmkColors(
    val background: Color, val surface: Color, val surfaceRaised: Color, val surface3: Color, val outline: Color,
    val text: Color, val textSecondary: Color, val textTertiary: Color,
    val primary: Color, val primaryContainer: Color,
    /** On the action gradient and the brand gradient: always white. */
    val onPrimary: Color,
    val gradientStart: Color, val gradientEnd: Color,
    /** The one "it is alive" accent: only on the gradient or on dark (sparkle, live ring). */
    val live: Color,
    val danger: Color, val dangerContainer: Color,
    val success: Color, val successContainer: Color, val warning: Color, val warningContainer: Color,
    /** Toasts and snackbars: the inverse of the page (dark on light, light on dark). */
    val inverseSurface: Color, val inverseOnSurface: Color,
    val dark: Boolean,
) {
    /** Kept for older call sites: the live accent. */
    val secondary: Color get() = live
}

private fun rgb(hex: Int) = Color(0xFF000000L or hex.toLong())

private fun tokenColors(dark: Boolean): VmkColors {
    fun c(r: DesignTokens.Role) = rgb(r.hex(dark))
    return VmkColors(
        background = c(DesignTokens.background), surface = c(DesignTokens.surface), surfaceRaised = c(DesignTokens.surface2), surface3 = c(DesignTokens.surface3), outline = c(DesignTokens.outline),
        text = c(DesignTokens.text), textSecondary = c(DesignTokens.textSecondary), textTertiary = c(DesignTokens.textTertiary),
        primary = c(DesignTokens.primary), primaryContainer = c(DesignTokens.primaryContainer), onPrimary = c(DesignTokens.onAction),
        gradientStart = c(DesignTokens.gradientStart), gradientEnd = c(DesignTokens.gradientEnd), live = rgb(DesignTokens.live),
        danger = c(DesignTokens.danger), dangerContainer = c(DesignTokens.dangerContainer),
        success = c(DesignTokens.success), successContainer = c(DesignTokens.successContainer), warning = c(DesignTokens.warning), warningContainer = c(DesignTokens.warningContainer),
        inverseSurface = c(DesignTokens.Role(DesignTokens.surface.dark, DesignTokens.surface.light)), inverseOnSurface = c(DesignTokens.Role(DesignTokens.text.dark, DesignTokens.text.light)),
        dark = dark,
    )
}

private val Light = tokenColors(false)
private val Dark = tokenColors(true)

val LocalVmkColors = compositionLocalOf { Light }

/**
 * The type roles of section 4 as Material roles (system font, sp with explicit line heights, so text and its leading follow the font size setting):
 * large title = headlineLarge, title = titleLarge, headline = titleMedium, body = bodyLarge, subhead = bodyMedium, footnote = bodySmall, caption = labelSmall.
 * Screens use these roles only: no literal sizes.
 */
object VmkType {
    val typography = Typography(
        displaySmall = TextStyle(fontSize = 40.sp, lineHeight = 46.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.8).sp),
        headlineLarge = TextStyle(fontSize = 34.sp, lineHeight = 40.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp),
        headlineMedium = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-0.4).sp),
        headlineSmall = TextStyle(fontSize = 24.sp, lineHeight = 30.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.3).sp),
        titleLarge = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.2).sp),
        titleMedium = TextStyle(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold),
        titleSmall = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.SemiBold),
        bodyLarge = TextStyle(fontSize = 17.sp, lineHeight = 24.sp),
        bodyMedium = TextStyle(fontSize = 15.sp, lineHeight = 20.sp),
        bodySmall = TextStyle(fontSize = 13.sp, lineHeight = 18.sp),
        labelLarge = TextStyle(fontSize = 15.sp, lineHeight = 20.sp, fontWeight = FontWeight.Medium),
        labelMedium = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.Medium),
        labelSmall = TextStyle(fontSize = 12.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium),
    )
    /** The prompt on Create ("A video about…") and the narration line on Making: the one large reading size. */
    val prompt: TextStyle get() = typography.headlineMedium
    /** The sentence being narrated, on the Making screen. */
    val narration: TextStyle get() = typography.headlineSmall.copy(fontWeight = FontWeight.Medium)
    /** The title on the Making card. */
    val makingTitle = TextStyle(fontSize = 19.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold)
    val question: TextStyle get() = typography.headlineMedium.copy(fontWeight = FontWeight.Bold)
    /** The label of the primary button. */
    val cta: TextStyle get() = typography.titleMedium
    val hero = TextStyle(fontSize = 56.sp, lineHeight = 60.sp, fontWeight = FontWeight.Bold, fontFeatureSettings = "tnum")
    val wordmark: TextStyle get() = typography.displaySmall
}

/** Spacing (4 dp base, 20 dp gutter), radii and sizes in dp, from core/DesignTokens.kt. */
object Vmk {
    val colors: VmkColors @Composable @ReadOnlyComposable get() = LocalVmkColors.current
    val radius = DesignTokens.Radius.card.dp
    val space = Spaces
    val radii = Radii
    object Spaces {
        val xs = DesignTokens.Space.xs.dp; val s = DesignTokens.Space.s.dp; val m = DesignTokens.Space.m.dp; val l = DesignTokens.Space.l.dp; val xl = DesignTokens.Space.xl.dp
        val xxl = DesignTokens.Space.xxl.dp; val xxxl = DesignTokens.Space.xxxl.dp
        /** The one screen gutter. */
        val screen = DesignTokens.Space.screenMargin.dp; val sheet = DesignTokens.Space.sheetMargin.dp
    }
    object Radii {
        val field = DesignTokens.Radius.field.dp; val thumb = DesignTokens.Radius.thumb.dp; val tile = DesignTokens.Radius.tile.dp; val card = DesignTokens.Radius.card.dp
        val videoCard = DesignTokens.Radius.videoCard.dp; val making = DesignTokens.Radius.making.dp; val composer = DesignTokens.Radius.composer.dp; val sheet = DesignTokens.Radius.sheet.dp
    }
    val minTouch = DesignTokens.Size.minTouch.dp
    /** The visible circle of an icon button (inside its 48 dp target). */
    val iconButton = DesignTokens.Size.iconButton.dp
    val primaryButton = DesignTokens.Size.primaryButton.dp
    /** The action gradient: the ONE primary button per screen (same in light and dark). */
    val gradient = Brush.linearGradient(listOf(rgb(DesignTokens.gradientStart.light), rgb(DesignTokens.gradientEnd.light)))
    val gradientNow: Brush get() = gradient
    /** The brand gradient: logo tile and Making card. */
    val makingGradient = Brush.linearGradient(listOf(rgb(DesignTokens.makingStart), rgb(DesignTokens.makingEnd)))
    /** The live ring: primary into the live accent (current scene, the capsule). */
    val liveRing = Brush.linearGradient(listOf(rgb(DesignTokens.gradientEnd.light), rgb(DesignTokens.gradientStart.light), rgb(DesignTokens.live)))
}

private fun scheme(c: VmkColors, dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    val onSolidPrimary = rgb(DesignTokens.onPrimary.hex(dark))
    return base.copy(
        primary = c.primary, onPrimary = onSolidPrimary, primaryContainer = c.primaryContainer, onPrimaryContainer = c.primary, inversePrimary = rgb(DesignTokens.primary.hex(!dark)),
        secondary = c.primary, onSecondary = onSolidPrimary, secondaryContainer = c.primaryContainer, onSecondaryContainer = c.text,
        tertiary = c.live, onTertiary = rgb(DesignTokens.background.dark),
        background = c.background, onBackground = c.text,
        surface = c.surface, onSurface = c.text, surfaceVariant = c.surfaceRaised, onSurfaceVariant = c.textSecondary,
        surfaceDim = c.surface3, surfaceBright = c.surface, surfaceTint = Color.Transparent,
        surfaceContainerLowest = c.background, surfaceContainerLow = c.surface, surfaceContainer = c.surface, surfaceContainerHigh = c.surfaceRaised, surfaceContainerHighest = c.surface3,
        inverseSurface = c.inverseSurface, inverseOnSurface = c.inverseOnSurface,
        error = c.danger, onError = onSolidPrimary, errorContainer = c.dangerContainer, onErrorContainer = c.text,
        outline = c.textTertiary, outlineVariant = c.outline, scrim = Color.Black,
    )
}

@Composable
fun VideoMkTheme(dark: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val c = if (dark) Dark else Light
    CompositionLocalProvider(LocalVmkColors provides c) {
        MaterialTheme(colorScheme = scheme(c, dark), typography = VmkType.typography, content = content)
    }
}

/**
 * The ONE primary button (rule 1): a pill filled with the action gradient, labelled with a verb, 56 dp tall (the label may wrap at large text sizes).
 * [content] replaces the label when the button needs an icon or a price beside it. One per screen.
 */
@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, fill: Boolean = true, content: (@Composable RowScope.() -> Unit)? = null) {
    val shape = CircleShape
    // disabled is an opaque fill with a quiet label and no glow: never a see-through gradient (over a photo grid that printed two texts on top of each other)
    val label = if (enabled) Vmk.colors.onPrimary else Vmk.colors.textSecondary
    Box(
        modifier
            .then(if (fill) Modifier.fillMaxWidth() else Modifier)
            .heightIn(min = Vmk.primaryButton)
            .then(if (enabled) Modifier.vmkGlow(shape) else Modifier)
            .clip(shape)
            .then(if (enabled) Modifier.background(Vmk.gradient, shape) else Modifier.background(Vmk.colors.surface3, shape))
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = Vmk.space.xxl, vertical = Vmk.space.m),
        contentAlignment = Alignment.Center,
    ) {
        CompositionLocalProvider(LocalContentColor provides label) {
            if (content != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) { content() }
            else Text(text, style = VmkType.cta, color = label, textAlign = TextAlign.Center)
        }
    }
}

/** An opaque card with the card radius (22 dp): cards never carry a border and a shadow together. */
@Composable
fun Card(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Surface(modifier = modifier.fillMaxWidth(), shape = RoundedCornerShape(Vmk.radii.card), color = Vmk.colors.surface) {
        Column(Modifier.padding(PaddingValues(Vmk.space.l))) { content() }
    }
}
