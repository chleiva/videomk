package com.videomk.app.ui

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
import com.videomk.app.core.CreateCapsule
import com.videomk.app.core.DesignTokens
import androidx.compose.animation.togetherWith
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.PointerEventPass
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.semantics.liveRegion
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
import com.videomk.app.core.CreateDock
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.CreatePlatforms
import com.videomk.app.core.CreatePrefs
import com.videomk.app.core.DeckState
import com.videomk.app.core.ClipPhase
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
import com.videomk.app.core.DictationEngine
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
    val listening = dictationState is DictationEngine.State.Listening || dictationState is DictationEngine.State.Starting
    val options = composer.options
    val caps = composer.caps
    val scroll = rememberScrollState()
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    var photoMenu by remember { mutableStateOf(false) }
    var moreOpen by rememberSaveable { mutableStateOf(false) }
    var costInfo by remember { mutableStateOf(false) }
    var tip by remember { mutableStateOf<String?>(null) }
    var pulse by remember { mutableIntStateOf(0) }
    val deckState = composer.deckState
    val shake = remember { Animatable(0f) }
    val flash = remember { Animatable(0f) }
    val still = reduceMotion(context)
    val haptics = rememberHaptics()

    // capabilities: the real ones when the server has the endpoint, else landscape 16:9 at 1080p only
    val localeTag = com.videomk.app.core.Txt.localeTag   // a language change refetches: the server's labels and notes come back in the new language
    LaunchedEffect(container, localeTag) {
        val api = container?.intake ?: return@LaunchedEffect
        composer.applyCapabilities(runCatching { api.capabilities() }.getOrDefault(com.videomk.app.core.Capabilities.FALLBACK))
    }
    composer.attachDeckApi(container?.deckApi, container?.deckUploader)
    val clipUrl = caps.videoUpload?.apiUrl
    composer.attachClipApi(remember(clipUrl, container) { container?.clipApi(clipUrl) }, container?.clipUploader)
    composer.attachDictationService(container?.dictationApi)
    val improving by composer.better.working.collectAsState()
    // dictation feedback (docs/DICTATION_FEEDBACK_2026-11-28.md): the panel replaces the dock while the mic works; TalkBack hears thresholds only; haptics at the moments that matter
    val voice by composer.better.voice.collectAsState()
    val barsState = composer.better.bars.collectAsState()
    val voiceVisible = voice.phase == com.videomk.app.core.VoicePhase.Recording || voice.phase == com.videomk.app.core.VoicePhase.Transcribing || voice.phase == com.videomk.app.core.VoicePhase.Failed
    val voiceHaptics = rememberHaptics()
    LaunchedEffect(voice.phase) {
        when (voice.phase) {
            com.videomk.app.core.VoicePhase.Recording -> voiceHaptics.play(DesignTokens.Haptic.Selection)
            com.videomk.app.core.VoicePhase.Failed -> voiceHaptics.play(DesignTokens.Haptic.Warning)
            com.videomk.app.core.VoicePhase.Inserted -> voiceHaptics.play(DesignTokens.Haptic.UploadDone)
            else -> Unit
        }
    }
    androidx.compose.runtime.DisposableEffect(composer) {
        composer.better.announce = { key, v ->
            val text = when (key) {
                "listening" -> context.getString(R.string.voice_listening)
                "warn_soon" -> context.getString(R.string.voice_soon_a11y, v.warning.second)
                "warn_final" -> context.getString(R.string.voice_final_a11y)
                "transcribing" -> context.getString(R.string.voice_wait_a11y)
                "slow" -> context.getString(R.string.voice_slow_a11y)
                "failed" -> context.getString(R.string.voice_failed_a11y)
                "inserted" -> context.getString(R.string.voice_inserted_a11y)
                else -> null
            }
            if (text != null) view.announceForAccessibility(text)
        }
        onDispose { composer.better.announce = null }
    }
    val betterNote by composer.better.note.collectAsState()
    // one line after a fallback or the 6 minute stop, for a few seconds
    LaunchedEffect(betterNote) { if (betterNote != null) { delay(6000); composer.better.clearNote() } }
    // the system document picker: its one-time read grant is used at once and never kept (no persistable permission)
    val docPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) composer.addDeck(com.videomk.app.data.DeckPicker.pickOf(context.contentResolver, uri), replacePhotos = true)
    }
    fun launchDeckPicker() { val types = caps.deck?.mimeTypes ?: return; if (types.isNotEmpty()) docPicker.launch(types) }
    // a video is made from photos or from a presentation: picking a presentation replaces the photos (no question; the bar says so)
    val replacedText = stringResource(R.string.deck_replaced_photos)
    fun addDeck() { if (composer.totalPhotos > 0) container?.undo?.say(replacedText); launchDeckPicker() }
    val pickFromPhone = rememberPhonePhotoPicker(composer)
    // the person's own video clips: the system photo picker, videos only (no permission needed); the answer is the sound question, then the upload
    val videoFullText = androidx.compose.ui.res.pluralStringResource(R.plurals.vclip_reason_full, caps.videoUpload?.clipsPerVideo ?: 2, caps.videoUpload?.clipsPerVideo ?: 2)
    val videoPicker = androidx.activity.compose.rememberLauncherForActivityResult(androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null && !composer.addVideo(com.videomk.app.data.VideoPicker.pickOf(context.contentResolver, uri))) container?.undo?.say(videoFullText)
    }
    fun launchVideoPicker() { videoPicker.launch(androidx.activity.result.PickVisualMediaRequest(androidx.activity.result.contract.ActivityResultContracts.PickVisualMedia.VideoOnly)) }
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
    // the lengths this plan makes: a fix is never a length the server would refuse
    val status = ComposerLogic.status(composer.text, options, balance, 0, listening, sending = false, lengths = lengths.filter { caps.lengthAllowed(it) }, createScreen = true, checking = composer.checking, deck = deckState.takeIf { it.attached })
    // "not enough credits" comes with its fix ON the button: one tap makes the longest video the balance pays for
    val offer = status.fix?.minutes?.takeIf { status.kind == StatusKind.NotAffordable }
    // a Free account with nothing to spend and no free video available: the plans and the showcase instead of a form that cannot work
    val gate = if (com.videomk.app.DebugHooks.balanceOverride(context) != null) null else com.videomk.app.core.CreateGate.locked(state.wallet, caps.plans)
    val announcement = statusAnnouncement(status)
    // the keyboard is open on arrival: the prompt is the first thing, on every platform
    LaunchedEffect(gate == null) { if (gate == null) { runCatching { focus.requestFocus() }; keyboard?.show() } }
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
    // a refusal or a failure: the warning haptic, once
    LaunchedEffect(composer.stop != null, composer.inlineError != null) { if (composer.stop != null || composer.inlineError != null) haptics.play(DesignTokens.Haptic.Warning) }
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
        return app.submitAwait(out.brief, o, out.photos, out.meta, out.libraryIds, brief, out.deckId, out.deckTitle, out.dictationIds, out.clipIds)
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
        if (status.sendReady) { haptics.play(DesignTokens.Haptic.Send); composer.create(container?.intake, ::send, ::accepted) }
        else if (offer != null) { haptics.play(DesignTokens.Haptic.Send); composer.setLength(offer); composer.create(container?.intake, ::send, ::accepted) }
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

    // back is never destructive and never asks: the draft (words, photos, a presentation) stays for the next visit; the person empties it by deleting the words
    fun close() {
        if (CreateSubmit.closeIsBlocked(phase)) { view.announceForAccessibility(phaseText.orEmpty()); return }
        if (CreateSubmit.closeCancelsCheck(phase)) { composer.dismissSheet(); return }
        composer.dictation.stop(); composer.dismissSheet()
        onClose()
    }
    BackHandler { close() }

    var forOpen by remember { mutableStateOf(false) }
    var lengthOpen by remember { mutableStateOf(false) }
    var lookOpen by remember { mutableStateOf(false) }
    var optionsOpen by rememberSaveable { mutableStateOf(false) }
    var lookSheet by rememberSaveable { mutableStateOf(false) }
    var castSheet by rememberSaveable { mutableStateOf(false) }
    // photos or a presentation were attached or removed (or the server's list changed): a look that is not made from them goes back to Auto, and one line says so
    val attached = composer.attached
    LaunchedEffect(attached, caps.lookPicker) { composer.syncLook()?.let { view.announceForAccessibility(it) } }

    // example chips type themselves into the prompt (reduced motion: the text simply appears)
    var typing by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(typing) {
        val t = typing ?: return@LaunchedEffect
        if (still) composer.text = t else for (i in 1..t.length) { composer.text = t.take(i); delay(DesignTokens.Motion.typeChar.toLong()) }
        typing = null
    }
    val uploading = state.pending.firstNotNullOfOrNull { (it.state as? com.videomk.app.core.PendingVideo.State.Uploading)?.let { u -> u.done to u.total } }
    val capsule = CreateCapsule.view(phase, uploading)
    val aura by androidx.compose.animation.core.animateFloatAsState(if (locked) 1f else 0f, tween(if (still) DesignTokens.Motion.reducedFade else 320), label = "aura")
    val dim by androidx.compose.animation.core.animateFloatAsState(if (locked) 0.5f else 1f, tween(DesignTokens.Motion.select), label = "dim")
    val hasFinished = CreateDock.hasFinishedVideo(state.loadState is LoadState.Loaded, state.videos.any { it.status is com.videomk.app.core.VideoStatus.Complete })
    val showExamples = CreateDock.showExamples(composer.text.isEmpty(), typing != null, deckState.attached || photoTotal > 0, listening, locked, hasFinished)
    val creating = capsule is CreateCapsule.View.Live

    androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxSize().background(Vmk.colors.background).vmkAura(aura).statusBarsPadding().windowInsetsPadding(WindowInsets.ime.union(WindowInsets.navigationBars)).testTag("createScreen")) {
        // on a short window (keyboard up at a large text size) the pills scroll with the prompt; the tool row and Create stay put, so Create and the caret always fit
        val compact = maxHeight < 270.dp || (isLargeText() && maxHeight < 620.dp)
        val chipCount = CreateDock.chipCount(maxHeight.value)
        // ONE dock. Row 1: the pills (what it is for, how long, which look; Characters only for a look with a cast), each with a leading glyph.
        val pills: @Composable () -> Unit = {
            Column(Modifier.fillMaxWidth().then(if (locked) Modifier.alpha(dim).lockTouches() else Modifier)) {
                val chips = remember(caps) { CreatePlatforms.chips(caps).filter { it.enabled } }
                val forDesc = stringResource(R.string.create_what_for)
                val lengthDesc = stringResource(R.string.create_length)
                val lookDesc = stringResource(R.string.create_look)
                // the look was changed for the person (photos sent it back to Auto, a look moved the length): said right above the pill it is about
                composer.lookNotice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.fillMaxWidth().padding(bottom = Vmk.space.xs).semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Polite }.testTag("lookNotice")) }
                val picker = caps.lookPicker
                PillRows(Modifier.fillMaxWidth().testTag("pills"), gap = 6.dp) {
                    Pill(platformPillValue(options, caps), forDesc, Modifier.testTag("pillFor"), leading = { FormatGlyph(options.aspect) }, expanded = forOpen, onExpandedChange = { haptics.play(DesignTokens.Haptic.Selection); forOpen = it }, locked = locked) {
                        for (c in chips) androidx.compose.material3.DropdownMenuItem(
                            text = { Text(c.label, fontWeight = if (c.id == options.platform && !CreatePlatforms.isCustom(options, caps)) FontWeight.Bold else FontWeight.Normal) },
                            trailingIcon = { if (c.id == options.platform && !CreatePlatforms.isCustom(options, caps)) Icon(Sym.Check, null, tint = Vmk.colors.primary) },
                            onClick = { forOpen = false; haptics.play(DesignTokens.Haptic.Selection); composer.selectPlatform(c) }, modifier = Modifier.testTag("platform-${c.id}"),
                        )
                    }
                    val maxMinutes = CreatePlatforms.chip(caps, options.platform)?.takeIf { it.enabled }?.maxMinutes
                    Pill(if (options.useSuggestedLength && deckState is DeckState.Ready) stringResource(R.string.deck_suggested) else Lengths.short(options.minutes), lengthDesc, Modifier.testTag("pillLength"), leading = { PillGlyph(Sym.Schedule) }, expanded = lengthOpen, onExpandedChange = { haptics.play(DesignTokens.Haptic.Selection); lengthOpen = it }, locked = locked) {
                        (deckState as? DeckState.Ready)?.let { ready ->
                            LengthMenuRow(stringResource(R.string.deck_suggested) + " · " + Lengths.short(ready.info.suggestedMinutes), ready.info.suggestedCredits, options.useSuggestedLength, balance != null && ready.info.suggestedCredits > balance, true, "length-suggested") { lengthOpen = false; composer.useSuggestedLength() }
                        }
                        var anyOver = false
                        val longerPlan = caps.planName(caps.longerPlan)
                        for (mi in caps.presets) {
                            val over = maxMinutes != null && mi > maxMinutes + 1e-9
                            if (over) anyOver = true
                            // a length the plan does not make is shown with the plan that does and cannot be picked (the server refuses it, it does not shorten it)
                            val onPlan = caps.lengthAllowed(mi)
                            val price = Lengths.credits(mi) * maxOf(1, options.creditsMultiplier)
                            LengthMenuRow(Lengths.short(mi), price, !options.useSuggestedLength && Math.abs(options.minutes - mi) < 1e-9, balance != null && price > balance, !over && onPlan, "length-${if (mi == Math.floor(mi)) mi.toInt().toString() else mi.toString()}", plan = longerPlan.takeIf { !onPlan }) { lengthOpen = false; haptics.play(DesignTokens.Haptic.Selection); composer.setLength(mi) }
                        }
                        if (anyOver && maxMinutes != null) Text(stringResource(R.string.create_over_max, CreatePlatforms.chip(caps, options.platform)!!.label, Lengths.clock(maxMinutes)), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = Vmk.space.l, vertical = Vmk.space.s).widthIn(max = 240.dp))
                    }
                    // with the server's look picker the pill says the look only and opens the sheet of four tiles (the characters have their own pill); without it (an older server): the menu it always was
                    if (picker != null) PillButton(com.videomk.app.core.LookRules.pillLabel(options.lookChoice, picker), lookDesc, Modifier.testTag("pillLook"), locked = locked, onClick = { haptics.play(DesignTokens.Haptic.Selection); focusManager.clearFocus(); composer.dismissLookNotice(); lookSheet = true }, leading = { PillGlyph(Sym.Sparkle) })
                    else Pill(options.look?.let { stringResource(R.string.create_summary_look, it.displayName()) } ?: stringResource(R.string.create_summary_look_auto), lookDesc, Modifier.testTag("pillLook"), leading = { PillGlyph(Sym.Sparkle) }, expanded = lookOpen, onExpandedChange = { haptics.play(DesignTokens.Haptic.Selection); lookOpen = it }, locked = locked) {
                        for (l in listOf<VideoLook?>(null) + VideoLook.entries) androidx.compose.material3.DropdownMenuItem(
                            text = { Text(l?.displayName() ?: stringResource(R.string.create_look_auto), fontWeight = if (options.look == l) FontWeight.Bold else FontWeight.Normal) },
                            trailingIcon = { if (options.look == l) Icon(Sym.Check, null, tint = Vmk.colors.primary) },
                            onClick = { lookOpen = false; haptics.play(DesignTokens.Haptic.Selection); composer.updateOptions(options.copy(look = l)) }, modifier = Modifier.testTag("look-${l?.wire ?: "auto"}"),
                        )
                    }
                    // only for a look with characters: who explains it. The chosen faces (or the people glyph of "we choose") lead the word; it opens the Characters sheet.
                    // The second form is the glyph or faces alone, for where the word does not fit in two rows of pills (large text, small phones); TalkBack hears "Characters" either way.
                    if (picker != null && composer.lookHasCast) {
                        val castDesc = stringResource(R.string.looks_cast)
                        val faces = options.lookChoice.cast.mapNotNull { picker.cast?.member(it) }
                        val spoken = com.videomk.app.core.LookRules.castSpoken(options.lookChoice, picker)
                        val open = { haptics.play(DesignTokens.Haptic.Selection); focusManager.clearFocus(); composer.dismissLookNotice(); castSheet = true }
                        for (compactForm in listOf(false, true)) PillButton(if (compactForm) "" else castDesc, castDesc, Modifier.testTag("pillCast"), spoken = spoken, locked = locked, onClick = open, leading = { if (faces.isEmpty()) PillGlyph(Sym.Person) else PillFaces(faces) })
                    }
                }
            }
        }
        // Row 2: photos, mic and Options on the left, Create at the trailing end (it drops to its own row at large text or where it does not fit)
        val toolRow: @Composable () -> Unit = {
            val createCredits = if (offer != null) Lengths.credits(offer) * maxOf(1, options.creditsMultiplier) else options.credits
            val priceKnown = !deckState.attached || deckState is DeckState.Ready      // not while a presentation is still being read: its price is not known yet
            val createState = CreateDock.createState(status.sendReady, offer != null, creating = false)
            // "Create" alone, or with the length the balance pays for: "Create · 1 min" (one tap makes that video)
            val createLabel = if (offer != null) stringResource(R.string.create_with_length, Lengths.short(offer)) else stringResource(R.string.create_create_video)
            val spokenLabel = if (offer != null) createLabel else stringResource(R.string.create_video_desc)
            val stateText = if (createState == CreateDock.CreateState.Active) pluralStringResource(R.plurals.create_state_ready, createCredits, createCredits)
                else stringResource(if (status.fix != null) R.string.create_state_not_ready_fix else R.string.create_state_not_ready, status.text)
            DockToolRow(
                Modifier.fillMaxWidth(),
                tools = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        // the photo icon is a menu, each row goes straight to its picker: the phone's own photo picker, Media, and a presentation where the server offers it
                        if (!deckState.attached) Box {
                            GlassIconButton(Sym.AddPhotoAlternate, stringResource(R.string.create_add_photos), { haptics.play(DesignTokens.Haptic.Selection); photoMenu = true }, Modifier.testTag("photoButton"), enabled = !listening, badge = AddPhotosLogic.badge(photoTotal))
                            VmkMenu(photoMenu, { photoMenu = false }) {
                                VmkMenuItem(stringResource(R.string.photo_menu_library), Sym.Image, Modifier.testTag("photoMenuLibrary")) { photoMenu = false; pickFromPhone() }
                                if (container?.mediaApi != null) VmkMenuItem(stringResource(R.string.nav_tab_media), Sym.PhotoLibrary, Modifier.testTag("photoMenuMedia")) { photoMenu = false; composer.openAddPhotos(1) }
                                VideoMenuRow(com.videomk.app.core.VideoRules.entry(caps.videoUpload, composer.clipper.leftToday, composer.clips.count { it.phase !is com.videomk.app.core.ClipPhase.Failed }), caps.videoUpload) { photoMenu = false; launchVideoPicker() }
                                if (caps.deck != null) VmkMenuItem(stringResource(R.string.photo_menu_presentation), Sym.Slideshow, Modifier.testTag("addDeck")) { photoMenu = false; addDeck() }
                            }
                        }
                        GlassIconButton(if (listening) Sym.Stop else Sym.Mic, stringResource(if (listening) R.string.create_stop_dictation else R.string.create_dictate_desc), ::onMic, Modifier.testTag("micButton"), danger = listening)
                        OptionsButton(labelled = !listening, enabled = !listening, onClick = { focusManager.clearFocus(); optionsOpen = true }, modifier = Modifier.testTag("optionsMenu"))
                    }
                },
                middle = { if (improving) Text(stringResource(R.string.better_working), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, maxLines = 1, softWrap = false, modifier = Modifier.testTag("improvingHint")) else if (listening) Text(stringResource(R.string.composer_listening), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger, maxLines = 1, softWrap = false, modifier = Modifier.testTag("listeningHint")) },
                create = { CreatePill(createState, createLabel, spokenLabel, createCredits.takeIf { priceKnown }, stateText, if (createState == CreateDock.CreateState.Active) createLabel else stringResource(R.string.create_explain_not_ready), onClick = ::tapCreate) },
            )
        }
        Column(Modifier.fillMaxSize()) {
            // the screen is the title: only the way out
            Row(Modifier.fillMaxWidth().heightIn(min = 60.dp).padding(horizontal = Vmk.space.screen - 2.dp), verticalAlignment = Alignment.CenterVertically) {
                GlassIconButton(Sym.Close, stringResource(if (CreateSubmit.closeCancelsCheck(phase)) R.string.common_cancel else R.string.common_close), ::close, Modifier.testTag("createCancel"), enabled = !CreateSubmit.closeIsBlocked(phase))
            }
            if (gate != null) { LockedCreate(gate, caps, container, Modifier.weight(1f)); return@Column }

            Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = Vmk.space.screen), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
                Column(Modifier.fillMaxWidth().then(if (locked) Modifier.alpha(dim).lockTouches() else Modifier), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
                    PromptField(composer, listening || typing != null, focus, deck = deckState.attached)
                    if (showExamples && chipCount > 0) FlowRow(Modifier.fillMaxWidth().testTag("createExamples"), horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                        val use = stringResource(R.string.create_example_use)
                        for ((i, res) in listOf(R.string.create_example_bees, R.string.create_example_focus, R.string.create_example_forests).take(chipCount).withIndex()) {
                            val t = stringResource(res)
                            SparkleChip(t, { haptics.play(DesignTokens.Haptic.Selection); focusManager.clearFocus(); typing = t }, Modifier.testTag("example-$i"), onClickLabel = use)
                        }
                    }
                    dictationHint(dictationState)
                    betterNote?.let { n -> betterNoteHint(n) }
                    if (deckState.attached) DeckCard(
                        deckState, caps.deck, onRemove = { composer.removeDeck() }, onPickAgain = { composer.removeDeck(); launchDeckPicker() }, onRetry = { composer.deck.retry() }, onKeepWaiting = { composer.deck.keepWaiting() },
                    ) else if (photoTotal > 0 || composer.clips.isNotEmpty()) PhotoStrip(composer, locked) { photoMenu = true }
                    tip?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.semantics { contentDescription = it }) }
                    // only when there is something to say: slides are wide, a platform's limit, what the photos can fill
                    if (composer.deckVerticalWarning) Column(Modifier.fillMaxWidth().testTag("deckVerticalWarning")) {
                        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                            Icon(Sym.Warning, null, tint = Vmk.colors.warning, modifier = Modifier.size(18.dp).padding(top = 2.dp))
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
                    // the length was shortened after the look was chosen: the video would still be made (one character presents), so this only offers the way back
                    composer.lookLengthNudge()?.takeIf { composer.lookNotice == null }?.let { nudge ->
                        FlowRow(Modifier.fillMaxWidth().testTag("lookLengthHint"), itemVerticalAlignment = Alignment.CenterVertically) {
                            Text(com.videomk.app.core.LookRules.needsLine(nudge, options.lookChoice, caps.lookPicker) + " ", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                            FixChip(stringResource(R.string.create_over_max_use, Lengths.short(nudge.minutes)), stringResource(R.string.create_over_max_use_desc, Lengths.long(nudge.minutes)), Modifier.testTag("lookLengthFix")) { composer.setLength(nudge.minutes) }
                        }
                    }
                    if (photoHint != null) PhotoHintBlock(photoHint, hintFix, composer, options)
                }
                if (compact && !creating) pills()
                Spacer(Modifier.size(Vmk.space.s))
            }

            // what never goes away: the dock (pills, then photos / mic / Options with Create), one sentence above it when something needs saying, one caption under it
            Column(Modifier.fillMaxWidth().padding(horizontal = Vmk.space.l).padding(top = Vmk.space.s, bottom = Vmk.space.m).testTag("createDock"), verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                composer.inlineError?.let { m ->
                    Row(Modifier.fillMaxWidth().testTag("createError").semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Assertive }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                        Icon(Sym.Warning, null, tint = Vmk.colors.danger, modifier = Modifier.size(18.dp))
                        Text(stringResource(R.string.create_error_retry, m), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text)
                    }
                }
                androidx.compose.animation.AnimatedContent(if (creating) 2 else if (voiceVisible) 1 else 0, transitionSpec = { androidx.compose.animation.fadeIn(tween(if (still) DesignTokens.Motion.reducedFade else 220)) togetherWith androidx.compose.animation.fadeOut(tween(DesignTokens.Motion.reducedFade)) }, label = "capsule") { mode ->
                    val live = mode == 2
                    if (live) (capsule as? CreateCapsule.View.Live ?: CreateCapsule.View.Live(CreateCapsule.Step.Starting, false)).let { LiveCapsule(it, onCancel = { haptics.play(DesignTokens.Haptic.Selection); composer.dismissSheet() }) }
                    else if (mode == 1) DictationPanel(voice, barsState, composer.better.usesClip, onStop = { composer.dictation.stop() }, onCancel = { composer.better.discard() }, onRetry = { composer.better.retry() }, onDevice = { composer.better.useDeviceDictation() })
                    else Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                        // calm: nothing is wrong, so the sentence stays away and (maybe) the caption speaks
                        val calm = status.kind == StatusKind.Ready || status.kind == StatusKind.PhotoHint || status.kind == StatusKind.Listening || status.kind == StatusKind.Idle ||
                            (status.kind == StatusKind.TooShort && composer.text.isEmpty() && pulse == 0 && !deckState.attached)
                        if (!calm) StatusLine(if (offer != null) status.copy(fix = null) else status, flash.value, shake.value, ::applyFix)
                        if (!compact) pills()
                        toolRow()
                        val cost = if (offer != null) Lengths.credits(offer) * maxOf(1, options.creditsMultiplier) else options.credits
                        when (val cap = CreateDock.caption(calm, balance, cost, hasFinished, priceKnown = !deckState.attached || deckState is DeckState.Ready)) {
                            is CreateDock.Caption.FirstVideo -> DockCaption(pluralStringResource(R.plurals.create_first_cost, cap.cost, cap.cost, cap.balance))
                            is CreateDock.Caption.Low -> DockCaption(pluralStringResource(R.plurals.create_credits_left, cap.balance, cap.balance))
                            CreateDock.Caption.None -> Unit
                        }
                    }
                }
            }
        }
    }

    if (lookSheet) LookSheet(composer) { lookSheet = false }
    if (castSheet) CharactersSheet(composer) { castSheet = false }
    composer.askingClip?.let { asking -> ClipSoundSheet(asking, onAnswer = { composer.clipper.answer(asking.id, it) }, onDismiss = { composer.clipper.dismissSheet(asking.id) }) }
    if (optionsOpen) CreateOptionsSheet(composer, caps, options, photoTotal > 0 || deckState.attached, onCostInfo = { costInfo = true }, onDismiss = { optionsOpen = false })

    if (composer.addPhotosRequest != null && container?.mediaApi != null) AddPhotosSheet(composer, container.mediaApi, container.mediaUploads?.arrivals, onDismiss = { composer.closeAddPhotos() })
    CreateSheetsHost(composer, balance, options, onSubmitEdit = {}, onWallet = onOpenWallet)
    if (costInfo) CostSheet(fourK = caps.resolutions.any { it.multiplier > 1 && it.available }) { costInfo = false }
}

