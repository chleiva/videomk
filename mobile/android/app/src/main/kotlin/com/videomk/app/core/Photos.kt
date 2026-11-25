package com.videomk.app.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.serialization.json.JsonObject
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** Photos the user attaches to a video (up to 100). */
object PhotoLimits {
    const val MAX_PHOTOS = 100
    /** Photos prepared (decoded, scaled, re-encoded) at the same time: each one briefly holds a decoded bitmap, so this stays small. */
    const val PREP_PARALLELISM = 2
    /** Photos uploaded at the same time. */
    const val UPLOAD_PARALLELISM = 4
    /** Tries per photo (the first plus two retries). */
    const val UPLOAD_TRIES = 3
    const val MAX_UPLOAD_BYTES = 10_000_000
    const val MAX_PIXEL = 2048
    /** JPEG qualities tried in order until the file fits [MAX_UPLOAD_BYTES]. */
    val QUALITIES = listOf(85, 70, 55)
}

/** How many photos a video of a given length can carry (the server shows several at once), and what to tell the person when it is too short. */
object PhotoCapacity {
    /** The server shows max(3, floor(seconds x 0.85)) photos: 15 s = 12, 30 s = 25, 45 s = 38, 1 min = 51. */
    fun capacity(minutes: Double): Int = maxOf(3, Math.floor(Math.round(minutes * 60) * 0.85 + 1e-9).toInt())

    /** The shortest length (whole seconds, as the server counts) whose capacity reaches [photos]. */
    fun minimumMinutes(photos: Int): Double = if (photos <= 0) 0.0 else Math.ceil(photos / 0.85 - 1e-9) / 60

    /** The smallest length option that shows all [photos]; null when they already fit or no option is long enough. */
    fun suggestion(photos: Int, minutes: Double, options: List<Number>): Double? {
        if (photos <= capacity(minutes)) return null
        val need = minimumMinutes(photos)
        return options.map { it.toDouble() }.sorted().firstOrNull { it >= need - 1e-9 }
    }

    fun minutesText(m: Double): String = Lengths.long(m)

    /** One line, or null when every photo fits. [options] are the app's length choices (minutes). */
    fun hint(photos: Int, minutes: Double, options: List<Number>): String? {
        if (photos <= capacity(minutes)) return null
        val photoWord = { n: Int -> if (n == 1) "photo" else "photos" }
        val need = minimumMinutes(photos)
        val suggestion = options.map { it.toDouble() }.sorted().firstOrNull { it >= need - 1e-9 }
        return if (suggestion != null) {
            "About ${capacity(minutes)} of your $photos ${photoWord(photos)} fit in ${minutesText(minutes)} (the best ones, no duplicates). Choose ${minutesText(suggestion)} to show them all."
        } else {
            val best = capacity(options.maxOfOrNull { it.toDouble() } ?: minutes)
            "About $best of your $photos ${photoWord(photos)} fit in the longest video."
        }
    }
}

/** What a selection does to the room left: the first photos that fit are kept, the rest are left out (and the user is told how many). */
data class PhotoIntake(val accepted: Int, val leftOut: Int) {
    companion object {
        fun plan(selected: Int, remaining: Int): PhotoIntake {
            val take = minOf(maxOf(selected, 0), maxOf(remaining, 0))
            return PhotoIntake(take, maxOf(selected, 0) - take)
        }

        /** Items for one system-picker round: the platform's per-pick maximum, never more than the room left, and at least 2 (the contract refuses fewer). */
        fun pickerMax(platformMax: Int, remaining: Int): Int = maxOf(2, minOf(maxOf(platformMax, 2), remaining))

        /** The picked items from a chooser result: the several (clipData) if present, else the single one (data). No duplicates, order kept. */
        fun <T> extract(single: T?, clip: List<T>): List<T> = (if (clip.isNotEmpty()) clip else listOfNotNull(single)).distinct()

        fun leftOutMessage(leftOut: Int): String =
            "$leftOut photo${if (leftOut == 1) " was" else "s were"} left out: a video can use up to ${PhotoLimits.MAX_PHOTOS}."

        fun unreadableMessage(n: Int): String = "$n photo${if (n == 1) " couldn't" else "s couldn't"} be read and ${if (n == 1) "was" else "were"} skipped."

        fun preparingText(done: Int, total: Int): String = "Preparing ${minOf(done + 1, total)} of $total"
    }
}

