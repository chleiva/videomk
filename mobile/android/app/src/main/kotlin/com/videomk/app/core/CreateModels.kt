package com.videomk.app.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** `GET /users/{id}/capabilities` (docs/CREATE_API.md): what the app may offer. Absent endpoint means [FALLBACK]. */
data class AspectInfo(val id: String, val label: String, val ready: Boolean, val beta: Boolean)
data class ResolutionInfo(val id: String, val label: String)
/** [recommendedMinutes], [maxMinutes] (a soft limit, or null), [otherAspects] and [note] come from the server ("Portrait 4:5 · 1080p · about 1 min"). */
data class PlatformInfo(
    val id: String, val label: String, val aspect: String, val resolution: String,
    val recommendedMinutes: Double? = null, val maxMinutes: Double? = null, val otherAspects: List<String> = emptyList(), val note: String? = null,
)
data class LanguageInfo(val id: String, val label: String)

data class Capabilities(
    val aspects: List<AspectInfo>, val resolutions: List<ResolutionInfo>, val platforms: List<PlatformInfo>, val languages: List<LanguageInfo>,
    val minMinutes: Double = 1.0, val maxMinutes: Double = 12.0, val presets: List<Double> = Lengths.OLD_PRESETS, val maxPhotos: Int = 100, val intake: Boolean = false,
) {
    val readyAspects: List<AspectInfo> get() = aspects.filter { it.ready }
    fun aspect(id: String) = aspects.firstOrNull { it.id == id }
    fun isReady(aspect: String) = aspect(aspect)?.ready == true

    companion object {
        /** The server has no capabilities endpoint yet: only landscape 16:9 at 1080p, the built-in platform table, no extra languages, no request check. */
        val FALLBACK = Capabilities(
            aspects = listOf(AspectInfo("16:9", "Landscape", true, false)), resolutions = listOf(ResolutionInfo("1080p", "1080p")),
            platforms = emptyList(), languages = emptyList(),
        )

        fun fromJson(o: JsonObject): Capabilities = Capabilities(
            aspects = o.arr("aspects")?.mapNotNull { e -> e.asObject()?.let { a -> a.str("id")?.let { AspectInfo(it, a.str("label") ?: it, a.bool("ready") ?: false, a.bool("beta") ?: false) } } } ?: emptyList(),
            resolutions = o.arr("resolutions")?.mapNotNull { e -> e.asObject()?.let { r -> r.str("id")?.let { ResolutionInfo(it, r.str("label") ?: it) } } } ?: emptyList(),
            platforms = o.arr("platforms")?.mapNotNull { e -> e.asObject()?.let { p -> p.str("id")?.let { PlatformInfo(it, p.str("label") ?: it, p.str("aspect") ?: "16:9", p.str("resolution") ?: "1080p", p.num("recommended_minutes"), p.num("max_minutes"), p.arr("other_aspects")?.mapNotNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: emptyList(), p.str("note")) } } } ?: emptyList(),
            languages = o.arr("languages")?.mapNotNull { e -> e.asObject()?.let { l -> l.str("id")?.let { LanguageInfo(it, l.str("label") ?: it) } } } ?: emptyList(),
            minMinutes = o.obj("lengths")?.num("min_minutes") ?: 1.0, maxMinutes = o.obj("lengths")?.num("max_minutes") ?: 12.0,
            presets = o.obj("lengths")?.arr("presets")?.mapNotNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.content?.toDoubleOrNull() }?.filter { it > 0 }?.distinct()?.sorted()?.takeIf { it.isNotEmpty() } ?: Lengths.OLD_PRESETS,
            maxPhotos = o.int("max_photos") ?: 100, intake = o.bool("intake") ?: false,
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
