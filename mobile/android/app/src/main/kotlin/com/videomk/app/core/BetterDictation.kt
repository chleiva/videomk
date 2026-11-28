package com.videomk.app.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// "Better dictation" (Pro and Max): the phone records a clip, the server turns it into text. Pure rules and the request body live here (tested without a microphone);
// the recorder and the screen are elsewhere. docs/SPEECH_TO_TEXT_2026-11-28.md sections 9 and 10, docs/BETTER_DICTATION_CLIENTS_2026-11-28.md.
// Same rules as the web and iPhone clients. Nothing here logs or stores audio.

/** `capabilities.dictation`. */
data class DictationCaps(
    val premium: Boolean = false, val available: Boolean = false, val paused: Boolean = false, val secondsLeft: Int? = null,
    val maxClipSeconds: Double = HARD_MAX_SECONDS, val maxClipBytes: Int = HARD_MAX_BYTES, val requiresPlan: String? = null,
) {
    /** Better dictation can be used now: the plan has it, it is not paused, seconds are left. */
    val isUsable: Boolean get() = available && !paused
    /** The Options sheet shows the small "Better dictation with Pro" line: the plan lacks it and says which plan has it. */
    val showsUpgradeHint: Boolean get() = !premium && requiresPlan != null
    /** The recording stops by itself here: the server's limit, never over 6 minutes. */
    val limitSeconds: Double get() = minOf(maxClipSeconds, HARD_MAX_SECONDS)
    val byteLimit: Int get() = minOf(maxClipBytes, HARD_MAX_BYTES)

    companion object {
        const val HARD_MAX_SECONDS = 360.0
        const val HARD_MAX_BYTES = 3 * 1024 * 1024

        /** Lenient: anything that is not an object is "not offered" (null). */
        fun fromJson(o: JsonObject?): DictationCaps? {
            if (o == null) return null
            return DictationCaps(
                premium = o.bool("premium") ?: false, available = o.bool("available") ?: false, paused = o.bool("paused") ?: false,
                secondsLeft = o.int("seconds_left_today"), maxClipSeconds = o.num("max_clip_seconds")?.takeIf { it > 0 } ?: HARD_MAX_SECONDS,
                maxClipBytes = o.int("max_clip_bytes")?.takeIf { it > 0 } ?: HARD_MAX_BYTES, requiresPlan = o.str("requires_plan"),
            )
        }
    }
}

object BetterDictationRules {
    const val PREFERENCE_KEY = "vmk.better_dictation"
    /** The mic uses Better dictation: offered by the server, wanted by the person (default on). */
    fun uses(caps: DictationCaps?, preferred: Boolean): Boolean = preferred && (caps?.isUsable ?: false)
    /** The prompt sent with a clip: the last 400 characters of the draft, nothing when it is blank. */
    fun prompt(draft: String): String? = draft.trim().takeIf { it.isNotEmpty() }?.takeLast(400)
}

/** Every id that produced text, sent as `dictation_ids` on the next create: at most 20 (the newest are kept), no repeats, only 32 hex characters. */
class DictationIds {
    private val items = ArrayList<String>()
    val list: List<String> get() = items.toList()
    fun add(id: String) {
        if (id.length != 32 || !id.all { it in '0'..'9' || it in 'a'..'f' || it in 'A'..'F' } || id in items) return
        items.add(id)
        while (items.size > MAXIMUM) items.removeAt(0)
    }
    fun clear() = items.clear()
    companion object { const val MAXIMUM = 20 }
}

/**
 * Where the better text goes: [base] is the field when recording started, [native] what the live preview last wrote (the field held exactly that).
 * Field unchanged since: the dictated span is replaced by the better text on top of the base (words are not doubled). Edited by hand meanwhile: the person's
 * text wins (null = write nothing); the id is still kept, the clip was paid. No preview: a plain append. Blank text: null.
 */
fun placeBetterText(base: String, native: String, field: String, better: String): String? {
    if (better.isBlank() || field != native) return null
    return DictationText.compose(base, better)
}

/** The short line to show after a fallback (a string resource is chosen from it by the screen). */
enum class BetterNote { Quota, Limit, Failed }

enum class BetterFailure {
    Plan, Quota, TooLong, Failed, Paused, BadAudio, Auth, Network;

    /** What the app says: nothing for plan, paused and auth (the person did nothing wrong and nothing useful can be said). */
    val note: BetterNote? get() = when (this) {
        Quota -> BetterNote.Quota
        TooLong -> BetterNote.Limit
        Failed, Network, BadAudio -> BetterNote.Failed
        Plan, Paused, Auth -> null
    }

    companion object {
        /** What the server answered (pure). */
        fun from(status: Int, body: String?): BetterFailure {
            val code = body?.let { runCatching { parseObject(it).str("code") }.getOrNull() }
            when (code) {
                "dictation_plan" -> return Plan
                "dictation_quota" -> return Quota
                "dictation_too_long" -> return TooLong
                "dictation_paused" -> return Paused
                "bad_audio" -> return BadAudio
            }
            return when (status) { 429 -> Quota; 413 -> TooLong; 503 -> Paused; 401, 403 -> Auth; else -> Failed }
        }
    }
}

class DictationClip(val audio: ByteArray, val seconds: Double, val languages: List<String>, val prompt: String? = null, val mime: String = MIME) {
    /** The JSON body: base64 audio, `mime`, `seconds` (one decimal), `languages` (at most 4), `prompt` (the last 400 characters of the draft, when there is one). */
    fun body(): JsonObject = buildJsonObject {
        put("audio", java.util.Base64.getEncoder().encodeToString(audio))
        put("mime", mime)
        put("seconds", Math.round(seconds * 10) / 10.0)
        put("languages", JsonArray(languages.take(4).map { JsonPrimitive(it) }))
        BetterDictationRules.prompt(prompt.orEmpty())?.let { put("prompt", it) }
    }
    companion object { const val MIME = "audio/mp4" }
}

data class DictationAnswer(val id: String, val text: String, val seconds: Double = 0.0, val secondsLeft: Int? = null) {
    companion object {
        fun fromJson(o: JsonObject?): DictationAnswer? {
            val id = o?.str("id") ?: return null
            val text = o.str("text") ?: return null
            return DictationAnswer(id, text, o.num("seconds") ?: 0.0, o.int("seconds_left_today"))
        }
    }
}

sealed interface DictateResult {
    data class Success(val answer: DictationAnswer) : DictateResult
    data class Failure(val reason: BetterFailure) : DictateResult
}

/** The call that sends a clip. Never throws: every failure is a typed result and the caller falls back to the native text. */
interface DictationService {
    suspend fun dictate(clip: DictationClip): DictateResult
}

/**
 * What to do when a clip's upload ends, pure: the text to write (null = leave the field), the id to remember (only when text came back) and the line to say.
 * Any failure leaves the field exactly as the native engine wrote it. [limitHit]: the recording was stopped by the 6 minute limit, which the person is told either way.
 */
data class BetterResolution(val write: String?, val id: String?, val note: BetterNote?) {
    companion object {
        fun resolve(base: String, native: String, field: String, result: DictateResult, limitHit: Boolean): BetterResolution = when (result) {
            is DictateResult.Success -> BetterResolution(
                write = placeBetterText(base, native, field, result.answer.text),
                id = result.answer.id.takeIf { result.answer.text.isNotBlank() },
                note = if (limitHit) BetterNote.Limit else null,
            )
            is DictateResult.Failure -> BetterResolution(null, null, if (result.reason == BetterFailure.Quota) BetterNote.Quota else if (limitHit) BetterNote.Limit else result.reason.note)
        }
    }
}
