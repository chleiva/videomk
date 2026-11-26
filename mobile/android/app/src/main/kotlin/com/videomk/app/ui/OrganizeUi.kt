package com.videomk.app.ui

import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.OrganizeGroup
import com.videomk.app.core.OrganizePref
import com.videomk.app.core.OrganizePrompt
import com.videomk.app.core.OrganizePreview
import com.videomk.app.core.OrganizeState
import com.videomk.app.data.OrganizeController
import com.videomk.app.data.OrganizeSheet

/** The "Organize" sheet (docs/UI_DESIGN.md section n.1): a preview of the top groups, the quiet skipped line, the Always switch and three actions. */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun OrganizeSheetHost(controller: OrganizeController) {
    val sheet by controller.sheet.collectAsState()
    val pref by controller.pref.collectAsState()
    if (sheet is OrganizeSheet.Hidden) return
    val shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
    ModalBottomSheet(
        onDismissRequest = { controller.closeSheet() }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), shape = shape, containerColor = Vmk.colors.surface,
    ) {
        val view = LocalView.current
        Crossfade(sheet, animationSpec = tween(if (reduceMotion(LocalContext.current)) 0 else 200), label = "organize-sheet") { s ->
            Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 16.dp).navigationBarsPadding().semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("organizeSheet")) {
                when (s) {
                    is OrganizeSheet.Loading -> Loading()
                    is OrganizeSheet.Failed -> Message(stringResource(R.string.organize_check_failed), stringResource(R.string.organize_check_failed_text), stringResource(R.string.common_try_again), { controller.retryPreview() }, stringResource(R.string.organize_not_now)) { controller.closeSheet() }
                    OrganizeSheet.Nothing -> Message(stringResource(R.string.organize_nothing_title), stringResource(R.string.organize_nothing_text), null, {}, stringResource(R.string.common_ok)) { controller.closeSheet() }
                    is OrganizeSheet.Offer -> if (s.single) SingleBody(s, controller) else OfferBody(s, controller, pref) { view.performHapticFeedback(android.view.HapticFeedbackConstants.CLOCK_TICK) }
                    OrganizeSheet.Hidden -> Unit
                }
            }
        }
    }
}

