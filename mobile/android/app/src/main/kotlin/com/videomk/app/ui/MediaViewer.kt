package com.videomk.app.ui

import androidx.compose.ui.semantics.liveRegion
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.width
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.ui.input.pointer.positionChanged
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil3.compose.AsyncImage
import coil3.request.ImageRequest
import com.videomk.app.core.MediaGrouping
import com.videomk.app.core.MediaLabels
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.StorageMeter
import java.time.ZoneId

/** Full-screen viewer: swipe between photos, pinch to zoom (double tap resets), info, add to collection, delete, and "Make a video from this". */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MediaViewer(vm: MediaViewModel, startIndex: Int, onClose: () -> Unit, onMakeVideo: (MediaPhoto) -> Unit) {
    val photos = vm.photos
    if (photos.isEmpty()) { LaunchedEffect(Unit) { onClose() }; return }
    val pager = rememberPagerState(initialPage = startIndex.coerceIn(0, photos.size - 1)) { photos.size }
    var zoomed by remember { mutableStateOf(false) }
    var info by remember { mutableStateOf(false) }
    var collect by remember { mutableStateOf(false) }
    val current = photos.getOrNull(pager.currentPage)
    BackHandler(onBack = onClose)
    Dialog(onDismissRequest = onClose, properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Box(Modifier.fillMaxSize().background(Color.Black).testTag("mediaViewer")) {
            HorizontalPager(pager, Modifier.fillMaxSize(), userScrollEnabled = !zoomed, key = { photos.getOrNull(it)?.id ?: it }) { page ->
                val p = photos[page]
                ZoomableImage(p, vm, onZoomChange = { if (page == pager.currentPage) zoomed = it })
            }
            // the kit's glass buttons over the picture; the position is read out when the page changes
            val position = stringResource(R.string.media_viewer_position, pager.currentPage + 1, photos.size)
            Row(Modifier.statusBarsPadding().fillMaxWidth().padding(horizontal = Vmk.space.m, vertical = Vmk.space.xs), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                GlassIconButton(Sym.Close, stringResource(R.string.media_close_viewer), onClose, Modifier.testTag("viewerClose"), onDark = true)
                Text(position, style = MaterialTheme.typography.titleSmall, color = Color.White, modifier = Modifier.weight(1f).semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite })
                GlassIconButton(Sym.Info, stringResource(R.string.media_photo_details), { info = true }, Modifier.testTag("viewerInfo"), onDark = true)
            }
            // one labelled action (Make a video, with the play-sparkle) and two quiet icons
            val make: @Composable (Modifier) -> Unit = { m ->
                PrimaryButton(stringResource(R.string.media_make_video), { current?.let(onMakeVideo) }, m.testTag("viewerMakeVideo"), content = {
                    Icon(Sym.PlaySparkle, null, Modifier.size(22.dp), tint = androidx.compose.material3.LocalContentColor.current)
                    Text(stringResource(R.string.media_make_video), style = VmkType.cta, color = androidx.compose.material3.LocalContentColor.current, maxLines = 2)
                })
            }
            val icons: @Composable () -> Unit = {
                GlassIconButton(Sym.CreateNewFolder, stringResource(R.string.media_add_to_collection), { collect = true }, Modifier.testTag("viewerCollection"), onDark = true, size = 56.dp)
                GlassIconButton(Sym.Delete, stringResource(R.string.media_delete_this_photo), { current?.let { vm.deleteIds(listOf(it.id)) } }, Modifier.testTag("viewerDelete"), onDark = true, size = 56.dp)
            }
            // at large text the two icons sit above the button, so its label is never squeezed onto two lines
            if (isLargeText()) Column(Modifier.align(Alignment.BottomCenter).navigationBarsPadding().fillMaxWidth().padding(horizontal = Vmk.space.screen, vertical = Vmk.space.m), verticalArrangement = Arrangement.spacedBy(Vmk.space.s), horizontalAlignment = Alignment.End) {
                Row(horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) { icons() }
                make(Modifier.fillMaxWidth())
            } else Row(Modifier.align(Alignment.BottomCenter).navigationBarsPadding().fillMaxWidth().padding(horizontal = Vmk.space.screen, vertical = Vmk.space.m), horizontalArrangement = Arrangement.spacedBy(Vmk.space.s), verticalAlignment = Alignment.CenterVertically) {
                make(Modifier.weight(1f)); icons()
            }
        }
    }
    if (info && current != null) {
        ModalBottomSheet(onDismissRequest = { info = false }, containerColor = Vmk.colors.surface, shape = androidx.compose.foundation.shape.RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet)) {
            Column(Modifier.padding(horizontal = Vmk.space.sheet).padding(bottom = Vmk.space.xxl), verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                val day = MediaGrouping.dayOf(current, ZoneId.systemDefault())
                SheetHeader(day?.let { com.videomk.app.core.MediaDates.full(it) } ?: stringResource(R.string.media_date_unknown), { info = false })
                current.place?.let { Text(it, color = Vmk.colors.text) }
                Text("${current.w} x ${current.h} · ${StorageMeter.format(current.bytes)}", color = Vmk.colors.textSecondary)
                val names = vm.collections.filter { it.id in current.collections }.joinToString { it.name }
                Text(if (names.isEmpty()) stringResource(R.string.media_no_collection) else stringResource(R.string.media_in_collections, names), color = Vmk.colors.textSecondary)
            }
        }
    }
    if (collect && current != null) CollectionPickerDialog(vm, onDismiss = { collect = false }) { c -> vm.addToCollection(c, listOf(current.id)); collect = false }
}

