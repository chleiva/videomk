package com.videomk.app.ui

import android.graphics.BitmapFactory
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.testTag
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.videomk.app.R
import com.videomk.app.core.ClipEntry
import com.videomk.app.core.ClipFailure
import com.videomk.app.core.ClipPhase
import com.videomk.app.core.VideoEntry
import com.videomk.app.core.VideoProblem
import com.videomk.app.core.VideoRules
import com.videomk.app.core.VideoUploadCaps

/** The "Add a video" row of the photo menu: label, and under it why it is off when it is. */
@Composable
fun VideoMenuRow(entry: VideoEntry, caps: VideoUploadCaps?, onClick: () -> Unit) {
    if (entry is VideoEntry.Hidden) return
    val enabled = entry is VideoEntry.Enabled
    val reason: String? = when (entry) {
        is VideoEntry.Disabled -> when (entry.reason) {
            VideoEntry.Reason.Paused -> stringResource(R.string.vclip_reason_paused)
            VideoEntry.Reason.DailyLimit -> stringResource(R.string.vclip_reason_daily)
            VideoEntry.Reason.RequiresPlan -> stringResource(R.string.vclip_reason_plan, entry.plan?.replaceFirstChar { it.uppercase() } ?: "")
            VideoEntry.Reason.VideoFull -> (caps?.clipsPerVideo ?: 2).let { pluralStringResource(R.plurals.vclip_reason_full, it, it) }
        }
        else -> null
    }
    val label = stringResource(R.string.vclip_menu_add)
    androidx.compose.material3.DropdownMenuItem(
        text = {
            Column(Modifier.widthIn(max = 260.dp)) {
                Text(label, style = MaterialTheme.typography.bodyLarge, color = if (enabled) Vmk.colors.text else Vmk.colors.textTertiary)
                if (reason != null) Text(reason, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
            }
        },
        leadingIcon = { Icon(Sym.Videocam, null, tint = if (enabled) Vmk.colors.textSecondary else Vmk.colors.textTertiary, modifier = Modifier.size(22.dp)) },
        enabled = enabled, onClick = onClick,
        modifier = Modifier.heightIn(min = Vmk.minTouch).semantics { contentDescription = if (reason != null) "$label. $reason" else label }.testTag("addVideo"),
    )
}

/** The ONE spoken line of a clip (for the tile and the status line). */
@Composable
private fun phaseLine(e: ClipEntry): String? = when (val p = e.phase) {
    is ClipPhase.Preparing -> stringResource(R.string.vclip_status_preparing)
    is ClipPhase.Uploading -> stringResource(R.string.vclip_status_uploading, p.percent)
    is ClipPhase.Analysing -> stringResource(if (p.slow) R.string.vclip_status_slow else R.string.vclip_status_checking)
    else -> null
}

/** A clip in the strip: 64 dp tall at its own shape, a play badge, the length chip, the sound mark and a close button. Tap changes the sound. */
@Composable
fun ClipTile(e: ClipEntry, onRemove: () -> Unit, onTap: () -> Unit, modifier: Modifier = Modifier) {
    val bmp = remember(e.thumb) { e.thumb?.let { runCatching { BitmapFactory.decodeByteArray(it, 0, it.size) }.getOrNull() } }
    val width = (64f * e.aspect).coerceIn(72f, 104f).dp
    val shape = RoundedCornerShape(12.dp)
    val failed = e.phase is ClipPhase.Failed
    val busy = e.phase is ClipPhase.Preparing || e.phase is ClipPhase.Uploading || e.phase is ClipPhase.Analysing
    val sound = e.soundOn
    val chipText = stringResource(if (e.longer && width >= 88.dp) R.string.vclip_chip_first5 else R.string.vclip_chip_5s)
    val soundText = stringResource(if (sound) R.string.vclip_sound_on else R.string.vclip_sound_off)
    val remove = stringResource(R.string.vclip_remove)
    val desc = when (val p = e.phase) {
        is ClipPhase.Ready -> stringResource(R.string.vclip_a11y_ready, chipText, soundText)
        is ClipPhase.Uploading -> stringResource(R.string.vclip_a11y_uploading, p.percent)
        is ClipPhase.Preparing -> stringResource(R.string.vclip_a11y_preparing)
        is ClipPhase.Analysing -> stringResource(R.string.vclip_a11y_checking)
        is ClipPhase.Failed -> stringResource(R.string.vclip_a11y_failed, p.failure.title())
        else -> stringResource(R.string.vclip_a11y_asking)
    }
    Box(modifier.size(width = width, height = 64.dp).testTag("clipTile")) {
        Box(
            Modifier.fillMaxSize().clip(shape).background(if (failed) Vmk.colors.dangerContainer else Vmk.colors.surface3)
                .clickable(role = Role.Button, enabled = e.ready || e.phase is ClipPhase.Failed, onClick = onTap).semantics { contentDescription = desc },
            contentAlignment = Alignment.Center,
        ) {
            if (bmp != null && !failed) Image(bmp.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            if (failed) Icon(Sym.Warning, null, tint = Vmk.colors.danger, modifier = Modifier.size(26.dp))
            if (busy || e.phase is ClipPhase.AskSound || e.phase is ClipPhase.Inspecting) Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.42f)))
            when (val p = e.phase) {
                is ClipPhase.Uploading -> CircularProgressIndicator(progress = { p.percent / 100f }, modifier = Modifier.size(30.dp).clearAndSetSemantics { }, color = Color.White, trackColor = Color.White.copy(alpha = 0.3f), strokeWidth = 3.dp)
                is ClipPhase.Preparing, is ClipPhase.Analysing -> LiveRing(size = 30.dp, stroke = 3.dp, track = Color.White.copy(alpha = 0.3f), color = Color.White)
                is ClipPhase.Ready -> Box(Modifier.size(26.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.55f)), contentAlignment = Alignment.Center) { Icon(Sym.PlayArrow, null, tint = Color.White, modifier = Modifier.size(16.dp)) }
                else -> Unit
            }
            if (e.ready) {
                // length chip bottom start, sound mark top start (the close button owns the top end corner)
                Text(chipText, style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp), color = Color.White, maxLines = 1, softWrap = false,
                    modifier = Modifier.align(Alignment.BottomStart).padding(4.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.6f)).padding(horizontal = 6.dp, vertical = 2.dp).clearAndSetSemantics { testTag = "clipChip" })
                Box(Modifier.align(Alignment.TopStart).padding(4.dp).size(20.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.6f)).clearAndSetSemantics { testTag = if (sound) "clipSoundOn" else "clipSoundOff" }, contentAlignment = Alignment.Center) {
                    Icon(if (sound) Sym.VolumeUp else Sym.VolumeOff, null, tint = Color.White, modifier = Modifier.size(13.dp))
                }
            }
        }
        Box(Modifier.align(Alignment.TopEnd).offset(x = 8.dp, y = (-8).dp).size(Vmk.minTouch).clickable(role = Role.Button, onClickLabel = remove, onClick = onRemove).semantics { contentDescription = remove }.testTag("removeClip"), contentAlignment = Alignment.TopEnd) {
            Box(Modifier.padding(10.dp).size(22.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.65f)), contentAlignment = Alignment.Center) { Icon(Sym.Close, null, tint = Color.White, modifier = Modifier.size(14.dp)) }
        }
    }
}

