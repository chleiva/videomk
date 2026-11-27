package com.videomk.app.ui

import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Timer
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Add
import com.videomk.app.core.AddPhotosLogic
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
import com.videomk.app.core.CreateSubmit
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.foundation.layout.fillMaxSize
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
import com.videomk.app.R
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.core.displayName
import com.videomk.app.core.Brief
import com.videomk.app.core.ComposerLogic
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.CreatePlatforms
import com.videomk.app.core.CreatePrefs
import com.videomk.app.core.DeckState
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.PhotoCapacity
import com.videomk.app.core.Lengths
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Spacer
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.PlatformChip
import com.videomk.app.core.StatusKind
import com.videomk.app.core.VideoLook
import com.videomk.app.data.DictationController
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable private fun statusAnnouncement(status: com.videomk.app.core.ComposerStatus): String = status.text + (status.fix?.let { ". " + it.description() } ?: "")

/**
 * The Create screen (docs/UI_DESIGN.md section o): a deterministic form with a Create button that is always visible. Prompt with dictation, Add photos (the unified
 * sheet), "What is it for?", length with prices, collapsed More options, and a bottom bar with the status line and "Create video · ⚡N".
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CreateScreen(app: AppViewModel, composer: ComposerViewModel, onClose: () -> Unit, onOpenWallet: () -> Unit, onSent: () -> Unit = onClose) {
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
    var costInfo by remember { mutableStateOf(false) }
    var tip by remember { mutableStateOf<String?>(null) }
    var pulse by remember { mutableIntStateOf(0) }
    var confirmDeck by rememberSaveable { mutableStateOf(false) }   // photos exist: ask before a presentation replaces them
    val deckState = composer.deckState
    val shake = remember { Animatable(0f) }
    val flash = remember { Animatable(0f) }
    val still = reduceMotion(context)

    // capabilities: the real ones when the server has the endpoint, else landscape 16:9 at 1080p only
    val localeTag = com.videomk.app.core.Txt.localeTag   // a language change refetches: the server's labels and notes come back in the new language
    LaunchedEffect(container, localeTag) {
        val api = container?.intake ?: return@LaunchedEffect
        composer.applyCapabilities(runCatching { api.capabilities() }.getOrDefault(com.videomk.app.core.Capabilities.FALLBACK))
    }
    composer.attachDeckApi(container?.deckApi, container?.deckUploader)
    // the system document picker: its one-time read grant is used at once and never kept (no persistable permission)
    val docPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) composer.addDeck(com.videomk.app.data.DeckPicker.pickOf(context.contentResolver, uri), replacePhotos = true)
    }
    fun launchDeckPicker() { val types = caps.deck?.mimeTypes ?: return; if (types.isNotEmpty()) docPicker.launch(types) }
    fun addDeck() { if (composer.totalPhotos > 0) confirmDeck = true else launchDeckPicker() }
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
    val status = ComposerLogic.status(composer.text, options, balance, 0, listening, sending = false, lengths = lengths, createScreen = true, checking = composer.checking, deck = deckState.takeIf { it.attached })
    val announcement = statusAnnouncement(status)
    val photoTotal = composer.totalPhotos
    val comingSoonText = stringResource(R.string.create_coming_soon)
    val photoHint = PhotoCapacity.hint(photoTotal, options.minutes, lengths).takeIf { status.sendReady }
    val hintFix = PhotoCapacity.suggestion(photoTotal, options.minutes, lengths)

    // between the tap and the answer the form is locked (CreateSubmit): the close icon cancels the request check; during the send itself it waits for the answer
    val phase = CreateSubmit.phase(composer.checking, composer.submitting)
    val locked = CreateSubmit.locked(phase)
    val phaseText = when (phase) { CreateSubmit.Phase.Checking -> stringResource(R.string.create_phase_checking); CreateSubmit.Phase.Starting -> stringResource(R.string.create_phase_starting); else -> null }
    val focusManager = androidx.compose.ui.platform.LocalFocusManager.current
    LaunchedEffect(phase) {
        if (phaseText != null) { focusManager.clearFocus(); keyboard?.hide(); view.announceForAccessibility(phaseText) }
    }
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
        return app.submitAwait(out.brief, o, out.photos, out.meta, out.libraryIds, brief, out.deckId, out.deckTitle)
    }
    /** Accepted: the library shows the Making card, Create closes. */
    fun accepted() {
        container?.createPrefs?.save(person, CreatePrefs.of(options))
        haptic(true)
        composer.dismissSheet()
        onSent()   // the new video is on the Videos tab as a Making card
    }

    fun tapCreate() {
        if (!CreateSubmit.tapAllowed(phase)) return
        if (status.sendReady) { haptic(true); composer.create(container?.intake, ::send, ::accepted) }
        else {
            haptic(false); pulse++
            view.announceForAccessibility(announcement)
            if (status.kind == StatusKind.TooShort) scope.launch { scroll.animateScrollTo(0); runCatching { focus.requestFocus() }; keyboard?.show() }
        }
    }

    fun applyFix() {
        val fix = status.fix ?: return
        if (fix.addCredits) onOpenWallet() else composer.setLength(fix.minutes!!)
    }

    // back is never destructive: a draft that is only photos picked in My media just closes (they stay attached, and Media keeps its selection); anything typed asks first
    fun close() {
        if (CreateSubmit.closeIsBlocked(phase)) { view.announceForAccessibility(phaseText.orEmpty()); return }
        if (CreateSubmit.closeCancelsCheck(phase)) { composer.dismissSheet(); return }
        val onlyLibraryPhotos = composer.text.isBlank() && composer.photos.isEmpty() && composer.loading == 0 && !composer.deckState.attached
        if (composer.hasDraft && !onlyLibraryPhotos) discard = true else if (onlyLibraryPhotos && composer.library.isNotEmpty()) onClose() else { composer.discardDraft(); onClose() }
    }
    BackHandler { close() }

    var forOpen by remember { mutableStateOf(false) }
    var lengthOpen by remember { mutableStateOf(false) }
    var lookOpen by remember { mutableStateOf(false) }
    var optionsOpen by rememberSaveable { mutableStateOf(false) }

    Column(Modifier.fillMaxWidth().background(Vmk.colors.background).statusBarsPadding().windowInsetsPadding(WindowInsets.ime.union(WindowInsets.navigationBars)).testTag("createScreen")) {
        // the sheet is the title: only a close button (docs/UX_2026_REDESIGN.md 4.2)
        Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            GlassIconButton(Icons.Filled.Close, stringResource(R.string.common_close), ::close, Modifier.testTag("createCancel"))
        }
        Box(Modifier.fillMaxWidth().size(1.dp).background(if (scroll.value > 0) Vmk.colors.outline else Color.Transparent))

        Column(Modifier.weight(1f).then(if (locked) Modifier.alpha(0.5f).lockTouches() else Modifier).verticalScroll(scroll).padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            PromptField(composer, listening, focus, deck = deckState.attached)
            // photo and mic: two icons under the prompt; the count is a badge, "Tap the mic to speak" is gone (the mic icon is universal)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                if (!deckState.attached) GlassIconButton(Icons.Filled.AddPhotoAlternate, stringResource(R.string.create_add_photos), { composer.openAddPhotos(null) }, Modifier.testTag("photoButton"), badge = AddPhotosLogic.badge(photoTotal))
                GlassIconButton(if (listening) Icons.Filled.Stop else Icons.Filled.Mic, stringResource(if (listening) R.string.create_stop_dictation else R.string.create_dictate_desc), ::onMic, Modifier.testTag("micButton"), filled = listening)
                if (listening) Text(stringResource(R.string.composer_listening), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger)
            }
            dictationHint(dictationState)
            if (deckState.attached) DeckCard(
                deckState, caps.deck, onRemove = { composer.removeDeck() }, onPickAgain = { composer.removeDeck(); launchDeckPicker() }, onRetry = { composer.deck.retry() }, onKeepWaiting = { composer.deck.keepWaiting() },
            ) else if (photoTotal > 0) PhotoStrip(composer) { composer.openAddPhotos(null) }

            // three pills (For, Length, Look) and one icon for Options; each pill shows its value, so the state is the label
            val chips = remember(caps) { CreatePlatforms.chips(caps).filter { it.enabled } }
            val forDesc = stringResource(R.string.create_what_for)
            val lengthDesc = stringResource(R.string.create_length)
            val lookDesc = stringResource(R.string.create_look)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.Center, itemVerticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().testTag("pills")) {
                Pill(platformPillValue(options, caps), forDesc, Modifier.testTag("pillFor"), expanded = forOpen, onExpandedChange = { forOpen = it }) {
                    for (c in chips) androidx.compose.material3.DropdownMenuItem(
                        text = { Text(c.label, fontWeight = if (c.id == options.platform && !CreatePlatforms.isCustom(options, caps)) FontWeight.Bold else FontWeight.Normal) },
                        trailingIcon = { if (c.id == options.platform && !CreatePlatforms.isCustom(options, caps)) Icon(Icons.Filled.Check, null, tint = Vmk.colors.primary) },
                        onClick = { forOpen = false; composer.selectPlatform(c) }, modifier = Modifier.testTag("platform-${c.id}"),
                    )
                }
                val maxMinutes = CreatePlatforms.chip(caps, options.platform)?.takeIf { it.enabled }?.maxMinutes
                Pill(if (options.useSuggestedLength && deckState is DeckState.Ready) stringResource(R.string.deck_suggested) else Lengths.short(options.minutes), lengthDesc, Modifier.testTag("pillLength"), Icons.Filled.Timer, expanded = lengthOpen, onExpandedChange = { lengthOpen = it }) {
                    (deckState as? DeckState.Ready)?.let { ready ->
                        LengthMenuRow(stringResource(R.string.deck_suggested) + " · " + Lengths.short(ready.info.suggestedMinutes), ready.info.suggestedCredits, options.useSuggestedLength, balance != null && ready.info.suggestedCredits > balance, true, "length-suggested") { lengthOpen = false; composer.useSuggestedLength() }
                    }
                    var anyOver = false
                    for (mi in caps.presets) {
                        val over = maxMinutes != null && mi > maxMinutes + 1e-9
                        if (over) anyOver = true
                        LengthMenuRow(Lengths.short(mi), Lengths.credits(mi), !options.useSuggestedLength && Math.abs(options.minutes - mi) < 1e-9, balance != null && Lengths.credits(mi) > balance, !over, "length-${if (mi == Math.floor(mi)) mi.toInt().toString() else mi.toString()}") { lengthOpen = false; composer.setLength(mi) }
                    }
                    if (anyOver && maxMinutes != null) Text(stringResource(R.string.create_over_max, CreatePlatforms.chip(caps, options.platform)!!.label, Lengths.clock(maxMinutes)), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp).widthIn(max = 240.dp))
                }
                Pill(options.look?.displayName() ?: stringResource(R.string.create_look_auto), lookDesc, Modifier.testTag("pillLook"), Icons.Filled.AutoAwesome, expanded = lookOpen, onExpandedChange = { lookOpen = it }) {
                    for (l in listOf<VideoLook?>(null) + VideoLook.entries) androidx.compose.material3.DropdownMenuItem(
                        text = { Text(l?.displayName() ?: stringResource(R.string.create_look_auto), fontWeight = if (options.look == l) FontWeight.Bold else FontWeight.Normal) },
                        trailingIcon = { if (options.look == l) Icon(Icons.Filled.Check, null, tint = Vmk.colors.primary) },
                        onClick = { lookOpen = false; composer.updateOptions(options.copy(look = l)) }, modifier = Modifier.testTag("look-${l?.wire ?: "auto"}"),
                    )
                }
                GlassIconButton(Icons.Filled.Tune, stringResource(R.string.create_options), { optionsOpen = true }, Modifier.testTag("optionsMenu"))
            }
            tip?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.semantics { contentDescription = it }) }
            // only when there is something to say: slides are wide, a platform's limit, what the photos can fill
            if (composer.deckVerticalWarning) Column(Modifier.fillMaxWidth().testTag("deckVerticalWarning")) {
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.Filled.Warning, null, tint = Vmk.colors.warning, modifier = Modifier.size(18.dp).padding(top = 2.dp))
                    Text(stringResource(R.string.deck_vertical_warning), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text)
                }
                FixChip(stringResource(R.string.deck_use_landscape), stringResource(R.string.deck_use_landscape_desc), Modifier.testTag("deckUseLandscape")) { composer.useLandscape() }
            }
            CreatePlatforms.overMax(options, caps)?.let { om ->
                FlowRow(Modifier.fillMaxWidth().testTag("overMaxHint"), itemVerticalAlignment = Alignment.CenterVertically) {
                    Text(om.text + (om.useMinutes?.let { " · " } ?: ""), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                    om.useMinutes?.let { u -> FixChip(stringResource(R.string.create_over_max_use, Lengths.short(u)), stringResource(R.string.create_over_max_use_desc, Lengths.long(u)), Modifier.testTag("overMaxChip")) { composer.setLength(u) } }
                }
            }
            if (photoHint != null) PhotoHintBlock(photoHint, hintFix, composer, options)
            Box(Modifier.size(8.dp))
        }

        // the bar that never goes away: Create (one primary action) and one caption, only when it says something
        Surface(color = Vmk.colors.background, modifier = Modifier.fillMaxWidth().then(if (locked) Modifier.lockTouches() else Modifier)) {
            Column(Modifier.padding(horizontal = 20.dp).padding(top = 6.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                composer.inlineError?.let { m ->
                    Row(Modifier.fillMaxWidth().testTag("createError").semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Assertive }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Filled.Warning, null, tint = Vmk.colors.danger, modifier = Modifier.size(18.dp))
                        Text(stringResource(R.string.create_error_retry, m), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.danger)
                    }
                }
                CreateButton(status.sendReady, phaseText, options.credits, status.text, status.fix != null, ::tapCreate)
                if (status.kind == StatusKind.Ready || status.kind == StatusKind.PhotoHint) {
                    if (balance != null) Text(pluralStringResource(R.plurals.create_credits_left, balance, balance), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.fillMaxWidth().testTag("costLine"))
                } else if (phaseText == null) StatusLine(status, flash.value, shake.value, ::applyFix)   // while locked the button itself says what is happening: no second copy of the line
            }
        }
    }

    if (optionsOpen) CreateOptionsSheet(composer, caps, options, onLanguage = { languageOpen = true }, onCostInfo = { costInfo = true }, onDismiss = { optionsOpen = false })

    if (composer.addPhotosRequest != null) AddPhotosSheet(
        composer, container?.mediaApi, container?.mediaUploads?.arrivals, startOnMyMedia = composer.addPhotosRequest?.tab == 1, onDismiss = { composer.closeAddPhotos() },
        onAddDeck = if (caps.deck != null) ({ addDeck() }) else null,
    )
    if (confirmDeck) AlertDialog(
        onDismissRequest = { confirmDeck = false }, title = { Text(stringResource(R.string.deck_replace_photos_title)) }, text = { Text(stringResource(R.string.deck_replace_photos_text)) },
        confirmButton = { TextButton(onClick = { confirmDeck = false; launchDeckPicker() }, modifier = Modifier.heightIn(min = 48.dp).testTag("deckReplaceConfirm")) { Text(stringResource(R.string.deck_replace_photos_confirm)) } },
        dismissButton = { TextButton(onClick = { confirmDeck = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.deck_replace_photos_keep)) } },
    )
    CreateSheetsHost(composer, balance, options, onSubmitEdit = {}, onWallet = onOpenWallet)
    if (costInfo) CostSheet(fourK = caps.resolutions.any { it.id.lowercase() == "4k" || it.id.lowercase() == "2160p" }) { costInfo = false }
    if (languageOpen) LanguageDialog(composer, options, caps) { languageOpen = false }
    if (discard) AlertDialog(
        onDismissRequest = { discard = false }, title = { Text(stringResource(R.string.create_discard_title)) }, text = { Text(stringResource(R.string.create_discard_text)) },
        confirmButton = { TextButton(onClick = { discard = false; composer.discardDraft(); onClose() }, modifier = Modifier.heightIn(min = 48.dp).testTag("discardConfirm")) { Text(stringResource(R.string.create_discard), color = Vmk.colors.danger) } },
        dismissButton = { TextButton(onClick = { discard = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.create_keep_editing)) } },
    )
}

