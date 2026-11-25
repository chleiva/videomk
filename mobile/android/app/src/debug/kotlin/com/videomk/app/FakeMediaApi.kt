package com.videomk.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import android.util.Base64
import com.videomk.app.core.*
import java.io.ByteArrayOutputStream
import java.time.LocalDateTime

/** Debug only: made-up My media data with gradient thumbnails (data: URIs), to look at the screens without a server. Never in a release build. */
class FakeMediaApi : MediaApi {
    private val places = listOf("Phuket, Thailand", "Lisbon, Portugal", "Kyoto, Japan", null, "Cape Town, South Africa", null)
    private val photos = MutableList(150) { i ->
        val t = LocalDateTime.of(2025, 9, 28, 14, 0).minusDays(i * 2L).minusHours(i % 5L)
        MediaPhoto("p$i", if (i % 11 == 7) null else t.toString().take(19).let { if (it.length == 16) "$it:00" else it }, t.plusDays(1).toString().take(16) + ":00Z",
            places[i % places.size], 1536, 2048, 900_000L + i * 4000, thumb(i), if (i % 9 == 0) listOf("c1") else emptyList())
    }
    private val cols = mutableListOf(MediaCollection("c1", "Family", "👪", photos.count { "c1" in it.collections }, "p0"), MediaCollection("c2", "Thailand", "🏝️", 0, null))

    private fun thumb(i: Int): String {
        val bmp = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
        val hue = (i * 37) % 360
        Canvas(bmp).drawRect(0f, 0f, 96f, 96f, Paint().apply { shader = LinearGradient(0f, 0f, 96f, 96f, Color.HSVToColor(floatArrayOf(hue.toFloat(), 0.55f, 0.95f)), Color.HSVToColor(floatArrayOf(((hue + 50) % 360).toFloat(), 0.7f, 0.55f)), Shader.TileMode.CLAMP) })
        val out = ByteArrayOutputStream(); bmp.compress(Bitmap.CompressFormat.PNG, 100, out)
        return "data:image/png;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }

    override suspend fun summary() = MediaSummary("free", 2_000_000_000, 1_790_000_000, photos.size, false, listOf(YearCount(2025, 110), YearCount(2024, 40)),
        listOf(PlaceCount("Phuket", "Thailand", 25)), cols.toList())
    override suspend fun requestUploads(items: List<UploadRequestItem>) = UploadsResponse(items.mapIndexed { i, _ -> UploadSlotResult(i, SlotStatus.NoSpace, null, null, emptyMap(), null, null) }, 1_790_000_000, 2_000_000_000)
    override suspend fun items(limit: Int, cursor: String?, filter: MediaFilter): MediaPage {
        val all = photos.filter { filter.collection == null || filter.collection in it.collections }
        val start = cursor?.toIntOrNull() ?: 0
        val end = minOf(all.size, start + limit)
        return MediaPage(all.subList(start, end), if (end < all.size) end.toString() else null)
    }
    override suspend fun item(id: String) = photos.first { it.id == id }.copy(url = photos.first { it.id == id }.thumbUrl)
    override suspend fun delete(ids: List<String>): DeleteResult { photos.removeAll { it.id in ids }; return DeleteResult(ids.size, 1_700_000_000) }
    override suspend fun search(query: String, limit: Int, drop: List<String>, cursor: String?): SearchResult {
        val chips = listOf(SearchChip("place", "Thailand"), SearchChip("date", "2025")).filter { it.label !in drop }
        return SearchResult(Understood(null, "2025-01-01", "2025-12-31", listOf("Thailand"), chips), photos.filter { it.place?.contains("Thailand") == true }.take(limit), "timeline")
    }
    override suspend fun collections() = cols.toList()
    override suspend fun createCollection(name: String, emoji: String?) = MediaCollection("c${cols.size + 1}", name, emoji, 0, null).also { cols += it }
    override suspend fun updateCollection(id: String, name: String?, emoji: String?) = cols.first { it.id == id }.copy(name = name ?: cols.first { it.id == id }.name).also { n -> cols.replaceAll { if (it.id == id) n else it } }
    override suspend fun deleteCollection(id: String) { cols.removeAll { it.id == id } }
    override suspend fun editCollection(id: String, add: List<String>, remove: List<String>) {
        photos.replaceAll { p -> when { p.id in add -> p.copy(collections = (p.collections + id).distinct()); p.id in remove -> p.copy(collections = p.collections - id); else -> p } }
        cols.replaceAll { if (it.id == id) it.copy(count = photos.count { p -> id in p.collections }) else it }
    }
}
