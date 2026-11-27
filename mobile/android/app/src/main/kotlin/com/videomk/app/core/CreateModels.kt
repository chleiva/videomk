package com.videomk.app.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import com.videomk.app.R

/** `GET /users/{id}/capabilities` (docs/CREATE_API.md): what the app may offer. Absent endpoint means [FALLBACK]. */
data class AspectInfo(val id: String, val label: String, val ready: Boolean, val beta: Boolean)
/** [multiplier]: what it costs relative to 1080p (2 for 4K). [available] false with [requiresPlan]: listed but locked for this account's plan (the tile shows the plan's name). */
data class ResolutionInfo(val id: String, val label: String, val multiplier: Int = 1, val available: Boolean = true, val requiresPlan: String? = null)

/** A scene style the server offers (`looks.style.options`): Auto, Illustrated, Real, Whiteboard... Labels and notes arrive in the app language. */
data class StyleOption(val id: String, val label: String, val note: String? = null, val available: Boolean = true)
/** A background the person can ask for in words (`looks.backgrounds.ask`): [say] is appended to the description. */
data class BackgroundWish(val id: String, val label: String, val say: String)
/** Present only when the server lists `looks`: an older server offers no style choice at all. */
data class LooksCaps(val styles: List<StyleOption>, val defaultStyle: String = "auto", val wishes: List<BackgroundWish> = emptyList()) {
    /** There is a real choice to show: at least two styles the account can pick. */
    val hasStyleChoice: Boolean get() = styles.count { it.available } > 1
    fun style(id: String) = styles.firstOrNull { it.id == id }

    companion object {
        fun fromJson(o: JsonObject?): LooksCaps? {
            o ?: return null
            val st = o.obj("style")
            val styles = st?.arr("options")?.mapNotNull { e -> e.asObject()?.let { x -> x.str("id")?.let { StyleOption(it, x.str("label")?.takeIf { l -> l.isNotBlank() } ?: it, x.str("note")?.takeIf { n -> n.isNotBlank() }, x.bool("available") ?: true) } } } ?: emptyList()
            val wishes = o.obj("backgrounds")?.arr("ask")?.mapNotNull { e -> e.asObject()?.let { x -> val id = x.str("id"); val say = x.str("say"); if (id == null || say.isNullOrBlank()) null else BackgroundWish(id, x.str("label")?.takeIf { l -> l.isNotBlank() } ?: say, say) } } ?: emptyList()
            if (styles.isEmpty() && wishes.isEmpty()) return null
            return LooksCaps(styles, st?.str("default") ?: "auto", wishes)
        }
    }
}

/** One watermark choice (`watermark.modes[]`, `watermark.presences[]`). */
data class WatermarkChoice(val id: String, val label: String, val available: Boolean = true, val note: String? = null, val requiresPlan: String? = null)
/**
 * The watermark as this account may set it (docs/WATERMARK.md section 8). [forced]: every video carries the mark and nothing can be chosen (a Free account): the row is a
 * fixed value with [forcedNote] under it and nothing is sent. Otherwise the modes and, for the product's own mark, the presence ("Always visible", "Now and then").
 */
data class WatermarkCaps(val forced: Boolean, val forcedNote: String? = null, val modes: List<WatermarkChoice> = emptyList(), val presences: List<WatermarkChoice> = emptyList(), val defaultPresence: String? = null) {
    companion object {
        private fun choices(list: List<kotlinx.serialization.json.JsonElement>?) = list?.mapNotNull { e -> e.asObject()?.let { x -> x.str("id")?.let { WatermarkChoice(it, x.str("label")?.takeIf { l -> l.isNotBlank() } ?: it, x.bool("available") ?: true, x.str("note")?.takeIf { n -> n.isNotBlank() }, x.str("requires_plan")) } } } ?: emptyList()
        fun fromJson(o: JsonObject?): WatermarkCaps? {
            o ?: return null
            return WatermarkCaps(o.bool("forced") ?: false, o.str("forced_note")?.takeIf { it.isNotBlank() }, choices(o.arr("modes")), choices(o.arr("presences")), o.str("default_presence"))
        }
    }
}
/** [recommendedMinutes], [maxMinutes] (a soft limit, or null), [otherAspects] and [note] come from the server ("Portrait 4:5 · 1080p · about 1 min"). */
data class PlatformInfo(
    val id: String, val label: String, val aspect: String, val resolution: String,
    val recommendedMinutes: Double? = null, val maxMinutes: Double? = null, val otherAspects: List<String> = emptyList(), val note: String? = null,
)
data class LanguageInfo(val id: String, val label: String)

