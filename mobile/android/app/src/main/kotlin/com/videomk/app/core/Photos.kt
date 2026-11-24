package com.videomk.app.core

import kotlinx.coroutines.CancellationException
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

/** Photos the user attaches to a video (up to 10). */
object PhotoLimits {
    const val MAX_PHOTOS = 10
    const val MAX_UPLOAD_BYTES = 10_000_000
    const val MAX_PIXEL = 2048
    /** JPEG qualities tried in order until the file fits [MAX_UPLOAD_BYTES]. */
    val QUALITIES = listOf(85, 70, 55)
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

/** Uploads the prepared photos and returns their ids in the same order. Throws on the first failure (the caller keeps the photos and can retry). */
class PhotoUploader(private val api: ApiClient, private val http: OkHttpClient = defaultHttpClient()) {
    suspend fun upload(photos: List<ByteArray>, progress: (done: Int, total: Int) -> Unit = { _, _ -> }): List<String> {
        if (photos.isEmpty() || photos.size > PhotoLimits.MAX_PHOTOS) throw ApiError.Invalid("Choose between 1 and ${PhotoLimits.MAX_PHOTOS} photos.")
        val slots = api.requestUploads(photos.size)
        if (slots.size != photos.size) throw ApiError.Server
        val ids = ArrayList<String>()
        progress(0, photos.size)
        for ((photo, slot) in photos.zip(slots)) {
            currentCoroutineContext().ensureActive()
            post(photo, slot)
            ids += slot.id
            progress(ids.size, photos.size)
        }
        return ids
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
