package com.videomk.app.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/** When to ask, when to organise by itself, when to stay quiet (docs/UI_DESIGN.md section n.1). */
object OrganizePrompt {
    const val THRESHOLD = 30
    /** A job of fewer photos than this is one apply call: no progress bar. */
    const val SINGLE_CALL = 300

    enum class Decision { Nothing, ShowSheet, RunSilently, RunWithProgress }

    /** [readyPhotos] is `preview.total` for the batch, after the arrival wait. */
    fun decide(pref: OrganizePref, readyPhotos: Int): Decision = when (pref) {
        OrganizePref.Never -> Decision.Nothing
        OrganizePref.Ask -> if (readyPhotos >= THRESHOLD) Decision.ShowSheet else Decision.Nothing
        OrganizePref.Always -> if (readyPhotos <= 0) Decision.Nothing else if (readyPhotos < SINGLE_CALL) Decision.RunSilently else Decision.RunWithProgress
    }

    /** "since": the device UTC clock at the start of the upload batch, minus 60 seconds. */
    fun since(batchStartMillis: Long): String =
        DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss").withZone(ZoneOffset.UTC).format(Instant.ofEpochMilli(batchStartMillis - 60_000))

    fun title(p: OrganizePreview, wholeLibrary: Boolean): String {
        val n = "%,d".format(p.total)
        return if (p.groups.isNotEmpty() && p.groups.all { it.existing }) "Add $n ${if (p.total == 1) "photo" else "photos"} to your collections?"
        else if (wholeLibrary) "Organize $n photos?" else "Organize $n new photos?"
    }

    /** The sheet shows the top five groups; the rest is "+ N more collections". */
    fun visibleGroups(p: OrganizePreview, expanded: Boolean): List<OrganizeGroup> = if (expanded) p.groups else p.groups.take(5)
    fun moreCount(p: OrganizePreview): Int = maxOf(0, p.groups.size - 5)
    fun moreLabel(p: OrganizePreview): String = "+ ${moreCount(p)} more collection${if (moreCount(p) == 1) "" else "s"}"
    fun skippedLine(p: OrganizePreview): String? = p.skipped.takeIf { it > 0 }?.let { "${"%,d".format(it)} photo${if (it == 1) "" else "s"} had no clear group and stay${if (it == 1) "s" else ""} as they are." }

    /** The done toast: "Organized into 14 collections" / "...1 collection" / "Everything is already organized". */
    fun doneMessage(created: Int, updated: Int): String = when {
        created > 0 -> "Organized into $created collection${if (created == 1) "" else "s"}"
        updated > 0 -> "Added to $updated collection${if (updated == 1) "" else "s"}"
        else -> "Everything is already organized"
    }

    fun nameValid(name: String) = name.trim().isNotEmpty() && name.trim().length <= 60
}

/** Suggested names for "Put all in one collection", read from the preview's group names ("London · Apr 2026", "Phuket · 14-21 Jul 2024", "Jun 2025"). */
object OrganizeNames {
    private val DATE = Regex("""(?:\d{1,2}(?:-\d{1,2})?\s+)?([A-Z][a-z]{2})\s+(\d{4})""")
    private val MONTHS = listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

    private fun monthKey(m: String, y: Int): Int? = MONTHS.indexOf(m).takeIf { it >= 0 }?.let { y * 12 + it }
    private fun label(key: Int) = "${MONTHS[key % 12]} ${key / 12}"

    fun suggest(p: OrganizePreview): List<String> {
        val keys = p.groups.mapNotNull { g -> DATE.findAll(g.name).lastOrNull()?.let { m -> monthKey(m.groupValues[1], m.groupValues[2].toInt()) } }
        if (keys.isEmpty()) return emptyList()
        val lo = keys.min(); val hi = keys.max()
        val range = if (lo == hi) label(lo) else "${label(lo)} - ${label(hi)}"
        val byPlace = HashMap<String, Int>()
        for (g in p.groups) g.name.substringBefore(" · ", "").takeIf { it.isNotEmpty() && g.name.contains(" · ") }?.let { byPlace.merge(it, g.count, Int::plus) }
        val top = byPlace.maxByOrNull { it.value }
        val out = ArrayList<String>()
        if (top != null && p.total > 0 && top.value * 100 > p.total * 60) {
            val when_ = if (hi - lo <= 2) label(lo) else "${lo / 12}".let { if (lo / 12 == hi / 12) it else "${lo / 12}-${hi / 12}" }
            out += "${top.key} $when_"
        }
        out += range
        return out.distinct()
    }
}

/** The organise job as the person sees it. */
sealed interface OrganizeState {
    data object Idle : OrganizeState
    data class Running(val total: Int, val done: Int, val resumed: Boolean = false, val waitingForUpload: Boolean = false) : OrganizeState
    /** The network is gone: the job retries by itself. */
    data class Offline(val total: Int, val done: Int) : OrganizeState
    data class Failed(val total: Int, val done: Int, val message: String) : OrganizeState
    data class Done(val created: Int, val updated: Int) : OrganizeState
}