@Composable
private fun Loading() {
    val checkingText = stringResource(R.string.organize_checking)
    Text(stringResource(R.string.organize_loading_title), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
    Column(Modifier.padding(top = 16.dp).semantics { contentDescription = checkingText }, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        repeat(3) { Box(Modifier.fillMaxWidth().heightIn(min = 56.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised)) }
    }
    Box(Modifier.heightIn(min = 120.dp))
}

@Composable
private fun Message(title: String, body: String, primary: String?, onPrimary: () -> Unit, secondary: String, onSecondary: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(Modifier.size(56.dp).clip(CircleShape).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(Icons.Filled.AutoAwesome, null, tint = Vmk.colors.primary, modifier = Modifier.size(28.dp)) }
        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
        Text(body, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        if (primary != null) PrimaryButton(primary, onPrimary, Modifier.padding(top = 6.dp))
        TextButton(onClick = onSecondary, modifier = Modifier.heightIn(min = 48.dp).testTag("organizeNotNow")) { Text(secondary, color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
    }
}

@Composable
private fun androidx.compose.foundation.layout.ColumnScope.OfferBody(offer: OrganizeSheet.Offer, controller: OrganizeController, pref: OrganizePref, tick: () -> Unit) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val onText = stringResource(R.string.organize_state_on); val offText = stringResource(R.string.organize_state_off)
    val p = offer.preview
    Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState())) {
        Text(OrganizePrompt.title(p, offer.wholeLibrary), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.semantics { heading() }.testTag("organizeTitle"))
        Text(stringResource(R.string.organize_explain), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp, bottom = 12.dp))
        for (g in OrganizePrompt.visibleGroups(p, expanded)) GroupRow(g, controller)
        if (!expanded && OrganizePrompt.moreCount(p) > 0) Text(
            OrganizePrompt.moreLabel(p), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary,
            modifier = Modifier.heightIn(min = 48.dp).clickable(role = Role.Button) { expanded = true }.padding(vertical = 12.dp).testTag("organizeMore"),
        )
        OrganizePrompt.skippedLine(p)?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(bottom = 8.dp).testTag("organizeSkipped")) }
        Box(Modifier.fillMaxWidth().size(1.dp).background(Vmk.colors.outline))
        Row(
            Modifier.fillMaxWidth().heightIn(min = 64.dp).clickable(role = Role.Switch) { tick(); controller.setPref(if (pref == OrganizePref.Always) OrganizePref.Ask else OrganizePref.Always) }
                .semantics(mergeDescendants = true) { stateDescription = if (pref == OrganizePref.Always) onText else offText }.testTag("organizeAlways"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(Modifier.weight(1f).padding(vertical = 8.dp)) {
                Text(stringResource(R.string.organize_always_title), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text)
                Text(stringResource(R.string.organize_always_text), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
            }
            Switch(checked = pref == OrganizePref.Always, onCheckedChange = null, colors = SwitchDefaults.colors(checkedTrackColor = Vmk.colors.gradientStart, checkedThumbColor = Color.White, uncheckedTrackColor = Vmk.colors.surface3, uncheckedBorderColor = Vmk.colors.outline))
        }
    }
    Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        PrimaryButton(stringResource(R.string.organize_go), { controller.organize(false) }, Modifier.testTag("organizeGo"))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(
                Modifier.weight(1.5f).heightIn(min = 46.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button) { controller.showSingle(true) }.testTag("organizeOne"),
                contentAlignment = Alignment.Center,
            ) { Text(stringResource(R.string.organize_one_collection), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, modifier = Modifier.padding(horizontal = 8.dp), maxLines = 2, textAlign = androidx.compose.ui.text.style.TextAlign.Center) }
            TextButton(onClick = { controller.closeSheet() }, modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("organizeNotNow")) { Text(stringResource(R.string.organize_not_now), color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
        }
    }
}

@Composable
private fun GroupRow(g: OrganizeGroup, controller: OrganizeController) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(vertical = 4.dp)
            .semantics(mergeDescendants = true) { contentDescription = Txt.n(if (g.existing) R.plurals.organize_group_desc_existing else R.plurals.organize_group_desc, g.count, g.name) }.testTag("organizeGroup"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(width = 30.dp + 20.dp, height = 30.dp).clearAndSetSemantics { }) {
            g.sampleIds.take(3).forEachIndexed { i, id -> SampleThumb(id, controller, Modifier.offset(x = (i * 10).dp)) }
        }
        Column(Modifier.weight(1f)) {
            Text(g.name, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(pluralStringResource(R.plurals.organize_group_count, g.count, g.count), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        }
        if (g.existing) Text(stringResource(R.string.organize_adds_existing), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.primary, maxLines = 1,
            modifier = Modifier.clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 10.dp, vertical = 5.dp))
    }
}

@Composable
private fun SampleThumb(id: String, controller: OrganizeController, modifier: Modifier) {
    val photo by produceState<MediaPhoto?>(null, id) { value = controller.photo(id) }
    Box(modifier.size(30.dp).clip(RoundedCornerShape(8.dp)).border(2.dp, Vmk.colors.surface, RoundedCornerShape(8.dp)).background(Vmk.colors.surfaceRaised)) {
        photo?.let { PhotoThumb(it, Modifier.size(30.dp)) }
    }
}

