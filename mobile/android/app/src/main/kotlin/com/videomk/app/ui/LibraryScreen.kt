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
    // the button's height (58 dp, growing with the font) plus its 16 dp margin and some air: the last card can always scroll clear of it
    val fabClearance = (58 * androidx.compose.ui.platform.LocalDensity.current.fontScale.coerceIn(1f, 2f)).dp + 40.dp
    // the label collapses by distance from the top only, with a gap (see FabCollapse); it never changes the list's layout or padding
    var fabExpanded by remember { mutableStateOf(true) }
    LaunchedEffect(listState) {
        val machine = com.videomk.app.core.FabCollapse()
        androidx.compose.runtime.snapshotFlow { if (listState.firstVisibleItemIndex > 0) Int.MAX_VALUE else listState.firstVisibleItemScrollOffset }.collect { fabExpanded = machine.update(it) }
    }
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
        floatingActionButton = { if (state.entries.isNotEmpty() && !com.videomk.app.DebugHooks.emptyHome(context)) NewVideoFab(expanded = fabExpanded) { newVideo(null) } },
        bottomBar = {
            Column {
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
                entries.isEmpty() -> EmptyState(onExample = { e -> newVideo(e) }, onNew = { newVideo(null) })
                else -> {
                    var refreshing by remember { mutableStateOf(false) }
                    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refresh(); refreshing = false } }) {
                        LazyColumn(
                            Modifier.fillMaxSize().testTag("videoList"), state = listState, contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = fabClearance),
                            verticalArrangement = Arrangement.spacedBy(14.dp),
                        ) {
                            item(key = "title") { Text(stringResource(R.string.lib_title), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, letterSpacing = (-0.9).sp, color = Vmk.colors.text, modifier = Modifier.padding(bottom = 2.dp).semantics { heading() }) }
                            if (state.offline) item(key = "offline") { OfflineBanner(onRetry = { scope.launch { app.refresh() } }) }
                            items(entries, key = { it.id }, contentType = { if (it is LibraryEntry.Pending) "pending" else (it as LibraryEntry.Video).video.status.let { s -> if (s.isRunning) "making" else if (s == VideoStatus.Complete) "ready" else "failed" } }) { entry ->
                                when (entry) {
                                    is LibraryEntry.Pending -> PendingCard(entry.pending, onRetry = { app.retry(entry.pending.id) }, onDismiss = { app.dismissPending(entry.pending.id) })
                                    is LibraryEntry.Video -> when {
                                        entry.video.status.isRunning -> { val v = entry.video; MakingCard(v, state) { onOpenVideo(v.id) } }
                                        entry.video.status == VideoStatus.Complete -> { val v = entry.video; ReadyCard(v, remember(v.id, onOpenVideo) { { onOpenVideo(v.id) } }) }
                                        else -> FailedCard(
                                            title = state.briefs[entry.video.id] ?: entry.video.displayTitle, rejected = entry.video.status == VideoStatus.Rejected, reason = entry.video.rejectReason,
                                            thumb = entry.video.previewGifUrl, tag = "videoRow",
                                            onRetry = state.briefs[entry.video.id]?.let { brief -> { app.submit(brief, CreateOptions(state.minutes[entry.video.id] ?: CreateOptions.DEFAULT_MINUTES)) } },
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

/** The one entry to Create: a labelled capsule that shrinks to a round button while the list scrolls and grows back at the top. */
@Composable
private fun NewVideoFab(expanded: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.heightIn(min = 58.dp).clip(CircleShape).background(Vmk.gradientNow).clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_new_video), onClick = onClick)
            .padding(horizontal = if (expanded) 22.dp else 17.dp).animateContentSize().semantics { contentDescription = Txt.s(R.string.lib_new_video) }.testTag("newVideoFab"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Icon(Icons.Filled.Add, null, tint = Color.White, modifier = Modifier.size(24.dp))
        if (expanded) Text(stringResource(R.string.lib_new_video), style = MaterialTheme.typography.titleMedium.copy(fontSize = 17.sp), fontWeight = FontWeight.Bold, color = Color.White, maxLines = 1)
    }
}

@Composable
private fun MainTopBar(wallet: com.videomk.app.core.WalletInfo?, onOpenWallet: () -> Unit, onOpenSettings: () -> Unit) {
    Row(Modifier.fillMaxWidth().statusBarsPadding().heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            LogoMark()
            Text("videomk", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text)
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

/** Two skeleton cards at the final height while the list loads. */
@Composable
private fun SkeletonFeed() {
    val still = reduceMotion(LocalContext.current)
    val loadingDesc = stringResource(R.string.lib_loading_desc)
    val a = if (still) 0.7f else rememberInfiniteTransition(label = "sk").animateFloat(0.45f, 0.9f, infiniteRepeatable(tween(1000), RepeatMode.Reverse), label = "a").value
    Column(Modifier.fillMaxSize().padding(16.dp).semantics { contentDescription = loadingDesc }, verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(stringResource(R.string.lib_title), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
        repeat(2) { Box(Modifier.fillMaxWidth().height(CardHeight).alpha(a).clip(RoundedCornerShape(22.dp)).background(Vmk.colors.surfaceRaised)) }
    }
}

/** First launch: one promise, three worked examples. Tapping one fills the composer (and length); none of them sends. */
@Composable
private fun EmptyState(onExample: (Example) -> Unit, onNew: () -> Unit) {
    val newVideoDesc = stringResource(R.string.lib_new_video)
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 16.dp).testTag("emptyState"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.padding(top = 12.dp).height(96.dp).fillMaxWidth().clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
            Frame(-7f, (-34).dp, listOf(Color(0xFFF2B27A), Color(0xFF8E4B63)))
            Frame(7f, 34.dp, listOf(Color(0xFF2A2A66), Color(0xFF6C4BC1)))
            Frame(0f, 0.dp, listOf(Color(0xFFFFC27A), Color(0xFFB9556F)), front = true)
        }
        Text(stringResource(R.string.lib_empty_title), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, letterSpacing = (-0.8).sp, textAlign = TextAlign.Center, color = Vmk.colors.text, modifier = Modifier.padding(top = 8.dp).semantics { heading() })
        Text(stringResource(R.string.lib_empty_body), style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 8.dp, bottom = 16.dp))
        Box(
            Modifier.fillMaxWidth().padding(bottom = 18.dp).heightIn(min = 58.dp).clip(CircleShape).background(Vmk.gradientNow)
                .clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_new_video), onClick = onNew).semantics { contentDescription = newVideoDesc }.testTag("newVideoButton"),
            contentAlignment = Alignment.Center,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(Icons.Filled.Add, null, tint = Color.White); Text(stringResource(R.string.lib_new_video), style = MaterialTheme.typography.titleMedium.copy(fontSize = 17.sp), fontWeight = FontWeight.Bold, color = Color.White)
            }
        }
        Overline(stringResource(R.string.lib_try_one), Modifier.fillMaxWidth().padding(bottom = 8.dp))
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (e in Examples) {
                val shape = RoundedCornerShape(18.dp)
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
                        .clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_use_idea)) { onExample(e) }.padding(horizontal = 12.dp, vertical = 8.dp).testTag("exampleCard"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(e.icon, null, tint = Vmk.colors.primary, modifier = Modifier.size(22.dp)) }
                    Text(stringResource(e.text), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, modifier = Modifier.weight(1f), maxLines = 3)
                    Text(stringResource(e.tag), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, maxLines = 1, modifier = Modifier.clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 10.dp, vertical = 5.dp))
                }
            }
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

