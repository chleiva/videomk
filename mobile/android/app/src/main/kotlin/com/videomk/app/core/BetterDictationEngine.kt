package com.videomk.app.core

import com.videomk.app.core.DictationEngine.State
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.UUID

/** Records one clip (AAC in MP4, mono, 16 kHz, 32 kbps) into a file. The Android one is `MediaRecorderClip`; tests use a fake. */
interface ClipRecorder {
    /** False when the phone does not let us record now (for instance the microphone is held by the recognizer): the native engine alone then carries on. */
    fun start(file: File): Boolean
    /** Ends the recording; false when the clip is not usable. */
    fun stop(): Boolean
    /** Throws the recording away. */
    fun abort()
}

/**
 * "Better dictation" (Pro and Max). The Create screen talks to this instead of the native engine; it has the same surface ([DictationEngine]).
 *
 * While recording, the native recognizer keeps running as a live preview and as the fallback (if the phone does not let both hold the microphone, whichever fails
 * simply drops out: no recorder = native alone; no preview = the clip is still recorded). On Stop the clip is uploaded; the returned text replaces the preview on top of
 * the text that was there before (or is appended when there was no preview), never over a field the person edited ([placeBetterText]). Any error leaves the native text in
 * the field. The audio lives in one temp file that is deleted as soon as it is read; it is never logged. Main thread only. No Android classes in here: tested on the JVM.
 */
class BetterDictationEngine(
    private val native: DictationEngine,
    private val recorder: ClipRecorder,
    private val scope: CoroutineScope,
    private val tempDir: () -> File,
    private val service: () -> DictationService?,
    private val caps: () -> DictationCaps?,
    private val preferred: () -> Boolean,
    private val language: () -> String,
    private val now: () -> Long = System::currentTimeMillis,
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : DictationEngine {
    private val _state = MutableStateFlow<State>(State.Idle)
    override val state: StateFlow<State> = _state.asStateFlow()
    private val _working = MutableStateFlow(false)
    /** The clip is being turned into text ("Improving the text..."). */
    val working: StateFlow<Boolean> = _working.asStateFlow()
    private val _note = MutableStateFlow<BetterNote?>(null)
    /** One line after a fallback or the 6 minute stop; the screen shows it for a few seconds, then calls [clearNote]. */
    val note: StateFlow<BetterNote?> = _note.asStateFlow()
    /** Every clip that produced text; sent as `dictation_ids` with the next create and cleared when the video is accepted. */
    val ids = DictationIds()

    override var onText: ((String) -> Unit)? = null
    override var textProvider: (() -> String)? = null
    override var onKeyboardFallback: (() -> Unit)?
        get() = native.onKeyboardFallback
        set(v) { native.onKeyboardFallback = v }

    private var recording = false
    private var file: File? = null
    private var startedAt = 0L
    private var base = ""
    private var nativeWrote = ""
    private var limitHit = false
    private var limitJob: Job? = null
    private var upload: Job? = null
    private var pendingFile: File? = null   // the clip being uploaded, deleted by whatever ends it

    init {
        native.onText = { text -> nativeWrote = text; onText?.invoke(text) }
        native.textProvider = { textProvider?.invoke() ?: "" }
        scope.launch { native.state.collect { refresh() } }
    }

    override val isListening: Boolean get() = recording || native.isListening

    private fun refresh() { _state.value = if (recording) State.Listening else native.state.value }

    fun clearNote() { _note.value = null }
    fun clearIds() = ids.clear()
    override fun clearHint() { native.clearHint(); refresh() }

    override fun start(currentText: String, permission: DictationPlan.Permission) {
        if (isListening || _working.value) return
        _note.value = null; limitHit = false
        base = currentText; nativeWrote = currentText
        val c = caps()
        // not offered, not wanted, or the microphone permission is not there (the native path explains that): the native engine alone
        if (service() == null || c == null || !BetterDictationRules.uses(c, preferred()) || permission != DictationPlan.Permission.Granted) { native.start(currentText, permission); refresh(); return }

        native.start(currentText, permission)           // the live preview
        if (!native.isListening) native.clearHint()     // no recognizer here: record anyway, without a preview
        val f = File(tempDir(), "dictation-${UUID.randomUUID()}.m4a")
        val ok = try { f.parentFile?.mkdirs(); recorder.start(f) } catch (e: Throwable) { false }
        if (!ok) {
            runCatching { f.delete() }
            if (!native.isListening) native.start(currentText, permission)   // nothing is recording and no preview: let the native path say why
            refresh(); return
        }
        recording = true; file = f; startedAt = now()
        val limitMs = (c.limitSeconds * 1000).toLong()
        limitJob = scope.launch { delay(limitMs); limitHit = true; stop() }
        refresh()
    }

    override fun stop() {
        val f = file
        if (!recording || f == null) { native.stop(); refresh(); return }
        limitJob?.cancel(); limitJob = null
        val usable = try { recorder.stop() } catch (e: Throwable) { false }
        recording = false; file = null
        native.stop()
        val maxSeconds = caps()?.limitSeconds ?: DictationCaps.HARD_MAX_SECONDS
        val seconds = minOf((now() - startedAt) / 1000.0, maxSeconds)
        val byteLimit = caps()?.byteLimit ?: DictationCaps.HARD_MAX_BYTES
        val (draft, limit) = base to limitHit
        _working.value = true; pendingFile = f
        refresh()
        upload = scope.launch {
            val result = withContext(io) { send(f, usable, seconds, draft, byteLimit) }
            finish(result, draft, limit)
        }
    }

    /** Reads the clip, deletes the file at once (whatever happens), and uploads. Nothing is logged. */
    private suspend fun send(f: File, usable: Boolean, seconds: Double, draft: String, byteLimit: Int): DictateResult {
        val data = try { if (usable) f.readBytes() else null } catch (e: Throwable) { null } finally { runCatching { f.delete() } }
        val s = service()
        if (data == null || data.isEmpty() || data.size > byteLimit || s == null) return DictateResult.Failure(BetterFailure.Failed)
        return try { s.dictate(DictationClip(data, seconds, listOf(language()), draft)) }
        catch (e: kotlinx.coroutines.CancellationException) { throw e }
        catch (e: Throwable) { DictateResult.Failure(BetterFailure.Failed) }
    }

    private fun finish(result: DictateResult, draft: String, limit: Boolean) {
        _working.value = false; upload = null; pendingFile = null
        val r = BetterResolution.resolve(draft, nativeWrote, textProvider?.invoke() ?: nativeWrote, result, limit)
        r.id?.let { ids.add(it) }
        r.write?.let { onText?.invoke(it) }
        native.release()            // a late transcript of the preview must not overwrite the better text
        _note.value = r.note
        refresh()
    }

    /** The text was sent or discarded: throw any clip away, upload nothing, and let nothing land in the field afterwards. */
    fun abandon() {
        limitJob?.cancel(); limitJob = null; upload?.cancel(); upload = null
        if (recording) runCatching { recorder.abort() }
        file?.let { runCatching { it.delete() } }; pendingFile?.let { runCatching { it.delete() } }; pendingFile = null
        recording = false; file = null; _working.value = false; _note.value = null
        native.release(); refresh()
    }

    /** The screen is going away for good. */
    override fun release() { abandon(); native.release() }
}
