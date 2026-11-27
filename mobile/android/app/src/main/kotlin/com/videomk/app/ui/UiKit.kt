package com.videomk.app.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.PlainTooltip
import androidx.compose.material3.Text
import androidx.compose.material3.TooltipBox
import androidx.compose.material3.TooltipDefaults
import androidx.compose.material3.rememberTooltipState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.DesignTokens

/** The shared building blocks (docs/DESIGN_BAR_2026.md sections 4 and 5): one primary button (Theme.kt), one icon button, one top bar, one pill, one chip. */

private val ShadowTint = Color(0xFF000000L or DesignTokens.makingStart.toLong())

/** The one soft card shadow, light mode only (dark mode separates by surface lightness). Never beside a border. */
fun Modifier.vmkShadow(level: Int, shape: Shape, dark: Boolean): Modifier {
    val e = when (level) { 1 -> 2.dp; 2 -> 8.dp; else -> 16.dp }
    return if (dark) this else this.shadow(e, shape, ambientColor = ShadowTint.copy(alpha = 0.10f), spotColor = ShadowTint.copy(alpha = 0.22f))
}

/** The glow under the primary button and the New video button: the action colour, soft, in both themes. */
fun Modifier.vmkGlow(shape: Shape): Modifier {
    val c = Color(0xFF000000L or DesignTokens.gradientEnd.light.toLong())
    return this.shadow(14.dp, shape, ambientColor = c.copy(alpha = 0.35f), spotColor = c.copy(alpha = 0.55f))
}

@Composable
fun Overline(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelSmall, color = Vmk.colors.textSecondary, modifier = modifier.semantics { heading() })
}

/** The fix that comes with a problem ("Use 1 min · ⚡1"): 32 dp to look at, 48 dp to hit. */
@Composable
fun FixChip(label: String, description: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier.heightIn(min = Vmk.minTouch).clickable(role = Role.Button, onClickLabel = description, onClick = onClick).semantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) {
        Row(
            Modifier.heightIn(min = 32.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp),
        ) { Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, maxLines = 2, overflow = TextOverflow.Ellipsis) }
    }
}

/** "3 min · ⚡3" with the bolt drawn; used on the options cards. */
@Composable
fun CreditsText(minutes: Int, credits: Int, color: Color, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(stringResource(R.string.nav_minutes_short, minutes), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text, maxLines = 1)
        Text("·", color = Vmk.colors.textTertiary)
        Icon(Sym.Bolt, null, tint = color, modifier = Modifier.size(15.dp))
        Text("$credits", style = MaterialTheme.typography.titleSmall, color = color, maxLines = 1)
    }
}

/** The brand mark: the app icon's own layers, a play triangle with its sparkle on the brand gradient. */
@Composable
fun LogoMark(modifier: Modifier = Modifier, size: Dp = 30.dp) {
    Box(modifier.size(size).clip(RoundedCornerShape(size * 0.26f))) {
        Image(painterResource(R.drawable.ic_launcher_background), null, Modifier.fillMaxSize())
        Image(painterResource(R.drawable.ic_launcher_foreground), null, Modifier.fillMaxSize().scale(1.3f))
    }
}

/** The sparkle: AI suggestions and live work only. */
@Composable
fun Sparkle(modifier: Modifier = Modifier, tint: Color = Vmk.colors.primary, size: Dp = 16.dp) {
    Icon(Sym.Sparkle, null, tint = tint, modifier = modifier.size(size).clearAndSetSemantics { })
}

