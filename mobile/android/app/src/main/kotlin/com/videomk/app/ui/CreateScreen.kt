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
        onClose()
    }

    fun tapCreate() {
        if (composer.checking || composer.submitting) return
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

    fun close() { if (composer.submitting) return; if (composer.hasDraft) discard = true else { composer.discardDraft(); onClose() } }
    BackHandler { close() }

    Column(Modifier.fillMaxWidth().background(Vmk.colors.background).statusBarsPadding().windowInsetsPadding(WindowInsets.ime.union(WindowInsets.navigationBars)).testTag("createScreen")) {
        // header
        val bigHeader = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f   // large text: Cancel and the title stack instead of overlapping
        val cancelBtn: @Composable (Modifier) -> Unit = { m ->
            TextButton(onClick = ::close, modifier = m.heightIn(min = 48.dp).testTag("createCancel")) { Text(stringResource(R.string.common_cancel), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.primary) }
        }
        val titleTxt: @Composable (Modifier) -> Unit = { m ->
            Text(stringResource(R.string.create_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, modifier = m.semantics { heading() })
        }
        if (bigHeader) Column(Modifier.fillMaxWidth().padding(horizontal = 4.dp)) { cancelBtn(Modifier); Box(Modifier.padding(start = 12.dp, bottom = 8.dp)) { titleTxt(Modifier) } }
        else Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).padding(horizontal = 4.dp)) {
            cancelBtn(Modifier.align(Alignment.CenterStart))
            titleTxt(Modifier.align(Alignment.Center))
        }
        Box(Modifier.fillMaxWidth().size(1.dp).background(if (scroll.value > 0) Vmk.colors.outline else Color.Transparent))

        Column(Modifier.weight(1f).verticalScroll(scroll).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            PromptCard(composer, listening, focus, ::onMic, deck = deckState.attached)
            dictationHint(dictationState)
            if (deckState.attached) DeckCard(
                deckState, caps.deck, onRemove = { composer.removeDeck() }, onPickAgain = { composer.removeDeck(); launchDeckPicker() }, onRetry = { composer.deck.retry() }, onKeepWaiting = { composer.deck.keepWaiting() },
            ) else PhotosRow(composer) { composer.openAddPhotos(null) }

            // what is it for
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Overline(stringResource(R.string.create_what_for), Modifier.semantics { heading() })
                // a wrapping grid, never a row that scrolls or crops: Spanish and large text just make a second line
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().testTag("platformChips")) {
                    for (c in CreatePlatforms.chips(caps)) {
                        PlatformChipView(c, selected = c.enabled && c.id == options.platform && !CreatePlatforms.isCustom(options, caps)) {
                            if (c.enabled) composer.selectPlatform(c) else { tip = comingSoonText; haptic(false) }
                        }
                    }
                }
                tip?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.semantics { contentDescription = it }) }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    val rec = CreatePlatforms.recommendation(options, caps, withNote = !deckState.attached)   // a presentation brings its own length: no "about 3 min" advice beside it
                    Text(rec, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f).testTag("recommendation"))
                    if (CreatePlatforms.canChangeFormat(caps)) TextButton(onClick = { moreOpen = true }, modifier = Modifier.heightIn(min = 44.dp).testTag("changeFormat")) { Text(stringResource(R.string.create_change), fontWeight = FontWeight.Bold) }
                }
                // slides are wide: a gentle word when a vertical or portrait picture is chosen, with the one-tap fix
                if (composer.deckVerticalWarning) Column(Modifier.fillMaxWidth().testTag("deckVerticalWarning")) {
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Filled.Warning, null, tint = Vmk.colors.warning, modifier = Modifier.size(18.dp).padding(top = 2.dp))
                        Text(stringResource(R.string.deck_vertical_warning), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text)
                    }
                    FixChip(stringResource(R.string.deck_use_landscape), stringResource(R.string.deck_use_landscape_desc), Modifier.testTag("deckUseLandscape")) { composer.useLandscape() }
                }
                // other formats this platform also accepts: small secondary choices that switch only the format
                val also = CreatePlatforms.alsoWorks(options, caps)
                if (also.isNotEmpty()) FlowRow(Modifier.testTag("alsoWorks"), verticalArrangement = Arrangement.Center, horizontalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.create_also_works), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                    for (a in also) Text(
                        a.label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary,
                        modifier = Modifier.heightIn(min = 44.dp).clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClickLabel = stringResource(R.string.create_use_format, a.label)) { composer.updateOptions(options.copy(aspect = a.id)) }
                            .padding(horizontal = 8.dp).wrapContentHeight(Alignment.CenterVertically).testTag("alsoWorks-${a.id}"),
                    )
                }
            }

            // length
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Overline(stringResource(R.string.create_length), Modifier.semantics { heading() })
                // the presets the server offers, scrolling sideways when there are more than fit
                androidx.compose.foundation.lazy.LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth().testTag("lengthChips")) {
                    // a ready presentation: its own suggested length first (the server's price), then the usual lengths
                    (deckState as? DeckState.Ready)?.let { ready ->
                        item(key = "suggested") {
                            LengthChip(ready.info.suggestedMinutes, ready.info.suggestedCredits, options.useSuggestedLength, balance != null && ready.info.suggestedCredits > balance, Modifier.widthIn(min = 78.dp), caption = stringResource(R.string.deck_suggested), tag = "length-suggested") { composer.useSuggestedLength() }
                        }
                    }
                    items(caps.presets) { mi ->
                        LengthChip(mi, Lengths.credits(mi), !options.useSuggestedLength && Math.abs(options.minutes - mi) < 1e-9, balance != null && Lengths.credits(mi) > balance, Modifier.widthIn(min = 78.dp)) { composer.setLength(mi) }
                    }
                }
                CreatePlatforms.overMax(options, caps)?.let { om ->
                    FlowRow(Modifier.fillMaxWidth().testTag("overMaxHint"), itemVerticalAlignment = Alignment.CenterVertically) {
                        Text(om.text + (om.useMinutes?.let { " · " } ?: ""), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                        om.useMinutes?.let { u -> FixChip(stringResource(R.string.create_over_max_use, Lengths.short(u)), stringResource(R.string.create_over_max_use_desc, Lengths.long(u)), Modifier.testTag("overMaxChip")) { composer.setLength(u) } }
                    }
                }
                if (photoHint != null) PhotoHintBlock(photoHint, hintFix, composer, options)
                CostLine(null, options.isFourK, onWhy = { costInfo = true })
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
                        Text(stringResource(R.string.create_error_retry, m), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.danger)
                    }
                }
                StatusLine(status, flash.value, shake.value, ::applyFix)
                CreateButton(status.sendReady, composer.checking || composer.submitting, options.credits, status.text, status.fix != null, ::tapCreate)
            }
        }
    }

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
private fun PromptCard(composer: ComposerViewModel, listening: Boolean, focus: FocusRequester, onMic: () -> Unit, deck: Boolean = false) {
    val shape = RoundedCornerShape(22.dp)
    val micDescription = if (listening) stringResource(R.string.create_stop_dictation) else stringResource(R.string.create_dictate_desc)
    // text on top, the mic row under it: the height follows the text (large text and Spanish just make the card taller, nothing overlaps)
    Column(Modifier.fillMaxWidth().heightIn(min = 112.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)) {
        BasicTextField(
            value = composer.text, onValueChange = { composer.text = it }, readOnly = listening,
            textStyle = VmkType.prompt.copy(color = if (listening) Vmk.colors.textSecondary else Vmk.colors.text),
            cursorBrush = SolidColor(Vmk.colors.primary), keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
            modifier = Modifier.fillMaxWidth().focusRequester(focus).padding(start = 18.dp, end = 18.dp, top = 16.dp, bottom = 4.dp).testTag("composerField"),
            decorationBox = { inner ->
                Box { if (composer.text.isEmpty()) Text(stringResource(if (deck) R.string.deck_prompt_hint else R.string.create_prompt_hint), style = VmkType.prompt, color = Vmk.colors.textTertiary); inner() }
            },
        )
        Row(Modifier.fillMaxWidth().padding(start = 18.dp, end = 10.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Spacer(Modifier.weight(1f).heightIn(min = 1.dp))
            if (composer.text.isEmpty() && !listening) Text(stringResource(R.string.create_tap_mic), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textTertiary, textAlign = androidx.compose.ui.text.style.TextAlign.End, modifier = Modifier.weight(2f, fill = false))
            if (listening) Text(stringResource(R.string.composer_listening), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger, modifier = Modifier.weight(2f, fill = false))
            Box(
                Modifier.size(48.dp).clip(CircleShape).background(if (listening) Vmk.colors.danger else Vmk.colors.surfaceRaised)
                    .clickable(role = Role.Button, onClickLabel = if (listening) stringResource(R.string.create_stop_dictation) else stringResource(R.string.create_dictate), onClick = onMic)
                    .semantics { contentDescription = micDescription }.testTag("micButton"),
                contentAlignment = Alignment.Center,
            ) { Icon(if (listening) Icons.Filled.Stop else Icons.Filled.Mic, null, tint = if (listening) Vmk.colors.onPrimary else Vmk.colors.text, modifier = Modifier.size(22.dp)) }
        }
    }
}

/** One row for photos: "Add photos" with the optional line, or, once chosen, the count with Edit and a strip of four thumbnails. */
@Composable
private fun PhotosRow(composer: ComposerViewModel, onOpen: () -> Unit) {
    val shape = RoundedCornerShape(20.dp)
    val total = composer.totalPhotos
    val rowDescription = if (total > 0) pluralStringResource(R.plurals.create_add_photos_selected_desc, total, total) else stringResource(R.string.create_add_photos_desc_empty)
    Row(
        Modifier.fillMaxWidth().heightIn(min = 64.dp).clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
            .clickable(role = Role.Button, onClickLabel = stringResource(R.string.create_add_photos), onClick = onOpen).padding(horizontal = 12.dp, vertical = 8.dp)
            .semantics(mergeDescendants = true) { contentDescription = rowDescription }.testTag("photoButton"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (total == 0) {
            Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(Icons.Filled.AddPhotoAlternate, null, tint = Vmk.colors.primary) }
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.create_add_photos), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
                Text(stringResource(R.string.create_add_photos_optional), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
            }
            Icon(Icons.Filled.ChevronRight, null, tint = Vmk.colors.textSecondary)
        } else {
            Column(Modifier.weight(1f)) {
                Text(pluralStringResource(R.plurals.create_photos_count, total, total), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.testTag("photosNote"))
                if (composer.loading > 0) Text(composer.preparingText, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("photosPreparing"))
                composer.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.testTag("photosNotice")) }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                val thumbs = composer.photos.take(4).map { it.thumbnail } + composer.library.take(4).map { null }
                composer.photos.take(4).forEach { p -> p.thumbnail?.let { androidx.compose.foundation.Image(it.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)).testTag("attachedPhoto")) } }
                if (composer.photos.size < 4) composer.library.take(4 - composer.photos.size).forEach { PhotoThumb(it, Modifier.size(36.dp).clip(RoundedCornerShape(8.dp)).testTag("attachedLibraryPhoto")) }
                if (total > 4) Text("+${total - 4}", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 4.dp))
            }
            Text(stringResource(R.string.create_edit), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.primary)
        }
    }
}