@Composable
private fun SingleBody(offer: OrganizeSheet.Offer, controller: OrganizeController) {
    val p = offer.preview
    var name by rememberSaveable { mutableStateOf(offer.suggestions.firstOrNull().orEmpty()) }
    Text(pluralStringResource(R.plurals.organize_single_title, p.total, p.total), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
    Text(stringResource(R.string.organize_single_text), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp, bottom = 12.dp))
    val shape = RoundedCornerShape(14.dp)
    BasicTextField(
        value = name, onValueChange = { name = it.take(80) }, singleLine = true,
        textStyle = MaterialTheme.typography.bodyLarge.copy(color = Vmk.colors.text), cursorBrush = SolidColor(Vmk.colors.primary),
        modifier = Modifier.fillMaxWidth().testTag("organizeName"),
        decorationBox = { inner -> Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(shape).background(Vmk.colors.surfaceRaised).border(2.dp, Vmk.colors.primary, shape).padding(horizontal = 16.dp), contentAlignment = Alignment.CenterStart) { inner() } },
    )
    if (offer.suggestions.isNotEmpty()) {
        Overline(stringResource(R.string.organize_suggestions), Modifier.padding(top = 14.dp, bottom = 6.dp))
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(offer.suggestions) { s -> FixChip(s, stringResource(R.string.organize_use_name, s)) { name = s } }
        }
    }
    Row(Modifier.fillMaxWidth().padding(top = 20.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        TextButton(onClick = { controller.showSingle(false) }, modifier = Modifier.heightIn(min = 48.dp).testTag("organizeBack")) { Text(stringResource(R.string.common_back), color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
        Box(Modifier.weight(1f))
        PrimaryButton(stringResource(R.string.organize_create), { controller.organize(true, name) }, Modifier.weight(2f).testTag("organizeCreate"), enabled = OrganizePrompt.nameValid(name))
    }
}

// progress

/** The organise bar, in the same slot and anatomy as the upload bar: ring with sparkle, count, "You can leave this screen.", stop button and a thin line. */
@Composable
fun OrganizeBar(state: OrganizeState, onCancel: () -> Unit, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    if (state is OrganizeState.Idle || state is OrganizeState.Done) return
    val shape = RoundedCornerShape(24.dp)
    var confirm by remember { mutableStateOf(false) }
    val failed = state is OrganizeState.Failed
    val offline = state is OrganizeState.Offline
    val total = when (state) { is OrganizeState.Running -> state.total; is OrganizeState.Offline -> state.total; is OrganizeState.Failed -> state.total; else -> 0 }
    val done = when (state) { is OrganizeState.Running -> state.done; is OrganizeState.Offline -> state.done; is OrganizeState.Failed -> state.done; else -> 0 }
    val title = when {
        failed -> stringResource(R.string.organize_err_unfinished)
        offline -> stringResource(R.string.organize_waiting)
        (state as OrganizeState.Running).resumed && done == 0 -> stringResource(R.string.organize_resuming)
        state.resumed -> stringResource(R.string.organize_resuming_progress, done, total)
        else -> stringResource(R.string.organize_progress, done, total)
    }
    val sub = when { failed -> (state as OrganizeState.Failed).message; offline -> stringResource(R.string.organize_offline_sub, done, total); else -> stringResource(R.string.organize_leave_screen) }
    val fraction = if (total > 0) done.toFloat() / total else 0f
    val percentText = stringResource(R.string.organize_percent, (fraction * 100).toInt())
    Column(
        modifier.fillMaxWidth().padding(horizontal = 12.dp).vmkShadow(3, shape, Vmk.colors.dark).clip(shape).background(Vmk.colors.surface)
            .border(if (failed) 1.5.dp else 1.dp, if (failed) Vmk.colors.warning else Vmk.colors.outline, shape).testTag("organizeBar")
            .semantics(mergeDescendants = true) { contentDescription = "$title. $sub"; stateDescription = percentText },
    ) {
        Row(Modifier.fillMaxWidth().heightIn(min = 68.dp).padding(start = 14.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(40.dp), contentAlignment = Alignment.Center) {
                when {
                    failed -> Icon(Icons.Filled.Warning, null, tint = Vmk.colors.warning)
                    offline -> Icon(Icons.Filled.CloudOff, null, tint = Vmk.colors.textSecondary)
                    else -> { CircularProgressIndicator(progress = { fraction }, Modifier.size(40.dp), color = Vmk.colors.primary, trackColor = Vmk.colors.surface3, strokeWidth = 3.dp); Icon(Icons.Filled.AutoAwesome, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp)) }
                }
            }
            Column(Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, maxLines = 2)
                Text(sub, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, maxLines = 2)
            }
            if (failed) TextButton(onClick = onRetry, modifier = Modifier.heightIn(min = 48.dp).testTag("organizeRetry")) { Text(stringResource(R.string.common_try_again), fontWeight = FontWeight.SemiBold) }
            IconButton(onClick = { confirm = true }, modifier = Modifier.size(48.dp).testTag("organizeStop")) { Icon(Icons.Filled.Close, stringResource(R.string.organize_stop), tint = Vmk.colors.textSecondary) }
        }
        if (!failed) LinearProgressIndicator(progress = { fraction }, modifier = Modifier.fillMaxWidth().heightIn(min = 3.dp), color = if (offline) Vmk.colors.outline else Vmk.colors.primary, trackColor = Vmk.colors.surface3, drawStopIndicator = {})
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false }, title = { Text(stringResource(R.string.organize_stop_title)) }, text = { Text(stringResource(R.string.organize_stop_text)) },
        confirmButton = { TextButton(onClick = { confirm = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.organize_keep_going), fontWeight = FontWeight.SemiBold) } },
        dismissButton = { TextButton(onClick = { confirm = false; onCancel() }, modifier = Modifier.heightIn(min = 48.dp).testTag("organizeStopConfirm")) { Text(stringResource(R.string.organize_stop_button), color = Vmk.colors.danger) } },
    )
}

