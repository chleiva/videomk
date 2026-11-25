package com.videomk.app.core

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.YearMonth
import java.time.ZoneId
import java.time.format.TextStyle
import java.util.Locale

/** The storage meter: green below 85 %, amber from 85 %, red when full. */
object StorageMeter {
    enum class State { Ok, Warning, Full }

    const val WARNING_AT = 0.85

    fun fraction(used: Long, limit: Long): Double = if (limit <= 0) 0.0 else (used.toDouble() / limit).coerceIn(0.0, 1.0)

    fun state(used: Long, limit: Long): State = when {
        limit > 0 && used >= limit -> State.Full
        fraction(used, limit) >= WARNING_AT -> State.Warning
        else -> State.Ok
    }

    /** "1.2 GB", "640 MB", "12 KB" (decimal units, one decimal only when it helps). */
    fun format(bytes: Long): String {
        val b = maxOf(0L, bytes).toDouble()
        fun one(v: Double) = if (v >= 10 || v == Math.floor(v)) Math.round(v).toString() else String.format(Locale.US, "%.1f", v)
        return when {
            b >= 1e9 -> "${one(b / 1e9)} GB"
            b >= 1e6 -> "${one(b / 1e6)} MB"
            b >= 1e3 -> "${one(b / 1e3)} KB"
            else -> "${b.toLong()} B"
        }
    }

    fun label(used: Long, limit: Long) = "${format(used)} of ${format(limit)}"
}

class MediaSection(val key: String, val title: String, val items: List<MediaPhoto>)

/** Groups photos under month headers (day headers inside a month that has many), newest first, by capture day else the day it was added, in the person's time zone. */
object MediaGrouping {
    const val DAY_HEADERS_FROM = 30

    /** The local date a photo belongs to: the capture time as written (wall clock), else the added instant converted to [zone]. */
    fun dayOf(p: MediaPhoto, zone: ZoneId): LocalDate? =
        runCatching { LocalDateTime.parse(p.taken!!).toLocalDate() }.getOrNull()
            ?: runCatching { Instant.parse(p.added).atZone(zone).toLocalDate() }.getOrNull()

    private fun sortKey(p: MediaPhoto, zone: ZoneId): LocalDateTime =
        runCatching { LocalDateTime.parse(p.taken!!) }.getOrNull()
            ?: runCatching { Instant.parse(p.added).atZone(zone).toLocalDateTime() }.getOrNull() ?: LocalDateTime.MIN

    fun group(items: List<MediaPhoto>, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): List<MediaSection> {
        val sorted = items.sortedByDescending { sortKey(it, zone) }
        val byMonth = LinkedHashMap<YearMonth?, MutableList<MediaPhoto>>()
        for (p in sorted) byMonth.getOrPut(dayOf(p, zone)?.let { YearMonth.from(it) }) { mutableListOf() }.add(p)
        val out = ArrayList<MediaSection>()
        for ((month, photos) in byMonth) {
            if (month == null) { out += MediaSection("unknown", "Undated", photos); continue }
            val title = "${month.month.getDisplayName(TextStyle.FULL, locale)} ${month.year}"
            if (photos.size < DAY_HEADERS_FROM) { out += MediaSection(month.toString(), title, photos); continue }
            val byDay = LinkedHashMap<LocalDate, MutableList<MediaPhoto>>()
            for (p in photos) byDay.getOrPut(dayOf(p, zone)!!) { mutableListOf() }.add(p)
            for ((day, list) in byDay) {
                out += MediaSection(day.toString(), "${day.dayOfWeek.getDisplayName(TextStyle.SHORT, locale)} ${day.dayOfMonth} ${month.month.getDisplayName(TextStyle.FULL, locale)} ${month.year}", list)
            }
        }
        return out
    }
}

/** What a photo is called for TalkBack: its date and place. */
object MediaLabels {
    fun photo(p: MediaPhoto, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Locale.getDefault()): String {
        val day = MediaGrouping.dayOf(p, zone)
        val date = day?.let { "${it.dayOfMonth} ${it.month.getDisplayName(TextStyle.FULL, locale)} ${it.year}" }
        return listOfNotNull("Photo", date?.let { "from $it" }, p.place?.let { "in $it" }).joinToString(" ")
    }
}

/** Runs [onFire] with the last submitted query once [delayMs] passes without another one. A blank query fires at once (clearing a search is not a question). */
class SearchDebouncer(private val scope: CoroutineScope, private val delayMs: Long = 400, private val onFire: suspend (String) -> Unit) {
    private var job: Job? = null

    fun submit(query: String) {
        job?.cancel()
        job = scope.launch {
            if (query.isNotBlank()) delay(delayMs)
            onFire(query.trim())
        }
    }

    fun cancel() { job?.cancel() }
}

/** A search as the person sees it: the question and the chips they removed (each removal searches again with `drop`). */
data class SearchState(val query: String = "", val dropped: List<String> = emptyList()) {
    val active: Boolean get() = query.isNotBlank()
    fun drop(label: String) = copy(dropped = (dropped + label).distinct())
    fun withQuery(q: String) = SearchState(q, emptyList())   // a new question starts with nothing dropped
}

/** Does the video prompt itself describe photos from the library ("a video of my holidays in Thailand in 2024")? Offers "Photos from your prompt". */
object PromptSearch {
    private val OWN = Regex("""\b(my|our|mine)\b""", RegexOption.IGNORE_CASE)
    private val PHOTOISH = Regex("""\b(photos?|pictures?|pics?|images?|holidays?|vacations?|trips?|travels?|wedding|birthday|summer|winter|beach|family|kids?|children|baby|graduation|christmas)\b""", RegexOption.IGNORE_CASE)
    private val EXPLICIT = Regex("""\b(photos?|pictures?|pics?|images?)\s+(of|from|in|at|with)\b""", RegexOption.IGNORE_CASE)

    fun looksLikePhotoRequest(prompt: String): Boolean {
        val t = prompt.trim()
        if (t.length < 8) return false
        return EXPLICIT.containsMatchIn(t) || (OWN.containsMatchIn(t) && PHOTOISH.containsMatchIn(t))
    }
}
