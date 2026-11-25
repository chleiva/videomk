package com.videomk.app.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.view.HapticFeedbackConstants
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.union
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Warning
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.ClosedCaption
import androidx.compose.material.icons.filled.CropLandscape
import androidx.compose.material.icons.filled.CropPortrait
import androidx.compose.material.icons.filled.CropSquare
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Language
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.videomk.app.core.Brief
import com.videomk.app.core.ComposerLogic
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.CreatePlatforms
import com.videomk.app.core.CreatePrefs
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.PhotoCapacity
import com.videomk.app.core.Lengths
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.layout.width
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.PlatformChip
import com.videomk.app.core.StatusKind
import com.videomk.app.core.VideoLook
import com.videomk.app.data.DictationController
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private fun plural(n: Int) = if (n == 1) "" else "s"

/**
 * The Create screen (docs/UI_DESIGN.md section o): a deterministic form with a Create button that is always visible. Prompt with dictation, Add photos (the unified
 * sheet), "What is it for?", length with prices, collapsed More options, and a bottom bar with the status line and "Create video · ⚡N".
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CreateScreen(app: AppViewModel, composer: ComposerViewModel, onClose: () -> Unit, onOpenWallet: () -> Unit) {
    val context = LocalContext.current
    val view = LocalView.current
    val scope = rememberCoroutineScope()
    val container = LocalContainerOrNull.current
    val state by app.state.collectAsState()
    val person = (state.phase as? Phase.SignedIn)?.email
    val balance = com.videomk.app.DebugHooks.balanceOverride(context) ?: state.wallet?.let { if (it.unlimited) null else it.balance }
    val dictationState by composer.dictation.state.collectAsState()
    val listening = dictationState is DictationController.State.Listening || dictationState is DictationController.State.Starting
    val options = composer.options
    val caps = composer.caps
    val scroll = rememberScrollState()
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    var discard by remember { mutableStateOf(false) }
    var moreOpen by rememberSaveable { mutableStateOf(false) }
    var languageOpen by remember { mutableStateOf(false) }
    var tip by remember { mutableStateOf<String?>(null) }
    var pulse by remember { mutableIntStateOf(0) }
    val shake = remember { Animatable(0f) }
    val flash = remember { Animatable(0f) }
    val still = reduceMotion(context)

    // capabilities: the real ones when the server has the endpoint, else landscape 16:9 at 1080p only
    LaunchedEffect(container) {
        val api = container?.intake ?: return@LaunchedEffect
        composer.applyCapabilities(runCatching { api.capabilities() }.getOrDefault(com.videomk.app.core.Capabilities.FALLBACK))
    }
    LaunchedEffect(composer.focusRequests) { if (composer.focusRequests > 0) { runCatching { focus.requestFocus() }; keyboard?.show() } }
    LaunchedEffect(tip) { if (tip != null) { delay(2500); tip = null } }
    LaunchedEffect(pulse) {
        if (pulse > 0 && !still) {
            flash.snapTo(1f)
            launch { flash.animateTo(0f, tween(450)) }
            for (x in listOf(4f, -4f, 3f, -3f, 0f)) shake.animateTo(x, tween(55))
        }
    }

    val lengths = caps.presets
    val status = ComposerLogic.status(composer.text, options, balance, 0, listening, sending = false, lengths = lengths, createScreen = true, checking = composer.checking)
    val photoTotal = composer.totalPhotos
    val photoHint = PhotoCapacity.hint(photoTotal, options.minutes, lengths).takeIf { status.sendReady }
    val hintFix = PhotoCapacity.suggestion(photoTotal, options.minutes, lengths)

    fun haptic(ok: Boolean) {
        if (Build.VERSION.SDK_INT >= 30) view.performHapticFeedback(if (ok) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.REJECT) else view.performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
    }

    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        composer.dictation.start(composer.text, if (granted) DictationPlan.Permission.Granted else DictationPlan.Permission.Denied)
    }
    fun onMic() {
        try {
            if (composer.dictation.isListening) { composer.dictation.stop(); return }
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) composer.dictation.start(composer.text, DictationPlan.Permission.Granted)
            else micPermission.launch(Manifest.permission.RECORD_AUDIO)
        } catch (e: Exception) { composer.dictation.start(composer.text, DictationPlan.Permission.Denied) }
    }

    /** Sends and waits for generate's answer (the screen stays open and the button busy for that short call). */
    suspend fun send(brief: kotlinx.serialization.json.JsonObject?): com.videomk.app.core.SubmitOutcome {
        val o = composer.options
        val out = composer.peekForSend()
        return app.submitAwait(out.brief, o, out.photos, out.meta, out.libraryIds, brief)
    }
    /** Accepted: the library shows the Making card, Create closes. */
    fun accepted() {
        container?.createPrefs?.save(person, CreatePrefs.of(options))
        haptic(true)
        composer.dismissSheet()
        onClose()
    }

    fun tapCreate() {
        if (composer.checking || composer.submitting) return
        if (status.sendReady) { haptic(true); composer.create(container?.intake, ::send, ::accepted) }
        else {
            haptic(false); pulse++
            view.announceForAccessibility(status.text + (status.fix?.let { ". " + it.description() } ?: ""))
            if (status.kind == StatusKind.TooShort) scope.launch { scroll.animateScrollTo(0); runCatching { focus.requestFocus() }; keyboard?.show() }
        }
    }

    fun applyFix() {
        val fix = status.fix ?: return
        if (fix.addCredits) onOpenWallet() else composer.setLength(fix.minutes!!)
    }

    fun close() { if (composer.submitting) return; if (composer.hasDraft) discard = true else { composer.discardDraft(); onClose() } }
    BackHandler { close() }

    Column(Modifier.fillMaxWidth().background(Vmk.colors.background).statusBarsPadding().windowInsetsPadding(WindowInsets.ime.union(WindowInsets.navigationBars)).testTag("createScreen")) {
        // header
        Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 4.dp)) {
            TextButton(onClick = ::close, modifier = Modifier.align(Alignment.CenterStart).heightIn(min = 48.dp).testTag("createCancel")) { Text("Cancel", style = MaterialTheme.typography.titleMedium, color = Vmk.colors.primary) }
            Text("New video", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, modifier = Modifier.align(Alignment.Center).semantics { heading() })
        }
        Box(Modifier.fillMaxWidth().size(1.dp).background(if (scroll.value > 0) Vmk.colors.outline else Color.Transparent))

        Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            PromptCard(composer, listening, focus, ::onMic)
            dictationHint(dictationState)
            PhotosRow(composer) { composer.openAddPhotos(null) }

            // what is it for
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Overline("What is it for?", Modifier.semantics { heading() })
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.testTag("platformChips")) {
                    items(CreatePlatforms.chips(caps), key = { it.id }) { c ->
                        PlatformChipView(c, selected = c.enabled && c.id == options.platform && !CreatePlatforms.isCustom(options, caps)) {
                            if (c.enabled) composer.selectPlatform(c) else { tip = "Coming soon"; haptic(false) }
                        }
                    }
                }
                tip?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.semantics { contentDescription = it }) }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val rec = CreatePlatforms.recommendation(options, caps)
                    Text(rec, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f).testTag("recommendation"))
                    if (CreatePlatforms.canChangeFormat(caps)) TextButton(onClick = { moreOpen = true }, modifier = Modifier.heightIn(min = 44.dp).testTag("changeFormat")) { Text("Change", fontWeight = FontWeight.Bold) }
                }
                // other formats this platform also accepts: small secondary choices that switch only the format
                val also = CreatePlatforms.alsoWorks(options, caps)
                if (also.isNotEmpty()) FlowRow(Modifier.testTag("alsoWorks"), verticalArrangement = Arrangement.Center, horizontalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Text("Also works:", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                    for (a in also) Text(
                        a.label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary,
                        modifier = Modifier.heightIn(min = 44.dp).clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClickLabel = "Use ${a.label} format") { composer.updateOptions(options.copy(aspect = a.id)) }
                            .padding(horizontal = 8.dp).wrapContentHeight(Alignment.CenterVertically).testTag("alsoWorks-${a.id}"),
                    )
                }
            }

            // length
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Overline("Length", Modifier.semantics { heading() })
                // the presets the server offers, scrolling sideways when there are more than fit
                androidx.compose.foundation.lazy.LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().testTag("lengthChips")) {
                    items(caps.presets) { mi ->
                        LengthChip(mi, Lengths.credits(mi), Math.abs(options.minutes - mi) < 1e-9, balance != null && Lengths.credits(mi) > balance, Modifier.widthIn(min = 78.dp)) { composer.setLength(mi) }
                    }
                }
                CreatePlatforms.overMax(options, caps)?.let { om ->
                    FlowRow(Modifier.fillMaxWidth().testTag("overMaxHint"), itemVerticalAlignment = Alignment.CenterVertically) {
                        Text(om.text + (om.useMinutes?.let { " · " } ?: ""), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                        om.useMinutes?.let { u -> FixChip("Use ${Lengths.short(u)}", "Use ${Lengths.long(u)} instead", Modifier.testTag("overMaxChip")) { composer.setLength(u) } }
                    }
                }
                if (photoHint != null) PhotoHintBlock(photoHint, hintFix, composer, options)
            }

            // more options
            MoreOptions(composer, options, caps, moreOpen, { moreOpen = it }, onLanguage = { languageOpen = true })
            Box(Modifier.size(8.dp))
        }

        // the bar that never goes away
        Surface(color = Vmk.colors.surface, shadowElevation = 6.dp, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(horizontal = 16.dp).padding(top = 6.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                composer.inlineError?.let { m ->
                    Row(Modifier.fillMaxWidth().testTag("createError").semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Assertive }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Filled.Warning, null, tint = Vmk.colors.danger, modifier = Modifier.size(18.dp))
                        Text("$m Tap Create video to try again.", style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.danger)
                    }
                }
                StatusLine(status, flash.value, shake.value, ::applyFix)
                CreateButton(status.sendReady, composer.checking || composer.submitting, options.credits, status.text, status.fix != null, ::tapCreate)
            }
        }
    }

    if (composer.addPhotosRequest != null) AddPhotosSheet(composer, container?.mediaApi, container?.mediaUploads?.arrivals, startOnMyMedia = composer.addPhotosRequest?.tab == 1, onDismiss = { composer.closeAddPhotos() })
    CreateSheetsHost(composer, balance, options, onSubmitEdit = {}, onWallet = onOpenWallet)
    if (languageOpen) LanguageDialog(composer, options, caps) { languageOpen = false }
    if (discard) AlertDialog(
        onDismissRequest = { discard = false }, title = { Text("Discard this video?") }, text = { Text("What you entered will be lost.") },
        confirmButton = { TextButton(onClick = { discard = false; composer.discardDraft(); onClose() }, modifier = Modifier.heightIn(min = 48.dp).testTag("discardConfirm")) { Text("Discard", color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = { discard = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Keep editing") } },
    )
}

@Composable
private fun PromptCard(composer: ComposerViewModel, listening: Boolean, focus: FocusRequester, onMic: () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    Box(Modifier.fillMaxWidth().heightIn(min = 112.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)) {
        BasicTextField(
            value = composer.text, onValueChange = { composer.text = it }, readOnly = listening,
            textStyle = MaterialTheme.typography.bodyLarge.copy(fontSize = 19.sp, lineHeight = 26.sp, color = if (listening) Vmk.colors.textSecondary else Vmk.colors.text),
            cursorBrush = SolidColor(Vmk.colors.primary), keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            modifier = Modifier.fillMaxWidth().focusRequester(focus).padding(start = 18.dp, end = 18.dp, top = 16.dp, bottom = 64.dp).testTag("composerField"),
            decorationBox = { inner ->
                Box { if (composer.text.isEmpty()) Text("Describe your video. For example: how bees make honey, explained for kids.", style = MaterialTheme.typography.bodyLarge.copy(fontSize = 19.sp, lineHeight = 26.sp), color = Vmk.colors.textTertiary); inner() }
            },
        )
        Row(Modifier.align(Alignment.BottomEnd).padding(10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (composer.text.isEmpty() && !listening) Text("Tap the mic to speak", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textTertiary)
            if (listening) Text("Listening…", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger)
            Box(
                Modifier.size(44.dp).clip(CircleShape).background(if (listening) Vmk.colors.danger else Vmk.colors.surfaceRaised)
                    .clickable(role = Role.Button, onClickLabel = if (listening) "Stop dictation" else "Dictate", onClick = onMic)
                    .semantics { contentDescription = if (listening) "Stop dictation" else "Dictate. Say what video you want instead of typing" }.testTag("micButton"),
                contentAlignment = Alignment.Center,
            ) { Icon(if (listening) Icons.Filled.Stop else Icons.Filled.Mic, null, tint = if (listening) Color.White else Vmk.colors.text, modifier = Modifier.size(22.dp)) }
        }
    }
}

/** One row for photos: "Add photos" with the optional line, or, once chosen, the count with Edit and a strip of four thumbnails. */
@Composable
private fun PhotosRow(composer: ComposerViewModel, onOpen: () -> Unit) {
    val shape = RoundedCornerShape(20.dp)
    val total = composer.totalPhotos
    Row(
        Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
            .clickable(role = Role.Button, onClickLabel = "Add photos", onClick = onOpen).padding(horizontal = 12.dp, vertical = 8.dp)
            .semantics(mergeDescendants = true) { contentDescription = if (total > 0) "Add photos. $total selected" else "Add photos. Optional, from this phone or My media" }.testTag("photoButton"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (total == 0) {
            Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(Icons.Filled.AddPhotoAlternate, null, tint = Vmk.colors.primary) }
            Column(Modifier.weight(1f)) {
                Text("Add photos", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
                Text("Optional · from this phone or My media", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
            }
            Icon(Icons.Filled.ChevronRight, null, tint = Vmk.colors.textSecondary)
        } else {
            Column(Modifier.weight(1f)) {
                Text("$total photo${plural(total)}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.testTag("photosNote"))
                if (composer.loading > 0) Text(composer.preparingText, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("photosPreparing"))
                composer.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.testTag("photosNotice")) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                val thumbs = composer.photos.take(4).map { it.thumbnail } + composer.library.take(4).map { null }
                composer.photos.take(4).forEach { p -> p.thumbnail?.let { androidx.compose.foundation.Image(it.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)).testTag("attachedPhoto")) } }
                if (composer.photos.size < 4) composer.library.take(4 - composer.photos.size).forEach { PhotoThumb(it, Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)).testTag("attachedLibraryPhoto")) }
                if (total > 4) Text("+${total - 4}", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 4.dp))
            }
            Text("Edit", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.primary)
        }
    }
}

@Composable
private fun PlatformChipView(c: PlatformChip, selected: Boolean, onClick: () -> Unit) {
    val shape = CircleShape
    Row(
        Modifier.heightIn(min = 44.dp).alpha(if (c.enabled) 1f else 0.62f).clip(shape)
            .background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surface)
            .border(if (selected) 1.5.dp else 1.dp, if (selected) Vmk.colors.primary else Vmk.colors.outline, shape)
            .clickable(role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 14.dp)
            .semantics { this.selected = selected; contentDescription = if (c.enabled) c.label else "${c.label}, coming soon, dimmed" }.testTag("platform-${c.id}"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(if (selected) Icons.Filled.Check else if (c.id == "other") Icons.Filled.AutoAwesome else if (c.aspect == "16:9") Icons.Filled.CropLandscape else if (c.aspect == "1:1") Icons.Filled.CropSquare else Icons.Filled.CropPortrait, null, tint = if (selected) Vmk.colors.primary else Vmk.colors.text, modifier = Modifier.size(18.dp))
        Text(c.label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = if (selected) Vmk.colors.primary else Vmk.colors.text, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.MiddleEllipsis)
        if (!c.enabled) Text("Soon", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.textSecondary, modifier = Modifier.clip(CircleShape).background(Vmk.colors.surfaceRaised).padding(horizontal = 6.dp, vertical = 2.dp))
    }
}

@Composable
private fun LengthChip(minutes: Double, credits: Int, selected: Boolean, overBalance: Boolean, modifier: Modifier, onClick: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    val tint = if (overBalance) Vmk.colors.warning else if (selected) Vmk.colors.primary else Vmk.colors.textSecondary
    Column(
        modifier.heightIn(min = 58.dp).clip(shape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised)
            .then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, shape) else Modifier)
            .clickable(role = Role.RadioButton, onClick = onClick)
            .semantics { this.selected = selected; contentDescription = "${Lengths.long(minutes)}, $credits credit${plural(credits)}${if (selected) ", selected" else ""}" }
            .testTag("length-${if (minutes == Math.floor(minutes)) minutes.toInt().toString() else minutes.toString()}").padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        Text(Lengths.short(minutes), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = if (selected) Vmk.colors.primary else Vmk.colors.text, maxLines = 1)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Bolt, null, tint = tint, modifier = Modifier.size(13.dp))
            Text("$credits", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = tint)
        }
    }
}