data class Capabilities(
    val aspects: List<AspectInfo>, val resolutions: List<ResolutionInfo>, val platforms: List<PlatformInfo>, val languages: List<LanguageInfo>,
    val minMinutes: Double = 1.0, val maxMinutes: Double = 12.0, val presets: List<Double> = Lengths.OLD_PRESETS, val maxPhotos: Int = 100, val intake: Boolean = false,
    /** Present only when the server has presentations switched on: the whole feature stays hidden otherwise. */
    val deck: DeckCaps? = null,
    /** Scene styles and background wishes, only when the server lists them. */
    val looks: LooksCaps? = null,
    /** The watermark choices, only where the server has the feature. */
    val watermark: WatermarkCaps? = null,
    /** The plan, the free plan's state, and what the plan caps: the longest video in seconds (`lengths.plan_max_seconds`) and the photos one video uses. Absent on a server without plans. */
    val plans: PlanState = PlanState.NONE, val planMaxSeconds: Int? = null, val planMaxPhotos: Int? = null,
    /** The plan that makes longer videos (`lengths.locked[].requires_plan`), for the badge on the lengths over the cap. */
    val longerPlan: String? = null,
) {
    /** A length this plan can make (every length where the server names no cap). */
    fun lengthAllowed(minutes: Double): Boolean = planMaxSeconds == null || minutes * 60 <= planMaxSeconds + 0.5
    fun resolution(id: String) = resolutions.firstOrNull { it.id == id }
    /** The plan's name as people read it ("Pro", "Max"). */
    fun planName(id: String?): String? = id?.takeIf { it.isNotBlank() }?.replaceFirstChar { it.uppercase() }

    val readyAspects: List<AspectInfo> get() = aspects.filter { it.ready }
    fun aspect(id: String) = aspects.firstOrNull { it.id == id }
    fun isReady(aspect: String) = aspect(aspect)?.ready == true

    companion object {
        /** The server has no capabilities endpoint yet: only landscape 16:9 at 1080p, the built-in platform table, no extra languages, no request check. */
        val FALLBACK = Capabilities(
            aspects = listOf(AspectInfo("16:9", "", true, false)), resolutions = listOf(ResolutionInfo("1080p", "1080p")),
            platforms = emptyList(), languages = emptyList(),
        )

        fun fromJson(o: JsonObject): Capabilities = Capabilities(
            aspects = o.arr("aspects")?.mapNotNull { e -> e.asObject()?.let { a -> a.str("id")?.let { AspectInfo(it, a.str("label") ?: it, a.bool("ready") ?: false, a.bool("beta") ?: false) } } } ?: emptyList(),
            resolutions = o.arr("resolutions")?.mapNotNull { e -> e.asObject()?.let { r -> r.str("id")?.let { ResolutionInfo(it, r.str("label") ?: it, r.int("credits_multiplier") ?: 1, r.bool("available") ?: true, r.str("requires_plan")) } } } ?: emptyList(),
            platforms = o.arr("platforms")?.mapNotNull { e -> e.asObject()?.let { p -> p.str("id")?.let { PlatformInfo(it, p.str("label") ?: it, p.str("aspect") ?: "16:9", p.str("resolution") ?: "1080p", p.num("recommended_minutes"), p.num("max_minutes"), p.arr("other_aspects")?.mapNotNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: emptyList(), p.str("note")) } } } ?: emptyList(),
            languages = o.arr("languages")?.mapNotNull { e -> e.asObject()?.let { l -> l.str("id")?.let { LanguageInfo(it, l.str("label") ?: it) } } } ?: emptyList(),
            minMinutes = o.obj("lengths")?.num("min_minutes") ?: 1.0, maxMinutes = o.obj("lengths")?.num("max_minutes") ?: 12.0,
            presets = o.obj("lengths")?.arr("presets")?.mapNotNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.content?.toDoubleOrNull() }?.filter { it > 0 }?.distinct()?.sorted()?.takeIf { it.isNotEmpty() } ?: Lengths.OLD_PRESETS,
            maxPhotos = o.int("max_photos") ?: 100, intake = o.bool("intake") ?: false,
            deck = o.obj("deck")?.let { DeckCaps.fromJson(it) },
            looks = LooksCaps.fromJson(o.obj("looks")), watermark = WatermarkCaps.fromJson(o.obj("watermark")),
            plans = PlanState.fromJson(o), planMaxSeconds = o.obj("lengths")?.int("plan_max_seconds"), planMaxPhotos = o.int("plan_max_photos"),
            longerPlan = o.obj("lengths")?.arr("locked")?.firstNotNullOfOrNull { it.asObject()?.str("requires_plan") },
        ).let { c -> if (c.readyAspects.isEmpty() || c.resolutions.isEmpty()) FALLBACK else c }
    }
}

