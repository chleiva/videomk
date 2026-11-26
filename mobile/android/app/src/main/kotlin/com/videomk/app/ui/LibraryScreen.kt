package com.videomk.app.ui

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import com.videomk.app.core.RelativeTime
import com.videomk.app.core.Txt
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.animation.animateContentSize
import androidx.compose.material.icons.filled.Add
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.unit.sp
import com.videomk.app.core.MakingSteps
import com.videomk.app.core.CreateOptions
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.HourglassTop
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil3.compose.SubcomposeAsyncImage
import com.videomk.app.core.LibraryEntry
import com.videomk.app.core.LibraryRow
import com.videomk.app.core.DayGroups
import com.videomk.app.core.MakingSnapshot
import com.videomk.app.core.PendingVideo
import com.videomk.app.core.ProgressEstimator
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private class Example(@androidx.annotation.StringRes val text: Int, @androidx.annotation.StringRes val tag: Int, val minutes: Double?, val photos: Boolean, val icon: ImageVector)

private val Examples = listOf(
    Example(R.string.lib_example_lighthouse, R.string.lib_example_tag_1min, 1.0, false, Icons.Filled.Movie),
    Example(R.string.lib_example_bees, R.string.lib_example_tag_3min, 3.0, false, Icons.Filled.AutoAwesome),
    Example(R.string.lib_example_holiday, R.string.lib_example_tag_photos, null, true, Icons.Filled.Image),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(app: AppViewModel, composer: ComposerViewModel, onOpenVideo: (String) -> Unit, onOpenWallet: () -> Unit, onOpenSettings: () -> Unit, onOpenMedia: () -> Unit = {}, onNewVideo: () -> Unit = {}) {
    val state by app.state.collectAsState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val container = LocalContainerOrNull.current
    val listState = androidx.compose.foundation.lazy.rememberLazyListState()
    val person = (state.phase as? Phase.SignedIn)?.email
    /** Opens Create with what this person used last time; an example prefills the text and length (never sends). */
    fun newVideo(e: Example?) {
        composer.openCreate(container?.createPrefs?.load(person))
        if (e != null) {
            composer.text = Txt.s(e.text)
            if (e.minutes != null) composer.updateOptions(composer.options.copy(minutes = e.minutes))
            if (e.photos) composer.openAddPhotos(if (container?.mediaApi != null) 1 else 0)
        }
        onNewVideo()
    }

    LaunchedEffect(Unit) { app.refresh() }
    PollWhileRunning(app, state.hasRunningVideos)
    DisposableEffect(context) {
        // when the connection comes back, reload what could not be loaded
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) { if (app.state.value.offline || app.state.value.loadState is LoadState.Failed) scope.launch { app.refresh() } }
        }
        runCatching { cm?.registerDefaultNetworkCallback(cb) }
        onDispose { runCatching { cm?.unregisterNetworkCallback(cb) } }
    }

    Scaffold(
        containerColor = Vmk.colors.background,
        contentWindowInsets = WindowInsets(0),
        topBar = { MainTopBar(state.wallet, onOpenWallet, onOpenSettings) },
        bottomBar = {
            Column {
                // Create is docked above the tab bar, not floating: the list ends above it, so it can never cover a row
                if (state.entries.isNotEmpty() && !com.videomk.app.DebugHooks.emptyHome(context)) NewVideoBar { newVideo(null) }
                val progress = container?.mediaUploads?.queue?.progress?.collectAsState()?.value
                val imeVisible = WindowInsets.ime.getBottom(androidx.compose.ui.platform.LocalDensity.current) > 0
                val org = container?.organize?.bar?.collectAsState()?.value
                if (progress != null && progress.active && !imeVisible) UploadPill(progress, onOpenMedia)
                else if (org != null && !imeVisible) OrganizePill(org, onOpenMedia)   // never two pills: uploads first
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            val many = com.videomk.app.DebugHooks.manyVideos(context)
            val entries = if (com.videomk.app.DebugHooks.emptyHome(context)) emptyList() else if (many > 1) state.entries.flatMap { e ->
                if (e is LibraryEntry.Video) (0 until many).map { i -> LibraryEntry.Video(e.video.copy(id = e.video.id + "#" + i)) } else listOf(e)
            } else state.entries
            if (many > 1) LaunchedEffect(listState) { androidx.compose.runtime.snapshotFlow { listState.firstVisibleItemIndex * 100000 + listState.firstVisibleItemScrollOffset }.collect { android.util.Log.d("VMKSCROLL", "$it fab=${!listState.canScrollBackward}") } }
            when {
                entries.isEmpty() && (state.loadState is LoadState.Loading || state.loadState is LoadState.Idle) -> SkeletonFeed()
                entries.isEmpty() && state.loadState is LoadState.Failed ->
                    MessageState(stringResource(R.string.lib_load_failed_title), (state.loadState as LoadState.Failed).message, stringResource(R.string.common_try_again), { scope.launch { app.refresh() } })
                entries.isEmpty() -> EmptyState(
                    onExample = { e -> newVideo(e) },
                    onFirst = { app.submit(Txt.s(R.string.lib_first_prompt), CreateOptions(minutes = com.videomk.app.core.CreateDefaults.FIRST_TIME_MINUTES)) },
                    onChange = { newVideo(Example(R.string.lib_first_prompt, R.string.lib_example_tag_1min, com.videomk.app.core.CreateDefaults.FIRST_TIME_MINUTES, false, Icons.Filled.Movie)) },
                )
                else -> {
                    var refreshing by remember { mutableStateOf(false) }
                    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refresh(); refreshing = false } }) {
                        val rows = remember(entries) { DayGroups.rows(entries, java.time.Instant.now(), java.time.ZoneId.systemDefault()) }
                        val now = remember(entries) { System.currentTimeMillis() }
                        LazyColumn(
                            Modifier.fillMaxSize().testTag("videoList"), state = listState, contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 16.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            item(key = "title") { Text(stringResource(R.string.lib_title), style = MaterialTheme.typography.headlineMedium, color = Vmk.colors.text, modifier = Modifier.padding(bottom = 2.dp).semantics { heading() }) }
                            if (state.offline) item(key = "offline") { OfflineBanner(onRetry = { scope.launch { app.refresh() } }) }
                            items(rows, key = { it.key }, contentType = { if (it is LibraryRow.Header) "header" else if ((it as LibraryRow.Item).entry is LibraryEntry.Pending) "pending" else "video" }) { row ->
                                when (row) {
                                    is LibraryRow.Header -> DayHeader(row.bucket)
                                    is LibraryRow.Item -> when (val entry = row.entry) {
                                        is LibraryEntry.Pending -> PendingCard(entry.pending, onRetry = { app.retry(entry.pending.id) }, onDismiss = { app.dismissPending(entry.pending.id) })
                                        is LibraryEntry.Video -> {
                                            val v = entry.video
                                            val kind = if (v.status.isRunning) 0 else if (v.status == VideoStatus.Complete) 1 else 2
                                            // one item per video: Making settles into Ready with a cross-fade instead of a pop
                                            SettleCrossfade(kind, Modifier.animateItem()) { k ->
                                                when (k) {
                                                    0 -> MakingCard(rememberMakingSnapshot(v, state), Modifier.testTag("runningRow"), onClick = { onOpenVideo(v.id) })
                                                    1 -> VideoRow(v, v.createdAt?.let { RelativeTime.text(it.toEpochMilli(), now) }, remember(v.id, onOpenVideo) { { onOpenVideo(v.id) } })
                                                    else -> FailedRow(
                                                        title = state.briefs[v.id] ?: v.displayTitle, rejected = v.status == VideoStatus.Rejected, detail = v.rejectReason,
                                                        thumb = v.previewGifUrl, tag = "videoRow",
                                                        onRetry = state.briefs[v.id]?.let { brief -> { app.submit(brief, CreateOptions(state.minutes[v.id] ?: CreateOptions.DEFAULT_MINUTES)) } },
                                                        onDismiss = null,
                                                    )
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

/** The one entry to Create on a list that has videos: one full-width primary button docked above the tab bar (never over a row), text-driven height, 48 dp at least. */
@Composable
private fun NewVideoBar(onClick: () -> Unit) {
    val label = stringResource(R.string.lib_new_video)
    Box(Modifier.fillMaxWidth().background(Vmk.colors.background).padding(horizontal = Vmk.space.screen, vertical = Vmk.space.s)) {
        PrimaryButton(label, onClick, Modifier.testTag("newVideoFab").semantics { contentDescription = label }) {
            Icon(Icons.Filled.Add, null, tint = Vmk.colors.onPrimary, modifier = Modifier.size(24.dp)); Spacer(Modifier.width(8.dp))
            Text(label, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.onPrimary, textAlign = TextAlign.Center)
        }
    }
}

@Composable
private fun MainTopBar(wallet: com.videomk.app.core.WalletInfo?, onOpenWallet: () -> Unit, onOpenSettings: () -> Unit) {
    Row(Modifier.fillMaxWidth().statusBarsPadding().heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            LogoMark()
            Text("videomk", style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, maxLines = 1)
        }
        wallet?.let { w ->
            val shape = CircleShape
            val unlimitedDesc = stringResource(R.string.lib_unlimited_credits)
            val creditsDesc = pluralStringResource(R.plurals.lib_credits_desc, w.balance, w.balance)
            Row(
                Modifier.heightIn(min = 44.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
                    .clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_show_credits), onClick = onOpenWallet).padding(horizontal = 14.dp)
                    .semantics(mergeDescendants = true) { contentDescription = if (w.unlimited) unlimitedDesc else creditsDesc }
                    .testTag("balanceChip"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Icon(Icons.Filled.Bolt, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
                Text(if (w.unlimited) "∞" else "${w.balance}", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
            }
        }
        IconButton(onClick = onOpenSettings, modifier = Modifier.size(48.dp).testTag("settingsButton")) {
            Icon(Icons.Filled.Settings, stringResource(R.string.lib_settings), tint = Vmk.colors.textSecondary)
        }
    }
}

@Composable
private fun OfflineBanner(onRetry: () -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = Vmk.colors.warningContainer, modifier = Modifier.fillMaxWidth().testTag("offlineBanner")) {
        Row(Modifier.padding(start = 14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Filled.CloudOff, null, tint = Vmk.colors.warning)
            Text(stringResource(R.string.lib_offline_banner), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            TextButton(onClick = onRetry, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.lib_retry)) }
        }
    }
}

/** Skeleton rows with the final shape of a video row while the list loads (the title is real: the screen never looks empty). */
@Composable
private fun SkeletonFeed() {
    val still = reduceMotion(LocalContext.current)
    val loadingDesc = stringResource(R.string.lib_loading_desc)
    val a = if (still) 0.7f else rememberInfiniteTransition(label = "sk").animateFloat(0.45f, 0.9f, infiniteRepeatable(tween(1000), RepeatMode.Reverse), label = "a").value
    Column(Modifier.fillMaxSize().padding(16.dp).semantics { contentDescription = loadingDesc }, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(stringResource(R.string.lib_title), style = MaterialTheme.typography.headlineMedium, color = Vmk.colors.text)
        repeat(4) {
            Row(Modifier.fillMaxWidth().alpha(a).clip(RoundedCornerShape(Vmk.radii.card)).background(Vmk.colors.surface).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.width(128.dp).height(72.dp).clip(RoundedCornerShape(Vmk.radii.thumb)).background(Vmk.colors.surfaceRaised))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(Modifier.fillMaxWidth().height(14.dp).clip(CircleShape).background(Vmk.colors.surfaceRaised))
                    Box(Modifier.fillMaxWidth(0.6f).height(12.dp).clip(CircleShape).background(Vmk.colors.surfaceRaised))
                }
            }
        }
    }
}

/** First launch: one promise, a first video that is already written (30 s, 1 credit), and three worked examples. Examples fill Create; none of them sends. */
@Composable
private fun EmptyState(onExample: (Example) -> Unit, onFirst: () -> Unit, onChange: () -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 16.dp).testTag("emptyState"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.padding(top = 12.dp).height(96.dp).fillMaxWidth().clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
            Frame(-7f, (-34).dp, listOf(Color(0xFFF2B27A), Color(0xFF8E4B63)))
            Frame(7f, 34.dp, listOf(Color(0xFF2A2A66), Color(0xFF6C4BC1)))
            Frame(0f, 0.dp, listOf(Color(0xFFFFC27A), Color(0xFFB9556F)), front = true)
        }
        Text(stringResource(R.string.lib_empty_title), style = MaterialTheme.typography.headlineMedium, textAlign = TextAlign.Center, color = Vmk.colors.text, modifier = Modifier.padding(top = 8.dp).semantics { heading() })
        Text(stringResource(R.string.lib_empty_body), style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 8.dp, bottom = 16.dp))
        FirstVideoCard(onFirst, onChange)
        Overline(stringResource(R.string.lib_try_one), Modifier.fillMaxWidth().padding(top = 20.dp, bottom = 8.dp))
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (e in Examples) {
                val shape = RoundedCornerShape(18.dp)
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
                        .clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_use_idea)) { onExample(e) }.padding(horizontal = 12.dp, vertical = 8.dp).testTag("exampleCard"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(e.icon, null, tint = Vmk.colors.primary, modifier = Modifier.size(22.dp)) }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(stringResource(e.text), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text)
                        Text(stringResource(e.tag), style = MaterialTheme.typography.labelMedium, color = Vmk.colors.primary, modifier = Modifier.clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 10.dp, vertical = 3.dp))
                    }
                }
            }
        }
    }
}