@Composable
private fun PhotoHintBlock(hint: String, fix: Double?, composer: ComposerViewModel, options: CreateOptions) {
    Column(Modifier.fillMaxWidth().padding(top = 2.dp)) {
        Text(hint, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, color = Vmk.colors.text, modifier = Modifier.testTag("photoCapacityHint"))
        if (fix != null) {
            val label = "Use ${Lengths.short(fix)} · ⚡${Lengths.credits(fix)}"
            FixChip(label, "Use ${Lengths.long(fix)} instead, ${Lengths.credits(fix)} credits", Modifier.testTag("photoFixChip")) { composer.setLength(fix) }
        }
    }
}

@Composable
private fun MoreOptions(composer: ComposerViewModel, o: CreateOptions, caps: com.videomk.app.core.Capabilities, open: Boolean, onOpen: (Boolean) -> Unit, onLanguage: () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    Column(Modifier.fillMaxWidth().clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClickLabel = if (open) "Collapse more options" else "Expand more options") { onOpen(!open) }
                .padding(horizontal = 16.dp, vertical = 8.dp).semantics(mergeDescendants = true) { stateDescription = if (open) "expanded" else "collapsed" }.testTag("optionsMenu"),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text("More options", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
                if (!open) Text(CreatePlatforms.moreSummary(o, caps), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            }
            Icon(if (open) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null, tint = Vmk.colors.text)
        }
        if (open) Column(Modifier.fillMaxWidth()) {
            Box(Modifier.fillMaxWidth().size(1.dp).background(Vmk.colors.outline))
            Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Overline("Look")
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LookSwatch("Auto", "Producer decides", null, o.look == null, Modifier.weight(1f).testTag("look-auto")) { composer.updateOptions(o.copy(look = null)) }
                    for (l in VideoLook.entries) LookSwatch(l.title, l.title, l, o.look == l, Modifier.weight(1f).testTag("look-${l.wire}")) { composer.updateOptions(o.copy(look = l)) }
                }
            }
            Box(Modifier.fillMaxWidth().size(1.dp).background(Vmk.colors.outline))
            Row(
                Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Switch, onClickLabel = "Subtitles") { composer.updateOptions(o.copy(captions = !o.captions)) }.padding(horizontal = 16.dp)
                    .semantics(mergeDescendants = true) { stateDescription = if (o.captions) "on" else "off" }.testTag("subtitlesRow"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Icon(Icons.Filled.ClosedCaption, null, tint = Vmk.colors.text)
                Text("Subtitles", style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f))
                Switch(checked = o.captions, onCheckedChange = null, colors = SwitchDefaults.colors(checkedTrackColor = Vmk.colors.gradientStart, checkedThumbColor = Color.White, uncheckedTrackColor = Vmk.colors.surface3, uncheckedBorderColor = Vmk.colors.outline))
            }
            Box(Modifier.fillMaxWidth().padding(horizontal = 16.dp).size(1.dp).background(Vmk.colors.outline))
            Row(
                Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClickLabel = "Choose the narration language", onClick = onLanguage).padding(horizontal = 16.dp).testTag("languageRow"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Icon(Icons.Filled.Language, null, tint = Vmk.colors.text)
                Text("Language", style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text)
                Text(CreatePlatforms.languageLabel(o, caps), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f), maxLines = 1, textAlign = androidx.compose.ui.text.style.TextAlign.End, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                Icon(Icons.Filled.ChevronRight, null, tint = Vmk.colors.textSecondary)
            }
            Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Overline("Format")
                val bigText = LocalDensity.current.fontScale >= 1.3f
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), maxItemsInEachRow = if (bigText) 2 else 4) {
                    for (id in listOf("16:9", "9:16", "1:1", "4:5")) {
                        val a = caps.aspect(id)
                        FormatTile(id, a?.label ?: when (id) { "16:9" -> "Landscape"; "9:16" -> "Vertical"; "1:1" -> "Square"; else -> "Portrait" }, ready = a?.ready == true, beta = a?.beta == true, selected = o.aspect == id, Modifier.weight(1f), tall = bigText) {
                            composer.updateOptions(o.copy(aspect = id))
                        }
                    }
                }
                Segmented(listOf("720p", "1080p"), o.resolution, enabled = { id -> caps.resolutions.any { it.id == id } }) { composer.updateOptions(o.copy(resolution = it)) }
            }
        }
    }
}

