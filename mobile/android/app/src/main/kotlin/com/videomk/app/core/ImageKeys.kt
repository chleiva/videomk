package com.videomk.app.core

/**
 * The server signs every picture link again on every list call (same path, new X-Amz-* query), so a link is never a good cache key.
 * The key is the link without its query: the same picture keeps the same key, a different video has a different path.
 */
object ImageKeys {
    fun stable(url: String): String = url.substringBefore('?').substringBefore('#')

    /** When a link was signed (X-Amz-Date, seconds since 1970 UTC), or null when it is not a signed link. */
    fun signedAtSeconds(url: String?): Long? {
        val d = url?.substringAfter('?', "")?.split('&')?.firstOrNull { it.startsWith("X-Amz-Date=") }?.substringAfter('=') ?: return null
        return runCatching { java.time.LocalDateTime.parse(d.removeSuffix("Z"), java.time.format.DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss")).toEpochSecond(java.time.ZoneOffset.UTC) }.getOrNull()
    }
}

object VideoMerge {
    /** Links are renewed after this long even when nothing else changed (they expire after an hour). */
    const val RENEW_SECONDS = 600L

    private fun same(a: VideoItem, b: VideoItem): Boolean =
        a.copy(videoUrl = null, previewGifUrl = null) == b.copy(videoUrl = null, previewGifUrl = null) &&
            keyOf(a.videoUrl) == keyOf(b.videoUrl) && keyOf(a.previewGifUrl) == keyOf(b.previewGifUrl)

    private fun keyOf(u: String?) = u?.let(ImageKeys::stable)

    private fun fresher(old: VideoItem, fresh: VideoItem): Boolean {
        val o = ImageKeys.signedAtSeconds(old.previewGifUrl ?: old.videoUrl) ?: return false
        val n = ImageKeys.signedAtSeconds(fresh.previewGifUrl ?: fresh.videoUrl) ?: return false
        return n - o >= RENEW_SECONDS
    }

    /** A refresh whose data did not change keeps the very same items (and the same list), so nothing redraws; only changed videos are replaced. */
    fun reuse(old: List<VideoItem>, fresh: List<VideoItem>): List<VideoItem> {
        val byId = old.associateBy { it.id }
        val merged = fresh.map { f -> byId[f.id]?.takeIf { same(it, f) && !fresher(it, f) } ?: f }
        return if (merged.size == old.size && merged.indices.all { merged[it] === old[it] }) old else merged
    }
}

/**
 * Whether the "New video" button shows its label. Only the distance from the top decides (never the scroll direction, never the bottom edge,
 * so a clamped or bouncing list cannot flip it back and forth), with a gap between collapsing and expanding so a few pixels of change do nothing.
 */
class FabCollapse(private val collapseAtPx: Int = 48, private val expandAtPx: Int = 8) {
    var expanded: Boolean = true
        private set

    /** [offsetPx]: how far the list is scrolled from its very top (any large number when the first item is out of sight). */
    fun update(offsetPx: Int): Boolean {
        if (expanded && offsetPx >= collapseAtPx) expanded = false
        else if (!expanded && offsetPx <= expandAtPx) expanded = true
        return expanded
    }
}
