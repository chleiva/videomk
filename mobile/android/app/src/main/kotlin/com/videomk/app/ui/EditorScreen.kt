package com.videomk.app.ui

import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.foundation.selection.toggleable
import androidx.compose.ui.semantics.Role
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import coil3.compose.AsyncImage
import com.videomk.app.R
import com.videomk.app.core.Txt
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.core.EditorBeat
import com.videomk.app.core.EditorDiff
import com.videomk.app.core.PhotoCandidate
import com.videomk.app.core.RenderMode
import com.videomk.app.core.SceneKind

/** The row text of a pause, e.g. Silent pause, 4 s. */
internal fun silentLabel(hold: Double?): String = if (hold == null) Txt.s(R.string.editor_silent_pause) else Txt.s(R.string.editor_silent_pause_hold, Math.round(hold).toInt())

@Composable
fun SceneKind?.icon(): ImageVector = when (this) {
    SceneKind.Title -> Sym.TextFields
    SceneKind.Bullets -> Sym.FormatListBulleted
    SceneKind.Diagram -> Sym.Hub
    SceneKind.Chart -> Sym.BarChart
    SceneKind.Timeline -> Sym.Schedule
    SceneKind.Stat -> Sym.Numbers
    SceneKind.Quote -> Sym.FormatQuote
    SceneKind.Image -> Sym.Image
    SceneKind.Clip -> Sym.Movie
    SceneKind.Gallery -> Sym.PhotoLibrary
    null -> Sym.Widgets   // a scene type this version doesn't know: a neutral icon
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditorScreen(vm: EditorViewModel, onClose: () -> Unit) {
    val state by vm.state.collectAsState()
    var selected by rememberSaveable { mutableStateOf<String?>(null) }
    var confirmDiscard by rememberSaveable { mutableStateOf(false) }
    var reorder by rememberSaveable { mutableStateOf(false) }

    fun requestClose() { if (state.isDirty && state.phase == EditorPhase.Editing) confirmDiscard = true else onClose() }

    BackHandler(enabled = selected == null && !state.isLocked) { requestClose() }

    val sel = selected
    if (sel != null && state.phase == EditorPhase.Editing) {
        BeatEditor(vm, state, sel, onDone = { selected = null })
        return
    }

    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            VmkTopBar(title = stringResource(R.string.editor_title), onBack = { if (!state.isLocked) requestClose() }, close = true, backTag = "closeEditor") {
                if (state.phase == EditorPhase.Editing) {
                    TextAction(stringResource(if (reorder) R.string.common_done else R.string.editor_reorder), { reorder = !reorder }, Modifier.testTag("reorderToggle"))
                }
            }
        },
        bottomBar = { if (state.phase == EditorPhase.Editing) ActionBar(vm, state) },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when (val phase = state.phase) {
                EditorPhase.Loading -> FullScreenSpinner()
                is EditorPhase.Failed -> MessageState(stringResource(R.string.editor_failed_title), phase.message, stringResource(R.string.editor_reload), { vm.load() })
                is EditorPhase.Rendering -> RenderingView(phase.mode)
                is EditorPhase.Done -> DoneView(phase.mode, state.resultUrl, onKeepEditing = { vm.keepEditing() }, onClose = onClose)
                EditorPhase.Editing -> BeatList(vm, state, reorder, onSelect = { selected = it })
            }
        }
    }

    if (confirmDiscard) {
        AlertDialog(
            onDismissRequest = { confirmDiscard = false },
            title = { Text(stringResource(R.string.editor_discard_title)) },
            confirmButton = { TextButton(onClick = { confirmDiscard = false; onClose() }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.editor_discard_confirm), color = Vmk.colors.danger) } },
            dismissButton = { TextButton(onClick = { confirmDiscard = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.editor_keep_editing)) } },
        )
    }
}