@Composable
private fun ZoomableImage(photo: MediaPhoto, vm: MediaViewModel, onZoomChange: (Boolean) -> Unit) {
    val context = LocalContext.current
    var full by remember(photo.id) { mutableStateOf<String?>(null) }
    LaunchedEffect(photo.id) { full = vm.fullPhoto(photo.id)?.url }   // the full-size link is valid for 10 minutes: fetched when the photo is opened, never stored
    var scale by remember(photo.id) { mutableFloatStateOf(1f) }
    var offset by remember(photo.id) { mutableStateOf(Offset.Zero) }
    LaunchedEffect(scale) { onZoomChange(scale > 1.01f) }
    val model = remember(photo.id, full) {
        if (full != null) ImageRequest.Builder(context).data(full).memoryCacheKey("media-full:${photo.id}").diskCacheKey("media-full:${photo.id}").placeholderMemoryCacheKey("media-thumb:${photo.id}").build()
        else ImageRequest.Builder(context).data(photo.thumbUrl ?: "https://media.invalid/thumb/${photo.id}").memoryCacheKey("media-thumb:${photo.id}").diskCacheKey("media-thumb:${photo.id}").build()
    }
    Box(
        Modifier.fillMaxSize()
            .pointerInput(photo.id) {
                // two fingers (or one while zoomed in) move the image; one finger at normal size is left alone so the pager can swipe
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    do {
                        val ev = awaitPointerEvent()
                        if (ev.changes.count { it.pressed } >= 2 || scale > 1f) {
                            val zoom = ev.calculateZoom(); val pan = ev.calculatePan()
                            if (zoom != 1f || pan != Offset.Zero) {
                                scale = (scale * zoom).coerceIn(1f, 5f)
                                offset = if (scale > 1f) offset + pan * scale else Offset.Zero
                                ev.changes.forEach { if (it.positionChanged()) it.consume() }
                            }
                        }
                    } while (ev.changes.any { it.pressed })
                }
            }
            .pointerInput(photo.id) { detectTapGestures(onDoubleTap = { scale = if (scale > 1f) 1f else 2.5f; offset = Offset.Zero }) }
            .graphicsLayer { scaleX = scale; scaleY = scale; translationX = offset.x; translationY = offset.y }
            .semantics { contentDescription = MediaLabels.photo(photo) },
        contentAlignment = Alignment.Center,
    ) {
        AsyncImage(model, null, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
    }
}
