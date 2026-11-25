package com.videomk.app.ui

import android.app.Activity
import android.content.Intent
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.border
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.SelectAll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.videomk.app.core.MediaCollection
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.MediaSummary
import com.videomk.app.core.StorageMeter
import com.videomk.app.core.UploadTiles
import com.videomk.app.data.MediaUploadController
import com.videomk.app.data.PhotoSettings

const val PRIVACY_COPY = "Your photos are private to you. Only you can see them. Nobody at videomk browses them. They are used to find your photos and to make the videos you ask for. Delete any photo or everything, any time."

/** Opens the chooser (the phone's gallery, Google Photos and Files side by side) and hands back the picked content uris. Falls back to the system photo picker. */
@Composable
fun rememberPhotoChooser(onPicked: (List<Uri>) -> Unit): () -> Unit {
    val context = LocalContext.current
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(100.coerceAtMost(runCatching { android.provider.MediaStore.getPickImagesMaxLimit() }.getOrDefault(100)).coerceAtLeast(2))) { if (it.isNotEmpty()) onPicked(it) }
    val chooser = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val data = r.data
        if (r.resultCode == Activity.RESULT_OK && data != null) {
            val clip = data.clipData?.let { c -> (0 until c.itemCount).mapNotNull { c.getItemAt(it).uri } } ?: emptyList()
            val uris = com.videomk.app.core.PhotoIntake.extract(data.data, clip)
            uris.forEach { runCatching { context.contentResolver.takePersistableUriPermission(it, Intent.FLAG_GRANT_READ_URI_PERMISSION) } }
            if (uris.isNotEmpty()) onPicked(uris)
        }
    }
    return {
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE); putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION) }
        val handled = try { context.packageManager.queryIntentActivities(intent, 0).isNotEmpty() } catch (e: Exception) { false }
        try { if (handled) chooser.launch(Intent.createChooser(intent, "Add photos")) else picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) } catch (e: Exception) { /* nothing can pick photos here */ }
    }
}