@Composable
private fun BeatList(vm: EditorViewModel, state: EditorState, reorder: Boolean, onSelect: (String) -> Unit) {
    LazyColumn(Modifier.fillMaxSize().testTag("beatList"), contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        state.banner?.let { banner ->
            item(key = "banner") {
                Card {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(banner, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.danger, modifier = Modifier.testTag("editorBanner"))
                        TextButton(onClick = { vm.load() }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.editor_reload_discard)) }
                    }
                }
            }
        }
        item(key = "title") {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Overline(stringResource(R.string.editor_field_title))
                VmkField(state.title, vm::setTitle, Modifier.testTag("titleField"))
                SubtitlesRow(state.captions, vm::setCaptions, Modifier.testTag("captionsToggle"))
                Text(stringResource(R.string.editor_scenes_count, state.beats.size), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 12.dp))
            }
        }
        items(state.beats, key = { it.id }) { beat ->
            BeatRow(beat, state.isEdited(beat.id), state.narrationError(beat.id), reorder, state.picks[beat.id] != null,
                canUp = state.beats.firstOrNull()?.id != beat.id, canDown = state.beats.lastOrNull()?.id != beat.id,
                onClick = { onSelect(beat.id) }, onUp = { vm.move(beat.id, -1) }, onDown = { vm.move(beat.id, 1) }, onDelete = { vm.delete(beat.id) })
        }
        item(key = "footer") {
            Text(
                stringResource(if (reorder) R.string.editor_footer_reorder else R.string.editor_footer_tap),
                style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary,
            )
        }
    }
}

@Composable
private fun SubtitlesRow(on: Boolean, onChange: (Boolean) -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(value = on, role = Role.Switch, onValueChange = onChange),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(stringResource(R.string.editor_subtitles), color = Vmk.colors.text, modifier = Modifier.weight(1f))
        Switch(checked = on, onCheckedChange = null, colors = vmkSwitchColors())
    }
}

