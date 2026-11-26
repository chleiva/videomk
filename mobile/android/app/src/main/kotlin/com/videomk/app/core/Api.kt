package com.videomk.app.core

import com.videomk.app.R
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
    /** `en` or `es`, the effective app language (docs/I18N.md): the server answers its messages, capability labels and notes in it. */
    private val locale: () -> String = { Txt.localeTag },
) : AccountApi {
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
    suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions = CreateOptions(), media: List<String> = emptyList(), mediaMeta: JsonObject? = null, libraryMedia: List<String> = emptyList(), brief: JsonObject? = null, deck: String? = null): String {
        val body = buildJsonObject {
            // a presentation needs no description: an empty one is simply not sent (the server then uses its short default)
            if (deck == null || Brief.normalized(prompt).isNotEmpty()) put("prompt", Brief.normalized(prompt))
            deck?.let { put("deck", it) }
            put("client_request_id", clientRequestId)
            // a presentation made at its suggested length sends no length: the server charges exactly the suggestion it showed
            if (deck == null || !options.useSuggestedLength) put("target_minutes", options.minutes)
            if (media.isNotEmpty()) put("media", JsonArray(media.map { JsonPrimitive(it) }))
            if (libraryMedia.isNotEmpty()) put("library_media", JsonArray(libraryMedia.map { JsonPrimitive(it) }))
            if (media.isNotEmpty() && mediaMeta != null) put("media_meta", mediaMeta)
            options.look?.let { put("theme", it.wire) }
            if (!options.captions) put("captions", false)   // on is the server default: only the choice to turn them off is sent
            // creation options: absent means today's behaviour, so only choices away from the defaults are sent
            if (options.platform != "other") put("platform", options.platform)
            if (options.aspect != "16:9") put("aspect", options.aspect)
            if (options.resolution != "1080p") put("resolution", options.resolution)
            if (options.language != "auto") put("language", options.language)
            brief?.let { put("brief", it) }
        }
        return send("POST", listOf("videos", "generate"), body = body, deck = deck != null).requireString("video_id")
    }

    // presentations (docs/CREATE_API.md, "Making a video from a presentation deck")

    /** A call under `/users/{me}/decks`. Server refusals come as [ApiError.Deck] with their stable code. */
    suspend fun deck(method: String, path: List<String> = emptyList(), body: JsonObject? = null): JsonObject =
        send(method, listOf("decks") + path, body, deck = true)

    // create: capabilities and the request check

    /** What the app may offer. Throws [ApiError.NotFound] when the server does not have the endpoint yet (the caller falls back to 16:9 and 1080p). */
    suspend fun capabilities(): JsonObject = send("GET", listOf("capabilities"), soft = true)

    /** The request check (nothing is charged). Statuses come back in the body; a paused account is [ApiError.Paused]. */
    suspend fun brief(body: JsonObject): JsonObject = send("POST", listOf("videos", "brief"), body = body, soft = true)

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

    // account deletion (docs/ACCOUNT_DELETION.md): both calls take the token and its own `sub` from the caller, so a re-authenticated token is used as it is

    override suspend fun deleteAccount(idToken: String, sub: String): AccountDeleteResult {
        val (code, text) = try { raw("POST", listOf("account", "delete"), idToken, sub, buildJsonObject { put("confirm", "DELETE") }) } catch (e: IOException) { return AccountDeleteResult.Offline }
        val o = runCatching { parseObject(text) }.getOrNull()
        return when (code) {
            in 200..299 -> AccountDeleteResult.Accepted(AppleRevoke.fromWire(o?.str("apple")))
            401 -> if (o?.str("code") == "reauth_required") AccountDeleteResult.ReauthRequired else AccountDeleteResult.Unauthorized
            403 -> AccountDeleteResult.Forbidden
            400 -> AccountDeleteResult.Rejected
            else -> AccountDeleteResult.ServerError
        }
    }

    override suspend fun appleRevokeUrl(idToken: String, sub: String): String? {
        val (code, text) = try { raw("POST", listOf("account", "apple-revoke"), idToken, sub, buildJsonObject { put("return", "app") }) } catch (e: IOException) { return null }
        if (code !in 200..299) return null
        return runCatching { parseObject(text).str("authorize_url") }.getOrNull()?.takeIf { AppleRevokeLink.isAcceptable(it) }
    }

    /** One request with the caller's token. Never logs; throws [IOException] for any network problem (including a timeout). */
    private suspend fun raw(method: String, path: List<String>, idToken: String, sub: String, body: JsonObject): Pair<Int, String> {
        val url = config.apiBase.newBuilder().addPathSegment("users").addPathSegment(sub).also { b -> path.forEach { b.addPathSegment(it) } }.build()
        val rb = Request.Builder().url(url)
            .header("Authorization", "Bearer $idToken")
            .header("X-Platform", "android")
            .header("X-App-Version", appVersion)
            .header("X-Locale", locale())
            .method(method, body.toString().toRequestBody("application/json".toMediaType()))
        val response = try { http.newBuilder().callTimeout(30, TimeUnit.SECONDS).build().newCall(rb.build()).await() } catch (e: CancellationException) { throw e }
        return response.use { r -> r.code to r.body.string() }
    }

    // plumbing

    /** A My media call: `/users/{me}/library/...`, with the library's own error mapping (402 storage_full, 404 not found, 413, 429). */
    suspend fun library(method: String, path: List<String>, body: JsonObject? = null, query: List<Pair<String, String>> = emptyList()): JsonObject =
        send(method, listOf("library") + path, body, query = query, library = true)

    private suspend fun send(method: String, path: List<String>, body: JsonObject? = null, conflictIsEdit: Boolean = false, query: List<Pair<String, String>> = emptyList(), library: Boolean = false, soft: Boolean = false, deck: Boolean = false): JsonObject {
        val a = auth.authorization()
        val url: HttpUrl = config.apiBase.newBuilder().addPathSegment("users").addPathSegment(a.userId).also { b -> path.forEach { b.addPathSegment(it) }; query.forEach { (k, v) -> b.addQueryParameter(k, v) } }.build()
        val rb = Request.Builder().url(url)
            .header("Authorization", "Bearer ${a.idToken}")
            .header("X-Platform", "android")
            .header("X-App-Version", appVersion)
            .header("X-Locale", locale())
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
                401 -> throw ApiError.Unauthorized
                403 -> if (soft) throw ApiError.NotFound else throw ApiError.Unauthorized
                404 -> if (deck) throw ApiError.Deck(codeOf(text) ?: "unavailable", message(text) ?: "") else if (library || soft) throw ApiError.NotFound else throw ApiError.Server
                413 -> if (library) throw ApiError.Invalid(Txt.s(R.string.err_photo_too_large)) else throw ApiError.Server
                402 -> if (library) {
                    val o = runCatching { parseObject(text) }.getOrNull()
                    throw ApiError.StorageFull((o?.num("used_bytes") ?: 0.0).toLong(), (o?.num("limit_bytes") ?: 0.0).toLong())
                } else {
                    val o = runCatching { parseObject(text) }.getOrNull()
                    throw ApiError.InsufficientCredits(o?.int("balance") ?: 0, o?.int("needed") ?: 1)
                }
                400 -> {
                    val o = runCatching { parseObject(text) }.getOrNull()
                    if (o?.str("status") == "blocked") throw ApiError.Blocked(o.str("message") ?: Txt.s(R.string.err_blocked_default))
                    if (deck && o?.str("code") != null) throw ApiError.Deck(o.str("code")!!, o.str("message") ?: "")
                    throw ApiError.Invalid(message(text) ?: Txt.s(R.string.err_brief_unusable))
                }
                409 -> if (deck) throw ApiError.Deck(codeOf(text) ?: "deck_not_ready", message(text) ?: "")
                       else if (library) throw ApiError.Conflict(message(text) ?: Txt.s(R.string.err_changed_meanwhile))
                       else if (conflictIsEdit) throw ApiError.Conflict(message(text) ?: Txt.s(R.string.err_video_changed))
                       else throw ApiError.NotReady(VideoStatus.fromServer(runCatching { parseObject(text).str("status") }.getOrNull() ?: ""))
                429 -> {
                    val o = runCatching { parseObject(text) }.getOrNull()
                    if (o?.str("status") == "paused") throw ApiError.Paused(o.str("message") ?: Txt.s(R.string.err_paused_default), o.int("retry_after") ?: r.header("Retry-After")?.toIntOrNull())
                    if (deck && o?.str("code") != null) throw ApiError.Deck(o.str("code")!!, o.str("message") ?: "")
                    throw ApiError.Quota(
                        message(text) ?: if (library) (r.header("Retry-After")?.toIntOrNull()?.let { if (it >= 120) Txt.n(R.plurals.err_rate_limited_minutes, it / 60) else Txt.n(R.plurals.err_rate_limited_seconds, it) } ?: Txt.s(R.string.err_rate_limited))
                        else Txt.s(R.string.err_daily_limit),
                    )
                }
                else -> throw ApiError.Server
            }
        }
    }

    private fun codeOf(text: String): String? = runCatching { parseObject(text).str("code") }.getOrNull()

    private fun message(text: String): String? = runCatching { parseObject(text).str("message") }.getOrNull()
}
