package com.videomk.app.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.security.MessageDigest

enum class UploadState { Queued, Uploading, Done, Duplicate, NoSpace, Failed;
    val finished: Boolean get() = this != Queued && this != Uploading
}

/** One photo waiting to go to My media. [path] is the prepared JPEG (upright, at most 2048 px, no metadata) kept on disk so the queue survives a restart. */
data class QueueItem(
    val id: String, val path: String, val size: Long, val sha256: String,
    val taken: String? = null, val lat: Double? = null, val lon: Double? = null,
    val state: UploadState = UploadState.Queued, val mediaId: String? = null, val error: String? = null,
    val slotUrl: String? = null, val slotFields: Map<String, String>? = null,
) {
    fun request() = UploadRequestItem(size, sha256, taken, lat, lon)

    fun toJson(): JsonObject = buildJsonObject {
        put("id", id); put("path", path); put("size", size); put("sha256", sha256)
        taken?.let { put("taken", it) }; if (lat != null && lon != null) { put("lat", lat); put("lon", lon) }
        put("state", state.name); mediaId?.let { put("media_id", it) }; error?.let { put("error", it) }
        // the slot is kept so a pause or a restart does not waste the reservation; it is dropped when the post is refused
        slotUrl?.let { put("slot_url", it) }
        slotFields?.let { f -> put("slot_fields", JsonObject(f.mapValues { JsonPrimitive(it.value) })) }
    }

    companion object {
        fun fromJson(o: JsonObject) = QueueItem(
            id = o.requireString("id"), path = o.requireString("path"), size = o.num("size")?.toLong() ?: 0L, sha256 = o.requireString("sha256"),
            taken = o.str("taken"), lat = o.num("lat"), lon = o.num("lon"),
            state = runCatching { UploadState.valueOf(o.str("state") ?: "Queued") }.getOrDefault(UploadState.Queued),
            mediaId = o.str("media_id"), error = o.str("error"), slotUrl = o.str("slot_url"),
            slotFields = o.obj("slot_fields")?.mapNotNull { (k, v) -> (v as? JsonPrimitive)?.takeIf { it.isString }?.let { k to it.content } }?.toMap(),
        )
    }
}

/** What the banner shows. */
data class QueueProgress(
    val total: Int, val finished: Int, val uploaded: Int, val duplicates: Int, val noSpace: Int, val failed: Int,
    val bytesDone: Long, val bytesTotal: Long, val paused: Boolean, val running: Boolean, val offline: Boolean = false,
) {
    val active: Boolean get() = total > finished
    val storageFullMessageNeeded: Boolean get() = noSpace > 0
    /** "Uploading 37 of 120 · 640 MB" */
    fun bannerText(): String = "Uploading ${minOf(finished + 1, total)} of $total · ${StorageMeter.format(bytesDone)}"
}

interface QueueStorage { fun load(): String?; fun save(text: String) }
class MemoryQueueStorage : QueueStorage { var text: String? = null; override fun load() = text; override fun save(text: String) { this.text = text } }

/** Reads and deletes the prepared files (real files in the app; a map in tests). */
interface BlobSource { fun read(path: String): ByteArray?; fun delete(path: String) }

/** The presigned POST to storage. Throws on any failure. The file is the LAST form part (S3 requires it). */
fun interface SlotPoster { suspend fun post(url: String, fields: Map<String, String>, bytes: ByteArray) }

/** The real poster: [MultipartForm] (signed fields first, the file last) over OkHttp, without the login token. */
class HttpSlotPoster(private val http: okhttp3.OkHttpClient = defaultHttpClient()) : SlotPoster {
    override suspend fun post(url: String, fields: Map<String, String>, bytes: ByteArray) {
        val u = okhttp3.HttpUrl.Companion.run { url.toHttpUrlOrNull() } ?: throw ApiError.Server
        val form = MultipartForm.body(fields, bytes)
        val req = okhttp3.Request.Builder().url(u).post(okhttp3.RequestBody.Companion.run { form.body.toRequestBody(okhttp3.MediaType.Companion.run { form.contentType.toMediaType() }) }).build()
        try {
            http.newBuilder().callTimeout(120, java.util.concurrent.TimeUnit.SECONDS).build().newCall(req).await().use { r ->
                if (r.code !in 200..299) throw ApiError.Invalid("A photo couldn't be uploaded.")
            }
        } catch (e: CancellationException) { throw e } catch (e: ApiError) { throw e } catch (e: java.io.IOException) { throw ApiError.Network }
    }
}

