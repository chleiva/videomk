package com.videomk.app.ui

import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.statusBarsPadding
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
import androidx.compose.ui.zIndex
import androidx.compose.foundation.layout.aspectRatio
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

private class Example(@androidx.annotation.StringRes val text: Int, @androidx.annotation.StringRes val chip: Int, @androidx.annotation.StringRes val tag: Int, val minutes: Double?, val photos: Boolean)

private val Examples = listOf(
    Example(R.string.lib_example_lighthouse, R.string.lib_example_chip_lighthouse, R.string.lib_example_tag_1min, 1.0, false),
    Example(R.string.lib_example_bees, R.string.lib_example_chip_bees, R.string.lib_example_tag_3min, 3.0, false),
    Example(R.string.lib_example_holiday, R.string.lib_example_chip_holiday, R.string.lib_example_tag_photos, null, true),
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

    state.retryNotice?.let { notice ->
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { app.dismissRetryNotice() },
            confirmButton = { TextButton(onClick = { app.dismissRetryNotice() }, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("retryNoticeOk")) { Text(stringResource(android.R.string.ok)) } },
            text = { Text(notice, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text) },
            containerColor = Vmk.colors.surface,
        )
    }
    Scaffold(
        containerColor = Vmk.colors.background,
        contentWindowInsets = WindowInsets(0),
        topBar = { MainTopBar(state.wallet, person, onOpenWallet, onOpenSettings) },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            // the slim pill while photos upload or are being organized floats above the tab bar (never two pills: uploads first)
            Column(Modifier.align(Alignment.BottomCenter).padding(bottom = LocalBarSpace.current).zIndex(1f)) {
                val progress = container?.mediaUploads?.queue?.progress?.collectAsState()?.value
                val imeVisible = WindowInsets.ime.getBottom(androidx.compose.ui.platform.LocalDensity.current) > 0
                val org = container?.organize?.bar?.collectAsState()?.value
                if (progress != null && progress.active && !imeVisible) UploadPill(progress, onOpenMedia)
                else if (org != null && !imeVisible) OrganizePill(org, onOpenMedia)
            }
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
                    onChange = { newVideo(Example(R.string.lib_first_prompt, R.string.lib_example_chip_bees, R.string.lib_example_tag_1min, com.videomk.app.core.CreateDefaults.FIRST_TIME_MINUTES, false)) },
                )
                else -> {
                    var refreshing by remember { mutableStateOf(false) }
                    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refresh(); refreshing = false } }) {
                        val nowInstant = remember(entries) { java.time.Instant.now() }
                        val rows = remember(entries) { com.videomk.app.core.FeedLayout.rows(entries, nowInstant) }
                        val zone = remember { java.time.ZoneId.systemDefault() }
                        val barSpace = LocalBarSpace.current
                        @Composable fun day(v: VideoItem): String = dayLabel(DayGroups.bucket(v.createdAt, nowInstant, zone))
                        LazyColumn(
                            Modifier.fillMaxSize().testTag("videoList"), state = listState,
                            contentPadding = PaddingValues(start = Vmk.space.screen, end = Vmk.space.screen, top = Vmk.space.s, bottom = Vmk.space.xxl + barSpace),
                            verticalArrangement = Arrangement.spacedBy(Vmk.space.xl),
                        ) {
                            if (state.offline) item(key = "offline") { OfflineBanner(onRetry = { scope.launch { app.refresh() } }) }
                            items(rows, key = { it.key }, contentType = { it::class }) { row ->
                                when (row) {
                                    is com.videomk.app.core.FeedRow.Live -> when (val entry = row.entry) {
                                        is LibraryEntry.Pending -> PendingCard(entry.pending, onRetry = { app.retry(entry.pending.id) }, onDismiss = { app.dismissPending(entry.pending.id) })
                                        is LibraryEntry.Video -> MakingCard(rememberMakingSnapshot(entry.video, state), Modifier.animateItem().testTag("runningRow"), onClick = { onOpenVideo(entry.video.id) }, videoId = entry.video.id)
                                    }
                                    // the Making card settles into the poster: the same list item, cross-faded by the list's own item animation
                                    is com.videomk.app.core.FeedRow.Hero -> PosterCard(row.video, day(row.video), large = true, onClick = { onOpenVideo(row.video.id) }, modifier = Modifier.animateItem())
                                    is com.videomk.app.core.FeedRow.Pair -> {
                                        if (isLargeText()) Column(Modifier.animateItem(), verticalArrangement = Arrangement.spacedBy(Vmk.space.xl)) {
                                            PosterCard(row.left, day(row.left), large = false, onClick = { onOpenVideo(row.left.id) })
                                            row.right?.let { r -> PosterCard(r, day(r), large = false, onClick = { onOpenVideo(r.id) }) }
                                        } else Row(Modifier.animateItem(), horizontalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
                                            PosterCard(row.left, day(row.left), large = false, onClick = { onOpenVideo(row.left.id) }, modifier = Modifier.weight(1f))
                                            row.right?.let { r -> PosterCard(r, day(r), large = false, onClick = { onOpenVideo(r.id) }, modifier = Modifier.weight(1f)) } ?: Spacer(Modifier.weight(1f))
                                        }
                                    }
                                    is com.videomk.app.core.FeedRow.Problem -> {
                                        val v = row.video
                                        FailedRow(
                                            title = state.briefs[v.id] ?: v.displayTitle, rejected = v.status == VideoStatus.Rejected, detail = v.rejectReason,
                                            thumb = v.previewGifUrl, tag = "problemRow", modifier = Modifier.animateItem(),
                                            // "Try again" starts THIS video again on the server (all its photos and options): no new row. Not offered for a refused video, a used-up presentation or one out of retries.
                                            onRetry = if (v.status == VideoStatus.Failed && v.canRetry != false && v.id !in state.deckVideos && v.id !in state.retrying) { { app.tryAgain(v) } } else null,
                                            onDismiss = { app.removeFailed(v) },
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

/** A finished video on Videos: the poster (the newest one large, the others half width), its length on the picture, then the title and the day. One tap plays it. */
@Composable
private fun PosterCard(video: VideoItem, day: String, large: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(Vmk.radii.videoCard)
    val desc = stringResource(R.string.lib_ready_desc, video.displayTitle) + " " + day + "."
    Column(
        modifier.fillMaxWidth().clip(shape).clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_play), onClick = onClick)
            .semantics(mergeDescendants = true) { contentDescription = desc }.testTag("videoRow"),
        verticalArrangement = Arrangement.spacedBy(Vmk.space.s),
    ) {
        Box(Modifier.fillMaxWidth().aspectRatio(if (large) 16f / 9f else 4f / 3f).clip(shape).background(Vmk.makingGradient).clearAndSetSemantics { }) {
            if (video.previewGifUrl != null) StableImage(video.previewGifUrl!!, ContentScale.Crop, Modifier.fillMaxSize())
            else Icon(Sym.PlayArrow, null, tint = Color.White.copy(alpha = 0.9f), modifier = Modifier.align(Alignment.Center).size(if (large) 44.dp else 32.dp))
            if (video.aspect != null && video.aspect != "16:9") GlassChip(video.aspect!!, Modifier.align(Alignment.TopStart).padding(Vmk.space.s))
            video.durationSeconds?.let { GlassChip(duration(it), Modifier.align(Alignment.BottomEnd).padding(Vmk.space.s)) }
        }
        Column(Modifier.padding(horizontal = 2.dp).padding(bottom = 2.dp)) {
            Text(video.displayTitle, style = if (large) VmkType.makingTitle else MaterialTheme.typography.titleSmall, color = Vmk.colors.text, maxLines = if (isLargeText()) 3 else 2, overflow = TextOverflow.Ellipsis)
            Text(day, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        }
    }
}

/** Videos: the name of the place at the large-title size, the credits and the account on the right. Nothing else. */
@Composable
private fun MainTopBar(wallet: com.videomk.app.core.WalletInfo?, email: String?, onOpenWallet: () -> Unit, onOpenSettings: () -> Unit) {
    VmkTopBar(title = stringResource(R.string.lib_title), large = true) {
        wallet?.let { w ->
            val unlimitedDesc = stringResource(R.string.lib_unlimited_credits)
            val creditsDesc = pluralStringResource(R.plurals.lib_credits_desc, w.balance, w.balance)
            Box(Modifier.heightIn(min = Vmk.minTouch).clip(CircleShape).clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_show_credits), onClick = onOpenWallet)
                .semantics(mergeDescendants = true) { contentDescription = if (w.unlimited) unlimitedDesc else creditsDesc }.testTag("balanceChip"), contentAlignment = Alignment.Center) {
                Row(Modifier.heightIn(min = Vmk.iconButton).clip(CircleShape).background(Vmk.colors.surfaceRaised).padding(horizontal = Vmk.space.l), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Sym.Bolt, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
                    Text(if (w.unlimited) "∞" else "${w.balance}", style = MaterialTheme.typography.titleSmall, color = Vmk.colors.text)
                }
            }
        }
        val settings = stringResource(R.string.lib_settings)
        val initial = email?.trim()?.firstOrNull { it.isLetterOrDigit() }?.uppercase()
        Box(Modifier.size(Vmk.minTouch).clip(CircleShape).clickable(role = Role.Button, onClickLabel = settings, onClick = onOpenSettings).semantics { contentDescription = settings }.testTag("settingsButton"), contentAlignment = Alignment.Center) {
            Box(Modifier.size(Vmk.iconButton).clip(CircleShape).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
                if (initial != null) Text(initial, style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary, modifier = Modifier.clearAndSetSemantics { })
                else Icon(Sym.Person, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(22.dp))
            }
        }
    }
}

@Composable
private fun OfflineBanner(onRetry: () -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = Vmk.colors.warningContainer, modifier = Modifier.fillMaxWidth().testTag("offlineBanner")) {
        Row(Modifier.padding(start = 14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Sym.CloudOff, null, tint = Vmk.colors.warning)
            Text(stringResource(R.string.lib_offline_banner), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            TextButton(onClick = onRetry, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.lib_retry)) }
        }
    }
}

/** Skeletons in the final shapes (a large poster, its two lines, two half posters) while the list loads: nothing jumps when the videos arrive. */
@Composable
private fun SkeletonFeed() {
    val still = reduceMotion(LocalContext.current)
    val loadingDesc = stringResource(R.string.lib_loading_desc)
    val a = if (still) 0.7f else rememberInfiniteTransition(label = "sk").animateFloat(0.45f, 0.9f, infiniteRepeatable(tween(1000), RepeatMode.Reverse), label = "a").value
    val block = Vmk.colors.surfaceRaised
    val shape = RoundedCornerShape(Vmk.radii.videoCard)
    Column(Modifier.fillMaxSize().padding(horizontal = Vmk.space.screen).padding(top = Vmk.space.s).alpha(a).semantics { contentDescription = loadingDesc }.testTag("skeleton"), verticalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(shape).background(block))
        Box(Modifier.fillMaxWidth(0.6f).height(18.dp).clip(CircleShape).background(block))
        Box(Modifier.fillMaxWidth(0.25f).height(12.dp).clip(CircleShape).background(block))
        Row(Modifier.padding(top = Vmk.space.s), horizontalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
            repeat(2) { Box(Modifier.weight(1f).aspectRatio(4f / 3f).clip(shape).background(block)) }
        }
    }
}

