package com.videomk.app.ui

import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import coil3.request.ImageRequest
import coil3.request.crossfade
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.QueueItem
import com.videomk.app.core.QueueProgress
import com.videomk.app.core.StorageMeter
import com.videomk.app.core.TileState
import com.videomk.app.core.UploadState
import com.videomk.app.core.UploadTiles
import java.io.File

/** The upload journey in the grid (docs/UI_DESIGN.md section m): the person's own pictures first, each with its state, swapped for the server thumbnail in place. */

/** "Adding 120 photos": local tiles for every photo of the batch, newest first. */
@Composable
fun UploadBatchSection(
    items: List<QueueItem>, photos: List<MediaPhoto>, columns: Int, stopped: Boolean, processingSeconds: Long, onRetry: (QueueItem) -> Unit,
) {
    if (items.isEmpty()) return
    val byId = remember(photos) { photos.associateBy { it.id } }
    val shown = remember(items) { items.reversed() }
    val done = items.count { it.state == UploadState.Done && byId.containsKey(it.mediaId) }
    val processing = items.count { it.state == UploadState.Done && !byId.containsKey(it.mediaId) }
    val addingText = pluralStringResource(R.plurals.upload_adding, items.size, items.size)
    val addingDesc = pluralStringResource(R.plurals.upload_adding_desc, items.size, items.size, done)
    Column(Modifier.fillMaxWidth().testTag("uploadBatch")) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = Vmk.space.screen, vertical = 8.dp).semantics(mergeDescendants = true) { heading(); contentDescription = addingDesc },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(addingText, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            Text(stringResource(R.string.upload_newest_first), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        }
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            for (row in shown.chunked(columns)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    for (qi in row) {
                        val server = qi.mediaId?.let { id -> byId[id] }
                        val state = UploadTiles.state(qi.state, server != null, stopped)
                        Box(Modifier.weight(1f)) {
                            LocalUploadTile(qi, server, state, showLabel = processing <= 12, secondsSince = processingSeconds, onRetry = { onRetry(qi) })
                        }
                    }
                    repeat(columns - row.size) { Box(Modifier.weight(1f)) }
                }
            }
        }
    }
}

private val Desaturate = ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(0.55f) })
private val Grey = ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(0f) })
private val Half = ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(0.5f) })

