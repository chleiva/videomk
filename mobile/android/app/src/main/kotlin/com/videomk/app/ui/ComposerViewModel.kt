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
    var checking by mutableStateOf(false)
        private set
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
    fun updateOptions(o: CreateOptions) { options = o; touched = true }

    /** The length chip (or a one-tap fix): from now on a platform pick keeps this length and only shows its recommendation. */
    fun setLength(minutes: Double) { options = DeckOptions.chooseLength(options, minutes); touched = true; lengthChosen = true }
    var lengthChosen = false
        private set

    /** A platform chip: its format and resolution, and its recommended length unless a length was chosen since this screen opened. */
    fun selectPlatform(chip: PlatformChip) { options = CreatePlatforms.select(options, chip, lengthChosen || deckState is DeckState.Ready, caps.presets); touched = true }

    /** The Create screen opened: start from what this person used last time (or the first-time defaults). */
    fun openCreate(stored: CreatePrefs?) {
        storedPrefs = stored; touched = false; lengthChosen = false
        options = CreateDefaults.resolve(stored, caps)
        deck.ready?.let { options = DeckOptions.onReady(options, it) }   // reopened with a presentation still attached
        sheetKind = CreateSheetKind.None; checking = false; stop = null
    }

    fun applyCapabilities(c: Capabilities) {
        caps = c; capsLoaded = true
        if (!touched) options = CreateDefaults.resolve(storedPrefs, c)
        waitingDeck?.let { if (c.deck != null) { waitingDeck = null; addDeck(it, true) } }
    }

    /** Anything entered that Cancel should ask about. */
    val hasDraft: Boolean get() = text.isNotBlank() || totalPhotos > 0 || deckState.attached

    fun discardDraft() { dictation.stop(); text = ""; photos.clear(); library.clear(); deck.cancel(); notice = null; cleanupIfIdle(); sheetKind = CreateSheetKind.None; checking = false; checkJob?.cancel() }

    private fun request(answers: List<Answer>) = IntakeRequest(text, options, totalPhotos, answers)

    /**
     * Create was tapped: the request check (when this server has it), then [submit] with the brief. Questions, a kind refusal or a pause open their sheets instead.
     * A failed or slow check never blocks: it just proceeds without a brief.
     */
    fun create(intake: IntakeApi?, submitter: suspend (kotlinx.serialization.json.JsonObject?) -> SubmitOutcome, onAccepted: () -> Unit) {
        if (checking || submitting) return
        dictation.stop()
        intakeApi = intake; submitFn = submitter; acceptedFn = onAccepted; inlineError = null
        if (intake == null || !caps.intake || deckState.attached) { finish(null); return }   // the request check is about a description and photos: a presentation brings its own story
        checking = true
        checkJob = viewModelScope.launch {
            val r = IntakeCheck(intake).run(request(emptyList())) { if (checking) sheetKind = CreateSheetKind.Checking }
            checking = false
            handle(r)
        }
    }

    private fun handle(r: IntakeResult) {
        when (r) {
            is IntakeResult.Ok -> { sheetKind = CreateSheetKind.None; finish(r.brief) }
            is IntakeResult.Questions -> { flow = QuestionFlow(r.questions); flowVersion++; sheetKind = CreateSheetKind.Asking }
            else -> { stop = CreateErrors.fromCheck(r); sheetKind = if (stop != null) CreateSheetKind.Stop else CreateSheetKind.None; if (stop == null) finish(null) }
        }
    }

    var submitting by mutableStateOf(false)
        private set
    /** Shown inline on Create when the send failed for lack of a connection; the draft is intact. */
    var inlineError by mutableStateOf<String?>(null)
        private set
    private var acceptedFn: (() -> Unit)? = null

    /** Sends and waits for generate: closes (via onAccepted) only when it was accepted. */
    private fun finish(brief: kotlinx.serialization.json.JsonObject?) {
        val send = submitFn ?: return
        if (submitting) return
        submitting = true; inlineError = null
        viewModelScope.launch {
            val r = try { send(brief) } catch (e: kotlinx.coroutines.CancellationException) { submitting = false; throw e } catch (e: Exception) { SubmitOutcome.Offline(ApiError.Network.message) }
            submitting = false
            when (r) {
                is SubmitOutcome.Accepted -> { clearAfterSend(); sheetKind = CreateSheetKind.None; stop = null; acceptedFn?.invoke() }
                is SubmitOutcome.Stopped -> if (!showStop(r.error)) inlineError = ApiError.Server.message
                is SubmitOutcome.Offline -> { sheetKind = CreateSheetKind.None; inlineError = r.message }
            }
        }
    }

    fun clearInlineError() { inlineError = null }

    /** generate itself answered blocked or paused (rare: the check already ran): the same kind sheets. */
    fun showStop(e: ApiError): Boolean { val s = CreateErrors.fromGenerate(e) ?: return false; stop = s; sheetKind = CreateSheetKind.Stop; return true }

    /** The slow-check skeleton's "Make it now": stop waiting and go on without a brief. */
    fun skipCheck() { checkJob?.cancel(); checking = false; sheetKind = CreateSheetKind.None; finish(null) }

    fun dismissSheet() { checkJob?.cancel(); checking = false; sheetKind = CreateSheetKind.None; stop = null }

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
