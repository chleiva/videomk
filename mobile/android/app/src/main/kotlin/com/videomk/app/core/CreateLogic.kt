package com.videomk.app.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import com.videomk.app.R

/** A "What is it for?" chip. [enabled] only when the server can make its format; the others are dimmed with "Soon". */
data class PlatformChip(
    val id: String, val label: String, val aspect: String, val resolution: String, val enabled: Boolean,
    val recommendedMinutes: Double? = null, val maxMinutes: Double? = null, val otherAspects: List<String> = emptyList(), val note: String? = null,
)

object CreatePlatforms {
    /** The built-in table of docs/UI_DESIGN.md section o; a server list for a platform overrides its format. */
    private fun builtIn() = listOf(
        PlatformInfo("youtube", "YouTube", "16:9", "1080p"), PlatformInfo("linkedin", "LinkedIn", "16:9", "1080p"), PlatformInfo("x", "X", "16:9", "1080p"),
        PlatformInfo("other", Txt.s(R.string.create_platform_other), "16:9", "1080p"),
        PlatformInfo("shorts", "Shorts · Reels · TikTok", "9:16", "1080p"), PlatformInfo("instagram_feed", "Instagram", "4:5", "1080p"),
    )

    /** Supported platforms first (in the table's order), then the ones that are "Soon". */
    fun chips(caps: Capabilities): List<PlatformChip> {
        // the server's entry decides the format, length advice and note; the built-in table only supplies the label and the order
        val base = builtIn().map { b -> caps.platforms.firstOrNull { it.id == b.id }?.let { it.copy(label = b.label) } ?: b }
        val all = base.map { p -> PlatformChip(p.id, p.label, p.aspect, p.resolution, caps.isReady(p.aspect) && caps.resolutions.any { it.id == p.resolution }, p.recommendedMinutes, p.maxMinutes, p.otherAspects.filter { caps.isReady(it) && it != p.aspect }, p.note) }
        return all.filter { it.enabled } + all.filter { !it.enabled }
    }

    fun chip(caps: Capabilities, id: String): PlatformChip? = chips(caps).firstOrNull { it.id == id }

    /**
     * Picking a platform sets its format and resolution, and its recommended length unless the person already chose a length on this screen
     * ([lengthChosen]); then their length stays and only the recommendation is shown. The length is the nearest preset the server offers.
     */
    fun select(o: CreateOptions, chip: PlatformChip, lengthChosen: Boolean = false, presets: List<Double> = Lengths.OLD_PRESETS): CreateOptions {
        if (!chip.enabled) return o
        val minutes = if (lengthChosen) o.minutes else chip.recommendedMinutes?.let { nearest(presets, it) } ?: o.minutes
        return o.copy(platform = chip.id, aspect = chip.aspect, resolution = chip.resolution, minutes = minutes)
    }

    private fun nearest(presets: List<Double>, m: Double): Double = presets.minByOrNull { Math.abs(it - m) } ?: m

    /** The platform's own limit when the chosen length is over it: "YouTube Shorts allows up to 2:20", with the longest preset that fits (null when none does). */
    data class OverMax(val text: String, val useMinutes: Double?)
    fun overMax(o: CreateOptions, caps: Capabilities): OverMax? {
        val c = chip(caps, o.platform)?.takeIf { it.enabled } ?: return null
        val max = c.maxMinutes ?: return null
        if (o.minutes <= max + 1e-9) return null
        return OverMax(Txt.s(R.string.create_over_max, c.label, Lengths.clock(max)), caps.presets.filter { it <= max + 1e-9 }.maxOrNull())
    }

    /** "Also works: Square, Landscape": other formats the platform accepts, each switches only the format. */
    fun alsoWorks(o: CreateOptions, caps: Capabilities): List<AspectInfo> {
        val c = chip(caps, o.platform)?.takeIf { it.enabled } ?: return emptyList()
        return c.otherAspects.mapNotNull { caps.aspect(it) }.filter { it.id != o.aspect }
    }

    /** The format was changed away from the platform's recommendation: the highlight goes and "Custom" shows. */
    fun isCustom(o: CreateOptions, caps: Capabilities): Boolean {
        val c = chip(caps, o.platform) ?: return true
        return !c.enabled || c.aspect != o.aspect || c.resolution != o.resolution
    }