/** The Media tab: title, storage, search, collections and the timeline, with the upload journey (local tiles, one bar, one toast) on top. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MediaScreen(
    vm: MediaViewModel, uploads: MediaUploadController?, onOpenCollection: (String) -> Unit,
    onMakeVideo: (List<MediaPhoto>) -> Unit,
) {
    val context = LocalContext.current
    val view = androidx.compose.ui.platform.LocalView.current
    LaunchedEffect(Unit) { vm.start(); vm.refreshLinksIfStale() }
    var storageOpen by rememberSaveable { mutableStateOf(false) }
    var barExpanded by rememberSaveable { mutableStateOf(false) }
    var toast by remember { mutableStateOf<String?>(null) }
    val choose = rememberPhotoChooser { uris -> uploads?.add(context.contentResolver, uris) }

    val progress = uploads?.queue?.progress?.collectAsState()?.value
    val items = uploads?.queue?.items?.collectAsState()?.value ?: emptyList()
    val preparing = uploads?.preparing?.collectAsState()?.value
    val skipped = uploads?.skipped?.collectAsState()?.value ?: 0
    LaunchedEffect(progress?.uploaded) { vm.onUploaded(progress?.uploaded ?: 0) }
    // back on this tab or back in the app: look again now; leaving stops the waiting
    androidx.lifecycle.compose.LifecycleResumeEffect(vm) { vm.onVisible(); onPauseOrDispose { vm.stopWaiting() } }
    val used = uploads?.queue?.usage?.collectAsState()?.value
    val listedIds = remember(vm.photos) { vm.photos.map { it.id }.toSet() }
    val stopped = progress != null && (progress.paused || progress.offline || progress.noSpace > 0)

    // the batch settles when every photo is finished and the server lists the added ones (or it stopped waiting): one summary, then the local tiles hand over to the grid
    val allFinished = items.isNotEmpty() && items.all { it.state.finished }
    val noProblems = items.none { it.state == com.videomk.app.core.UploadState.Failed || it.state == com.videomk.app.core.UploadState.NoSpace }
    val allListed = items.filter { it.state == com.videomk.app.core.UploadState.Done }.all { it.mediaId in listedIds }
    val settled = allFinished && noProblems && allListed
    val settledGaveUp = allFinished && noProblems && !allListed && vm.gettingReady == 0
    LaunchedEffect(settled, settledGaveUp) {
        if (!settled && !settledGaveUp) return@LaunchedEffect
        if (settledGaveUp) kotlinx.coroutines.delay(2500)
        val msg = UploadTiles.summary(items.count { it.state == com.videomk.app.core.UploadState.Done }, items.count { it.state == com.videomk.app.core.UploadState.Duplicate }, 0)
        toast = msg; view.announceForAccessibility(msg)
        kotlinx.coroutines.delay(1500)
        uploads?.queue?.dismissFinished(); uploads?.clearSkipped()
    }
    LaunchedEffect(toast) { if (toast != null) { kotlinx.coroutines.delay(8000); toast = null } }
    // polite, aggregated progress for screen readers: at most every 10 percent or 15 seconds, never per photo
    UploadAnnouncements(progress)

    // how long the finished photos have waited for the server ("Getting it ready" becomes "Still getting it ready")
    var finishedAt by remember { androidx.compose.runtime.mutableLongStateOf(0L) }
    var tickNow by remember { androidx.compose.runtime.mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(allFinished) { if (allFinished) { finishedAt = System.currentTimeMillis(); while (true) { kotlinx.coroutines.delay(5000); tickNow = System.currentTimeMillis() } } else finishedAt = 0L }
    val processingSeconds = if (finishedAt > 0) (tickNow - finishedAt) / 1000 else 0L
    val started = remember(progress?.active) { System.currentTimeMillis() }
    val elapsed = System.currentTimeMillis() - started

    Box(Modifier.fillMaxSize()) {
        Scaffold(
            containerColor = Vmk.colors.background,
            contentWindowInsets = WindowInsets(0),
            topBar = {
                Row(Modifier.fillMaxWidth().statusBarsPadding().padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Media", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, letterSpacing = (-0.9).sp, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() })
                    val shape = CircleShape
                    Row(Modifier.heightIn(min = 44.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape), verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = { vm.beginSelecting() }, modifier = Modifier.heightIn(min = 44.dp).testTag("selectMode")) { Text("Select", fontWeight = FontWeight.SemiBold) }
                        if (vm.summary?.readOnly != true) IconButton(onClick = choose, modifier = Modifier.size(44.dp).testTag("addMedia")) { Icon(Icons.Filled.Add, "Add photos to My media", tint = Vmk.colors.primary) }
                    }
                }
            },
            bottomBar = { SelectionBar(vm, onMakeVideo) },
        ) { padding ->
            Column(Modifier.fillMaxSize().padding(padding)) {
                val s = vm.summary
                if (s != null) StorageMeterRow(used?.first ?: s.usedBytes, used?.second ?: s.limitBytes, { storageOpen = true }, Modifier.padding(horizontal = 16.dp))
                if (vm.summary?.readOnly == true) Text("Read only until you are under your storage limit. You can still view and delete photos.", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp).testTag("readOnlyNote"))
                MediaSearchBar(vm, Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
                NoticeLine(vm)
                val columns = rememberColumns()
                val batchIds = remember(items) { items.mapNotNull { it.mediaId }.toSet() }
                MediaBody(
                    vm, onAdd = if (vm.summary?.readOnly == true) null else choose, onOpenCollection = onOpenCollection, onMakeVideo = onMakeVideo,
                    header = {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(bottom = 8.dp)) {
                            PrivacyNote()
                            if (!vm.search.active) CollectionsStrip(vm, onOpenCollection)
                        }
                    },
                    localTiles = if (items.isNotEmpty() && !vm.search.active) ({
                        UploadBatchSection(items, vm.photos, columns, stopped, processingSeconds = processingSeconds, onRetry = { uploads?.queue?.retry(it.id); uploads?.start() })
                    }) else null,
                    hiddenIds = if (items.isNotEmpty()) batchIds else emptySet(),
                )
            }
        }
        if (barExpanded) Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.18f)).clickable(onClickLabel = "Close upload details") { barExpanded = false })
        Column(Modifier.align(Alignment.BottomCenter).padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            toast?.let { MediaToast(it, "Got it", { toast = null }) }
            if (uploads != null && progress != null && !vm.selecting) UploadBar(
                progress, items, listedIds, preparing, elapsed, barExpanded, { barExpanded = it },
                onPause = { uploads.pause() }, onResume = { uploads.resume() }, onCancel = { uploads.cancel(); barExpanded = false },
                onRetry = { uploads.queue.retry(it.id); uploads.start() }, onRetryAll = { uploads.retryFailed() },
                onManageStorage = { storageOpen = true }, onNotNow = { uploads.queue.dismissFinished() },
            )
        }
    }
    if (storageOpen) vm.summary?.let { StorageSheet(it, used, onDismiss = { storageOpen = false }) }
}

/** Rate-limited, aggregated TalkBack announcements while uploading (docs/UI_DESIGN.md section m.5). */
@Composable
private fun UploadAnnouncements(progress: com.videomk.app.core.QueueProgress?) {
    val view = androidx.compose.ui.platform.LocalView.current
    var lastBucket by remember { mutableStateOf(-1) }
    var lastTime by remember { mutableStateOf(0L) }
    var lastState by remember { mutableStateOf("") }
    if (progress == null) return
    val state = when { progress.noSpace > 0 -> "Storage is full"; progress.offline -> "Waiting for connection"; progress.paused -> "Upload paused"; else -> "" }
    LaunchedEffect(state) { if (state.isNotEmpty() && state != lastState) view.announceForAccessibility(state); lastState = state }
    LaunchedEffect(progress.finished) {
        if (!progress.active || progress.total == 0) return@LaunchedEffect
        val bucket = progress.finished * 10 / progress.total
        val now = System.currentTimeMillis()
        if (bucket > lastBucket && (bucket != lastBucket || now - lastTime > 15_000) && progress.finished > 0) {
            lastBucket = bucket; lastTime = now
            view.announceForAccessibility("Uploaded ${progress.finished} of ${progress.total} photos.")
        }
    }
}

