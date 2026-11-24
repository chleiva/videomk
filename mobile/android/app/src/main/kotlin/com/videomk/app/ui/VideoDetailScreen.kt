package com.videomk.app.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.PanTool
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material.icons.filled.Share
import androidx.compose.material.icons.automirrored.filled.TextSnippet
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VideoDetailScreen(app: AppViewModel, detail: VideoDetailViewModel, http: OkHttpClient, onBack: () -> Unit, onEdit: () -> Unit) {
    val state by app.state.collectAsState()
    val video = state.video(detail.videoId)
    val playback by detail.playback.collectAsState()
    val editRevision by app.editRevision.collectAsState()
    val initialRevision = rememberSaveable { editRevision }

    LaunchedEffect(Unit) { if (app.state.value.videos.none { it.id == detail.videoId }) app.refresh() }
    PollWhileRunning(app, state.hasRunningVideos)
    LaunchedEffect(video?.status) { if (video?.status == VideoStatus.Complete) detail.load() }
    LaunchedEffect(editRevision) { if (editRevision != initialRevision && video?.status == VideoStatus.Complete) { app.refresh(); detail.reload() } }
    LifecycleEventEffect(Lifecycle.Event.ON_STOP) { detail.pause() }

    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            TopAppBar(
                title = { Text(video?.displayTitle ?: "Video", maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack, modifier = Modifier.size(48.dp).testTag("backButton")) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
                actions = {
                    if (video != null && video.editable && video.status == VideoStatus.Complete) {
                        TextButton(onClick = { detail.pause(); onEdit() }, modifier = Modifier.heightIn(min = 48.dp).testTag("editButton")) { Text("Edit") }
                    }
                },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            if (video == null) { FullScreenSpinner(); return@Box }
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                when (val st = video.status) {
                    VideoStatus.Complete -> PlayerSection(video, detail, playback, http)
                    is VideoStatus.Running -> ProgressCard(st.stage)
                    VideoStatus.Failed -> MessageCard("Something went wrong", "We couldn't finish this video. You haven't been charged for it.", Icons.Filled.Warning, Vmk.colors.danger)
                    VideoStatus.Rejected -> MessageCard("This request can't be turned into a video", video.rejectReason ?: "Try describing something different.", Icons.Filled.PanTool, Vmk.colors.warning)
                }
            }
        }
    }
}

@Composable
private fun PlayerSection(video: VideoItem, detail: VideoDetailViewModel, playback: PlaybackState, http: OkHttpClient) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val fullScreen = rememberLauncherForActivityResult(FullScreenContract()) { r -> r?.let { detail.returnFromFullScreen(it.positionMs, it.playWhenReady) } }

    when (playback) {
        is PlaybackState.Ready -> InlinePlayer(detail.player, onFullScreen = { detail.enterFullScreen()?.let { fullScreen.launch(it) } })
        is PlaybackState.Error -> Column(
            Modifier.fillMaxWidth().background(Vmk.colors.surface, androidx.compose.foundation.shape.RoundedCornerShape(Vmk.radius)).padding(24.dp).testTag("playbackError"),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(playback.message, color = Vmk.colors.textSecondary)
            OutlinedButton(onClick = { detail.reload() }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Try again") }
        }
        else -> Box(Modifier.fillMaxWidth().androidAspect(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
    }

    Text(video.displayTitle, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text)

    val description = (playback as? PlaybackState.Ready)?.description
    if (description != null) {
        var open by rememberSaveable { mutableStateOf(false) }
        Column(Modifier.testTag("descriptionGroup")) {
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClickLabel = if (open) "Hide description" else "Show description") { open = !open },
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text("Description and photo credits", color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(1f), fontWeight = FontWeight.Medium)
                Icon(if (open) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null, tint = MaterialTheme.colorScheme.primary)
            }
            if (open) {
                androidx.compose.foundation.text.selection.SelectionContainer {
                    Text(linkified(description, MaterialTheme.colorScheme.primary), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 6.dp))
                }
            }
        }
    }

    var sharing by remember { mutableStateOf(false) }
    var shareError by remember { mutableStateOf<String?>(null) }
    var copied by remember { mutableStateOf(false) }
    var copiedDescription by remember { mutableStateOf(false) }
    val url = (playback as? PlaybackState.Ready)?.url

    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
        if (url != null) {
            OutlinedButton(
                onClick = {
                    if (sharing) return@OutlinedButton
                    sharing = true; shareError = null
                    scope.launch {
                        try { shareVideo(context, http, url, video.displayTitle) } catch (e: Exception) { shareError = "Couldn't prepare the video to share. Check your connection and try again." }
                        sharing = false
                    }
                },
                modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("shareButton"),
            ) {
                if (sharing) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Icon(Icons.Filled.Share, null, Modifier.size(18.dp))
                Text(if (sharing) "  Preparing…" else "  Share", maxLines = 1)
            }
        }
        OutlinedButton(
            onClick = { copyText(context, "videomk title", video.displayTitle); copied = true; scope.launch { delay(2000); copied = false } },
            modifier = Modifier.weight(1f).heightIn(min = 48.dp),
        ) {
            Icon(if (copied) Icons.Filled.Check else Icons.Filled.ContentCopy, null, Modifier.size(18.dp))
            Text(if (copied) "  Copied" else "  Copy title", maxLines = 1)
        }
    }
    shareError?.let { Text(it, color = Vmk.colors.danger, style = MaterialTheme.typography.bodySmall) }
    if (description != null) {
        OutlinedButton(
            onClick = { copyText(context, "videomk description", description); copiedDescription = true; scope.launch { delay(2000); copiedDescription = false } },
            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("copyDescription"),
        ) {
            Icon(if (copiedDescription) Icons.Filled.Check else Icons.AutoMirrored.Filled.TextSnippet, null, Modifier.size(18.dp))
            Text(if (copiedDescription) "  Copied" else "  Copy description with credits", maxLines = 1)
        }
    }
}

