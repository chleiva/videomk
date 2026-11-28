package com.videomk.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.layout.layoutId
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.CreateDock

/**
 * The glyph in the "made for" pill: the shape of the chosen format, drawn (a rounded rectangle, 1.8 dp line) so a wide, a tall, a square and a 4:5 frame
 * read as themselves. Same four shapes as web's shape-wide, shape-tall, shape-square and shape-portrait.
 */
@Composable
internal fun FormatGlyph(aspect: String, modifier: Modifier = Modifier) {
    val (w, h) = when (aspect) { "9:16" -> 9 to 18; "4:5" -> 12 to 16; "1:1" -> 14 to 14; else -> 18 to 11 }
    val k = glyphScale()
    Box(modifier.size(18.dp * k), contentAlignment = Alignment.Center) {
        Box(Modifier.size(w.dp * k, h.dp * k).border(1.8.dp, Vmk.colors.primary, RoundedCornerShape(2.5.dp)))
    }
}

/** A 18 dp glyph from the icon set in the primary colour, the leading mark of a pill. */
@Composable
internal fun PillGlyph(icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Icon(icon, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp * glyphScale()))
}

/** Pill glyphs follow the text size up to 1.5 times, so they do not shrink beside large labels. */
@Composable
private fun glyphScale(): Float = LocalDensity.current.fontScale.coerceIn(1f, 1.5f)

/** The sliders icon with its word: 48 dp to hit, 44 to look at. [labelled] false (recording) keeps the icon only, to leave room for "Listening…". */
@Composable
internal fun OptionsButton(labelled: Boolean, enabled: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val label = stringResource(R.string.create_options)
    Box(modifier.heightIn(min = Vmk.minTouch).widthIn(min = Vmk.minTouch).alpha(if (enabled) 1f else 0.4f), contentAlignment = Alignment.Center) {
        Row(
            Modifier.heightIn(min = Vmk.iconButton).clip(CircleShape).background(Vmk.colors.surfaceRaised)
                .clickable(enabled = enabled, role = Role.Button, onClickLabel = null, onClick = onClick)
                .semantics(mergeDescendants = true) { contentDescription = label }
                .padding(start = 10.dp, end = if (labelled) Vmk.space.m else 10.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Icon(Sym.Tune, null, tint = Vmk.colors.text, modifier = Modifier.size(22.dp))
            if (labelled) Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 1, softWrap = false)
        }
    }
}

/**
 * Create, the one primary action: 48 dp high (52 on its own row), 112 dp wide at least, "Create", a bolt and the price as one unit; the label never truncates.
 * Inactive: an opaque fill and the secondary label, no shadow, and it still takes the tap (it says what is missing). Active: the gradient.
 */
@Composable
internal fun CreatePill(state: CreateDock.CreateState, label: String, spokenLabel: String, credits: Int?, stateText: String, tapLabel: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val active = state == CreateDock.CreateState.Active
    val c = if (active) Vmk.colors.onPrimary else Vmk.colors.textSecondary
    val shape = CircleShape
    Row(
        modifier.heightIn(min = 48.dp).widthIn(min = 112.dp).clip(shape).then(if (active) Modifier.background(Vmk.gradient) else Modifier.background(Vmk.colors.surface3))
            .clickable(role = Role.Button, onClickLabel = tapLabel, onClick = onClick)
            .semantics { contentDescription = spokenLabel; stateDescription = stateText }.testTag("sendButton")
            .padding(horizontal = 18.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally),
    ) {
        Text(label, style = VmkType.cta, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold, color = c, maxLines = 1, softWrap = false, overflow = TextOverflow.Clip)
        if (credits != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            Icon(Sym.Bolt, null, tint = c, modifier = Modifier.size(16.dp))
            Text("$credits", style = VmkType.cta, fontWeight = androidx.compose.ui.text.font.FontWeight.Bold, color = c, maxLines = 1, softWrap = false)
        }
    }
}

/** The one caption under the tool row (docs: first-video price, or the balance running low). Centred, 14 sp-ish, secondary. */
@Composable
internal fun DockCaption(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center, modifier = modifier.fillMaxWidth().testTag("costLine"))
}

/**
 * The tool row: [tools] (photos, mic, Options), the flexible [middle] ("Listening…", centred) and [create]. One row while it fits, measured: the tools and Create side by side
 * with Create at the trailing end (the mic stays far from it: a mis-tap beside Create would spend credits). At font scale 1.5 and up, or where Create does not fit beside the
 * tools, Create drops to its own full-width row (52 dp) under them.
 */
@Composable
internal fun DockToolRow(modifier: Modifier = Modifier, tools: @Composable () -> Unit, middle: @Composable () -> Unit, create: @Composable () -> Unit) {
    val fontScale = LocalDensity.current.fontScale
    Layout(
        content = {
            Box(Modifier.layoutId("tools")) { tools() }
            Box(Modifier.layoutId("middle")) { middle() }
            Box(Modifier.layoutId("create"), propagateMinConstraints = true) { create() }
        },
        modifier = modifier,
    ) { measurables, constraints ->
        val tools = measurables.first { it.layoutId == "tools" }; val middle = measurables.first { it.layoutId == "middle" }; val create = measurables.first { it.layoutId == "create" }
        val max = constraints.maxWidth
        val gap = 4.dp.roundToPx(); val rowGap = 8.dp.roundToPx()
        // the tools are measured once, for real (no intrinsics: the icon buttons carry tooltips); Create's width is asked of its own row, which is plain layout
        val t = tools.measure(androidx.compose.ui.unit.Constraints(maxWidth = max))
        val createW = create.maxIntrinsicWidth(48.dp.roundToPx())
        val own = CreateDock.createOnOwnRow(fontScale, t.width, createW, gap, max)
        if (!own) {
            val c = create.measure(androidx.compose.ui.unit.Constraints(maxWidth = max - t.width - gap))
            val room = max - t.width - c.width - 2 * gap
            val m = middle.measure(androidx.compose.ui.unit.Constraints(maxWidth = room.coerceAtLeast(0)))
            val h = maxOf(t.height, c.height, m.height)
            layout(max, h) {
                t.placeRelative(0, (h - t.height) / 2)
                c.placeRelative(max - c.width, (h - c.height) / 2)
                m.placeRelative(t.width + gap + (room - m.width) / 2, (h - m.height) / 2)
            }
        } else {
            val room = max - t.width - gap
            val m = middle.measure(androidx.compose.ui.unit.Constraints(maxWidth = room.coerceAtLeast(0)))
            val c = create.measure(androidx.compose.ui.unit.Constraints(minWidth = max, maxWidth = max, minHeight = 52.dp.roundToPx()))
            val h1 = maxOf(t.height, m.height)
            layout(max, h1 + rowGap + c.height) {
                t.placeRelative(0, (h1 - t.height) / 2)
                m.placeRelative(t.width + gap + (room - m.width) / 2, (h1 - m.height) / 2)
                c.placeRelative(0, h1 + rowGap)
            }
        }
    }
}
