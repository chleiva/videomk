package com.videomk.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.PlainTooltip
import androidx.compose.material3.Text
import androidx.compose.material3.TooltipBox
import androidx.compose.material3.TooltipDefaults
import androidx.compose.material3.rememberTooltipState
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.wrapContentSize
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Shared building blocks of the redesigned screens (docs/UI_DESIGN.md sections g and h). */

/** Card shadow: a soft tinted shadow in light mode; dark mode relies on surface lightness and the hairline ring instead. */
fun Modifier.vmkShadow(level: Int, shape: Shape, dark: Boolean): Modifier {
    val e = when (level) { 1 -> 1.dp; 2 -> 4.dp; else -> 8.dp }
    return if (dark) this else this.shadow(e, shape, ambientColor = Color(0xFF282C6E).copy(alpha = 0.18f), spotColor = Color(0xFF282C6E).copy(alpha = 0.25f))
}

@Composable
fun Overline(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.textSecondary, modifier = modifier)
}

/** The fix that comes with a problem ("Use 1 min · ⚡1"): 32 dp to look at, 44 dp to hit. */
@Composable
fun FixChip(label: String, description: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier.heightIn(min = 48.dp).clickable(role = Role.Button, onClickLabel = description, onClick = onClick).semantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) {
        Row(
            Modifier.heightIn(min = 32.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 14.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp),
        ) { Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.primary, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis) }
    }
}

/** "3 min · ⚡3" with the bolt drawn; used on the options pill and the options cards. */
@Composable
fun CreditsText(minutes: Int, credits: Int, color: Color, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(stringResource(R.string.nav_minutes_short, minutes), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 1)
        Text("·", color = Vmk.colors.textTertiary)
        Icon(Icons.Filled.Bolt, null, tint = color, modifier = Modifier.size(15.dp))
        Text("$credits", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = color, maxLines = 1)
    }
}

/** The brand mark (Sparklet Trio): the app icon's own layers, a play triangle emitting three sparks on the brand gradient. */
@Composable
fun LogoMark(modifier: Modifier = Modifier, size: Dp = 30.dp) {
    Box(modifier.size(size).clip(RoundedCornerShape(size * 0.3f))) {
        Image(painterResource(R.drawable.ic_launcher_background), null, Modifier.fillMaxSize())
        Image(painterResource(R.drawable.ic_launcher_foreground), null, Modifier.fillMaxSize().scale(1.3f))
    }
}

/** A dark glass chip for text on pictures (always white on the dark scrim). */
@Composable
fun GlassChip(text: String, modifier: Modifier = Modifier, dot: Color? = null, container: Color = Color.Black.copy(alpha = 0.38f), leading: (@Composable () -> Unit)? = null) {
    Row(
        modifier.heightIn(min = 26.dp).clip(CircleShape).background(container).padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        if (dot != null) Box(Modifier.size(8.dp).clip(CircleShape).background(dot))
        leading?.invoke()
        Text(text, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** Hairline ring used on cards and the composer. */
fun Modifier.hairline(shape: Shape, color: Color): Modifier = this.border(1.dp, color, shape)

@Composable
fun hairlineColor(): Color = Vmk.colors.outline


/**
 * The one icon button (docs/UX_2026_REDESIGN.md section 5): a 48 dp target around a 40 dp tonal circle ("glass" on Android is a tonal surface, no blur).
 * The spoken label is a required parameter and doubles as the long-press tooltip. [filled] is the one primary icon action (the brand gradient).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GlassIconButton(
    icon: ImageVector, description: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    filled: Boolean = false, enabled: Boolean = true, badge: String? = null, size: Dp = 48.dp, onDark: Boolean = false,
) {
    val container = when {
        filled -> null
        onDark -> Color.Black.copy(alpha = 0.55f)
        else -> Vmk.colors.surfaceRaised
    }
    val tint = if (filled || onDark) Color.White.let { if (filled) Vmk.colors.onPrimary else it } else Vmk.colors.text
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
                    Modifier.size(size - 8.dp).clip(CircleShape).then(if (filled) Modifier.background(Vmk.gradientNow) else Modifier.background(container!!)),
                    contentAlignment = Alignment.Center,
                ) { Icon(icon, null, tint = tint, modifier = Modifier.size(22.dp)) }
            }
            // drawn outside the clipped circle and nudged inwards, so a count such as "45" is never cut off
            if (badge != null) Text(
                badge, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.onPrimary, maxLines = 1, softWrap = false,
                modifier = Modifier.align(Alignment.TopEnd).offset(x = 2.dp, y = (-2).dp).clip(CircleShape).background(Vmk.colors.primary).padding(horizontal = 6.dp, vertical = 2.dp).clearAndSetSemantics { },
            )
        }
    }
}

/**
 * A pill that opens a menu (docs/UX_2026_REDESIGN.md section 5): icon, the current value, a chevron. The value is the label, so the state is always visible.
 * 40 dp tall visually, 48 dp to hit; values are one short word (the menu rows carry the long names).
 */
@Composable
fun Pill(
    value: String, description: String, modifier: Modifier = Modifier, icon: ImageVector? = null, expanded: Boolean, onExpandedChange: (Boolean) -> Unit,
    menu: @Composable () -> Unit,
) {
    Box(modifier) {
        Row(
            Modifier.heightIn(min = 48.dp).wrapContentSize(Alignment.CenterStart).clip(CircleShape)
                .clickable(role = Role.DropdownList, onClickLabel = description) { onExpandedChange(true) }
                .semantics(mergeDescendants = true) { contentDescription = "$description: $value"; stateDescription = value },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(
                Modifier.heightIn(min = 40.dp).clip(CircleShape).background(Vmk.colors.surfaceRaised).padding(start = 12.dp, end = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                if (icon != null) Icon(icon, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
                Text(value, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                Icon(Icons.Filled.ExpandMore, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(18.dp))
            }
        }
        androidx.compose.material3.DropdownMenu(expanded = expanded, onDismissRequest = { onExpandedChange(false) }, containerColor = Vmk.colors.surface) { menu() }
    }
}