/** "Make your first video": the prompt is already there, 30 s and 1 credit. The button makes it as it is (no question sheet); "Change the idea" opens Create with it filled in. */
@Composable
private fun FirstVideoCard(onMake: () -> Unit, onChange: () -> Unit) {
    val shape = RoundedCornerShape(Vmk.radii.videoCard)
    Column(
        Modifier.fillMaxWidth().clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape).padding(Vmk.space.l).testTag("firstVideoCard"),
        verticalArrangement = Arrangement.spacedBy(Vmk.space.m),
    ) {
        Text(stringResource(R.string.lib_first_title), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
        Text(stringResource(R.string.quoted, stringResource(R.string.lib_first_prompt)), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text,
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(Vmk.radii.field)).background(Vmk.colors.primaryContainer).padding(Vmk.space.m))
        Text(stringResource(R.string.lib_first_sub), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
        PrimaryButton(stringResource(R.string.lib_first_cta), onMake, Modifier.testTag("firstVideoMake"))
        TextButton(onClick = onChange, modifier = Modifier.fillMaxWidth().heightIn(min = Vmk.minTouch).testTag("newVideoButton")) {   // opens Create with the idea filled in (UI tests use it as "New video")
            Text(stringResource(R.string.lib_first_edit), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.primary)
        }
    }
}

