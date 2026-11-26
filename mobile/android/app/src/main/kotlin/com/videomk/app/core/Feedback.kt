package com.videomk.app.core

/** Where in the app the message was written (the `context` field of `POST /users/{userId}/feedback`, docs/FEEDBACK.md). */
enum class FeedbackContext(val wire: String) { Settings("settings"), AfterVideo("after_video"), RatingPrompt("rating_prompt") }

/** The optional chip: `idea`, `problem` or `other`. No chip selected means the field is left out. */
enum class FeedbackKind(val wire: String) { Idea("idea"), Problem("problem"), Other("other") }

sealed interface FeedbackResult {
    data object Sent : FeedbackResult
    /** 429: gently ask them to try again later. */
    data object RateLimited : FeedbackResult
    /** 400: the server did not accept the text. */
    data object Invalid : FeedbackResult
    /** No connection (or a timeout). */
    data object Offline : FeedbackResult
    /** Anything else (5xx, an expired session...). */
    data object Failed : FeedbackResult
}

/** `POST /users/{userId}/feedback`. The real one is [ApiClient]; tests use a fake. */
interface FeedbackApi {
    suspend fun sendFeedback(text: String, kind: FeedbackKind?, context: FeedbackContext): FeedbackResult
}

/** The text rules: 3 to 2000 characters after trimming (the server enforces the same limits). */
object FeedbackRules {
    const val MIN = 3
    const val MAX = 2000
    fun clean(text: String): String = text.trim()
    fun isValid(text: String): Boolean = clean(text).length in MIN..MAX
    /** What the field accepts: the typed text, cut at [MAX] characters. */
    fun clamp(text: String): String = if (text.length > MAX) text.take(MAX) else text
}

/** What the person typed, kept in memory for as long as the app lives so a failed send, a closed sheet or a rotation never loses it. Cleared only after a successful send. */
class FeedbackDraft {
    var text: String = ""
    var kind: FeedbackKind? = null
    fun clear() { text = ""; kind = null }
}

sealed interface FeedbackStage {
    data object Editing : FeedbackStage
    data object Sending : FeedbackStage
    data object Sent : FeedbackStage
    /** The send failed; the text is still in the draft. */
    data class Failed(val reason: FeedbackResult) : FeedbackStage
}

/** The sheet's logic: one send at a time, the draft kept on every failure and cleared on success. */
class FeedbackFlow(private val api: FeedbackApi?, val draft: FeedbackDraft, val context: FeedbackContext) {
    private val _stage = kotlinx.coroutines.flow.MutableStateFlow<FeedbackStage>(FeedbackStage.Editing)
    val stage: kotlinx.coroutines.flow.StateFlow<FeedbackStage> = _stage

    val canSend: Boolean get() = _stage.value !is FeedbackStage.Sending && FeedbackRules.isValid(draft.text)

    fun edit(text: String) { draft.text = FeedbackRules.clamp(text); if (_stage.value is FeedbackStage.Failed) _stage.value = FeedbackStage.Editing }
    fun pick(kind: FeedbackKind?) { draft.kind = kind }

    suspend fun send() {
        if (!canSend) return
        _stage.value = FeedbackStage.Sending
        val r = try { api?.sendFeedback(draft.text, draft.kind, context) ?: FeedbackResult.Failed } catch (e: kotlinx.coroutines.CancellationException) { _stage.value = FeedbackStage.Editing; throw e } catch (e: Exception) { FeedbackResult.Failed }
        if (r == FeedbackResult.Sent) { draft.clear(); _stage.value = FeedbackStage.Sent } else _stage.value = FeedbackStage.Failed(r)
    }
}
