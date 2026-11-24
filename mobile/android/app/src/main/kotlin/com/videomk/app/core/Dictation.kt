package com.videomk.app.core

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
                    microphone == Permission.Denied -> "Microphone access is off for videomk, so use the microphone key on your keyboard instead."
                    speech == Permission.Denied -> "Speech recognition is off for videomk, so use the microphone key on your keyboard instead."
                    !recognizerAvailable -> "Speech recognition isn't available on this phone, so use the microphone key on your keyboard instead."
                    else -> "Tap the microphone key on your keyboard to dictate."
                }
                return UseKeyboard(why)
            }
            if (microphone == Permission.Denied) return Blocked("Allow microphone access for videomk in Settings, or turn on voice typing in your keyboard settings.")
            if (speech == Permission.Denied) return Blocked("Allow speech recognition for videomk in Settings, or turn on voice typing in your keyboard settings.")
            return Blocked("Dictation isn't available right now. You can turn on voice typing in your keyboard settings, or type your idea.")
        }
    }
}