/**
 * Under the strip, only where something needs saying: a clip getting ready, uploading, being checked, taking long, or one that did not work (with its one action and Remove).
 * Polite live regions announce each change ("Uploading 42%", "Checking your clip", "Clip ready" is the tile's own state).
 */
@Composable
fun ClipStatus(entries: List<ClipEntry>, caps: VideoUploadCaps?, onRetry: (String) -> Unit, onKeepWaiting: (String) -> Unit, onRemove: (String) -> Unit) {
    val shown = entries.filter { it.phase is ClipPhase.Preparing || it.phase is ClipPhase.Uploading || it.phase is ClipPhase.Analysing || it.phase is ClipPhase.Failed || (it.info?.soundDropped == true && it.ready) }
    if (shown.isEmpty()) return
    Column(Modifier.fillMaxWidth().testTag("clipStatus"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (e in shown) key(e.id) {
            val failure = (e.phase as? ClipPhase.Failed)?.failure
            if (failure != null) ClipFailureRow(e.id, failure, caps, onRetry, onKeepWaiting, onRemove)
            else {
                val line = phaseLine(e) ?: stringResource(R.string.vclip_status_dropped)
                Row(Modifier.fillMaxWidth().heightIn(min = 28.dp).semantics { contentDescription = line; liveRegion = LiveRegionMode.Polite }.testTag("clipStatusLine"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (e.phase is ClipPhase.Analysing || e.phase is ClipPhase.Preparing) LiveRing(size = 16.dp, stroke = 2.dp)
                    Text(line, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.clearAndSetSemantics { })
                }
            }
        }
    }
}

@Composable
private fun ClipFailureRow(id: String, f: ClipFailure, caps: VideoUploadCaps?, onRetry: (String) -> Unit, onKeepWaiting: (String) -> Unit, onRemove: (String) -> Unit) {
    val spoken = f.title() + ". " + f.body(caps)
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Vmk.radii.field)).background(Vmk.colors.warningContainer).padding(horizontal = 12.dp, vertical = 8.dp).semantics(mergeDescendants = true) { contentDescription = spoken; liveRegion = LiveRegionMode.Polite }.testTag("clipFailure")) {
        Text(f.title(), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text)
        Text(f.body(caps), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.offset(x = (-12).dp)) {
            if (f.problem == VideoProblem.Stalled) TextAction(stringResource(R.string.vclip_keep_checking), { onKeepWaiting(id) }, Modifier.testTag("clipKeepWaiting"))
            else if (f.problem.retry) TextAction(stringResource(R.string.vclip_try_again), { onRetry(id) }, Modifier.testTag("clipRetry"))
            TextAction(stringResource(R.string.vclip_remove), { onRemove(id) }, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("clipRemoveText"))
        }
    }
}