/** A dark glass chip for text on pictures (always white on the dark scrim): durations, format badges. */
@Composable
fun GlassChip(text: String, modifier: Modifier = Modifier, dot: Color? = null, container: Color = Color.Black.copy(alpha = 0.5f), leading: (@Composable () -> Unit)? = null) {
    Row(
        modifier.heightIn(min = 26.dp).clip(CircleShape).background(container).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (dot != null) Box(Modifier.size(8.dp).clip(CircleShape).background(dot))
        leading?.invoke()
        Text(text, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** Hairline ring: only where there is no shadow (an empty scene tile, an outlined provider button). */
fun Modifier.hairline(shape: Shape, color: Color): Modifier = this.border(1.dp, color, shape)

@Composable
fun hairlineColor(): Color = Vmk.colors.outline

/**
 * The ONE icon button: a 48 dp target around a 44 dp circle. Quiet by default (a tonal circle on the page); [onDark] is the glass version for controls over media;
 * [filled] carries the action gradient and is used at most once per screen, only where the primary action has no room for its label.
 * The spoken label is a required parameter and doubles as the long-press tooltip.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GlassIconButton(
    icon: ImageVector, description: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    filled: Boolean = false, enabled: Boolean = true, badge: String? = null, size: Dp = Vmk.minTouch, onDark: Boolean = false, tint: Color? = null,
    /** Floating over content (the selection bar): an opaque surface circle with the one soft shadow instead of the tonal fill. */
    raised: Boolean = false,
) {
    val container = when {
        filled -> null
        onDark -> Color.Black.copy(alpha = 0.45f)
        raised -> Vmk.colors.surface
        else -> Vmk.colors.surfaceRaised
    }
    val iconTint = tint ?: if (filled) Vmk.colors.onPrimary else if (onDark) Color.White else Vmk.colors.text
    TooltipBox(
        positionProvider = TooltipDefaults.rememberPlainTooltipPositionProvider(),
        tooltip = { PlainTooltip { Text(description) } },
        state = rememberTooltipState(),
    ) {
        Box(modifier.size(size).alpha(if (enabled) 1f else 0.4f), contentAlignment = Alignment.Center) {
            Box(
                Modifier.matchParentSize().clip(CircleShape)
                    .clickable(enabled = enabled, role = Role.Button, onClickLabel = null, onClick = onClick)
                    .semantics { contentDescription = description },
                contentAlignment = Alignment.Center,
            ) {
                Box(
                    Modifier.size(size - 4.dp).then(if (raised) Modifier.vmkShadow(2, CircleShape, Vmk.colors.dark) else Modifier).clip(CircleShape).then(if (filled) Modifier.background(Vmk.gradient) else Modifier.background(container!!)),
                    contentAlignment = Alignment.Center,
                ) { Icon(icon, null, tint = iconTint, modifier = Modifier.size(22.dp)) }
            }
            // drawn outside the clipped circle and nudged inwards, so a count such as "45" is never cut off
            if (badge != null) Text(
                badge, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimary, maxLines = 1, softWrap = false,
                modifier = Modifier.align(Alignment.TopEnd).offset(x = 2.dp, y = (-2).dp).clip(CircleShape).background(Vmk.colors.primary).padding(horizontal = 6.dp, vertical = 2.dp).clearAndSetSemantics { },
            )
        }
    }
}

/**
 * A pill that opens a menu: the current value and a chevron, no key label (the value is the label, so the state is always visible).
 * 44 dp tall to look at, 48 dp to hit; values are one short word (the menu rows carry the long names). [locked]: the chevron goes and it stops answering.
 */
@Composable
fun Pill(
    value: String, description: String, modifier: Modifier = Modifier, icon: ImageVector? = null, expanded: Boolean, onExpandedChange: (Boolean) -> Unit, locked: Boolean = false,
    menu: @Composable () -> Unit,
) {
    Box(modifier) {
        Row(
            Modifier.heightIn(min = Vmk.minTouch).wrapContentSize(Alignment.CenterStart).clip(CircleShape)
                .clickable(enabled = !locked, role = Role.DropdownList, onClickLabel = description) { onExpandedChange(true) }
                .semantics(mergeDescendants = true) { contentDescription = "$description: $value"; stateDescription = value },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(
                Modifier.heightIn(min = Vmk.iconButton).clip(CircleShape).background(Vmk.colors.surfaceRaised).padding(start = Vmk.space.l, end = if (locked) Vmk.space.l else Vmk.space.m),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                if (icon != null) Icon(icon, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
                Text(value, style = MaterialTheme.typography.labelLarge, color = if (locked) Vmk.colors.textSecondary else Vmk.colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                if (!locked) Icon(Sym.ExpandMore, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(18.dp))
            }
        }
        androidx.compose.material3.DropdownMenu(expanded = expanded, onDismissRequest = { onExpandedChange(false) }, containerColor = Vmk.colors.surface, shape = RoundedCornerShape(Vmk.radii.card)) { menu() }
    }
}

/**
 * A suggestion chip (an example prompt on Create, "Make another" on the player): the sparkle and a few words on an opaque pill.
 * 44 dp to look at, 48 dp to hit; the text wraps to two lines at large sizes.
 */
@Composable
fun SparkleChip(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, onClickLabel: String? = null) {
    Box(modifier.heightIn(min = Vmk.minTouch), contentAlignment = Alignment.Center) {
        Row(
            Modifier.heightIn(min = Vmk.iconButton).vmkShadow(1, CircleShape, Vmk.colors.dark).clip(CircleShape).background(Vmk.colors.surface)
                .clickable(role = Role.Button, onClickLabel = onClickLabel, onClick = onClick).padding(horizontal = Vmk.space.l, vertical = Vmk.space.s),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s),
        ) {
            Sparkle(size = 14.dp)
            Text(text, style = MaterialTheme.typography.labelLarge, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
    }
}

/**
 * The ONE top bar. [large]: a top-level screen (its name at the large-title size on the left, actions on the right). Otherwise: the way back as an icon button,
 * an optional title (one line, beside it) and actions. No divider, no elevation; it sits on the page.
 */
@Composable
fun VmkTopBar(
    modifier: Modifier = Modifier, title: String? = null, large: Boolean = false, onBack: (() -> Unit)? = null, close: Boolean = false, backTag: String = "backButton",
    actions: @Composable RowScope.() -> Unit = {},
) {
    if (large) Row(
        modifier.fillMaxWidth().statusBarsPadding().heightIn(min = 64.dp).padding(start = Vmk.space.screen, end = Vmk.space.screen - 2.dp, top = Vmk.space.s),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s),
    ) {
        Text(title.orEmpty(), style = MaterialTheme.typography.headlineLarge, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f).semantics { heading() }.testTag("screenTitle"))
        actions()
    } else Row(
        modifier.fillMaxWidth().statusBarsPadding().heightIn(min = 60.dp).padding(horizontal = Vmk.space.screen - 2.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.xs),
    ) {
        if (onBack != null) GlassIconButton(if (close) Sym.Close else Sym.ArrowBack, stringResource(if (close) R.string.common_close else R.string.common_back), onBack, Modifier.testTag(backTag))
        if (title != null) Text(title, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f).padding(horizontal = Vmk.space.s).semantics { heading() })
        else Spacer(Modifier.weight(1f))
        actions()
    }
}

/**
 * The live ring: one turn every 2.4 s on the capsule and the current scene. Reduced motion: a still two-tone ring (motion is never the only signal: words sit beside it).
 */
@Composable
fun LiveRing(modifier: Modifier = Modifier, size: Dp = 22.dp, stroke: Dp = 2.5.dp, track: Color = Vmk.colors.surface3, color: Color = Vmk.colors.primary) {
    val still = reduceMotion(LocalContext.current)
    val angle = if (still) 0f else rememberInfiniteTransition(label = "ring").animateFloat(0f, 360f, infiniteRepeatable(tween(DesignTokens.Motion.ring, easing = LinearEasing), RepeatMode.Restart), label = "a").value
    Canvas(modifier.size(size).clearAndSetSemantics { }) {
        val w = stroke.toPx()
        val inset = Offset(w / 2, w / 2); val s = Size(this.size.width - w, this.size.height - w)
        drawArc(track, 0f, 360f, false, inset, s, style = Stroke(w))
        rotate(angle) { drawArc(color, -90f, if (still) 180f else 100f, false, inset, s, style = Stroke(w, cap = StrokeCap.Round)) }
    }
}

/** A soft aura behind a locked, waiting screen: the action colour and the live accent, low and blurred by distance (two radial washes, no blur effect needed). */
fun Modifier.vmkAura(strength: Float): Modifier = this.then(
    Modifier.background(Brush.radialGradient(listOf(Color(0xFF000000L or DesignTokens.gradientEnd.light.toLong()).copy(alpha = 0.34f * strength), Color.Transparent), center = Offset(0f, Float.POSITIVE_INFINITY), radius = 900f))
        .background(Brush.radialGradient(listOf(Color(0xFF000000L or DesignTokens.live.toLong()).copy(alpha = 0.26f * strength), Color.Transparent), center = Offset(Float.POSITIVE_INFINITY, Float.POSITIVE_INFINITY), radius = 1000f)),
)


/**
 * The ONE secondary button: a tonal pill (primary on its container), 48 dp, labelled. [onSurface]: it sits on a tinted card, so its own fill is the plain surface.
 * [danger]: a destructive choice (delete), in the danger colour on its container. Never more prominent than the screen's primary.
 */
@Composable
fun TonalButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, icon: ImageVector? = null, onSurface: Boolean = false, danger: Boolean = false, enabled: Boolean = true, fill: Boolean = false) {
    val fg = if (!enabled) Vmk.colors.textSecondary else if (danger) Vmk.colors.danger else Vmk.colors.primary
    val bg = if (!enabled) Vmk.colors.surface3 else if (danger) Vmk.colors.dangerContainer else if (onSurface) Vmk.colors.surface else Vmk.colors.primaryContainer
    Row(
        modifier.then(if (fill) Modifier.fillMaxWidth() else Modifier).heightIn(min = Vmk.minTouch).clip(CircleShape).background(bg)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(horizontal = Vmk.space.xl, vertical = Vmk.space.s),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s, Alignment.CenterHorizontally),
    ) {
        if (icon != null) Icon(icon, null, tint = fg, modifier = Modifier.size(20.dp))
        Text(text, style = MaterialTheme.typography.titleSmall, color = fg, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

/** A quiet text action (Cancel, Not now): 48 dp to hit, the secondary text colour unless it is a link. */
@Composable
fun TextAction(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, color: Color = Vmk.colors.primary, enabled: Boolean = true) {
    Box(modifier.heightIn(min = Vmk.minTouch).clip(CircleShape).clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(horizontal = Vmk.space.l, vertical = Vmk.space.s), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.titleSmall, color = if (enabled) color else Vmk.colors.textTertiary)
    }
}

/** The head of every sheet: its title (the sheet-title role) and one close icon. Nothing else lives here. */
@Composable
fun SheetHeader(title: String, onClose: () -> Unit, modifier: Modifier = Modifier, closeTag: String = "sheetClose", closeLabel: String? = null) {
    Row(modifier.fillMaxWidth().heightIn(min = 52.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
        Text(title, style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() })
        GlassIconButton(Sym.Close, closeLabel ?: stringResource(R.string.common_close), onClose, Modifier.testTag(closeTag))
    }
}

/** The one switch look, everywhere (Making, Options, Settings, Editor): the success green when on, so "on" is never the same lavender as a link. */
@Composable
fun vmkSwitchColors() = androidx.compose.material3.SwitchDefaults.colors(
    checkedTrackColor = Vmk.colors.success, checkedThumbColor = Color.White, checkedBorderColor = Color.Transparent,
    uncheckedTrackColor = Vmk.colors.surface3, uncheckedThumbColor = Vmk.colors.textSecondary, uncheckedBorderColor = Color.Transparent,
)

/**
 * The ONE row of Settings and of every list sheet: an optional leading icon, the title (and a quiet line under it), then a value, a switch or a trailing glyph.
 * At least 56 dp; the whole row is the target. [danger]: a destructive row.
 */
@Composable
fun VmkRow(
    title: String, modifier: Modifier = Modifier, icon: ImageVector? = null, subtitle: String? = null, value: String? = null, trailing: ImageVector? = null, danger: Boolean = false,
    checked: Boolean? = null, onCheckedChange: ((Boolean) -> Unit)? = null, onClick: (() -> Unit)? = null, onClickLabel: String? = null,
) {
    val on = stringResource(R.string.create_state_on); val off = stringResource(R.string.create_state_off)
    val base = modifier.fillMaxWidth().heightIn(min = 56.dp)
    val interactive = when {
        checked != null && onCheckedChange != null -> base.clickable(role = Role.Switch) { onCheckedChange(!checked) }.semantics(mergeDescendants = true) { stateDescription = if (checked) on else off }
        onClick != null -> base.clickable(role = Role.Button, onClickLabel = onClickLabel, onClick = onClick)
        else -> base.semantics(mergeDescendants = true) { }
    }
    Row(interactive.padding(horizontal = Vmk.space.l, vertical = Vmk.space.s), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
        if (icon != null) Icon(icon, null, tint = if (danger) Vmk.colors.danger else Vmk.colors.textSecondary, modifier = Modifier.size(22.dp))
        androidx.compose.foundation.layout.Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyLarge, color = if (danger) Vmk.colors.danger else Vmk.colors.text)
            if (subtitle != null) Text(subtitle, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        }
        if (value != null) Text(value, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis, textAlign = androidx.compose.ui.text.style.TextAlign.End, modifier = Modifier.weight(0.8f, fill = false))
        if (checked != null) androidx.compose.material3.Switch(checked, onCheckedChange = null, colors = vmkSwitchColors())
        if (trailing != null) Icon(trailing, null, tint = Vmk.colors.textTertiary, modifier = Modifier.size(20.dp))
    }
}

/** A group of rows on one opaque card (Settings, the Credits sheet). */
@Composable
fun VmkGroup(modifier: Modifier = Modifier, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    androidx.compose.foundation.layout.Column(modifier.fillMaxWidth().clip(RoundedCornerShape(Vmk.radii.card)).background(Vmk.colors.surface).padding(vertical = Vmk.space.xs), content = content)
}

/** The ONE text field outside the prompt: a filled, rounded field with the primary ring while it has focus. */
@Composable
fun VmkField(
    value: String, onValueChange: (String) -> Unit, modifier: Modifier = Modifier, placeholder: String? = null, singleLine: Boolean = true, minHeight: Dp = 52.dp, enabled: Boolean = true,
    keyboardOptions: androidx.compose.foundation.text.KeyboardOptions = androidx.compose.foundation.text.KeyboardOptions.Default, keyboardActions: androidx.compose.foundation.text.KeyboardActions = androidx.compose.foundation.text.KeyboardActions.Default,
) {
    val shape = RoundedCornerShape(Vmk.radii.field)
    var focused by androidx.compose.runtime.remember { androidx.compose.runtime.mutableStateOf(false) }
    androidx.compose.foundation.text.BasicTextField(
        value = value, onValueChange = onValueChange, singleLine = singleLine, enabled = enabled, textStyle = MaterialTheme.typography.bodyLarge.copy(color = Vmk.colors.text),
        cursorBrush = androidx.compose.ui.graphics.SolidColor(Vmk.colors.primary), keyboardOptions = keyboardOptions, keyboardActions = keyboardActions,
        modifier = modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused },
        decorationBox = { inner ->
            Box(
                Modifier.fillMaxWidth().heightIn(min = minHeight).clip(shape).background(Vmk.colors.surfaceRaised).then(if (focused) Modifier.border(2.dp, Vmk.colors.primary, shape) else Modifier).padding(horizontal = Vmk.space.l, vertical = Vmk.space.m),
                contentAlignment = if (singleLine) Alignment.CenterStart else Alignment.TopStart,
            ) { if (value.isEmpty() && placeholder != null) Text(placeholder, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary); inner() }
        },
    )
}