/** Runs [work] over [items] at most [parallelism] at a time (not more), returning results in the order of [items]. */
suspend fun <T, R> boundedMap(items: List<T>, parallelism: Int, work: suspend (index: Int, item: T) -> R): List<R> = coroutineScope {
    val gate = Semaphore(maxOf(1, parallelism))
    items.mapIndexed { i, item -> async { gate.withPermit { work(i, item) } } }.awaitAll()
}

/**
 * Prepares [items] with [parallelism] in flight and hands each result to [onResult] **in order**, as soon as it and all before it are ready.
 * Only a few results are ever waiting, because the next window of items starts only when the previous window has been delivered.
 */
suspend fun <T, R> prepareInOrder(items: List<T>, parallelism: Int, prepare: suspend (T) -> R, onResult: suspend (index: Int, result: R) -> Unit) {
    var next = 0
    for (window in items.chunked(maxOf(1, parallelism))) {
        val results = coroutineScope { window.map { async { prepare(it) } }.awaitAll() }
        for (r in results) onResult(next++, r)
    }
}

/** Where a picked photo's bytes come from (a content uri on the phone, a file in tests). Null when it can't be opened. */
fun interface PickedSource<T> { fun open(item: T): java.io.InputStream? }

/**
 * Private copies of the picked originals, made right after the pick while the gallery app's read grant is valid, so preparing never touches the provider
 * again (it survives a rotation and the gallery app going away). Files live in `<root>/<session>/<n>.src`; the prepared JPEG is what stays in memory.
 */
class PickedCache(private val root: java.io.File, private val maxBytes: Long = 120_000_000L) {
    private val session = java.io.File(root, UUID.randomUUID().toString())
    private val counter = AtomicInteger(0)

    /** Streams the item into a new file with a small buffer (never the whole original in memory). Null when it can't be read or is too big. */
    fun <T> copy(item: T, source: PickedSource<T>): java.io.File? {
        val input = try { source.open(item) } catch (e: Exception) { null } ?: return null
        session.mkdirs()
        val file = java.io.File(session, "${counter.incrementAndGet()}.src")
        try {
            input.use { ins -> file.outputStream().use { out ->
                val buf = ByteArray(64 * 1024)
                var total = 0L
                while (true) {
                    val n = ins.read(buf)
                    if (n < 0) break
                    total += n
                    if (total > maxBytes) throw IOException("too big")
                    out.write(buf, 0, n)
                }
                if (total == 0L) throw IOException("empty")
            } }
            return file
        } catch (e: Exception) {
            file.delete()
            return null
        }
    }

    /** Files currently held for this session. */
    fun files(): List<java.io.File> = session.listFiles()?.toList() ?: emptyList()

    /** Removes this session's folder and everything in it. */
    fun endSession() { session.deleteRecursively() }

    companion object {
        /** At app start: remove the folders a crashed session left behind. */
        fun cleanLeftovers(root: java.io.File) { root.deleteRecursively() }
    }
}

/** The pure part of photo preparation (the pixels are handled by the platform code in `data/PhotoPrep`). */
object PhotoGeometry {
    /** Largest power-of-two sample size that still leaves at least [maxPixel] on the longest side (decode small, then scale precisely). */
    fun sampleSize(width: Int, height: Int, maxPixel: Int = PhotoLimits.MAX_PIXEL): Int {
        var s = 1
        val longest = maxOf(width, height)
        while (longest / (s * 2) >= maxPixel) s *= 2
        return s
    }

    /** Output size with the longest side at most [maxPixel], keeping the aspect ratio. Never upscales. */
    fun fit(width: Int, height: Int, maxPixel: Int = PhotoLimits.MAX_PIXEL): Pair<Int, Int> {
        val longest = maxOf(width, height)
        if (longest <= maxPixel) return width to height
        val f = maxPixel.toDouble() / longest
        return maxOf(1, Math.round(width * f).toInt()) to maxOf(1, Math.round(height * f).toInt())
    }

    /** For an EXIF orientation value (1..8): degrees to rotate clockwise and whether to mirror horizontally first. */
    fun orientation(exif: Int): Pair<Int, Boolean> = when (exif) {
        2 -> 0 to true
        3 -> 180 to false
        4 -> 180 to true
        5 -> 270 to true
        6 -> 90 to false
        7 -> 90 to true
        8 -> 270 to false
        else -> 0 to false
    }
}