/**
 * Create for an account that cannot make a video right now (a Free account with no credit to spend while free videos are off, used up or paused for today):
 * the server's own sentence, when it comes back, the plans by name (nothing can be bought yet, so no button), and the showcase of videos made with the product.
 */
@Composable
private fun LockedCreate(gate: com.videomk.app.core.CreateGate.Locked, caps: com.videomk.app.core.Capabilities, container: com.videomk.app.AppContainer?, modifier: Modifier = Modifier) {
    var videos by remember { mutableStateOf<List<com.videomk.app.core.GalleryVideo>?>(null) }
    LaunchedEffect(Unit) { videos = runCatching { container?.backend?.gallery() }.getOrNull().orEmpty() }
    val play = rememberLauncherForActivityResult(FullScreenContract()) { }
    Column(modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = Vmk.space.screen).padding(bottom = Vmk.space.xxl).testTag("createLocked"), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
        Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            Text(gate.message ?: stringResource(R.string.create_locked_default), style = VmkType.prompt, color = Vmk.colors.text, modifier = Modifier.semantics { heading() }.testTag("lockedMessage"))
            gate.resumesAt?.let { Text(stringResource(R.string.stop_resumes, com.videomk.app.core.PlanText.moment(it)), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary) }
            if (!caps.plans.canUpgrade) Text(stringResource(R.string.plans_coming_soon), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("plansSoon"))
        }
        val list = videos
        if (list == null) Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(Vmk.radii.videoCard)).background(Vmk.colors.surfaceRaised))
        else for (v in list) {
            val shape = RoundedCornerShape(Vmk.radii.videoCard)
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(Vmk.radii.tile)).clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_play)) { play.launch(FullScreenArgs(v.videoUrl, 0, true, com.videomk.app.core.VideoItem.ratioOf(v.aspect) < 0.99f)) }
                    .semantics(mergeDescendants = true) { }.testTag("showcaseVideo"),
                verticalArrangement = Arrangement.spacedBy(Vmk.space.s),
            ) {
                Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(shape).background(Vmk.makingGradient)) {
                    if (v.posterUrl != null) StableImage(v.posterUrl, ContentScale.Crop, Modifier.fillMaxSize())
                    else Icon(Sym.PlayArrow, null, tint = Color.White.copy(alpha = 0.9f), modifier = Modifier.align(Alignment.Center).size(44.dp))
                    v.seconds?.let { GlassChip(duration(it), Modifier.align(Alignment.BottomEnd).padding(Vmk.space.s)) }
                }
                if (v.title.isNotBlank()) Text(v.title, style = VmkType.makingTitle, color = Vmk.colors.text, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis, modifier = Modifier.padding(horizontal = Vmk.space.xs).padding(bottom = Vmk.space.xs))
            }
        }
    }
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
        Icon(if (selected) Sym.Check else if (c.id == "other") Sym.AutoAwesome else if (c.aspect == "16:9") Sym.CropLandscape else if (c.aspect == "1:1") Sym.CropSquare else Sym.CropPortrait, null, tint = if (selected) Vmk.colors.primary else Vmk.colors.text, modifier = Modifier.size(18.dp))
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

