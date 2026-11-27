package com.videomk.app.ui

import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.statusBarsPadding
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
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.FlowRow
import android.os.Build
import com.videomk.app.core.DesignTokens
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import com.videomk.app.R
import com.videomk.app.core.Txt
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.foundation.layout.width
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
fun VideoDetailScreen(app: AppViewModel, detail: VideoDetailViewModel, http: OkHttpClient, onBack: () -> Unit, onEdit: () -> Unit, onMakeAnother: () -> Unit = {}, onFeedback: () -> Unit = {}) {
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
            // back (a glass circle), the title once, nothing on the right (docs/UX_2026_REDESIGN.md 4.1)
            Row(Modifier.fillMaxWidth().statusBarsPadding().heightIn(min = 56.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                GlassIconButton(Sym.ArrowBack, stringResource(R.string.common_back), onBack, Modifier.testTag("backButton"))
                Text(
                    if (video?.status?.isRunning == true) "" else video?.displayTitle ?: stringResource(R.string.video_title_fallback), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text,
                    maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, textAlign = TextAlign.Center, modifier = Modifier.weight(1f).padding(horizontal = 8.dp).semantics { heading() },
                )
                Spacer(Modifier.size(48.dp))
            }
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            if (video == null) { FullScreenSpinner(); return@Box }
            val kind = when (video.status) { VideoStatus.Complete -> 1; is VideoStatus.Running -> 0; VideoStatus.Failed -> 2; VideoStatus.Rejected -> 3 }
            // Making settles into the player with a cross-fade (the same component as the home card, in its roomier layout)
            SettleCrossfade(kind, Modifier.fillMaxSize()) { k ->
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    when (k) {
                        1 -> PlayerSection(video, detail, playback, http, onEdit = { detail.pause(); onEdit() }, onMakeAnother = onMakeAnother, onFeedback = onFeedback)
                        0 -> Column(Modifier.padding(20.dp)) { MakingCard(rememberMakingSnapshot(video, state), Modifier.testTag("progressCard"), MakingLayout.Detail) }
                        2 -> Column(Modifier.padding(20.dp)) { MessageCard(stringResource(R.string.video_failed_title), stringResource(R.string.video_failed_body), Sym.Warning, Vmk.colors.danger) }
                        else -> Column(Modifier.padding(20.dp)) { MessageCard(stringResource(R.string.video_rejected_title), video.rejectReason ?: stringResource(R.string.video_rejected_body), Sym.PanTool, Vmk.colors.warning) }
                    }
                }
            }
        }
    }
}

