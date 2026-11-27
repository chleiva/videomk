package com.videomk.app.ui

import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
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
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.widthIn
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
import androidx.compose.ui.semantics.Role
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
import com.videomk.app.core.SelectAll
import androidx.compose.foundation.layout.Spacer
import com.videomk.app.core.MediaSummary
import com.videomk.app.core.StorageMeter
import com.videomk.app.core.UploadTiles
import com.videomk.app.data.MediaUploadController
import com.videomk.app.data.PhotoSettings

val PRIVACY_COPY: String get() = Txt.s(R.string.media_privacy_copy)

/** Opens the chooser (the phone's gallery, Google Photos and Files side by side) and hands back the picked content uris. Falls back to the system photo picker. */
@Composable
fun rememberPhotoChooser(onPicked: (List<Uri>) -> Unit): () -> Unit {
    val context = LocalContext.current
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(100.coerceAtMost(runCatching { pickImagesMaxLimit() }.getOrDefault(100)).coerceAtLeast(2))) { if (it.isNotEmpty()) onPicked(it) }
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
        try { if (handled) chooser.launch(Intent.createChooser(intent, Txt.s(R.string.media_add_photos))) else picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) } catch (e: Exception) { /* nothing can pick photos here */ }
    }
}

/** The Media tab: title, storage, search, collections and the timeline, with the upload journey (local tiles, one bar, one toast) on top. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MediaScreen(
    vm: MediaViewModel, uploads: MediaUploadController?, onOpenCollection: (String) -> Unit,
    onMakeVideo: (List<MediaPhoto>) -> Unit, organize: com.videomk.app.data.OrganizeController? = null, onOpenCollections: () -> Unit = {},
    onSelectingChange: (Boolean) -> Unit = {},
) {
    val context = LocalContext.current
    val view = androidx.compose.ui.platform.LocalView.current
    LaunchedEffect(Unit) { vm.start(); vm.refreshLinksIfStale() }
    // while photos are being selected the tab bar and the round Create button step aside: the selection bar is the only thing at the bottom (one primary action)
    LaunchedEffect(vm.selecting) { onSelectingChange(vm.selecting) }
    androidx.compose.runtime.DisposableEffect(Unit) { onDispose { onSelectingChange(false) } }
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

    // smart collections: the prompt after a batch, the job's bar and its done toast
    val orgState = organize?.bar?.collectAsState()?.value ?: com.videomk.app.core.OrganizeState.Idle
    val orgPref = organize?.pref?.collectAsState()?.value ?: com.videomk.app.core.OrganizePref.Ask
    val orgDone = organize?.doneMessage?.collectAsState()?.value
    val orgChanges = organize?.changes?.collectAsState()?.value ?: 0
    var menuOpen by remember { mutableStateOf(false) }
    androidx.lifecycle.compose.LifecycleResumeEffect(organize) { organize?.setMediaVisible(true); organize?.refreshPref(); onPauseOrDispose { organize?.setMediaVisible(false) } }
    LaunchedEffect(orgChanges) { if (orgChanges > 0) vm.refresh() }
    LaunchedEffect(settled, settledGaveUp) { if ((settled || settledGaveUp) && uploads != null) { kotlinx.coroutines.delay(4000); organize?.onBatchReady(uploads.batchStart) } }
    OrganizeAnnouncements(orgState)
    if (organize != null) OrganizeSheetHost(organize)

    Box(Modifier.fillMaxSize()) {
        Scaffold(
            containerColor = Vmk.colors.background,
            contentWindowInsets = WindowInsets(0),
            topBar = {
                if (vm.selecting) SelectionTopBar(vm)
                else MediaHeader(vm, organize, menuOpen, { menuOpen = it }, onStorage = { storageOpen = true })
            },
        ) { padding ->
            Column(Modifier.fillMaxSize().padding(top = padding.calculateTopPadding())) {
                val s = vm.summary
                // the one labelled primary action of this screen: Add photos (the empty state carries its own button); hidden while selecting
                MediaSearchBar(vm, Modifier.padding(horizontal = Vmk.space.screen, vertical = 4.dp))
                if (!vm.selecting && s?.readOnly != true && (vm.photos.isNotEmpty() || items.isNotEmpty())) AddPhotosButton(choose, Modifier.padding(horizontal = Vmk.space.screen, vertical = Vmk.space.s))
                if (s != null && StorageMeter.shouldShow(used?.first ?: s.usedBytes, used?.second ?: s.limitBytes)) StorageMeterRow(used?.first ?: s.usedBytes, used?.second ?: s.limitBytes, { storageOpen = true }, Modifier.padding(horizontal = Vmk.space.screen))
                if (vm.summary?.readOnly == true) Text(stringResource(R.string.media_read_only), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.padding(horizontal = Vmk.space.screen, vertical = 4.dp).testTag("readOnlyNote"))
                NoticeLine(vm)
                val columns = rememberColumns()
                val batchIds = remember(items) { items.mapNotNull { it.mediaId }.toSet() }
                MediaBody(
                    vm, onAdd = if (vm.summary?.readOnly == true) null else choose, onOpenCollection = onOpenCollection, onMakeVideo = onMakeVideo,
                    header = {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(bottom = 8.dp)) {
                            MediaNotes(hasPhotos = vm.photos.isNotEmpty())
                            if (!vm.search.active && !vm.selecting) CollectionsStrip(vm, orgPref, onOpenCollection, onOpenCollections)
                        }
                    },
                    localTiles = if (items.isNotEmpty() && !vm.search.active) ({
                        UploadBatchSection(items, vm.photos, columns, stopped, processingSeconds = processingSeconds, onRetry = { uploads?.queue?.retry(it.id); uploads?.start() })
                    }) else null,
                    hiddenIds = if (items.isNotEmpty()) batchIds else emptySet(),
                )
            }
        }
        Box(Modifier.align(Alignment.BottomCenter)) { SelectionBar(vm, onMakeVideo) }
        if (barExpanded) Box(Modifier.fillMaxSize().background(Color.Black.copy(alpha = 0.18f)).clickable(onClickLabel = stringResource(R.string.media_close_upload_details)) { barExpanded = false })
        Column(Modifier.align(Alignment.BottomCenter).padding(bottom = 8.dp + LocalBarSpace.current), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            toast?.let { MediaToast(it, stringResource(R.string.media_got_it), { toast = null }) }
            orgDone?.let { msg ->
                LaunchedEffect(msg) { view.announceForAccessibility(msg); kotlinx.coroutines.delay(8000); organize?.consumeDone() }
                MediaToast(msg, stringResource(R.string.media_view), { organize?.consumeDone(); onOpenCollections() })
            }
            // never two bars: the upload bar owns the slot while photos are going up
            val uploadBarShown = uploads != null && progress != null && (preparing != null || items.isNotEmpty())
            if (!uploadBarShown && !vm.selecting && organize != null) OrganizeBar(orgState, onCancel = { organize.cancelJob() }, onRetry = { organize.retryJob() })
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

/** The idle header: the title, Select, and one overflow menu (Organize, Storage). Adding photos is its own labelled button below, never a bare "+". */
@Composable
private fun MediaHeader(vm: MediaViewModel, organize: com.videomk.app.data.OrganizeController?, menuOpen: Boolean, onMenu: (Boolean) -> Unit, onStorage: () -> Unit) {
    val bigText = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.3f   // large text: the title gets its own line, so a word is never cut in two
    val actions: @Composable () -> Unit = {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            if (vm.photos.isNotEmpty()) TextButton(onClick = { vm.beginSelecting() }, modifier = Modifier.heightIn(min = 48.dp).testTag("selectMode")) { Text(stringResource(R.string.media_select), fontWeight = FontWeight.SemiBold) }
            Box {
                GlassIconButton(Sym.MoreHoriz, stringResource(R.string.media_more), { onMenu(true) }, Modifier.testTag("mediaMenu"))
                DropdownMenu(menuOpen, { onMenu(false) }) {
                    if (organize != null) DropdownMenuItem(text = { Text(stringResource(R.string.media_organize_library)) }, leadingIcon = { Icon(Sym.AutoAwesome, null, tint = Vmk.colors.primary) }, onClick = { onMenu(false); organize.organizeLibrary() }, modifier = Modifier.testTag("organizeLibrary"))
                    DropdownMenuItem(text = { Text(stringResource(R.string.media_storage)) }, onClick = { onMenu(false); onStorage() })
                }
            }
        }
    }
    val titleLine: @Composable (Modifier) -> Unit = { m ->
        Text(stringResource(R.string.media_title), style = MaterialTheme.typography.headlineLarge, color = Vmk.colors.text, modifier = m.semantics { heading() })
    }
    if (bigText) Column(Modifier.fillMaxWidth().statusBarsPadding().padding(start = Vmk.space.screen, end = Vmk.space.screen, top = 8.dp, bottom = 6.dp), horizontalAlignment = Alignment.End) { titleLine(Modifier.fillMaxWidth()); actions() }
    else Row(Modifier.fillMaxWidth().statusBarsPadding().padding(start = Vmk.space.screen, end = Vmk.space.screen, top = 8.dp, bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) { titleLine(Modifier.weight(1f)); actions() }
}

