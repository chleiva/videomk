package com.videomk.app.data

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import android.view.inputmethod.InputMethodManager
import com.videomk.app.core.DictationEngine
import com.videomk.app.core.DictationEngine.State
import com.videomk.app.core.DictationLanguage
import com.videomk.app.core.DictationLocale
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.DictationRestartPolicy
import com.videomk.app.core.DictationText
import com.videomk.app.core.Txt
import com.videomk.app.R
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Speech to text for the brief. Our own recognizer (android.speech.SpeechRecognizer) gives live partial text. If it can't be used
 * (permission denied, no recognition service on the phone, the microphone is busy) we fall back to the keyboard's own voice typing, or say how
 * to turn one on. Nothing in here may crash the app: every call into the platform is guarded and every failure ends in a message.
 *
 * It keeps listening through pauses: the recognizer is asked for long silence lengths, and when it ends by itself (a result, NO_MATCH, SPEECH_TIMEOUT, busy)
 * a new one is started after a short delay until the person taps Stop, 5 minutes pass, 90 seconds go by with nothing said, or it keeps failing at once.
 * Each recognised segment is APPENDED to the text already in the field ([DictationText]); text typed meanwhile is never overwritten.
 * The rules are pure and tested ([DictationText], [DictationRestartPolicy], [DictationLocale]).
 *
 * Main thread only (SpeechRecognizer requires it).
 */
class DictationController(context: Context) : DictationEngine {
    private val appContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private val _state = MutableStateFlow<State>(State.Idle)
    override val state: StateFlow<State> = _state.asStateFlow()

    override var onText: ((String) -> Unit)? = null
    override var textProvider: (() -> String)? = null
    override var onKeyboardFallback: (() -> Unit)? = null

    private var recognizer: SpeechRecognizer? = null
    private var text = DictationText("")
    private var policy = DictationRestartPolicy()
    private var lastWritten = ""
    private var segmentHadText = false  // the running recognizer has produced text
    private var gotText = false         // any recognizer of this session has
    private var language = DictationLanguage.English
    private var generation = 0          // callbacks of a recognizer we already replaced are ignored

    override val isListening: Boolean get() = _state.value is State.Listening || _state.value is State.Starting

    /** The app's language (what the Create screen is in and what requests say), not the phone's: a Spanish app on an English phone dictates in Spanish. */
    private fun languageTag(): String {
        val locales = androidx.core.os.LocaleListCompat.getAdjustedDefault()
        val tags = (0 until locales.size()).mapNotNull { locales[it]?.toLanguageTag() }
        language = DictationLanguage.fromCode(Txt.localeTag) ?: DictationLanguage.English
        return DictationLocale.tag(Txt.localeTag, tags)
    }

    fun toggleOrStart(currentText: String, permission: DictationPlan.Permission) {
        if (isListening) stop() else start(currentText, permission)
    }

    /** [permission]: the microphone permission as the caller found it (Android has one runtime permission for dictation). */
    override fun start(currentText: String, permission: DictationPlan.Permission) {
        if (isListening) return
        _state.value = State.Starting
        try {
            val available = try { SpeechRecognizer.isRecognitionAvailable(appContext) } catch (e: Throwable) { false }
            when (val plan = DictationPlan.decide(permission, permission, available, keyboardDictationEnabled())) {
                is DictationPlan.Blocked -> { _state.value = State.Unavailable(plan.message); return }
                is DictationPlan.UseKeyboard -> { fallBackToKeyboard(plan.message); return }
                DictationPlan.UseApp -> Unit
            }
            text = DictationText(currentText)
            lastWritten = currentText
            gotText = false
            policy = DictationRestartPolicy()
            policy.sessionStarted(SystemClock.elapsedRealtime())
            listen()
        } catch (e: Throwable) {
            Log.w(TAG, "dictation start failed", e)
            teardown()
            failOver(Txt.s(R.string.dictation_start_failed_keyboard), Txt.s(R.string.dictation_start_failed))
        }
    }