// cards

private val CardHeight = 190.dp
private val TallCardMax = 420.dp

@Composable
private fun CardFrame(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, height: Dp = CardHeight, content: @Composable androidx.compose.foundation.layout.BoxScope.() -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    val fontScale = androidx.compose.ui.platform.LocalDensity.current.fontScale
    val h = if (fontScale > 1f) height * (1f + (fontScale - 1f) * 0.7f) else height   // larger text (and longer Spanish) needs a taller card, never clipped text
    Box(
        modifier.fillMaxWidth().height(h).vmkShadow(2, shape, Vmk.colors.dark).clip(shape)
            .then(if (Vmk.colors.dark) Modifier.border(1.dp, Color.White.copy(alpha = 0.05f), shape) else Modifier)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier),
    ) { content() }
}

private val Scrim = Brush.verticalGradient(0f to Color.Transparent, 0.46f to Color.Transparent, 1f to Color(0xC7080A1C))

@Composable
private fun ReadyCard(video: VideoItem, onClick: () -> Unit) {
    val now = remember { System.currentTimeMillis() }
    val meta = video.createdAt?.let { RelativeTime.text(it.toEpochMilli(), now) }
    val readyDesc = stringResource(R.string.lib_ready_desc, video.displayTitle) + (meta?.let { " $it." } ?: "")
    // a tall video (9:16, 4:5) gets a taller card at its own shape (capped), so the thumbnail is not cropped to a landscape strip
    androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxWidth()) {
    val h = if (video.isTall) minOf(maxWidth / video.frameRatio, TallCardMax).coerceAtLeast(CardHeight) else CardHeight
    CardFrame(Modifier.semantics(mergeDescendants = true) { contentDescription = readyDesc }.testTag("videoRow"), onClick, h) {
        Thumbnail(video.previewGifUrl, video.status, Modifier.fillMaxSize().background(Brush.linearGradient(listOf(Color(0xFF3A3F7A), Color(0xFF7A5BC4)))))
        Box(Modifier.fillMaxSize().background(Scrim))
        GlassChip(stringResource(R.string.lib_status_ready), Modifier.align(Alignment.TopStart).padding(14.dp), dot = Color(0xFF4ADE80))
        Box(Modifier.align(Alignment.Center).size(52.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.35f)), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.PlayArrow, null, tint = Color.White, modifier = Modifier.size(32.dp))
        }
        Column(Modifier.align(Alignment.BottomStart).padding(start = 16.dp, end = 76.dp, bottom = 14.dp)) {
            Text(video.displayTitle, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 2, overflow = TextOverflow.Ellipsis)
            meta?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.85f)) }
        }
        video.durationSeconds?.let { Text(duration(it), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = Color.White, modifier = Modifier.align(Alignment.BottomEnd).padding(14.dp).clip(RoundedCornerShape(8.dp)).background(Color.Black.copy(alpha = 0.45f)).padding(horizontal = 8.dp, vertical = 3.dp)) }
    }
    }
}

