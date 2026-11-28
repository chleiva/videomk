package com.videomk.app.data

import android.content.ContentResolver
import android.content.Context
import android.graphics.Bitmap
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.media.MediaMuxer
import android.net.Uri
import android.provider.OpenableColumns
import com.videomk.app.core.ClipMedia
import com.videomk.app.core.ClipProbe
import com.videomk.app.core.VideoPick
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer

/** What the system photo picker handed over (a video). The grant is temporary and never made persistable: the file is read once into a private copy. Name and size are never logged. */
object VideoPicker {
    fun pickOf(resolver: ContentResolver, uri: Uri): VideoPick {
        var name: String? = null
        var size: Long? = null
        try {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    c.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 && !c.isNull(it) }?.let { name = c.getString(it) }
                    c.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 && !c.isNull(it) }?.let { size = c.getLong(it) }
                }
            }
        } catch (e: Exception) { /* a provider that will not say: the copy checks the size itself */ }
        val mime = try { resolver.getType(uri) } catch (e: Exception) { null }
        return VideoPick(name, mime, size, uri) { try { resolver.openInputStream(uri) } catch (e: Exception) { null } }
    }
}

/** The platform's own tools, no extra library: [MediaMetadataRetriever] to read, [MediaExtractor] + [MediaMuxer] to cut the first seconds without re-encoding. */
class AndroidClipMedia(private val context: Context) : ClipMedia {
    override fun probe(pick: VideoPick): ClipProbe? {
        val uri = pick.handle as? Uri ?: return null
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(context, uri)
            readProbe(r)
        } catch (e: Exception) { null } finally { runCatching { r.release() } }
    }

    private fun readProbe(r: MediaMetadataRetriever): ClipProbe {
        val dur = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()
        val audio = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_AUDIO)?.let { it == "yes" }
        var w = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull()
        var h = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull()
        val rot = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
        if (rot == 90 || rot == 270) { val t = w; w = h; h = t }
        return ClipProbe(dur, audio, w, h, frame(r, dur))
    }

    /** A poster from the clip itself: a frame about half a second in (or the first one for a very short clip). */
    private fun frame(r: MediaMetadataRetriever, durationMs: Long?): ByteArray? = try {
        val at = if ((durationMs ?: 0) > 1200) 500_000L else 0L
        val bmp = r.getFrameAtTime(at, MediaMetadataRetriever.OPTION_CLOSEST_SYNC) ?: r.getFrameAtTime(0)
        bmp?.let { b ->
            val scale = 384f / maxOf(b.width, b.height)
            val small = if (scale < 1f) Bitmap.createScaledBitmap(b, (b.width * scale).toInt().coerceAtLeast(1), (b.height * scale).toInt().coerceAtLeast(1), true) else b
            ByteArrayOutputStream().also { small.compress(Bitmap.CompressFormat.JPEG, 82, it) }.toByteArray()
        }
    } catch (e: Exception) { null }

    override fun thumbnail(file: File): ByteArray? {
        val r = MediaMetadataRetriever()
        return try {
            r.setDataSource(file.absolutePath)
            frame(r, r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull())
        } catch (e: Exception) { null } finally { runCatching { r.release() } }
    }

    /** Copies the samples up to [seconds] into a new MP4. Starts at the first sample, so there is no key-frame problem at the front; without [keepAudio] the sound tracks are left out. */
    override fun trim(src: File, dst: File, seconds: Double, keepAudio: Boolean): Boolean {
        val extractor = MediaExtractor()
        var muxer: MediaMuxer? = null
        var started = false
        try {
            extractor.setDataSource(src.absolutePath)
            val map = HashMap<Int, Int>()
            var rotation = 0
            val r = MediaMetadataRetriever()
            try { r.setDataSource(src.absolutePath); rotation = r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0 } catch (e: Exception) { } finally { runCatching { r.release() } }
            muxer = MediaMuxer(dst.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
            if (rotation != 0) muxer.setOrientationHint(rotation)
            var haveVideo = false; var haveAudio = false
            for (i in 0 until extractor.trackCount) {
                val f = extractor.getTrackFormat(i)
                val mime = f.getString(MediaFormat.KEY_MIME) ?: continue
                val take = (mime.startsWith("video/") && !haveVideo) || (keepAudio && !haveAudio && mime.startsWith("audio/"))
                if (!take) continue
                if (mime.startsWith("video/")) haveVideo = true else haveAudio = true
                map[i] = muxer.addTrack(f)
                extractor.selectTrack(i)
            }
            if (!haveVideo) return false
            muxer.start(); started = true
            val limitUs = (seconds * 1_000_000).toLong()
            val buf = ByteBuffer.allocate(4 * 1024 * 1024)
            val info = MediaCodec.BufferInfo()
            while (true) {
                val size = extractor.readSampleData(buf, 0)
                val t = extractor.sampleTime
                if (size < 0 || t < 0 || t > limitUs) break
                info.set(0, size, t, if (extractor.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                muxer.writeSampleData(map[extractor.sampleTrackIndex] ?: break, buf, info)
                extractor.advance()
            }
            return true
        } catch (e: Exception) {
            return false
        } finally {
            runCatching { extractor.release() }
            runCatching { if (started) muxer?.stop() }
            runCatching { muxer?.release() }
        }
    }
}