@Composable
internal fun PlatformChipView(c: PlatformChip, selected: Boolean, onClick: () -> Unit) {
    val shape = CircleShape
    val chipDescription = if (c.enabled) c.label else stringResource(R.string.create_chip_soon_desc, c.label)
    Row(
        Modifier.heightIn(min = Vmk.minTouch).alpha(if (c.enabled) 1f else 0.62f).clip(shape)
            .background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surface)
            .border(if (selected) 1.5.dp else 1.dp, if (selected) Vmk.colors.primary else Vmk.colors.outline, shape)
            .clickable(role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 6.dp)
            .semantics { this.selected = selected; contentDescription = chipDescription }.testTag("platform-${c.id}"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(if (selected) Icons.Filled.Check else if (c.id == "other") Icons.Filled.AutoAwesome else if (c.aspect == "16:9") Icons.Filled.CropLandscape else if (c.aspect == "1:1") Icons.Filled.CropSquare else Icons.Filled.CropPortrait, null, tint = if (selected) Vmk.colors.primary else Vmk.colors.text, modifier = Modifier.size(18.dp))
        Text(c.label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = if (selected) Vmk.colors.primary else Vmk.colors.text, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
        if (!c.enabled) Text(stringResource(R.string.create_soon), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.textSecondary, modifier = Modifier.clip(CircleShape).background(Vmk.colors.surfaceRaised).padding(horizontal = 6.dp, vertical = 2.dp))
    }
}

@Composable
private fun PhotoHintBlock(hint: String, fix: Double?, composer: ComposerViewModel, options: CreateOptions) {
    Column(Modifier.fillMaxWidth().padding(top = 2.dp)) {
        Text(hint, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, color = Vmk.colors.text, modifier = Modifier.testTag("photoCapacityHint"))
        if (fix != null) {
            val f = com.videomk.app.core.StatusFix(fix)
            FixChip(f.label(), f.description(), Modifier.testTag("photoFixChip")) { composer.setLength(fix) }
        }
    }
}

/** Create: 54 dp, full width, never absent. Filled when it can act, tonal when it cannot; a spinner while the request is being checked. */
@Composable
private fun CreateButton(ready: Boolean, busyText: String?, credits: Int, reason: String, hasFix: Boolean, onClick: () -> Unit) {
    val shape = CircleShape
    val createLabel = stringResource(R.string.create_create_video)
    val busy = busyText != null
    val boxState = if (busy) busyText!!
        else if (ready) pluralStringResource(R.plurals.create_state_ready, credits, credits)
        else stringResource(if (hasFix) R.string.create_state_not_ready_fix else R.string.create_state_not_ready, reason)
    Box(
        Modifier.fillMaxWidth().heightIn(min = 54.dp).clip(shape).then(if (ready || busy) Modifier.background(Vmk.gradientNow) else Modifier.background(Vmk.colors.surface3))
            .clickable(enabled = !busy, role = Role.Button, onClickLabel = if (ready) createLabel else stringResource(R.string.create_explain_not_ready), onClick = onClick)
            .semantics { contentDescription = if (busy) busyText!! else createLabel; stateDescription = boxState }.testTag("sendButton"),
        contentAlignment = Alignment.Center,
    ) {
        val c = if (ready || busy) Vmk.colors.onPrimary else Vmk.colors.textSecondary
        Row(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (busy) {
                // locked: a spinner and one honest line, no price
                CircularProgressIndicator(Modifier.size(20.dp), color = c, strokeWidth = 2.dp)
                Text(busyText!!, style = VmkType.cta, color = c, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.weight(1f, fill = false).testTag("sendBusyText"))
            } else {
                // the label may wrap (Spanish, large text); the price stays together
                Text(createLabel, style = VmkType.cta, color = c, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.weight(1f, fill = false))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("·", style = VmkType.cta, color = c, modifier = Modifier.padding(end = 8.dp))
                    Icon(Icons.Filled.Bolt, null, tint = c, modifier = Modifier.size(20.dp))
                    Text("$credits", style = VmkType.cta, color = c)
                }
            }
        }
    }
}