/**
 * The live capsule the Create button turns into (signature 2): the sparkle, three words that say what is happening, one quiet line beneath, the moving ring,
 * and Cancel as the only control (while cancelling is clean). The words are announced once per step, never on every tick.
 */
@Composable
private fun LiveCapsule(v: CreateCapsule.View.Live, onCancel: () -> Unit) {
    val shape = CircleShape
    val title = stringResource(if (v.step == CreateCapsule.Step.Checking) R.string.create_capsule_checking else R.string.create_capsule_starting)
    val sub = if (v.photo != null && v.photos != null) stringResource(R.string.create_capsule_photo, v.photo, v.photos) else stringResource(R.string.create_capsule_sub)
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(Vmk.space.xs)) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = Vmk.primaryButton + 8.dp).clip(shape).background(Vmk.colors.surface).border(2.dp, Vmk.liveRing, shape)
                .padding(horizontal = Vmk.space.xxl, vertical = Vmk.space.m)
                .semantics(mergeDescendants = true) { }.testTag("createCapsule"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m),
        ) {
            Sparkle(size = 18.dp)
            Column(Modifier.weight(1f)) {
                Text(title, style = VmkType.cta, color = Vmk.colors.text, modifier = Modifier.testTag("sendBusyText"))
                Text(sub, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
            }
            LiveRing()
        }
        // Cancel keeps its place while the send is in flight (it cannot be taken back then), so nothing jumps
        TextButton(onClick = onCancel, enabled = v.canCancel, modifier = Modifier.heightIn(min = Vmk.minTouch).alpha(if (v.canCancel) 1f else 0f).testTag("capsuleCancel")) {
            Text(stringResource(R.string.common_cancel), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text)
        }
    }
}