/**
 * The ONE bar for "Deleted · Undo" and for short confirmations ("Cancelled · 2 credits back"): the inverse of the page, floating above the tab bar, read out at once.
 * Undo is its only action; the bar leaves by itself (the removal is sent when it does). See core/Undo.kt.
 */
@Composable
fun UndoBar(item: com.videomk.app.core.UndoCenter.Item, onUndo: () -> Unit, modifier: Modifier = Modifier) {
    val undo = stringResource(R.string.common_undo)
    Row(
        modifier.fillMaxWidth().padding(horizontal = Vmk.space.screen).vmkShadow(2, CircleShape, Vmk.colors.dark).clip(CircleShape).background(Vmk.colors.inverseSurface)
            .heightIn(min = 52.dp).padding(start = Vmk.space.xl, end = Vmk.space.s)
            .semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Assertive }.testTag("undoBar"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s),
    ) {
        Text(item.text, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.inverseOnSurface, modifier = Modifier.weight(1f).padding(vertical = Vmk.space.m))
        if (item.undoable) Box(Modifier.heightIn(min = Vmk.minTouch).clip(CircleShape).clickable(role = Role.Button, onClick = onUndo).padding(horizontal = Vmk.space.l).testTag("undoButton"), contentAlignment = Alignment.Center) {
            Text(undo, style = MaterialTheme.typography.titleSmall, color = if (Vmk.colors.dark) Color(0xFF000000L or DesignTokens.primary.light.toLong()) else Color(0xFF000000L or DesignTokens.primary.dark.toLong()))
        }
    }
}