/** One square. Size never changes between states; the server picture fades in over the local one with the same crop. */
@Composable
fun LocalUploadTile(item: QueueItem, server: MediaPhoto?, state: TileState, showLabel: Boolean, secondsSince: Long, onRetry: () -> Unit) {
    val context = LocalContext.current
    val still = reduceMotion(context)
    val local = remember(item.path) { ImageRequest.Builder(context).data(File(item.path)).size(400).build() }
    val filter = when (state) { TileState.Queued -> Desaturate; TileState.Failed -> Grey; TileState.Waiting -> Half; else -> null }
    val dim = when (state) { TileState.Queued -> 0.28f; TileState.Uploading -> 0.38f; TileState.Waiting -> 0.34f; TileState.AlreadyThere -> 0.38f; else -> 0f }
    var tick by remember(item.id) { mutableStateOf(false) }
    LaunchedEffect(state) { if (state == TileState.Done) { tick = true; kotlinx.coroutines.delay(900); tick = false } }
    val desc = if (state == TileState.Failed) stringResource(R.string.upload_tile_failed_desc) else null
    Box(
        Modifier.fillMaxWidth().aspectRatio(1f).background(Vmk.colors.surfaceRaised)
            .then(if (state == TileState.Failed) Modifier.clickable(role = Role.Button, onClickLabel = stringResource(R.string.upload_retry_photo), onClick = onRetry) else Modifier)
            .then(if (desc != null) Modifier.semantics { contentDescription = desc } else Modifier.clearAndSetSemantics { })
            .testTag("uploadTile"),
    ) {
        AsyncImage(local, null, contentScale = ContentScale.Crop, colorFilter = filter, modifier = Modifier.fillMaxSize())
        if (server != null) {
            val ctx = LocalContext.current
            val key = "media-thumb:${server.id}"
            val req = remember(server.id, server.thumbUrl, still) {
                ImageRequest.Builder(ctx).data(server.thumbUrl ?: "https://media.invalid/thumb/${server.id}").memoryCacheKey(key).diskCacheKey(key).crossfade(if (still) 0 else 280).build()
            }
            AsyncImage(req, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        }
        if (dim > 0f) Box(Modifier.fillMaxSize().background(Color(0xFF0B0D2A).copy(alpha = dim)))
        when (state) {
            TileState.Queued -> Badge(Sym.Schedule, Modifier.align(Alignment.TopEnd).padding(6.dp))
            TileState.Waiting -> Badge(Sym.Pause, Modifier.align(Alignment.TopEnd).padding(6.dp))
            TileState.Uploading -> Box(Modifier.align(Alignment.Center).size(44.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(Modifier.size(44.dp), color = Color.White, trackColor = Color.White.copy(alpha = 0.35f), strokeWidth = 3.dp)
                Icon(Sym.CloudUpload, null, tint = Color.White, modifier = Modifier.size(18.dp))
            }
            TileState.Processing -> {
                Shimmer(Modifier.fillMaxSize())
                if (showLabel) GlassLabel(UploadTiles.processingLabel(secondsSince), Modifier.align(Alignment.BottomStart).padding(8.dp)) {
                    Icon(Sym.AutoAwesome, null, tint = Color.White, modifier = Modifier.size(12.dp))
                }
            }
            TileState.Done -> AnimatedVisibility(tick, Modifier.align(Alignment.TopEnd).padding(6.dp), exit = fadeOut(tween(if (still) 0 else 300))) {
                Box(Modifier.size(24.dp).clip(CircleShape).background(Color.White), contentAlignment = Alignment.Center) { Icon(Sym.Check, null, tint = Color(0xFF127035), modifier = Modifier.size(16.dp)) }
            }
            TileState.Failed -> {
                Box(Modifier.fillMaxSize().background(Color(0xFFB91C1C).copy(alpha = 0.55f)))
                Box(Modifier.align(Alignment.Center).size(44.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.9f)), contentAlignment = Alignment.Center) { Icon(Sym.Refresh, null, tint = Vmk.colors.danger) }
                Text(stringResource(R.string.upload_tap_retry), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Color(0xFFB91C1C), maxLines = 2, textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                    modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 8.dp).clip(CircleShape).background(Color.White).padding(horizontal = 8.dp, vertical = 3.dp))
            }
            TileState.AlreadyThere -> GlassLabel(stringResource(R.string.upload_already_there), Modifier.align(Alignment.Center), white = true) { Icon(Sym.Check, null, tint = Color(0xFF127035), modifier = Modifier.size(12.dp)) }
        }
    }
}

@Composable
private fun Badge(icon: androidx.compose.ui.graphics.vector.ImageVector, modifier: Modifier) {
    Box(modifier.size(24.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.45f)), contentAlignment = Alignment.Center) { Icon(icon, null, tint = Color.White, modifier = Modifier.size(14.dp)) }
}