fun sha256Hex(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

/**
 * The upload queue for My media. Pure logic over ports ([MediaApi], [SlotPoster], [BlobSource], [QueueStorage]).
 * Slots are requested in batches of at most 100; photos go up [concurrency] at a time, each tried [tries] times with a backoff; the state is saved after
 * every change, so a restart resumes where it stopped (an item that was Uploading goes back to Queued). Nothing is dropped silently:
 * duplicates, no-space and failures stay in the list with their state until the person dismisses them.
 */
class MediaUploadQueue(
    private val api: MediaApi, private val storage: QueueStorage, private val blobs: BlobSource, private val poster: SlotPoster,
    private val concurrency: Int = 3, private val tries: Int = 3, private val backoffMillis: (Int) -> Long = { 500L * it },
    private val batchSize: Int = 100,
) {
    private val lock = Any()
    private val _items = MutableStateFlow<List<QueueItem>>(emptyList())
    val items: StateFlow<List<QueueItem>> = _items.asStateFlow()
    private val _progress = MutableStateFlow(compute(emptyList(), false, false, false))
    val progress: StateFlow<QueueProgress> = _progress.asStateFlow()
    private val _usage = MutableStateFlow<Pair<Long, Long>?>(null)
    /** (used, limit) bytes as of the last slot answer, so the header meter can update at once. */
    val usage: StateFlow<Pair<Long, Long>?> = _usage.asStateFlow()

    @Volatile private var paused = false
    @Volatile private var cancelled = false
    @Volatile private var running = false
    @Volatile private var offline = false

    init { restore() }

    private fun restore() {
        val loaded = runCatching { storage.load()?.let { parseObject(it).arr("items")?.mapNotNull { e -> e.asObject()?.let { o -> runCatching { QueueItem.fromJson(o) }.getOrNull() } } } }.getOrNull().orEmpty()
        _items.value = loaded.map { if (it.state == UploadState.Uploading) it.copy(state = UploadState.Queued) else it }
        publish()
    }

    private fun mutate(f: (List<QueueItem>) -> List<QueueItem>) {
        synchronized(lock) {
            _items.update(f)
            runCatching { storage.save(JsonObject(mapOf("items" to JsonArray(_items.value.map { it.toJson() }))).toString()) }
        }
        publish()
    }

    private fun publish() { _progress.value = compute(_items.value, paused, running, offline) }

    private fun compute(list: List<QueueItem>, paused: Boolean, running: Boolean, offline: Boolean) = QueueProgress(
        total = list.size, finished = list.count { it.state.finished },
        uploaded = list.count { it.state == UploadState.Done }, duplicates = list.count { it.state == UploadState.Duplicate },
        noSpace = list.count { it.state == UploadState.NoSpace }, failed = list.count { it.state == UploadState.Failed },
        bytesDone = list.filter { it.state == UploadState.Done }.sumOf { it.size }, bytesTotal = list.sumOf { it.size },
        paused = paused, running = running, offline = offline,
    )

    fun enqueue(newItems: List<QueueItem>) { if (newItems.isNotEmpty()) mutate { it + newItems } }

    fun pause() { paused = true; publish() }
    fun resumeFlag() { paused = false; publish() }

    /** Stops what is waiting: queued photos are removed (and their files deleted); photos already finished stay for the summary. In-flight ones finish. */
    fun cancel() {
        cancelled = true
        val gone = _items.value.filter { it.state == UploadState.Queued }
        mutate { l -> l.filter { it.state != UploadState.Queued } }
        gone.forEach { blobs.delete(it.path) }
        publish()
    }

    /** Puts failed photos back in the queue (their reservation is dropped; a fresh slot is requested). */
    fun retryFailed() = mutate { l -> l.map { if (it.state == UploadState.Failed) it.copy(state = UploadState.Queued, error = null, slotUrl = null, slotFields = null, mediaId = null) else it } }

    /** Removes finished items from the list (the banner message was read). */
    fun dismissFinished() {
        _items.value.filter { it.state.finished }.forEach { blobs.delete(it.path) }
        mutate { l -> l.filter { !it.state.finished } }
    }

    /** Photos that did not fit are queued again (storage was freed or the plan changed). */
    fun requeueNoSpace() = mutate { l -> l.map { if (it.state == UploadState.NoSpace) it.copy(state = UploadState.Queued, error = null, slotUrl = null, slotFields = null) else it } }

    /** Retries one failed photo (the tile's "Tap to retry"). */
    fun retry(id: String) = mutate { l -> l.map { if (it.id == id && it.state == UploadState.Failed) it.copy(state = UploadState.Queued, error = null, slotUrl = null, slotFields = null, mediaId = null) else it } }

    /** Removes one waiting photo ("Remove from queue"). */
    fun remove(id: String) {
        _items.value.firstOrNull { it.id == id }?.let { blobs.delete(it.path) }
        mutate { l -> l.filter { it.id != id } }
    }

    fun hasWork(): Boolean = _items.value.any { it.state == UploadState.Queued || it.state == UploadState.Uploading }

    /** Processes the queue until nothing is queued, it is paused, cancelled or the network is gone. Safe to call again (a second call while running returns at once). */
    suspend fun run() {
        synchronized(lock) { if (running) return; running = true; cancelled = false; offline = false }
        publish()
        try {
            while (!paused && !cancelled) {
                val batch = _items.value.filter { it.state == UploadState.Queued }.take(batchSize)
                if (batch.isEmpty()) break
                if (!processBatch(batch)) break
            }
        } finally {
            synchronized(lock) { running = false }
            publish()
        }
    }

    /** False when the run should stop (offline or unauthorised). */
    private suspend fun processBatch(batch: List<QueueItem>): Boolean {
        val needSlots = batch.filter { it.slotUrl == null }
        if (needSlots.isNotEmpty()) {
            val answer = try {
                api.requestUploads(needSlots.map { it.request() })
            } catch (e: CancellationException) { throw e
            } catch (e: ApiError.StorageFull) {
                _usage.value = e.usedBytes to e.limitBytes
                setStates(needSlots.map { it.id }) { it.copy(state = UploadState.NoSpace, error = "Not enough storage") }
                return true
            } catch (e: ApiError.Network) { offline = true; return false
            } catch (e: ApiError.Unauthorized) { return false
            } catch (e: ApiError) {
                setStates(needSlots.map { it.id }) { it.copy(state = UploadState.Failed, error = e.message) }
                return true
            }
            _usage.value = answer.usedBytes to answer.limitBytes
            val byIndex = answer.uploads.associateBy { it.index }
            mutate { l ->
                l.map { item ->
                    val i = needSlots.indexOfFirst { it.id == item.id }
                    if (i < 0) item else {
                        val r = byIndex[i]
                        when (r?.status) {
                            SlotStatus.Upload -> if (r.url != null && r.id != null) item.copy(slotUrl = r.url, slotFields = r.fields, mediaId = r.id) else item.copy(state = UploadState.Failed, error = "The server didn't give an upload address.")
                            SlotStatus.Duplicate -> item.copy(state = UploadState.Duplicate, mediaId = r.duplicateOf)
                            SlotStatus.NoSpace -> item.copy(state = UploadState.NoSpace, error = "Not enough storage")
                            else -> item.copy(state = UploadState.Failed, error = r?.reason ?: "The photo was not accepted.")
                        }
                    }
                }
            }
        }
        val ready = _items.value.filter { it.state == UploadState.Queued && it.slotUrl != null && it.id in batch.map { b -> b.id } }
        boundedMap(ready, concurrency) { _, item -> if (!paused && !cancelled) uploadOne(item) }
        return !offline
    }

    private suspend fun uploadOne(item: QueueItem) {
        setStates(listOf(item.id)) { it.copy(state = UploadState.Uploading) }
        val bytes = blobs.read(item.path)
        if (bytes == null) { setStates(listOf(item.id)) { it.copy(state = UploadState.Failed, error = "The photo file is gone.") }; return }
        var last: ApiError = ApiError.Server
        for (attempt in 1..tries) {
            try {
                poster.post(item.slotUrl!!, item.slotFields.orEmpty(), bytes)
                // the prepared file stays until the batch is dismissed: the grid shows it as the photo's own local picture while the server prepares the thumbnail
                setStates(listOf(item.id)) { it.copy(state = UploadState.Done, error = null, slotUrl = null, slotFields = null) }
                return
            } catch (e: CancellationException) { setStates(listOf(item.id)) { it.copy(state = UploadState.Queued) }; throw e
            } catch (e: ApiError) { last = e }
            if (attempt < tries) delay(backoffMillis(attempt))
        }
        if (last is ApiError.Network) offline = true
        // a refused or unreachable slot may have expired: a retry asks for a new one
        setStates(listOf(item.id)) { it.copy(state = if (last is ApiError.Network) UploadState.Queued else UploadState.Failed, error = if (last is ApiError.Network) null else last.message, slotUrl = if (last is ApiError.Network) it.slotUrl else null, slotFields = if (last is ApiError.Network) it.slotFields else null) }
    }

    private fun setStates(ids: List<String>, f: (QueueItem) -> QueueItem) { val s = ids.toSet(); mutate { l -> l.map { if (it.id in s) f(it) else it } } }
}
