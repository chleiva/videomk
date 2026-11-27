package com.videomk.app.ui

import android.app.Application
import android.content.ContentResolver
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.runtime.mutableStateListOf
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.videomk.app.DebugHooks
import com.videomk.app.core.Brief
import com.videomk.app.core.CreateCapsule
import com.videomk.app.core.CreateCapsule.Event as E
import com.videomk.app.core.CreateSubmit
import com.videomk.app.core.DeckApi
import com.videomk.app.core.DeckAttachment
import com.videomk.app.core.DeckJourney
import com.videomk.app.core.DeckOptions
import com.videomk.app.core.DeckPick
import com.videomk.app.core.DeckState
import com.videomk.app.core.DeckUploader
import com.videomk.app.core.Txt
import com.videomk.app.R
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.PhotoIntake
import com.videomk.app.core.PlatformChip
import com.videomk.app.core.CreatePlatforms
import com.videomk.app.core.PickedCache
import com.videomk.app.core.PickedSource
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.prepareInOrder
import com.videomk.app.data.DictationController
import com.videomk.app.core.Answer
import com.videomk.app.core.ApiError
import com.videomk.app.core.Capabilities
import com.videomk.app.core.CreateDefaults
import com.videomk.app.core.CreateErrors
import com.videomk.app.core.CreatePrefs
import com.videomk.app.core.CreateStop
import com.videomk.app.core.IntakeApi
import com.videomk.app.core.IntakeCheck
import com.videomk.app.core.IntakeRequest
import com.videomk.app.core.IntakeResult
import com.videomk.app.core.QuestionFlow
import com.videomk.app.core.SubmitOutcome
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.PhotoMeta
import com.videomk.app.data.PhotoExif
import com.videomk.app.data.PhotoPrep
import com.videomk.app.data.PhotoSettings
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.util.UUID

class AttachedPhoto(val id: String = UUID.randomUUID().toString(), val data: ByteArray, val thumbnail: Bitmap?, val meta: PhotoMeta? = null)

/** What the composer hands over when the user sends: the text, the prepared photos and (parallel to them) what was read from each original. */
class Outgoing(val brief: String, val photos: List<ByteArray>, val meta: List<PhotoMeta?>, val libraryIds: List<String> = emptyList(), val deckId: String? = null, val deckTitle: String? = null)

/**
 * Everything about the video being composed: the text, the length and look, the attached photos (up to 100) and dictation.
 * Lives in the ViewModelStore, so a rotation keeps the half-typed brief, the photos and a running dictation.
 */
class ComposerViewModel(app: Application) : AndroidViewModel(app) {
    var text by mutableStateOf("")
    var options by mutableStateOf(CreateOptions())
    val photos: SnapshotStateList<AttachedPhoto> = mutableStateListOf()
    /** Bumps when dictation wants the text field focused (the keyboard's own mic is the fallback). */
    var focusRequests by mutableIntStateOf(0)
        private set

    val dictation = DictationController(app).also { d ->
        d.onText = { text = it }
        d.onKeyboardFallback = { focusRequests++ }
    }

    /** Photos being prepared in the current batch (the "Preparing N of M" text) and how many of them are finished. */
    var preparing by mutableIntStateOf(0)
        private set
    var prepared by mutableIntStateOf(0)
        private set
    /** A short message about the last selection (photos left out, photos that couldn't be read). Cleared by the next selection or send. */
    var notice by mutableStateOf<String?>(null)
        private set

    var copied by mutableIntStateOf(0)
        private set
    private val cacheRoot = java.io.File(app.cacheDir, "picked")
    private val cache = PickedCache(java.io.File(cacheRoot, "session")).also { PickedCache.cleanLeftovers(cacheRoot) }   // an app start removes what a crashed session left
    private val settings = PhotoSettings(app)
    private val copyLock = kotlinx.coroutines.sync.Mutex()
    private var unreadable = 0
    private val prepLock = kotlinx.coroutines.sync.Mutex()   // batches queue up, so at most PREP_PARALLELISM photos are ever in flight

    val loading: Int get() = preparing - prepared
    /** Photos picked from My media (they count towards the same 100 as the phone's photos). */
    val library: SnapshotStateList<MediaPhoto> = mutableStateListOf()
    val totalPhotos: Int get() = photos.size + loading + library.size
    val remaining: Int get() = maxOf(0, PhotoLimits.MAX_PHOTOS - totalPhotos)
    /** The most My media photos the picker may hold right now: what is left for them, counting the ones already chosen. */
    val libraryRoom: Int get() = maxOf(0, PhotoLimits.MAX_PHOTOS - photos.size - loading)