/** First launch (docs/UX_2026_REDESIGN.md 4.3): the headline, a prompt field that opens Create with the keyboard up, and three example chips (they fill Create, none sends). */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun EmptyState(onExample: (Example) -> Unit, onFirst: () -> Unit, onChange: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(top = 24.dp, bottom = 16.dp).testTag("emptyState"), verticalArrangement = Arrangement.spacedBy(20.dp)) {
        Text(stringResource(R.string.lib_empty_title), style = MaterialTheme.typography.headlineLarge, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
        val shape = RoundedCornerShape(Vmk.radii.composer)
        val hint = stringResource(R.string.create_prompt_hint)
        Row(
            Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
                .clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_new_video), onClick = onChange).padding(horizontal = 20.dp, vertical = 12.dp).semantics(mergeDescendants = true) { contentDescription = hint }.testTag("newVideoButton"),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(hint, style = VmkType.prompt, color = Vmk.colors.textTertiary, modifier = Modifier.weight(1f))
            Icon(Sym.Add, null, tint = Vmk.colors.primary)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (e in Examples) {
                Row(
                    Modifier.heightIn(min = 48.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_use_idea)) { onExample(e) }.padding(horizontal = 14.dp, vertical = 8.dp).testTag("exampleCard"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Sparkle(size = 14.dp)
                    Text(stringResource(e.chip), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.text)
                }
            }
        }
    }
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
    val deck = (video.status as? VideoStatus.Running)?.deck
    return (if (deck != null) MakingSnapshot.ofDeck(title, deck, inStage, minutes) else MakingSnapshot.of(title, stage, inStage, minutes)).with(video.making)
}

