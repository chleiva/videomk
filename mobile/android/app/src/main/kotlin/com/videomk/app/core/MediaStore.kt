package com.videomk.app.core

/** Where the cached item pages live (a file in the app; a map in tests). Keys are fixed names, never URLs. */
interface PageDisk {
    fun read(key: String): String?
    fun write(key: String, text: String)
    fun clear()
}

class MemoryPageDisk : PageDisk {
    val map = HashMap<String, String>()
    override fun read(key: String) = map[key]
    override fun write(key: String, text: String) { map[key] = text }
    override fun clear() = map.clear()
}

/**
 * The cached timeline: photos by id (so a photo is stored once however many lists show it), the order of the list, the opaque cursor, and when the
 * links were fetched. Links expire after an hour but the image never changes, so images are cached by photo id (see the UI loader) and only the links
 * are refreshed: [linksStale] says when, [refreshLinks] swaps in fresh links without touching order or selection.
 */
class MediaListing(private val clock: () -> Long = System::currentTimeMillis) {
    private val byId = LinkedHashMap<String, MediaPhoto>()
    private var order: List<String> = emptyList()
    var cursor: String? = null
        private set
    var fetchedAt: Long = 0L
        private set

    val items: List<MediaPhoto> get() = order.mapNotNull { byId[it] }
    val hasMore: Boolean get() = cursor != null
    fun get(id: String): MediaPhoto? = byId[id]

    fun replace(page: MediaPage) {
        byId.clear(); page.items.forEach { byId[it.id] = it }
        order = page.items.map { it.id }; cursor = page.cursor; fetchedAt = clock()
    }

    /** Adds the next page (an item that is already listed keeps its place and gets the fresher data). */
    fun append(page: MediaPage) {
        val known = order.toHashSet()
        page.items.forEach { byId[it.id] = it }
        order = order + page.items.map { it.id }.filter { it !in known }
        cursor = page.cursor; fetchedAt = clock()
    }

    fun remove(ids: Collection<String>) { val s = ids.toSet(); s.forEach { byId.remove(it) }; order = order.filter { it !in s } }

    fun update(p: MediaPhoto) { if (p.id in byId) byId[p.id] = p }

    fun linksStale(): Boolean = clock() - fetchedAt > LINK_LIFETIME_MS

    /** Fresh thumb links by id; photos not in the fresh page keep their old data. */
    fun refreshLinks(fresh: List<MediaPhoto>) {
        for (f in fresh) byId[f.id]?.let { byId[f.id] = it.copy(thumbUrl = f.thumbUrl ?: it.thumbUrl) }
        fetchedAt = clock()
    }

    companion object { const val LINK_LIFETIME_MS = 50L * 60_000L }   // links last an hour; refresh a little before
}

/** Disk copy of the first page and the summary, so the Media tab shows something offline. */
class MediaCache(private val disk: PageDisk) {
    fun savePage(name: String, page: MediaPage) {
        runCatching { disk.write(name, kotlinx.serialization.json.JsonObject(mapOf(
            "items" to kotlinx.serialization.json.JsonArray(page.items.map { photoJson(it) }),
        )).toString()) }
    }

    fun loadPage(name: String): MediaPage? = runCatching {
        disk.read(name)?.let { MediaPage(MediaPage.fromJson(parseObject(it)).items, null) }
    }.getOrNull()

    private fun photoJson(p: MediaPhoto) = kotlinx.serialization.json.buildJsonObject {
        put("id", kotlinx.serialization.json.JsonPrimitive(p.id)); p.taken?.let { put("taken", kotlinx.serialization.json.JsonPrimitive(it)) }
        put("added", kotlinx.serialization.json.JsonPrimitive(p.added)); p.place?.let { put("place", kotlinx.serialization.json.JsonPrimitive(it)) }
        put("w", kotlinx.serialization.json.JsonPrimitive(p.w)); put("h", kotlinx.serialization.json.JsonPrimitive(p.h)); put("bytes", kotlinx.serialization.json.JsonPrimitive(p.bytes))
        // links are not stored: they expire; the image itself is cached by photo id
        put("collections", kotlinx.serialization.json.JsonArray(p.collections.map { kotlinx.serialization.json.JsonPrimitive(it) }))
    }

    fun clear() = disk.clear()
}