/** Swallows every touch on this part of the screen (the form while a request is running). */
private fun Modifier.lockTouches(): Modifier = this.pointerInput(Unit) {
    awaitPointerEventScope { while (true) { awaitPointerEvent(PointerEventPass.Initial).changes.forEach { it.consume() } } }
}

/** The prompt: large borderless text on the page (no card, no outline); the short hint is the only words around it. */
@Composable
private fun PromptField(composer: ComposerViewModel, listening: Boolean, focus: FocusRequester, deck: Boolean = false) {
    // the text that just arrived from Better dictation is tinted for a moment (a plain fade with reduced motion)
    val inserted by composer.better.inserted.collectAsState()
    val tint by androidx.compose.animation.animateColorAsState(if (inserted) Vmk.colors.primaryContainer else Color.Transparent, tween(if (reduceMotion(LocalContext.current)) DesignTokens.Motion.reducedFade else 600), label = "inserted")
    BasicTextField(
        value = composer.text, onValueChange = { composer.text = it }, readOnly = listening,
        textStyle = VmkType.prompt.copy(color = if (listening) Vmk.colors.textSecondary else Vmk.colors.text),
        cursorBrush = SolidColor(Vmk.colors.primary), keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
        modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).focusRequester(focus).background(tint, RoundedCornerShape(8.dp)).padding(top = Vmk.space.s).testTag("composerField"),
        decorationBox = { inner ->
            Box { if (composer.text.isEmpty()) Text(stringResource(if (deck) R.string.deck_prompt_hint else R.string.create_prompt_hint), style = VmkType.prompt, color = Vmk.colors.textTertiary); inner() }
        },
    )
}