@Composable
private fun GlassLabel(text: String, modifier: Modifier, white: Boolean = false, icon: @Composable () -> Unit) {
    Row(
        modifier.clip(CircleShape).background(if (white) Color.White.copy(alpha = 0.95f) else Color.Black.copy(alpha = 0.42f)).padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        icon()
        Text(text, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold, color = if (white) Color(0xFF11142B) else Color.White, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

/** A soft diagonal shimmer (a static lighter fill when animations are off). */
@Composable
private fun Shimmer(modifier: Modifier) {
    if (reduceMotion(LocalContext.current)) { Box(modifier.background(Color.White.copy(alpha = 0.08f))); return }
    val t by rememberInfiniteTransition(label = "tile-shimmer").animateFloat(0f, 1f, infiniteRepeatable(tween(2400, easing = LinearEasing), RepeatMode.Restart), label = "x")
    Box(modifier.drawBehind {
        val w = size.width * 0.8f
        val x = -w + (size.width + w) * t
        drawRect(Brush.linearGradient(listOf(Color.Transparent, Color.White.copy(alpha = 0.28f), Color.Transparent), start = Offset(x, 0f), end = Offset(x + w, size.height)))
    })
}

/**
 * The one upload bar (replaces the old banner): collapsed it is a single calm card with the overall ring, count, bytes and pause; expanded it adds the four
 * numbers, what needs the person, and the cancel/pause controls. Storage full and offline have their own looks.
 */
@Composable
fun UploadBar(
    progress: QueueProgress, items: List<QueueItem>, listedIds: Set<String>, preparing: Pair<Int, Int>?, elapsedMillis: Long,
    expanded: Boolean, onExpanded: (Boolean) -> Unit, onPause: () -> Unit, onResume: () -> Unit, onCancel: () -> Unit,
    onRetry: (QueueItem) -> Unit, onRetryAll: () -> Unit, onManageStorage: () -> Unit, onNotNow: () -> Unit, modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(24.dp)
    val storageFull = progress.noSpace > 0 && !progress.running
    var confirmCancel by remember { mutableStateOf(false) }
    val waitingCount = items.count { it.state == UploadState.Queued || it.state == UploadState.Uploading || it.state == UploadState.NoSpace }
    if (preparing == null && items.isEmpty()) return
    val stats = UploadTiles.stats(items, listedIds)
    val warnBar = storageFull || (!progress.active && progress.failed > 0)

    Column(
        modifier.fillMaxWidth().padding(horizontal = 12.dp).vmkShadow(3, shape, Vmk.colors.dark).clip(shape).background(Vmk.colors.surface)
            .border(if (warnBar) 1.5.dp else 1.dp, if (warnBar) Vmk.colors.warning else Vmk.colors.outline, shape).testTag("uploadBar"),
    ) {
        when {
            preparing != null -> {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(stringResource(R.string.upload_preparing, minOf(preparing.first + 1, preparing.second), preparing.second), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
                    LinearProgressIndicator(progress = { preparing.first.toFloat() / maxOf(preparing.second, 1) }, modifier = Modifier.fillMaxWidth(), trackColor = Vmk.colors.surface3)
                }
            }
            storageFull -> Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top) {
                    Box(Modifier.size(36.dp).clip(CircleShape).background(Vmk.colors.warningContainer), contentAlignment = Alignment.Center) { Icon(Sym.Warning, null, tint = Vmk.colors.warning) }
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(stringResource(R.string.upload_storage_full), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.testTag("storageFullMessage"))
                        Text(pluralStringResource(R.plurals.upload_no_space_waiting, progress.noSpace, progress.noSpace), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.heightIn(min = 44.dp).clip(CircleShape).background(Vmk.gradientNow).clickable(role = Role.Button, onClick = onManageStorage).padding(horizontal = 18.dp).testTag("manageStorage"), contentAlignment = Alignment.Center) {
                        Text(stringResource(R.string.upload_manage_storage), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Color.White)
                    }
                    Box(Modifier.heightIn(min = 44.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button, onClick = onNotNow).padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
                        Text(stringResource(R.string.organize_not_now), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary)
                    }
                }
            }
            else -> {
                val total = maxOf(progress.total, 1)
                val title = when {
                    progress.offline -> stringResource(R.string.organize_waiting)
                    progress.paused -> stringResource(R.string.upload_paused_progress, progress.finished, progress.total)
                    progress.active -> stringResource(R.string.upload_progress, minOf(progress.finished + 1, progress.total), progress.total)
                    progress.failed > 0 -> pluralStringResource(R.plurals.upload_need_you, progress.failed, progress.failed)
                    else -> UploadTiles.summary(progress.uploaded, progress.duplicates, progress.failed)
                }
                val left = (progress.bytesTotal - progress.bytesDone).coerceAtLeast(0)
                val toggleText = stringResource(if (expanded) R.string.upload_collapse else R.string.upload_expand)
                val sub = when {
                    progress.offline -> pluralStringResource(R.plurals.upload_auto_resume, waitingCount, waitingCount)
                    progress.active -> listOfNotNull(stringResource(R.string.upload_left, StorageMeter.format(left)), UploadTiles.etaText(left, progress.bytesDone, elapsedMillis)).joinToString(" · ")
                    else -> stringResource(R.string.upload_tap_review)
                }
                Row(
                    Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = stringResource(if (expanded) R.string.upload_collapse_details else R.string.upload_expand_details)) { onExpanded(!expanded) }
                        .padding(start = 14.dp, end = 4.dp, top = 12.dp, bottom = 12.dp).heightIn(min = 68.dp)
                        .semantics(mergeDescendants = true) { contentDescription = Txt.s(R.string.upload_bar_desc, title, sub, toggleText) },
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Box(Modifier.size(40.dp), contentAlignment = Alignment.Center) {
                        if (progress.offline) Icon(Sym.CloudOff, null, tint = Vmk.colors.warning)
                        else {
                            CircularProgressIndicator(progress = { progress.finished.toFloat() / total }, Modifier.size(40.dp), color = Vmk.colors.primary, trackColor = Vmk.colors.surface3, strokeWidth = 3.dp)
                            Icon(Sym.CloudUpload, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
                        }
                    }
                    Column(Modifier.weight(1f)) {
                        Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, maxLines = 2)
                        Text(sub, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, maxLines = 2)
                    }
                    if (progress.active && !progress.offline) IconButton(onClick = { if (progress.paused) onResume() else onPause() }, modifier = Modifier.size(48.dp).testTag(if (progress.paused) "uploadResume" else "uploadPause")) {
                        Icon(if (progress.paused) Sym.PlayArrow else Sym.Pause, stringResource(if (progress.paused) R.string.upload_resume_uploads else R.string.upload_pause_uploads), tint = Vmk.colors.text)
                    }
                    IconButton(onClick = { onExpanded(!expanded) }, modifier = Modifier.size(48.dp)) { Icon(if (expanded) Sym.ExpandMore else Sym.ExpandLess, toggleText, tint = Vmk.colors.textSecondary) }
                }
                if (progress.active) LinearProgressIndicator(progress = { progress.finished.toFloat() / total }, modifier = Modifier.fillMaxWidth().heightIn(min = 3.dp), color = Vmk.colors.primary, trackColor = Vmk.colors.surface3, drawStopIndicator = {})
                if (expanded) Expanded(progress, items, stats, onRetry, onRetryAll, onPause, onResume, onCancelAsk = { confirmCancel = true })
            }
        }
    }
    if (confirmCancel) AlertDialog(
        onDismissRequest = { confirmCancel = false },
        title = { Text(pluralStringResource(R.plurals.upload_cancel_title, waitingCount, waitingCount)) }, text = { Text(stringResource(R.string.upload_cancel_text)) },
        confirmButton = { TextButton(onClick = { confirmCancel = false; onCancel() }, modifier = Modifier.heightIn(min = 48.dp).testTag("confirmCancelUploads")) { Text(stringResource(R.string.upload_cancel_remaining), color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = { confirmCancel = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.upload_keep)) } },
    )
}

