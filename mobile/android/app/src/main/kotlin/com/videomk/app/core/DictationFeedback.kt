package com.videomk.app.core

import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Visible feedback for dictation (docs/DICTATION_FEEDBACK_2026-11-28.md): the pure rules, the same cases as web `dictationFeedback.ts` and iOS `DictationFeedback.swift`.
 * No clock and no UI here: the screen feeds in mic levels (0..1) and time in milliseconds.
 */
object DictationFeedback {
    const val BAR_COUNT = 24
    const val METER_FPS = 25
    const val MIN_BAR = 0.1          // silence is a row of dots, never a gap
    const val ATTACK = 0.6           // fast up
    const val RELEASE = 0.12         // slow down: calm
    const val SLOW_AFTER_S = 8       // "taking longer than usual"
    const val TIMEOUT_AFTER_S = 60   // then Retry / device dictation
    const val WARN_SOON_S = 30
    const val WARN_FINAL_S = 10

    /** Loudness (0..1) to bar height (MIN_BAR..1): speech sits at 0.02 to 0.3, so the curve is steep at the bottom. */
    fun barHeight(level: Double): Double {
        val v = min(1.0, max(0.0, level) * 3.2)
        return MIN_BAR + (1 - MIN_BAR) * sqrt(v)
    }
    /** `MediaRecorder.getMaxAmplitude()` (0..32767, peak since the last call) to a 0..1 level; peaks run about twice the RMS, so halve them. */
    fun level(maxAmplitude: Int): Double = min(1.0, max(0, maxAmplitude) / 32767.0 * 0.5)
    /** m:ss */
    fun timer(seconds: Double): String { val t = max(0, seconds.toInt()); return "%d:%02d".format(t / 60, t % 60) }
    /** The nearer of the clip limit and what is left of today's allowance. */
    fun effectiveLimit(maxClip: Int, secondsLeft: Int?): Int = max(0, if (secondsLeft == null) maxClip else min(maxClip, secondsLeft))

    enum class Warning { None, Soon, Final }
    fun warning(elapsed: Int, limit: Int, recording: Boolean = true): Pair<Warning, Int> {
        val remaining = max(0, limit - max(0, elapsed))
        if (!recording) return Warning.None to remaining
        return (if (remaining <= WARN_FINAL_S) Warning.Final else if (remaining <= WARN_SOON_S) Warning.Soon else Warning.None) to remaining
    }
    enum class Wait { Normal, Slow, Timeout }
    fun wait(waited: Int): Wait = if (waited >= TIMEOUT_AFTER_S) Wait.Timeout else if (waited >= SLOW_AFTER_S) Wait.Slow else Wait.Normal
}

/** A scrolling level history: newest bar on the right. [push] takes the raw level once per frame. */
class LevelMeter(val count: Int = DictationFeedback.BAR_COUNT) {
    private var smooth = 0.0
    private var bars = DoubleArray(count) { DictationFeedback.MIN_BAR }
    fun push(raw: Double): List<Double> {
        val x = if (raw.isFinite()) min(1.0, max(0.0, raw)) else 0.0
        smooth += (x - smooth) * (if (x > smooth) DictationFeedback.ATTACK else DictationFeedback.RELEASE)
        bars = DoubleArray(count) { i -> if (i < count - 1) bars[i + 1] else DictationFeedback.barHeight(smooth) }
        return heights()
    }
    fun heights(): List<Double> = bars.toList()
    fun reset() { smooth = 0.0; bars = DoubleArray(count) { DictationFeedback.MIN_BAR } }
}

enum class VoicePhase { Idle, Requesting, Recording, Transcribing, Failed, Inserted }

sealed interface VoiceEvent {
    data object Request : VoiceEvent
    data class Granted(val now: Long, val limit: Int) : VoiceEvent
    data object Denied : VoiceEvent
    data class Stop(val now: Long) : VoiceEvent
    data object Ok : VoiceEvent
    data class Fail(val kind: String) : VoiceEvent
    data object Cancel : VoiceEvent
    data class Retry(val now: Long) : VoiceEvent
    data object Dismiss : VoiceEvent
    data class Tick(val now: Long) : VoiceEvent
}

/** The phase machine; times are milliseconds. Impossible events change nothing. */
data class VoiceFeedback(
    val phase: VoicePhase = VoicePhase.Idle, val startedAt: Long? = null, val waitStartedAt: Long? = null, val now: Long = 0, val limit: Int = 360, val failure: String? = null,
) {
    fun apply(e: VoiceEvent): VoiceFeedback = when {
        e is VoiceEvent.Request && phase in setOf(VoicePhase.Idle, VoicePhase.Inserted, VoicePhase.Failed) -> VoiceFeedback(phase = VoicePhase.Requesting)
        e is VoiceEvent.Granted && phase == VoicePhase.Requesting -> copy(phase = VoicePhase.Recording, startedAt = e.now, now = e.now, limit = e.limit)
        e is VoiceEvent.Denied && (phase == VoicePhase.Requesting || phase == VoicePhase.Recording) -> VoiceFeedback()
        e is VoiceEvent.Stop && phase == VoicePhase.Recording -> copy(phase = VoicePhase.Transcribing, waitStartedAt = e.now, now = max(now, e.now))
        e is VoiceEvent.Ok && phase == VoicePhase.Transcribing -> copy(phase = VoicePhase.Inserted)
        e is VoiceEvent.Fail && phase == VoicePhase.Transcribing -> copy(phase = VoicePhase.Failed, failure = e.kind)
        e is VoiceEvent.Cancel && phase in setOf(VoicePhase.Recording, VoicePhase.Transcribing, VoicePhase.Requesting) -> VoiceFeedback()
        e is VoiceEvent.Retry && phase == VoicePhase.Failed -> copy(phase = VoicePhase.Transcribing, waitStartedAt = e.now, now = max(now, e.now), failure = null)
        e is VoiceEvent.Dismiss && (phase == VoicePhase.Failed || phase == VoicePhase.Inserted) -> VoiceFeedback()
        e is VoiceEvent.Tick -> copy(now = max(now, e.now))
        else -> this
    }
    val elapsed: Int get() = startedAt?.let { max(0, ((now - it) / 1000).toInt()) } ?: 0
    val waited: Int get() = waitStartedAt?.let { max(0, ((now - it) / 1000).toInt()) } ?: 0
    val warning: Pair<DictationFeedback.Warning, Int> get() = DictationFeedback.warning(elapsed, limit, phase == VoicePhase.Recording)
    val wait: DictationFeedback.Wait get() = if (phase == VoicePhase.Transcribing) DictationFeedback.wait(waited) else DictationFeedback.Wait.Normal
    /** What the screen reader says: changes only at thresholds, never per tick (null = nothing). */
    val announcement: String? get() = when (phase) {
        VoicePhase.Recording -> when (warning.first) { DictationFeedback.Warning.Final -> "warn_final"; DictationFeedback.Warning.Soon -> "warn_soon"; else -> "listening" }
        VoicePhase.Transcribing -> if (wait == DictationFeedback.Wait.Slow) "slow" else "transcribing"
        VoicePhase.Failed -> "failed"
        VoicePhase.Inserted -> "inserted"
        else -> null
    }
}
