package com.videomk.app

import com.videomk.app.core.BetterFailure
import com.videomk.app.core.DictationFeedback
import com.videomk.app.core.DictationFeedback.Warning
import com.videomk.app.core.LevelMeter
import com.videomk.app.core.VoiceEvent
import com.videomk.app.core.VoiceFeedback
import com.videomk.app.core.VoicePhase
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DictationFeedbackTest {
    private fun recording(limit: Int = 360) = VoiceFeedback().apply(VoiceEvent.Request).apply(VoiceEvent.Granted(1000, limit))
    private fun at(sec: Double, limit: Int = 360) = recording(limit).apply(VoiceEvent.Tick(1000 + (sec * 1000).toLong()))

    @Test fun `meter has a fixed bar count and silence is dots`() {
        val m = LevelMeter(); val h = m.push(0.0)
        assertEquals(DictationFeedback.BAR_COUNT, h.size); assertEquals(DictationFeedback.MIN_BAR, h.min(), 1e-9); assertTrue(h.max() <= 1.0)
    }
    @Test fun `attack is fast and release is slow`() {
        val m = LevelMeter(); m.push(0.1); val up = m.heights().last()
        assertTrue(up > 0.3)
        m.push(0.1); m.push(0.1); val loud = m.heights().last(); assertTrue(loud > up)
        m.push(0.0); val down = m.heights().last()
        assertTrue(down < loud && down > DictationFeedback.MIN_BAR + (loud - DictationFeedback.MIN_BAR) * 0.4)
    }
    @Test fun `constant input does not jitter and a loud frame raises the newest bar`() {
        val m = LevelMeter(); repeat(60) { m.push(0.2) }
        val h = m.heights(); assertEquals(1, h.map { "%.3f".format(it) }.toSet().size)
        m.push(1.0); assertTrue(m.heights().last() > h.last())
    }
    @Test fun `bad input is clamped and the meter is deterministic`() {
        val a = LevelMeter(); val b = LevelMeter()
        for (x in listOf(0.0, 0.3, Double.NaN, 5.0, -1.0, 0.1)) { a.push(x); b.push(x) }
        assertEquals(a.heights(), b.heights()); assertTrue(a.heights().max() <= 1.0)
        assertEquals(1.0, DictationFeedback.barHeight(1.0), 0.0); assertEquals(0.1, DictationFeedback.barHeight(0.0), 1e-9)
    }
    @Test fun `max amplitude maps to a level`() {
        assertEquals(0.0, DictationFeedback.level(0), 0.0); assertEquals(0.0, DictationFeedback.level(-5), 0.0)
        assertEquals(0.5, DictationFeedback.level(32767), 1e-9); assertEquals(1.0, DictationFeedback.level(99999), 1e-9)
    }
    @Test fun `happy path cancel and denied`() {
        var s = recording(); assertEquals(VoicePhase.Recording, s.phase)
        s = s.apply(VoiceEvent.Stop(5000)); assertEquals(VoicePhase.Transcribing, s.phase)
        s = s.apply(VoiceEvent.Ok); assertEquals(VoicePhase.Inserted, s.phase)
        assertEquals(VoicePhase.Idle, s.apply(VoiceEvent.Dismiss).phase)
        assertEquals(VoicePhase.Idle, VoiceFeedback().apply(VoiceEvent.Request).apply(VoiceEvent.Denied).phase)
        assertEquals(VoicePhase.Idle, recording().apply(VoiceEvent.Cancel).phase)
        assertEquals(VoicePhase.Idle, recording().apply(VoiceEvent.Stop(2000)).apply(VoiceEvent.Cancel).phase)
    }
    @Test fun `failure then retry restarts the wait clock`() {
        var s = recording().apply(VoiceEvent.Stop(2000)).apply(VoiceEvent.Fail("network"))
        assertEquals(VoicePhase.Failed, s.phase); assertEquals("network", s.failure)
        s = s.apply(VoiceEvent.Retry(9000)); assertEquals(VoicePhase.Transcribing, s.phase); assertEquals(9000L, s.waitStartedAt); assertNull(s.failure)
    }
    @Test fun `impossible events do nothing`() {
        assertEquals(VoicePhase.Idle, VoiceFeedback().apply(VoiceEvent.Stop(1)).phase)
        assertEquals(VoicePhase.Recording, recording().apply(VoiceEvent.Ok).phase)
        assertEquals(VoicePhase.Recording, recording().apply(VoiceEvent.Request).phase)
    }
    @Test fun `timer format`() {
        assertEquals("0:00", DictationFeedback.timer(0.0)); assertEquals("0:07", DictationFeedback.timer(7.0)); assertEquals("1:05", DictationFeedback.timer(65.0))
        assertEquals("5:59", DictationFeedback.timer(359.9)); assertEquals("0:00", DictationFeedback.timer(-3.0))
    }
    @Test fun `warnings at thirty and ten seconds`() {
        assertEquals(Warning.None, at(329.0).warning.first); assertEquals(Warning.Soon, at(330.0).warning.first); assertEquals(Warning.Soon, at(349.0).warning.first)
        assertEquals(Warning.Final, at(350.0).warning.first); assertEquals(10, at(350.0).warning.second); assertEquals(0, at(400.0).warning.second)
    }
    @Test fun `the daily allowance can be nearer than the clip limit`() {
        assertEquals(45, DictationFeedback.effectiveLimit(360, 45)); assertEquals(360, DictationFeedback.effectiveLimit(360, 5000))
        assertEquals(360, DictationFeedback.effectiveLimit(360, null)); assertEquals(0, DictationFeedback.effectiveLimit(360, -4))
        assertEquals(Warning.None, recording(45).warning.first); assertEquals(Warning.Soon, at(21.0, 45).warning.first)
    }
    @Test fun `wait hints`() {
        fun w(sec: Double) = recording().apply(VoiceEvent.Stop(2000)).apply(VoiceEvent.Tick(2000 + (sec * 1000).toLong())).wait
        assertEquals(DictationFeedback.Wait.Normal, w(7.0)); assertEquals(DictationFeedback.Wait.Slow, w(8.0)); assertEquals(DictationFeedback.Wait.Slow, w(59.0)); assertEquals(DictationFeedback.Wait.Timeout, w(60.0))
        assertEquals(DictationFeedback.Wait.Normal, recording().wait)
    }
    @Test fun `announcements change only at thresholds`() {
        assertEquals(at(1.0).announcement, at(100.0).announcement); assertEquals("warn_soon", at(335.0).announcement); assertEquals("warn_final", at(355.0).announcement)
        assertEquals(at(355.0).announcement, at(358.0).announcement); assertNull(VoiceFeedback().announcement)
    }
    @Test fun `tick never goes backwards`() {
        val s = recording().apply(VoiceEvent.Tick(4600)).apply(VoiceEvent.Tick(2000)); assertEquals(4600L, s.now); assertEquals(3, s.elapsed)
    }
    @Test fun `only hiccups are retryable`() {
        assertTrue(BetterFailure.Failed.isRetryable && BetterFailure.Network.isRetryable)
        for (f in listOf(BetterFailure.Quota, BetterFailure.Plan, BetterFailure.Paused, BetterFailure.TooLong, BetterFailure.BadAudio, BetterFailure.Auth)) assertTrue(!f.isRetryable)
    }
}