@Composable
private fun PlatformChipView(c: PlatformChip, selected: Boolean, onClick: () -> Unit) {
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
private fun LengthChip(minutes: Double, credits: Int, selected: Boolean, overBalance: Boolean, modifier: Modifier, caption: String? = null, tag: String? = null, onClick: () -> Unit) {
    val shape = RoundedCornerShape(16.dp)
    val tint = if (overBalance) Vmk.colors.warning else if (selected) Vmk.colors.primary else Vmk.colors.textSecondary
    val lengthDescription = if (caption != null) pluralStringResource(R.plurals.deck_suggested_desc, credits, credits, Lengths.long(minutes)) else pluralStringResource(if (selected) R.plurals.create_length_desc_selected else R.plurals.create_length_desc, credits, credits, Lengths.long(minutes))
    Column(
        modifier.heightIn(min = 58.dp).clip(shape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised)
            .then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, shape) else Modifier)
            .clickable(role = Role.RadioButton, onClick = onClick)
            .semantics { this.selected = selected; contentDescription = lengthDescription }
            .testTag(tag ?: "length-${if (minutes == Math.floor(minutes)) minutes.toInt().toString() else minutes.toString()}").padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
    ) {
        if (caption != null) Text(caption, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = if (selected) Vmk.colors.primary else Vmk.colors.textSecondary, maxLines = 1)
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
            val f = com.videomk.app.core.StatusFix(fix)
            FixChip(f.label(), f.description(), Modifier.testTag("photoFixChip")) { composer.setLength(fix) }
        }
    }
}

