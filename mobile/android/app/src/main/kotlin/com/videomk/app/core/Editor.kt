package com.videomk.app.core

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// what the server sends for the editor (GET .../plan)

data class PhotoCandidate(
    val provider: String,
    val candidateId: String,
    val thumbUrl: String? = null,
    val creator: String = "Unknown",
    val license: String = "",
    val alt: String = "",
    val landingUrl: String? = null,
) {
    /** The id the server's `pick_image` operation expects. */
    val key: String get() = "$provider:$candidateId"

    companion object {
        fun fromJson(o: JsonObject) = PhotoCandidate(
            provider = o.requireString("provider"), candidateId = o.requireString("id"), thumbUrl = o.str("thumb_url"),
            creator = o.str("creator") ?: "Unknown", license = o.str("license") ?: "", alt = o.str("alt") ?: "", landingUrl = o.str("landing_url"),
        )
    }
}

data class BeatPhoto(val url: String? = null, val credit: String? = null, val chosen: String? = null, val noPhoto: Boolean = false) {
    companion object {
        fun fromJson(o: JsonObject) = BeatPhoto(o.str("url"), o.str("credit"), o.str("chosen"), o.bool("no_photo") ?: false)
    }
}

/** The scene types this app knows how to label. The server may send others (it recently added `clip` and `gallery`); those show as a generic "Scene". */
enum class SceneKind(val wire: String, val label: String) {
    Title("title", "Title"), Bullets("bullets", "List"), Diagram("diagram", "Diagram"), Chart("chart", "Chart"), Timeline("timeline", "Timeline"),
    Stat("stat", "Big number"), Quote("quote", "Quote"), Image("image", "Photo"), Clip("clip", "Video clip"), Gallery("gallery", "Photo gallery");

    companion object {
        fun fromWire(type: String?): SceneKind? = entries.firstOrNull { it.wire == type }
    }
}

data class EditorBeat(
    val id: String,
    val narration: String,
    /** Null for a scene type this app doesn't know: shown with a generic label, never an error. */
    val kind: SceneKind?,
    val sceneType: String = "",
    val summary: String = "",
    val chapter: String? = null,
    val duration: Double? = null,
    val stale: Boolean = false,
    val photo: BeatPhoto? = null,
    val candidates: List<PhotoCandidate> = emptyList(),
) {
    val label: String get() = kind?.label ?: "Scene"

    companion object {
        fun fromJson(o: JsonObject): EditorBeat {
            val scene = o.obj("scene")
            val type = scene?.str("type") ?: ""
            return EditorBeat(
                id = o.requireString("id"), narration = o.requireString("narration"), kind = SceneKind.fromWire(type), sceneType = type,
                summary = summary(type, scene?.obj("props") ?: JsonObject(emptyMap())),
                chapter = o.str("chapter")?.takeIf { it.isNotEmpty() }, duration = o.num("duration"), stale = o.bool("stale") ?: false,
                photo = o.obj("photo")?.let { BeatPhoto.fromJson(it) },
                candidates = o.arr("candidates")?.mapNotNull { e -> e.asObject()?.let { runCatching { PhotoCandidate.fromJson(it) }.getOrNull() } } ?: emptyList(),
            )
        }

        /** One line describing what the scene shows, for the list. Unknown scene types fall back to any title-like prop. */
        fun summary(type: String, p: JsonObject): String {
            fun s(k: String) = p.str(k)
            return when (type) {
                "title", "diagram", "chart", "timeline" -> s("title") ?: ""
                "bullets" -> s("heading") ?: ""
                "stat" -> listOfNotNull(s("value"), s("label")).joinToString(" ")
                "quote" -> s("text") ?: ""
                "image" -> s("alt") ?: s("image_query") ?: ""
                "clip" -> s("alt") ?: s("clip_query") ?: ""
                else -> s("title") ?: s("heading") ?: s("alt") ?: s("caption") ?: ""
            }
        }
    }
}

data class EditorLimits(val minWords: Int = 6, val maxWords: Int = 70, val maxBeats: Int = 90)

enum class EditState {
    Ready, Rendering, Failed;

    companion object {
        fun fromServer(raw: String?) = when (raw) { "RENDERING" -> Rendering; "FAILED" -> Failed; else -> Ready }
    }
}