/** "n clips per video" and, once, what happens to them. Quiet text under the strip. */
@Composable
fun ClipCaption(caps: VideoUploadCaps?) {
    val per = caps?.clipsPerVideo ?: return
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(pluralStringResource(R.plurals.vclip_count_caption, per, per), style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textTertiary, modifier = Modifier.testTag("clipCaption"))
        Text(stringResource(R.string.vclip_usage_note), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("clipUsage"))
    }
}

/** Pick, then at once: "Use this clip's sound?". Both answers are equal in weight; neither is preselected for a new clip. */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun ClipSoundSheet(e: ClipEntry, onAnswer: (Boolean) -> Unit, onDismiss: () -> Unit) {
    val notice = VideoRules.notice(e.durationMs)
    val bmp = remember(e.thumb) { e.thumb?.let { runCatching { BitmapFactory.decodeByteArray(it, 0, it.size) }.getOrNull() } }
    val current = if (e.info != null) e.soundOn else null
    val view = LocalView.current
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), shape = RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet), containerColor = Vmk.colors.surface) {
        Column(Modifier.fillMaxWidth().padding(horizontal = Vmk.space.sheet).navigationBarsPadding().semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("clipSoundSheet"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (bmp != null) Image(bmp.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.size(width = (48f * e.aspect).coerceIn(40f, 72f).dp, height = 48.dp).clip(RoundedCornerShape(10.dp)))
                Text(stringResource(R.string.vclip_sheet_title), style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() })
                GlassIconButton(Sym.Close, stringResource(R.string.common_close), onDismiss, Modifier.testTag("clipSheetClose"))
            }
            // the one thing to know about length, always; the file's own length when it is longer
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Vmk.radii.field)).background(Vmk.colors.surfaceRaised).padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Sym.Schedule, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(18.dp))
                    Text(stringResource(R.string.vclip_notice_first), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, modifier = Modifier.testTag("clipNotice"))
                }
                notice.longerSeconds?.let { Text(stringResource(R.string.vclip_notice_longer, it), style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.textSecondary, modifier = Modifier.padding(start = 26.dp).testTag("clipNoticeLonger")) }
            }
            SoundChoice(Sym.VolumeUp, stringResource(R.string.vclip_sheet_keep), stringResource(R.string.vclip_sheet_keep_help), current == true, Modifier.testTag("clipKeepSound")) { view.announceForAccessibility(""); onAnswer(true) }
            SoundChoice(Sym.VolumeOff, stringResource(R.string.vclip_sheet_none), stringResource(R.string.vclip_sheet_none_help), current == false, Modifier.testTag("clipNoSound")) { onAnswer(false) }
            Text(stringResource(R.string.vclip_privacy), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textTertiary, modifier = Modifier.padding(bottom = 16.dp))
        }
    }
}

@Composable
private fun SoundChoice(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, help: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(Vmk.radii.card)
    Row(
        modifier.fillMaxWidth().heightIn(min = 64.dp).clip(shape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised)
            .clickable(role = Role.Button, onClick = onClick).padding(horizontal = 16.dp, vertical = 10.dp).semantics(mergeDescendants = true) { this.selected = selected; contentDescription = "$title. $help" },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Icon(icon, null, tint = Vmk.colors.primary, modifier = Modifier.size(24.dp))
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
            Text(help, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        }
        if (selected) Icon(Sym.Check, null, tint = Vmk.colors.primary, modifier = Modifier.size(22.dp))
    }
}
