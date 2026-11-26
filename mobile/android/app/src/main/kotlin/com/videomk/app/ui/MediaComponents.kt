package com.videomk.app.ui

import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.InputChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInWindow
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalViewConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import coil3.request.ImageRequest
import com.videomk.app.core.MediaGrouping
import com.videomk.app.core.MediaLabels
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.MediaSection
import com.videomk.app.core.QueueProgress
import com.videomk.app.core.StorageMeter
import kotlin.math.abs

/** A square thumbnail. Cached by photo id (memory and disk), never by URL: the link changes every hour, the image never does. */
@Composable
fun PhotoThumb(photo: MediaPhoto, modifier: Modifier = Modifier, contentScale: ContentScale = ContentScale.Crop) {
    val context = LocalContext.current
    val key = "media-thumb:${photo.id}"
    // without a link (offline, from the disk copy of the list) a placeholder address lets the cached image load by its key
    val model = remember(photo.id, photo.thumbUrl) {
        ImageRequest.Builder(context).data(photo.thumbUrl ?: "https://media.invalid/thumb/${photo.id}").memoryCacheKey(key).diskCacheKey(key).build()
    }
    Box(modifier.background(Vmk.colors.surfaceRaised)) {
        AsyncImage(model, contentDescription = null, contentScale = contentScale, modifier = Modifier.fillMaxSize())
    }
}

@Composable
fun rememberColumns(): Int = if (LocalConfiguration.current.screenWidthDp >= 600) 4 else 3

/** Skeleton tiles while the first page loads (still when animations are off). */
@Composable
fun SkeletonGrid(columns: Int, modifier: Modifier = Modifier) {
    val still = reduceMotion(LocalContext.current)
    val a = if (still) 0.6f else rememberInfiniteTransition(label = "skeleton").animateFloat(0.35f, 0.75f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "a").value
    Column(modifier.semantics { contentDescription = Txt.s(R.string.media_loading_photos) }.testTag("mediaSkeleton"), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        repeat(5) {
            Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                repeat(columns) { Box(Modifier.weight(1f).aspectRatio(1f).alpha(a).background(Vmk.colors.surfaceRaised)) }
            }
        }
    }
}

