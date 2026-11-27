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

/** One row of the Videos screen (docs/DESIGN_BAR_2026.md, `phone_2_videos`): what is being made, then the newest video large, then the rest two by two. */
sealed interface FeedRow {
    val key: String
    /** A request on its way or a video being made: the Making card. */
    data class Live(val entry: LibraryEntry) : FeedRow { override val key get() = entry.id }
    /** The newest finished video, as a large poster. */
    data class Hero(val video: VideoItem) : FeedRow { override val key get() = video.id }
    /** Two finished videos side by side ([right] is null for an odd one out). */
    data class Pair(val left: VideoItem, val right: VideoItem?) : FeedRow { override val key get() = "pair-" + left.id }
    /** A video that did not finish or was not allowed: one card with what happened and the way out. */
    data class Problem(val video: VideoItem) : FeedRow { override val key get() = video.id }
}

object FeedLayout {
    private const val RECENT_SECONDS = 24 * 3600L

    /**
     * Making cards first; then anything that failed in the last day (it wants an answer: try again or remove); then the newest finished video large and the others
     * in pairs, newest first as the server lists them; older failures last. Every entry appears exactly once.
     */
    fun rows(entries: List<LibraryEntry>, now: Instant): List<FeedRow> {
        val out = ArrayList<FeedRow>()
        val videos = entries.filterIsInstance<LibraryEntry.Video>().map { it.video }
        entries.filter { it is LibraryEntry.Pending || (it is LibraryEntry.Video && it.video.status.isRunning) }.forEach { out += FeedRow.Live(it) }
        val problems = videos.filter { !it.status.isRunning && it.status != VideoStatus.Complete }
        val (recent, old) = problems.partition { v -> v.createdAt?.let { now.epochSecond - it.epochSecond < RECENT_SECONDS } ?: false }
        recent.forEach { out += FeedRow.Problem(it) }
        val ready = videos.filter { it.status == VideoStatus.Complete }
        ready.firstOrNull()?.let { out += FeedRow.Hero(it) }
        ready.drop(1).chunked(2).forEach { out += FeedRow.Pair(it[0], it.getOrNull(1)) }
        old.forEach { out += FeedRow.Problem(it) }
        return out
    }
}