/** What is attached: one row of 56 dp thumbnails, "+" at the end (it opens the photo sheet again). */
@Composable
private fun PhotoStrip(composer: ComposerViewModel, locked: Boolean, onAdd: () -> Unit) {
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
            val stripClips = composer.clips
            items(stripClips.size, key = { stripClips[it].id }) { i ->
                val clip = stripClips[i]
                ClipTile(clip, onRemove = { composer.clipper.remove(clip.id) }, onTap = { if (clip.phase is ClipPhase.Failed) composer.clipper.retry(clip.id) else composer.clipper.askAgain(clip.id) })
            }
            if (!locked) item {
                val add = stringResource(R.string.create_add_photos)
                Box(Modifier.size(64.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised).clickable(role = Role.Button, onClickLabel = add, onClick = onAdd).semantics { contentDescription = add }, contentAlignment = Alignment.Center) {
                    Icon(Sym.AddPhotoAlternate, null, tint = Vmk.colors.primary)
                }
            }
        }
        // only when something needs saying: still preparing, or a notice
        if (composer.loading > 0) Text(composer.preparingText, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("photosPreparing"))
        composer.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.testTag("photosNotice")) }
        if (total > 0) Text(pluralStringResource(R.plurals.create_photos_count, total, total), style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textTertiary, modifier = Modifier.testTag("photosNote"))
        if (composer.clips.isNotEmpty()) {
            ClipStatus(composer.clips, composer.caps.videoUpload, onRetry = { composer.clipper.retry(it) }, onKeepWaiting = { composer.clipper.keepWaiting(it) }, onRemove = { composer.clipper.remove(it) })
            ClipCaption(composer.caps.videoUpload)
        }
    }
}