    /** "YouTube · Landscape 16:9 · 1080p" (or "Custom · Vertical 9:16 · 720p"). */
    fun recommendation(o: CreateOptions, caps: Capabilities): String {
        val c = chip(caps, o.platform)
        if (!isCustom(o, caps) && c?.note != null) return "${c.label} · ${c.note}"   // the server's own words, e.g. "Portrait 4:5 · 1080p · about 1 min"
        val name = if (isCustom(o, caps)) Txt.s(R.string.create_custom) else c?.label ?: Txt.s(R.string.create_platform_other)
        return "$name · ${aspectText(o.aspect, caps)} · ${o.resolution}"
    }

    fun aspectText(aspect: String, caps: Capabilities): String = "${aspectName(aspect, caps)} $aspect"

    /** The server's (localized) label for a format, else the app's own name for it. */
    fun aspectName(aspect: String, caps: Capabilities): String = caps.aspect(aspect)?.label?.takeIf { it.isNotBlank() } ?: defaultLabel(aspect)
    fun defaultLabel(a: String): String = Txt.s(when (a) { "16:9" -> R.string.create_aspect_landscape; "9:16" -> R.string.create_aspect_vertical; "1:1" -> R.string.create_aspect_square; "4:5" -> R.string.create_aspect_portrait; else -> R.string.create_aspect_other })

    /** The "Change" link is only offered when there is a real choice. */
    fun canChangeFormat(caps: Capabilities): Boolean = caps.readyAspects.size > 1 || caps.resolutions.size > 1

    /** The one-line summary of More options: "Auto look · Subtitles on · Same language as description". */
    fun moreSummary(o: CreateOptions, caps: Capabilities): String {
        val look = o.look?.let { Txt.s(R.string.create_summary_look, it.displayName()) } ?: Txt.s(R.string.create_summary_look_auto)
        val lang = if (o.language == "auto") Txt.s(R.string.create_summary_same_language) else caps.languages.firstOrNull { it.id == o.language }?.label ?: languageName(o.language)
        return "$look · ${Txt.s(if (o.captions) R.string.create_summary_subtitles_on else R.string.create_summary_subtitles_off)} · $lang"
    }

    fun languageLabel(o: CreateOptions, caps: Capabilities): String = if (o.language == "auto") Txt.s(R.string.create_same_as_description) else caps.languages.firstOrNull { it.id == o.language }?.label ?: languageName(o.language)

    /** A language written in its own language; an id the app does not know is shown as it is. */
    fun languageName(id: String): String = when (id) { "en" -> "English"; "es" -> "Español"; else -> id }
}

/** What is remembered per person after a successful Create (prompt and photos never). */
data class CreatePrefs(val platform: String, val aspect: String, val resolution: String, val minutes: Double, val look: String?, val captions: Boolean, val language: String) {
    fun toJson(): String = buildJsonObject {
        put("platform", platform); put("aspect", aspect); put("resolution", resolution); put("minutes", minutes); look?.let { put("look", it) }; put("captions", captions); put("language", language)
    }.toString()

    companion object {
        fun of(o: CreateOptions) = CreatePrefs(o.platform, o.aspect, o.resolution, o.minutes, o.look?.wire, o.captions, o.language)
        fun fromJson(text: String?): CreatePrefs? = runCatching {
            val o = parseObject(text ?: return null)
            CreatePrefs(o.str("platform") ?: "other", o.str("aspect") ?: "16:9", o.str("resolution") ?: "1080p", o.num("minutes") ?: 3.0, o.str("look"), o.bool("captions") ?: true, o.str("language") ?: "auto")
        }.getOrNull()
    }
}

object CreateDefaults {
    /** First launch: Just a video, Landscape 16:9, 1080p, 3 min, Auto look, subtitles on, same language as the description. */
    val FIRST_TIME = CreateOptions()