/** A collection's own screen: its photos in the same grid, with search and selection. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CollectionScreen(vm: MediaViewModel, collectionId: String, onBack: () -> Unit, onMakeVideo: (List<MediaPhoto>) -> Unit) {
    LaunchedEffect(Unit) { vm.start() }
    val collection = vm.collections.firstOrNull { it.id == collectionId }
    var menu by remember { mutableStateOf(false) }
    var rename by remember { mutableStateOf(false) }
    var delete by remember { mutableStateOf(false) }
    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            TopAppBar(
                title = { Text(listOfNotNull(collection?.emoji, collection?.name ?: "Collection").joinToString(" "), maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
                actions = {
                    Box {
                        TextButton(onClick = { menu = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("collectionMenu")) { Text("Edit") }
                        DropdownMenu(menu, { menu = false }) {
                            DropdownMenuItem(text = { Text("Rename") }, onClick = { menu = false; rename = true })
                            DropdownMenuItem(text = { Text("Delete collection", color = Vmk.colors.danger) }, onClick = { menu = false; delete = true })
                        }
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
            )
        },
        bottomBar = { SelectionBar(vm, onMakeVideo, inCollection = true) },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            NoticeLine(vm)
            MediaBody(vm, onAdd = null, onOpenCollection = {}, onMakeVideo = onMakeVideo, header = null)
        }
    }
    if (rename && collection != null) NameDialog("Rename collection", collection.name, "Save", onDismiss = { rename = false }) { vm.renameCollection(collection.id, it); rename = false }
    if (delete && collection != null) AlertDialog(
        onDismissRequest = { delete = false }, title = { Text("Delete \"${collection.name}\"?") },
        text = { Text("The photos stay in your library. Only the collection goes away.") },
        confirmButton = { TextButton(onClick = { delete = false; vm.deleteCollection(collection.id) { onBack() } }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Delete", color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = { delete = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    )
}

/** The grid with its loading, empty, error and offline states, and the full-screen viewer. */
@Composable
fun MediaBody(
    vm: MediaViewModel, onAdd: (() -> Unit)?, onOpenCollection: (String) -> Unit, onMakeVideo: (List<MediaPhoto>) -> Unit,
    header: (@Composable () -> Unit)?, modifier: Modifier = Modifier, selectionHint: String? = null,
    order: Map<String, Int> = emptyMap(), dimUnselected: Boolean = false, localTiles: (@Composable () -> Unit)? = null, hiddenIds: Set<String> = emptySet(),
) {
    val columns = rememberColumns()
    androidx.compose.material3.pulltorefresh.PullToRefreshBox(isRefreshing = vm.refreshing, onRefresh = { vm.pullRefresh() }, modifier = modifier.fillMaxSize()) {
    Box(Modifier.fillMaxSize()) {
        when {
            vm.photos.isEmpty() && localTiles != null -> PhotoGrid(
                photos = emptyList(), selected = emptySet(), selecting = false, columns = columns, onOpen = {}, onToggle = {}, onLongPress = {}, onDragSelect = {}, onNearEnd = {},
                header = header, localTiles = localTiles,
            )
            vm.loading && vm.photos.isEmpty() -> SkeletonGrid(columns, Modifier.padding(top = 4.dp))
            vm.error != null && vm.photos.isEmpty() -> StateMessage("Couldn't load your photos", vm.error!!, "Try again") { vm.refresh() }
            vm.photos.isEmpty() && vm.search.active && !vm.searching -> StateMessage("No photos match", "Try fewer words, or remove a filter above.", "Clear search") { vm.clearSearch() }
            vm.photos.isEmpty() && !vm.search.active && vm.gettingReady > 0 -> Column(Modifier.fillMaxSize()) {
                header?.invoke()
                Text("Getting ${vm.gettingReady} photo${if (vm.gettingReady == 1) "" else "s"} ready…", style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(16.dp).testTag("gettingReady"))
            }
            vm.photos.isEmpty() && !vm.search.active -> Column(Modifier.fillMaxSize()) {
                header?.invoke()
                StateMessage("Your photos, in one private place", if (onAdd != null) "Add photos once, then find them by describing them and make videos from them." else "No photos here yet. Add photos in the Media tab.", if (onAdd != null) "Add photos" else null) { onAdd?.invoke() }
            }
            else -> PhotoGrid(
                photos = vm.photos, selected = vm.selection.toSet(), selecting = vm.selecting, columns = columns,
                onOpen = { vm.viewerIndex = it }, onToggle = { vm.toggle(it) }, onLongPress = { vm.startSelecting(it) },
                onDragSelect = { id -> if (id !in vm.selection) vm.toggle(id) }, onNearEnd = { vm.loadMore() }, header = header, flat = vm.flatOrder,
                order = order, dimUnselected = dimUnselected, localTiles = localTiles, hiddenIds = hiddenIds,
                footer = { if (vm.offline) Text("Offline. Showing the photos saved on this phone.", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(16.dp)) },
            )
        }
        if (vm.search.active && vm.photos.isNotEmpty() && !vm.selecting) {
            TextButton(onClick = { vm.selectAllInView() }, modifier = Modifier.align(Alignment.BottomEnd).padding(8.dp).heightIn(min = 48.dp).testTag("selectAllInView")) {
                Icon(Icons.Filled.SelectAll, null, Modifier.size(18.dp)); Text("  Select all in this view")
            }
        }
    }
    }
    vm.viewerIndex?.let { idx ->
        MediaViewer(vm, startIndex = idx, onClose = { vm.viewerIndex = null }, onMakeVideo = { onMakeVideo(listOf(it)); vm.viewerIndex = null })
    }
}