/** While selecting: Close (X), "N selected" and Select all replace the title. Back closes it too (the system back gesture never leaves the screen with photos half-picked). */
@Composable
fun SelectionTopBar(vm: MediaViewModel) {
    BackHandler(enabled = vm.selecting) { vm.clearSelection() }
    val n = vm.selection.size
    val desc = stringResource(R.string.media_selection_top_desc)
    val count: @Composable (Modifier) -> Unit = { m ->
        Text(
            pluralStringResource(R.plurals.media_selected, n, n), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = 2,
            modifier = m.semantics { contentDescription = Txt.n(R.plurals.media_selected_desc, n); stateDescription = desc; heading() },
        )
    }
    // the count and "Select all" share a line when both fit; a longer language or larger text puts "Select all" on the next line instead of cutting a word
    Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = Vmk.space.screen - 12.dp, vertical = 4.dp).testTag("selectionTopBar"), verticalAlignment = Alignment.Top) {
        GlassIconButton(Sym.Close, stringResource(R.string.media_cancel_selection), { vm.clearSelection() }, Modifier.testTag("closeSelection"))
        androidx.compose.foundation.layout.FlowRow(Modifier.weight(1f).padding(start = 8.dp), horizontalArrangement = Arrangement.SpaceBetween, itemVerticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.heightIn(min = Vmk.minTouch), contentAlignment = Alignment.CenterStart) { count(Modifier) }
            SelectAllButton(vm)
        }
    }
}

