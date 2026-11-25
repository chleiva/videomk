package com.videomk.app.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.Call
import okhttp3.Callback
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Runs the call without blocking a thread and cancels it with the coroutine. */
suspend fun Call.await(): Response = suspendCancellableCoroutine { cont ->
    cont.invokeOnCancellation { runCatching { cancel() } }
    enqueue(object : Callback {
        override fun onFailure(call: Call, e: IOException) { if (cont.isActive) cont.resumeWithException(e) }
        override fun onResponse(call: Call, response: Response) { if (cont.isActive) cont.resume(response) else response.close() }
    })
}

fun defaultHttpClient(): OkHttpClient = OkHttpClient.Builder()
    .connectTimeout(20, TimeUnit.SECONDS)
    .readTimeout(30, TimeUnit.SECONDS)
    .writeTimeout(120, TimeUnit.SECONDS)
    .build()

/**
 * Every endpoint of the videomk API. [region] is the device's region setting (ISO country code); the server uses it only to pick a default
 * voice accent. [timeZone] says where the user's day ends, for the daily free credits.
 */
class ApiClient(
    private val config: AppConfig,
    private val auth: AuthorizationProviding,
    private val http: OkHttpClient = defaultHttpClient(),
    private val appVersion: String = "0",
    private val region: () -> String? = { java.util.Locale.getDefault().country.takeIf { it.isNotEmpty() } },
    private val timeZone: () -> String = { java.util.TimeZone.getDefault().id },
) {
    suspend fun requestUploads(count: Int): List<UploadSlot> {
        val body = buildJsonObject { put("count", count) }
        val o = send("POST", listOf("uploads"), body = body)
        return o.arr("uploads")?.map { UploadSlot.fromJson(it.asObject() ?: throw ApiError.Server) } ?: throw ApiError.Server
    }

    suspend fun wallet(): WalletInfo = WalletInfo.fromJson(send("GET", listOf("wallet")))

    suspend fun listVideos(): List<VideoItem> {
        val o = send("GET", listOf("videos"))
        return o.arr("items")?.mapNotNull { e -> e.asObject()?.let { runCatching { VideoItem.fromJson(it) }.getOrNull() } } ?: throw ApiError.Server
    }

    /** A presigned MP4 URL. Throws [ApiError.NotReady] (with the current status) while the video is still being made. */
    suspend fun playback(videoId: String): PlaybackInfo {
        val o = send("GET", listOf("videos", videoId))
        return PlaybackInfo(o.requireString("url"), o.str("description"))
    }

    /** [clientRequestId] makes a retry of the same attempt idempotent (no double charge, no second video). */
    suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions = CreateOptions(), media: List<String> = emptyList(), mediaMeta: JsonObject? = null, libraryMedia: List<String> = emptyList()): String {
        val body = buildJsonObject {
            put("prompt", Brief.normalized(prompt))
            put("client_request_id", clientRequestId)
            put("target_minutes", options.minutes)
            if (media.isNotEmpty()) put("media", JsonArray(media.map { JsonPrimitive(it) }))
            if (libraryMedia.isNotEmpty()) put("library_media", JsonArray(libraryMedia.map { JsonPrimitive(it) }))
            if (media.isNotEmpty() && mediaMeta != null) put("media_meta", mediaMeta)
            options.look?.let { put("theme", it.wire) }
            if (!options.captions) put("captions", false)   // on is the server default: only the choice to turn them off is sent
        }
        return send("POST", listOf("videos", "generate"), body = body).requireString("video_id")
    }

    // editor

    suspend fun editorSnapshot(videoId: String): EditorSnapshot =
        EditorSnapshot.fromJson(send("GET", listOf("videos", videoId, "plan"), conflictIsEdit = true))

    /** Returns the new revision. Throws [ApiError.Conflict] when the base revision is stale or a render is running. */
    suspend fun applyEdits(videoId: String, baseRev: Int, ops: List<EditOp>, mode: RenderMode): Int {
        val body = buildJsonObject {
            put("base_rev", baseRev)
            put("ops", JsonArray(ops.map { it.json }))
            put("mode", mode.wire)
        }
        return send("POST", listOf("videos", videoId, "edits"), body = body, conflictIsEdit = true).requireInt("rev")
    }

    // plumbing

    /** A My media call: `/users/{me}/library/...`, with the library's own error mapping (402 storage_full, 404 not found, 413, 429). */
    suspend fun library(method: String, path: List<String>, body: JsonObject? = null, query: List<Pair<String, String>> = emptyList()): JsonObject =
        send(method, listOf("library") + path, body, query = query, library = true)

    private suspend fun send(method: String, path: List<String>, body: JsonObject? = null, conflictIsEdit: Boolean = false, query: List<Pair<String, String>> = emptyList(), library: Boolean = false): JsonObject {
        val a = auth.authorization()
        val url: HttpUrl = config.apiBase.newBuilder().addPathSegment("users").addPathSegment(a.userId).also { b -> path.forEach { b.addPathSegment(it) }; query.forEach { (k, v) -> b.addQueryParameter(k, v) } }.build()
        val rb = Request.Builder().url(url)
            .header("Authorization", "Bearer ${a.idToken}")
            .header("X-Platform", "android")
            .header("X-App-Version", appVersion)
            .header("X-Timezone", timeZone())   // where the user's day ends, for the daily free credits
        region()?.takeIf { it.length == 2 }?.let { rb.header("X-Region", it.uppercase()) }
        val requestBody: RequestBody? = (body ?: if (method == "POST") JsonObject(emptyMap()) else null)?.let { it.toString().toRequestBody("application/json".toMediaType()) }
        rb.method(method, requestBody)

        val response = try {
            http.newBuilder().callTimeout(60, TimeUnit.SECONDS).build().newCall(rb.build()).await()
        } catch (e: CancellationException) { throw e } catch (e: IOException) { throw ApiError.Network }
        response.use { r ->
            val text = try { r.body.string() } catch (e: IOException) { throw ApiError.Network }
            when (r.code) {
                in 200..299 -> return if (text.isBlank()) JsonObject(emptyMap()) else parseObject(text)
                401, 403 -> throw ApiError.Unauthorized
                404 -> if (library) throw ApiError.NotFound else throw ApiError.Server
                413 -> if (library) throw ApiError.Invalid("That photo is too large.") else throw ApiError.Server
                402 -> if (library) {
                    val o = runCatching { parseObject(text) }.getOrNull()
                    throw ApiError.StorageFull((o?.num("used_bytes") ?: 0.0).toLong(), (o?.num("limit_bytes") ?: 0.0).toLong())
                } else {
                    val o = runCatching { parseObject(text) }.getOrNull()
                    throw ApiError.InsufficientCredits(o?.int("balance") ?: 0, o?.int("needed") ?: 1)
                }
                400 -> throw ApiError.Invalid(message(text) ?: "That brief can't be used.")
                409 -> if (library) throw ApiError.Conflict(message(text) ?: "That changed in the meantime. Please try again.")
                       else if (conflictIsEdit) throw ApiError.Conflict(message(text) ?: "This video changed. Reload to continue.")
                       else throw ApiError.NotReady(VideoStatus.fromServer(runCatching { parseObject(text).str("status") }.getOrNull() ?: ""))
                429 -> throw ApiError.Quota(message(text) ?: if (library) (r.header("Retry-After")?.toIntOrNull()?.let { "Too many requests. Try again in ${if (it >= 120) "${it / 60} minutes" else "$it seconds"}." } ?: "Too many requests. Try again in a moment.") else "You've reached today's limit. Try again tomorrow.")
                else -> throw ApiError.Server
            }
        }
    }

    private fun message(text: String): String? = runCatching { parseObject(text).str("message") }.getOrNull()
}