@Composable
private fun Frame(rotate: Float, dx: androidx.compose.ui.unit.Dp, colors: List<Color>, front: Boolean = false) {
    Box(
        Modifier.offset(x = dx, y = if (front) (-6).dp else 4.dp).rotate(rotate).size(width = 104.dp, height = 66.dp).clip(RoundedCornerShape(14.dp))
            .background(Brush.linearGradient(colors)),
    )
}

// rows and cards: the shared components live in Components.kt

fun duration(s: Double): String = "%d:%02d".format(s.toInt() / 60, s.toInt() % 60)
fun elapsed(s: Long): String { val t = maxOf(0L, s); return "%d:%02d".format(t / 60, t % 60) }

/** What the one waiting component shows for a running video: the same value is used by the home card and the detail screen. */
@Composable
fun rememberMakingSnapshot(video: VideoItem, state: AppState): MakingSnapshot {
    val stage = (video.status as? VideoStatus.Running)?.stage ?: VideoStatus.Stage.Starting
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(1000); now = System.currentTimeMillis() } }
    val since = state.stageSince[video.id]?.sinceMillis
    val inStage = since?.let { (now - it) / 1000.0 } ?: 0.0
    val minutes = state.minutes[video.id] ?: CreateOptions.DEFAULT_MINUTES
    val title = state.briefs[video.id] ?: video.title?.takeIf { it.isNotEmpty() } ?: stringResource(R.string.lib_making_title)
    return MakingSnapshot.of(title, stage, inStage, minutes)
}