/** The persisted job: enough to call apply again after the app was killed (apply is safe to repeat). */
data class OrganizeJob(val single: Boolean, val since: String?, val name: String?, val collectionId: String?, val total: Int, val done: Int, val created: Int, val updated: Int) {
    fun toJson(): String = buildJsonObject {
        put("single", single); since?.let { put("since", it) }; name?.let { put("name", it) }; collectionId?.let { put("collection_id", it) }
        put("total", total); put("done", done); put("created", created); put("updated", updated)
    }.toString()

    companion object {
        fun fromJson(text: String): OrganizeJob? = runCatching {
            val o = parseObject(text)
            OrganizeJob(o.bool("single") ?: false, o.str("since"), o.str("name"), o.str("collection_id"), o.int("total") ?: 0, o.int("done") ?: 0, o.int("created") ?: 0, o.int("updated") ?: 0)
        }.getOrNull()
    }
}

interface JobStore { fun load(): String?; fun save(text: String?) }
class MemoryJobStore : JobStore { var text: String? = null; override fun load() = text; override fun save(text: String?) { this.text = text } }

/**
 * Calls apply until `remaining` is 0, with real progress from the cumulative answers. Cancel stops calling (nothing is rolled back). A lost network pauses the
 * job and it retries by itself; a server error fails it ("Try again" resumes where it stopped). The job is saved after every call.
 */
class OrganizeRunner(
    private val api: MediaApi, private val store: JobStore,
    private val retryDelayMs: Long = 5000, private val maxOfflineRetries: Int = Int.MAX_VALUE,
) {
    private val _state = MutableStateFlow<OrganizeState>(OrganizeState.Idle)
    val state: StateFlow<OrganizeState> = _state.asStateFlow()
    @Volatile private var cancelled = false
    @Volatile private var running = false

    val isActive: Boolean get() = _state.value.let { it is OrganizeState.Running || it is OrganizeState.Offline }

    /** A job left behind by a killed app (null when there is none). */
    fun pendingJob(): OrganizeJob? = store.load()?.let(OrganizeJob::fromJson)

    fun acknowledge() { if (_state.value is OrganizeState.Done || _state.value is OrganizeState.Failed) _state.value = OrganizeState.Idle }

    fun cancel() { cancelled = true; store.save(null); _state.value = OrganizeState.Idle }

    /** Starts a new job from a preview (total = photos to do). */
    suspend fun start(single: Boolean, total: Int, since: String?, name: String? = null) {
        run(OrganizeJob(single, since, name, null, total, 0, 0, 0), resumed = false)
    }

    /** Continues the saved job (after a restart or a failure). */
    suspend fun resume(job: OrganizeJob? = pendingJob()) { if (job != null) run(job, resumed = true) }

    private suspend fun run(initial: OrganizeJob, resumed: Boolean) {
        if (running) return
        running = true; cancelled = false
        var job = initial
        var offlineTries = 0
        try {
            store.save(job.toJson())
            _state.value = OrganizeState.Running(job.total, job.done, resumed)
            while (!cancelled) {
                val r = try {
                    api.organizeApply(job.single, job.since, job.name, job.collectionId)
                } catch (e: CancellationException) { throw e
                } catch (e: ApiError.Network) {
                    if (++offlineTries > maxOfflineRetries) { _state.value = OrganizeState.Failed(job.total, job.done, e.message); return }
                    _state.value = OrganizeState.Offline(job.total, job.done)
                    delay(retryDelayMs); continue
                } catch (e: ApiError) {
                    _state.value = OrganizeState.Failed(job.total, job.done, e.message); return
                } catch (e: Exception) {
                    _state.value = OrganizeState.Failed(job.total, job.done, ApiError.Server.message); return
                }
                offlineTries = 0
                val total = maxOf(job.total, job.done + r.applied + r.remaining)   // a cumulative total that never shrinks
                job = job.copy(
                    collectionId = r.collectionId ?: job.collectionId, total = total, done = total - r.remaining,
                    created = job.created + r.created, updated = job.updated + r.updated,
                )
                if (cancelled) return
                if (r.remaining <= 0) { store.save(null); _state.value = OrganizeState.Done(job.created, job.updated); return }
                if (r.applied == 0) { _state.value = OrganizeState.Failed(job.total, job.done, "Couldn't finish organizing."); return }   // no progress: do not spin
                store.save(job.toJson())
                _state.value = OrganizeState.Running(job.total, job.done)
            }
        } finally { running = false }
    }

    fun progressText(): String? = when (val s = _state.value) {
        is OrganizeState.Running -> "Organizing... ${"%,d".format(s.done)} of ${"%,d".format(s.total)}"
        is OrganizeState.Offline -> "Waiting for a connection"
        else -> null
    }
}