/** Swallows every touch on this part of the screen (the form while a request is running). */
private fun Modifier.lockTouches(): Modifier = this.pointerInput(Unit) {
    awaitPointerEventScope { while (true) { awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() } } }
}

@Composable
private fun LanguageDialog(composer: ComposerViewModel, o: CreateOptions, caps: com.videomk.app.core.Capabilities, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss, title = { Text(stringResource(R.string.create_narration_language)) },
        text = {
            Column {
                val rows = listOf("auto" to stringResource(R.string.create_same_as_description)) + caps.languages.map { it.id to it.label }
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
        confirmButton = {}, dismissButton = { TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_cancel)) } },
    )
}


/** The prompt: large borderless text on the page (no card, no outline); the short hint is the only words around it. */
@Composable
private fun PromptField(composer: ComposerViewModel, listening: Boolean, focus: FocusRequester, deck: Boolean = false) {
    BasicTextField(
        value = composer.text, onValueChange = { composer.text = it }, readOnly = listening,
        textStyle = VmkType.prompt.copy(color = if (listening) Vmk.colors.textSecondary else Vmk.colors.text),
        cursorBrush = SolidColor(Vmk.colors.primary), keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
        modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp).focusRequester(focus).padding(top = 8.dp).testTag("composerField"),
        decorationBox = { inner ->
            Box { if (composer.text.isEmpty()) Text(stringResource(if (deck) R.string.deck_prompt_hint else R.string.create_prompt_hint), style = VmkType.prompt, color = Vmk.colors.textTertiary); inner() }
        },
    )
}