private fun Modifier.androidAspect(): Modifier = this.then(Modifier.heightIn(min = 200.dp))

private fun copyText(context: Context, label: String, text: String) {
    runCatching { (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text)) }
}

/** Downloads the MP4 only when the user actually shares it, then hands the file to the share sheet. */
private suspend fun shareVideo(context: Context, http: OkHttpClient, url: String, name: String) {
    val file = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, "shared").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
        val safe = name.replace(Regex("[^\\p{L}\\p{N} _.-]"), "-").trim().ifEmpty { "video" }.take(80)
        val out = File(dir, "$safe.mp4")
        http.newCall(Request.Builder().url(url).build()).execute().use { r ->
            if (!r.isSuccessful) throw java.io.IOException("download failed")
            r.body.byteStream().use { input -> out.outputStream().use { input.copyTo(it) } }
        }
        out
    }
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val send = Intent(Intent.ACTION_SEND).apply {
        type = "video/mp4"
        putExtra(Intent.EXTRA_STREAM, uri)
        putExtra(Intent.EXTRA_TITLE, name)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(send, "Share video").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

@Composable
private fun MessageCard(title: String, body: String, icon: androidx.compose.ui.graphics.vector.ImageVector, color: Color) {
    Card {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(icon, null, tint = color)
                Text(title, style = MaterialTheme.typography.titleMedium, color = color)
            }
            Text(body, color = Vmk.colors.textSecondary)
        }
    }
}

@Composable
fun ProgressCard(stage: VideoStatus.Stage) {
    Card(Modifier.testTag("progressCard")) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("Making your video", style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text)
            Text("This usually takes a few minutes. You can leave this screen; it keeps going.", style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            for (s in VideoStatus.Stage.entries) {
                Row(
                    Modifier.semantics(mergeDescendants = true) { stateDescription = if (s < stage) "done" else if (s == stage) "in progress" else "waiting" },
                    horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically,
                ) {
                    when {
                        s < stage -> Icon(Icons.Filled.CheckCircle, null, tint = Vmk.colors.success, modifier = Modifier.size(22.dp))
                        s == stage -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        else -> Icon(Icons.Filled.RadioButtonUnchecked, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(22.dp))
                    }
                    Text(s.title, color = if (s <= stage) Vmk.colors.text else Vmk.colors.textSecondary)
                }
            }
        }
    }
}