/** "1:20 · 1080p": the duration and the quality are the only metadata under the video. */
private fun captionOf(video: VideoItem): String? = listOfNotNull(video.durationSeconds?.let { duration(it) }, video.resolution?.takeIf { it.isNotBlank() }).joinToString(" · ").ifEmpty { null }

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class, ExperimentalMaterial3Api::class)
@Composable
private fun PlayerSection(video: VideoItem, detail: VideoDetailViewModel, playback: PlaybackState, http: OkHttpClient, onEdit: () -> Unit, onMakeAnother: () -> Unit, onFeedback: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val fullScreen = rememberLauncherForActivityResult(FullScreenContract()) { r -> r?.let { detail.returnFromFullScreen(it.positionMs, it.playWhenReady, it.completed) } }

    // edge to edge: the picture uses the whole width (black bars for tall videos), everything else keeps the 20 dp margin
    when (playback) {
        is PlaybackState.Ready -> InlinePlayer(detail.player, onFullScreen = { detail.enterFullScreen(video.isTall)?.let { fullScreen.launch(it) } }, ratio = video.frameRatio, edgeToEdge = true, onNew = onMakeAnother)
        is PlaybackState.Error -> Column(
            Modifier.padding(horizontal = 20.dp).fillMaxWidth().background(Vmk.colors.surface, androidx.compose.foundation.shape.RoundedCornerShape(Vmk.radius)).padding(24.dp).testTag("playbackError"),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(playback.message, color = Vmk.colors.textSecondary)
            OutlinedButton(onClick = { detail.reload() }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_try_again)) }
        }
        else -> Box(Modifier.fillMaxWidth().androidAspect(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
    }

    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        val liveAnnounce = stringResource(R.string.making_ready_announce, video.displayTitle)
        // the caption also carries the "ready" announcement for screen readers (the visible title is in the top bar)
        captionOf(video)?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.fillMaxWidth().semantics { contentDescription = "$liveAnnounce $it"; liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite }.testTag("videoCaption")) }

        val description = (playback as? PlaybackState.Ready)?.description
        var sharing by remember { mutableStateOf(false) }
        var shareError by remember { mutableStateOf<String?>(null) }
        var saving by remember { mutableStateOf(false) }
        var saved by remember { mutableStateOf(false) }
        var infoOpen by rememberSaveable { mutableStateOf(false) }
        var moreOpen by remember { mutableStateOf(false) }
        val url = (playback as? PlaybackState.Ready)?.url
        val shareFailedText = stringResource(R.string.share_failed)
        val saveFailedText = stringResource(R.string.video_save_failed)
        val savedText = stringResource(R.string.video_saved)
        val haptics = rememberHaptics()

        // five icons, one primary (Share, filled); they wrap to a second row at large text sizes, never clip
        FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly, verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            if (url != null) {
                val shareLabel = stringResource(if (sharing) R.string.share_preparing else R.string.share_action)
                Box(
                    Modifier.size(56.dp).clip(CircleShape).background(Vmk.gradientNow)
                        .clickable(enabled = !sharing, role = androidx.compose.ui.semantics.Role.Button) {
                            sharing = true; shareError = null
                            scope.launch {
                                try { shareVideo(context, http, url, video.displayTitle) } catch (e: Exception) { shareError = shareFailedText }
                                sharing = false
                            }
                        }.semantics { contentDescription = shareLabel }.testTag("shareButton"),
                    contentAlignment = Alignment.Center,
                ) { if (sharing) CircularProgressIndicator(Modifier.size(24.dp), color = Vmk.colors.onPrimary, strokeWidth = 2.dp) else Icon(Sym.Share, null, Modifier.size(26.dp), tint = Vmk.colors.onPrimary) }
            }
            if (url != null && Build.VERSION.SDK_INT >= 29) {
                if (saving) Box(Modifier.size(48.dp).semantics { contentDescription = Txt.s(R.string.video_saving) }, contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp) }
                else GlassIconButton(
                    if (saved) Sym.Check else Sym.Download, stringResource(R.string.video_save),
                    onClick = {
                        saving = true; shareError = null; saved = false
                        scope.launch {
                            try { saveVideoToGallery(context, http, url, video.displayTitle); saved = true; haptics.play(DesignTokens.Haptic.UploadDone); android.widget.Toast.makeText(context, savedText, android.widget.Toast.LENGTH_SHORT).show() } catch (e: Exception) { shareError = saveFailedText }
                            saving = false
                        }
                    },
                    modifier = Modifier.testTag("saveButton"),
                )
            }
            if (video.editable) GlassIconButton(Sym.Tune, stringResource(R.string.video_edit_desc), onEdit, Modifier.testTag("editButton"))
            if (description != null) GlassIconButton(Sym.Info, stringResource(R.string.action_info), { infoOpen = true }, Modifier.testTag("infoButton"))
            Box {
                GlassIconButton(Sym.MoreHoriz, stringResource(R.string.action_more), { moreOpen = true }, Modifier.testTag("moreButton"))
                androidx.compose.material3.DropdownMenu(expanded = moreOpen, onDismissRequest = { moreOpen = false }, containerColor = Vmk.colors.surface) {
                    androidx.compose.material3.DropdownMenuItem(text = { Text(stringResource(R.string.lib_new_video)) }, leadingIcon = { Icon(Sym.Add, null) }, onClick = { moreOpen = false; onMakeAnother() }, modifier = Modifier.testTag("makeAnother"))
                    androidx.compose.material3.DropdownMenuItem(text = { Text(stringResource(R.string.feedback_title)) }, leadingIcon = { Icon(Sym.ChatBubbleOutline, null) }, onClick = { moreOpen = false; onFeedback() }, modifier = Modifier.testTag("feedbackLink"))
                }
            }
        }
        shareError?.let { Text(it, color = Vmk.colors.danger, style = MaterialTheme.typography.bodySmall, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center) }

        if (infoOpen && description != null) InfoSheet(description, onDismiss = { infoOpen = false })
    }
}

