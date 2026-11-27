package com.videomk.app.core

import com.videomk.app.R

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
    /** The meter is quiet until it matters: from half full on (the Storage sheet is always in the overflow menu). */
    const val SHOW_FROM = 0.5
    fun shouldShow(used: Long, limit: Long): Boolean = fraction(used, limit) >= SHOW_FROM

    fun fraction(used: Long, limit: Long): Double = if (limit <= 0) 0.0 else (used.toDouble() / limit).coerceIn(0.0, 1.0)

    fun state(used: Long, limit: Long): State = when {
        limit > 0 && used >= limit -> State.Full
        fraction(used, limit) >= WARNING_AT -> State.Warning
        else -> State.Ok
    }

    /** "1.2 GB", "640 MB", "12 KB" (decimal units, one decimal only when it helps). */
    fun format(bytes: Long): String {
        val b = maxOf(0L, bytes).toDouble()
        fun one(v: Double) = if (v >= 10 || v == Math.floor(v)) Math.round(v).toString() else String.format(Txt.locale, "%.1f", v)
        return when {
            b >= 1e9 -> "${one(b / 1e9)} GB"
            b >= 1e6 -> "${one(b / 1e6)} MB"
            b >= 1e3 -> "${one(b / 1e3)} KB"
            else -> "${b.toLong()} B"
        }
    }

    fun label(used: Long, limit: Long) = Txt.s(R.string.media_storage_of, format(used), format(limit))
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

    fun group(items: List<MediaPhoto>, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Txt.locale): List<MediaSection> {
        val sorted = items.sortedByDescending { sortKey(it, zone) }
        val byMonth = LinkedHashMap<YearMonth?, MutableList<MediaPhoto>>()
        for (p in sorted) byMonth.getOrPut(dayOf(p, zone)?.let { YearMonth.from(it) }) { mutableListOf() }.add(p)
        val out = ArrayList<MediaSection>()
        for ((month, photos) in byMonth) {
            if (month == null) { out += MediaSection("unknown", Txt.s(R.string.media_undated), photos); continue }
            val title = Txt.s(R.string.media_month_year, MediaDates.monthName(month.month, locale), month.year)
            if (photos.size < DAY_HEADERS_FROM) { out += MediaSection(month.toString(), title, photos); continue }
            val byDay = LinkedHashMap<LocalDate, MutableList<MediaPhoto>>()
            for (p in photos) byDay.getOrPut(dayOf(p, zone)!!) { mutableListOf() }.add(p)
            for ((day, list) in byDay) {
                out += MediaSection(day.toString(), Txt.s(R.string.media_day_header, day.dayOfWeek.getDisplayName(TextStyle.SHORT, locale).trimEnd('.'), day.dayOfMonth, month.month.getDisplayName(TextStyle.FULL, locale), month.year), list)
            }
        }
        return out
    }
}

object MediaDates {
    /** "March" / "marzo", capitalised for a header ("Marzo de 2025"). */
    fun monthName(m: java.time.Month, locale: Locale): String = m.getDisplayName(TextStyle.FULL, locale).replaceFirstChar { it.titlecase(locale) }

    /** "2 March 2025" / "2 de marzo de 2025" (a full date written with the locale's word order and joining words). */
    fun full(d: LocalDate, locale: Locale = Txt.locale): String = Txt.s(R.string.media_date_full, d.dayOfMonth, d.month.getDisplayName(TextStyle.FULL, locale), d.year)
}

/** What a photo is called for TalkBack: its date and place. */
object MediaLabels {
    fun photo(p: MediaPhoto, zone: ZoneId = ZoneId.systemDefault(), locale: Locale = Txt.locale): String {
        val date = MediaGrouping.dayOf(p, zone)?.let { MediaDates.full(it, locale) }
        return when {
            date != null && p.place != null -> Txt.s(R.string.media_photo_date_place, date, p.place)
            date != null -> Txt.s(R.string.media_photo_date, date)
            p.place != null -> Txt.s(R.string.media_photo_place, p.place)
            else -> Txt.s(R.string.media_photo)
        }
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
    // English and Spanish: the prompt may be written in either.
    // NEVER the (?U) flag here: Android's regex engine (ICU) rejects it with PatternSyntaxException, which crashed the app the moment the My media picker opened
    // (JVM unit tests accept it, so they could not see it). ICU's \b is already Unicode-aware, so accented words match without it.
    private val OWN = Regex("""\b(my|our|mine|mi|mis|nuestr[oa]s?)\b""", RegexOption.IGNORE_CASE)
    private val PHOTOISH = Regex("""\b(photos?|pictures?|pics?|images?|holidays?|vacations?|trips?|travels?|wedding|birthday|summer|winter|beach|family|kids?|children|baby|graduation|christmas|fotos?|imágenes|imagen|vacaciones|viajes?|boda|cumpleaños|verano|invierno|playa|familia|niños?|hijos?|bebé|graduación|navidad)\b""", RegexOption.IGNORE_CASE)
    private val EXPLICIT = Regex("""\b(photos?|pictures?|pics?|images?|fotos?|imágenes|imagen)\s+(of|from|in|at|with|de|del|en|con)\b""", RegexOption.IGNORE_CASE)

    fun looksLikePhotoRequest(prompt: String): Boolean {
        val t = prompt.trim()
        if (t.length < 8) return false
        return EXPLICIT.containsMatchIn(t) || (OWN.containsMatchIn(t) && PHOTOISH.containsMatchIn(t))
    }
}

/** How many photos the library should list once the uploads of this session are ready (the server needs a few seconds per photo). Duplicates are never counted. */
class ArrivalTracker {
    @Volatile var expected: Int? = null
        private set

