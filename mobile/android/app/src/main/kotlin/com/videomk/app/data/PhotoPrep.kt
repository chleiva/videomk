package com.videomk.app.data

import android.content.ContentResolver
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.Paint
import android.net.Uri
import androidx.exifinterface.media.ExifInterface
import com.videomk.app.core.PhotoGeometry
import com.videomk.app.core.PhotoLimits
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

/**
 * Prepares a photo on the phone before it is uploaded: upright, at most 2048 px on its longest side, and with **no metadata at all**
 * (no GPS, camera or date), because only the pixels are re-encoded (Bitmap.compress writes none of the source's EXIF).
 * The server cleans every upload again, so this is for privacy and speed.
 */
object PhotoPrep {
    /** Reads the picked photo (a content:// URI from the system photo picker) and prepares it. Null when it isn't a usable picture. */
    fun jpeg(resolver: ContentResolver, uri: Uri, maxPixel: Int = PhotoLimits.MAX_PIXEL): ByteArray? {
        val raw = try {
            resolver.openInputStream(uri)?.use { it.readBytes() }
        } catch (e: Exception) { null } ?: return null
        return jpeg(raw, maxPixel)
    }

    fun jpeg(raw: ByteArray, maxPixel: Int = PhotoLimits.MAX_PIXEL): ByteArray? {
        if (raw.isEmpty() || raw.size > 120_000_000) return null
        return try { prepare(raw, maxPixel) } catch (e: OutOfMemoryError) { null } catch (e: Exception) { null }
    }

    private fun prepare(raw: ByteArray, maxPixel: Int): ByteArray? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(raw, 0, raw.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null

        val orientation = try {
            ExifInterface(ByteArrayInputStream(raw)).getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_NORMAL)
        } catch (e: Exception) { ExifInterface.ORIENTATION_NORMAL }

        val opts = BitmapFactory.Options().apply { inSampleSize = PhotoGeometry.sampleSize(bounds.outWidth, bounds.outHeight, maxPixel) }
        val decoded = BitmapFactory.decodeByteArray(raw, 0, raw.size, opts) ?: return null

        // 1. upright (apply the orientation tag to the pixels) and 2. fit in maxPixel, in one pass over the pixels
        val (degrees, mirror) = PhotoGeometry.orientation(orientation)
        val upright = Matrix()
        if (mirror) upright.postScale(-1f, 1f)
        if (degrees != 0) upright.postRotate(degrees.toFloat())
        val rotatedW = if (degrees == 90 || degrees == 270) decoded.height else decoded.width
        val rotatedH = if (degrees == 90 || degrees == 270) decoded.width else decoded.height
        val (tw, th) = PhotoGeometry.fit(rotatedW, rotatedH, maxPixel)
        if (tw != rotatedW) upright.postScale(tw.toFloat() / rotatedW, th.toFloat() / rotatedH)
        var bitmap = Bitmap.createBitmap(decoded, 0, 0, decoded.width, decoded.height, upright, true)
        if (bitmap !== decoded) decoded.recycle()

        if (bitmap.hasAlpha()) {   // JPEG has no transparency: put a PNG's transparent areas on white instead of black
            val flat = Bitmap.createBitmap(bitmap.width, bitmap.height, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(flat)
            canvas.drawColor(Color.WHITE)
            canvas.drawBitmap(bitmap, 0f, 0f, Paint(Paint.FILTER_BITMAP_FLAG))
            bitmap.recycle()
            bitmap = flat
        }
        try {
            for (q in PhotoLimits.QUALITIES) {
                val out = ByteArrayOutputStream(512 * 1024)
                if (!bitmap.compress(Bitmap.CompressFormat.JPEG, q, out)) return null
                if (out.size() <= PhotoLimits.MAX_UPLOAD_BYTES) return out.toByteArray()
            }
            return null
        } finally {
            bitmap.recycle()
        }
    }

    /** A small preview for the strip of attached photos (longest side at most [target] px, 16-bit colour: about 70 KB), decoded from the prepared JPEG. */
    fun thumbnail(jpeg: ByteArray, target: Int = 192): Bitmap? {
        val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size, bounds)
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
        val sample = PhotoGeometry.sampleSize(bounds.outWidth, bounds.outHeight, target)
        val opts = BitmapFactory.Options().apply { inSampleSize = sample; inPreferredConfig = Bitmap.Config.RGB_565 }
        val small = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size, opts) ?: return null
        val (w, h) = PhotoGeometry.fit(small.width, small.height, target)
        if (w == small.width && h == small.height) return small
        return Bitmap.createScaledBitmap(small, w, h, true).also { if (it !== small) small.recycle() }
    }
}