/**
 * The timeline: month headers that stick while their photos scroll, [columns] square thumbnails per row. Tap opens (or toggles while selecting); a long press
 * starts selecting; a horizontal drag while selecting selects every tile it passes over (a vertical drag still scrolls).
 */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun PhotoGrid(
    photos: List<MediaPhoto>, selected: Set<String>, selecting: Boolean, columns: Int,
    onOpen: (Int) -> Unit, onToggle: (String) -> Unit, onLongPress: (String) -> Unit, onDragSelect: (String) -> Unit,
    onNearEnd: () -> Unit, modifier: Modifier = Modifier, state: LazyListState = rememberLazyListState(), header: (@Composable () -> Unit)? = null,
    footer: (@Composable () -> Unit)? = null, flat: Boolean = false,
    order: Map<String, Int> = emptyMap(), dimUnselected: Boolean = false, localTiles: (@Composable () -> Unit)? = null, hiddenIds: Set<String> = emptySet(),
) {
    val bestFirst = stringResource(R.string.media_best_first)
    val shown = remember(photos, hiddenIds) { if (hiddenIds.isEmpty()) photos else photos.filter { it.id !in hiddenIds } }
    val sections = remember(shown, flat) { if (flat) listOf(MediaSection("relevance", bestFirst, shown)) else MediaGrouping.group(shown) }
    val indexById = remember(photos) { photos.withIndex().associate { it.value.id to it.index } }
    val bounds = remember { HashMap<String, Rect>() }
    var origin by remember { mutableStateOf(Offset.Zero) }
    val slop = LocalViewConfiguration.current.touchSlop

    LaunchedEffect(state, photos.size) {
        snapshotFlow { state.layoutInfo.visibleItemsInfo.lastOrNull()?.index to state.layoutInfo.totalItemsCount }.collect { (last, total) -> if (last != null && total > 0 && last >= total - 4) onNearEnd() }
    }

    LazyColumn(
        state = state,
        modifier = modifier.fillMaxSize().testTag("mediaGrid")
            .onGloballyPositioned { origin = it.positionInWindow() }
            .pointerInput(selecting) {
                if (!selecting) return@pointerInput
                awaitEachGesture {
                    val down = awaitFirstDown(requireUnconsumed = false, pass = PointerEventPass.Initial)
                    var total = Offset.Zero
                    var dragging = false
                    fun hit(p: Offset) { val w = p + origin; bounds.entries.firstOrNull { it.value.contains(w) }?.let { onDragSelect(it.key) } }
                    while (true) {
                        val ev = awaitPointerEvent(PointerEventPass.Initial)
                        val ch = ev.changes.firstOrNull { it.id == down.id } ?: break
                        if (!ch.pressed) break
                        total += ch.positionChange()
                        if (!dragging && abs(total.x) > slop && abs(total.x) > abs(total.y) * 1.5f) { dragging = true; hit(down.position) }
                        if (dragging) { ch.consume(); hit(ch.position) }
                    }
                }
            },
        contentPadding = PaddingValues(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        if (header != null) item(key = "header") { header() }
        if (localTiles != null) item(key = "local-tiles") { localTiles() }
        for (section in sections) {
            stickyHeader(key = "h-${section.key}") { SectionHeader(section) }
            val rows = section.items.chunked(columns)
            items(rows.size, key = { "r-${section.key}-${rows[it].first().id}" }) { r ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    for (p in rows[r]) {
                        val isSel = p.id in selected
                        val label = MediaLabels.photo(p)
                        val selectedText = stringResource(R.string.media_state_selected); val notSelectedText = stringResource(R.string.media_state_not_selected)
                        Box(
                            Modifier.weight(1f).aspectRatio(1f)
                                .onGloballyPositioned { bounds[p.id] = it.boundsInWindow() }
                                .semantics { contentDescription = label; this.selected = isSel; if (selecting) stateDescription = if (isSel) selectedText else notSelectedText }
                                .combinedClickable(
                                    role = Role.Button, onClickLabel = if (selecting) (if (isSel) stringResource(R.string.media_deselect) else stringResource(R.string.media_select)) else stringResource(R.string.media_open_photo),
                                    onLongClickLabel = stringResource(R.string.media_select_photos), onLongClick = { onLongPress(p.id) },
                                    onClick = { if (selecting) onToggle(p.id) else onOpen(indexById[p.id] ?: 0) },
                                )
                                .testTag("mediaTile"),
                        ) {
                            PhotoThumb(p, Modifier.fillMaxSize().padding(if (isSel) 8.dp else 0.dp).clip(RoundedCornerShape(if (isSel) 10.dp else 0.dp)).alpha(if (dimUnselected && !isSel) 0.45f else 1f))
                            if (isSel) Box(Modifier.fillMaxSize().border(3.dp, MaterialTheme.colorScheme.primary).background(MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)))
                            if (selecting) SelectBadge(isSel, order[p.id], Modifier.align(Alignment.TopEnd).padding(6.dp))
                        }
                    }
                    repeat(columns - rows[r].size) { Box(Modifier.weight(1f)) }
                }
            }
        }
        if (footer != null) item(key = "footer") { footer() }
    }
}

@Composable
private fun SectionHeader(section: MediaSection) {
    Text(
        section.title, style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text,
        modifier = Modifier.fillMaxWidth().background(Vmk.colors.background.copy(alpha = 0.96f)).padding(horizontal = 16.dp, vertical = 8.dp).semantics { contentDescription = Txt.n(R.plurals.media_section_desc, section.items.size, section.title) },
    )
}

