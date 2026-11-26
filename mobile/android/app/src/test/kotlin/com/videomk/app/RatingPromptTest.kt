package com.videomk.app

import com.videomk.app.core.RatingContext
import com.videomk.app.core.RatingPrompt
import com.videomk.app.core.RatingState
import com.videomk.app.core.RatingStorage
import com.videomk.app.core.WatchTracker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RatingPromptTest {
    private class Mem(var state: RatingState = RatingState()) : RatingStorage {
        override fun load() = RatingState.decode(state.encode())   // through the real encoding, like a restart
        override fun save(state: RatingState) { this.state = state }
    }
    private var now = 0L
    private val calm = RatingContext()
    private fun prompt(mem: Mem = Mem()) = RatingPrompt(mem, { now }, launchedAt = 0L).also { now = 10 * 60_000L }
    private fun RatingPrompt.watch(n: Int, from: Int = 1) { for (i in from until from + n) recordCompletion("v$i") }

    @Test fun `not eligible before the 11th distinct complete video, eligible on it`() {
        val p = prompt(); p.watch(10)
        assertFalse(p.eligible); assertFalse(p.shouldShow(calm))
        p.recordCompletion("v11")
        assertTrue(p.eligible); assertTrue(p.shouldShow(calm))
    }

    @Test fun `the same video is never counted twice`() {
        val p = prompt(); repeat(30) { p.recordCompletion("same") }
        assertEquals(1, p.snapshot.completedCount); assertFalse(p.eligible)
    }

    @Test fun `closing the first ask means ask again at the 21st, then the 31st, at most three asks`() {
        val p = prompt(); p.watch(11); p.onShown()
        assertFalse(p.eligible)
        p.watch(9, 12); assertFalse(p.eligible)          // 20 videos
        p.recordCompletion("v21"); assertTrue(p.eligible); p.onShown()
        p.watch(9, 22); assertFalse(p.eligible)          // 30
        p.recordCompletion("v31"); assertTrue(p.eligible); p.onShown()
        p.watch(50, 32); assertFalse(p.eligible); assertFalse(p.shouldShow(calm))
        assertEquals(3, p.snapshot.askedCount)
    }

    @Test fun `a prompt delayed past the 11th still waits ten more videos after it was shown`() {
        val p = prompt(); p.watch(14); p.onShown()
        p.watch(9, 15); assertFalse(p.eligible)          // 23
        p.recordCompletion("v24"); assertTrue(p.eligible)
    }

    @Test fun `already rated ends it forever`() {
        val p = prompt(); p.watch(11); p.onShown(); p.onAlreadyRated()
        p.watch(100, 12)
        assertFalse(p.eligible); assertFalse(p.shouldShow(calm)); assertTrue(p.snapshot.done)
        assertEquals(11, p.snapshot.completedCount)      // nothing is counted any more
    }

    @Test fun `never while playing or creating, never when suppressed, never in the first two minutes`() {
        val mem = Mem(); val p = RatingPrompt(mem, { now }, launchedAt = 0L); p.watch(11)
        now = 119_999; assertFalse(p.shouldShow(calm))
        now = 120_000; assertTrue(p.shouldShow(calm))
        assertFalse(p.shouldShow(RatingContext(videoPlaying = true)))
        assertFalse(p.shouldShow(RatingContext(creating = true)))
        assertFalse(p.shouldShow(RatingContext(suppressed = true)))
    }

    @Test fun `debug override ignores the counters but still never shows during playback`() {
        val p = prompt()
        assertTrue(p.shouldShow(calm, debugForce = true))
        assertFalse(p.shouldShow(RatingContext(videoPlaying = true), debugForce = true))
    }

    @Test fun `state survives a restart`() {
        val mem = Mem(); val a = prompt(mem); a.watch(11); a.onShown(); a.watch(3, 12)
        val b = RatingPrompt(mem, { now }, 0L)
        assertEquals(a.snapshot, b.snapshot)
        assertEquals(1, b.snapshot.askedCount); assertEquals(14, b.snapshot.completedCount)
        b.recordCompletion("v1"); assertEquals(14, b.snapshot.completedCount)   // ids are remembered too
        val c = prompt(Mem(RatingState(done = true))); assertFalse(c.eligible)
    }

    @Test fun `unreadable stored state starts fresh`() {
        assertEquals(RatingState(), RatingState.decode("not json")); assertEquals(RatingState(), RatingState.decode(null))
    }

    @Test fun `the remembered ids are bounded but the count is not`() {
        val p = prompt(); p.watch(RatingPrompt.MAX_IDS + 50)
        assertEquals(RatingPrompt.MAX_IDS, p.snapshot.completedIds.size); assertEquals(RatingPrompt.MAX_IDS + 50, p.snapshot.completedCount)
    }

    // ---- WatchTracker ----

    private fun WatchTracker.play(fromMs: Long, toMs: Long, step: Long = 500) { var t = fromMs; while (t <= toMs) { sample(t, true); t += step }; sample(toMs, true) }

    @Test fun `playing from start to end counts`() {
        val t = WatchTracker(20_000); t.seek(0); t.play(0, 20_000); t.ended()
        assertTrue(t.completed)
    }

    @Test fun `scrubbing to the end does not count`() {
        val t = WatchTracker(60_000); t.seek(0); t.play(0, 3_000)
        t.seek(59_800); t.sample(59_800, true); t.play(59_800, 60_000); t.ended()
        assertFalse(t.completed)
    }

    @Test fun `skipping the middle does not count but small skips of under ten percent do`() {
        val skip = WatchTracker(100_000); skip.seek(0); skip.play(0, 30_000); skip.seek(60_000); skip.play(60_000, 100_000); skip.ended()
        assertFalse(skip.completed)
        val small = WatchTracker(100_000); small.seek(0); small.play(0, 40_000); small.seek(45_000); small.play(45_000, 100_000); small.ended()
        assertTrue(small.completed)
    }

    @Test fun `stopping short of the end does not count even at 95 percent`() {
        val t = WatchTracker(100_000); t.seek(0); t.play(0, 95_000)
        assertFalse(t.completed)
    }

    @Test fun `watching the first half twice does not make up for a skipped second half`() {
        val t = WatchTracker(40_000); t.seek(0); t.play(0, 20_000); t.seek(0); t.play(0, 20_000); t.seek(39_500); t.play(39_500, 40_000); t.ended()
        assertFalse(t.completed)
    }

    @Test fun `pausing does not matter and a paused position is not credited`() {
        val t = WatchTracker(10_000); t.seek(0); t.play(0, 4_000)
        repeat(20) { t.sample(4_000, false) }
        t.play(4_000, 10_000); t.ended()
        assertTrue(t.completed)
    }

    @Test fun `unknown duration never completes`() { val t = WatchTracker(0); t.play(0, 5_000); t.ended(); assertFalse(t.completed) }
}