    /** [added] photos reached the server; [listedNow] is how many the library lists right now (used as the baseline the first time). */
    fun expect(listedNow: Int, added: Int) { if (added > 0) expected = (expected ?: listedNow) + added }
    fun missing(listed: Int): Int = expected?.let { maxOf(0, it - listed) } ?: 0
    fun settle(listed: Int) { if (expected != null && listed >= expected!!) expected = null }
    fun clear() { expected = null }
    val pending: Boolean get() = expected != null
}

/**
 * ONE polling job that asks the server for the library until [tracker] is satisfied: every 2 s, every 4 s after 10 s, giving up after 90 s of waiting.
 * [start] cancels the running job and starts again (more uploads finished); [stop] ends it (the tab left the screen, or the person is searching).
 * [fetch] returns how many photos the library lists now, or null when the call failed (it is tried again).
 */
class ArrivalPoller(
    private val scope: CoroutineScope, private val tracker: ArrivalTracker, private val fetch: suspend () -> Int?,
    private val fastMs: Long = 2000, private val slowMs: Long = 4000, private val slowAfterMs: Long = 10_000, private val capMs: Long = 90_000,
) {
    private var job: Job? = null
    val running: Boolean get() = job?.isActive == true

    fun start() {
        job?.cancel()
        if (!tracker.pending) return
        job = scope.launch {
            var waited = 0L
            while (waited < capMs && tracker.pending) {
                val d = if (waited < slowAfterMs) fastMs else slowMs
                delay(d); waited += d
                val listed = fetch() ?: continue
                tracker.settle(listed)
            }
            if (tracker.pending) { tracker.clear(); fetch() }   // gave up: stop saying "getting ready"; the next refresh shows whatever has arrived
        }
    }

    fun stop() { job?.cancel(); job = null }
}

/** "Select all" for whatever is in view (All photos, a collection, a search result): pure, so the limit and the mixed sources are testable. */
object SelectAll {
    /** The note when the limit stopped it ("Selected the first 100: the limit for one video"). [limit]: how many My media photos may be selected (100 minus photos from the phone). */
    fun limitNote(limit: Int, total: Int = com.videomk.app.core.PhotoLimits.MAX_PHOTOS): String =
        if (limit >= total) Txt.s(R.string.media_select_limit, limit) else Txt.s(R.string.media_select_limit_phone, limit, total, total - limit)

    /** What to add: the in-view ids not yet selected, in view order, until the selection holds [limit]. */
    fun toAdd(view: List<String>, selected: Collection<String>, limit: Int): List<String> {
        val have = selected.toHashSet()
        var room = limit - have.size
        val out = ArrayList<String>()
        for (id in view) { if (room <= 0) break; if (have.add(id)) { out += id; room-- } }
        return out
    }

    /** Everything in view (as far as the limit allows) is selected: the control then reads "Clear". */
    fun allSelected(view: List<String>, selected: Collection<String>, limit: Int, moreToLoad: Boolean): Boolean {
        if (view.isEmpty()) return false
        val have = selected.toHashSet()
        if (have.size >= limit && view.any { it in have }) return true   // the limit is reached: nothing more can be added, so the control offers Clear
        if (view.all { it in have }) return !moreToLoad
        return false
    }

    /** "Select all 38", "Select all" when the count is not known (more pages), "Clear" when all is selected. */
    fun label(allSelected: Boolean, viewCount: Int?): String = if (allSelected) Txt.s(R.string.media_select_clear) else if (viewCount != null) Txt.s(R.string.media_select_all_count, viewCount) else Txt.s(R.string.media_select_all)

    /** The view holds this many photos: the loaded ones when there is no more, otherwise the known total (library or collection), otherwise unknown. */
    fun viewCount(loaded: Int, moreToLoad: Boolean, knownTotal: Int?): Int? = if (!moreToLoad) loaded else knownTotal?.takeIf { it >= loaded }
}