/** The request is on its way (or failed before the server answered): the same card as a running one, so the list never jumps. */
@Composable
private fun PendingCard(pending: PendingVideo, onRetry: () -> Unit, onDismiss: () -> Unit) {
    val failed = (pending.state as? PendingVideo.State.Failed)?.message
    if (failed != null) { FailedRow(pending.shownTitle, false, failed, null, "failedRow", onRetry, onDismiss); return }
    val st = pending.state
    val line = when (st) {
        is PendingVideo.State.Uploading -> stringResource(R.string.lib_pending_uploading, minOf(st.done + 1, st.total), st.total)
        else -> stringResource(R.string.lib_pending_sending)
    }
    MakingCard(MakingSnapshot.pending(pending.shownTitle, line, if (st is PendingVideo.State.Uploading) 0.2 * st.done / maxOf(st.total, 1) else 0.0), Modifier.testTag("pendingRow"))
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
            Icon(Sym.CloudUpload, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
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
                when { status.isRunning -> Sym.HourglassTop; status == VideoStatus.Complete -> Sym.PlayArrow; else -> Sym.ErrorOutline },
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
internal fun StableImage(url: String, scale: ContentScale, modifier: Modifier = Modifier, colorFilter: ColorFilter? = null, key: String = com.videomk.app.core.ImageKeys.stable(url)) {
    val context = LocalContext.current
    val latest by androidx.compose.runtime.rememberUpdatedState(url)
    var retried by remember(key) { mutableStateOf(false) }
    val request = remember(key, retried) {
        coil3.request.ImageRequest.Builder(context).data(latest).memoryCacheKey(key).diskCacheKey(key).build()
    }
    coil3.compose.AsyncImage(request, null, contentScale = scale, colorFilter = colorFilter, modifier = modifier, onError = { if (!retried) retried = true })
}