    /** The picker's answer: exactly this selection replaces the library photos (never beyond the 100 total). */
    fun setLibrary(list: List<MediaPhoto>) { if (list.isNotEmpty()) attachment.photosChosen(); library.clear(); library.addAll(list.distinctBy { it.id }.take(libraryRoom)) }

    /** "Make a video from this": adds to the library photos already chosen. */
    fun addLibrary(list: List<MediaPhoto>) { setLibrary(library + list) }

    fun removeLibrary(id: String) { library.removeAll { it.id == id } }

    fun requestFocus() { focusRequests++ }

    /** The Add photos sheet is open (null: closed). [tab] 0 is This phone, 1 is My media. */
    class AddPhotosRequest(val tab: Int)
    var addPhotosRequest by mutableStateOf<AddPhotosRequest?>(null); private set
    fun openAddPhotos(tab: Int?) { addPhotosRequest = AddPhotosRequest(tab ?: 0) }
    fun closeAddPhotos() { addPhotosRequest = null }
    fun flagLimit() { notice = com.videomk.app.core.AddPhotosLogic.LIMIT_MESSAGE }

    /** A tapped example prompt: fills the field and the length, keeps the cursor in the field, never sends. */
    fun useExample(text: String, minutes: Double?) {
        this.text = text
        if (minutes != null) options = options.copy(minutes = minutes)
        requestFocus()
    }

    fun applyDebugDefaults(minutes: Double?) { if (minutes != null) options = options.copy(minutes = minutes) }

    fun addPhotos(resolver: ContentResolver, uris: List<Uri>) =
        enqueue(uris, PickedSource { uri -> resolver.openInputStream(uri) })

    fun addPhotoFiles(paths: List<String>) =
        enqueue(paths, PickedSource { path -> java.io.FileInputStream(path) })

    /**
     * Keeps the first selected photos that fit in the room left and tells how many were left out. Then, at once (the gallery's read grant is only
     * valid for a while), each original is streamed into a private cache file a couple at a time; after that the files are prepared a couple at a
     * time off the main thread, each source file deleted as soon as its photo is prepared. Only the prepared JPEG and a small preview are kept.
     */
    private fun <T> enqueue(items: List<T>, source: PickedSource<T>) {
        if (items.isNotEmpty()) attachment.photosChosen()   // photos and a presentation are different stories: the last choice wins
        val plan = PhotoIntake.plan(items.size, remaining)
        if (items.isEmpty()) return
        notice = if (plan.leftOut > 0) PhotoIntake.leftOutMessage(plan.leftOut) else null
        if (plan.accepted == 0) return
        val batch = items.take(plan.accepted)
        if (loading == 0) { preparing = 0; prepared = 0; copied = 0; unreadable = 0 }
        preparing += batch.size
        viewModelScope.launch {
            val files = ArrayList<java.io.File?>(batch.size)
            copyLock.withLock {
                prepareInOrder(batch, PhotoLimits.PREP_PARALLELISM, prepare = { item -> withContext(Dispatchers.IO) { cache.copy(item, source) } }) { _, f ->
                    files += f; copied += 1
                }
            }
            prepLock.withLock { prepareInOrder(
                files, PhotoLimits.PREP_PARALLELISM,
                prepare = { f ->
                    withContext(Dispatchers.Default) {
                        if (f == null) null else try {
                            val meta = PhotoExif.read(f, settings.policy)   // from the original, before the pixels are re-encoded without any metadata
                            PhotoPrep.jpeg(f.readBytes())?.let { AttachedPhoto(data = it, thumbnail = PhotoPrep.thumbnail(it), meta = meta) }
                        } catch (e: Exception) { null } finally { f.delete() }
                    }
                },
            ) { _, photo ->
                if (photo != null && photos.size < PhotoLimits.MAX_PHOTOS) photos.add(photo) else unreadable++
                prepared += 1
                if (loading == 0) {
                    if (unreadable > 0) notice = listOfNotNull(notice, PhotoIntake.unreadableMessage(unreadable)).joinToString(" ")
                    cleanupIfIdle()
                }
            } }
        }
    }

    /** Copying counts as half of preparing a photo, so the number moves from the first copy on. */
    val preparingText: String get() = PhotoIntake.preparingText((copied + prepared) / 2, preparing)