/** Aggregated, polite progress announcements for screen readers: at most every 10 percent or 15 seconds, never per call. */
@Composable
fun OrganizeAnnouncements(state: OrganizeState) {
    val view = LocalView.current
    var lastBucket by remember { mutableStateOf(-1) }
    var lastTime by remember { mutableStateOf(0L) }
    var lastKind by remember { mutableStateOf("") }
    val kind = when (state) { is OrganizeState.Offline -> stringResource(R.string.organize_waiting); is OrganizeState.Failed -> stringResource(R.string.organize_err_unfinished); else -> "" }
    LaunchedEffect(kind) { if (kind.isNotEmpty() && kind != lastKind) view.announceForAccessibility(kind); lastKind = kind }
    val done = (state as? OrganizeState.Running)?.done ?: -1
    LaunchedEffect(done) {
        val s = state as? OrganizeState.Running ?: return@LaunchedEffect
        if (s.total <= 0 || s.done <= 0) return@LaunchedEffect
        val bucket = s.done * 10 / s.total
        val now = System.currentTimeMillis()
        if (bucket > lastBucket || now - lastTime > 15_000) { lastBucket = maxOf(lastBucket, bucket); lastTime = now; view.announceForAccessibility(Txt.n(R.plurals.organize_announce, s.total, s.done)) }
    }
}

/** The 36 dp pill on the other tabs while organising (hidden while the composer has focus); opens Media. */
@Composable
fun OrganizePill(state: OrganizeState, onClick: () -> Unit) {
    val (done, total) = when (state) { is OrganizeState.Running -> state.done to state.total; is OrganizeState.Offline -> state.done to state.total; else -> return }
    val text = if (state is OrganizeState.Offline) stringResource(R.string.organize_paused) else stringResource(R.string.organize_pill_progress, done, total)
    Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp).heightIn(min = 44.dp).clickable(role = Role.Button, onClickLabel = stringResource(R.string.organize_open_media), onClick = onClick), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.heightIn(min = 36.dp).clip(CircleShape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, CircleShape).padding(horizontal = 16.dp).semantics(mergeDescendants = true) { contentDescription = text }.testTag("organizePill"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Filled.AutoAwesome, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
            Text(text, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text)
        }
    }
}

/** The small "Auto" mark on collections made by the organiser. */
@Composable
fun AutoChip(modifier: Modifier = Modifier) {
    val autoText = stringResource(R.string.organize_auto_desc)
    Row(
        modifier.heightIn(min = 20.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 8.dp).semantics { contentDescription = autoText },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp),
    ) {
        Icon(Icons.Filled.AutoAwesome, null, tint = Vmk.colors.primary, modifier = Modifier.size(11.dp))
        Text(stringResource(R.string.organize_auto), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.primary)
    }
}
