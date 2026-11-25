package com.videomk.app.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.view.HapticFeedbackConstants
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.union
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.videomk.app.core.AddPhotosLogic
import com.videomk.app.core.ComposerLogic
import com.videomk.app.core.ComposerStatus
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.MediaLabels
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.StatusKind
import com.videomk.app.data.DictationController
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private fun plural(n: Int) = if (n == 1) "" else "s"

/**
 * The docked composer card (docs/UI_DESIGN.md section e): photo strip, a two-line field, ONE status line (price, reason and fix), and a toolbar with
 * attach, the options pill, the microphone and a send button that is always drawn (tonal until it can act).
 */
@Composable
fun ComposerBar(
    composer: ComposerViewModel, balance: Int?, onSend: () -> Unit, modifier: Modifier = Modifier,
    onAddCredits: () -> Unit = {},
) {
    val context = LocalContext.current
    val view = LocalView.current
    val scope = rememberCoroutineScope()
    val dictationState by composer.dictation.state.collectAsState()
    val listening = dictationState is DictationController.State.Listening || dictationState is DictationController.State.Starting
    val options = composer.options
    val status = ComposerLogic.status(composer.text, options, balance, composer.totalPhotos, listening, sending = false)
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val container = LocalContainerOrNull.current
    var optionsOpen by remember { mutableStateOf(false) }
    var pulse by remember { mutableIntStateOf(0) }
    val shake = remember { Animatable(0f) }
    val flash = remember { Animatable(0f) }
    val still = reduceMotion(context)

    LaunchedEffect(composer.focusRequests) {
        if (composer.focusRequests > 0) { runCatching { focus.requestFocus() }; keyboard?.show() }
    }
    LaunchedEffect(dictationState) {
        if (dictationState is DictationController.State.Unavailable || dictationState is DictationController.State.KeyboardHint) {
            delay(8000); composer.dictation.clearHint()
        }
    }
    LaunchedEffect(pulse) {
        if (pulse > 0 && !still) {
            flash.snapTo(1f)
            launch { flash.animateTo(0f, tween(450)) }
            for (x in listOf(4f, -4f, 3f, -3f, 0f)) shake.animateTo(x, tween(55))
        }
    }

    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        composer.dictation.start(composer.text, if (granted) DictationPlan.Permission.Granted else DictationPlan.Permission.Denied)
    }

    fun onMic() {
        try {
            if (composer.dictation.isListening) { composer.dictation.stop(); return }
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                composer.dictation.start(composer.text, DictationPlan.Permission.Granted)
            } else {
                micPermission.launch(Manifest.permission.RECORD_AUDIO)   // answers at once (as denied) when the user chose "don't ask again"
            }
        } catch (e: Exception) {
            composer.dictation.start(composer.text, DictationPlan.Permission.Denied)
        }
    }

    fun haptic(ok: Boolean) {
        if (Build.VERSION.SDK_INT >= 30) view.performHapticFeedback(if (ok) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.REJECT)
        else view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
    }

    fun tapSend() {
        if (status.sendReady) { haptic(true); onSend() }
        else {
            // a tonal send is never dead: it pulses the reason and says it out loud
            haptic(false); pulse++
            view.announceForAccessibility(status.text + (status.fix?.let { ". " + it.description() } ?: ""))
        }
    }

    fun applyFix() {
        val fix = status.fix ?: return
        if (fix.addCredits) onAddCredits() else composer.options = options.copy(minutes = fix.minutes!!.toDouble())
    }

    val shape = RoundedCornerShape(28.dp)
    val dark = Vmk.colors.dark
    val big = LocalDensity.current.fontScale >= 1.5f
    Surface(
        modifier = modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.navigationBars.union(WindowInsets.ime))
            .padding(horizontal = 12.dp).padding(bottom = 8.dp, top = 4.dp)
            .widthIn(max = 640.dp)
            .vmkShadow(3, shape, dark).hairline(shape, Vmk.colors.outline),
        shape = shape, color = Vmk.colors.surface,
    ) {
        Column(Modifier.padding(start = 16.dp, end = 12.dp, top = 12.dp, bottom = 10.dp)) {
            if (composer.totalPhotos > 0) {
                PhotoStrip(composer)
                Box(Modifier.size(6.dp))
            }
            TextField(
                value = composer.text, onValueChange = { composer.text = it },
                modifier = Modifier.fillMaxWidth().focusRequester(focus).offset(x = (-16).dp).testTag("composerField"),
                placeholder = { Text(if (composer.totalPhotos == 0) "Describe your video…" else "What should the video be about?", style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textTertiary) },
                textStyle = MaterialTheme.typography.bodyLarge,
                minLines = 2, maxLines = 6,
                readOnly = listening,
                keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                colors = TextFieldDefaults.colors(
                    focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent, disabledContainerColor = Color.Transparent,
                    focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent, disabledIndicatorColor = Color.Transparent,
                    focusedTextColor = if (listening) Vmk.colors.textSecondary else Vmk.colors.text, unfocusedTextColor = if (listening) Vmk.colors.textSecondary else Vmk.colors.text,
                ),
            )
            dictationHint(dictationState)
            StatusLine(status, flash.value, shake.value, ::applyFix)
            Box(Modifier.size(6.dp))
            val attach: @Composable () -> Unit = { AttachButton(composer, enabled = !listening) { composer.openAddPhotos(null) } }
            val pill: @Composable (Modifier) -> Unit = { m -> OptionsPill(composer, status, enabled = !listening, m) { optionsOpen = true } }
            val mic: @Composable () -> Unit = { MicButton(listening, ::onMic) }
            val send: @Composable () -> Unit = { SendButton(status, balance, options, ::tapSend) }
            if (big) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) { attach(); pill(Modifier.weight(1f)) }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) { mic(); send() }
                }
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) { attach(); pill(Modifier.weight(1f)); mic(); send() }
            }
        }
    }

    if (optionsOpen) OptionsSheet(composer, balance, onDismiss = { optionsOpen = false })
    val request = composer.addPhotosRequest
    if (request != null) {
        AddPhotosSheet(composer, container?.mediaApi, container?.mediaUploads?.arrivals, startOnMyMedia = request.tab == 1, onDismiss = { composer.closeAddPhotos() })
    }
}