data class UploadSlot(val id: String, val url: String, val fields: Map<String, String>) {
    companion object {
        fun fromJson(o: JsonObject): UploadSlot = UploadSlot(
            id = o.requireString("id"),
            url = o.requireString("url"),
            fields = o.obj("fields")?.mapNotNull { (k, v) -> (v as? kotlinx.serialization.json.JsonPrimitive)?.takeIf { it.isString }?.let { k to it.content } }?.toMap() ?: emptyMap(),
        )
    }
}

/** A multipart/form-data body for S3's presigned POST: the signed fields first, the file last (S3 requires that order). */
object MultipartForm {
    class Built(val body: ByteArray, val contentType: String)

    fun body(
        fields: Map<String, String>, file: ByteArray, fileName: String = "photo.jpg", mimeType: String = "image/jpeg",
        boundary: String = UUID.randomUUID().toString(),
    ): Built {
        val out = ByteArrayOutputStream(file.size + 2048)
        for ((name, value) in fields.toSortedMap()) {
            out.write("--$boundary\r\nContent-Disposition: form-data; name=\"$name\"\r\n\r\n$value\r\n".toByteArray())
        }
        out.write("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"$fileName\"\r\nContent-Type: $mimeType\r\n\r\n".toByteArray())
        out.write(file)
        out.write("\r\n--$boundary--\r\n".toByteArray())
        return Built(out.toByteArray(), "multipart/form-data; boundary=$boundary")
    }
}

/**
 * Uploads the prepared photos and returns their ids in the same order: one presign call for all of them, then [parallelism] posts at a time, each photo
 * tried up to [tries] times with a short backoff. If any photo still fails, the others finish and this throws one clear error (the caller keeps the photos
 * and the user can retry without choosing them again).
 */
class PhotoUploader(
    private val api: ApiClient,
    private val http: OkHttpClient = defaultHttpClient(),
    private val parallelism: Int = PhotoLimits.UPLOAD_PARALLELISM,
    private val tries: Int = PhotoLimits.UPLOAD_TRIES,
    private val backoffMillis: (failedAttempts: Int) -> Long = { 500L * it },
) {
    suspend fun upload(photos: List<ByteArray>, progress: (done: Int, total: Int) -> Unit = { _, _ -> }): List<String> {
        if (photos.isEmpty() || photos.size > PhotoLimits.MAX_PHOTOS) throw ApiError.Invalid("Choose between 1 and ${PhotoLimits.MAX_PHOTOS} photos.")
        val slots = api.requestUploads(photos.size)
        if (slots.size != photos.size) throw ApiError.Server
        val done = AtomicInteger(0)
        progress(0, photos.size)
        val failures = boundedMap(photos.zip(slots), parallelism) { _, (photo, slot) ->
            val ok = postWithRetry(photo, slot)
            if (ok == null) synchronized(done) { progress(done.incrementAndGet(), photos.size) }   // counts reach the caller in order
            ok
        }.filterNotNull()
        if (failures.isNotEmpty()) {
            if (failures.all { it is ApiError.Network }) throw ApiError.Network   // offline: say so
            throw ApiError.Invalid(
                if (photos.size == 1) "A photo couldn't be uploaded. Please try again."
                else "${failures.size} of ${photos.size} photos couldn't be uploaded. Tap Try again: your photos are still here.",
            )
        }
        return slots.map { it.id }
    }

    /** Null when the photo went up, otherwise the last error. */
    private suspend fun postWithRetry(photo: ByteArray, slot: UploadSlot): ApiError? {
        var last: ApiError = ApiError.Server
        for (attempt in 1..tries) {
            currentCoroutineContext().ensureActive()
            try { post(photo, slot); return null } catch (e: ApiError) { last = e }
            if (attempt < tries) delay(backoffMillis(attempt))
        }
        return last
    }

    private suspend fun post(photo: ByteArray, slot: UploadSlot) {
        val url = slot.url.toHttpUrlOrNull() ?: throw ApiError.Server
        val form = MultipartForm.body(slot.fields, photo)
        // deliberately no Authorization header: the presigned fields are the credential, and the login token must never go to storage
        val req = Request.Builder().url(url).post(form.body.toRequestBody(form.contentType.toMediaType())).build()
        try {
            http.newBuilder().callTimeout(120, TimeUnit.SECONDS).build().newCall(req).await().use { r ->
                if (r.code !in 200..299) throw ApiError.Invalid("A photo couldn't be uploaded. Please try again.")
            }
        } catch (e: CancellationException) { throw e } catch (e: ApiError) { throw e } catch (e: IOException) { throw ApiError.Network }
    }
}
