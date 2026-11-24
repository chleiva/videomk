package com.videomk.app.core

import java.util.UUID
import kotlin.math.exp

/**
 * A video the user just asked for. It shows up in the list immediately (before the server has answered) and hands over to the
 * server's own row once that exists, so the user can keep browsing and queue more videos while they wait.
 */
data class PendingVideo(
    /** Doubles as the request's idempotency key: retrying the same placeholder can never create a second video. */
    val id: String = UUID.randomUUID().toString(),
    val brief: String,
    val options: CreateOptions,
    val photoCount: Int = 0,
    val state: State = State.Sending,
    val createdAtMillis: Long = System.currentTimeMillis(),
) {
    sealed interface State {
        data object Sending : State
        /** Photos going up before the video is requested. */
        data class Uploading(val done: Int, val total: Int) : State
        data class Accepted(val videoId: String) : State
        data class Failed(val message: String) : State
    }

    val acceptedVideoId: String? get() = (state as? State.Accepted)?.videoId
}

sealed interface LibraryEntry {
    val id: String

    data class Pending(val pending: PendingVideo) : LibraryEntry { override val id: String get() = "pending-${pending.id}" }
    data class Video(val video: VideoItem) : LibraryEntry { override val id: String get() = video.id }
}

object LibraryMerge {
    /**
     * Placeholders first (newest first), then the server's list in its own order (newest first).
     * A placeholder disappears the moment the server lists its video, so the row is replaced in place, never duplicated.
     */
    fun entries(pending: List<PendingVideo>, server: List<VideoItem>): List<LibraryEntry> {
        val known = server.map { it.id }.toSet()
        val live = pending.filter { p -> p.acceptedVideoId?.let { it !in known } ?: true }
        return live.sortedByDescending { it.createdAtMillis }.map { LibraryEntry.Pending(it) } + server.map { LibraryEntry.Video(it) }
    }

    /** Placeholders still needed after a refresh (the ones the server has taken over can be forgotten). */
    fun stillPending(pending: List<PendingVideo>, server: List<VideoItem>): List<PendingVideo> {
        val known = server.map { it.id }.toSet()
        return pending.filter { p -> p.acceptedVideoId?.let { it !in known } ?: true }
    }
}

/**
 * The server reports coarse stages, not percentages, so the bar is an honest estimate: each stage owns a slice of the bar and
 * eases toward the end of its slice the longer it takes, but never reaches the next slice until the server says so.
 */
object ProgressEstimator {
    fun slice(stage: VideoStatus.Stage): Pair<Double, Double> = when (stage) {
        VideoStatus.Stage.Starting -> 0.00 to 0.06
        VideoStatus.Stage.Writing -> 0.06 to 0.22
        VideoStatus.Stage.VoiceAndVisuals -> 0.22 to 0.62
        VideoStatus.Stage.Rendering -> 0.62 to 0.97
    }

    /** Typical seconds a stage takes for a video of [minutes] (from QA timings: planning is about fixed, the rest grows with length). */
    fun expectedSeconds(stage: VideoStatus.Stage, minutes: Double): Double = when (stage) {
        VideoStatus.Stage.Starting -> 6.0
        VideoStatus.Stage.Writing -> 18.0
        VideoStatus.Stage.VoiceAndVisuals -> 25 + 18 * minutes
        VideoStatus.Stage.Rendering -> 30 + 35 * minutes
    }

    fun fraction(stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double = CreateOptions.DEFAULT_MINUTES): Double {
        val (lo, hi) = slice(stage)
        val t = maxOf(0.0, secondsInStage) / expectedSeconds(stage, minutes)
        val eased = 1 - exp(-1.6 * t)   // fast at first, slows down, never completes the slice
        return lo + (hi - lo) * minOf(eased, 0.96)
    }
}