@Composable
private fun Expanded(
    progress: QueueProgress, items: List<QueueItem>, stats: UploadTiles.Stats, onRetry: (QueueItem) -> Unit, onRetryAll: () -> Unit,
    onPause: () -> Unit, onResume: () -> Unit, onCancelAsk: () -> Unit,
) {
    Column(Modifier.padding(horizontal = Vmk.space.screen).padding(bottom = 14.dp, top = 6.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Stat("${stats.added}", stringResource(R.string.upload_stat_added), Modifier.weight(1f)); Stat("${stats.gettingReady}", stringResource(R.string.upload_stat_getting_ready), Modifier.weight(1f))
            Stat("${stats.waiting}", stringResource(R.string.upload_stat_waiting), Modifier.weight(1f)); Stat("${stats.needYou}", stringResource(R.string.upload_stat_need_you), Modifier.weight(1f), danger = stats.needYou > 0)
        }
        val failed = items.filter { it.state == UploadState.Failed }
        if (failed.isNotEmpty()) {
            Overline(stringResource(R.string.upload_needs_attention))
            failed.forEachIndexed { i, it ->
                Row(Modifier.fillMaxWidth().heightIn(min = 52.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    AsyncImage(remember(it.path) { File(it.path) }, null, contentScale = ContentScale.Crop, modifier = Modifier.size(44.dp).clip(RoundedCornerShape(8.dp)).background(Vmk.colors.surfaceRaised))
                    Column(Modifier.weight(1f)) {
                        Text(stringResource(R.string.upload_photo_n, i + 1), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text)
                        Text(it.error ?: stringResource(R.string.upload_failed_default), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger, maxLines = 2)
                    }
                    Text(stringResource(R.string.upload_retry), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary,
                        modifier = Modifier.heightIn(min = 44.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button) { onRetry(it) }.padding(horizontal = 14.dp, vertical = 10.dp).testTag("retryOne"))
                }
            }
        }
        Text(stringResource(R.string.upload_close_app_note), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (progress.active || progress.paused) TextButton(onClick = onCancelAsk, modifier = Modifier.heightIn(min = 44.dp).testTag("uploadCancel")) { Text(stringResource(R.string.upload_cancel_remaining), color = Vmk.colors.danger, fontWeight = FontWeight.SemiBold) }
            Box(Modifier.weight(1f))
            if (failed.isNotEmpty() && !progress.active) TextButton(onClick = onRetryAll, modifier = Modifier.heightIn(min = 44.dp).testTag("uploadRetry")) { Text(stringResource(R.string.upload_retry_all), fontWeight = FontWeight.SemiBold) }
            if (progress.active) Box(
                Modifier.heightIn(min = 44.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button) { if (progress.paused) onResume() else onPause() }.padding(horizontal = 18.dp),
                contentAlignment = Alignment.Center,
            ) { Text(stringResource(if (progress.paused) R.string.upload_resume else R.string.upload_pause_all), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary) }
        }
    }
}

@Composable
private fun Stat(value: String, label: String, modifier: Modifier, danger: Boolean = false) {
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised).padding(vertical = 8.dp, horizontal = 6.dp).semantics(mergeDescendants = true) {}, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = if (danger) Vmk.colors.danger else Vmk.colors.text)
        Text(label, style = MaterialTheme.typography.labelSmall, color = if (danger) Vmk.colors.danger else Vmk.colors.textSecondary, maxLines = 2, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
    }
}

/** The one completion message ("120 photos added. 12 were already there.") as a dark toast with an action. */
@Composable
fun MediaToast(message: String, action: String?, onAction: () -> Unit, modifier: Modifier = Modifier) {
    Surface(modifier.padding(horizontal = 12.dp).fillMaxWidth().testTag("mediaToast"), shape = RoundedCornerShape(16.dp), color = Vmk.colors.inverseSurface) {
        val fg = Vmk.colors.inverseOnSurface
        Row(Modifier.heightIn(min = 52.dp).padding(start = 14.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(Sym.CheckCircle, null, tint = Color(0xFF4ADE80), modifier = Modifier.size(22.dp))
            Text(message, style = MaterialTheme.typography.bodyMedium, color = fg, modifier = Modifier.weight(1f).padding(vertical = 10.dp))
            if (action != null) TextButton(onClick = onAction, modifier = Modifier.heightIn(min = 44.dp)) { Text(action, color = if (Vmk.colors.dark) Color(0xFF4F52E0) else Color(0xFFB9BBFF), fontWeight = FontWeight.SemiBold) }
        }
    }
}
