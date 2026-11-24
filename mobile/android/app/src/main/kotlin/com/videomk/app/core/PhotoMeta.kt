package com.videomk.app.core

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Which parts of a photo's metadata may be read and sent (the two switches in Settings). */
data class PhotoMetaPolicy(val useDates: Boolean = true, val useLocations: Boolean = true)

/**
 * What is read from a photo's original before it is stripped: when it was taken (local wall-clock, no zone) and an approximate place.
 * Latitude and longitude are rounded to 2 decimals (about 1 km) the moment they are created, so a precise coordinate never exists outside the reader.
 */
data class PhotoMeta(val taken: String? = null, val lat: Double? = null, val lon: Double? = null) {
    val isEmpty: Boolean get() = taken == null && (lat == null || lon == null)

    /** The same metadata limited to what the switches allow. */
    fun limitedTo(policy: PhotoMetaPolicy): PhotoMeta =
        PhotoMeta(taken = if (policy.useDates) taken else null, lat = if (policy.useLocations) lat else null, lon = if (policy.useLocations) lon else null)

    companion object {
        private val DATE = Regex("""^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})""")

        /** EXIF "YYYY:MM:DD HH:MM:SS" to "YYYY-MM-DDTHH:MM:SS"; null when it isn't a real date (cameras write zeros for "unknown"). */
        fun parseDate(exif: String?): String? {
            val m = DATE.find(exif?.trim() ?: return null) ?: return null
            val g = m.groupValues.drop(1).map { it.toInt() }
            val y = g[0]; val mo = g[1]; val d = g[2]; val h = g[3]; val mi = g[4]; val s = g[5]
            if (y < 1900 || mo !in 1..12 || d !in 1..31 || h !in 0..23 || mi !in 0..59 || s !in 0..60) return null
            return "%04d-%02d-%02dT%02d:%02d:%02d".format(y, mo, d, h, mi, minOf(s, 59))
        }

        /** Two decimals (about 1 km), never negative zero. */
        fun round2(v: Double): Double = (Math.round(v * 100.0) / 100.0).let { if (it == 0.0) 0.0 else it }

        /** A signed latitude and longitude (south and west negative, as ExifInterface returns them) rounded to 2 decimals; null when out of range. */
        fun place(lat: Double?, lon: Double?): Pair<Double, Double>? {
            if (lat == null || lon == null || lat.isNaN() || lon.isNaN()) return null
            if (lat !in -90.0..90.0 || lon !in -180.0..180.0) return null
            return round2(lat) to round2(lon)
        }

        /** Builds the metadata from the raw EXIF values, reading only what the policy allows (a switch that is off is not looked at). */
        fun fromExif(dateOriginal: String?, dateTime: String?, latLong: DoubleArray?, policy: PhotoMetaPolicy): PhotoMeta {
            val taken = if (policy.useDates) parseDate(dateOriginal) ?: parseDate(dateTime) else null
            val p = if (policy.useLocations && latLong != null && latLong.size >= 2) place(latLong[0], latLong[1]) else null
            return PhotoMeta(taken, p?.first, p?.second)
        }

        /** The `media_meta` request field: keyed by media id, only photos that have something, only the fields present. Null when nothing at all. */
        fun requestJson(ids: List<String>, metas: List<PhotoMeta?>, policy: PhotoMetaPolicy = PhotoMetaPolicy()): JsonObject? {
            val entries = ids.zip(metas).mapNotNull { (id, m) ->
                val lim = m?.limitedTo(policy)?.takeIf { !it.isEmpty } ?: return@mapNotNull null
                val withPlace = lim.lat != null && lim.lon != null
                id to buildJsonObject {
                    lim.taken?.let { put("taken", it) }
                    if (withPlace) { put("lat", lim.lat!!); put("lon", lim.lon!!) }
                }
            }
            return if (entries.isEmpty()) null else JsonObject(entries.toMap())
        }
    }
}
