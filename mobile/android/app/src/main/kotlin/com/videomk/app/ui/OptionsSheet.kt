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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import com.videomk.app.core.displayName
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.VideoLook

/**
 * The one Options sheet: everything the three pills do not carry, on the shared kit (one header, one chip, one row, one switch). For (every platform in one place),
 * Look (the colour theme), Scenes and Background (only when the server offers them), Quality (what the plan locks carries the plan's name), Subtitles, Language and
 * Watermark as rows, and Format as tiles that always say their ratio. Scrolls when it needs to.
 */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun CreateOptionsSheet(composer: ComposerViewModel, caps: com.videomk.app.core.Capabilities, o: CreateOptions, ownPictures: Boolean, onCostInfo: () -> Unit, onDismiss: () -> Unit) {
    var languageMenu by remember { mutableStateOf(false) }
    var watermarkMenu by remember { mutableStateOf(false) }
    var presenceMenu by remember { mutableStateOf(false) }
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false), shape = RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet), containerColor = Vmk.colors.surface) {
        Column(Modifier.padding(horizontal = Vmk.space.sheet).verticalScroll(rememberScrollState()).navigationBarsPadding().semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("optionsSheet"), verticalArrangement = Arrangement.spacedBy(Vmk.space.xl)) {
            SheetHeader(stringResource(R.string.create_options), onDismiss, closeTag = "optionsDone", closeLabel = stringResource(R.string.common_done))
            // FOR: the same list as the pill, so every choice is in one place
            Section(stringResource(R.string.create_what_for)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(Vmk.space.s), verticalArrangement = Arrangement.spacedBy(Vmk.space.s), modifier = Modifier.fillMaxWidth().testTag("platformChips")) {
                    for (c in CreatePlatforms.chips(caps).filter { it.enabled }) ChoiceChip(c.label, c.id == o.platform && !CreatePlatforms.isCustom(o, caps), Modifier.testTag("platform-${c.id}")) { composer.selectPlatform(c) }
                }
            }
            // LOOK: the colour theme; two rows of two at large text so no label shrinks
            // with the look picker, "Look" is the pill's word: these are the colours
            Section(stringResource(if (caps.lookPicker == null) R.string.create_look else R.string.looks_colours)) {
                val looks = listOf<VideoLook?>(null) + VideoLook.entries
                for (row in if (isLargeText()) looks.chunked(2) else listOf(looks)) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                    for (l in row) LookSwatch(l?.displayName() ?: stringResource(R.string.create_look_auto), l?.displayName() ?: stringResource(R.string.create_look_auto_desc), l, o.look == l, Modifier.weight(1f).testTag("look-${l?.wire ?: "auto"}")) { composer.updateOptions(o.copy(look = l)) }
                }
            }
            // SCENES: the server's own styles (Auto, Illustrated, Real, Whiteboard...), only where it lists a real choice; the chosen one says what it means
            // (a server with the look picker offers that INSTEAD: the older style wish is neither shown nor sent)
            caps.looks?.takeIf { it.hasStyleChoice && caps.lookPicker == null }?.let { looks ->
                Section(stringResource(R.string.opt_scenes)) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(Vmk.space.s), verticalArrangement = Arrangement.spacedBy(Vmk.space.s), modifier = Modifier.fillMaxWidth().testTag("styleChips")) {
                        for (st in looks.styles.filter { it.available }) ChoiceChip(st.label, o.style == st.id, Modifier.testTag("style-${st.id}")) { composer.updateOptions(o.copy(style = st.id)) }
                    }
                    looks.style(o.style)?.note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("styleNote")) }
                }
            }
            // BACKGROUND: a wish in the server's own words; never for a video made from the person's photos or slides (they keep a still background)
            caps.looks?.wishes?.takeIf { it.isNotEmpty() && !ownPictures }?.let { wishes ->
                Section(stringResource(R.string.opt_background)) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(Vmk.space.s), verticalArrangement = Arrangement.spacedBy(Vmk.space.s), modifier = Modifier.fillMaxWidth().testTag("backgroundChips")) {
                        ChoiceChip(stringResource(R.string.create_look_auto), o.backgroundWish == null, Modifier.testTag("wish-auto")) { composer.updateOptions(o.copy(backgroundWish = null)) }
                        for (w in wishes) ChoiceChip(w.label, o.backgroundWish == w.say, Modifier.testTag("wish-${w.id}")) { composer.updateOptions(o.copy(backgroundWish = w.say)) }
                    }
                }
            }
            // QUALITY: every quality the server lists; one the plan locks says which plan has it
            if (caps.resolutions.size > 1) Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Overline(stringResource(R.string.create_quality), Modifier.weight(1f))
                    if (caps.resolutions.any { it.multiplier > 1 }) GlassIconButton(Sym.Info, stringResource(R.string.create_quality_info), onCostInfo, Modifier.testTag("costWhy"))
                }
                Segmented(caps.resolutions, o.resolution, { caps.planName(it) }) { composer.updateOptions(o.copy(resolution = it)) }
            }
            // rows: subtitles, narration language, watermark
            VmkGroup(onSheet = true) {
                VmkRow(stringResource(R.string.create_subtitles), Modifier.testTag("subtitlesRow"), icon = Sym.ClosedCaption, checked = o.captions, onCheckedChange = { composer.updateOptions(o.copy(captions = it)) })
                Box {
                    VmkRow(stringResource(R.string.create_language), Modifier.testTag("languageRow"), icon = Sym.Language, value = CreatePlatforms.languageLabel(o, caps), trailing = Sym.ExpandMore, onClick = { languageMenu = true }, onClickLabel = stringResource(R.string.create_language_desc))
                    VmkMenu(languageMenu, { languageMenu = false }) {
                        for ((id, label) in listOf("auto" to stringResource(R.string.create_same_as_description)) + caps.languages.map { it.id to it.label })
                            VmkMenuItem(label, null, Modifier.testTag("language-$id"), selected = o.language == id) { languageMenu = false; composer.updateOptions(o.copy(language = id)) }
                    }
                }
                caps.watermark?.let { wm ->
                    val brand = stringResource(R.string.brand_name)
                    fun name(c: com.videomk.app.core.WatermarkChoice) = if (c.id == "videomk") brand else c.label
                    if (wm.forced) {
                        // a fixed value, not a control: the plan includes the mark; nothing is sent
                        VmkRow(stringResource(R.string.opt_watermark), Modifier.testTag("watermarkRow"), icon = Sym.Shield, subtitle = wm.forcedNote, value = brand)
                    } else {
                        val modes = wm.modes.filter { it.id != "custom" }   // the person's own logo is set up on the web for now
                        val current = modes.firstOrNull { it.id == o.watermarkMode }
                        Box {
                            VmkRow(stringResource(R.string.opt_watermark), Modifier.testTag("watermarkRow"), icon = Sym.Shield, value = current?.let { name(it) } ?: stringResource(R.string.opt_watermark_default), trailing = Sym.ExpandMore, onClick = { watermarkMenu = true })
                            VmkMenu(watermarkMenu, { watermarkMenu = false }) {
                                VmkMenuItem(stringResource(R.string.opt_watermark_default), null, Modifier.testTag("watermark-default"), selected = o.watermarkMode == null) { watermarkMenu = false; composer.updateOptions(o.copy(watermarkMode = null, watermarkPresence = null)) }
                                for (m in modes) VmkMenuItem(name(m), null, Modifier.testTag("watermark-${m.id}"), selected = o.watermarkMode == m.id, enabled = m.available, trailing = caps.planName(m.requiresPlan).takeIf { !m.available }) {
                                    watermarkMenu = false; composer.updateOptions(o.copy(watermarkMode = m.id, watermarkPresence = if (m.id == "videomk") o.watermarkPresence ?: wm.defaultPresence else null))
                                }
                            }
                        }
                        // the product's own mark: there for the whole video, or now and then (the server's own labels)
                        if (o.watermarkMode == "videomk" && wm.presences.count { it.available } > 1) Box {
                            val p = wm.presences.firstOrNull { it.id == o.watermarkPresence } ?: wm.presences.firstOrNull { it.id == wm.defaultPresence }
                            VmkRow(stringResource(R.string.opt_presence), Modifier.testTag("presenceRow"), subtitle = p?.note, value = p?.label, trailing = Sym.ExpandMore, onClick = { presenceMenu = true })
                            VmkMenu(presenceMenu, { presenceMenu = false }) {
                                for (c in wm.presences.filter { it.available }) VmkMenuItem(c.label, null, Modifier.testTag("presence-${c.id}"), selected = p?.id == c.id) { presenceMenu = false; composer.updateOptions(o.copy(watermarkPresence = c.id)) }
                            }
                        }
                    }
                }
            }
            // FORMAT: every tile says its ratio; a beta format says "Beta" in words; formats that are not ready for this account are not shown
            val formats = listOf("16:9", "9:16", "1:1", "4:5").filter { caps.aspect(it)?.ready == true }
            if (formats.size > 1) Section(stringResource(R.string.create_format)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                    for (id in formats) FormatTile(id, CreatePlatforms.aspectName(id, caps), beta = caps.aspect(id)?.beta == true, selected = o.aspect == id, Modifier.weight(1f)) { composer.updateOptions(o.copy(aspect = id)) }
                }
            }
            Box(Modifier.size(Vmk.space.s))
        }
    }
}

