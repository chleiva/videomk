package com.videomk.app.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** My media: one photo as the server describes it. [taken] is local wall-clock "YYYY-MM-DDTHH:MM:SS" (no zone), [added] an ISO instant. [url] only on a single-item read (valid 10 minutes). */
data class MediaPhoto(
    val id: String, val taken: String?, val added: String, val place: String?, val w: Int, val h: Int, val bytes: Long,
    val thumbUrl: String?, val collections: List<String> = emptyList(), val url: String? = null,
) {
    companion object {
        fun fromJson(o: JsonObject) = MediaPhoto(
            id = o.requireString("id"), taken = o.str("taken"), added = o.str("added") ?: "", place = o.str("place"),
            w = o.int("w") ?: 0, h = o.int("h") ?: 0, bytes = o.num("bytes")?.toLong() ?: 0L, thumbUrl = o.str("thumb_url"),
            collections = o.arr("collections")?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content } ?: emptyList(),
            url = o.str("url"),
        )
    }
}

data class MediaCollection(val id: String, val name: String, val emoji: String?, val count: Int, val coverId: String?, val coverThumbUrl: String? = null, val auto: Boolean = false) {
    companion object {
        fun fromJson(o: JsonObject) = MediaCollection(o.requireString("id"), o.str("name") ?: "", o.str("emoji"), o.int("count") ?: 0, o.str("cover_id"), o.str("cover_thumb_url"), o.bool("auto") ?: false)
    }
}

data class YearCount(val year: Int, val count: Int)
data class PlaceCount(val name: String, val country: String?, val count: Int)

data class MediaSummary(
    val plan: String, val limitBytes: Long, val usedBytes: Long, val count: Int, val canUpgrade: Boolean,
    val years: List<YearCount>, val places: List<PlaceCount>, val collections: List<MediaCollection>,
    /** A lapsed plan left the library over its limit: uploads are refused, viewing and deleting still work. */
    val readOnly: Boolean = false,
    /** What to do after an upload (the server keeps it per account). */
    val organizePref: OrganizePref = OrganizePref.Ask,
) {
    companion object {
        fun fromJson(o: JsonObject) = MediaSummary(
            plan = o.str("plan") ?: "free", limitBytes = o.num("limit_bytes")?.toLong() ?: 0L, usedBytes = o.num("used_bytes")?.toLong() ?: 0L,
            count = o.int("count") ?: 0, canUpgrade = o.bool("can_upgrade") ?: false,
            years = o.arr("years")?.mapNotNull { e -> e.asObject()?.let { y -> y.int("year")?.let { YearCount(it, y.int("count") ?: 0) } } } ?: emptyList(),
            places = o.arr("places")?.mapNotNull { e -> e.asObject()?.let { p -> p.str("name")?.let { PlaceCount(it, p.str("country"), p.int("count") ?: 0) } } } ?: emptyList(),
            collections = o.arr("collections")?.mapNotNull { e -> e.asObject()?.let { runCatching { MediaCollection.fromJson(it) }.getOrNull() } } ?: emptyList(),
            readOnly = o.bool("read_only") ?: false,
            organizePref = OrganizePref.fromWire(o.obj("prefs")?.str("organize")),
        )
    }
}

/** One photo to put in the library: [size] and [sha256] are of the exact bytes that will be uploaded. [lat]/[lon] are already rounded to 2 decimals. */
data class UploadRequestItem(val size: Long, val sha256: String, val taken: String? = null, val lat: Double? = null, val lon: Double? = null) {
    fun toJson(): JsonObject = buildJsonObject {
        put("size", size); put("sha256", sha256)
        taken?.let { put("taken", it) }
        if (lat != null && lon != null) { put("lat", lat); put("lon", lon) }
    }
}

enum class SlotStatus { Upload, Duplicate, NoSpace, Rejected;
    companion object { fun fromWire(s: String?) = when (s) { "upload" -> Upload; "duplicate" -> Duplicate; "no_space" -> NoSpace; else -> Rejected } }
}

data class UploadSlotResult(
    val index: Int, val status: SlotStatus, val id: String?, val url: String?, val fields: Map<String, String>, val duplicateOf: String?, val reason: String?,
)

data class UploadsResponse(val uploads: List<UploadSlotResult>, val usedBytes: Long, val limitBytes: Long) {
    companion object {
        fun fromJson(o: JsonObject) = UploadsResponse(
            uploads = o.arr("uploads")?.mapNotNull { e ->
                e.asObject()?.let { u ->
                    UploadSlotResult(
                        index = u.int("index") ?: return@let null, status = SlotStatus.fromWire(u.str("status")), id = u.str("id"), url = u.str("url"),
                        fields = u.obj("fields")?.mapNotNull { (k, v) -> (v as? JsonPrimitive)?.takeIf { it.isString }?.let { k to it.content } }?.toMap() ?: emptyMap(),
                        duplicateOf = u.str("duplicate_of"), reason = u.str("reason"),
                    )
                }
            } ?: throw ApiError.Server,
            usedBytes = o.num("used_bytes")?.toLong() ?: 0L, limitBytes = o.num("limit_bytes")?.toLong() ?: 0L,
        )
    }
}