/** The ONE menu: a rounded surface card under its button; rows are an icon and a few words, 48 dp, the destructive one in the danger colour and last. */
@Composable
fun VmkMenu(expanded: Boolean, onDismiss: () -> Unit, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    androidx.compose.material3.DropdownMenu(expanded = expanded, onDismissRequest = onDismiss, containerColor = Vmk.colors.surface, shape = RoundedCornerShape(Vmk.radii.card), content = content)
}

@Composable
fun VmkMenuItem(text: String, icon: ImageVector?, modifier: Modifier = Modifier, danger: Boolean = false, selected: Boolean = false, enabled: Boolean = true, trailing: String? = null, onClick: () -> Unit) {
    val c = if (danger) Vmk.colors.danger else Vmk.colors.text
    androidx.compose.material3.DropdownMenuItem(
        text = { Text(text, style = MaterialTheme.typography.bodyLarge, color = if (enabled) c else Vmk.colors.textTertiary, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal) },
        leadingIcon = icon?.let { i -> { Icon(i, null, tint = if (danger) Vmk.colors.danger else Vmk.colors.textSecondary, modifier = Modifier.size(22.dp)) } },
        trailingIcon = if (selected) ({ Icon(Sym.Check, null, tint = Vmk.colors.primary, modifier = Modifier.size(20.dp)) }) else trailing?.let { t -> { Text(t, style = MaterialTheme.typography.labelMedium, color = Vmk.colors.primary, modifier = Modifier.clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = Vmk.space.s, vertical = 2.dp)) } },
        enabled = enabled, onClick = onClick, modifier = modifier.heightIn(min = Vmk.minTouch).semantics { this.selected = selected },
    )
}