/** "Add photos": the photo-plus glyph and the words on a tonal pill (the gradient belongs to the one primary action: New video, or Make a video while selecting). */
@Composable
private fun AddPhotosButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val label = stringResource(R.string.media_add_photos)
    Row(
        modifier.fillMaxWidth().heightIn(min = Vmk.primaryButton).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = Vmk.space.xxl, vertical = Vmk.space.m).testTag("addMedia"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s, Alignment.CenterHorizontally),
    ) {
        Icon(Sym.AddPhotoAlternate, null, Modifier.size(22.dp), tint = Vmk.colors.primary)
        Text(label, style = VmkType.cta, color = Vmk.colors.primary)
    }
}

/** Rate-limited, aggregated TalkBack announcements while uploading (docs/UI_DESIGN.md section m.5). */
@Composable
private fun UploadAnnouncements(progress: com.videomk.app.core.QueueProgress?) {
    val view = androidx.compose.ui.platform.LocalView.current
    var lastBucket by remember { mutableStateOf(-1) }
    var lastTime by remember { mutableStateOf(0L) }
    var lastState by remember { mutableStateOf("") }
    if (progress == null) return
    val state = when { progress.noSpace > 0 -> Txt.s(R.string.media_announce_storage_full); progress.offline -> Txt.s(R.string.media_announce_offline); progress.paused -> Txt.s(R.string.media_announce_paused); else -> "" }
    LaunchedEffect(state) { if (state.isNotEmpty() && state != lastState) view.announceForAccessibility(state); lastState = state }
    LaunchedEffect(progress.finished) {
        if (!progress.active || progress.total == 0) return@LaunchedEffect
        val bucket = progress.finished * 10 / progress.total
        val now = System.currentTimeMillis()
        if (bucket > lastBucket && (bucket != lastBucket || now - lastTime > 15_000) && progress.finished > 0) {
            lastBucket = bucket; lastTime = now
            view.announceForAccessibility(Txt.n(R.plurals.media_announce_uploaded, progress.total, progress.finished))
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
            if (vm.selecting) SelectionTopBar(vm) else VmkTopBar(title = listOfNotNull(collection?.emoji, collection?.name ?: stringResource(R.string.media_collection_default)).joinToString(" "), onBack = onBack) {
                if (vm.photos.isNotEmpty()) TextButton(onClick = { vm.beginSelecting() }, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("selectMode")) { Text(stringResource(R.string.media_select), style = MaterialTheme.typography.titleMedium) }
                Box {
                    GlassIconButton(Sym.MoreHoriz, stringResource(R.string.media_edit), { menu = true }, Modifier.testTag("collectionMenu"))
                    DropdownMenu(menu, { menu = false }, containerColor = Vmk.colors.surface) {
                        DropdownMenuItem(text = { Text(stringResource(R.string.media_rename)) }, onClick = { menu = false; rename = true })
                        DropdownMenuItem(text = { Text(stringResource(R.string.media_delete_collection), color = Vmk.colors.danger) }, onClick = { menu = false; delete = true })
                    }
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(top = padding.calculateTopPadding())) {
            Column(Modifier.fillMaxSize()) {
                NoticeLine(vm)
                MediaBody(vm, onAdd = null, onOpenCollection = {}, onMakeVideo = onMakeVideo, header = null)
            }
            Box(Modifier.align(Alignment.BottomCenter)) { SelectionBar(vm, onMakeVideo, inCollection = true) }
        }
    }
    if (rename && collection != null) NameDialog(stringResource(R.string.media_rename_collection), collection.name, stringResource(R.string.common_save), onDismiss = { rename = false }) { vm.renameCollection(collection.id, it); rename = false }
    if (delete && collection != null) AlertDialog(
        onDismissRequest = { delete = false }, title = { Text(stringResource(R.string.media_delete_collection_title, collection.name)) },
        text = { Text(stringResource(R.string.media_delete_collection_text)) },
        confirmButton = { TextButton(onClick = { delete = false; vm.deleteCollection(collection.id) { onBack() } }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_delete), color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = { delete = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_cancel)) } },
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
            vm.error != null && vm.photos.isEmpty() -> StateMessage(stringResource(R.string.media_load_failed), vm.error!!, stringResource(R.string.common_try_again)) { vm.refresh() }
            vm.photos.isEmpty() && vm.search.active && !vm.searching -> StateMessage(stringResource(R.string.media_no_match_title), stringResource(R.string.media_no_match_text), stringResource(R.string.media_clear_search)) { vm.clearSearch() }
            vm.photos.isEmpty() && !vm.search.active && vm.gettingReady > 0 -> Column(Modifier.fillMaxSize()) {
                header?.invoke()
                Text(pluralStringResource(R.plurals.media_getting_ready, vm.gettingReady, vm.gettingReady), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(16.dp).testTag("gettingReady"))
            }
            vm.photos.isEmpty() && !vm.search.active -> Column(Modifier.fillMaxSize()) {
                header?.invoke()
                StateMessage(stringResource(R.string.media_empty_title), if (onAdd != null) stringResource(R.string.media_empty_text) else stringResource(R.string.media_empty_text_pick), if (onAdd != null) stringResource(R.string.media_add_photos) else null) { onAdd?.invoke() }
            }
            else -> PhotoGrid(
                photos = vm.photos, selected = vm.selection.toSet(), selecting = vm.selecting, columns = columns,
                onOpen = { vm.viewerIndex = it }, onToggle = { vm.toggle(it) }, onLongPress = { vm.startSelecting(it) },
                onDragSelect = { id -> if (id !in vm.selection) vm.toggle(id) }, onNearEnd = { vm.loadMore() }, header = header, flat = vm.flatOrder,
                order = order, dimUnselected = dimUnselected, localTiles = localTiles, hiddenIds = hiddenIds,
                footer = { if (vm.offline) Text(stringResource(R.string.media_offline), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(16.dp)) },
            )
        }
        if (vm.search.active && vm.photos.isNotEmpty() && !vm.selecting) {
            TextButton(onClick = { vm.selectAllInView() }, modifier = Modifier.align(Alignment.BottomEnd).padding(8.dp).heightIn(min = 48.dp).testTag("selectAllInView")) {
                Icon(Sym.SelectAll, null, Modifier.size(18.dp)); Spacer(Modifier.width(6.dp)); Text(stringResource(R.string.media_select_all_in_view))
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
        Icon(Sym.PhotoLibrary, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(48.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, modifier = Modifier.padding(top = 12.dp))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp, bottom = 16.dp))
        if (button != null) Button(onClick = onClick, modifier = Modifier.heightIn(min = 48.dp)) { Text(button) }
    }
}