/** What is attached: one row of 56 dp thumbnails, "+" at the end (it opens the photo sheet again). */
@Composable
private fun PhotoStrip(composer: ComposerViewModel, onAdd: () -> Unit) {
    val total = composer.totalPhotos
    // copy the live lists once, here: the lazy row reads them later, after the picker may already have changed them
    val stripPhotos = composer.photos.toList().take(12)
    val stripLibrary = composer.library.toList().distinctBy { it.id }.take(12 - stripPhotos.size)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        androidx.compose.foundation.lazy.LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth().testTag("photoStrip")) {
            items(stripPhotos.size) { i ->
                val photo = stripPhotos[i]
                photo.thumbnail?.let { bmp -> RemovableThumb({ composer.removePhoto(photo.id) }) { androidx.compose.foundation.Image(bmp.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize().testTag("attachedPhoto")) } }
            }
            items(stripLibrary.size) { i ->
                val photo = stripLibrary[i]
                RemovableThumb({ composer.removeLibrary(photo.id) }) { PhotoThumb(photo, Modifier.fillMaxSize().testTag("attachedLibraryPhoto")) }
            }
            item {
                val add = stringResource(R.string.create_add_photos)
                Box(Modifier.size(64.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised).clickable(role = Role.Button, onClickLabel = add, onClick = onAdd).semantics { contentDescription = add }, contentAlignment = Alignment.Center) {
                    Icon(Icons.Filled.AddPhotoAlternate, null, tint = Vmk.colors.primary)
                }
            }
        }
        // only when something needs saying: still preparing, or a notice
        if (composer.loading > 0) Text(composer.preparingText, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("photosPreparing"))
        composer.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.testTag("photosNotice")) }
        Text(pluralStringResource(R.plurals.create_photos_count, total, total), style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textTertiary, modifier = Modifier.testTag("photosNote"))
    }
}

