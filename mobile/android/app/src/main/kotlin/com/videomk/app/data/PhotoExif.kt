package com.videomk.app.data

import androidx.exifinterface.media.ExifInterface
import com.videomk.app.core.PhotoMeta
import com.videomk.app.core.PhotoMetaPolicy
import java.io.File
import java.io.InputStream

/** Reads capture time and an approximate place from an ORIGINAL photo, before [PhotoPrep] strips everything. Best effort: any problem means "nothing". */
object PhotoExif {
    fun read(file: File, policy: PhotoMetaPolicy): PhotoMeta? {
        if (!policy.useDates && !policy.useLocations) return null
        return try { file.inputStream().use { read(it, policy) } } catch (e: Exception) { null }
    }

    fun read(input: InputStream, policy: PhotoMetaPolicy): PhotoMeta? {
        if (!policy.useDates && !policy.useLocations) return null
        return try {
            val exif = ExifInterface(input)
            PhotoMeta.fromExif(
                exif.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL), exif.getAttribute(ExifInterface.TAG_DATETIME),
                if (policy.useLocations) exif.latLong else null, policy,
            ).takeIf { !it.isEmpty }
        } catch (e: Exception) { null }
    }
}
