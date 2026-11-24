package com.videomk.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import androidx.exifinterface.media.ExifInterface
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.videomk.app.core.PhotoLimits
import com.videomk.app.data.PhotoPrep
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File

/** The real image pipeline on a real decoder: metadata gone, upright pixels, size limits. */
@RunWith(AndroidJUnit4::class)
class PhotoPrepTest {
    /** A JPEG with a red square in the top-left corner, EXIF GPS + camera + date and an orientation tag. */
    private fun sourceJpeg(w: Int, h: Int, orientation: Int, withExif: Boolean = true): ByteArray {
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        bmp.eraseColor(Color.BLUE)
        val sq = minOf(w, h) / 4
        for (x in 0 until sq) for (y in 0 until sq) bmp.setPixel(x, y, Color.RED)
        val file = File.createTempFile("src", ".jpg", Ui.context.cacheDir)
        file.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 95, it) }
        if (withExif) {
            val exif = ExifInterface(file.absolutePath)
            exif.setAttribute(ExifInterface.TAG_ORIENTATION, orientation.toString())
            exif.setLatLong(48.8584, 2.2945)
            exif.setAttribute(ExifInterface.TAG_MAKE, "SecretCam")
            exif.setAttribute(ExifInterface.TAG_MODEL, "X100")
            exif.setAttribute(ExifInterface.TAG_DATETIME, "2025:01:02 03:04:05")
            exif.setAttribute(ExifInterface.TAG_DATETIME_ORIGINAL, "2024:12:31 23:59:58")
            exif.saveAttributes()
        }
        return file.readBytes().also { file.delete() }
    }

    private fun assertNoMetadata(jpeg: ByteArray) {
        val exif = ExifInterface(ByteArrayInputStream(jpeg))
        assertNull("GPS must be gone", exif.latLong)
        assertNull(exif.getAttribute(ExifInterface.TAG_GPS_LATITUDE))
        assertNull(exif.getAttribute(ExifInterface.TAG_MAKE)); assertNull(exif.getAttribute(ExifInterface.TAG_MODEL))
        assertNull(exif.getAttribute(ExifInterface.TAG_DATETIME)); assertNull(exif.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL))
        assertEquals("orientation tag must be reset (the pixels are already upright)", ExifInterface.ORIENTATION_UNDEFINED, exif.getAttributeInt(ExifInterface.TAG_ORIENTATION, ExifInterface.ORIENTATION_UNDEFINED))
        // belt and braces: no EXIF/XMP/GPS marker text anywhere in the bytes
        val text = String(jpeg, Charsets.ISO_8859_1)
        assertTrue("no Exif segment", !text.contains("Exif\u0000\u0000")); assertTrue(!text.contains("SecretCam")); assertTrue(!text.contains("http://ns.adobe.com/xap"))
    }

    private fun decode(jpeg: ByteArray) = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size)!!

    @Test fun gpsAndAllMetadataAreStrippedAndSizeIsLimited() {
        val src = sourceJpeg(4000, 3000, ExifInterface.ORIENTATION_NORMAL)
        // the source really has the secrets
        val before = ExifInterface(ByteArrayInputStream(src))
        assertNotNull("test setup: the source must contain GPS", before.latLong); assertEquals("SecretCam", before.getAttribute(ExifInterface.TAG_MAKE))
        val out = PhotoPrep.jpeg(src)!!
        assertNoMetadata(out)
        val bmp = decode(out)
        assertEquals(2048, maxOf(bmp.width, bmp.height)); assertEquals(2048 to 1536, bmp.width to bmp.height)
        assertTrue(out.size <= PhotoLimits.MAX_UPLOAD_BYTES)
    }

    @Test fun dateAndApproximatePlaceAreReadFromTheOriginalAndAreGoneFromTheOutput() {
        val src = sourceJpeg(1200, 800, ExifInterface.ORIENTATION_NORMAL)   // Eiffel tower 48.8584, 2.2945 and a known capture time
        val meta = com.videomk.app.data.PhotoExif.read(ByteArrayInputStream(src), com.videomk.app.core.PhotoMetaPolicy())!!
        assertEquals("2024-12-31T23:59:58", meta.taken)
        assertEquals(48.86, meta.lat!!, 0.0); assertEquals(2.29, meta.lon!!, 0.0)
        val noPlace = com.videomk.app.data.PhotoExif.read(ByteArrayInputStream(src), com.videomk.app.core.PhotoMetaPolicy(useLocations = false))!!
        assertEquals("2024-12-31T23:59:58", noPlace.taken); assertNull(noPlace.lat)
        assertNull(com.videomk.app.data.PhotoExif.read(ByteArrayInputStream(src), com.videomk.app.core.PhotoMetaPolicy(false, false)))
        assertNoMetadata(PhotoPrep.jpeg(src)!!)
        assertNull(com.videomk.app.data.PhotoExif.read(ByteArrayInputStream(PhotoPrep.jpeg(src)!!), com.videomk.app.core.PhotoMetaPolicy()))
        assertNull(com.videomk.app.data.PhotoExif.read(ByteArrayInputStream(sourceJpeg(300, 300, 1, withExif = false)), com.videomk.app.core.PhotoMetaPolicy()))
    }

    @Test fun theStripPreviewIsSmall() {
        val out = PhotoPrep.jpeg(sourceJpeg(4000, 3000, ExifInterface.ORIENTATION_NORMAL))!!
        val t = PhotoPrep.thumbnail(out)!!
        assertTrue("preview is at most 192 px, was ${t.width}x${t.height}", maxOf(t.width, t.height) <= 192 && maxOf(t.width, t.height) >= 96)
        assertTrue("about 70 KB, not megabytes", t.byteCount < 200_000)
    }

    @Test fun orientationSixIsAppliedToThePixels() {
        // A 4000x3000 file tagged "rotate 90 clockwise to view": the upright picture is 3000x4000 (portrait), scaled to 1536x2048.
        val out = PhotoPrep.jpeg(sourceJpeg(4000, 3000, ExifInterface.ORIENTATION_ROTATE_90))!!
        assertNoMetadata(out)
        val bmp = decode(out)
        assertEquals(1536 to 2048, bmp.width to bmp.height)
        // the red square was top-left; after a 90 degree clockwise turn it is top-right
        assertTrue("top-right is red", isRed(bmp.getPixel(bmp.width - 40, 40)))
        assertTrue("top-left is blue", isBlue(bmp.getPixel(40, 40)))
    }

    @Test fun orientationThreeAndEightAreApplied() {
        val r180 = decode(PhotoPrep.jpeg(sourceJpeg(800, 600, ExifInterface.ORIENTATION_ROTATE_180))!!)
        assertEquals(800 to 600, r180.width to r180.height)
        assertTrue("bottom-right is red", isRed(r180.getPixel(r180.width - 20, r180.height - 20)))
        val r270 = decode(PhotoPrep.jpeg(sourceJpeg(800, 600, ExifInterface.ORIENTATION_ROTATE_270))!!)
        assertEquals(600 to 800, r270.width to r270.height)
        assertTrue("bottom-left is red", isRed(r270.getPixel(20, r270.height - 20)))
    }

    @Test fun smallPhotosAreNotUpscaledAndPhotosWithoutExifWork() {
        val out = PhotoPrep.jpeg(sourceJpeg(640, 480, 1, withExif = false))!!
        val bmp = decode(out)
        assertEquals(640 to 480, bmp.width to bmp.height); assertNoMetadata(out)
    }

    @Test fun pngWithTransparencyBecomesAJpegOnWhite() {
        val bmp = Bitmap.createBitmap(300, 200, Bitmap.Config.ARGB_8888)   // fully transparent
        val png = ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
        val out = decode(PhotoPrep.jpeg(png)!!)
        val p = out.getPixel(150, 100)
        assertTrue(Color.red(p) > 240 && Color.green(p) > 240 && Color.blue(p) > 240)
    }

    @Test fun notAPictureIsRejectedWithoutCrashing() {
        assertNull(PhotoPrep.jpeg(ByteArray(0)))
        assertNull(PhotoPrep.jpeg("this is not an image".toByteArray()))
        assertNull(PhotoPrep.jpeg(ByteArray(5000) { it.toByte() }))
    }

    @Test fun anIncompressibleLargePhotoStillFitsTenMegabytes() {
        // random noise is the worst case for JPEG: 4000x3000 noise would be far above 10 MB at quality 95
        val bmp = Bitmap.createBitmap(4000, 3000, Bitmap.Config.ARGB_8888)
        val rnd = java.util.Random(1)
        val row = IntArray(4000)
        for (y in 0 until 3000) { for (x in 0 until 4000) row[x] = Color.rgb(rnd.nextInt(256), rnd.nextInt(256), rnd.nextInt(256)); bmp.setPixels(row, 0, 4000, 0, y, 4000, 1) }
        val src = ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.JPEG, 100, it) }.toByteArray()
        val out = PhotoPrep.jpeg(src)
        assertNotNull(out); assertTrue(out!!.size <= PhotoLimits.MAX_UPLOAD_BYTES); assertEquals(2048, maxOf(decode(out).width, decode(out).height))
    }

    @Test fun theRealPhoneJpegWithGpsAndRotationIsCleaned() {
        val file = File(Ui.context.filesDir, "p3.jpg")   // pushed by the QA setup (README); skipped when absent
        assumeTrue("p3.jpg not pushed", file.exists())
        val raw = file.readBytes()
        val before = ExifInterface(ByteArrayInputStream(raw))
        assumeTrue("p3.jpg has no GPS", before.latLong != null)
        val out = PhotoPrep.jpeg(raw)!!
        assertNoMetadata(out)
        val bmp = decode(out)
        assertTrue(maxOf(bmp.width, bmp.height) <= 2048)
        val rotated = before.rotationDegrees != 0
        val srcOpts = BitmapFactory.Options().apply { inJustDecodeBounds = true }.also { BitmapFactory.decodeByteArray(raw, 0, raw.size, it) }
        if (rotated && (before.rotationDegrees == 90 || before.rotationDegrees == 270)) assertTrue("width/height swapped by the rotation", (srcOpts.outWidth > srcOpts.outHeight) == (bmp.width < bmp.height))
    }

    private fun isRed(c: Int) = Color.red(c) > 180 && Color.green(c) < 90 && Color.blue(c) < 90
    private fun isBlue(c: Int) = Color.blue(c) > 180 && Color.red(c) < 90 && Color.green(c) < 90
}