/** The request is on its way (or failed before the server answered): the same card as a running one, so the list never jumps. */
@Composable
private fun PendingCard(pending: PendingVideo, onRetry: () -> Unit, onDismiss: () -> Unit) {
    val failed = (pending.state as? PendingVideo.State.Failed)?.message
    if (failed != null) { FailedRow(pending.brief, false, failed, null, "failedRow", onRetry, onDismiss); return }
    val st = pending.state
    val line = when (st) {
        is PendingVideo.State.Uploading -> stringResource(R.string.lib_pending_uploading, minOf(st.done + 1, st.total), st.total)
        else -> stringResource(R.string.lib_pending_sending)
    }
    MakingCard(MakingSnapshot.pending(pending.brief, line, if (st is PendingVideo.State.Uploading) 0.2 * st.done / maxOf(st.total, 1) else 0.0), Modifier.testTag("pendingRow"))
}

/** The slim pill on the Videos tab while photos upload: opens Media. */
@Composable
private fun UploadPill(progress: com.videomk.app.core.QueueProgress, onClick: () -> Unit) {
    val text = stringResource(R.string.lib_upload_pill, minOf(progress.finished + 1, progress.total), progress.total)
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp).heightIn(min = 44.dp).clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_open_media), onClick = onClick),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically,
    ) {
        Row(Modifier.heightIn(min = 36.dp).clip(CircleShape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, CircleShape).padding(horizontal = 16.dp).semantics(mergeDescendants = true) { contentDescription = text }.testTag("uploadPill"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Filled.CloudUpload, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
            Text(text, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text)
        }
    }
}