@Composable
private fun NoticeLine(vm: MediaViewModel) {
    val n = vm.notice ?: return
    LaunchedEffect(n) { kotlinx.coroutines.delay(4000); if (vm.notice == n) vm.notice = null }
    Text(n, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = Vmk.space.screen, vertical = 4.dp).semantics { contentDescription = n }.testTag("mediaNotice"))
}

@Composable
private fun MediaNotes(hasPhotos: Boolean) {
    val context = LocalContext.current
    val settings = remember { PhotoSettings(context) }
    var privacySeen by remember { mutableStateOf(settings.mediaPrivacySeen) }
    var hintSeen by remember { mutableStateOf(settings.mediaSelectHintSeen) }
    if (!privacySeen) {
        Column(Modifier.padding(horizontal = Vmk.space.screen).clip(RoundedCornerShape(14.dp)).background(Vmk.colors.surfaceRaised).padding(14.dp).testTag("privacyNote")) {
            Text(stringResource(R.string.media_private_title), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text)
            Text(PRIVACY_COPY, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp))
            TextButton(onClick = { settings.mediaPrivacySeen = true; privacySeen = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("privacyGotIt")) { Text(stringResource(R.string.media_got_it)) }
        }
    } else if (!hintSeen && hasPhotos) {
        // the one-time tip: how a person gets from photos to a video
        Row(Modifier.padding(horizontal = Vmk.space.screen).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Vmk.colors.surfaceRaised).padding(start = 14.dp, top = 4.dp, bottom = 4.dp, end = 4.dp).testTag("selectHint"), verticalAlignment = Alignment.CenterVertically) {
            Icon(Sym.Movie, null, tint = Vmk.colors.primary, modifier = Modifier.size(20.dp))
            Text(stringResource(R.string.media_select_hint), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, modifier = Modifier.weight(1f).padding(horizontal = 10.dp))
            TextButton(onClick = { settings.mediaSelectHintSeen = true; hintSeen = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("selectHintGotIt")) { Text(stringResource(R.string.media_got_it)) }
        }
    }
}

