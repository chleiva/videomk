package com.videomk.app.ui

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.text.format.DateUtils
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
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
import androidx.compose.ui.unit.dp
import coil3.compose.SubcomposeAsyncImage
import com.videomk.app.core.LibraryEntry
import com.videomk.app.core.PendingVideo
import com.videomk.app.core.ProgressEstimator
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private val ExampleBriefs = listOf(
    "How a bill becomes law in the United States, explained for teenagers.",
    "A visual tour of the most famous landmarks of Paris.",
    "Why the sky is blue, with a simple diagram.",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(app: AppViewModel, composer: ComposerViewModel, onOpenVideo: (String) -> Unit, onOpenWallet: () -> Unit, onOpenSettings: () -> Unit) {
    val state by app.state.collectAsState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val focusManager = androidx.compose.ui.platform.LocalFocusManager.current

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
    DisposableEffect(Unit) { onDispose { composer.dictation.stop() } }

    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            TopAppBar(
                title = { Text("Videos", fontWeight = FontWeight.Bold) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
                actions = {
                    state.wallet?.let { w ->
                        Row(
                            Modifier.heightIn(min = 48.dp).clip(RoundedCornerShape(24.dp)).clickable(onClickLabel = "Show your credits", onClick = onOpenWallet)
                                .padding(horizontal = 12.dp)
                                .semantics(mergeDescendants = true) { contentDescription = if (w.unlimited) "Unlimited credits" else "${w.balance} credits" }
                                .testTag("balanceChip"),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Icon(Icons.Filled.Bolt, null, tint = MaterialTheme.colorScheme.primary)
                            Text(if (w.unlimited) "∞" else "${w.balance}", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary)
                        }
                    }
                    IconButton(onClick = onOpenSettings, modifier = Modifier.size(48.dp).testTag("settingsButton")) {
                        Icon(Icons.Filled.Settings, "Settings")
                    }
                },
            )
        },
        bottomBar = {
            ComposerBar(
                composer = composer, balance = state.wallet?.let { if (it.unlimited) null else it.balance },
                onSend = {
                    val out = composer.takeForSend()
                    app.submit(out.brief, composer.options, out.photos, out.meta)
                    focusManager.clearFocus()   // the keyboard goes away: the new row is what you look at now
                },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            val entries = state.entries
            when {
                entries.isEmpty() && (state.loadState is LoadState.Loading || state.loadState is LoadState.Idle) -> FullScreenSpinner()
                entries.isEmpty() && state.loadState is LoadState.Failed ->
                    MessageState("Couldn't load your videos", (state.loadState as LoadState.Failed).message, "Try again", { scope.launch { app.refresh() } })
                entries.isEmpty() -> EmptyState(onExample = { composer.text = it; composer.requestFocus() })
                else -> {
                    var refreshing by remember { mutableStateOf(false) }
                    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refresh(); refreshing = false } }) {
                        LazyColumn(Modifier.fillMaxSize().testTag("videoList"), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            if (state.offline) item(key = "offline") { OfflineBanner(onRetry = { scope.launch { app.refresh() } }) }
                            items(entries, key = { it.id }) { entry ->
                                when (entry) {
                                    is LibraryEntry.Pending -> PendingRow(entry.pending, onRetry = { app.retry(entry.pending.id) }, onDismiss = { app.dismissPending(entry.pending.id) })
                                    is LibraryEntry.Video ->
                                        if (entry.video.status.isRunning) RunningRow(entry.video, state) { onOpenVideo(entry.video.id) }
                                        else VideoRow(entry.video) { onOpenVideo(entry.video.id) }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OfflineBanner(onRetry: () -> Unit) {
    Surface(shape = RoundedCornerShape(Vmk.radius), color = Vmk.colors.surfaceRaised, modifier = Modifier.fillMaxWidth().testTag("offlineBanner")) {
        Row(Modifier.padding(start = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Filled.CloudOff, null, tint = Vmk.colors.warning)
            Text("You're offline. Showing what was loaded last.", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            TextButton(onClick = onRetry, modifier = Modifier.heightIn(min = 48.dp)) { Text("Retry") }
        }
    }
}

@Composable
private fun EmptyState(onExample: (String) -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(24.dp).verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(20.dp), horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.AutoAwesome, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(52.dp))
        Text("Make your first video", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
        Text(
            "Type or tap the microphone and say what you want. It appears here while it's made, and you can ask for more.",
            textAlign = TextAlign.Center, color = Vmk.colors.textSecondary,
        )
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (example in ExampleBriefs) {
                Surface(
                    onClick = { onExample(example) }, shape = RoundedCornerShape(Vmk.radius), color = Vmk.colors.surface,
                    modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                ) { Text(example, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, modifier = Modifier.padding(14.dp)) }
            }
        }
    }
}

// rows

private val ThumbWidth = 112.dp
private val ThumbHeight = 63.dp

@Composable
private fun RowCard(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable () -> Unit) {
    val m = modifier.fillMaxWidth()
    if (onClick != null) Surface(onClick = onClick, shape = RoundedCornerShape(Vmk.radius), color = Vmk.colors.surface, modifier = m) { Box(Modifier.padding(12.dp)) { content() } }
    else Surface(shape = RoundedCornerShape(Vmk.radius), color = Vmk.colors.surface, modifier = m) { Box(Modifier.padding(12.dp)) { content() } }
}

@Composable
private fun VideoRow(video: VideoItem, onClick: () -> Unit) {
    val now = remember { System.currentTimeMillis() }
    RowCard(Modifier.semantics(mergeDescendants = true) {}.testTag("videoRow"), onClick) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Thumbnail(video.previewGifUrl, video.status, Modifier.size(ThumbWidth, ThumbHeight).clip(RoundedCornerShape(10.dp)))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(video.displayTitle, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    StatusChip(video.status)
                    if (video.status == VideoStatus.Complete) video.durationSeconds?.let { Text(duration(it), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary) }
                }
                video.createdAt?.let {
                    Text(DateUtils.getRelativeTimeSpanString(it.toEpochMilli(), now, DateUtils.MINUTE_IN_MILLIS, DateUtils.FORMAT_ABBREV_RELATIVE).toString(),
                        style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                }
                if (video.status == VideoStatus.Rejected) video.rejectReason?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

fun duration(s: Double): String = "%d:%02d".format(s.toInt() / 60, s.toInt() % 60)
fun elapsed(s: Long): String { val t = maxOf(0L, s); return "%d:%02d".format(t / 60, t % 60) }

/** A video being made: live stage, an honest estimate bar and elapsed time, in the list next to finished videos. */
@Composable
private fun RunningRow(video: VideoItem, state: AppState, onClick: () -> Unit) {
    val stage = (video.status as? VideoStatus.Running)?.stage ?: VideoStatus.Stage.Starting
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while (true) { delay(1000); now = System.currentTimeMillis() } }
    val since = state.stageSince[video.id]?.sinceMillis
    val inStage = since?.let { (now - it) / 1000.0 } ?: 0.0
    val fraction = ProgressEstimator.fraction(stage, inStage, state.minutes[video.id] ?: com.videomk.app.core.CreateOptions.DEFAULT_MINUTES).toFloat()
    val title = state.briefs[video.id] ?: video.title?.takeIf { it.isNotEmpty() } ?: "Making your video"
    RowCard(
        Modifier.semantics(mergeDescendants = true) {
            contentDescription = "Making video: $title"
            stateDescription = "${stage.title}, about ${(fraction * 100).toInt()} percent"
        }.testTag("runningRow"),
        onClick,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            ShimmerThumb(Icons.Filled.AutoAwesome, animate = true, Modifier.size(ThumbWidth, ThumbHeight).clip(RoundedCornerShape(10.dp)))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(title, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                LinearProgressIndicator(progress = { fraction }, modifier = Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.primary, trackColor = Vmk.colors.surfaceRaised)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stage.shortTitle, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, maxLines = 1, modifier = Modifier.weight(1f))
                    video.createdAt?.let { Text(elapsed((now - it.toEpochMilli()) / 1000), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary) }
                }
            }
        }
    }
}

/** The request is on its way (or failed before the server answered). Same shape as a running row so the list doesn't jump. */
@Composable
private fun PendingRow(pending: PendingVideo, onRetry: () -> Unit, onDismiss: () -> Unit) {
    val failed = (pending.state as? PendingVideo.State.Failed)?.message
    RowCard(Modifier.testTag(if (failed == null) "pendingRow" else "failedRow")) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
            ShimmerThumb(
                if (failed != null) Icons.Filled.Warning else if (pending.photoCount > 0) Icons.Filled.PhotoLibrary else Icons.AutoMirrored.Filled.Send,
                animate = failed == null, Modifier.size(ThumbWidth, ThumbHeight).clip(RoundedCornerShape(10.dp)),
            )
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(pending.brief, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                val st = pending.state
                when {
                    failed != null -> {
                        Text(failed, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger, maxLines = 3, overflow = TextOverflow.Ellipsis)
                        Row {
                            TextButton(onClick = onRetry, modifier = Modifier.heightIn(min = 48.dp).testTag("retryButton")) { Text("Try again", fontWeight = FontWeight.SemiBold) }
                            TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp).testTag("removeButton")) { Text("Remove", color = Vmk.colors.danger) }
                        }
                    }
                    st is PendingVideo.State.Uploading -> {
                        LinearProgressIndicator(progress = { st.done.toFloat() / maxOf(st.total, 1) }, modifier = Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.primary, trackColor = Vmk.colors.surfaceRaised)
                        Text("Uploading ${minOf(st.done + 1, st.total)} of ${st.total}", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                    }
                    else -> {
                        LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = MaterialTheme.colorScheme.primary, trackColor = Vmk.colors.surfaceRaised)
                        Text("Sending your request…", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                    }
                }
            }
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
        if (url != null) {
            SubcomposeAsyncImage(model = url, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize(), loading = { Box(Modifier.fillMaxSize(), Alignment.Center) { placeholder() } }, error = { Box(Modifier.fillMaxSize(), Alignment.Center) { placeholder() } })
        } else placeholder()
    }
}

@Composable
fun StatusChip(status: VideoStatus) {
    val (label, color) = when (status) {
        is VideoStatus.Running -> "Making" to MaterialTheme.colorScheme.primary
        VideoStatus.Complete -> "Ready" to Vmk.colors.success
        VideoStatus.Failed -> "Failed" to Vmk.colors.danger
        VideoStatus.Rejected -> "Not allowed" to Vmk.colors.warning
    }
    Text(label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = color,
        modifier = Modifier.clip(CircleShape).background(color.copy(alpha = 0.15f)).padding(horizontal = 8.dp, vertical = 3.dp))
}
