package com.videomk.app.ui

import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.ui.semantics.heading
import androidx.compose.foundation.layout.FlowRow
import com.videomk.app.core.CreatePlatforms
import androidx.compose.foundation.shape.CircleShape
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
import com.videomk.app.R
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.core.displayName
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.VideoLook

/**
 * The one Options sheet (docs/UX_2026_REDESIGN.md 4.2): everything the three pills do not carry. For (all platforms in one place), Look swatches, Quality, Subtitles, Language
 * and Format as icon tiles (formats that are not ready for this account are hidden, not dimmed). Medium height by default, scrolls when it needs to.
 */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun CreateOptionsSheet(composer: ComposerViewModel, caps: com.videomk.app.core.Capabilities, o: CreateOptions, onLanguage: () -> Unit, onCostInfo: () -> Unit, onDismiss: () -> Unit) {
    val captionsState = stringResource(if (o.captions) R.string.create_state_on else R.string.create_state_off)
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false), shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp), containerColor = Vmk.colors.surface) {
        Column(Modifier.padding(horizontal = 20.dp).verticalScroll(rememberScrollState()).navigationBarsPadding().semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("optionsSheet"), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.create_options), style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() })
                TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp).testTag("optionsDone")) { Text(stringResource(R.string.common_done), fontWeight = FontWeight.SemiBold) }
            }
            // FOR: the same list as the pill, so every choice is in one place
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Overline(stringResource(R.string.create_what_for), Modifier.semantics { heading() })
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().testTag("platformChips")) {
                    for (c in CreatePlatforms.chips(caps).filter { it.enabled }) PlatformChipView(c, selected = c.id == o.platform && !CreatePlatforms.isCustom(o, caps)) { composer.selectPlatform(c) }
                }
            }
            // LOOK
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Overline(stringResource(R.string.create_look), Modifier.semantics { heading() })
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LookSwatch(stringResource(R.string.create_look_auto), stringResource(R.string.create_look_auto_desc), null, o.look == null, Modifier.weight(1f).testTag("look-auto")) { composer.updateOptions(o.copy(look = null)) }
                    for (l in VideoLook.entries) LookSwatch(l.displayName(), l.displayName(), l, o.look == l, Modifier.weight(1f).testTag("look-${l.wire}")) { composer.updateOptions(o.copy(look = l)) }
                }
            }
            // QUALITY: only the qualities this account has; 4K carries a small 2x tag, the explanation is behind the (i)
            val qualities = caps.resolutions.map { it.id }.filter { it.isNotBlank() }
            if (qualities.size > 1) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Overline(stringResource(R.string.create_quality), Modifier.weight(1f).semantics { heading() })
                    GlassIconButton(Sym.Info, stringResource(R.string.create_quality_info), onCostInfo, Modifier.testTag("costWhy"), size = 40.dp)
                }
                Segmented(qualities, o.resolution) { composer.updateOptions(o.copy(resolution = it)) }
            }
            // SUBTITLES and LANGUAGE: two plain rows
            Column {
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Switch, onClickLabel = stringResource(R.string.create_subtitles)) { composer.updateOptions(o.copy(captions = !o.captions)) }
                        .semantics(mergeDescendants = true) { stateDescription = captionsState }.testTag("subtitlesRow"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Icon(Sym.ClosedCaption, null, tint = Vmk.colors.text)
                    Text(stringResource(R.string.create_subtitles), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f))
                    Switch(checked = o.captions, onCheckedChange = null, colors = SwitchDefaults.colors(checkedTrackColor = Vmk.colors.gradientStart, checkedThumbColor = Vmk.colors.onPrimary, uncheckedTrackColor = Vmk.colors.surface3, uncheckedBorderColor = Vmk.colors.outline))
                }
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClickLabel = stringResource(R.string.create_language_desc), onClick = onLanguage).testTag("languageRow"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Icon(Sym.Language, null, tint = Vmk.colors.text)
                    Text(stringResource(R.string.create_language), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text)
                    Text(CreatePlatforms.languageLabel(o, caps), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f), maxLines = 1, textAlign = androidx.compose.ui.text.style.TextAlign.End, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                    Icon(Sym.ChevronRight, null, tint = Vmk.colors.textSecondary)
                }
            }
            // FORMAT: the shape is the label; the name only under the chosen one; formats that are not ready for this account are not shown
            val formats = listOf("16:9", "9:16", "1:1", "4:5").filter { caps.aspect(it)?.ready == true }
            if (formats.size > 1) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Overline(stringResource(R.string.create_format), Modifier.semantics { heading() })
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (id in formats) FormatTile(id, CreatePlatforms.aspectName(id, caps), beta = caps.aspect(id)?.beta == true, selected = o.aspect == id, Modifier.weight(1f)) { composer.updateOptions(o.copy(aspect = id)) }
                }
            }
            Box(Modifier.size(16.dp))
        }
    }
}