@Composable
private fun StateMessage(title: String, text: String, button: String?, onClick: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(32.dp).testTag("mediaState"), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(Icons.Filled.PhotoLibrary, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(48.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, modifier = Modifier.padding(top = 12.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp, bottom = 16.dp))
        if (button != null) Button(onClick = onClick, modifier = Modifier.heightIn(min = 48.dp)) { Text(button) }
    }
}

@Composable
private fun NoticeLine(vm: MediaViewModel) {
    val n = vm.notice ?: return
    LaunchedEffect(n) { kotlinx.coroutines.delay(4000); if (vm.notice == n) vm.notice = null }
    Text(n, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp).semantics { contentDescription = n }.testTag("mediaNotice"))
}

@Composable
private fun PrivacyNote() {
    val context = LocalContext.current
    val settings = remember { PhotoSettings(context) }
    var seen by remember { mutableStateOf(settings.mediaPrivacySeen) }
    if (seen) return
    Column(Modifier.padding(horizontal = 16.dp).clip(RoundedCornerShape(14.dp)).background(Vmk.colors.surfaceRaised).padding(14.dp).testTag("privacyNote")) {
        Text("Private by design", style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text)
        Text(PRIVACY_COPY, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp))
        TextButton(onClick = { settings.mediaPrivacySeen = true; seen = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("privacyGotIt")) { Text("Got it") }
    }
}