@Composable
private fun FormatTile(id: String, label: String, ready: Boolean, beta: Boolean, selected: Boolean, modifier: Modifier, tall: Boolean = false, onClick: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    Box(
        modifier.then(if (tall) Modifier.heightIn(min = 110.dp) else Modifier.aspectRatio(1f)).alpha(if (ready) 1f else 0.6f).clip(shape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised)
            .then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, shape) else Modifier)
            .clickable(enabled = ready, role = Role.RadioButton, onClick = onClick)
            .semantics { this.selected = selected; contentDescription = "$label $id${if (!ready) ", coming soon" else if (beta) ", beta" else ""}" }.testTag("format-$id"),
    ) {
        if (!ready || beta) Text(if (ready) "Beta" else "Soon", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.textSecondary, modifier = Modifier.align(Alignment.TopEnd).padding(6.dp))
        Column(Modifier.align(Alignment.Center).padding(horizontal = 6.dp, vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(if (id == "16:9") Icons.Filled.CropLandscape else if (id == "1:1") Icons.Filled.CropSquare else Icons.Filled.CropPortrait, null, tint = if (selected) Vmk.colors.primary else Vmk.colors.textSecondary, modifier = Modifier.size(26.dp))
            Text("$label\n$id", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold, color = if (selected) Vmk.colors.primary else Vmk.colors.textSecondary, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
    }
}

@Composable
private fun Segmented(ids: List<String>, selected: String, enabled: (String) -> Boolean, onSelect: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised).padding(3.dp)) {
        for (id in ids) {
            val sel = id == selected; val on = enabled(id)
            Box(
                Modifier.weight(1f).heightIn(min = 38.dp).alpha(if (on) 1f else 0.5f).clip(RoundedCornerShape(10.dp)).then(if (sel) Modifier.background(if (Vmk.colors.dark) Vmk.colors.surface3 else Vmk.colors.surface) else Modifier)
                    .clickable(enabled = on, role = Role.RadioButton) { onSelect(id) }.semantics { this.selected = sel }.testTag("resolution-$id"),
                contentAlignment = Alignment.Center,
            ) { Text(id, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = if (sel) Vmk.colors.text else Vmk.colors.textSecondary) }
        }
    }
}

