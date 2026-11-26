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
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Edit
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
fun VideoDetailScreen(app: AppViewModel, detail: VideoDetailViewModel, http: OkHttpClient, onBack: () -> Unit, onEdit: () -> Unit, onMakeAnother: () -> Unit = {}) {
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
                title = { Text(if (video?.status?.isRunning == true) "" else video?.displayTitle ?: stringResource(R.string.video_title_fallback), style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = onBack, modifier = Modifier.size(48.dp).testTag("backButton")) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back)) } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            if (video == null) { FullScreenSpinner(); return@Box }
            val kind = when (video.status) { VideoStatus.Complete -> 1; is VideoStatus.Running -> 0; VideoStatus.Failed -> 2; VideoStatus.Rejected -> 3 }
            // Making settles into the player with a cross-fade (the same component as the home card, in its roomier layout)
            SettleCrossfade(kind, Modifier.fillMaxSize()) { k ->
                Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    when (k) {
                        1 -> PlayerSection(video, detail, playback, http, onEdit = { detail.pause(); onEdit() }, onMakeAnother = onMakeAnother)
                        0 -> Column(Modifier.padding(20.dp)) { MakingCard(rememberMakingSnapshot(video, state), Modifier.testTag("progressCard"), MakingLayout.Detail) }
                        2 -> Column(Modifier.padding(20.dp)) { MessageCard(stringResource(R.string.video_failed_title), stringResource(R.string.video_failed_body), Icons.Filled.Warning, Vmk.colors.danger) }
                        else -> Column(Modifier.padding(20.dp)) { MessageCard(stringResource(R.string.video_rejected_title), video.rejectReason ?: stringResource(R.string.video_rejected_body), Icons.Filled.PanTool, Vmk.colors.warning) }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun PlayerSection(video: VideoItem, detail: VideoDetailViewModel, playback: PlaybackState, http: OkHttpClient, onEdit: () -> Unit, onMakeAnother: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val fullScreen = rememberLauncherForActivityResult(FullScreenContract()) { r -> r?.let { detail.returnFromFullScreen(it.positionMs, it.playWhenReady) } }

    // edge to edge: the picture uses the whole width (black bars for tall videos), everything else keeps the 20 dp margin
    when (playback) {
        is PlaybackState.Ready -> InlinePlayer(detail.player, onFullScreen = { detail.enterFullScreen(video.isTall)?.let { fullScreen.launch(it) } }, ratio = video.frameRatio, edgeToEdge = true)
        is PlaybackState.Error -> Column(
            Modifier.padding(horizontal = 20.dp).fillMaxWidth().background(Vmk.colors.surface, androidx.compose.foundation.shape.RoundedCornerShape(Vmk.radius)).padding(24.dp).testTag("playbackError"),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(playback.message, color = Vmk.colors.textSecondary)
            OutlinedButton(onClick = { detail.reload() }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_try_again)) }
        }
        else -> Box(Modifier.fillMaxWidth().androidAspect(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
    }

    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        val liveAnnounce = stringResource(R.string.making_ready_announce, video.displayTitle)
        Text(video.displayTitle, style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, modifier = Modifier.semantics { heading(); contentDescription = liveAnnounce; liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite })

        val description = (playback as? PlaybackState.Ready)?.description
        var sharing by remember { mutableStateOf(false) }
        var shareError by remember { mutableStateOf<String?>(null) }
        var saving by remember { mutableStateOf(false) }
        var saved by remember { mutableStateOf(false) }
        val url = (playback as? PlaybackState.Ready)?.url
        val shareFailedText = stringResource(R.string.share_failed)
        val saveFailedText = stringResource(R.string.video_save_failed)
        val haptics = rememberHaptics()

        // Share is the one primary action
        if (url != null) {
            PrimaryButton(
                stringResource(if (sharing) R.string.share_preparing else R.string.share_action),
                onClick = {
                    if (sharing) return@PrimaryButton
                    sharing = true; shareError = null
                    scope.launch {
                        try { shareVideo(context, http, url, video.displayTitle) } catch (e: Exception) { shareError = shareFailedText }
                        sharing = false
                    }
                },
                modifier = Modifier.testTag("shareButton"),
            ) {
                if (sharing) CircularProgressIndicator(Modifier.size(20.dp), color = Vmk.colors.onPrimary, strokeWidth = 2.dp) else Icon(Icons.Filled.Share, null, Modifier.size(20.dp), tint = Vmk.colors.onPrimary)
                Spacer(Modifier.width(8.dp))
                Text(stringResource(if (sharing) R.string.share_preparing else R.string.share_action), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.onPrimary, textAlign = TextAlign.Center)
            }
        }
        // Save and Edit: secondary, side by side while they fit, stacked when they do not
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth(), maxItemsInEachRow = if (isLargeText()) 1 else 2) {
            if (url != null && Build.VERSION.SDK_INT >= 29) OutlinedButton(
                onClick = {
                    if (saving) return@OutlinedButton
                    saving = true; shareError = null; saved = false
                    scope.launch {
                        try { saveVideoToGallery(context, http, url, video.displayTitle); saved = true; haptics.play(DesignTokens.Haptic.UploadDone) } catch (e: Exception) { shareError = saveFailedText }
                        saving = false
                    }
                },
                modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("saveButton"),
            ) {
                if (saving) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Icon(if (saved) Icons.Filled.Check else Icons.Filled.Download, null, Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(stringResource(if (saving) R.string.video_saving else if (saved) R.string.video_saved else R.string.video_save), textAlign = TextAlign.Center)
            }
            if (video.editable) OutlinedButton(onClick = onEdit, modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("editButton")) {
                Icon(Icons.Filled.Edit, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.video_edit), textAlign = TextAlign.Center)
            }
        }
        shareError?.let { Text(it, color = Vmk.colors.danger, style = MaterialTheme.typography.bodySmall) }

        if (description != null) {
            var open by rememberSaveable { mutableStateOf(false) }
            var copiedDescription by remember { mutableStateOf(false) }
            Column(Modifier.testTag("descriptionGroup")) {
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClickLabel = stringResource(if (open) R.string.video_hide_description else R.string.video_show_description)) { open = !open },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(stringResource(R.string.video_description_toggle), style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.primary, modifier = Modifier.weight(1f))
                    Icon(if (open) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null, tint = MaterialTheme.colorScheme.primary)
                }
                if (open) {
                    androidx.compose.foundation.text.selection.SelectionContainer {
                        Text(linkified(description, MaterialTheme.colorScheme.primary), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 6.dp))
                    }
                    // "Copy description with credits" lives inside the credits disclosure (it is a rare action)
                    TextButton(
                        onClick = { copyText(context, Txt.s(R.string.share_clip_label_description), description); copiedDescription = true; scope.launch { delay(2000); copiedDescription = false } },
                        modifier = Modifier.heightIn(min = 48.dp).testTag("copyDescription"),
                    ) {
                        Icon(if (copiedDescription) Icons.Filled.Check else Icons.AutoMirrored.Filled.TextSnippet, null, Modifier.size(18.dp)); Spacer(Modifier.width(8.dp))
                        Text(stringResource(if (copiedDescription) R.string.share_copied else R.string.share_copy_description), textAlign = TextAlign.Start)
                    }
                }
            }
        }

        // the next card: the best moment to ask for another video
        val nextShape = androidx.compose.foundation.shape.RoundedCornerShape(Vmk.radii.card)
        Row(
            Modifier.fillMaxWidth().clip(nextShape).background(Vmk.colors.primaryContainer).clickable(role = androidx.compose.ui.semantics.Role.Button, onClick = onMakeAnother).padding(Vmk.space.l).testTag("makeAnother"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m),
        ) {
            Icon(Icons.Filled.Add, null, tint = Vmk.colors.primary, modifier = Modifier.size(28.dp))
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.video_make_another), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text)
                Text(stringResource(R.string.video_make_another_sub), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            }
            Icon(Icons.Filled.ChevronRight, null, tint = Vmk.colors.textSecondary)
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
