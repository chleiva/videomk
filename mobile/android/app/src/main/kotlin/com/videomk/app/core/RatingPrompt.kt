package com.videomk.app.core

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.BitSet

/*
 * The rating prompt (docs/FEEDBACK.md, "Rating prompt (Android)"). Everything here is pure: the clock and the storage are injected.
 */

/**
 * Decides whether one playback session was a real watch of the whole video.
 *
 * Rule (documented in docs/FEEDBACK.md): the video counts as fully watched when
 *  1. the seconds that were actually PLAYED forward (continuous playback, no seek in between) cover at least [COVERAGE] (90%) of the duration, and
 *  2. the position reached is within [END_SLACK_MS] (1 s) of the end (or the player reported the end of the media).
 * A seek (the scrubber, a tap on the bar) breaks the continuity: the time jumped over is not counted, so dragging to the end never completes a
 * video. A forward step larger than [MAX_STEP_MS] between two samples is treated as a jump, for the same reason. Pausing, replaying and rewinding
 * are fine: coverage is the set of distinct seconds played, so watching the first half twice does not make up for a skipped second half.
 * Feed it a sample every ~500 ms ([sample]) and every seek ([seek]); read [completed].
 */
class WatchTracker(private val durationMs: Long) {
    private val covered = BitSet()
    private var last = -1L
    private var reachedEnd = false

    /** The playback position after a seek or a discontinuity: nothing between the old and new position is credited. */
    fun seek(positionMs: Long) { last = positionMs }

    /** One look at the player. [playing] is `isPlaying` (not buffering, not paused). */
    fun sample(positionMs: Long, playing: Boolean) {
        if (durationMs <= 0) return
        if (playing && last >= 0 && positionMs > last && positionMs - last <= MAX_STEP_MS) {
            for (sec in (last / 1000)..(positionMs / 1000)) covered.set(sec.toInt())
        } else if (playing && last < 0) covered.set((positionMs / 1000).toInt())
        last = positionMs
        if (playing && positionMs >= durationMs - END_SLACK_MS) reachedEnd = true
    }

    /** The player says playback ended (STATE_ENDED) after playing up to the end; counts as the position being at the end. */
    fun ended() {
        if (durationMs <= 0) return
        if (last >= 0 && durationMs - last <= MAX_STEP_MS) { for (sec in (last / 1000)..(durationMs / 1000)) covered.set(sec.toInt()); reachedEnd = true }
        last = durationMs
    }

    val completed: Boolean get() {
        if (durationMs <= 0 || !reachedEnd) return false
        val buckets = ((durationMs + 999) / 1000).toInt()
        // the last partial second is within the slack and counts as played once the end was reached
        return covered.get(0, buckets).cardinality() >= Math.ceil(buckets * COVERAGE).toInt()
    }

    companion object {
        const val COVERAGE = 0.9
        const val END_SLACK_MS = 1000L
        const val MAX_STEP_MS = 2000L
    }
}

/** What is stored between launches. [completedIds] is the bounded set (most recent last) that keeps one video from counting twice. */
data class RatingState(
    val completedIds: List<String> = emptyList(),
    val completedCount: Int = 0,
    val askedCount: Int = 0,
    /** [completedCount] at the moment of the last ask: the next ask needs [RatingPrompt.GAP] more videos than that. */
    val askedAtCount: Int = 0,
    val lastAskedAt: Long = 0,
    val done: Boolean = false,
) {
    fun encode(): String = buildJsonObject {
        put("ids", JsonArray(completedIds.map { JsonPrimitive(it) }))
        put("count", completedCount); put("asked", askedCount); put("askedAt", askedAtCount); put("lastAskedAt", lastAskedAt); put("done", done)
    }.toString()

    companion object {
        /** Anything unreadable gives the empty state (the prompt then simply starts counting again). */
        fun decode(text: String?): RatingState {
            if (text.isNullOrBlank()) return RatingState()
            return try {
                val o = parseObject(text)
                RatingState(
                    completedIds = o.arr("ids")?.mapNotNull { (it as? JsonPrimitive)?.takeIf { p -> p.isString }?.content } ?: emptyList(),
                    completedCount = (o.int("count") ?: 0).coerceAtLeast(0), askedCount = (o.int("asked") ?: 0).coerceAtLeast(0),
                    askedAtCount = (o.int("askedAt") ?: 0).coerceAtLeast(0), lastAskedAt = (o.num("lastAskedAt") ?: 0.0).toLong(), done = o.bool("done") ?: false,
                )
            } catch (e: Exception) { RatingState() }
        }
    }
}