    private fun cleanupIfIdle() { if (loading == 0) cache.endSession() }

    fun removePhoto(id: String) { photos.removeAll { it.id == id }; cleanupIfIdle() }

    val canSend: Boolean get() = Brief.isValid(text) || deckState is DeckState.Ready

    /** Hands back what to send and clears the composer, ready for the next request. */
    fun takeForSend(): Outgoing { val out = peekForSend(); clearAfterSend(); return out }

    /** What would be sent, leaving the draft in place (Create keeps it until generate has answered). */
    fun peekForSend(): Outgoing {
        dictation.stop()
        val policy = settings.policy   // a switch turned off after the photos were prepared still wins
        val ready = deck.ready
        return Outgoing(
            text, photos.map { it.data }, photos.map { it.meta?.limitedTo(policy)?.takeIf { m -> !m.isEmpty } }, library.map { it.id },
            deckId = ready?.id, deckTitle = ready?.let { DeckOptions.title((deckState as? DeckState.Ready)?.name) ?: Txt.s(R.string.deck_title_fallback) },
        )
    }

    fun clearAfterSend() {
        lookNotice = null
        photos.clear(); library.clear(); deck.cancel()
        cleanupIfIdle()
        notice = null
        text = ""
    }

    // ---- the Create flow: options, capabilities, the request check and its sheets

    enum class CreateSheetKind { None, Checking, Asking, Summary, Stop }

    /** What the server offers (landscape 16:9 at 1080p only until the capabilities endpoint exists). */
    var caps by mutableStateOf(Capabilities.FALLBACK)
        private set
    private var touched = false
    private var capsLoaded = false
    /** The run between the tap on Create and its answer: the state machine of core/CreateSubmit.kt (CreateCapsule) is the one source of "is something running". */
    var run by mutableStateOf(CreateCapsule.State())
        private set
    private fun fire(e: E) { run = CreateCapsule.next(run, e) }
    val checking: Boolean get() = run.phase == CreateSubmit.Phase.Checking
    var sheetKind by mutableStateOf(CreateSheetKind.None)
        private set
    var stop by mutableStateOf<CreateStop?>(null)
        private set
    var flow: QuestionFlow? = null
        private set
    var flowVersion by mutableIntStateOf(0)
        private set
    var summaryBrief by mutableStateOf<kotlinx.serialization.json.JsonObject?>(null)
        private set
    var summaryLoading by mutableStateOf(false)
        private set
    private var checkJob: kotlinx.coroutines.Job? = null
    private var submitFn: (suspend (kotlinx.serialization.json.JsonObject?) -> SubmitOutcome)? = null
    private var intakeApi: IntakeApi? = null
    private var storedPrefs: CreatePrefs? = null

    /** A choice the person made on the Create screen (a remembered default no longer overrides it when the capabilities arrive). */
    fun updateOptions(o: CreateOptions) { options = CreateDefaults.priced(o, caps); touched = true }

    /** The length chip (or a one-tap fix): from now on a platform pick keeps this length and only shows its recommendation. */
    fun setLength(minutes: Double) { options = CreateDefaults.priced(DeckOptions.chooseLength(options, minutes), caps); touched = true; lengthChosen = true }
    var lengthChosen = false
        private set

    /** A platform chip: its format and resolution, and its recommended length unless a length was chosen since this screen opened. */
    fun selectPlatform(chip: PlatformChip) {
        // a platform's recommended length never goes over what the plan makes (the server refuses a longer one, it does not shorten it)
        val o = CreatePlatforms.select(options, chip, lengthChosen || deckState is DeckState.Ready, caps.presets)
        options = CreateDefaults.priced(o.copy(minutes = CreateDefaults.withinPlan(o.minutes, caps), resolution = o.resolution.takeIf { caps.resolution(it)?.available != false } ?: options.resolution), caps); touched = true
    }

    /** "Make another" from a finished video: Create opens with the idea filled in and one choice changed (core/Remix.kt). Nothing is sent. */
    fun startRemix(prompt: String, kind: com.videomk.app.core.RemixKind) {
        text = prompt
        com.videomk.app.core.Remix.apply(options, kind, caps)?.let { options = it; touched = true; if (kind == com.videomk.app.core.RemixKind.Cut30) lengthChosen = true }
    }