@Composable
private fun dictationHint(state: DictationController.State) {
    when (state) {
        is DictationController.State.Unavailable -> HintRow(state.message, Vmk.colors.warning, "dictationUnavailable")
        is DictationController.State.KeyboardHint -> HintRow(state.message, Vmk.colors.textSecondary, "dictationKeyboardHint")
        else -> Unit
    }
}

@Composable
private fun HintRow(message: String, color: Color, tag: String) {
    Row(Modifier.padding(top = 4.dp).testTag(tag), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Icon(Icons.Filled.Warning, null, tint = color, modifier = Modifier.size(16.dp))
        Text(message, style = MaterialTheme.typography.bodySmall, color = color)
    }
}

/** The single place for price, reason and fix: exactly one message at a time. */
@Composable
private fun StatusLine(status: ComposerStatus, flash: Float, shake: Float, onFix: () -> Unit) {
    val color = when (status.kind) {
        StatusKind.TooLong -> Vmk.colors.danger
        StatusKind.NotAffordable, StatusKind.NoCredits -> Vmk.colors.warning
        StatusKind.Listening -> Vmk.colors.danger
        StatusKind.PhotoHint -> Vmk.colors.text
        else -> Vmk.colors.textSecondary
    }
    val icon = when (status.kind) {
        StatusKind.NotAffordable, StatusKind.NoCredits, StatusKind.TooLong -> Icons.Filled.Warning
        StatusKind.Listening -> Icons.Filled.GraphicEq
        else -> Icons.Filled.Bolt
    }
    val iconTint = when (status.kind) { StatusKind.Ready, StatusKind.Idle, StatusKind.PhotoHint, StatusKind.TooShort -> Vmk.colors.primary; else -> color }
    val tag = when (status.kind) {
        StatusKind.NotAffordable, StatusKind.NoCredits -> "notEnoughCredits"
        StatusKind.PhotoHint -> "photoCapacityHint"
        StatusKind.Ready, StatusKind.Idle -> "costLine"
        else -> "hintLine"
    }
    val bg = Vmk.colors.warningContainer.copy(alpha = flash)
    Column(
        Modifier.fillMaxWidth().offset(x = shake.dp).clip(RoundedCornerShape(10.dp)).background(bg).testTag("statusLine")
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Row(Modifier.heightIn(min = 28.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(icon, null, tint = iconTint, modifier = Modifier.size(15.dp))
            Text(status.text, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, color = color, modifier = Modifier.weight(1f).testTag(tag))
            if (status.fix != null && status.kind != StatusKind.PhotoHint) FixChip(status.fix.label(), status.fix.description(), Modifier.testTag("fixChip"), onFix)
        }
        if (status.fix != null && status.kind == StatusKind.PhotoHint) FixChip(status.fix.label(), status.fix.description(), Modifier.padding(start = 23.dp).testTag("fixChip"), onFix)
    }
}

@Composable
private fun AttachButton(composer: ComposerViewModel, enabled: Boolean, onClick: () -> Unit) {
    val n = composer.totalPhotos
    val full = composer.remaining == 0
    Box(Modifier.size(48.dp).alpha(if (enabled) 1f else 0.4f), contentAlignment = Alignment.Center) {
        Box(
            Modifier.size(44.dp).clip(CircleShape).background(Vmk.colors.surfaceRaised)
                .clickable(enabled = enabled, role = Role.Button, onClickLabel = "Add photos", onClick = onClick)
                .semantics { contentDescription = if (n > 0) "Add photos. $n selected" else "Add photos" }.testTag("photoButton"),
            contentAlignment = Alignment.Center,
        ) { Icon(Icons.Filled.AddPhotoAlternate, null, tint = if (full) Vmk.colors.textTertiary else Vmk.colors.text, modifier = Modifier.size(24.dp)) }
        AddPhotosLogic.badge(n)?.let { b ->
            Box(
                Modifier.align(Alignment.TopEnd).offset(x = 4.dp, y = (-2).dp).heightIn(min = 20.dp).clip(CircleShape).background(Vmk.colors.primary).padding(horizontal = 6.dp)
                    .testTag("photoBadge"),
                contentAlignment = Alignment.Center,
            ) { Text(b, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.onPrimary, maxLines = 1) }
        }
    }
}

@Composable
private fun OptionsPill(composer: ComposerViewModel, status: ComposerStatus, enabled: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val options = composer.options
    val warn = status.kind == StatusKind.NotAffordable || status.kind == StatusKind.NoCredits
    val shape = RoundedCornerShape(24.dp)
    val bg by animateColorAsState(if (warn) Vmk.colors.warningContainer else Vmk.colors.surfaceRaised, label = "pill")
    val look = options.look?.title ?: "Producer decides the look"
    val narrow = LocalContext.current.resources.configuration.screenWidthDp < 340
    Row(
        modifier.heightIn(min = 44.dp).clip(shape).background(bg).then(if (warn) Modifier.border(1.5.dp, Vmk.colors.warning, shape) else Modifier)
            .alpha(if (enabled) 1f else 0.4f)
            .clickable(enabled = enabled, role = Role.Button, onClickLabel = "Open video options", onClick = onClick)
            .padding(horizontal = 14.dp)
            .semantics {
                contentDescription = "Video options"
                stateDescription = "${options.minutes.toInt()} minute${plural(options.minutes.toInt())}, ${options.credits} credit${plural(options.credits)}, $look, subtitles ${if (options.captions) "on" else "off"}"
            }.testTag("optionsMenu"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterHorizontally),
    ) {
        Icon(Icons.Filled.Tune, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(20.dp))
        if (narrow) Text("${options.minutes.toInt()} min · ${options.credits}", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 1)
        else CreditsText(options.minutes.toInt(), options.credits, if (warn) Vmk.colors.warning else Vmk.colors.primary)
    }
}

@Composable
private fun MicButton(listening: Boolean, onClick: () -> Unit) {
    val still = reduceMotion(LocalContext.current)
    Box(Modifier.size(48.dp).clickable(role = Role.Button, onClickLabel = if (listening) "Stop dictation" else "Dictate", onClick = onClick)
        .semantics { contentDescription = if (listening) "Stop dictation" else "Dictate. Say what video you want instead of typing" }.testTag("micButton"), contentAlignment = Alignment.Center) {
        if (listening) {
            val ring = if (still) 1f else rememberInfiniteTransition(label = "ring").animateFloat(1f, 1.5f, infiniteRepeatable(tween(1000), RepeatMode.Restart), label = "r").value
            Box(Modifier.size(44.dp).scale(ring).clip(CircleShape).background(Vmk.colors.danger.copy(alpha = 0.18f)))
            Box(Modifier.size(44.dp).clip(CircleShape).background(Vmk.colors.danger), contentAlignment = Alignment.Center) { Icon(Icons.Filled.Stop, null, tint = Color.White, modifier = Modifier.size(22.dp)) }
        } else Icon(Icons.Filled.Mic, null, tint = Vmk.colors.textSecondary, modifier = Modifier.size(24.dp))
    }
}

/** 52 dp, always drawn: filled with the brand gradient when it can act, tonal when it cannot. Never disabled for screen readers. */
@Composable
private fun SendButton(status: ComposerStatus, balance: Int?, options: CreateOptions, onClick: () -> Unit) {
    val ready = status.sendReady
    val desc = if (ready) "Ready, costs ${options.credits} credit${plural(options.credits)}" else "Not ready. ${status.text}${if (status.fix != null) ". Double tap for the fix." else ""}"
    Box(
        Modifier.size(52.dp).clip(CircleShape)
            .then(if (ready) Modifier.background(Vmk.gradientNow) else Modifier.background(Vmk.colors.surface3))
            .clickable(role = Role.Button, onClickLabel = if (ready) "Make video" else "Explain why this can't be sent yet", onClick = onClick)
            .semantics { contentDescription = "Make video"; stateDescription = desc }.testTag("sendButton"),
        contentAlignment = Alignment.Center,
    ) {
        Icon(Icons.Filled.ArrowUpward, null, tint = if (ready) Color.White else Vmk.colors.textTertiary, modifier = Modifier.size(26.dp))
    }
}

/** The attached photos: a count row and a horizontally scrolling strip of small previews, each removable (phone and My media in one strip). */
@Composable
private fun PhotoStrip(composer: ComposerViewModel) {
    val phone = composer.photos.size + composer.loading
    val library = composer.library.size
    val source = when { phone > 0 && library > 0 -> "From this phone and My media"; library > 0 -> "From My media"; else -> "From this phone" }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                "${composer.photos.size + composer.library.size} of ${PhotoLimits.MAX_PHOTOS} photos", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold,
                color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f).testTag("photosNote"),
            )
            Text(source, style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textSecondary)
        }
        if (composer.loading > 0) Text(composer.preparingText, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("photosPreparing"))
        composer.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.testTag("photosNotice")) }
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(end = 4.dp)) {
            itemsIndexed(composer.photos, key = { _, p -> p.id }) { index, photo ->
                StripTile(Modifier.semantics { contentDescription = "Photo ${index + 1} of ${composer.photos.size + composer.library.size}" }.testTag("attachedPhoto"), "Remove photo ${index + 1}", { composer.removePhoto(photo.id) }) {
                    photo.thumbnail?.let { Image(it, it.hashCode()) }
                }
            }
            itemsIndexed(composer.library, key = { _, p -> "lib-${p.id}" }) { _, photo ->
                StripTile(Modifier.semantics { contentDescription = "From My media: ${MediaLabels.photo(photo)}" }.testTag("attachedLibraryPhoto"), "Remove from the video", { composer.removeLibrary(photo.id) }) {
                    PhotoThumb(photo, Modifier.size(56.dp))
                }
            }
            if (composer.loading > 0) item(key = "preparing") {
                Box(Modifier.size(56.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
                    androidx.compose.material3.CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                }
            }
        }
    }
}

@Composable
private fun Image(bitmap: android.graphics.Bitmap, key: Int) {
    androidx.compose.foundation.Image(bitmap.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.size(56.dp))
}

@Composable
private fun StripTile(modifier: Modifier, removeLabel: String, onRemove: () -> Unit, content: @Composable () -> Unit) {
    Box(modifier.size(56.dp)) {
        Box(Modifier.size(56.dp).clip(RoundedCornerShape(12.dp))) { content() }
        // 18 dp to look at, 44 dp to hit
        Box(Modifier.align(Alignment.TopEnd).offset(x = 12.dp, y = (-12).dp).size(44.dp).clickable(onClickLabel = removeLabel, role = Role.Button, onClick = onRemove), contentAlignment = Alignment.Center) {
            Box(Modifier.size(18.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.7f)), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Close, removeLabel, tint = Color.White, modifier = Modifier.size(12.dp))
            }
        }
    }
}
