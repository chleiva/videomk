package com.videomk.app.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Every My media call. All of them go to `/users/{me}/library/...` (the user id comes from the token, never from the caller). */
interface MediaApi {
    suspend fun summary(): MediaSummary
    suspend fun requestUploads(items: List<UploadRequestItem>): UploadsResponse
    suspend fun items(limit: Int = 60, cursor: String? = null, filter: MediaFilter = MediaFilter()): MediaPage
    suspend fun item(id: String): MediaPhoto
    suspend fun delete(ids: List<String>): DeleteResult
    suspend fun search(query: String, limit: Int = 60, drop: List<String> = emptyList(), cursor: String? = null): SearchResult
    suspend fun collections(): List<MediaCollection>
    suspend fun createCollection(name: String, emoji: String? = null): MediaCollection
    suspend fun updateCollection(id: String, name: String? = null, emoji: String? = null): MediaCollection
    suspend fun deleteCollection(id: String)
    suspend fun editCollection(id: String, add: List<String> = emptyList(), remove: List<String> = emptyList())
    /** Smart collections. [since] is a UTC "YYYY-MM-DDTHH:MM:SS" (the batch just uploaded); null means every photo that is in no collection. */
    suspend fun organizePreview(since: String? = null): OrganizePreview
    suspend fun organizeApply(single: Boolean, since: String? = null, name: String? = null, collectionId: String? = null): OrganizeApplyResult
    suspend fun setOrganizePref(pref: OrganizePref)
}

class ApiMediaApi(private val api: ApiClient) : MediaApi {
    override suspend fun summary() = MediaSummary.fromJson(api.library("GET", listOf("summary")))

    override suspend fun requestUploads(items: List<UploadRequestItem>): UploadsResponse {
        require(items.size in 1..100)
        return UploadsResponse.fromJson(api.library("POST", listOf("uploads"), buildJsonObject { put("items", kotlinx.serialization.json.JsonArray(items.map { it.toJson() })) }))
    }

    override suspend fun items(limit: Int, cursor: String?, filter: MediaFilter): MediaPage {
        val q = buildList {
            add("limit" to limit.toString())
            cursor?.let { add("cursor" to it) }
            filter.from?.let { add("from" to it) }; filter.to?.let { add("to" to it) }
            filter.collection?.let { add("collection" to it) }; filter.place?.let { add("place" to it) }
        }
        return MediaPage.fromJson(api.library("GET", listOf("items"), query = q))
    }

    override suspend fun item(id: String) = MediaPhoto.fromJson(api.library("GET", listOf("items", id)))

    override suspend fun delete(ids: List<String>): DeleteResult {
        val o = api.library("POST", listOf("items", "delete"), buildJsonObject { put("ids", jsonIds(ids)) })
        return DeleteResult(o.int("deleted") ?: 0, o.num("used_bytes")?.toLong() ?: 0L)
    }

    override suspend fun search(query: String, limit: Int, drop: List<String>, cursor: String?): SearchResult =
        SearchResult.fromJson(api.library("POST", listOf("search"), buildJsonObject {
            put("query", query); put("limit", limit); cursor?.let { put("cursor", it) }
            if (drop.isNotEmpty()) put("drop", kotlinx.serialization.json.JsonArray(drop.map { kotlinx.serialization.json.JsonPrimitive(it) }))
        }))

    override suspend fun collections(): List<MediaCollection> =
        api.library("GET", listOf("collections")).arr("collections")?.mapNotNull { e -> e.asObject()?.let { runCatching { MediaCollection.fromJson(it) }.getOrNull() } } ?: throw ApiError.Server

    override suspend fun createCollection(name: String, emoji: String?) =
        MediaCollection.fromJson(api.library("POST", listOf("collections"), buildJsonObject { put("name", name.trim().take(40)); emoji?.let { put("emoji", it) } }))

    override suspend fun updateCollection(id: String, name: String?, emoji: String?) =
        MediaCollection.fromJson(api.library("POST", listOf("collections", id), buildJsonObject { name?.let { put("name", it.trim().take(40)) }; emoji?.let { put("emoji", it) } }))

    override suspend fun deleteCollection(id: String) { api.library("POST", listOf("collections", id, "delete")) }

    override suspend fun editCollection(id: String, add: List<String>, remove: List<String>) {
        api.library("POST", listOf("collections", id, "items"), buildJsonObject {
            if (add.isNotEmpty()) put("add", jsonIds(add)); if (remove.isNotEmpty()) put("remove", jsonIds(remove))
        })
    }

    override suspend fun organizePreview(since: String?) =
        OrganizePreview.fromJson(api.library("POST", listOf("organize", "preview"), buildJsonObject { since?.let { put("since", it) } }))

    override suspend fun organizeApply(single: Boolean, since: String?, name: String?, collectionId: String?) =
        OrganizeApplyResult.fromJson(api.library("POST", listOf("organize", "apply"), buildJsonObject {
            put("mode", if (single) "single" else "auto")
            since?.let { put("since", it) }
            if (single) { name?.let { put("name", it) }; collectionId?.let { put("collection_id", it) } }
        }))

    override suspend fun setOrganizePref(pref: OrganizePref) { api.library("POST", listOf("prefs"), buildJsonObject { put("organize", pref.wire) }) }
}
