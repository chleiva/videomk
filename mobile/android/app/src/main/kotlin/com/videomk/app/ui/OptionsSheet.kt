package com.videomk.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.VideoLook

/** The options sheet (docs/UI_DESIGN.md section e): length cards with credits, look swatches, subtitles, and a Done button that shows the price. */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun OptionsSheet(composer: ComposerViewModel, balance: Int?, onDismiss: () -> Unit) {
    val options = composer.options
    val shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
    val affordable = balance == null || options.credits <= balance
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), shape = shape, containerColor = Vmk.colors.surface) {
        Column(Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState()).semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("optionsSheet"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth().heightIn(min = 52.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Video options", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.weight(1f))
                TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 44.dp)) { Text("Done", fontWeight = FontWeight.SemiBold) }
            }
            Overline("Length")
            val cols = if (LocalDensity.current.fontScale >= 1.5f) 1 else 3
            for (row in CreateOptions.LENGTHS.chunked(cols)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    for (m in row) {
                        val credits = CreateOptions(m).credits
                        val sel = options.minutes == m
                        val over = balance != null && credits > balance
                        LengthCard(m.toInt(), credits, sel, over, Modifier.weight(1f)) { composer.options = options.copy(minutes = m) }
                    }
                    repeat(cols - row.size) { Box(Modifier.weight(1f)) }
                }
            }
            Text(
                "Each started minute costs 1 credit.${balance?.let { " You have $it." } ?: ""}", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary,
                modifier = Modifier.padding(bottom = 8.dp),
            )
            Overline("Look")
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                LookSwatch("Auto", "Producer decides", null, options.look == null, Modifier.weight(1f).testTag("look-auto")) { composer.options = options.copy(look = null) }
                for (l in VideoLook.entries) LookSwatch(l.title, l.title, l, options.look == l, Modifier.weight(1f).testTag("look-${l.wire}")) { composer.options = options.copy(look = l) }
            }
            Box(Modifier.fillMaxWidth().padding(top = 8.dp).size(1.dp).background(Vmk.colors.outline))
            Row(
                Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Switch, onClickLabel = "Subtitles") { composer.options = options.copy(captions = !options.captions) }
                    .semantics(mergeDescendants = true) { stateDescription = if (options.captions) "on" else "off" }.testTag("subtitlesRow"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Icon(Icons.Filled.ClosedCaption, null, tint = Vmk.colors.text)
                Text("Subtitles", style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f))
                Switch(
                    checked = options.captions, onCheckedChange = null,
                    colors = SwitchDefaults.colors(checkedTrackColor = Vmk.colors.gradientStart, checkedThumbColor = Color.White, uncheckedTrackColor = Vmk.colors.surface3, uncheckedBorderColor = Vmk.colors.outline),
                )
            }
            Box(Modifier.fillMaxWidth().size(1.dp).background(Vmk.colors.outline))
            Box(Modifier.size(8.dp))
            val warn = !affordable
            Box(
                Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(RoundedCornerShape(26.dp))
                    .background(if (warn) Brush.linearGradient(listOf(Vmk.colors.warning, Vmk.colors.warning)) else Vmk.gradientNow)
                    .clickable(role = Role.Button, onClick = onDismiss).testTag("optionsDone"),
                contentAlignment = Alignment.Center,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    val c = if (warn) Vmk.colors.surface else Color.White
                    Text("Done ·", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = c)
                    Icon(Icons.Filled.Bolt, null, tint = c, modifier = Modifier.size(18.dp))
                    Text("${options.credits} credit${if (options.credits == 1) "" else "s"}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = c)
                }
            }
            Box(Modifier.size(24.dp))
        }
    }
}

@Composable
private fun LengthCard(minutes: Int, credits: Int, selected: Boolean, overBalance: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    val bg = when { selected -> Vmk.colors.primaryContainer; overBalance -> Vmk.colors.warningContainer.copy(alpha = 0.55f); else -> Vmk.colors.surfaceRaised }
    val tint = if (selected) Vmk.colors.primary else if (overBalance) Vmk.colors.warning else Vmk.colors.textSecondary
    Column(
        modifier.heightIn(min = 62.dp).clip(shape).background(bg).then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, shape) else Modifier)
            .clickable(role = Role.RadioButton, onClick = onClick)
            .semantics { this.selected = selected; contentDescription = "$minutes minute${if (minutes == 1) "" else "s"}, $credits credit${if (credits == 1) "" else "s"}" }
            .testTag("length-$minutes").padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        Text("$minutes min", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = if (selected) Vmk.colors.primary else Vmk.colors.text)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Bolt, null, tint = tint, modifier = Modifier.size(13.dp))
            Text("$credits", style = MaterialTheme.typography.labelMedium, color = tint)
        }
    }
}

@Composable
internal fun LookSwatch(label: String, description: String, look: VideoLook?, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    Column(
        modifier.clickable(role = Role.RadioButton, onClick = onClick).semantics { this.selected = selected; contentDescription = "$description look" },
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(3f / 3.6f)
                .then(if (selected) Modifier.border(3.dp, Vmk.colors.primaryContainer, RoundedCornerShape(19.dp)).padding(3.dp) else Modifier.padding(3.dp))
                .clip(shape).background(swatch(look)).then(if (selected) Modifier.border(2.dp, Vmk.colors.primary, shape) else Modifier),
            contentAlignment = Alignment.Center,
        ) {
            if (look == null) Icon(Icons.Filled.AutoAwesome, null, tint = Vmk.colors.primary)
            else Column(Modifier.padding(horizontal = 18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val c = lineColor(look)
                for (a in listOf(1f, 0.7f, 0.5f)) Box(Modifier.fillMaxWidth().size(width = 10.dp, height = 3.dp).background(c.copy(alpha = a), RoundedCornerShape(2.dp)))
            }
        }
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium, color = if (selected) Vmk.colors.primary else Vmk.colors.text)
    }
}

@Composable
private fun swatch(look: VideoLook?): Brush = when (look) {
    null -> Brush.linearGradient(listOf(Vmk.colors.primaryContainer, Vmk.colors.primaryContainer))
    VideoLook.Midnight -> Brush.linearGradient(listOf(Color(0xFF1A1E4D), Color(0xFF0B0D2A)))
    VideoLook.Paper -> Brush.linearGradient(listOf(Color(0xFFF6EEE2), Color(0xFFF1E6D3)))
    VideoLook.Sunrise -> Brush.linearGradient(listOf(Color(0xFFFFA45E), Color(0xFFF4607F)))
}

private fun lineColor(look: VideoLook): Color = when (look) {
    VideoLook.Midnight -> Color(0xFF8F92FF); VideoLook.Paper -> Color(0xFF4A3B2A); VideoLook.Sunrise -> Color.White
}
