package com.videomk.app.core

import java.time.Instant
import java.time.ZoneId

enum class DayBucket { Today, Yesterday, Earlier }

/** One line of the home list: a day header or an entry. Videos being made (and requests on their way) stay on top with no header. */
sealed interface LibraryRow {
    val key: String
    data class Header(val bucket: DayBucket) : LibraryRow { override val key get() = "header-$bucket" }
    data class Item(val entry: LibraryEntry) : LibraryRow { override val key get() = entry.id }
}

object DayGroups {
    fun bucket(created: Instant?, now: Instant, zone: ZoneId): DayBucket {
        if (created == null) return DayBucket.Earlier
        val today = now.atZone(zone).toLocalDate()
        val day = created.atZone(zone).toLocalDate()
        return when {
            !day.isBefore(today) -> DayBucket.Today
            day == today.minusDays(1) -> DayBucket.Yesterday
            else -> DayBucket.Earlier
        }
    }

    private fun isLive(e: LibraryEntry) = e is LibraryEntry.Pending || (e is LibraryEntry.Video && e.video.status.isRunning)

    /**
     * Videos being made (and requests on their way) first, with no header, in their own order; then the finished and failed videos in the order given
     * (newest first from the server) with a header whenever the day bucket changes.
     */
    fun rows(entries: List<LibraryEntry>, now: Instant, zone: ZoneId): List<LibraryRow> {
        val out = ArrayList<LibraryRow>()
        entries.filter { isLive(it) }.forEach { out += LibraryRow.Item(it) }
        var last: DayBucket? = null
        for (e in entries) {
            if (isLive(e)) continue
            val b = bucket((e as LibraryEntry.Video).video.createdAt, now, zone)
            if (b != last) { out += LibraryRow.Header(b); last = b }
            out += LibraryRow.Item(e)
        }
        return out
    }
}