@Composable
private fun ActionBar(vm: EditorViewModel, state: EditorState) {
    Surface(color = Vmk.colors.surface, shadowElevation = 6.dp, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.navigationBarsPadding().padding(horizontal = 20.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                TonalButton(stringResource(R.string.editor_preview), { vm.submit(RenderMode.Preview) }, Modifier.weight(1f).heightIn(min = Vmk.primaryButton).testTag("previewButton"), enabled = state.isDirty)
                PrimaryButton(
                    stringResource(R.string.editor_publish), onClick = { vm.submit(RenderMode.Final) }, enabled = state.isDirty || state.canPublishWithoutChanges,
                    modifier = Modifier.weight(1f).testTag("publishButton"),
                )
            }
            Text(
                stringResource(if (state.isDirty) R.string.editor_action_hint_dirty else R.string.editor_action_hint_clean),
                style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
internal fun BeatRow(
    beat: EditorBeat, edited: Boolean, error: String?, reorder: Boolean, picked: Boolean, canUp: Boolean, canDown: Boolean,
    onClick: () -> Unit, onUp: () -> Unit, onDown: () -> Unit, onDelete: () -> Unit,
) {
    Surface(shape = RoundedCornerShape(Vmk.radius), color = Vmk.colors.surface, modifier = Modifier.fillMaxWidth().testTag("beatRow")) {
        Row(Modifier.padding(vertical = 4.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Row(
                Modifier.weight(1f).heightIn(min = 56.dp).clickable(onClickLabel = stringResource(R.string.editor_edit_scene), onClick = onClick).padding(8.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Box(Modifier.size(64.dp, 44.dp).clip(RoundedCornerShape(8.dp)).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
                    val photoUrl = beat.photo?.url
                    if (beat.kind == SceneKind.Image && photoUrl != null) {
                        AsyncImage(photoUrl, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                    } else Icon(beat.kind.icon(), null, tint = MaterialTheme.colorScheme.primary)
                }
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(beat.label, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
                        beat.duration?.let { Text(stringResource(R.string.len_short_seconds, Math.round(it).toInt()), style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textSecondary) }
                        if (edited) Text(stringResource(R.string.editor_edited), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.warning)
                        else if (beat.stale) Text(stringResource(R.string.editor_will_remake), style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textSecondary)
                    }
                    if (beat.silent && beat.narration.isEmpty()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.testTag("silentBeatLabel")) {
                            Icon(Sym.VolumeOff, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(18.dp))
                            Text(silentLabel(beat.hold), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
                        }
                    } else Text(beat.narration, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger) }
                }
            }
            if (reorder) {
                Column {
                    GlassIconButton(Sym.ArrowUpward, stringResource(R.string.editor_move_up), onUp, enabled = canUp)
                    GlassIconButton(Sym.ArrowDownward, stringResource(R.string.editor_move_down), onDown, enabled = canDown)
                }
                GlassIconButton(Sym.Delete, stringResource(R.string.editor_delete_scene), onDelete, tint = Vmk.colors.danger)
            }
        }
    }
}

@Composable
private fun RenderingView(mode: RenderMode) {
    Column(
        Modifier.fillMaxSize().padding(32.dp).testTag("renderingView"),
        verticalArrangement = Arrangement.spacedBy(18.dp, Alignment.CenterVertically), horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        CircularProgressIndicator(Modifier.size(48.dp))
        Text(stringResource(if (mode == RenderMode.Final) R.string.editor_rendering_final else R.string.editor_rendering_preview), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
        Text(
            stringResource(R.string.editor_rendering_body),
            textAlign = TextAlign.Center, color = Vmk.colors.textSecondary,
        )
    }
}

@Composable
private fun DoneView(mode: RenderMode, url: String?, onKeepEditing: () -> Unit, onClose: () -> Unit) {
    val context = LocalContext.current
    val player = remember(url) {
        url?.let {
            ExoPlayer.Builder(context)
                .setAudioAttributes(androidx.media3.common.AudioAttributes.Builder().setUsage(androidx.media3.common.C.USAGE_MEDIA).setContentType(androidx.media3.common.C.AUDIO_CONTENT_TYPE_MOVIE).build(), true)
                .build().apply { setMediaItem(MediaItem.fromUri(it)); prepare() }
        }
    }
    DisposableEffect(player) { onDispose { player?.release() } }
    val fullScreen = rememberLauncherForActivityResult(FullScreenContract()) { r -> r?.let { player?.seekTo(it.positionMs); player?.playWhenReady = it.playWhenReady } }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(stringResource(if (mode == RenderMode.Final) R.string.editor_done_published else R.string.editor_done_preview), style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.testTag("doneTitle"))
        if (player != null && url != null) {
            InlinePlayer(player, onFullScreen = { player.pause(); fullScreen.launch(FullScreenArgs(url, player.currentPosition, true)) })
        }
        if (mode == RenderMode.Preview) Text(stringResource(R.string.editor_done_draft_note), color = Vmk.colors.textSecondary)
        PrimaryButton(stringResource(if (mode == RenderMode.Final) R.string.common_done else R.string.editor_back_to_editing), onClick = { if (mode == RenderMode.Final) onClose() else onKeepEditing() }, modifier = Modifier.testTag("doneButton"))
    }
}

// one scene

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BeatEditor(vm: EditorViewModel, state: EditorState, beatId: String, onDone: () -> Unit) {
    val beat = state.beats.firstOrNull { it.id == beatId }
    val error = state.narrationError(beatId)
    BackHandler(enabled = true) { if (error == null) onDone() }

    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            VmkTopBar(title = stringResource(R.string.editor_scene_generic)) {
                TextAction(stringResource(R.string.common_done), onDone, Modifier.testTag("beatDone"), enabled = error == null)
            }
        },
    ) { padding ->
        if (beat == null) { MessageState(stringResource(R.string.editor_scene_missing_title), stringResource(R.string.editor_scene_missing_body), stringResource(R.string.common_back), onDone, Modifier.padding(padding)); return@Scaffold }
        Column(Modifier.fillMaxSize().padding(padding).imePadding().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            val words = EditorDiff.wordCount(beat.narration)
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Overline(stringResource(R.string.editor_field_narration))
                VmkField(beat.narration, { vm.setNarration(beatId, it) }, Modifier.testTag("narrationField"), singleLine = false, minHeight = 140.dp)
                androidx.compose.runtime.CompositionLocalProvider(androidx.compose.material3.LocalTextStyle provides MaterialTheme.typography.bodySmall, androidx.compose.material3.LocalContentColor provides if (error != null) Vmk.colors.danger else Vmk.colors.textSecondary) {
                    NarrationSupport(beat, words, state.limits.minWords, state.limits.maxWords, error)
                }
            }
            Card {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text(stringResource(R.string.editor_visual), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.textSecondary)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(beat.kind.icon(), null, tint = MaterialTheme.colorScheme.primary)
                        Column {
                            Text(beat.label, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, modifier = Modifier.testTag("sceneLabel"))
                            if (beat.summary.isNotEmpty()) Text(beat.summary, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
                        }
                    }
                    if (beat.kind != SceneKind.Image) {
                        Text(
                            stringResource(R.string.editor_visual_note),
                            style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary,
                        )
                    }
                }
            }
            if (beat.kind == SceneKind.Image) PhotoSection(vm, state, beat)
        }
    }
}