// collections

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun CollectionsStrip(vm: MediaViewModel, pref: com.videomk.app.core.OrganizePref, onOpen: (String) -> Unit, onSeeAll: () -> Unit) {
    var create by remember { mutableStateOf(false) }
    var menuFor by remember { mutableStateOf<MediaCollection?>(null) }
    var rename by remember { mutableStateOf<MediaCollection?>(null) }
    var delete by remember { mutableStateOf<MediaCollection?>(null) }
    if (vm.collections.isEmpty()) {
        // nothing to show yet: one quiet text button, no big tile
        TextButton(onClick = { create = true }, modifier = Modifier.padding(horizontal = 8.dp).heightIn(min = 48.dp).testTag("newCollection")) {
            Icon(Sym.CreateNewFolder, null, Modifier.size(20.dp)); Spacer(Modifier.width(8.dp)); Text(stringResource(R.string.media_new_collection_text), fontWeight = FontWeight.SemiBold)
        }
    } else {
    Row(Modifier.fillMaxWidth().padding(horizontal = Vmk.space.screen), verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(R.string.media_collections), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() })
        TextButton(onClick = onSeeAll, modifier = Modifier.heightIn(min = 44.dp).testTag("seeAllCollections")) { Text(stringResource(R.string.media_see_all), fontWeight = FontWeight.SemiBold) }
    }
    LazyRow(contentPadding = PaddingValues(horizontal = Vmk.space.screen), horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.testTag("collectionsStrip")) {
        items(vm.collections, key = { it.id }) { c ->
            Box {
                Column(
                    Modifier.width(104.dp)
                        .combinedClickable(
                            role = androidx.compose.ui.semantics.Role.Button, onClickLabel = stringResource(R.string.media_open_collection), onLongClickLabel = stringResource(R.string.media_rename_or_delete),
                            onClick = { onOpen(c.id) }, onLongClick = { menuFor = c },
                        ).semantics(mergeDescendants = true) { contentDescription = Txt.n(if (c.auto) R.plurals.media_collection_desc_auto else R.plurals.media_collection_desc, c.count, c.name) }.testTag("collectionCard"),
                    verticalArrangement = Arrangement.spacedBy(2.dp),
                ) {
                    Box(Modifier.size(104.dp).clip(RoundedCornerShape(18.dp)).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
                        if (c.coverId != null && c.coverThumbUrl != null) PhotoThumb(MediaPhoto(c.coverId, null, "", null, 0, 0, 0, c.coverThumbUrl), Modifier.fillMaxSize())
                        else Text(c.emoji ?: "🖼️", style = MaterialTheme.typography.headlineMedium)
                        if (c.auto) Box(Modifier.align(Alignment.TopStart).padding(6.dp).size(22.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.5f)).testTag("autoBadge"), contentAlignment = Alignment.Center) {
                            Icon(Sym.AutoAwesome, null, tint = Color.White, modifier = Modifier.size(13.dp))
                        }
                    }
                    Text(c.name, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(pluralStringResource(R.plurals.media_photos, c.count, c.count), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                }
                CollectionMenu(menuFor?.id == c.id, { menuFor = null }, onRename = { rename = c; menuFor = null }, onDelete = { delete = c; menuFor = null })
            }
        }
        item {
            // the one place to make a collection: the end of the row, a folder-plus icon with its words
            Column(
                Modifier.width(104.dp).clickable(role = androidx.compose.ui.semantics.Role.Button, onClickLabel = stringResource(R.string.media_create_collection)) { create = true }.testTag("newCollection"),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Box(Modifier.size(104.dp).clip(RoundedCornerShape(18.dp)).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) { Icon(Sym.CreateNewFolder, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(28.dp)) }
                Text(stringResource(R.string.media_new_collection_text), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 2)
            }
        }
    }
    }
    if (create) NameDialog(stringResource(R.string.media_new_collection), "", stringResource(R.string.media_create), onDismiss = { create = false }) { vm.createCollection(it); create = false }
    rename?.let { c -> NameDialog(stringResource(R.string.media_rename_collection), c.name, stringResource(R.string.common_save), onDismiss = { rename = null }) { vm.renameCollection(c.id, it); rename = null } }
    delete?.let { c -> DeleteCollectionDialog(c, pref, onDismiss = { delete = null }) { vm.deleteCollection(c.id); delete = null } }
}