    /** The Create screen opened: start from what this person used last time (or the first-time defaults). */
    fun openCreate(stored: CreatePrefs?) {
        storedPrefs = stored; touched = false; lengthChosen = false
        options = CreateDefaults.resolve(stored, caps)
        deck.ready?.let { options = DeckOptions.onReady(options, it) }   // reopened with a presentation still attached
        sheetKind = CreateSheetKind.None; cancelCheck(); stop = null; lookNotice = null
    }

    // ---- the chosen look (docs/CREATE_API.md "Video look"): only when the server lists `looks.look`

    /** One line right above the pills when something about the look was changed for the person (photos sent it back to Auto, a look moved the length). */
    var lookNotice by mutableStateOf<String?>(null)
        private set
    /** What is attached decides which looks can be made (the person's own photos or slides are the pictures of the video). */
    val attached: com.videomk.app.core.LookRules.Attached get() = com.videomk.app.core.LookRules.Attached(photos = totalPhotos > 0, deck = deckState.attached)
    val lookHasCast: Boolean get() = com.videomk.app.core.LookRules.hasCast(options.lookChoice, caps.lookPicker)

    /** A tap on a look tile; the length moves when the look needs a longer video, and the line above the pills says so (the returned line is also read out). */
    fun pickLook(id: String): String? {
        val looks = caps.lookPicker ?: return null
        lookNotice = null
        options = options.copy(lookChoice = com.videomk.app.core.LookRules.select(id, options.lookChoice, looks, attached)); touched = true
        return applyLookLength()?.let { com.videomk.app.core.LookRules.movedLine(it, options.lookChoice, looks) }?.also { lookNotice = it }
    }

    /** A tap on a face. Two or three are a conversation, which needs its own shortest length: the returned line says when the length was moved. */
    fun toggleCast(member: String): Pair<com.videomk.app.core.LookRules.CastTap, String?> {
        val looks = caps.lookPicker ?: return com.videomk.app.core.LookRules.CastTap.Full to null
        val (choice, tap) = com.videomk.app.core.LookRules.toggle(member, options.lookChoice, looks)
        options = options.copy(lookChoice = choice); touched = true
        val line = if (tap == com.videomk.app.core.LookRules.CastTap.Added) applyLookLength()?.let { com.videomk.app.core.LookRules.movedLine(it, choice, looks) } else null
        return tap to line
    }

    fun setLookExtra(id: String, on: Boolean) { options = options.copy(lookChoice = com.videomk.app.core.LookRules.setExtra(id, on, options.lookChoice)); touched = true }

    /** The length is shorter than the chosen look (or a conversation) needs: the length to use instead (never one the plan does not make). A presentation keeps its own length. */
    fun lookLengthNudge(): com.videomk.app.core.LookRules.LengthNudge? =
        if (deckState.attached) null else com.videomk.app.core.LookRules.lengthNudge(options.lookChoice, caps.lookPicker, options.minutes, caps.presets.filter { caps.lengthAllowed(it) })

    private fun applyLookLength(): com.videomk.app.core.LookRules.LengthNudge? {
        val nudge = lookLengthNudge() ?: return null
        options = CreateDefaults.priced(options.copy(minutes = nudge.minutes), caps)
        return nudge
    }

    /** Photos or a presentation were attached or removed (or the server's list changed): a look that is not made from them goes back to Auto, with one line saying so. Returns that line. */
    fun syncLook(): String? {
        val was = options.lookChoice
        val r = com.videomk.app.core.LookRules.normalized(was, caps.lookPicker, attached)
        if (r.choice != was) options = options.copy(lookChoice = r.choice)
        val label = caps.lookPicker?.option(was.look)?.label
        if (r.reset != null && label != null) { lookNotice = com.videomk.app.core.LookRules.resetLine(r.reset, label); return lookNotice }
        if (!attached.any && r.choice == was && lookNoticeIsReset) lookNotice = null
        return null
    }
    private val lookNoticeIsReset: Boolean get() = lookNotice != null && options.lookChoice.isAuto

    /** The line was read: the next touch of the pill it sits above takes it away. */
    fun dismissLookNotice() { lookNotice = null }

    /** Stops a running request check (nothing exists on the server yet, so this is clean). Does nothing while the send itself is in flight. */
    private fun cancelCheck() { checkJob?.cancel(); fire(E.Cancel) }