/** A format as an icon tile; its name is only shown when it is the chosen one. A small dot marks a beta format (the dot has a spoken label). */
@Composable
private fun FormatTile(id: String, label: String, beta: Boolean, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    val desc = stringResource(if (beta) R.string.create_format_desc_beta else R.string.create_format_desc, label, id)
    Box(
        modifier.heightIn(min = 76.dp).clip(shape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised).then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, shape) else Modifier)
            .clickable(role = Role.RadioButton, onClick = onClick).semantics { this.selected = selected; contentDescription = desc }.testTag("format-$id"),
    ) {
        if (beta) Box(Modifier.align(Alignment.TopEnd).padding(8.dp).size(7.dp).clip(CircleShape).background(Vmk.colors.warning))
        Column(Modifier.align(Alignment.Center).padding(horizontal = 6.dp, vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(when (id) { "16:9" -> Sym.CropLandscape; "1:1" -> Sym.CropSquare; else -> Sym.CropPortrait }, null, tint = if (selected) Vmk.colors.primary else Vmk.colors.textSecondary, modifier = Modifier.size(28.dp))
            if (selected) Text(label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
    }
}

/** 720p | 1080p | 4K: one dimension, three choices at most. The 4K id (2160p) is written "4K" with a 2x tag. */
@Composable
private fun Segmented(ids: List<String>, selected: String, onSelect: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised).padding(3.dp)) {
        for (id in ids) {
            val sel = id == selected
            val four = id.lowercase() == "2160p" || id.lowercase() == "4k"
            Box(
                Modifier.weight(1f).heightIn(min = 38.dp).clip(RoundedCornerShape(10.dp)).then(if (sel) Modifier.background(if (Vmk.colors.dark) Vmk.colors.surface3 else Vmk.colors.surface) else Modifier)
                    .clickable(role = Role.RadioButton) { onSelect(id) }.semantics { this.selected = sel }.testTag("resolution-$id"),
                contentAlignment = Alignment.Center,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(if (four) "4K" else id, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = if (sel) Vmk.colors.text else Vmk.colors.textSecondary)
                    if (four) Text("2x", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.primary, modifier = Modifier.clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 5.dp, vertical = 1.dp))
                }
            }
        }
    }
}

@Composable
internal fun LookSwatch(label: String, description: String, look: VideoLook?, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    val lookDescription = stringResource(R.string.create_look_desc, description)
    Column(
        modifier.clickable(role = Role.RadioButton, onClick = onClick).semantics { this.selected = selected; contentDescription = lookDescription },
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(3f / 3.6f)
                .then(if (selected) Modifier.border(3.dp, Vmk.colors.primaryContainer, RoundedCornerShape(19.dp)).padding(3.dp) else Modifier.padding(3.dp))
                .clip(shape).background(swatch(look)).then(if (selected) Modifier.border(2.dp, Vmk.colors.primary, shape) else Modifier),
            contentAlignment = Alignment.Center,
        ) {
            if (look == null) Icon(Sym.AutoAwesome, null, tint = Vmk.colors.primary)
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
