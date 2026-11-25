package com.videomk.app.data

import android.content.ContentResolver
import android.content.Context
import android.net.Uri
import com.videomk.app.core.BlobSource
import com.videomk.app.core.MediaApi
import com.videomk.app.core.MediaUploadQueue
import com.videomk.app.core.HttpSlotPoster
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.PickedCache
import com.videomk.app.core.PickedSource
import com.videomk.app.core.QueueItem
import com.videomk.app.core.QueueStorage
import com.videomk.app.core.boundedMap
import com.videomk.app.core.sha256Hex
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import java.io.File
import java.util.UUID

/**
 * Adds photos from the phone to My media: each one is copied right away while the gallery's read grant is valid, read for date and approximate place
 * (only if the Settings switches are on), prepared (upright, at most 2048 px, no metadata: the same [PhotoPrep] as video photos), hashed, kept as a file in the
 * app's private folder and queued. The queue lives in the app scope, so the banner survives leaving the tab; it is saved to disk and resumed on next launch.
 */
class MediaUploadController(context: Context, api: MediaApi, http: OkHttpClient, private val scope: CoroutineScope, poster: com.videomk.app.core.SlotPoster? = null) {
    private val app = context.applicationContext
    private val dir = File(app.filesDir, "media-queue").also { it.mkdirs() }
    private val settings = PhotoSettings(app)

    val queue = MediaUploadQueue(
        api,
        object : QueueStorage {
            private val f = File(dir, "queue.json")
            override fun load() = runCatching { f.readText() }.getOrNull()
            override fun save(text: String) { val t = File(dir, "queue.json.tmp"); t.writeText(text); t.renameTo(f) }
        },
        object : BlobSource {
            override fun read(path: String) = runCatching { File(path).readBytes() }.getOrNull()
            override fun delete(path: String) { runCatching { File(path).delete() } }
        },
        poster ?: HttpSlotPoster(http),
    )

    /** Shared by the Media tab and the composer picker: how many photos should be listed once the server has prepared the uploads. */
    val arrivals = com.videomk.app.core.ArrivalTracker()

    private val _preparing = MutableStateFlow<Pair<Int, Int>?>(null)
    /** (done, total) while photos are being copied and prepared. */
    val preparing: StateFlow<Pair<Int, Int>?> = _preparing.asStateFlow()
    private val _skipped = MutableStateFlow(0)
    /** Photos that couldn't be read at all (not a picture, or the source went away). */
    val skipped: StateFlow<Int> = _skipped.asStateFlow()

    init { File(app.cacheDir, "media-pick").deleteRecursively() }

    /** When the current upload batch began (device clock): the organise "since" is derived from it. Set when photos are added to an idle queue. */
    @Volatile var batchStart: Long = 0L
        private set

    fun add(resolver: ContentResolver, uris: List<Uri>) {
        if (uris.isEmpty()) return
        if (!queue.hasWork() && _preparing.value == null) batchStart = System.currentTimeMillis()
        scope.launch {
            val total = uris.size
            _preparing.value = 0 to total
            val cache = PickedCache(File(app.cacheDir, "media-pick"))
            val source = PickedSource<Uri> { resolver.openInputStream(it) }
            val files = ArrayList<File?>()
            // copy first (grants are temporary), a few at a time, in order
            com.videomk.app.core.prepareInOrder(uris, PhotoLimits.PREP_PARALLELISM, prepare = { withContext(Dispatchers.IO) { cache.copy(it, source) } }) { _, f -> files += f }
            var done = 0
            val items = boundedMap(files, PhotoLimits.PREP_PARALLELISM) { _, f ->
                val item = withContext(Dispatchers.Default) { f?.let { prepareOne(it) } }
                f?.delete()
                synchronized(this@MediaUploadController) { done += 1; _preparing.value = done to total }
                item
            }
            cache.endSession()
            val good = items.filterNotNull()
            _skipped.value += items.size - good.size
            _preparing.value = null
            queue.enqueue(good)
            start()
        }
    }

    private fun prepareOne(f: File): QueueItem? = try {
        val policy = settings.policy
        val meta = PhotoExif.read(f, policy)   // from the original, before it is re-encoded without any metadata
        val jpeg = PhotoPrep.jpeg(f.readBytes()) ?: return null
        val id = UUID.randomUUID().toString()
        val out = File(dir, "$id.jpg"); out.writeBytes(jpeg)
        val m = meta?.limitedTo(policy)
        QueueItem(id = id, path = out.absolutePath, size = jpeg.size.toLong(), sha256 = sha256Hex(jpeg), taken = m?.taken, lat = m?.lat.takeIf { m?.lon != null }, lon = m?.lon.takeIf { m?.lat != null })
    } catch (e: Exception) { null }

    fun clearSkipped() { _skipped.value = 0 }

    fun start() { scope.launch { queue.run() } }
    fun pause() = queue.pause()
    fun resume() { queue.resumeFlag(); start() }
    fun cancel() = queue.cancel()
    fun retryFailed() { queue.retryFailed(); start() }
    fun resumeIfAny() { if (queue.hasWork()) start() }
}

/** The disk copy of the cached first page (a JSON file in the app's private cache folder). */
class FilePageDisk(private val dir: File) : com.videomk.app.core.PageDisk {
    init { dir.mkdirs() }
    override fun read(key: String) = runCatching { File(dir, "$key.json").readText() }.getOrNull()
    override fun write(key: String, text: String) { runCatching { File(dir, "$key.json").writeText(text) } }
    override fun clear() { dir.listFiles()?.forEach { it.delete() } }
}