/** Info: the description and the photo credits, with one Copy button (replaces the disclosure and "Copy description with credits"). */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun InfoSheet(description: String, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var copied by remember { mutableStateOf(false) }
    androidx.compose.material3.ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Vmk.colors.surface, modifier = Modifier.testTag("infoSheet")) {
        Column(Modifier.padding(horizontal = Vmk.space.sheet).padding(bottom = Vmk.space.xxl), verticalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
            Text(stringResource(R.string.video_info_title), style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
            androidx.compose.foundation.text.selection.SelectionContainer {
                Text(linkified(description, MaterialTheme.colorScheme.primary), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.verticalScroll(rememberScrollState()).heightIn(max = 320.dp))
            }
            TextButton(
                onClick = { copyText(context, Txt.s(R.string.share_clip_label_description), description); copied = true; scope.launch { delay(2000); copied = false } },
                modifier = Modifier.heightIn(min = 48.dp).testTag("copyDescription"),
            ) {
                Icon(if (copied) Sym.Check else Sym.TextSnippet, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
                Text(stringResource(if (copied) R.string.share_copied else R.string.video_copy), textAlign = TextAlign.Start)
            }
        }
    }
}

private fun Modifier.androidAspect(): Modifier = this.then(Modifier.heightIn(min = 200.dp))

private fun copyText(context: Context, label: String, text: String) {
    runCatching { (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text)) }
}

/** Copies the video into the phone's gallery (Movies/videomk) through MediaStore: no storage permission is needed from Android 10; older versions do not offer Save. */
@androidx.annotation.RequiresApi(29)
private suspend fun saveVideoToGallery(context: Context, http: OkHttpClient, url: String, name: String) {
    withContext(Dispatchers.IO) {
        val safe = name.replace(Regex("[^\\p{L}\\p{N} _.-]"), "-").trim().ifEmpty { "video" }.take(80)
        val values = android.content.ContentValues().apply {
            put(android.provider.MediaStore.Video.Media.DISPLAY_NAME, "$safe.mp4")
            put(android.provider.MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(android.provider.MediaStore.Video.Media.RELATIVE_PATH, "Movies/videomk")
            put(android.provider.MediaStore.Video.Media.IS_PENDING, 1)
        }
        val resolver = context.contentResolver
        val uri = resolver.insert(android.provider.MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values) ?: throw java.io.IOException("no gallery")
        try {
            http.newCall(Request.Builder().url(url).build()).execute().use { r ->
                if (!r.isSuccessful) throw java.io.IOException("download failed")
                resolver.openOutputStream(uri)?.use { out -> r.body.byteStream().use { it.copyTo(out) } } ?: throw java.io.IOException("no output")
            }
            resolver.update(uri, android.content.ContentValues().apply { put(android.provider.MediaStore.Video.Media.IS_PENDING, 0) }, null, null)
        } catch (e: Exception) { runCatching { resolver.delete(uri, null, null) }; throw e }
    }
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
    context.startActivity(Intent.createChooser(send, Txt.s(R.string.share_chooser_title)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
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
    val doneText = stringResource(R.string.video_step_done); val activeText = stringResource(R.string.video_step_active); val waitingText = stringResource(R.string.video_step_waiting)
    Card(Modifier.testTag("progressCard")) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(stringResource(R.string.lib_making_title), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text)
            Text(stringResource(R.string.video_progress_body), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            for (s in VideoStatus.Stage.entries) {
                Row(
                    Modifier.semantics(mergeDescendants = true) { stateDescription = if (s < stage) doneText else if (s == stage) activeText else waitingText },
                    horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically,
                ) {
                    when {
                        s < stage -> Icon(Sym.CheckCircle, null, tint = Vmk.colors.success, modifier = Modifier.size(22.dp))
                        s == stage -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                        else -> Icon(Sym.RadioButtonUnchecked, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(22.dp))
                    }
                    Text(s.title, color = if (s <= stage) Vmk.colors.text else Vmk.colors.textSecondary)
                }
            }
        }
    }
}