/** The text under the narration field. A silent pause with no words explains itself instead of counting words. */
@Composable
internal fun NarrationSupport(beat: EditorBeat, words: Int, minWords: Int, maxWords: Int, error: String?) {
    Column(Modifier.testTag("narrationSupport")) {
        if (beat.silent && words == 0) {
            Text(pluralStringResource(R.plurals.editor_silent_note, Math.round(beat.hold ?: 0.0).toInt(), Math.round(beat.hold ?: 0.0).toInt()))
        } else {
            Text(pluralStringResource(R.plurals.editor_words_spoken, words, words, Math.round(EditorDiff.spokenSeconds(beat.narration)).toInt()))
            Text(stringResource(R.string.editor_words_range, minWords, maxWords))
        }
        if (error != null) Text(error, color = Vmk.colors.danger)
    }
}

@Composable
private fun PhotoSection(vm: EditorViewModel, state: EditorState, beat: EditorBeat) {
    val pick = state.picks[beat.id]
    Card {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.editor_photo), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.textSecondary)
            val photo = beat.photo
            if (photo?.url != null && pick == null) {
                AsyncImage(photo.url, contentDescription = stringResource(R.string.editor_current_photo), contentScale = ContentScale.Crop, modifier = Modifier.fillMaxWidth().height(180.dp).clip(RoundedCornerShape(12.dp)))
                photo.credit?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary) }
            } else if (photo?.noPhoto == true && pick == null) {
                Text(stringResource(R.string.editor_no_photo), color = Vmk.colors.warning)
            }
            val chosen = pick?.let { p -> beat.candidates.firstOrNull { it.key == p } }
            if (chosen != null) {
                Text(stringResource(R.string.editor_will_use_photo, chosen.creator), color = Vmk.colors.success, fontWeight = FontWeight.Medium, modifier = Modifier.testTag("pickedNote"))
                TextButton(onClick = { vm.clearPick(beat.id) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.editor_undo_photo)) }
            }
        }
    }
    if (beat.candidates.isNotEmpty()) {
        Card {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(stringResource(R.string.editor_other_photos), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.textSecondary)
                beat.candidates.chunked(2).forEach { row ->
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                        for (c in row) CandidateTile(c, chosen = pick == c.key || (pick == null && beat.photo?.chosen == c.key), modifier = Modifier.weight(1f)) { vm.pick(c, beat.id) }
                        if (row.size == 1) Box(Modifier.weight(1f))
                    }
                }
                Text(stringResource(R.string.editor_credit_note), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
            }
        }
    }
}

@Composable
private fun CandidateTile(c: PhotoCandidate, chosen: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val tileDesc = stringResource(if (chosen) R.string.editor_photo_by_selected else R.string.editor_photo_by, c.creator)
    Column(
        modifier.clickable(onClickLabel = stringResource(R.string.editor_use_photo), onClick = onClick).semantics(mergeDescendants = true) { contentDescription = tileDesc },
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Box(Modifier.fillMaxWidth().height(90.dp).clip(RoundedCornerShape(10.dp)).background(Vmk.colors.surfaceRaised)) {
            AsyncImage(c.thumbUrl, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            if (chosen) Box(Modifier.align(Alignment.TopEnd).padding(6.dp).size(22.dp).clip(RoundedCornerShape(11.dp)).background(MaterialTheme.colorScheme.primary), contentAlignment = Alignment.Center) {
                Icon(Sym.Check, null, tint = Color.White, modifier = Modifier.size(16.dp))
            }
        }
        Text(c.creator, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(if (c.provider == "unsplash") "Unsplash" else c.license.uppercase(), style = MaterialTheme.typography.labelSmall, color = Vmk.colors.textSecondary)
    }
}