fun duration(s: Double): String = "%d:%02d".format(s.toInt() / 60, s.toInt() % 60)
fun elapsed(s: Long): String { val t = maxOf(0L, s); return "%d:%02d".format(t / 60, t % 60) }

/** A video being made: named steps and honest words, no percent and no spinner. */
@Composable
private fun MakingCard(video: VideoItem, state: AppState, onClick: () -> Unit) {
    val stage = (video.status as? VideoStatus.Running)?.stage ?: VideoStatus.Stage.Starting
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(1000); now = System.currentTimeMillis() } }
    val since = state.stageSince[video.id]?.sinceMillis
    val inStage = since?.let { (now - it) / 1000.0 } ?: 0.0
    val minutes = state.minutes[video.id] ?: CreateOptions.DEFAULT_MINUTES
    val fraction = ProgressEstimator.fraction(stage, inStage, minutes)
    val title = state.briefs[video.id] ?: video.title?.takeIf { it.isNotEmpty() } ?: stringResource(R.string.lib_making_title)
    val line = stringResource(R.string.lib_making_line, MakingSteps.sentence(stage), ProgressEstimator.leftText(stage, inStage, minutes))
    val makingDesc = stringResource(R.string.lib_making_desc, title, line)
    MakingBody(title, line, fraction, Modifier.semantics(mergeDescendants = true) {
        contentDescription = makingDesc
    }.testTag("runningRow"), onClick)
}

@Composable
private fun MakingBody(title: String, line: String, fraction: Double, modifier: Modifier, onClick: (() -> Unit)?) {
    CardFrame(modifier, onClick) {
        Box(Modifier.fillMaxSize().background(Vmk.makingGradient))
        Shimmer(Modifier.fillMaxSize())
        Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            GlassChip(stringResource(R.string.lib_status_making), dot = Color(0xFFC4C6FF))
            Spacer(Modifier.height(4.dp))
            Text(title, style = MaterialTheme.typography.titleMedium, fontSize = 19.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(line, style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = 0.8f), maxLines = 2, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.weight(1f))
            Steps(fraction)
        }
    }
}

@Composable
private fun Steps(target: Double) {
    // eases to each new estimate over the poll interval instead of jumping
    val fraction by androidx.compose.animation.core.animateFloatAsState(target.toFloat(), androidx.compose.animation.core.tween(3500, easing = LinearEasing), label = "progress")
    val fills = MakingSteps.fills(fraction.toDouble())
    val current = MakingSteps.current(fraction.toDouble())
    Column(Modifier.fillMaxWidth().clearAndSetSemantics { }, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            fills.forEach { f ->
                Box(Modifier.weight(1f).height(5.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.22f))) {
                    Box(Modifier.fillMaxWidth(f).fillMaxHeight().background(Color(0xFFC4C6FF), CircleShape))
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            MakingSteps.names.forEachIndexed { i, n ->
                Text(n, Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, fontWeight = if (i == current) FontWeight.Bold else FontWeight.Normal,
                    color = if (i == current) Color.White else Color.White.copy(alpha = 0.7f), maxLines = 1, textAlign = when (i) { 0 -> TextAlign.Start; 3 -> TextAlign.End; else -> TextAlign.Center })
            }
        }
    }
}