/** An attached photo: a 64 dp thumbnail with a small close button (a 40 dp target) in its corner, so every photo can be taken out in one tap. */
@Composable
private fun RemovableThumb(onRemove: () -> Unit, content: @Composable () -> Unit) {
    val remove = stringResource(R.string.media_remove_photo)
    Box(Modifier.size(64.dp)) {
        Box(Modifier.fillMaxSize().clip(RoundedCornerShape(12.dp))) { content() }
        Box(Modifier.align(Alignment.TopEnd).offset(x = 8.dp, y = (-8).dp).size(Vmk.minTouch).clickable(role = Role.Button, onClickLabel = remove, onClick = onRemove).semantics { contentDescription = remove }.testTag("removePhoto"), contentAlignment = Alignment.TopEnd) {
            Box(Modifier.padding(10.dp).size(22.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.65f)), contentAlignment = Alignment.Center) {
                Icon(Sym.Close, null, tint = Color.White, modifier = Modifier.size(14.dp))
            }
        }
    }
}

/** One row of the Length menu: "2 min" and its price; greyed when over the platform's limit; the warning tint when the balance is short. */
@Composable
private fun LengthMenuRow(label: String, credits: Int, selected: Boolean, overBalance: Boolean, enabled: Boolean, tag: String, plan: String? = null, onClick: () -> Unit) {
    val tint = if (overBalance) Vmk.colors.warning else Vmk.colors.textSecondary
    val desc = pluralStringResource(if (selected) R.plurals.create_length_desc_selected else R.plurals.create_length_desc, credits, credits, label)
    androidx.compose.material3.DropdownMenuItem(
        text = {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(label, fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal, modifier = Modifier.widthIn(min = 72.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Sym.Bolt, null, tint = tint, modifier = Modifier.size(14.dp))
                    Text("$credits", style = MaterialTheme.typography.labelMedium, color = tint)
                }
            }
        },
        trailingIcon = { if (selected) Icon(Sym.Check, null, tint = Vmk.colors.primary) else if (plan != null) PlanTag(plan) },
        enabled = enabled, onClick = onClick, modifier = Modifier.semantics { this.selected = selected; contentDescription = if (plan != null) "$desc. $plan" else desc }.testTag(tag),
    )
}

/** The pill shows the same word as its menu row (rule 13); only the long vertical-video group is shortened to "Shorts". */
@Composable
private fun platformPillValue(o: CreateOptions, caps: com.videomk.app.core.Capabilities): String {
    if (CreatePlatforms.isCustom(o, caps)) return stringResource(R.string.create_custom)
    val c = CreatePlatforms.chip(caps, o.platform) ?: return stringResource(R.string.create_platform_other)
    return when (c.id) { "shorts" -> "Shorts"; else -> c.label }
}

/** The plan that unlocks a choice ("Pro", "Max"): a small tonal tag on the locked row or tile. */
@Composable
internal fun PlanTag(plan: String, modifier: Modifier = Modifier) {
    Text(plan, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, maxLines = 1, modifier = modifier.clip(CircleShape).background(Vmk.colors.primaryContainer).padding(horizontal = Vmk.space.s, vertical = 2.dp))
}