/** An attached photo: a 64 dp thumbnail with a small close button (a 40 dp target) in its corner, so every photo can be taken out in one tap. */
@Composable
private fun RemovableThumb(onRemove: () -> Unit, content: @Composable () -> Unit) {
    val remove = stringResource(R.string.media_remove_photo)
    Box(Modifier.size(64.dp)) {
        Box(Modifier.fillMaxSize().clip(RoundedCornerShape(12.dp))) { content() }
        Box(Modifier.align(Alignment.TopEnd).size(40.dp).clickable(role = Role.Button, onClickLabel = remove, onClick = onRemove).semantics { contentDescription = remove }.testTag("removePhoto"), contentAlignment = Alignment.TopEnd) {
            Box(Modifier.padding(2.dp).size(22.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.65f)), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Close, null, tint = Color.White, modifier = Modifier.size(14.dp))
            }
        }
    }
}

/** One row of the Length menu: "2 min" and its price; greyed when over the platform's limit; the warning tint when the balance is short. */
@Composable
private fun LengthMenuRow(label: String, credits: Int, selected: Boolean, overBalance: Boolean, enabled: Boolean, tag: String, onClick: () -> Unit) {
    val tint = if (overBalance) Vmk.colors.warning else Vmk.colors.textSecondary
    val desc = pluralStringResource(if (selected) R.plurals.create_length_desc_selected else R.plurals.create_length_desc, credits, credits, label)
    androidx.compose.material3.DropdownMenuItem(
        text = {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(label, fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal, modifier = Modifier.widthIn(min = 72.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Bolt, null, tint = tint, modifier = Modifier.size(14.dp))
                    Text("$credits", style = MaterialTheme.typography.labelMedium, color = tint)
                }
            }
        },
        trailingIcon = { if (selected) Icon(Icons.Filled.Check, null, tint = Vmk.colors.primary) },
        enabled = enabled, onClick = onClick, modifier = Modifier.semantics { this.selected = selected; contentDescription = desc }.testTag(tag),
    )
}

/** The pill value is one short word: "Shorts" for the vertical-video group, "Video" for no platform in particular (the menu rows carry the long names). */
@Composable
private fun platformPillValue(o: CreateOptions, caps: com.videomk.app.core.Capabilities): String {
    if (CreatePlatforms.isCustom(o, caps)) return stringResource(R.string.create_custom)
    val c = CreatePlatforms.chip(caps, o.platform) ?: return stringResource(R.string.create_pill_video)
    return when (c.id) { "shorts" -> "Shorts"; "other" -> stringResource(R.string.create_pill_video); else -> c.label }
}