/** One clarifying question from the server (never invented by the app). */
data class QuestionOption(val id: String, val label: String)
data class Question(val id: String, val text: String, val options: List<QuestionOption>, val allowOther: Boolean = true, val helper: String? = null)

/** An answer: a chosen option, free text from "Other...", or a skip ("Skip" and "You decide" both mean the planner chooses). */
sealed interface Answer {
    val id: String
    data class Option(override val id: String, val option: String, val label: String) : Answer
    data class Text(override val id: String, val text: String) : Answer
    data class Skip(override val id: String, val youDecide: Boolean = false) : Answer

    fun toJson(): JsonObject = buildJsonObject {
        put("id", id)
        when (this@Answer) { is Option -> put("option", option); is Text -> put("text", text); is Skip -> put("skip", true) }
    }
}

data class IntakeRequest(val prompt: String, val options: CreateOptions, val mediaCount: Int, val answers: List<Answer> = emptyList()) {
    fun toJson(): JsonObject = buildJsonObject {
        put("prompt", Brief.normalized(prompt))
        put("options", buildJsonObject {
            put("platform", options.platform); put("aspect", options.aspect); put("resolution", options.resolution)
            put("captions", options.captions); put("language", options.language); put("target_minutes", options.minutes)
            if (options.style != "auto") put("style", options.style)
        })
        put("media_count", mediaCount)
        put("answers", JsonArray(answers.map { it.toJson() }))
    }
}

/** What the request check said. Anything unexpected is [Ok] with no brief: a failed check never blocks a video. */
sealed interface IntakeResult {
    data class Ok(val brief: JsonObject?) : IntakeResult
    data class Questions(val questions: List<Question>) : IntakeResult
    data class NotSupported(val message: String?, val suggestion: String?) : IntakeResult
    data class Blocked(val message: String?) : IntakeResult
    data class Paused(val message: String, val retryAfterSeconds: Int?) : IntakeResult

    companion object {
        fun fromJson(o: JsonObject): IntakeResult = when (o.str("status")) {
            "ok" -> Ok(o.obj("brief"))
            "questions" -> o.arr("questions")?.mapNotNull { e ->
                e.asObject()?.let { q ->
                    val id = q.str("id") ?: return@let null
                    val opts = q.arr("options")?.mapNotNull { x -> x.asObject()?.let { oo -> oo.str("id")?.let { QuestionOption(it, oo.str("label") ?: it) } } } ?: emptyList()
                    if (opts.isEmpty()) null else Question(id, q.str("text") ?: q.str("title") ?: "", opts.take(5), q.bool("allow_other") ?: true, q.str("helper"))
                }
            }?.take(3)?.takeIf { it.isNotEmpty() }?.let { Questions(it) } ?: Ok(null)
            "not_supported", "unsupported", "unsafe" -> NotSupported(o.str("message"), o.str("suggestion"))
            "blocked" -> Blocked(o.str("message"))
            else -> Ok(null)
        }
    }
}

/** The two new endpoints, behind an interface so tests and the debug build can fake them. */
interface IntakeApi {
    suspend fun capabilities(): Capabilities
    suspend fun brief(request: IntakeRequest): IntakeResult
}

class ApiIntake(private val api: ApiClient) : IntakeApi {
    override suspend fun capabilities(): Capabilities = try { Capabilities.fromJson(api.capabilities()) } catch (e: ApiError.NotFound) { Capabilities.FALLBACK }
    override suspend fun brief(request: IntakeRequest): IntakeResult = try {
        IntakeResult.fromJson(api.brief(request.toJson()))
    } catch (e: ApiError.Paused) { IntakeResult.Paused(e.text, e.retryAfterSeconds) }
}

/** The look's name in the app language (Midnight, Paper, Sunrise); the wire value never changes. */
fun VideoLook.displayName(): String = Txt.s(when (this) { VideoLook.Midnight -> R.string.create_look_midnight; VideoLook.Paper -> R.string.create_look_paper; VideoLook.Sunrise -> R.string.create_look_sunrise })