/** Create: 54 dp, full width, never absent. Filled when it can act, tonal when it cannot; a spinner while the request is being checked. */
@Composable
private fun CreateButton(ready: Boolean, checking: Boolean, credits: Int, reason: String, hasFix: Boolean, onClick: () -> Unit) {
    val shape = CircleShape
    Box(
        Modifier.fillMaxWidth().heightIn(min = 54.dp).clip(shape).then(if (ready || checking) Modifier.background(Vmk.gradientNow) else Modifier.background(Vmk.colors.surface3))
            .clickable(role = Role.Button, onClickLabel = if (ready) "Create video" else "Explain why this can't be created yet", onClick = onClick)
            .semantics { contentDescription = "Create video"; stateDescription = if (checking) "Checking your request" else if (ready) "Ready, costs $credits credit${plural(credits)}" else "Not ready. $reason${if (hasFix) ". Double tap for the fix." else ""}" }.testTag("sendButton"),
        contentAlignment = Alignment.Center,
    ) {
        val c = if (ready || checking) Color.White else Vmk.colors.textTertiary
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (checking) CircularProgressIndicator(Modifier.size(20.dp), color = Color.White, strokeWidth = 2.dp)
            Text("Create video", style = MaterialTheme.typography.titleMedium.copy(fontSize = 19.sp), fontWeight = FontWeight.Bold, color = c)
            Text("·", color = c)
            Icon(Icons.Filled.Bolt, null, tint = c, modifier = Modifier.size(20.dp))
            Text("$credits", style = MaterialTheme.typography.titleMedium.copy(fontSize = 19.sp), fontWeight = FontWeight.Bold, color = c)
        }
    }
}

@Composable
private fun LanguageDialog(composer: ComposerViewModel, o: CreateOptions, caps: com.videomk.app.core.Capabilities, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text("Narration language") },
        text = {
            Column {
                val rows = listOf("auto" to "Same as my description") + caps.languages.map { it.id to it.label }
                for ((id, label) in rows) {
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = Role.RadioButton) { composer.updateOptions(o.copy(language = id)); onDismiss() }.padding(vertical = 4.dp).testTag("language-$id"),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        androidx.compose.material3.RadioButton(selected = o.language == id, onClick = null)
                        Text(label, color = Vmk.colors.text)
                    }
                }
            }
        },
        confirmButton = {}, dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
    )
}
