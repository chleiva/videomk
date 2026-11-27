package com.videomk.app

import com.videomk.app.core.Brief
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.LibraryEntry
import com.videomk.app.core.LibraryMerge
import com.videomk.app.core.MakingSteps
import com.videomk.app.core.PendingVideo
import com.videomk.app.core.ProgressEstimator
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import com.videomk.app.core.VideoStatus.Stage
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LibraryTest {
    private fun video(id: String, status: VideoStatus = VideoStatus.Complete) = VideoItem(id, status)
    private fun pending(id: String, at: Long, state: PendingVideo.State = PendingVideo.State.Sending) =
        PendingVideo(id = id, brief = "brief $id", options = CreateOptions(), state = state, createdAtMillis = at)

    @Test fun `placeholders come first, newest first, then the server list in its own order`() {
        val entries = LibraryMerge.entries(listOf(pending("p1", 100), pending("p2", 200)), listOf(video("a"), video("b")))
        assertEquals(listOf("pending-p2", "pending-p1", "a", "b"), entries.map { it.id })
    }

    @Test fun `a placeholder is replaced in place once the server lists its video`() {
        val accepted = pending("p1", 100, PendingVideo.State.Accepted("v1"))
        assertEquals(listOf("pending-p1", "x"), LibraryMerge.entries(listOf(accepted), listOf(video("x"))).map { it.id })   // not listed yet: placeholder stays
        val merged = LibraryMerge.entries(listOf(accepted), listOf(video("v1", VideoStatus.Running(Stage.Starting)), video("x")))
        assertEquals(listOf("v1", "x"), merged.map { it.id })
        assertTrue(merged[0] is LibraryEntry.Video)
    }

    @Test fun `unsent and failed placeholders always stay`() {
        val list = listOf(pending("s", 1), pending("f", 2, PendingVideo.State.Failed("no")), pending("u", 3, PendingVideo.State.Uploading(1, 4)))
        assertEquals(3, LibraryMerge.entries(list, listOf(video("a"))).count { it is LibraryEntry.Pending })
        assertEquals(3, LibraryMerge.stillPending(list, listOf(video("a"))).size)
    }

    @Test fun `still pending forgets what the server has taken over`() {
        val list = listOf(pending("p1", 1, PendingVideo.State.Accepted("v1")), pending("p2", 2, PendingVideo.State.Accepted("v2")))
        assertEquals(listOf("p2"), LibraryMerge.stillPending(list, listOf(video("v1"))).map { it.id })
    }

    @Test fun `progress eases within a stage's slice and never reaches the next stage`() {
        for (stage in Stage.entries) {
            val (lo, hi) = ProgressEstimator.slice(stage)
            assertEquals(lo, ProgressEstimator.fraction(stage, 0.0), 1e-9)
            var last = -1.0
            for (s in listOf(0.0, 5.0, 20.0, 60.0, 200.0, 5_000.0, 1_000_000.0)) {
                val f = ProgressEstimator.fraction(stage, s)
                assertTrue("monotonic", f >= last); assertTrue("inside slice", f >= lo && f < hi)
                last = f
            }
        }
        // stages are ordered, so the bar never goes backwards when the server moves on
        val slices = Stage.entries.map { ProgressEstimator.slice(it) }
        for (i in 1 until slices.size) assertEquals(slices[i - 1].second, slices[i].first, 1e-9)
        assertTrue(ProgressEstimator.slice(Stage.Rendering).second < 1.0)
    }

    @Test fun `longer videos take longer, and negative time is clamped`() {
        assertTrue(ProgressEstimator.expectedSeconds(Stage.Rendering, 8.0) > ProgressEstimator.expectedSeconds(Stage.Rendering, 1.0))
        assertTrue(ProgressEstimator.fraction(Stage.Rendering, 60.0, 1.0) > ProgressEstimator.fraction(Stage.Rendering, 60.0, 12.0))
        assertEquals(ProgressEstimator.fraction(Stage.Writing, 0.0), ProgressEstimator.fraction(Stage.Writing, -5.0), 1e-9)
    }

    @Test fun `credits are one per started minute, between 1 and 12`() {
        assertEquals(1, CreateOptions(0.5).credits); assertEquals(1, CreateOptions(1.0).credits); assertEquals(2, CreateOptions(1.2).credits)
        assertEquals(3, CreateOptions(3.0).credits); assertEquals(12, CreateOptions(12.0).credits); assertEquals(12, CreateOptions(30.0).credits)
    }

    @Test fun `brief validation mirrors the server`() {
        assertFalse(Brief.isValid("too short")); assertTrue(Brief.isValid("Why is the sky blue?"))
        assertFalse(Brief.isValid("   a    b    c   ")); assertEquals("a b c", Brief.normalized("  a \n b\t c "))
        assertTrue(Brief.isValid("x".repeat(2000))); assertFalse(Brief.isValid("x".repeat(2001)))
    }

    @Test fun `status mapping covers the server's statuses`() {
        assertEquals(VideoStatus.Complete, VideoStatus.fromServer("preview_ready"))
        assertEquals(VideoStatus.Cancelled, VideoStatus.fromServer("CANCELLED")); assertEquals(VideoStatus.Failed, VideoStatus.fromServer("EDIT_FAILED"))
        assertEquals(VideoStatus.Running(Stage.VoiceAndVisuals), VideoStatus.fromServer("STORYBOARD_CREATION"))
        assertEquals(VideoStatus.Running(Stage.Starting), VideoStatus.fromServer(""))
        assertTrue(VideoStatus.fromServer("RENDERING").isRunning); assertFalse(VideoStatus.Complete.isRunning)
    }

    @Test fun `making steps fill from the overall estimate and the card says what is left`() {
        assertEquals(listOf(0f, 0f, 0f, 0f), MakingSteps.fills(0.0)); assertEquals(listOf(1f, 1f, 1f, 1f), MakingSteps.fills(1.0))
        assertEquals(listOf(1f, 0.5f, 0f, 0f), MakingSteps.fills(0.32).map { Math.round(it * 100) / 100f })
        assertEquals(2, MakingSteps.current(0.5)); assertEquals(3, MakingSteps.current(1.0)); assertEquals(0, MakingSteps.current(0.0))
        assertEquals("Finding the story", MakingSteps.sentence(VideoStatus.Stage.Writing))
        assertEquals("Less than a minute left.", ProgressEstimator.leftText(VideoStatus.Stage.Rendering, 500.0, 1.0))
        assertTrue(ProgressEstimator.leftText(VideoStatus.Stage.Starting, 0.0, 3.0).startsWith("About "))
        assertTrue(ProgressEstimator.secondsLeft(VideoStatus.Stage.Starting, 0.0) > ProgressEstimator.secondsLeft(VideoStatus.Stage.Rendering, 0.0))
    }
}