    fun applyCapabilities(c: Capabilities) {
        caps = c; capsLoaded = true
        if (!touched) options = CreateDefaults.resolve(storedPrefs, c)
        else options = CreateDefaults.priced(options.copy(minutes = if (options.useSuggestedLength) options.minutes else CreateDefaults.withinPlan(options.minutes, c), style = if (c.lookPicker != null) "auto" else options.style), c)
        waitingDeck?.let { if (c.deck != null) { waitingDeck = null; addDeck(it, true) } }
    }

    /** Anything entered that Cancel should ask about. */
    val hasDraft: Boolean get() = text.isNotBlank() || totalPhotos > 0 || deckState.attached

    fun discardDraft() { dictation.stop(); text = ""; photos.clear(); library.clear(); deck.cancel(); notice = null; cleanupIfIdle(); sheetKind = CreateSheetKind.None; cancelCheck() }

    private fun request(answers: List<Answer>) = IntakeRequest(text, options, totalPhotos, answers)

    /**
     * Create was tapped: the request check (when this server has it), then [submit] with the brief. Questions, a kind refusal or a pause open their sheets instead.
     * A failed or slow check never blocks: it just proceeds without a brief.
     */
    fun create(intake: IntakeApi?, submitter: suspend (kotlinx.serialization.json.JsonObject?) -> SubmitOutcome, onAccepted: () -> Unit) {
        if (run.phase != CreateSubmit.Phase.Idle) return
        dictation.stop()
        intakeApi = intake; submitFn = submitter; acceptedFn = onAccepted; inlineError = null
        if (intake == null || !caps.intake || deckState.attached) { finish(null); return }   // the request check is about a description and photos: a presentation brings its own story
        fire(E.Tap(willCheck = true))
        checkJob = viewModelScope.launch {
            // the capsule on the screen says "Checking your request" and offers Cancel for as long as this takes (the check gives up by itself after a few seconds)
            val r = IntakeCheck(intake).run(request(emptyList()))
            handle(r)
        }
    }

    private fun handle(r: IntakeResult) {
        when (r) {
            is IntakeResult.Ok -> { sheetKind = CreateSheetKind.None; finish(r.brief) }
            is IntakeResult.Questions -> { fire(E.CheckAsks); flow = QuestionFlow(r.questions); flowVersion++; sheetKind = CreateSheetKind.Asking }
            else -> {
                stop = CreateErrors.fromCheck(r); sheetKind = if (stop != null) CreateSheetKind.Stop else CreateSheetKind.None
                if (stop == null) finish(null) else fire(E.CheckRefuses)
            }
        }
    }

    val submitting: Boolean get() = run.phase == CreateSubmit.Phase.Starting
    /** Shown inline on Create when the send failed for lack of a connection; the draft is intact. */
    var inlineError by mutableStateOf<String?>(null)
        private set
    private var acceptedFn: (() -> Unit)? = null

    /** Sends and waits for generate: closes (via onAccepted) only when it was accepted. */
    private fun finish(brief: kotlinx.serialization.json.JsonObject?) {
        val send = submitFn ?: return
        if (submitting) return
        fire(if (checking) E.CheckDone else E.Tap(willCheck = false)); inlineError = null
        viewModelScope.launch {
            val r = try { send(brief) } catch (e: kotlinx.coroutines.CancellationException) { fire(E.SendFailed); throw e } catch (e: Exception) { SubmitOutcome.Offline(ApiError.Network.message) }
            when (r) {
                is SubmitOutcome.Accepted -> { fire(E.Accepted); clearAfterSend(); sheetKind = CreateSheetKind.None; stop = null; acceptedFn?.invoke() }
                // every other end restores the form exactly as it was: the prompt, the photos and the options are untouched
                is SubmitOutcome.Stopped -> if (showStop(r.error)) fire(E.SendRefused) else { fire(E.SendFailed); inlineError = ApiError.Server.message }
                is SubmitOutcome.Offline -> { fire(E.SendFailed); sheetKind = CreateSheetKind.None; inlineError = r.message }
            }
        }
    }

    fun clearInlineError() { inlineError = null }

    /** generate itself answered blocked or paused (rare: the check already ran): the same kind sheets. */
    fun showStop(e: ApiError): Boolean { val s = CreateErrors.fromGenerate(e) ?: return false; stop = CreateErrors.withFix(s, caps, e); sheetKind = CreateSheetKind.Stop; return true }

    /** The one-tap fix of a "too long for your plan" refusal: that length, and the sheet closes on the form (the person taps Create when ready). */
    fun useShorter(minutes: Double) { setLength(minutes); dismissSheet() }

