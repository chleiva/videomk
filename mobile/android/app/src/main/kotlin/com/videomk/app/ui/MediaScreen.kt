package com.videomk.app.ui

import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.imePadding
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
    vm.undo = LocalContainerOrNull.current?.undo
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
            if (vm.photos.isNotEmpty()) TextAction(stringResource(R.string.media_select), { vm.beginSelecting() }, Modifier.testTag("selectMode"))
            Box {
                GlassIconButton(Sym.MoreHoriz, stringResource(R.string.media_more), { onMenu(true) }, Modifier.testTag("mediaMenu"))
                VmkMenu(menuOpen, { onMenu(false) }) {
                    if (organize != null) VmkMenuItem(stringResource(R.string.media_organize_library), Sym.AutoAwesome, Modifier.testTag("organizeLibrary")) { onMenu(false); organize.organizeLibrary() }
                    VmkMenuItem(stringResource(R.string.media_storage), Sym.CloudUpload) { onMenu(false); onStorage() }
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
fun CollectionScreen(vm: MediaViewModel, collectionId: String, onBack: () -> Unit, onMakeVideo: (List<MediaPhoto>) -> Unit, onAddPhotos: (() -> Unit)? = null) {
    vm.undo = LocalContainerOrNull.current?.undo
    LaunchedEffect(Unit) { vm.start() }
    val collection = vm.collections.firstOrNull { it.id == collectionId }
    var menu by remember { mutableStateOf(false) }
    var rename by remember { mutableStateOf(false) }
    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            if (vm.selecting) SelectionTopBar(vm) else VmkTopBar(title = listOfNotNull(collection?.emoji, collection?.name ?: stringResource(R.string.media_collection_default)).joinToString(" "), onBack = onBack) {
                if (vm.photos.isNotEmpty()) TextAction(stringResource(R.string.media_select), { vm.beginSelecting() }, Modifier.testTag("selectMode"))
                Box {
                    GlassIconButton(Sym.MoreHoriz, stringResource(R.string.media_edit), { menu = true }, Modifier.testTag("collectionMenu"))
                    VmkMenu(menu, { menu = false }) {
                        VmkMenuItem(stringResource(R.string.media_rename), Sym.Edit) { menu = false; rename = true }
                        if (collection != null) VmkMenuItem(stringResource(R.string.media_delete_collection), Sym.Delete, danger = true) { menu = false; vm.deleteCollection(collection.id) { onBack() } }
                    }
                }
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(top = padding.calculateTopPadding())) {
            Column(Modifier.fillMaxSize()) {
                NoticeLine(vm)
                // an empty collection offers the way to fill it: Media opens ready to select, and the folder button there adds to this collection
                MediaBody(vm, onAdd = onAddPhotos, onOpenCollection = {}, onMakeVideo = onMakeVideo, header = null, emptyInCollection = true)
            }
            Box(Modifier.align(Alignment.BottomCenter)) { SelectionBar(vm, onMakeVideo, inCollection = true) }
        }
    }
    if (rename && collection != null) NameDialog(stringResource(R.string.media_rename_collection), collection.name, stringResource(R.string.common_save), onDismiss = { rename = false }) { vm.renameCollection(collection.id, it); rename = false }
}

/** The grid with its loading, empty, error and offline states, and the full-screen viewer. */
@Composable
fun MediaBody(
    vm: MediaViewModel, onAdd: (() -> Unit)?, onOpenCollection: (String) -> Unit, onMakeVideo: (List<MediaPhoto>) -> Unit,
    header: (@Composable () -> Unit)?, modifier: Modifier = Modifier, selectionHint: String? = null,
    order: Map<String, Int> = emptyMap(), dimUnselected: Boolean = false, localTiles: (@Composable () -> Unit)? = null, hiddenIds: Set<String> = emptySet(), emptyInCollection: Boolean = false,
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
                if (emptyInCollection) StateMessage(stringResource(R.string.collection_empty_title), "", if (onAdd != null) stringResource(R.string.media_add_photos) else null) { onAdd?.invoke() }
                else StateMessage(stringResource(R.string.media_empty_title), if (onAdd != null) stringResource(R.string.media_empty_text) else stringResource(R.string.media_empty_text_pick), if (onAdd != null) stringResource(R.string.media_add_photos) else null) { onAdd?.invoke() }
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
        if (text.isNotBlank()) Text(text, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.padding(top = 4.dp))
        Spacer(Modifier.size(Vmk.space.l))
        if (button != null) TonalButton(button, onClick, Modifier.testTag("stateAction"), icon = Sym.AddPhotoAlternate.takeIf { button == stringResource(R.string.media_add_photos) })
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

/**
 * Collections on the Media tab: ONE row that opens the list ("Collections", how many), so the first photos are on screen without scrolling. With none yet the row
 * offers to make the first one. Rename and delete live in the list.
 */
@Composable
private fun CollectionsStrip(vm: MediaViewModel, @Suppress("UNUSED_PARAMETER") pref: com.videomk.app.core.OrganizePref, @Suppress("UNUSED_PARAMETER") onOpen: (String) -> Unit, onSeeAll: () -> Unit) {
    var create by remember { mutableStateOf(false) }
    Box(Modifier.padding(horizontal = Vmk.space.screen).clip(RoundedCornerShape(Vmk.radii.card)).background(Vmk.colors.surface)) {
        if (vm.collections.isEmpty()) VmkRow(stringResource(R.string.media_new_collection_text), Modifier.testTag("newCollection"), icon = Sym.CreateNewFolder, onClick = { create = true })
        else VmkRow(stringResource(R.string.media_collections), Modifier.testTag("seeAllCollections"), icon = Sym.PhotoLibrary, value = "${vm.collections.size}", trailing = Sym.ChevronRight, onClick = onSeeAll)
    }
    if (create) NameDialog(stringResource(R.string.media_new_collection), "", stringResource(R.string.media_create), onDismiss = { create = false }) { vm.createCollection(it); create = false }
}

/** Rename and Delete, with the quiet reassurance under them. */
@Composable
fun CollectionMenu(open: Boolean, onDismiss: () -> Unit, onRename: () -> Unit, onDelete: () -> Unit) {
    VmkMenu(open, onDismiss) {
        VmkMenuItem(stringResource(R.string.media_rename), Sym.Edit, Modifier.testTag("collectionRename"), onClick = onRename)
        VmkMenuItem(stringResource(R.string.media_delete_collection), Sym.Delete, Modifier.testTag("collectionDelete"), danger = true, onClick = onDelete)
    }
}

/** Naming a collection: a small sheet with the one field and the one button (a name is typed, so this is a form, not a confirmation). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NameDialog(title: String, initial: String, confirm: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var text by rememberSaveable { mutableStateOf(initial) }
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Vmk.colors.surface, shape = RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet)) {
        Column(Modifier.padding(horizontal = Vmk.space.sheet).padding(bottom = Vmk.space.xxl).imePadding(), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
            SheetHeader(title, onDismiss)
            VmkField(text, { text = it.take(40) }, Modifier.testTag("collectionName"), placeholder = stringResource(R.string.media_name))
            PrimaryButton(confirm, { onConfirm(text.trim()) }, Modifier.testTag("collectionNameOk"), enabled = text.isNotBlank())
        }
    }
}

// selection

/** The bar at the bottom while selecting: ONE primary button, "Make a video · N", with two quiet icons beside it (Add to collection, Delete with a confirmation). */
@Composable
fun SelectionBar(vm: MediaViewModel, onMakeVideo: (List<MediaPhoto>) -> Unit, inCollection: Boolean = false) {
    if (!vm.selecting) return
    var pick by remember { mutableStateOf(false) }
    val n = vm.selection.size
    val max = com.videomk.app.core.PhotoLimits.MAX_PHOTOS
    val used = minOf(n, max)   // a video takes at most [max] photos: the button says how many it will really use
    val makeLabel = if (n > 0) stringResource(R.string.media_make_video_count, used) else stringResource(R.string.media_make_video_none)
    val makeDesc = if (n > 0) stringResource(R.string.media_make_video_desc, used) else stringResource(R.string.media_make_video_none)
    // floats over the photos, which fade out beneath it: one labelled primary (Make a video · N) and two quiet icons
    val bg = Vmk.colors.background
    Column(Modifier.fillMaxWidth().background(androidx.compose.ui.graphics.Brush.verticalGradient(0f to bg.copy(alpha = 0f), 0.45f to bg.copy(alpha = 0.92f), 1f to bg)).navigationBarsPadding().padding(top = Vmk.space.xl)) {
        if (n > max) Text(stringResource(R.string.media_make_video_limit, max), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = Vmk.space.screen).testTag("makeVideoLimit"))
        val icons: @Composable () -> Unit = {
            GlassIconButton(Sym.CreateNewFolder, stringResource(R.string.media_add_to_collection), { pick = true }, Modifier.testTag("addToCollection"), enabled = n > 0, size = 56.dp, raised = true)
            GlassIconButton(Sym.Delete, stringResource(R.string.media_delete_selected), { vm.deleteSelected() }, Modifier.testTag("deleteSelected"), enabled = n > 0, size = 56.dp, tint = Vmk.colors.danger, raised = true)
        }
        val button: @Composable (Modifier) -> Unit = { m ->
            PrimaryButton(makeLabel, { onMakeVideo(vm.selectedPhotos().take(max)) }, m.testTag("makeVideo").semantics { contentDescription = makeDesc }, enabled = n > 0, content = {
                Icon(Sym.PlaySparkle, null, Modifier.size(22.dp), tint = androidx.compose.material3.LocalContentColor.current)
                Text(makeLabel, style = VmkType.cta, color = androidx.compose.material3.LocalContentColor.current, maxLines = 2, overflow = TextOverflow.Ellipsis)
            })
        }
        if (isLargeText()) Column(Modifier.fillMaxWidth().padding(horizontal = Vmk.space.screen, vertical = Vmk.space.s).testTag("selectionBar"), verticalArrangement = Arrangement.spacedBy(Vmk.space.s), horizontalAlignment = Alignment.End) {
            Row(horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) { icons() }
            button(Modifier.fillMaxWidth())
        } else Row(Modifier.fillMaxWidth().padding(horizontal = Vmk.space.screen, vertical = Vmk.space.s).testTag("selectionBar"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            button(Modifier.weight(1f)); icons()
        }
    }
    if (pick) CollectionPickerDialog(vm, onDismiss = { pick = false }) { c -> vm.addToCollection(c, vm.selection.toList()); pick = false }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CollectionPickerDialog(vm: MediaViewModel, onDismiss: () -> Unit, onPick: (MediaCollection) -> Unit) {
    var creating by remember { mutableStateOf(false) }
    if (creating) { NameDialog(stringResource(R.string.media_new_collection), "", stringResource(R.string.media_create_and_add), onDismiss = { creating = false }) { name -> vm.createCollection(name) { onPick(it) }; creating = false }; return }
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Vmk.colors.surface, shape = RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet)) {
        Column(Modifier.padding(horizontal = Vmk.space.sheet).padding(bottom = Vmk.space.xxl).verticalScroll(rememberScrollState())) {
            SheetHeader(stringResource(R.string.media_add_to_collection), onDismiss)
            vm.collections.forEach { c -> VmkRow(listOfNotNull(c.emoji, c.name).joinToString("  "), onClick = { onPick(c) }) }
            VmkRow(stringResource(R.string.media_new_collection), icon = Sym.CreateNewFolder, onClick = { creating = true })
        }
    }
}

// storage

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StorageSheet(summary: MediaSummary, live: Pair<Long, Long>?, onDismiss: () -> Unit) {
    val uri = LocalUriHandler.current
    val used = live?.first ?: summary.usedBytes
    val limit = live?.second ?: summary.limitBytes
    ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Vmk.colors.surface, shape = RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet)) {
        Column(Modifier.padding(horizontal = Vmk.space.sheet).padding(bottom = Vmk.space.xxl).testTag("storageSheet"), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
            SheetHeader(stringResource(R.string.media_storage), onDismiss)
            StorageMeterRow(used, limit, onClick = {})
            VmkGroup(onSheet = true) {
                VmkRow(stringResource(R.string.media_plan), value = if (summary.plan == "pro") stringResource(R.string.media_plan_pro) else summary.plan.replaceFirstChar { it.uppercase() }.ifBlank { stringResource(R.string.media_plan_free) })
                VmkRow(stringResource(R.string.media_photos_label), value = String.format(Txt.locale, "%,d", summary.count))
                VmkRow(stringResource(R.string.media_used), value = StorageMeter.label(used, limit))
            }
            Text(stringResource(R.string.media_storage_short), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            if (summary.canUpgrade) TonalButton(stringResource(R.string.media_get_more_storage), { runCatching { uri.openUri("https://videomk.com/storage") } }, Modifier.testTag("upgradeButton"), fill = true)
        }
    }
}

/** "Select all 38" next to the count (becomes "Clear" when everything in view is selected). Works on whatever is in view: all photos, a collection, a search. */
@Composable
fun SelectAllButton(vm: MediaViewModel, modifier: Modifier = Modifier) {
    if (vm.photos.isEmpty()) return
    val all = vm.allInViewSelected
    val label = SelectAll.label(all, vm.viewCount)
    Row(modifier.heightIn(min = Vmk.minTouch).clip(CircleShape).clickable(enabled = !vm.selectingAll, role = Role.Button) { vm.toggleSelectAll() }.padding(horizontal = Vmk.space.m).testTag("selectAllButton"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (vm.selectingAll) LiveRing(size = 16.dp) else Icon(Sym.SelectAll, null, Modifier.size(18.dp), tint = Vmk.colors.primary)
        Text(label, style = MaterialTheme.typography.titleSmall, color = Vmk.colors.primary)
    }
}