/** Rename and Delete, with the quiet reassurance under them. */
@Composable
fun CollectionMenu(open: Boolean, onDismiss: () -> Unit, onRename: () -> Unit, onDelete: () -> Unit) {
    DropdownMenu(open, onDismiss) {
        DropdownMenuItem(text = { Text(stringResource(R.string.media_rename)) }, onClick = onRename, modifier = Modifier.testTag("collectionRename"))
        DropdownMenuItem(text = { Text(stringResource(R.string.media_delete_collection), color = Vmk.colors.danger) }, onClick = onDelete, modifier = Modifier.testTag("collectionDelete"))
        Text(stringResource(R.string.media_collection_menu_note), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = Vmk.space.screen, vertical = 8.dp).widthIn(max = 240.dp))
    }
}

@Composable
fun DeleteCollectionDialog(c: MediaCollection, pref: com.videomk.app.core.OrganizePref, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(stringResource(R.string.media_delete_collection_title, c.name)) },
        text = { Text(pluralStringResource(if (c.auto && pref == com.videomk.app.core.OrganizePref.Always) R.plurals.media_delete_collection_body_auto else R.plurals.media_delete_collection_body, c.count, c.count)) },
        confirmButton = { TextButton(onClick = onConfirm, modifier = Modifier.heightIn(min = 48.dp).testTag("confirmDeleteCollection")) { Text(stringResource(R.string.common_delete), color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_cancel)) } },
    )
}