interface RatingStorage {
    fun load(): RatingState
    fun save(state: RatingState)
}

/** What the screen knows at the moment it considers showing the prompt. */
data class RatingContext(
    /** A video is playing (inline or full screen). */
    val videoPlaying: Boolean = false,
    /** A video is being created or sent right now, or the Create screen is open. */
    val creating: Boolean = false,
    /** Instrumented or screenshot runs: never. */
    val suppressed: Boolean = false,
)

/**
 * The state machine. Start: [RatingState.completedCount] = 0, asked 0, not done.
 *
 *  - [recordCompletion] (a video was fully watched, see [WatchTracker]): a video id counts once, ever (bounded memory of [MAX_IDS] ids; the
 *    count itself is unbounded). Nothing is counted once [RatingState.done] is set.
 *  - Eligible when not done, askedCount < [MAX_ASKS] and completedCount >= [FIRST_AT] (11: ten earlier complete views plus this one) for the
 *    first ask, or >= askedAtCount + [GAP] (10 more completed videos) for the next ones: normally the 21st and the 31st.
 *  - [shouldShow]: eligible, and not while a video plays, not while creating, not within [LAUNCH_QUIET_MS] (2 minutes) of launch, not when suppressed.
 *    [debugForce] (debug builds only, set by the caller) skips every condition except the played video.
 *  - [onShown]: the pre-prompt appeared. It uses one of the 3 asks at once (askedCount + 1, askedAtCount = completedCount, lastAskedAt = now), so
 *    any way of leaving it (swipe, back, tap outside, "Maybe later", "Not really" or a tap on "Rate VideoMK" the store may ignore) means "ask again
 *    after 10 more completed videos", until the 3 asks are used.
 *  - [onAlreadyRated]: done = true, never again. The only way to end it early. ("Not really" goes to the feedback sheet, it does not end it.)
 */
class RatingPrompt(private val storage: RatingStorage, private val clock: () -> Long, private val launchedAt: Long = clock()) {
    private var state: RatingState = storage.load()
    val snapshot: RatingState get() = state

    @Synchronized fun recordCompletion(videoId: String): Boolean {
        if (state.done || videoId in state.completedIds) return false
        state = state.copy(completedIds = (state.completedIds + videoId).takeLast(MAX_IDS), completedCount = state.completedCount + 1).also(storage::save)
        return true
    }

    val eligible: Boolean get() = !state.done && state.askedCount < MAX_ASKS &&
        state.completedCount >= (if (state.askedCount == 0) FIRST_AT else state.askedAtCount + GAP)

    fun shouldShow(ctx: RatingContext = RatingContext(), debugForce: Boolean = false): Boolean {
        if (ctx.videoPlaying) return false
        if (debugForce) return true
        if (ctx.creating || ctx.suppressed || !eligible) return false
        return clock() - launchedAt >= LAUNCH_QUIET_MS
    }

    @Synchronized fun onShown() {
        state = state.copy(askedCount = state.askedCount + 1, askedAtCount = state.completedCount, lastAskedAt = clock()).also(storage::save)
    }

    @Synchronized fun onAlreadyRated() { state = state.copy(done = true).also(storage::save) }

    companion object {
        const val FIRST_AT = 11
        const val GAP = 10
        const val MAX_ASKS = 3
        const val MAX_IDS = 200
        const val LAUNCH_QUIET_MS = 2 * 60 * 1000L
    }
}