// collections

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CollectionsStrip(vm: MediaViewModel, onOpen: (String) -> Unit) {
    var create by remember { mutableStateOf(false) }
    var menuFor by remember { mutableStateOf<MediaCollection?>(null) }
    var rename by remember { mutableStateOf<MediaCollection?>(null) }
    var delete by remember { mutableStateOf<MediaCollection?>(null) }
    LazyRow(contentPadding = PaddingValues(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.testTag("collectionsStrip")) {
        items(vm.collections, key = { it.id }) { c ->
            Box {
                Column(
                    Modifier.width(112.dp).clip(RoundedCornerShape(14.dp)).background(Vmk.colors.surface).heightIn(min = 72.dp)
                        .combinedClickable(
                            role = androidx.compose.ui.semantics.Role.Button, onClickLabel = "Open collection", onLongClickLabel = "Rename or delete",
                            onClick = { onOpen(c.id) }, onLongClick = { menuFor = c },
                        ).padding(12.dp).semantics(mergeDescendants = true) { contentDescription = "${c.name}, ${c.count} photo${if (c.count == 1) "" else "s"}" }.testTag("collectionCard"),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    if (c.coverId != null && c.coverThumbUrl != null) PhotoThumb(
                        MediaPhoto(c.coverId, null, "", null, 0, 0, 0, c.coverThumbUrl), Modifier.fillMaxWidth().height(56.dp).clip(RoundedCornerShape(8.dp)),
                    )
                    Text(c.emoji ?: "🖼️", style = MaterialTheme.typography.titleLarge)
                    Text(c.name, style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("${c.count} photo${if (c.count == 1) "" else "s"}", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                }
                DropdownMenu(menuFor?.id == c.id, { menuFor = null }) {
                    DropdownMenuItem(text = { Text("Rename") }, onClick = { rename = c; menuFor = null })
                    DropdownMenuItem(text = { Text("Delete", color = Vmk.colors.danger) }, onClick = { delete = c; menuFor = null })
                }
            }
        }
        item {
            Column(
                Modifier.width(112.dp).heightIn(min = 72.dp).clip(RoundedCornerShape(14.dp)).background(Vmk.colors.surfaceRaised)
                    .clickable(role = androidx.compose.ui.semantics.Role.Button, onClickLabel = "Create a collection") { create = true }.padding(12.dp).testTag("newCollection"),
                verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally,
            ) { Icon(Icons.Filled.Add, null, tint = MaterialTheme.colorScheme.primary); Text("New", color = Vmk.colors.text) }
        }
    }
    if (create) NameDialog("New collection", "", "Create", onDismiss = { create = false }) { vm.createCollection(it); create = false }
    rename?.let { c -> NameDialog("Rename collection", c.name, "Save", onDismiss = { rename = null }) { vm.renameCollection(c.id, it); rename = null } }
    delete?.let { c ->
        AlertDialog(
            onDismissRequest = { delete = null }, title = { Text("Delete \"${c.name}\"?") }, text = { Text("The photos stay in your library. Only the collection goes away.") },
            confirmButton = { TextButton(onClick = { vm.deleteCollection(c.id); delete = null }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Delete", color = Vmk.colors.danger) } },
            dismissButton = { TextButton(onClick = { delete = null }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
        )
    }
}

@Composable
fun NameDialog(title: String, initial: String, confirm: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var text by rememberSaveable { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(title) },
        text = { OutlinedTextField(text, { text = it.take(40) }, singleLine = true, label = { Text("Name") }, modifier = Modifier.fillMaxWidth().testTag("collectionName")) },
        confirmButton = { TextButton(onClick = { onConfirm(text.trim()) }, enabled = text.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp).testTag("collectionNameOk")) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    )
}

// selection

/** The bar at the bottom while selecting: Add to collection, Make a video, Delete (with a confirmation that it cannot be undone). */
@Composable
fun SelectionBar(vm: MediaViewModel, onMakeVideo: (List<MediaPhoto>) -> Unit, inCollection: Boolean = false) {
    if (!vm.selecting) return
    var pick by remember { mutableStateOf(false) }
    var confirm by remember { mutableStateOf(false) }
    val n = vm.selection.size
    Surface(color = Vmk.colors.surface, shadowElevation = 8.dp) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp).testTag("selectionBar"), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { vm.clearSelection() }, modifier = Modifier.size(48.dp)) { Icon(Icons.Filled.Close, "Cancel selection") }
            Text("$n selected", color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { contentDescription = "$n photos selected" })
            TextButton(onClick = { pick = true }, enabled = n > 0, modifier = Modifier.heightIn(min = 48.dp).testTag("addToCollection")) { Text("Collection") }
            TextButton(onClick = { onMakeVideo(vm.selectedPhotos().take(100)); vm.clearSelection() }, enabled = n > 0, modifier = Modifier.heightIn(min = 48.dp).testTag("makeVideo")) { Icon(Icons.Filled.Movie, null, Modifier.size(18.dp)); Text(" Video") }
            IconButton(onClick = { confirm = true }, enabled = n > 0, modifier = Modifier.size(48.dp).testTag("deleteSelected")) { Icon(Icons.Filled.Delete, "Delete selected photos", tint = if (n > 0) Vmk.colors.danger else Vmk.colors.textSecondary) }
        }
    }
    if (pick) CollectionPickerDialog(vm, onDismiss = { pick = false }) { c -> vm.addToCollection(c, vm.selection.toList()); pick = false }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        title = { Text(if (n == 1) "Delete this photo?" else "Delete $n photos?") },
        text = { Text("This removes ${if (n == 1) "it" else "them"} from your library for good. This cannot be undone.") },
        confirmButton = { TextButton(onClick = { confirm = false; vm.deleteSelected() }, modifier = Modifier.heightIn(min = 48.dp).testTag("confirmDelete")) { Text("Delete", color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = { confirm = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    )
}

@Composable
fun CollectionPickerDialog(vm: MediaViewModel, onDismiss: () -> Unit, onPick: (MediaCollection) -> Unit) {
    var creating by remember { mutableStateOf(false) }
    if (creating) { NameDialog("New collection", "", "Create and add", onDismiss = { creating = false }) { name -> vm.createCollection(name) { onPick(it) }; creating = false }; return }
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text("Add to collection") },
        text = {
            Column {
                vm.collections.forEach { c -> Text("${c.emoji ?: "🖼️"}  ${c.name}", color = Vmk.colors.text, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { onPick(c) }.padding(vertical = 12.dp)) }
                Text("+  New collection", color = MaterialTheme.colorScheme.primary, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { creating = true }.padding(vertical = 12.dp))
            }
        },
        confirmButton = {}, dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    )
}

// storage

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StorageSheet(summary: MediaSummary, live: Pair<Long, Long>?, onDismiss: () -> Unit) {
    val uri = LocalUriHandler.current
    val used = live?.first ?: summary.usedBytes
    val limit = live?.second ?: summary.limitBytes
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Vmk.colors.surface) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 32.dp).testTag("storageSheet"), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Storage", style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text)
            StorageMeterRow(used, limit, onClick = {})
            Row { Text("Plan", color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f)); Text(if (summary.plan == "pro") "Pro" else "Free", color = Vmk.colors.text) }
            Row { Text("Photos", color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f)); Text("${summary.count}", color = Vmk.colors.text) }
            Row { Text("Used", color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f)); Text(StorageMeter.label(used, limit), color = Vmk.colors.text) }
            Text("When your storage is full you can still view, download and delete your photos, but new photos can't be added until you delete some or get more space. We never delete anything for you.", style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            Text(PRIVACY_COPY, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            if (summary.canUpgrade) Button(onClick = { runCatching { uri.openUri("https://videomk.com/storage") } }, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("upgradeButton")) { Text("Get more storage") }
        }
    }
}