/** [cursor] is opaque: it is passed back exactly as received and never read or built by the app. */
data class MediaPage(val items: List<MediaPhoto>, val cursor: String?) {
    companion object {
        fun fromJson(o: JsonObject) = MediaPage(
            items = o.arr("items")?.mapNotNull { e -> e.asObject()?.let { runCatching { MediaPhoto.fromJson(it) }.getOrNull() } } ?: throw ApiError.Server,
            cursor = o.str("cursor")?.takeIf { it.isNotEmpty() },
        )
    }
}

data class SearchChip(val kind: String, val label: String)

data class Understood(val text: String?, val from: String?, val to: String?, val places: List<String>, val chips: List<SearchChip>) {
    companion object {
        val NONE = Understood(null, null, null, emptyList(), emptyList())
        fun fromJson(o: JsonObject?) = if (o == null) NONE else Understood(
            text = o.str("text")?.takeIf { it.isNotBlank() }, from = o.str("from"), to = o.str("to"),
            places = o.arr("places")?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content } ?: emptyList(),
            chips = o.arr("chips")?.mapNotNull { e -> e.asObject()?.let { c -> c.str("label")?.let { SearchChip(c.str("kind") ?: "topic", it) } } } ?: emptyList(),
        )
    }
}

/** [mode] "timeline": the complete filtered list newest first, paged with the opaque [cursor]; "semantic": by relevance (keep the order, do not regroup), at most 100, no cursor. */
data class SearchResult(val understood: Understood, val items: List<MediaPhoto>, val mode: String, val cursor: String? = null) {
    val isSemantic: Boolean get() = mode == "semantic"
    companion object {
        fun fromJson(o: JsonObject) = SearchResult(
            Understood.fromJson(o.obj("understood")),
            o.arr("items")?.mapNotNull { e -> e.asObject()?.let { runCatching { MediaPhoto.fromJson(it) }.getOrNull() } } ?: throw ApiError.Server,
            o.str("mode") ?: "timeline", o.str("cursor")?.takeIf { it.isNotEmpty() },
        )
    }
}

data class DeleteResult(val deleted: Int, val usedBytes: Long)

/** The list filters of `GET .../library/items`. */
data class MediaFilter(val from: String? = null, val to: String? = null, val collection: String? = null, val place: String? = null)

fun jsonIds(ids: List<String>) = JsonArray(ids.map { JsonPrimitive(it) })

/** Smart collections: what the app does after an upload (docs/MEDIA_LIBRARY.md "Smart collections"). */
enum class OrganizePref(val wire: String, val label: String) {
    Ask("ask", "Ask"), Always("always", "Always"), Never("never", "Never");
    companion object { fun fromWire(s: String?) = entries.firstOrNull { it.wire == s } ?: Ask }
}

data class OrganizeGroup(val name: String, val count: Int, val existing: Boolean, val sampleIds: List<String>)

data class OrganizePreview(val total: Int, val organized: Int, val skipped: Int, val home: String?, val groups: List<OrganizeGroup>) {
    companion object {
        fun fromJson(o: JsonObject) = OrganizePreview(
            total = o.int("total") ?: 0, organized = o.int("organized") ?: 0, skipped = o.int("skipped") ?: 0, home = o.str("home"),
            groups = o.arr("groups")?.mapNotNull { e ->
                e.asObject()?.let { g ->
                    g.str("name")?.let { n ->
                        OrganizeGroup(n, g.int("count") ?: 0, g.bool("existing") ?: false, g.arr("sample_ids")?.mapNotNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.takeIf { p -> p.isString }?.content } ?: emptyList())
                    }
                }
            } ?: emptyList(),
        )
    }
}

/** One call of `organize/apply` (about 300 photos). [collectionId] only in single mode: send it back on the next calls. */
data class OrganizeApplyResult(val applied: Int, val remaining: Int, val created: Int, val updated: Int, val skipped: Int, val collectionId: String?) {
    companion object {
        fun fromJson(o: JsonObject) = OrganizeApplyResult(o.int("applied") ?: 0, o.int("remaining") ?: 0, o.int("created") ?: 0, o.int("updated") ?: 0, o.int("skipped") ?: 0, o.str("collection_id"))
    }
}