    /** The slow-check skeleton's "Make it now": stop waiting and go on without a brief. */
    fun skipCheck() { checkJob?.cancel(); sheetKind = CreateSheetKind.None; finish(null) }

    /** Closes whatever sheet is open; during the request check this is Cancel (the form comes back exactly as it was). */
    fun dismissSheet() { cancelCheck(); sheetKind = CreateSheetKind.None; stop = null }

    fun useSuggestion(s: String) { text = s; dismissSheet() }

    // questions
    fun choose(optionId: String) { flow?.choose(optionId); afterAnswer() }
    fun answerOther(t: String) { flow?.other(t); afterAnswer() }
    fun skipQuestion() { flow?.skip(); afterAnswer() }
    fun youDecide() { flow?.youDecide(); afterAnswer() }
    fun questionBack() { flow?.back(); flowVersion++ }
    fun makeItNow() { flow?.makeItNow(); afterAnswer() }
    fun editAnswer(questionId: String) { flow?.edit(questionId); summaryBrief = null; flowVersion++; sheetKind = CreateSheetKind.Asking }

    private fun afterAnswer() {
        flowVersion++
        val f = flow ?: return
        if (!f.inSummary) return
        if (f.allSkipped()) { sheetKind = CreateSheetKind.None; finish(null); return }   // nothing to confirm: start at once
        sheetKind = CreateSheetKind.Summary
        summaryBrief = null; summaryLoading = true
        checkJob?.cancel()
        checkJob = viewModelScope.launch {
            val r = IntakeCheck(intakeApi).run(request(f.answerList()))
            summaryLoading = false
            when (r) { is IntakeResult.Ok -> summaryBrief = r.brief; else -> CreateErrors.fromCheck(r)?.let { stop = it; sheetKind = CreateSheetKind.Stop } }
        }
    }

    /** The summary's Create video. */
    fun confirmSummary() { sheetKind = CreateSheetKind.None; finish(summaryBrief) }

    // ---- a presentation (PowerPoint or PDF): only where the server lists it; a video is made from photos or from a presentation, never both

    var deckState by mutableStateOf<DeckState>(DeckState.Idle)
        private set
    private var minutesBeforeDeck: Double? = null
    private val deckRoot = java.io.File(app.cacheDir, "deck").also { DeckJourney.cleanLeftovers(it) }   // an app start removes what a killed process left
    val deck = DeckJourney(viewModelScope, deckRoot, onState = { onDeckState(it) })
    private val attachment = DeckAttachment(deck, { totalPhotos }, { photos.clear(); library.clear(); cleanupIfIdle(); notice = null })

    /** The real calls (or the debug fakes); the Create screen hands them over when it opens. */
    fun attachDeckApi(api: DeckApi?, uploader: DeckUploader?) = deck.attach(api, uploader)

    val deckVerticalWarning: Boolean get() = DeckOptions.verticalWarning(options, deckState.attached)

    /** A picked file. False when photos exist and [replacePhotos] is not set (nothing changed: the caller asks first). */
    fun addDeck(pick: DeckPick, replacePhotos: Boolean): Boolean {
        val c = caps.deck ?: return false
        dictation.stop()
        val ok = attachment.add(pick, c, replacePhotos)
        if (ok) { options = DeckOptions.landscape(options, caps); touched = true }   // slides are wide: 16:9 unless the person picks another shape later
        return ok
    }

    fun removeDeck() { deck.cancel() }

    /** Debug launches only: the pick waits for the capabilities (the feature exists only where the server lists it) and for the Create screen's api. */
    private var waitingDeck: DeckPick? = null
    fun addDeckWhenReady(pick: DeckPick) { if (caps.deck != null) addDeck(pick, true) else waitingDeck = pick }

    fun useSuggestedLength() { deck.ready?.let { options = DeckOptions.useSuggestion(options, it); touched = true } }

    fun useLandscape() { options = DeckOptions.landscape(options, caps); touched = true }

    private fun onDeckState(s: DeckState) {
        val before = deckState
        deckState = s
        if (s is DeckState.Ready) {
            if (before !is DeckState.Ready) { minutesBeforeDeck = options.minutes; options = DeckOptions.onReady(options, s.info) }
        } else if (before is DeckState.Ready || options.useSuggestedLength) {
            options = DeckOptions.onGone(options, minutesBeforeDeck); minutesBeforeDeck = null
        }
    }

    override fun onCleared() {
        deck.release()
        cache.endSession()
        dictation.release()
    }
}
