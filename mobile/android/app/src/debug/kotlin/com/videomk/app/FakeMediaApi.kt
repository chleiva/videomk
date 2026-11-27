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
class FakeMediaApi(private val full: Boolean = false, private val dupes: Boolean = false) : MediaApi {
    private val places = listOf("Phuket, Thailand", "Lisbon, Portugal", "Kyoto, Japan", null, "Cape Town, South Africa", null)
    private val photos = MutableList(150) { i ->
        val t = LocalDateTime.of(2025, 9, 28, 14, 0).minusDays(i * 2L).minusHours(i % 5L)
        MediaPhoto("p$i", if (i % 11 == 7) null else t.toString().take(19).let { if (it.length == 16) "$it:00" else it }, t.plusDays(1).toString().take(16) + ":00Z",
            places[i % places.size], 1536, 2048, 900_000L + i * 4000, thumb(i), if (i % 9 == 0) listOf("c1") else emptyList())
    }
    private val cols = mutableListOf(MediaCollection("c1", "Family", "👪", photos.count { "c1" in it.collections }, "p0"), MediaCollection("c2", "Thailand", "🏝️", 0, null),
        MediaCollection("x1", "London · May 2026", null, 71, "p9", thumb(9), auto = true), MediaCollection("x2", "Phuket · 14-21 Jul 2024", null, 188, "p12", thumb(12), auto = true))

    private fun thumb(i: Int): String {
        val bmp = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
        val hue = (i * 37) % 360
        Canvas(bmp).drawRect(0f, 0f, 96f, 96f, Paint().apply { shader = LinearGradient(0f, 0f, 96f, 96f, Color.HSVToColor(floatArrayOf(hue.toFloat(), 0.55f, 0.95f)), Color.HSVToColor(floatArrayOf(((hue + 50) % 360).toFloat(), 0.7f, 0.55f)), Shader.TileMode.CLAMP) })
        val out = ByteArrayOutputStream(); bmp.compress(Bitmap.CompressFormat.PNG, 100, out)
        return "data:image/png;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP)
    }

    override suspend fun summary() = MediaSummary("free", 2_000_000_000, if (full) 2_000_000_000 else 1_790_000_000, photos.size, false, listOf(YearCount(2025, 110), YearCount(2024, 40)),
        listOf(PlaceCount("Phuket", "Thailand", 25)), cols.toList(), organizePref = organizePref)
    override suspend fun requestUploads(items: List<UploadRequestItem>) = UploadsResponse(items.mapIndexed { i, _ ->
        if (full) return@mapIndexed UploadSlotResult(i, if (i < 3) SlotStatus.Upload else SlotStatus.NoSpace, if (i < 3) "new$i" else null, "https://fake.invalid/up", mapOf("key" to "ok$i"), null, null)
        when (i % 6) {
            2 -> UploadSlotResult(i, SlotStatus.Duplicate, null, null, emptyMap(), "p0", null)
            4 -> UploadSlotResult(i, SlotStatus.Upload, "new$i", "https://fake.invalid/up", mapOf("key" to "fail"), null, null)
            else -> UploadSlotResult(i, SlotStatus.Upload, "new$i", "https://fake.invalid/up", mapOf("key" to "ok$i"), null, null)
        }
    }, 1_790_000_000, 2_000_000_000)
    override suspend fun items(limit: Int, cursor: String?, filter: MediaFilter): MediaPage {
        val all = photos.filter { filter.collection == null || filter.collection in it.collections }
        val start = cursor?.toIntOrNull() ?: 0
        val end = minOf(all.size, start + limit)
        // `files/fake_dupes`: every page repeats some ids and photos share a timestamp (what a server hiccup can send), to prove the grids survive it
        val page = all.subList(start, end).let { p -> if (dupes) p + p.take(5) + p.takeLast(3).map { it.copy(taken = p.first().taken) } else p }
        return MediaPage(page, if (end < all.size) end.toString() else null)
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

    // smart collections: 842 photos, 14 groups, about 300 photos a call, two seconds each so the progress can be looked at
    private var organizeRemaining = -1
    private val groupNames = listOf("London · Apr 2026" to 214, "Phuket · 14-21 Jul 2024" to 188, "Lisbon · 3-6 Oct 2025" to 96, "London · May 2026" to 71, "Jun 2025" to 52) +
        (1..9).map { "Group $it · Aug 2025" to 20 }
    override suspend fun organizePreview(since: String?): OrganizePreview = OrganizePreview(
        842, 0, 37, "London",
        groupNames.mapIndexed { i, (n, c) -> OrganizeGroup(n, c, i == 0 || i == 3, listOf("p${i * 3}", "p${i * 3 + 1}", "p${i * 3 + 2}")) },
    )
    override suspend fun organizeApply(single: Boolean, since: String?, name: String?, collectionId: String?): OrganizeApplyResult {
        kotlinx.coroutines.delay(2500)
        if (organizeRemaining < 0) organizeRemaining = 842
        val n = minOf(300, organizeRemaining); organizeRemaining -= n
        if (organizeRemaining == 0) {
            organizeRemaining = -1
            if (single) cols.add(0, MediaCollection("s1", name ?: "All", null, 842, "p0", photos[0].thumbUrl, auto = false))
            else for ((i, g) in groupNames.take(3).withIndex()) cols.add(0, MediaCollection("a$i", g.first, null, g.second, "p${i * 3}", photos[i * 3].thumbUrl, auto = true))
        }
        return OrganizeApplyResult(n, organizeRemaining.coerceAtLeast(0), if (organizeRemaining <= 0) 14 else 0, 0, 0, if (single) "s1" else null)
    }
    override suspend fun setOrganizePref(pref: OrganizePref) { organizePref = pref }
    var organizePref = OrganizePref.Ask
}