    /**
     * The options to start Create with: the remembered ones, but never something the server no longer offers (a stored format that is gone falls back to the
     * first ready format, a stored resolution to the first listed, a language that is not listed to "auto", a length outside the range to the default).
     */
    fun resolve(stored: CreatePrefs?, caps: Capabilities): CreateOptions {
        if (stored == null) return FIRST_TIME.copy(aspect = caps.readyAspects.first().id.takeIf { caps.isReady("16:9") } ?: caps.readyAspects.first().id, resolution = firstRes(caps, "1080p"))
        val aspect = if (caps.isReady(stored.aspect)) stored.aspect else caps.readyAspects.first().id
        val res = if (caps.resolutions.any { it.id == stored.resolution }) stored.resolution else firstRes(caps, "1080p")
        val lang = if (stored.language == "auto" || caps.languages.any { it.id == stored.language }) stored.language else "auto"
        val minutes = stored.minutes.takeIf { m -> caps.presets.any { Math.abs(it - m) < 1e-9 } } ?: CreateOptions.DEFAULT_MINUTES.takeIf { it in caps.presets } ?: caps.presets.first()
        val platform = if (CreatePlatforms.chip(caps, stored.platform)?.enabled == true) stored.platform else "other"
        return CreateOptions(minutes, VideoLook.entries.firstOrNull { it.wire == stored.look }, stored.captions, platform, aspect, res, lang)
    }

    private fun firstRes(caps: Capabilities, preferred: String) = caps.resolutions.firstOrNull { it.id == preferred }?.id ?: caps.resolutions.first().id
}

/**
 * The request check with its budgets (docs/UI_DESIGN.md section o.3): nothing visible below [slowAfterMs]; between that and [giveUpMs] the sheet shows its skeleton
 * ([onSlow]); after [giveUpMs], or on any error, the answer is [IntakeResult.Ok] with no brief. A failed check never shows an error and never blocks a video.
 */
class IntakeCheck(private val api: IntakeApi?, private val slowAfterMs: Long = 2500, private val giveUpMs: Long = 8000) {
    suspend fun run(request: IntakeRequest, onSlow: () -> Unit = {}): IntakeResult {
        val a = api ?: return IntakeResult.Ok(null)
        return coroutineScope {
            val slow = launch { delay(slowAfterMs); onSlow() }
            try {
                withTimeoutOrNull(giveUpMs) { a.brief(request) } ?: IntakeResult.Ok(null)
            } catch (e: CancellationException) { throw e
            } catch (e: ApiError.Paused) { IntakeResult.Paused(e.text, e.retryAfterSeconds)
            } catch (e: ApiError.Blocked) { IntakeResult.Blocked(e.text)
            } catch (e: Exception) { IntakeResult.Ok(null)
            } finally { slow.cancel() }
        }
    }
}

/** The one-question-at-a-time flow: answers, back, skip, "You decide", "Make it now", progress and the final summary. */
class QuestionFlow(val questions: List<Question>) {
    private val answers = LinkedHashMap<String, Answer>()
    var index: Int = 0
        private set
    /** Editing one answer from the summary returns straight to the summary afterwards. */
    private var returnToSummary = false
    var inSummary: Boolean = false
        private set

    val current: Question? get() = if (inSummary) null else questions.getOrNull(index)
    val total: Int get() = questions.size
    val overline: String get() = overline(index)
    fun overline(i: Int): String = Txt.s(R.string.question_overline, i + 1, total).uppercase(Txt.locale)
    fun answerOf(id: String): Answer? = answers[id]
    val canGoBack: Boolean get() = !inSummary && index > 0

    fun choose(optionId: String) { val q = current ?: return; val o = q.options.firstOrNull { it.id == optionId } ?: return; put(Answer.Option(q.id, o.id, o.label)) }
    fun other(text: String) { val q = current ?: return; if (text.isNotBlank()) put(Answer.Text(q.id, text.trim().take(200))) }
    fun skip() { val q = current ?: return; put(Answer.Skip(q.id)) }
    fun youDecide() { val q = current ?: return; put(Answer.Skip(q.id, youDecide = true)) }

    private fun put(a: Answer) {
        answers[a.id] = a
        if (returnToSummary) { returnToSummary = false; inSummary = true; return }
        if (index + 1 >= questions.size) inSummary = true else index++
    }

    fun back() { if (canGoBack) index-- }