data class EditorSnapshot(
    val videoId: String,
    val rev: Int,
    val editState: EditState,
    val editMode: String?,
    val title: String,
    /** Subtitles on the video (the creator's choice); on when the server does not say. */
    val captions: Boolean = true,
    val beats: List<EditorBeat>,
    val limits: EditorLimits,
    val finalUrl: String? = null, val finalRev: Int? = null,
    val previewUrl: String? = null, val previewRev: Int? = null,
) {
    companion object {
        fun fromJson(o: JsonObject): EditorSnapshot {
            val l = o.obj("limits"); val f = o.obj("final"); val p = o.obj("preview")
            return EditorSnapshot(
                videoId = o.requireString("video_id"), rev = o.requireInt("rev"), editState = EditState.fromServer(o.str("edit_state")),
                editMode = o.str("edit_mode"), title = o.str("title") ?: "", captions = o.bool("captions") ?: true,
                beats = (o.arr("beats") ?: throw ApiError.Server).map { EditorBeat.fromJson(it.asObject() ?: throw ApiError.Server) },
                limits = EditorLimits(l?.int("min_words") ?: 6, l?.int("max_words") ?: 70, l?.int("max_beats") ?: 90),
                finalUrl = f?.str("url"), finalRev = f?.int("rev"), previewUrl = p?.str("url"), previewRev = p?.int("rev"),
            )
        }
    }
}

// operations and the diff that produces them

enum class RenderMode(val wire: String) { Preview("preview"), Final("final") }

sealed interface EditOp {
    data class SetNarration(val id: String, val text: String) : EditOp
    data class PickImage(val id: String, val candidate: String) : EditOp
    data class Delete(val id: String) : EditOp
    data class Move(val id: String, val to: Int) : EditOp
    data class SetTitle(val title: String) : EditOp
    data class SetCaptions(val on: Boolean) : EditOp

    val json: JsonElement get() = buildJsonObject {
        when (val op = this@EditOp) {
            is SetNarration -> { put("op", "set_narration"); put("id", op.id); put("text", op.text) }
            is PickImage -> { put("op", "pick_image"); put("id", op.id); put("candidate", op.candidate) }
            is Delete -> { put("op", "delete"); put("id", op.id) }
            is Move -> { put("op", "move"); put("id", op.id); put("to", op.to) }
            is SetTitle -> { put("op", "set_meta"); put("title", op.title) }
            is SetCaptions -> { put("op", "set_meta"); put("captions", op.on) }
        }
    }
}

object EditorDiff {
    /** The operations that turn `server` into `local`. Order matters: content first, then deletions, then moves by target index. */
    fun ops(
        serverTitle: String, server: List<EditorBeat>, localTitle: String, local: List<EditorBeat>, picks: Map<String, String> = emptyMap(),
        serverCaptions: Boolean = true, localCaptions: Boolean = true,
    ): List<EditOp> {
        val ops = ArrayList<EditOp>()
        val serverById = server.associateBy { it.id }
        val localIds = local.map { it.id }.toSet()

        for (b in local) {
            val s = serverById[b.id]
            if (s != null && normalize(s.narration) != normalize(b.narration)) ops += EditOp.SetNarration(b.id, normalize(b.narration))
            val pick = picks[b.id]
            if (pick != null && s != null) ops += EditOp.PickImage(b.id, pick)
        }
        for (s in server) if (s.id !in localIds) ops += EditOp.Delete(s.id)

        val current = server.map { it.id }.filter { it in localIds }.toMutableList()
        val target = local.map { it.id }.filter { it in serverById }
        for ((i, id) in target.withIndex()) {
            if (current[i] != id) {
                current.remove(id)
                current.add(i, id)
                ops += EditOp.Move(id, i)
            }
        }
        val t = normalize(localTitle)
        if (t.isNotEmpty() && t != normalize(serverTitle)) ops += EditOp.SetTitle(t)
        if (localCaptions != serverCaptions) ops += EditOp.SetCaptions(localCaptions)
        return ops
    }

    fun normalize(s: String): String = s.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")

    /** Mirrors the server's narration limits so errors show beside the field before anything is sent. */
    fun narrationError(text: String, limits: EditorLimits): String? {
        val n = wordCount(text)
        if (n < limits.minWords) return "Needs at least ${limits.minWords} words (now $n)."
        if (n > limits.maxWords) return "Limited to ${limits.maxWords} words per scene (now $n). Split it into two scenes."
        return null
    }

    fun wordCount(text: String): Int = normalize(text).split(" ").count { it.isNotEmpty() }

    /** Spoken time at about 2.5 words per second. */
    fun spokenSeconds(text: String): Double = wordCount(text) / 2.5
}