@Composable
private fun SelectBadge(selected: Boolean, number: Int?, modifier: Modifier = Modifier) {
    Box(
        modifier.size(24.dp).clip(CircleShape)
            .background(if (selected) Vmk.gradientNow else androidx.compose.ui.graphics.SolidColor(Color.Black.copy(alpha = 0.3f)))
            .border(2.dp, Color.White, CircleShape),
        contentAlignment = Alignment.Center,
    ) {
        if (selected) { if (number != null) Text("$number", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = Color.White) else Icon(Icons.Filled.Check, null, tint = Color.White, modifier = Modifier.size(16.dp)) }
    }
}

/** The search field (40 dp, filled, no border) and, under it, what was understood as removable chips. */
@Composable
fun MediaSearchBar(vm: MediaViewModel, modifier: Modifier = Modifier, label: String? = null) {
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        androidx.compose.foundation.text.BasicTextField(
            value = vm.search.query, onValueChange = { vm.onQuery(it) }, singleLine = true,
            textStyle = MaterialTheme.typography.bodyMedium.copy(color = Vmk.colors.text),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(Vmk.colors.primary),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
            modifier = Modifier.fillMaxWidth().testTag("mediaSearch"),
            decorationBox = { inner ->
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 44.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised).padding(start = 12.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Icon(Icons.Filled.Search, null, tint = Vmk.colors.textTertiary, modifier = Modifier.size(20.dp))
                    Box(Modifier.weight(1f)) {
                        if (vm.search.query.isEmpty()) Text(stringResource(R.string.media_search_hint), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textTertiary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        inner()
                    }
                    if (vm.searching) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    else if (vm.search.active) IconButton(onClick = { vm.clearSearch() }, modifier = Modifier.size(44.dp)) { Icon(Icons.Filled.Close, stringResource(R.string.media_clear_search)) }
                    else Box(Modifier.size(12.dp))
                }
            },
        )
        if (label != null || vm.understoodChips.isNotEmpty()) {
            androidx.compose.foundation.lazy.LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                if (label != null) item { Text(label, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary) }
                items(vm.understoodChips.size, key = { vm.understoodChips[it].label }) { i ->
                    val chip = vm.understoodChips[i]
                    InputChip(
                        selected = true, onClick = { vm.dropChip(chip.label) }, label = { Text(chip.label) },
                        trailingIcon = { Icon(Icons.Filled.Close, null, Modifier.size(16.dp)) },
                        modifier = Modifier.semantics { contentDescription = "${chip.label}. Double tap to remove this filter" }.testTag("searchChip"),
                    )
                }
            }
        }
    }
}

/** The slim storage meter: green, amber from 85 %, red when full. Tapping it opens the Storage sheet. */
@Composable
fun StorageMeterRow(used: Long, limit: Long, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val state = StorageMeter.state(used, limit)
    val color = when (state) { StorageMeter.State.Ok -> MaterialTheme.colorScheme.primary; StorageMeter.State.Warning -> Vmk.colors.warning; StorageMeter.State.Full -> Vmk.colors.danger }
    val label = StorageMeter.label(used, limit)
    val text = when (state) { StorageMeter.State.Full -> stringResource(R.string.media_meter_full, label); StorageMeter.State.Warning -> stringResource(R.string.media_meter_almost_full, label); else -> label }
    val description = stringResource(R.string.media_storage_desc, text)
    Column(
        modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = Role.Button, onClickLabel = stringResource(R.string.media_open_storage), onClick = onClick)
            .semantics(mergeDescendants = true) { contentDescription = description }.testTag("storageMeter"),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        LinearProgressIndicator(progress = { StorageMeter.fraction(used, limit).toFloat() }, modifier = Modifier.fillMaxWidth().heightIn(min = 4.dp), color = color, trackColor = Vmk.colors.surfaceRaised)
        Text(text, style = MaterialTheme.typography.bodySmall, color = if (state == StorageMeter.State.Ok) Vmk.colors.textSecondary else color)
    }
}
