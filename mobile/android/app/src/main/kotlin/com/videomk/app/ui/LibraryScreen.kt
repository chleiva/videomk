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
import androidx.compose.ui.unit.dp
import coil3.compose.SubcomposeAsyncImage
import com.videomk.app.core.LibraryEntry
import com.videomk.app.core.PendingVideo
import com.videomk.app.core.ProgressEstimator
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private class Example(val text: String, val tag: String, val minutes: Double?, val photos: Boolean, val icon: ImageVector)

private val Examples = listOf(
    Example("A calm one-minute story about a lighthouse keeper", "1 min", 1.0, false, Icons.Filled.Movie),
    Example("How bees make honey, explained for kids", "3 min", 3.0, false, Icons.Filled.AutoAwesome),
    Example("My holiday in Thailand, told from my photos", "Your photos", null, true, Icons.Filled.Image),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(app: AppViewModel, composer: ComposerViewModel, onOpenVideo: (String) -> Unit, onOpenWallet: () -> Unit, onOpenSettings: () -> Unit, onOpenMedia: () -> Unit = {}) {
    val state by app.state.collectAsState()
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val focusManager = androidx.compose.ui.platform.LocalFocusManager.current
    val container = LocalContainerOrNull.current

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
        contentWindowInsets = WindowInsets(0),
        topBar = { MainTopBar(state.wallet, onOpenWallet, onOpenSettings) },
        bottomBar = {
            Column {
                val progress = container?.mediaUploads?.queue?.progress?.collectAsState()?.value
                val imeVisible = WindowInsets.ime.getBottom(androidx.compose.ui.platform.LocalDensity.current) > 0
                if (progress != null && progress.active && !imeVisible) UploadPill(progress, onOpenMedia)
                ComposerBar(
                    composer = composer, balance = com.videomk.app.DebugHooks.balanceOverride(context) ?: state.wallet?.let { if (it.unlimited) null else it.balance },
                    onSend = {
                        val out = composer.takeForSend()
                        app.submit(out.brief, composer.options, out.photos, out.meta, out.libraryIds)
                        focusManager.clearFocus()   // the keyboard goes away: the new card is what you look at now
                    },
                    onAddCredits = onOpenWallet,
                )
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            val entries = state.entries
            when {
                entries.isEmpty() && (state.loadState is LoadState.Loading || state.loadState is LoadState.Idle) -> SkeletonFeed()
                entries.isEmpty() && state.loadState is LoadState.Failed ->
                    MessageState("Couldn't load your videos", (state.loadState as LoadState.Failed).message, "Try again", { scope.launch { app.refresh() } })
                entries.isEmpty() -> EmptyState(onExample = { e ->
                    composer.useExample(e.text, e.minutes)
                    if (e.photos) composer.openAddPhotos(if (container?.mediaApi != null) 1 else 0)
                })
                else -> {
                    var refreshing by remember { mutableStateOf(false) }
                    PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.refresh(); refreshing = false } }) {
                        LazyColumn(
                            Modifier.fillMaxSize().testTag("videoList"), contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 16.dp),
                            verticalArrangement = Arrangement.spacedBy(14.dp),
                        ) {
                            item(key = "title") { Text("Your videos", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, letterSpacing = (-0.9).sp, color = Vmk.colors.text, modifier = Modifier.padding(bottom = 2.dp).semantics { heading() }) }
                            if (state.offline) item(key = "offline") { OfflineBanner(onRetry = { scope.launch { app.refresh() } }) }
                            items(entries, key = { it.id }) { entry ->
                                when (entry) {
                                    is LibraryEntry.Pending -> PendingCard(entry.pending, onRetry = { app.retry(entry.pending.id) }, onDismiss = { app.dismissPending(entry.pending.id) })
                                    is LibraryEntry.Video -> when {
                                        entry.video.status.isRunning -> MakingCard(entry.video, state) { onOpenVideo(entry.video.id) }
                                        entry.video.status == VideoStatus.Complete -> ReadyCard(entry.video) { onOpenVideo(entry.video.id) }
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

@Composable
private fun MainTopBar(wallet: com.videomk.app.core.WalletInfo?, onOpenWallet: () -> Unit, onOpenSettings: () -> Unit) {
    Row(Modifier.fillMaxWidth().statusBarsPadding().heightIn(min = 52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Row(Modifier.weight(1f).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            LogoMark()
            Text("videomk", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text)
        }
        wallet?.let { w ->
            val shape = CircleShape
            Row(
                Modifier.heightIn(min = 44.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
                    .clickable(role = Role.Button, onClickLabel = "Show your credits", onClick = onOpenWallet).padding(horizontal = 14.dp)
                    .semantics(mergeDescendants = true) { contentDescription = if (w.unlimited) "Unlimited credits" else "${w.balance} credit${if (w.balance == 1) "" else "s"}" }
                    .testTag("balanceChip"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Icon(Icons.Filled.Bolt, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp))
                Text(if (w.unlimited) "∞" else "${w.balance}", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
            }
        }
        IconButton(onClick = onOpenSettings, modifier = Modifier.size(48.dp).testTag("settingsButton")) {
            Icon(Icons.Filled.Settings, "Settings", tint = Vmk.colors.textSecondary)
        }
    }
}

@Composable
private fun OfflineBanner(onRetry: () -> Unit) {
    Surface(shape = RoundedCornerShape(16.dp), color = Vmk.colors.warningContainer, modifier = Modifier.fillMaxWidth().testTag("offlineBanner")) {
        Row(Modifier.padding(start = 14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(Icons.Filled.CloudOff, null, tint = Vmk.colors.warning)
            Text("You're offline. Showing what was loaded last.", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            TextButton(onClick = onRetry, modifier = Modifier.heightIn(min = 48.dp)) { Text("Retry") }
        }
    }
}

/** Two skeleton cards at the final height while the list loads. */
@Composable
private fun SkeletonFeed() {
    val still = reduceMotion(LocalContext.current)
    val a = if (still) 0.7f else rememberInfiniteTransition(label = "sk").animateFloat(0.45f, 0.9f, infiniteRepeatable(tween(1000), RepeatMode.Reverse), label = "a").value
    Column(Modifier.fillMaxSize().padding(16.dp).semantics { contentDescription = "Loading your videos" }, verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Your videos", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
        repeat(2) { Box(Modifier.fillMaxWidth().height(CardHeight).alpha(a).clip(RoundedCornerShape(22.dp)).background(Vmk.colors.surfaceRaised)) }
    }
}

/** First launch: one promise, three worked examples. Tapping one fills the composer (and length); none of them sends. */
@Composable
private fun EmptyState(onExample: (Example) -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).padding(bottom = 16.dp).testTag("emptyState"),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(Modifier.padding(top = 12.dp).height(96.dp).fillMaxWidth().clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
            Frame(-7f, (-34).dp, listOf(Color(0xFFF2B27A), Color(0xFF8E4B63)))
            Frame(7f, 34.dp, listOf(Color(0xFF2A2A66), Color(0xFF6C4BC1)))
            Frame(0f, 0.dp, listOf(Color(0xFFFFC27A), Color(0xFFB9556F)), front = true)
        }
        Text("Describe it.\nWe'll make the video.", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, letterSpacing = (-0.8).sp, textAlign = TextAlign.Center, color = Vmk.colors.text, modifier = Modifier.padding(top = 8.dp).semantics { heading() })
        Text("Narrated and illustrated in minutes. Add your own photos if you like.", style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 8.dp, bottom = 16.dp))
        Overline("Try one", Modifier.fillMaxWidth().padding(bottom = 8.dp))
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (e in Examples) {
                val shape = RoundedCornerShape(18.dp)
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
                        .clickable(role = Role.Button, onClickLabel = "Use this idea") { onExample(e) }.padding(horizontal = 12.dp, vertical = 8.dp).testTag("exampleCard"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(e.icon, null, tint = Vmk.colors.primary, modifier = Modifier.size(22.dp)) }
                    Text(e.text, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, modifier = Modifier.weight(1f), maxLines = 3)
                    Text(e.tag, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, maxLines = 1, modifier = Modifier.clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = 10.dp, vertical = 5.dp))
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

@Composable
private fun CardFrame(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable androidx.compose.foundation.layout.BoxScope.() -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    Box(
        modifier.fillMaxWidth().height(CardHeight).vmkShadow(2, shape, Vmk.colors.dark).clip(shape)
            .then(if (Vmk.colors.dark) Modifier.border(1.dp, Color.White.copy(alpha = 0.05f), shape) else Modifier)
            .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier),
    ) { content() }
}

private val Scrim = Brush.verticalGradient(0f to Color.Transparent, 0.46f to Color.Transparent, 1f to Color(0xC7080A1C))

@Composable
private fun ReadyCard(video: VideoItem, onClick: () -> Unit) {
    val now = remember { System.currentTimeMillis() }
    val meta = video.createdAt?.let { DateUtils.getRelativeTimeSpanString(it.toEpochMilli(), now, DateUtils.MINUTE_IN_MILLIS, DateUtils.FORMAT_ABBREV_RELATIVE).toString() }
    CardFrame(Modifier.semantics(mergeDescendants = true) { contentDescription = "${video.displayTitle}. Ready.${meta?.let { " $it." } ?: ""}" }.testTag("videoRow"), onClick) {
        Thumbnail(video.previewGifUrl, video.status, Modifier.fillMaxSize().background(Brush.linearGradient(listOf(Color(0xFF3A3F7A), Color(0xFF7A5BC4)))))
        Box(Modifier.fillMaxSize().background(Scrim))
        GlassChip("Ready", Modifier.align(Alignment.TopStart).padding(14.dp), dot = Color(0xFF4ADE80))
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
    val title = state.briefs[video.id] ?: video.title?.takeIf { it.isNotEmpty() } ?: "Making your video"
    val line = MakingSteps.sentence(stage) + " " + ProgressEstimator.leftText(stage, inStage, minutes)
    MakingBody(title, line, fraction, Modifier.semantics(mergeDescendants = true) {
        contentDescription = "$title. Making. $line"
    }.testTag("runningRow"), onClick)
}

@Composable
private fun MakingBody(title: String, line: String, fraction: Double, modifier: Modifier, onClick: (() -> Unit)?) {
    CardFrame(modifier, onClick) {
        Box(Modifier.fillMaxSize().background(Vmk.makingGradient))
        Shimmer(Modifier.fillMaxSize())
        Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            GlassChip("Making", dot = Color(0xFFC4C6FF))
            Spacer(Modifier.height(4.dp))
            Text(title, style = MaterialTheme.typography.titleMedium, fontSize = 19.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text(line, style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = 0.8f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Spacer(Modifier.weight(1f))
            Steps(fraction)
        }
    }
}

@Composable
private fun Steps(fraction: Double) {
    val fills = MakingSteps.fills(fraction)
    val current = MakingSteps.current(fraction)
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
    CardFrame(Modifier.semantics { contentDescription = "$title. ${if (rejected) "Not allowed" else "Didn't finish"}." }.testTag(tag)) {
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color(0xFF5A5252), Color(0xFF2B2425)))))
        if (thumb != null) coil3.compose.AsyncImage(thumb, null, contentScale = ContentScale.Crop, colorFilter = grey, modifier = Modifier.fillMaxSize().alpha(0.55f))
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(0f to Color(0x33200808), 1f to Color(0xE6180A0C))))
        GlassChip(if (rejected) "Not allowed" else "Didn't finish", Modifier.align(Alignment.TopStart).padding(14.dp), container = (if (rejected) Vmk.colors.warning else Color(0xFFB91C1C)).copy(alpha = 0.85f),
            leading = { Icon(Icons.Filled.Warning, null, tint = Color.White, modifier = Modifier.size(14.dp)) })
        Column(Modifier.align(Alignment.BottomStart).padding(start = 16.dp, end = 16.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val detail = message ?: reason
            Text(title, style = MaterialTheme.typography.titleMedium, fontSize = 19.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = if (detail != null) 1 else 2, overflow = TextOverflow.Ellipsis)
            detail?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.9f), maxLines = 2, overflow = TextOverflow.Ellipsis) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (onRetry != null) Row(
                    Modifier.heightIn(min = 44.dp).clip(CircleShape).background(Color.White).clickable(role = Role.Button, onClick = onRetry).padding(horizontal = 16.dp).testTag("retryButton"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) { Icon(Icons.Filled.Refresh, null, tint = Color(0xFF11142B), modifier = Modifier.size(18.dp)); Text("Try again", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Color(0xFF11142B)) }
                if (!rejected) Text("No credits were used.", style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.85f), modifier = Modifier.weight(1f))
                if (onDismiss != null) TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 44.dp).testTag("removeButton")) { Text("Remove", color = Color.White) }
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
        is PendingVideo.State.Uploading -> "Uploading photos ${minOf(st.done + 1, st.total)} of ${st.total}"
        else -> "Sending your request…"
    }
    MakingBody(pending.brief, line, if (st is PendingVideo.State.Uploading) 0.2 * st.done / maxOf(st.total, 1) else 0.0, Modifier.semantics(mergeDescendants = true) { contentDescription = "${pending.brief}. $line" }.testTag("pendingRow"), null)
}

/** The slim pill on the Videos tab while photos upload: opens Media. */
@Composable
private fun UploadPill(progress: com.videomk.app.core.QueueProgress, onClick: () -> Unit) {
    val text = "Uploading ${minOf(progress.finished + 1, progress.total)} of ${progress.total}"
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 12.dp).heightIn(min = 44.dp).clickable(role = Role.Button, onClickLabel = "Open My media", onClick = onClick),
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
