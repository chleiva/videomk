package com.videomk.app.core

import com.videomk.app.R

/**
 * Which speech-recognition language to use. The recognizer must match the language being spoken: a Spanish speaker on an English
 * phone would otherwise get a garbled English transcript, which the server then can't recognise as Spanish.
 */
enum class DictationLanguage(val code: String, val title: String) {
    English("en", "English"), Spanish("es", "Español");

    /**
     * The best recognizer locale tag for this language: same region as the phone when available, else the first one offered,
     * else the largest audience (en-US, es-MX).
     */
    fun locale(region: String?, supported: List<String>): String {
        val mine = supported.filter { it.lowercase().startsWith("$code-") || it.lowercase() == code }
        if (region != null) mine.firstOrNull { it.uppercase().endsWith("-" + region.uppercase()) }?.let { return it }
        val preferred = if (this == English) "en-US" else "es-MX"
        return mine.firstOrNull { it == preferred } ?: mine.firstOrNull() ?: preferred
    }

    companion object {
        fun fromCode(code: String): DictationLanguage? = entries.firstOrNull { it.code == code }

        /** The saved choice if any, else the first supported language in the phone's preferred-language order, else English. */
        fun initial(saved: String?, preferred: List<String>): DictationLanguage {
            saved?.let { s -> fromCode(s)?.let { return it } }
            for (tag in preferred) {
                fromCode(tag.take(2).lowercase())?.let { return it }
            }
            return English
        }
    }
}

/**
 * What the mic button should do, decided from what the phone allows. Pure, so every combination is tested.
 * Order of preference: our own recognizer (live text) -> the keyboard's built-in dictation -> a clear way to turn one on.
 */
sealed interface DictationPlan {
    enum class Permission { Undetermined, Granted, Denied }

    /** Our recognizer (the system asks for any missing permission first). */
    data object UseApp : DictationPlan
    /** Focus the text field and point at the keyboard's own mic key. */
    data class UseKeyboard(val message: String) : DictationPlan
    /** Nothing usable: say how to fix it. */
    data class Blocked(val message: String) : DictationPlan

    companion object {
        /**
         * Android has one runtime permission for this (RECORD_AUDIO); pass it as both [speech] and [microphone] unless a platform
         * offers a separate speech permission.
         */
        fun decide(speech: Permission, microphone: Permission, recognizerAvailable: Boolean, keyboardDictationEnabled: Boolean): DictationPlan {
            val appCanWork = speech != Permission.Denied && microphone != Permission.Denied && recognizerAvailable
            if (appCanWork) return UseApp
            if (keyboardDictationEnabled) {
                val why = when {
                    microphone == Permission.Denied -> Txt.s(R.string.dictation_mic_off_keyboard)
                    speech == Permission.Denied -> Txt.s(R.string.dictation_speech_off_keyboard)
                    !recognizerAvailable -> Txt.s(R.string.dictation_unavailable_keyboard)
                    else -> Txt.s(R.string.dictation_tap_keyboard)
                }
                return UseKeyboard(why)
            }
            if (microphone == Permission.Denied) return Blocked(Txt.s(R.string.dictation_allow_mic))
            if (speech == Permission.Denied) return Blocked(Txt.s(R.string.dictation_allow_speech))
            return Blocked(Txt.s(R.string.dictation_unavailable))
        }
    }
}

/**
 * How dictated text joins what is already in the field. Pure (no microphone), so the append and rebase rules are unit tested.
 *
 * The text in the field when dictation starts is the BASE. The field always shows base + separator + the running segment; a segment that ends is folded
 * into the base ([fold]) and the next one starts empty, so nothing said is lost and nothing typed is overwritten. If the field no longer holds what we last
 * wrote, the person edited it by hand: the field becomes the new base ([Step.Rebased]) and the caller restarts the recognizer.
 */
class DictationText(startingWith: String) {
    sealed interface Step {
        data class Write(val text: String) : Step
        data object Rebased : Step
    }

    var base: String = startingWith
        private set
    private var expected: String = startingWith

    fun hear(segment: String, field: String): Step {
        if (field != expected) { base = field; expected = field; return Step.Rebased }
        val text = compose(base, segment)
        expected = text
        return Step.Write(text)
    }

    fun fold(segment: String, field: String): Step {
        val step = hear(segment, field)
        if (step is Step.Write) base = step.text
        return step
    }

