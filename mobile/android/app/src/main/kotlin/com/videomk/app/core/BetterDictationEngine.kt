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
    /** The input level since the last call, 0..1 (for the live bars). Recorders that cannot say answer 0. */
    fun level(): Double = 0.0
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

    // Visible feedback (docs/DICTATION_FEEDBACK_2026-11-28.md): phase machine, real mic level, the clip kept in memory for Retry.
    private val _voice = MutableStateFlow(VoiceFeedback())
    val voice: StateFlow<VoiceFeedback> = _voice.asStateFlow()
    private val meter = LevelMeter()
    private val _bars = MutableStateFlow(meter.heights())
    /** The bars of the live waveform, newest last; updated about 25 times a second while recording. */
    val bars: StateFlow<List<Double>> = _bars.asStateFlow()
    private val _inserted = MutableStateFlow(false)
    /** True for a moment after the better text arrived (the screen highlights the text). */
    val inserted: StateFlow<Boolean> = _inserted.asStateFlow()
    /** Spoken by the screen (TalkBack live region / announce): called with the key of [VoiceFeedback.announcement]. */
    var announce: ((String, VoiceFeedback) -> Unit)? = null
    /** The phone's own recognizer is the one listening (no level to show): the panel draws a pulsing mic. */
    val usesClip: Boolean get() = recording || clip != null || _voice.value.phase == VoicePhase.Transcribing
    private var clip: Pair<ByteArray, Double>? = null
    private var clock: Job? = null
    private var timeout: Job? = null
    private var attempt = 0
    private var limitFlag = false

    private fun voice(e: VoiceEvent) {
        val before = _voice.value.announcement
        _voice.value = _voice.value.apply(e)
        val after = _voice.value
        if (after.announcement != before && after.announcement != null) announce?.invoke(after.announcement!!, after)
    }
    private fun startClock() {
        clock?.cancel()
        clock = scope.launch {
            var frame = 0
            while (true) {
                delay(1000L / DictationFeedback.METER_FPS)
                frame++
                if (recording) { meter.push(recorder.level()); _bars.value = meter.heights() }
                if (frame % (DictationFeedback.METER_FPS / 4) == 0) voice(VoiceEvent.Tick(now()))
            }
        }
    }
    private fun stopClock() { val p = _voice.value.phase; if (p == VoicePhase.Idle || p == VoicePhase.Inserted) { clock?.cancel(); clock = null } }

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
        voice(VoiceEvent.Request); meter.reset(); _bars.value = meter.heights()
        val c = caps()
        // not offered, not wanted, or the microphone permission is not there (the native path explains that): the native engine alone
        if (service() == null || c == null || !BetterDictationRules.uses(c, preferred()) || permission != DictationPlan.Permission.Granted) {
            native.start(currentText, permission); refresh()
            if (native.isListening) { voice(VoiceEvent.Granted(now(), 300)); startClock() } else voice(VoiceEvent.Denied)
            return
        }

        native.start(currentText, permission)           // the live preview
        if (!native.isListening) native.clearHint()     // no recognizer here: record anyway, without a preview
        val f = File(tempDir(), "dictation-${UUID.randomUUID()}.m4a")
        val ok = try { f.parentFile?.mkdirs(); recorder.start(f) } catch (e: Throwable) { false }
        if (!ok) {
            runCatching { f.delete() }
            if (!native.isListening) native.start(currentText, permission)   // nothing is recording and no preview: let the native path say why
            refresh()
            if (native.isListening) { voice(VoiceEvent.Granted(now(), 300)); startClock() } else voice(VoiceEvent.Denied)
            return
        }
        recording = true; file = f; startedAt = now()
        val limit = DictationFeedback.effectiveLimit(c.limitSeconds.toInt(), c.secondsLeft)
        voice(VoiceEvent.Granted(now(), limit)); startClock()
        limitJob = scope.launch { delay(limit * 1000L); limitHit = true; stop() }
        refresh()
    }

    override fun stop() {
        val f = file
        if (!recording || f == null) { native.stop(); refresh(); if (_voice.value.phase == VoicePhase.Recording) { voice(VoiceEvent.Cancel); stopClock() }; return }
        limitJob?.cancel(); limitJob = null
        val usable = try { recorder.stop() } catch (e: Throwable) { false }
        recording = false; file = null
        native.stop()
        val maxSeconds = caps()?.limitSeconds ?: DictationCaps.HARD_MAX_SECONDS
        val seconds = minOf((now() - startedAt) / 1000.0, maxSeconds)
        val byteLimit = caps()?.byteLimit ?: DictationCaps.HARD_MAX_BYTES
        _working.value = true; pendingFile = f; limitFlag = limitHit
        voice(VoiceEvent.Stop(now()))
        refresh()
        // read the clip into memory and delete the file at once (whatever happens); the bytes stay only until the upload ends, or Retry
        val draft = base
        upload = scope.launch {
            val data = withContext(io) { readClip(f, usable) }
            if (data == null || data.isEmpty() || data.size > byteLimit || service() == null) { finish(DictateResult.Failure(BetterFailure.Failed), draft, limitFlag); return@launch }
            clip = data to seconds
            send()
        }
    }

    private fun readClip(f: File, usable: Boolean): ByteArray? = try { if (usable) f.readBytes() else null } catch (e: Throwable) { null } finally { runCatching { f.delete() } }

    /** Sends the kept clip. A hiccup (network, server, 60 s without an answer) shows Retry; other failures end as before. */
    private fun send() {
        val (data, seconds) = clip ?: return
        val mine = ++attempt; val draft = base; val limit = limitFlag
        upload?.cancel(); timeout?.cancel()
        timeout = scope.launch {
            delay(DictationFeedback.TIMEOUT_AFTER_S * 1000L)
            if (mine == attempt && _voice.value.phase == VoicePhase.Transcribing) { attempt++; upload?.cancel(); failedRetryable() }
        }
        upload = scope.launch {
            val s = service()
            val result = if (s == null) DictateResult.Failure(BetterFailure.Failed) else try { withContext(io) { s.dictate(DictationClip(data, seconds, listOf(language()), draft)) } }
                catch (e: kotlinx.coroutines.CancellationException) { throw e } catch (e: Throwable) { DictateResult.Failure(BetterFailure.Failed) }
            if (mine != attempt) return@launch
            timeout?.cancel()
            if (result is DictateResult.Failure && result.reason.isRetryable) { failedRetryable(); return@launch }
            finish(result, draft, limit)
        }
    }

    private fun failedRetryable() { voice(VoiceEvent.Fail("network")) }
    /** "Retry" on the failed panel: the same clip goes up again. */
    fun retry() {
        if (_voice.value.phase != VoicePhase.Failed || clip == null) return
        voice(VoiceEvent.Retry(now())); send()
    }
    /** "Use phone dictation": give up on the clip; the words the phone heard stay and the usual line says so. */
    fun useDeviceDictation() {
        if (_voice.value.phase != VoicePhase.Failed) return
        finish(DictateResult.Failure(BetterFailure.Failed), base, limitFlag)
    }
    /** The person's Cancel. Recording: the clip is thrown away and the field goes back to what it was. Transcribing: stop waiting, the phone's words stay. */
    fun discard() {
        val wasRecording = recording
        limitJob?.cancel(); limitJob = null; timeout?.cancel(); timeout = null; upload?.cancel(); upload = null; attempt++
        if (recording) runCatching { recorder.abort() }
        file?.let { runCatching { it.delete() } }; pendingFile?.let { runCatching { it.delete() } }; pendingFile = null
        recording = false; file = null; clip = null; _working.value = false
        native.release()
        if (wasRecording) onText?.invoke(base)
        voice(VoiceEvent.Cancel); stopClock(); refresh()
    }

    private fun finish(result: DictateResult, draft: String, limit: Boolean) {
        _working.value = false; upload = null; pendingFile = null; clip = null; timeout?.cancel(); timeout = null
        val r = BetterResolution.resolve(draft, nativeWrote, textProvider?.invoke() ?: nativeWrote, result, limit)
        r.id?.let { ids.add(it) }
        r.write?.let { onText?.invoke(it) }
        native.release()            // a late transcript of the preview must not overwrite the better text
        _note.value = r.note
        if (r.id != null) {
            voice(VoiceEvent.Ok); _inserted.value = true
            scope.launch { delay(1300); _inserted.value = false; voice(VoiceEvent.Dismiss); stopClock() }
        } else {
            val p = _voice.value.phase
            if (p == VoicePhase.Failed) voice(VoiceEvent.Dismiss) else if (p == VoicePhase.Transcribing) voice(VoiceEvent.Cancel)
            stopClock()
        }
        refresh()
    }

    /** The text was sent or discarded: throw any clip away, upload nothing, and let nothing land in the field afterwards. */
    fun abandon() {
        limitJob?.cancel(); limitJob = null; upload?.cancel(); upload = null
        if (recording) runCatching { recorder.abort() }
        file?.let { runCatching { it.delete() } }; pendingFile?.let { runCatching { it.delete() } }; pendingFile = null
        recording = false; file = null; clip = null; timeout?.cancel(); timeout = null; attempt++; _working.value = false; _note.value = null
        native.release(); voice(VoiceEvent.Cancel); voice(VoiceEvent.Dismiss); stopClock(); refresh()
    }

    /** The screen is going away for good. */
    override fun release() { abandon(); native.release() }
}