    private fun listen() {
        val r = SpeechRecognizer.createSpeechRecognizer(appContext) ?: throw IllegalStateException("no recognizer")
        generation++
        val mine = generation
        recognizer = r
        segmentHadText = false
        r.setRecognitionListener(listenerFor(mine))
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag())
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, appContext.packageName)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            // keep listening while the person thinks (the defaults end the session after about 1 to 2 seconds of quiet); some recognizers ignore these, hence the restart below
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, COMPLETE_SILENCE_MS)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, POSSIBLY_COMPLETE_SILENCE_MS)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, MINIMUM_LENGTH_MS)
        }
        policy.recognizerStarted(SystemClock.elapsedRealtime())
        r.startListening(intent)
        _state.value = State.Listening
    }

    override fun stop() {
        if (_state.value is State.Idle) return
        handler.removeCallbacks(restart)
        val r = recognizer
        _state.value = State.Idle
        if (r == null) return
        try { r.stopListening() } catch (e: Throwable) { Log.w(TAG, "stopListening failed", e) }
        // the recognizer delivers its final result (which still lands in the field) and is then destroyed in the listener; make sure it does not linger if it never answers
        val mine = generation
        handler.postDelayed({ if (generation == mine && recognizer != null) teardown() }, 2000)
    }

    override fun clearHint() {
        val s = _state.value
        if (s is State.Unavailable || s is State.KeyboardHint) _state.value = State.Idle
    }

    /** Ends everything (the screen is going away). */
    override fun release() {
        handler.removeCallbacksAndMessages(null)
        teardown()
        _state.value = State.Idle
    }

    private fun teardown() {
        generation++
        val r = recognizer
        recognizer = null
        if (r != null) {
            try { r.setRecognitionListener(null) } catch (e: Throwable) { /* ignore */ }
            try { r.cancel() } catch (e: Throwable) { /* ignore */ }
            try { r.destroy() } catch (e: Throwable) { /* ignore */ }
        }
    }

    private fun fallBackToKeyboard(message: String) {
        _state.value = State.KeyboardHint(message)
        onKeyboardFallback?.invoke()
    }

    private fun failOver(keyboardMessage: String, plainMessage: String) {
        if (keyboardDictationEnabled()) fallBackToKeyboard(keyboardMessage) else _state.value = State.Unavailable(plainMessage)
    }

    private val restart = Runnable {
        if (_state.value !is State.Listening) return@Runnable
        try { listen() } catch (e: Throwable) {
            Log.w(TAG, "dictation restart failed", e)
            teardown()
            if (gotText) _state.value = State.Idle else failOver(Txt.s(R.string.dictation_start_failed_keyboard), Txt.s(R.string.dictation_start_failed))
        }
    }

    private fun listenerFor(mine: Int) = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}

        override fun onPartialResults(partialResults: Bundle?) { if (mine == generation) deliver(partialResults, final = false) }

        override fun onResults(results: Bundle?) {
            if (mine != generation) return
            deliver(results, final = true)
            if (mine == generation) ended(error = null)     // a hand edit already started a new recognizer
        }

        override fun onError(error: Int) {
            if (mine != generation) return
            Log.i(TAG, "recognizer error $error")
            ended(error)
        }
    }

    /** Puts base + segment in the field; folds the segment into the base when it is final. A hand edit rebases and restarts the recognizer instead of being overwritten. */
    private fun deliver(bundle: Bundle?, final: Boolean) {
        val heard = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.takeIf { it.isNotBlank() } ?: return
        gotText = true
        segmentHadText = true
        policy.textArrived(SystemClock.elapsedRealtime())
        val field = textProvider?.invoke() ?: lastWritten
        when (val step = if (final) text.fold(heard, field) else text.hear(heard, field)) {
            is DictationText.Step.Write -> { lastWritten = step.text; onText?.invoke(step.text) }
            DictationText.Step.Rebased -> {
                lastWritten = field
                // what was said so far is in the field the person edited: start again from nothing
                if (_state.value is State.Listening) { teardown(); handler.removeCallbacks(restart); handler.postDelayed(restart, 100) }
            }
        }
    }

    /** The recognizer session ended (a result or an error). Keep going until the person stops, unless this is a real failure or a limit. */
    private fun ended(error: Int?) {
        val userStopped = _state.value !is State.Listening
        teardown()
        if (userStopped) return                                              // Stop: the final text has landed
        when (error) {
            null -> Unit
            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> { failOver(Txt.s(R.string.dictation_mic_off_keyboard), Txt.s(R.string.dictation_allow_mic)); return }
            DictationRestartPolicy.ERROR_LANGUAGE_NOT_SUPPORTED, DictationRestartPolicy.ERROR_LANGUAGE_UNAVAILABLE -> {
                // never quietly listen in another language: say so
                val name = language.title
                failOver(Txt.s(R.string.dictation_language_unavailable_keyboard, name), Txt.s(R.string.dictation_language_unavailable, name)); return
            }
            SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT, SpeechRecognizer.ERROR_SERVER -> if (!gotText) {
                failOver(Txt.s(R.string.dictation_network_keyboard), Txt.s(R.string.dictation_network)); return
            }
            else -> Unit    // NO_MATCH, SPEECH_TIMEOUT, RECOGNIZER_BUSY, CLIENT, an odd error after speech: the policy decides whether to go on
        }
        when (policy.ended(hadText = segmentHadText, now = SystemClock.elapsedRealtime())) {
            DictationRestartPolicy.Action.Restart -> { handler.removeCallbacks(restart); handler.postDelayed(restart, DictationRestartPolicy.delayMillis(error)) }
            DictationRestartPolicy.Action.StopTimeLimit, DictationRestartPolicy.Action.StopIdle -> _state.value = State.Idle
            DictationRestartPolicy.Action.StopFailing ->
                if (gotText) _state.value = State.Idle else failOver(Txt.s(R.string.dictation_error_keyboard), Txt.s(R.string.dictation_error))
        }
    }

    /** True when some enabled keyboard offers voice typing (Gboard's microphone key, Samsung voice input...). */
    fun keyboardDictationEnabled(): Boolean = try {
        val imm = appContext.getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
        imm?.enabledInputMethodList?.any { info ->
            val voiceSubtype = (0 until info.subtypeCount).any { info.getSubtypeAt(it).mode.equals("voice", ignoreCase = true) }
            voiceSubtype || info.packageName == "com.google.android.inputmethod.latin" || info.packageName == "com.google.android.googlequicksearchbox"
        } ?: false
    } catch (e: Throwable) { false }

    companion object {
        private const val TAG = "Dictation"
        private const val COMPLETE_SILENCE_MS = 8_000L
        private const val POSSIBLY_COMPLETE_SILENCE_MS = 6_000L
        private const val MINIMUM_LENGTH_MS = 15_000L
    }
}