/** A slow diagonal shimmer (a static lighter wash when animations are off). */
@Composable
private fun Shimmer(modifier: Modifier) {
    val still = reduceMotion(LocalContext.current)
    if (still) { Box(modifier.background(Color.White.copy(alpha = 0.05f))); return }
    val t by rememberInfiniteTransition(label = "shimmer").animateFloat(0f, 1f, infiniteRepeatable(tween(2400, easing = LinearEasing), RepeatMode.Restart), label = "x")
    Box(
        modifier.drawBehind {
            val w = size.width * 0.5f
            val x = -w + (size.width + w) * t
            drawRect(Brush.linearGradient(listOf(Color.Transparent, Color.White.copy(alpha = 0.14f), Color.Transparent), start = Offset(x, 0f), end = Offset(x + w, size.height)))
        },
    )
}

/** "Didn't finish": the picture goes grey, and the card says what happens to credits and how to try again. */
@Composable
private fun FailedCard(title: String, rejected: Boolean, reason: String?, thumb: String?, tag: String, onRetry: (() -> Unit)?, onDismiss: (() -> Unit)?, message: String? = null) {
    val grey = remember { ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(0f) }) }
    val statusLabel = stringResource(if (rejected) R.string.lib_status_not_allowed else R.string.lib_status_didnt_finish)
    val failedDesc = stringResource(R.string.lib_failed_desc, title, statusLabel)
    CardFrame(Modifier.semantics { contentDescription = failedDesc }.testTag(tag)) {
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color(0xFF5A5252), Color(0xFF2B2425)))))
        if (thumb != null) StableImage(thumb, ContentScale.Crop, Modifier.fillMaxSize().alpha(0.55f), grey)
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0f to Color(0x33200808), 1f to Color(0xE6180A0C))))
        GlassChip(statusLabel, Modifier.align(Alignment.TopStart).padding(14.dp), container = (if (rejected) Vmk.colors.warning else Color(0xFFB91C1C)).copy(alpha = 0.85f),
            leading = { Icon(Icons.Filled.Warning, null, tint = Color.White, modifier = Modifier.size(14.dp)) })
        Column(Modifier.align(Alignment.BottomStart).padding(start = 16.dp, end = 16.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val detail = message ?: reason
            Text(title, style = MaterialTheme.typography.titleMedium, fontSize = 19.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = if (detail != null) 1 else 2, overflow = TextOverflow.Ellipsis)
            detail?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.9f), maxLines = 2, overflow = TextOverflow.Ellipsis) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (onRetry != null) Row(
                    Modifier.heightIn(min = 44.dp).clip(CircleShape).background(Color.White).clickable(role = Role.Button, onClick = onRetry).padding(horizontal = 16.dp).testTag("retryButton"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) { Icon(Icons.Filled.Refresh, null, tint = Color(0xFF11142B), modifier = Modifier.size(18.dp)); Text(stringResource(R.string.common_try_again), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Color(0xFF11142B)) }
                if (!rejected) Text(stringResource(R.string.lib_no_credits_used), style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.85f), modifier = Modifier.weight(1f))
                if (onDismiss != null) TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 44.dp).testTag("removeButton")) { Text(stringResource(R.string.common_remove), color = Color.White) }
            }
        }
    }
}

/** The request is on its way (or failed before the server answered): the same card shape as a running one, so the list never jumps. */
@Composable
private fun PendingCard(pending: PendingVideo, onRetry: () -> Unit, onDismiss: () -> Unit) {
    val failed = (pending.state as? PendingVideo.State.Failed)?.message
    if (failed != null) { FailedCard(pending.brief, false, null, null, "failedRow", onRetry, onDismiss, message = failed); return }
    val st = pending.state
    val line = when (st) {
        is PendingVideo.State.Uploading -> stringResource(R.string.lib_pending_uploading, minOf(st.done + 1, st.total), st.total)
        else -> stringResource(R.string.lib_pending_sending)
    }
    MakingBody(pending.brief, line, if (st is PendingVideo.State.Uploading) 0.2 * st.done / maxOf(st.total, 1) else 0.0, Modifier.semantics(mergeDescendants = true) { contentDescription = "${pending.brief}. $line" }.testTag("pendingRow"), null)
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