@Composable
fun NameDialog(title: String, initial: String, confirm: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var text by rememberSaveable { mutableStateOf(initial) }
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(title) },
        text = { OutlinedTextField(text, { text = it.take(40) }, singleLine = true, label = { Text(stringResource(R.string.media_name)) }, modifier = Modifier.fillMaxWidth().testTag("collectionName")) },
        confirmButton = { TextButton(onClick = { onConfirm(text.trim()) }, enabled = text.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp).testTag("collectionNameOk")) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_cancel)) } },
    )
}

// selection

/** The bar at the bottom while selecting: ONE primary button, "Make a video · N", with two quiet icons beside it (Add to collection, Delete with a confirmation). */
@Composable
fun SelectionBar(vm: MediaViewModel, onMakeVideo: (List<MediaPhoto>) -> Unit, inCollection: Boolean = false) {
    if (!vm.selecting) return
    var pick by remember { mutableStateOf(false) }
    var confirm by remember { mutableStateOf(false) }
    val n = vm.selection.size
    val max = com.videomk.app.core.PhotoLimits.MAX_PHOTOS
    val used = minOf(n, max)   // a video takes at most [max] photos: the button says how many it will really use
    val makeLabel = if (n > 0) stringResource(R.string.media_make_video_count, used) else stringResource(R.string.media_make_video_none)
    val makeDesc = if (n > 0) stringResource(R.string.media_make_video_desc, used) else stringResource(R.string.media_make_video_none)
    // floats over the photos, which fade out beneath it: one labelled primary (Make a video · N) and two quiet icons
    val bg = Vmk.colors.background
    Column(Modifier.fillMaxWidth().background(androidx.compose.ui.graphics.Brush.verticalGradient(0f to bg.copy(alpha = 0f), 0.45f to bg.copy(alpha = 0.92f), 1f to bg)).navigationBarsPadding().padding(top = Vmk.space.xl)) {
        if (n > max) Text(stringResource(R.string.media_make_video_limit, max), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = Vmk.space.screen).testTag("makeVideoLimit"))
        Row(Modifier.fillMaxWidth().padding(horizontal = Vmk.space.screen, vertical = Vmk.space.s).testTag("selectionBar"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            PrimaryButton(makeLabel, { onMakeVideo(vm.selectedPhotos().take(max)) }, Modifier.weight(1f).testTag("makeVideo").semantics { contentDescription = makeDesc }, enabled = n > 0, content = {
                Icon(Sym.PlaySparkle, null, Modifier.size(22.dp), tint = androidx.compose.material3.LocalContentColor.current)
                Text(makeLabel, style = VmkType.cta, color = androidx.compose.material3.LocalContentColor.current, maxLines = 2, overflow = TextOverflow.Ellipsis)
            })
            GlassIconButton(Sym.CreateNewFolder, stringResource(R.string.media_add_to_collection), { pick = true }, Modifier.testTag("addToCollection"), enabled = n > 0, size = 56.dp, raised = true)
            GlassIconButton(Sym.Delete, stringResource(R.string.media_delete_selected), { confirm = true }, Modifier.testTag("deleteSelected"), enabled = n > 0, size = 56.dp, tint = Vmk.colors.danger, raised = true)
        }
    }
    if (pick) CollectionPickerDialog(vm, onDismiss = { pick = false }) { c -> vm.addToCollection(c, vm.selection.toList()); pick = false }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        title = { Text(pluralStringResource(R.plurals.media_delete_title, n, n)) },
        text = { Text(pluralStringResource(R.plurals.media_delete_text, n)) },
        confirmButton = { TextButton(onClick = { confirm = false; vm.deleteSelected() }, modifier = Modifier.heightIn(min = 48.dp).testTag("confirmDelete")) { Text(stringResource(R.string.common_delete), color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = { confirm = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_cancel)) } },
    )
}

