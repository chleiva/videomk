package com.videomk.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
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

/** The brand mark: a gradient rounded square with a play triangle. */
@Composable
fun LogoMark(modifier: Modifier = Modifier, size: Dp = 30.dp) {
    Box(modifier.size(size).clip(RoundedCornerShape(size * 0.3f)).background(Vmk.gradientNow), contentAlignment = Alignment.Center) {
        Icon(Icons.Filled.PlayArrow, null, tint = Vmk.colors.onPrimary, modifier = Modifier.size(size * 0.62f))
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
