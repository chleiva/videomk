package com.videomk.app.data

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import android.view.inputmethod.InputMethodManager
import com.videomk.app.core.DictationLanguage
import com.videomk.app.core.DictationPlan
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
 * Main thread only (SpeechRecognizer requires it).
 */
class DictationController(context: Context) {
    sealed interface State {
        data object Idle : State
        data object Starting : State
        data object Listening : State
        data class Unavailable(val message: String) : State
        data class KeyboardHint(val message: String) : State
    }

    private val appContext = context.applicationContext
    private val handler = Handler(Looper.getMainLooper())
    private val _state = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = _state.asStateFlow()

    /** Called with the full text (what was already typed plus what was said) every time the recognizer updates. */
    var onText: ((String) -> Unit)? = null
    /** Called when we hand over to the keyboard's own dictation: the screen focuses the text field. */
    var onKeyboardFallback: (() -> Unit)? = null

    private var recognizer: SpeechRecognizer? = null
    private var base = ""
    private var gotText = false

    val isListening: Boolean get() = _state.value is State.Listening || _state.value is State.Starting

    /** No language menu: dictation follows the phone's first preferred language we support (English or Spanish). */
    private fun languageTag(): String {
        val locales = androidx.core.os.LocaleListCompat.getAdjustedDefault()
        val tags = (0 until locales.size()).mapNotNull { locales[it]?.toLanguageTag() }
        val language = DictationLanguage.initial(saved = null, preferred = tags)
        val region = locales[0]?.country?.takeIf { it.isNotEmpty() }
        return language.locale(region, tags.filter { it.lowercase().startsWith(language.code) })
    }

    fun toggleOrStart(currentText: String, permission: DictationPlan.Permission) {
        if (isListening) stop() else start(currentText, permission)
    }

    /** [permission]: the microphone permission as the caller found it (Android has one runtime permission for dictation). */
    fun start(currentText: String, permission: DictationPlan.Permission) {
        if (isListening) return
        _state.value = State.Starting
        try {
            val available = try { SpeechRecognizer.isRecognitionAvailable(appContext) } catch (e: Throwable) { false }
            when (val plan = DictationPlan.decide(permission, permission, available, keyboardDictationEnabled())) {
                is DictationPlan.Blocked -> { _state.value = State.Unavailable(plan.message); return }
                is DictationPlan.UseKeyboard -> { fallBackToKeyboard(plan.message); return }
                DictationPlan.UseApp -> Unit
            }
            base = if (currentText.isEmpty() || currentText.endsWith(" ")) currentText else "$currentText "
            gotText = false
            listen()
        } catch (e: Throwable) {
            Log.w(TAG, "dictation start failed", e)
            teardown()
            failOver(Txt.s(R.string.dictation_start_failed_keyboard), Txt.s(R.string.dictation_start_failed))
        }
    }

    private fun listen() {
        val r = SpeechRecognizer.createSpeechRecognizer(appContext) ?: throw IllegalStateException("no recognizer")
        recognizer = r
        r.setRecognitionListener(listener)
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag())
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, appContext.packageName)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        r.startListening(intent)
        _state.value = State.Listening
    }

    fun stop() {
        if (_state.value is State.Idle) return
        try { recognizer?.stopListening() } catch (e: Throwable) { Log.w(TAG, "stopListening failed", e) }
        // the recognizer delivers its final result and is then destroyed in the listener; make sure it does not linger if it never answers
        handler.postDelayed({ if (recognizer != null && _state.value is State.Idle) teardown() }, 2000)
        if (_state.value is State.Listening || _state.value is State.Starting) _state.value = State.Idle
    }

    fun clearHint() {
        val s = _state.value
        if (s is State.Unavailable || s is State.KeyboardHint) _state.value = State.Idle
    }

    /** Ends everything (the screen is going away). */
    fun release() {
        handler.removeCallbacksAndMessages(null)
        teardown()
        _state.value = State.Idle
    }

    private fun teardown() {
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

    private val listener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {}
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onEvent(eventType: Int, params: Bundle?) {}

        override fun onPartialResults(partialResults: Bundle?) = deliver(partialResults)

        override fun onResults(results: Bundle?) {
            deliver(results)
            finish()
        }

        override fun onError(error: Int) {
            Log.i(TAG, "recognizer error $error")
            val wasListening = _state.value is State.Listening
            teardown()
            if (!wasListening && _state.value is State.Idle) return   // the user already stopped it
            when (error) {
                SpeechRecognizer.ERROR_NO_MATCH, SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> _state.value = State.Idle   // the user said nothing: not an error
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY, SpeechRecognizer.ERROR_CLIENT -> _state.value = State.Idle
                SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ->
                    failOver(Txt.s(R.string.dictation_mic_off_keyboard), Txt.s(R.string.dictation_allow_mic))
                SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT, SpeechRecognizer.ERROR_SERVER ->
                    if (wasListening && gotText) _state.value = State.Idle
                    else failOver(Txt.s(R.string.dictation_network_keyboard), Txt.s(R.string.dictation_network))
                else -> failOver(Txt.s(R.string.dictation_error_keyboard), Txt.s(R.string.dictation_error))
            }
        }
    }

    private fun deliver(bundle: Bundle?) {
        val text = bundle?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.takeIf { it.isNotBlank() } ?: return
        gotText = true
        onText?.invoke(base + text)
    }

    private fun finish() {
        teardown()
        if (_state.value is State.Listening || _state.value is State.Starting) _state.value = State.Idle
    }

    /** True when some enabled keyboard offers voice typing (Gboard's microphone key, Samsung voice input...). */
    fun keyboardDictationEnabled(): Boolean = try {
        val imm = appContext.getSystemService(Context.INPUT_METHOD_SERVICE) as? InputMethodManager
        imm?.enabledInputMethodList?.any { info ->
            val voiceSubtype = (0 until info.subtypeCount).any { info.getSubtypeAt(it).mode.equals("voice", ignoreCase = true) }
            voiceSubtype || info.packageName == "com.google.android.inputmethod.latin" || info.packageName == "com.google.android.googlequicksearchbox"
        } ?: false
    } catch (e: Throwable) { false }

    companion object { private const val TAG = "Dictation" }
}