    companion object {
        /** base + one space + segment; no space when the base is empty or ends with a new line, no doubling of trailing spaces, a blank segment changes nothing. */
        fun compose(base: String, segment: String): String {
            val seg = segment.trim()
            if (seg.isEmpty()) return base
            val b = base.trimEnd(' ', '\t')
            return if (b.isEmpty() || b.endsWith("\n")) b + seg else "$b $seg"
        }
    }
}

/**
 * When the recognizer may be started again and when dictation must stop. A recognizer session ends by itself after a pause, a result or an error such as
 * NO_MATCH / SPEECH_TIMEOUT; none of that may end the dictation. Only the person's Stop, the hard maximum, a long stretch with nothing said, or a recognizer
 * that keeps failing at once may. Clock-free: the caller passes milliseconds.
 */
class DictationRestartPolicy(
    private val maxMillis: Long = 5 * 60_000L,
    private val idleMillis: Long = 90_000L,
    private val maxRapidFailures: Int = 4,
) {
    enum class Action { Restart, StopTimeLimit, StopIdle, StopFailing }

    private var sessionStart = 0L
    private var lastText = 0L
    private var started = 0L
    private var rapid = 0

    fun sessionStarted(now: Long) { sessionStart = now; lastText = now; started = now; rapid = 0 }
    fun recognizerStarted(now: Long) { started = now }
    fun textArrived(now: Long) { lastText = now; rapid = 0 }

    /** [hadText]: this recognizer session produced any text. One that ends within a second without text is a quick failure (a busy or broken recognizer must not loop). */
    fun ended(hadText: Boolean, now: Long): Action {
        if (now - sessionStart >= maxMillis) return Action.StopTimeLimit
        if (hadText) { rapid = 0; return Action.Restart }
        if (now - started < 1_000) { rapid++; if (rapid >= maxRapidFailures) return Action.StopFailing } else rapid = 0
        if (now - lastText >= idleMillis) return Action.StopIdle
        return Action.Restart
    }

    companion object {
        /** SpeechRecognizer error codes that mean "nothing was said or understood": normal while the person thinks. */
        fun isSilence(error: Int): Boolean = error == 6 || error == 7   // ERROR_SPEECH_TIMEOUT, ERROR_NO_MATCH
        const val ERROR_RECOGNIZER_BUSY = 8
        const val ERROR_LANGUAGE_NOT_SUPPORTED = 12
        const val ERROR_LANGUAGE_UNAVAILABLE = 13
        /** Wait before starting the recognizer again: short, so little is missed, long enough not to hammer a busy service. */
        fun delayMillis(error: Int?): Long = if (error == ERROR_RECOGNIZER_BUSY) 1_000L else 300L
    }
}

/** The language dictation listens in: the app's own (`en` or `es`, what the Create screen and the requests use); the phone's region only picks the variant. */
object DictationLocale {
    fun tag(appLanguage: String, deviceTags: List<String>): String {
        val language = DictationLanguage.fromCode(appLanguage) ?: DictationLanguage.English
        val mine = deviceTags.filter { it.lowercase().startsWith(language.code) }
        val region = deviceTags.firstOrNull()?.let { runCatching { java.util.Locale.forLanguageTag(it).country }.getOrNull() }?.takeIf { it.isNotEmpty() }
        return language.locale(region, mine)
    }
}

/** The seam for a different engine (the paid "Better dictation" mode plugs in here). The Create screen only talks to this. */
interface DictationEngine {
    sealed interface State {
        data object Idle : State
        data object Starting : State
        data object Listening : State
        data class Unavailable(val message: String) : State
        data class KeyboardHint(val message: String) : State
    }

    val state: kotlinx.coroutines.flow.StateFlow<State>
    val isListening: Boolean
    /** Called with the whole field text every time dictation changes it. */
    var onText: ((String) -> Unit)?
    /** What the field holds right now; lets the engine notice hand edits and rebase instead of overwriting them. */
    var textProvider: (() -> String)?
    /** Called when we hand over to the keyboard's own dictation: the screen focuses the text field. */
    var onKeyboardFallback: (() -> Unit)?

    fun start(currentText: String, permission: DictationPlan.Permission)
    fun stop()
    fun clearHint()
    fun release()
}