/** A calm moving highlight on a placeholder thumbnail. Static when animations are off. */
@Composable
fun ShimmerThumb(icon: ImageVector, animate: Boolean, modifier: Modifier = Modifier) {
    val still = reduceMotion(LocalContext.current)
    Box(modifier.background(Vmk.colors.surfaceRaised).clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
        if (animate && !still) {
            val t by rememberInfiniteTransition(label = "shimmer").animateFloat(0f, 1f, infiniteRepeatable(tween(1800, easing = LinearEasing), RepeatMode.Restart), label = "x")
            val glow = MaterialTheme.colorScheme.primary.copy(alpha = 0.22f)
            Box(
                Modifier.fillMaxSize().drawBehind {
                    val w = size.width * 0.6f
                    val x = -w + (size.width + w) * t
                    drawRect(Brush.horizontalGradient(listOf(Color.Transparent, glow, Color.Transparent), startX = x, endX = x + w), topLeft = Offset(x, 0f), size = Size(w, size.height))
                },
            )
        }
        Icon(icon, null, tint = MaterialTheme.colorScheme.primary)
    }
}

@Composable
fun Thumbnail(url: String?, status: VideoStatus, modifier: Modifier = Modifier) {
    Box(modifier.background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
        val placeholder: @Composable () -> Unit = {
            Icon(
                when { status.isRunning -> Icons.Filled.HourglassTop; status == VideoStatus.Complete -> Icons.Filled.PlayArrow; else -> Icons.Filled.ErrorOutline },
                null, tint = Vmk.colors.textSecondary,
            )
        }
        // the placeholder sits behind the picture: it shows on the first load only, never again when the signed link is renewed
        placeholder()
        if (url != null) StableImage(url, ContentScale.Crop, Modifier.fillMaxSize())
    }
}

@Composable
fun StatusChip(status: VideoStatus) {
    val (label, color) = when (status) {
        is VideoStatus.Running -> stringResource(R.string.lib_status_making) to MaterialTheme.colorScheme.primary
        VideoStatus.Complete -> stringResource(R.string.lib_status_ready) to Vmk.colors.success
        VideoStatus.Failed -> stringResource(R.string.lib_status_failed) to Vmk.colors.danger
        VideoStatus.Rejected -> stringResource(R.string.lib_status_not_allowed) to Vmk.colors.warning
    }
    Text(label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = color,
        modifier = Modifier.clip(CircleShape).background(color.copy(alpha = 0.15f)).padding(horizontal = 8.dp, vertical = 3.dp))
}

/**
 * A picture cached by its link without the query string (memory and disk): the server signs the link again on every list call, and a new link
 * must not look like a new picture. The request is built once per picture; a failed load retries once with the newest link.
 */
@Composable
internal fun StableImage(url: String, scale: ContentScale, modifier: Modifier = Modifier, colorFilter: ColorFilter? = null) {
    val context = LocalContext.current
    val key = com.videomk.app.core.ImageKeys.stable(url)
    val latest by androidx.compose.runtime.rememberUpdatedState(url)
    var retried by remember(key) { mutableStateOf(false) }
    val request = remember(key, retried) {
        coil3.request.ImageRequest.Builder(context).data(latest).memoryCacheKey(key).diskCacheKey(key).build()
    }
    coil3.compose.AsyncImage(request, null, contentScale = scale, colorFilter = colorFilter, modifier = modifier, onError = { if (!retried) retried = true })
}