@Composable
fun CollectionPickerDialog(vm: MediaViewModel, onDismiss: () -> Unit, onPick: (MediaCollection) -> Unit) {
    var creating by remember { mutableStateOf(false) }
    if (creating) { NameDialog(stringResource(R.string.media_new_collection), "", stringResource(R.string.media_create_and_add), onDismiss = { creating = false }) { name -> vm.createCollection(name) { onPick(it) }; creating = false }; return }
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(stringResource(R.string.media_add_to_collection)) },
        text = {
            Column {
                vm.collections.forEach { c -> Text("${c.emoji ?: "🖼️"}  ${c.name}", color = Vmk.colors.text, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { onPick(c) }.padding(vertical = 12.dp)) }
                Text(stringResource(R.string.media_new_collection_row), color = MaterialTheme.colorScheme.primary, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable { creating = true }.padding(vertical = 12.dp))
            }
        },
        confirmButton = {}, dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_cancel)) } },
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
            Text(stringResource(R.string.media_storage), style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text)
            StorageMeterRow(used, limit, onClick = {})
            Row { Text(stringResource(R.string.media_plan), color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f)); Text(if (summary.plan == "pro") stringResource(R.string.media_plan_pro) else stringResource(R.string.media_plan_free), color = Vmk.colors.text) }
            Row { Text(stringResource(R.string.media_photos_label), color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f)); Text(String.format(Txt.locale, "%,d", summary.count), color = Vmk.colors.text) }
            Row { Text(stringResource(R.string.media_used), color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f)); Text(StorageMeter.label(used, limit), color = Vmk.colors.text) }
            Text(stringResource(R.string.media_storage_full_text), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            Text(PRIVACY_COPY, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            if (summary.canUpgrade) Button(onClick = { runCatching { uri.openUri("https://videomk.com/storage") } }, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("upgradeButton")) { Text(stringResource(R.string.media_get_more_storage)) }
        }
    }
}

/** "Select all 38" next to the count (becomes "Clear" when everything in view is selected). Works on whatever is in view: all photos, a collection, a search. */
@Composable
fun SelectAllButton(vm: MediaViewModel, modifier: Modifier = Modifier) {
    if (vm.photos.isEmpty()) return
    val all = vm.allInViewSelected
    val label = SelectAll.label(all, vm.viewCount)
    TextButton(onClick = { vm.toggleSelectAll() }, enabled = !vm.selectingAll, modifier = modifier.heightIn(min = 48.dp).testTag("selectAllButton")) {
        if (vm.selectingAll) androidx.compose.material3.CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
        else Icon(Sym.SelectAll, null, Modifier.size(18.dp))
        Spacer(Modifier.width(6.dp)); Text(label, fontWeight = FontWeight.Bold)
    }
}