    /** Stops asking: the questions not answered yet count as skipped. */
    fun makeItNow() {
        for (q in questions) answers.putIfAbsent(q.id, Answer.Skip(q.id))
        inSummary = true; returnToSummary = false
    }

    /** From a summary chip: reopens that question; answering it comes back to the summary. */
    fun edit(questionId: String) {
        val i = questions.indexOfFirst { it.id == questionId }.takeIf { it >= 0 } ?: return
        index = i; inSummary = false; returnToSummary = true
    }

    /** Every answer so far in question order (all of them go with each later check call). */
    fun answerList(): List<Answer> = questions.mapNotNull { answers[it.id] }
    fun answered(): List<Answer> = answerList().filter { it !is Answer.Skip }

    /** Nothing to confirm: everything was skipped or left to the planner. */
    fun allSkipped(): Boolean = inSummary && answered().isEmpty()

    /** The chips of the summary ("For kids", "Calm", "Focus: Making honey"): the server's summary parts when they line up, else the answers' own labels. */
    fun chips(summary: String?): List<SummaryChip> {
        val a = answered()
        val parts = summary?.split(" · ")?.map { it.trim() }?.filter { it.isNotEmpty() }
        return a.mapIndexed { i, ans -> SummaryChip(ans.id, parts?.takeIf { it.size == a.size }?.get(i) ?: when (ans) { is Answer.Option -> ans.label; is Answer.Text -> ans.text; is Answer.Skip -> "" }) }
    }
}

data class SummaryChip(val questionId: String, val label: String)

/** What a sheet should say about a failure (Blocked and Paused come from the check or from generate itself). */
sealed interface CreateStop {
    data class NotSupported(val message: String, val suggestion: String?) : CreateStop
    data class Blocked(val message: String) : CreateStop
    data class Paused(val message: String, val retryAfterSeconds: Int?) : CreateStop
}

object CreateErrors {
    val DEFAULT_NOT_SUPPORTED: String get() = Txt.s(R.string.create_default_not_supported)
    val DEFAULT_BLOCKED: String get() = Txt.s(R.string.create_default_blocked)

    fun fromCheck(r: IntakeResult): CreateStop? = when (r) {
        is IntakeResult.NotSupported -> CreateStop.NotSupported(r.message?.takeIf { it.isNotBlank() } ?: DEFAULT_NOT_SUPPORTED, r.suggestion?.takeIf { it.isNotBlank() })
        is IntakeResult.Blocked -> CreateStop.Blocked(r.message?.takeIf { it.isNotBlank() } ?: DEFAULT_BLOCKED)
        is IntakeResult.Paused -> CreateStop.Paused(r.message, r.retryAfterSeconds)
        else -> null
    }

    /** generate itself can answer 400 blocked or 429 paused: the same sheets. */
    fun fromGenerate(e: ApiError): CreateStop? = when (e) {
        is ApiError.Blocked -> CreateStop.Blocked(e.text)
        is ApiError.Paused -> CreateStop.Paused(e.text, e.retryAfterSeconds)
        else -> null
    }

    /** "You can try again in about 1 hour." (no retry loop: the person decides). */
    fun retryText(seconds: Int?): String? = seconds?.takeIf { it > 0 }?.let {
        when {
            it >= 3600 -> Math.round(it / 3600.0).toInt().let { h -> Txt.n(R.plurals.create_retry_hours, h) }
            it >= 120 -> Txt.n(R.plurals.create_retry_minutes, it / 60)
            else -> Txt.s(R.string.create_retry_minute)
        }
    }
}

/** How the generate call answered when Create waits for it: the screen closes only on [Accepted]. */
sealed interface SubmitOutcome {
    data object Accepted : SubmitOutcome
    /** The server's safety gate (400 blocked) or a pause (429): the kind sheets, nothing charged, the draft stays. */
    data class Stopped(val error: ApiError) : SubmitOutcome
    /** No connection or a network error: stay on Create with a message; tapping Create again retries. */
    data class Offline(val message: String) : SubmitOutcome
}

/** The brief object for generate: the server's own, passed back untouched. */
fun briefForGenerate(r: IntakeResult): JsonObject? = (r as? IntakeResult.Ok)?.brief