@Composable
private fun Section(title: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) { Overline(title); content() }
}

/** The ONE chip for a choice among a few: a pill; chosen = tonal fill, the primary colour and a tick (never colour alone). 44 dp to look at, 48 dp to hit. */
@Composable
fun ChoiceChip(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val haptics = rememberHaptics()
    Box(modifier.heightIn(min = Vmk.minTouch).clip(CircleShape).clickable(role = Role.RadioButton) { haptics.play(com.videomk.app.core.DesignTokens.Haptic.Selection); onClick() }.semantics { this.selected = selected }, contentAlignment = Alignment.Center) {
        Row(
            Modifier.heightIn(min = Vmk.iconButton).clip(CircleShape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised).padding(horizontal = Vmk.space.l, vertical = Vmk.space.s),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (selected) Icon(Sym.Check, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
            Text(label, style = MaterialTheme.typography.labelLarge, color = if (selected) Vmk.colors.primary else Vmk.colors.text, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
        }
    }
}

/** A format tile: its shape, its ratio (always), and "Beta" in words where the server says so. Chosen = tonal fill and the primary colour. */
@Composable
private fun FormatTile(id: String, label: String, beta: Boolean, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(Vmk.radii.thumb)
    val desc = stringResource(if (beta) R.string.create_format_desc_beta else R.string.create_format_desc, label, id)
    val c = if (selected) Vmk.colors.primary else Vmk.colors.textSecondary
    Column(
        modifier.heightIn(min = 84.dp).clip(shape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised)
            .clickable(role = Role.RadioButton, onClick = onClick).semantics(mergeDescendants = true) { this.selected = selected; contentDescription = desc }.padding(horizontal = 6.dp, vertical = Vmk.space.m).testTag("format-$id"),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterVertically),
    ) {
        Icon(when (id) { "16:9" -> Sym.CropLandscape; "1:1" -> Sym.CropSquare; else -> Sym.CropPortrait }, null, tint = c, modifier = Modifier.size(26.dp))
        Text(id, style = MaterialTheme.typography.labelLarge, color = if (selected) Vmk.colors.primary else Vmk.colors.text)
        if (beta) Text(stringResource(R.string.opt_beta), style = MaterialTheme.typography.labelSmall, color = Vmk.colors.textSecondary)
    }
}

/** 720p | 1080p | 4K: one dimension, the server's labels. A quality that costs more says so ("2x"); one the plan does not have says the plan and cannot be picked. */
@Composable
private fun Segmented(items: List<com.videomk.app.core.ResolutionInfo>, selected: String, planName: (String?) -> String?, onSelect: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = Vmk.minTouch).clip(CircleShape).background(Vmk.colors.surfaceRaised).padding(3.dp)) {
        for (r in items) {
            val sel = r.id == selected
            val label = if (r.id.lowercase() == "2160p") "4K" else r.label.ifBlank { r.id }
            Box(
                Modifier.weight(1f).heightIn(min = 42.dp).clip(CircleShape).then(if (sel) Modifier.background(if (Vmk.colors.dark) Vmk.colors.surface3 else Vmk.colors.surface) else Modifier)
                    .clickable(enabled = r.available, role = Role.RadioButton) { onSelect(r.id) }.semantics { this.selected = sel }.testTag("resolution-${r.id}"),
                contentAlignment = Alignment.Center,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(label, style = MaterialTheme.typography.titleSmall, color = if (!r.available) Vmk.colors.textTertiary else if (sel) Vmk.colors.text else Vmk.colors.textSecondary)
                    if (!r.available) planName(r.requiresPlan)?.let { PlanTag(it) }
                    else if (r.multiplier > 1) PlanTag("${r.multiplier}x")
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
        Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium, color = if (selected) Vmk.colors.primary else Vmk.colors.text, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
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