@Composable
private fun MoreOptions(composer: ComposerViewModel, o: CreateOptions, caps: com.videomk.app.core.Capabilities, open: Boolean, onOpen: (Boolean) -> Unit, onLanguage: () -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    val openState = stringResource(if (open) R.string.create_state_expanded else R.string.create_state_collapsed)
    val captionsState = stringResource(if (o.captions) R.string.create_state_on else R.string.create_state_off)
    Column(Modifier.fillMaxWidth().clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClickLabel = stringResource(if (open) R.string.create_collapse_more else R.string.create_expand_more)) { onOpen(!open) }
                .padding(horizontal = 16.dp, vertical = 8.dp).semantics(mergeDescendants = true) { stateDescription = openState }.testTag("optionsMenu"),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.create_more_options), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
                if (!open) Text(CreatePlatforms.moreSummary(o, caps), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
            }
            Icon(if (open) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null, tint = Vmk.colors.text)
        }
        if (open) Column(Modifier.fillMaxWidth()) {
            Box(Modifier.fillMaxWidth().size(1.dp).background(Vmk.colors.outline))
            Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Overline(stringResource(R.string.create_look))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LookSwatch(stringResource(R.string.create_look_auto), stringResource(R.string.create_look_auto_desc), null, o.look == null, Modifier.weight(1f).testTag("look-auto")) { composer.updateOptions(o.copy(look = null)) }
                    for (l in VideoLook.entries) LookSwatch(l.displayName(), l.displayName(), l, o.look == l, Modifier.weight(1f).testTag("look-${l.wire}")) { composer.updateOptions(o.copy(look = l)) }
                }
            }
            Box(Modifier.fillMaxWidth().size(1.dp).background(Vmk.colors.outline))
            Row(
                Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Switch, onClickLabel = stringResource(R.string.create_subtitles)) { composer.updateOptions(o.copy(captions = !o.captions)) }.padding(horizontal = 16.dp)
                    .semantics(mergeDescendants = true) { stateDescription = captionsState }.testTag("subtitlesRow"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Icon(Icons.Filled.ClosedCaption, null, tint = Vmk.colors.text)
                Text(stringResource(R.string.create_subtitles), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f))
                Switch(checked = o.captions, onCheckedChange = null, colors = SwitchDefaults.colors(checkedTrackColor = Vmk.colors.gradientStart, checkedThumbColor = Vmk.colors.onPrimary, uncheckedTrackColor = Vmk.colors.surface3, uncheckedBorderColor = Vmk.colors.outline))
            }
            Box(Modifier.fillMaxWidth().padding(horizontal = 16.dp).size(1.dp).background(Vmk.colors.outline))
            Row(
                Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.Button, onClickLabel = stringResource(R.string.create_language_desc), onClick = onLanguage).padding(horizontal = 16.dp).testTag("languageRow"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Icon(Icons.Filled.Language, null, tint = Vmk.colors.text)
                Text(stringResource(R.string.create_language), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text)
                Text(CreatePlatforms.languageLabel(o, caps), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f), maxLines = 1, textAlign = androidx.compose.ui.text.style.TextAlign.End, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                Icon(Icons.Filled.ChevronRight, null, tint = Vmk.colors.textSecondary)
            }
            Column(Modifier.padding(horizontal = 16.dp, vertical = 14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Overline(stringResource(R.string.create_format))
                val bigText = LocalDensity.current.fontScale >= 1.3f
                FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), maxItemsInEachRow = if (bigText) 2 else 4) {
                    for (id in listOf("16:9", "9:16", "1:1", "4:5")) {
                        val a = caps.aspect(id)
                        FormatTile(id, CreatePlatforms.aspectName(id, caps), ready = a?.ready == true, beta = a?.beta == true, selected = o.aspect == id, Modifier.weight(1f), tall = bigText) {
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
    val tileDescription = stringResource(if (!ready) R.string.create_format_desc_soon else if (beta) R.string.create_format_desc_beta else R.string.create_format_desc, label, id)
    Box(
        modifier.then(if (tall) Modifier.heightIn(min = 110.dp) else Modifier.aspectRatio(1f)).alpha(if (ready) 1f else 0.6f).clip(shape).background(if (selected) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised)
            .then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, shape) else Modifier)
            .clickable(enabled = ready, role = Role.RadioButton, onClick = onClick)
            .semantics { this.selected = selected; contentDescription = tileDescription }.testTag("format-$id"),
    ) {
        if (!ready || beta) Text(stringResource(if (ready) R.string.create_beta else R.string.create_soon), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.textSecondary, modifier = Modifier.align(Alignment.TopEnd).padding(6.dp))
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
    val createLabel = stringResource(R.string.create_create_video)
    val boxState = if (checking) stringResource(R.string.create_state_checking)
        else if (ready) pluralStringResource(R.plurals.create_state_ready, credits, credits)
        else stringResource(if (hasFix) R.string.create_state_not_ready_fix else R.string.create_state_not_ready, reason)
    Box(
        Modifier.fillMaxWidth().heightIn(min = 54.dp).clip(shape).then(if (ready || checking) Modifier.background(Vmk.gradientNow) else Modifier.background(Vmk.colors.surface3))
            .clickable(role = Role.Button, onClickLabel = if (ready) createLabel else stringResource(R.string.create_explain_not_ready), onClick = onClick)
            .semantics { contentDescription = createLabel; stateDescription = boxState }.testTag("sendButton"),
        contentAlignment = Alignment.Center,
    ) {
        val c = if (ready || checking) Vmk.colors.onPrimary else Vmk.colors.textSecondary
        Row(Modifier.padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (checking) CircularProgressIndicator(Modifier.size(20.dp), color = c, strokeWidth = 2.dp)
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
