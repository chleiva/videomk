package com.videomk.app.core

import com.videomk.app.R

/** "Scene 3 of 7". The server reports stages, not scenes, so this stays null until the backend sends it (docs/UX_REVIEW.md section 4, backend item 6). The card already lays it out. */
data class MakingScene(val index: Int, val total: Int)

/**
 * Everything the ONE waiting component needs. The home card and the detail screen both render a value of this type, so they can never disagree.
 * Seams for later (no UI change needed when they are filled): [scene] (per-scene progress), [thumbnails] (poster urls as scenes are found),
 * [narrationLine] (the line being narrated), and `MakingEvents` for notifications.
 */
data class MakingSnapshot(
    val title: String,
    val stageLine: String,
    val eta: String?,
    val fills: List<Float>,
    val current: Int,
    val scene: MakingScene? = null,
    val thumbnails: List<String> = emptyList(),
    val narrationLine: String? = null,
) {
    /** What TalkBack reads for the whole card. */
    fun spoken(): String {
        val line = listOfNotNull(stageLine, scene?.let { Txt.s(R.string.making_scene_counter, it.index, it.total) }, eta).joinToString(" ")
        return Txt.s(R.string.lib_making_desc, title, line)
    }

    companion object {
        fun of(title: String, stage: VideoStatus.Stage, secondsInStage: Double, minutes: Double): MakingSnapshot {
            val fraction = ProgressEstimator.fraction(stage, secondsInStage, minutes)
            return MakingSnapshot(title, MakingSteps.sentence(stage), ProgressEstimator.leftText(stage, secondsInStage, minutes), MakingSteps.fills(fraction), MakingSteps.current(fraction))
        }

        /** A request still going to the server (or its photos still going up): no estimate yet, the bar shows the upload share. */
        fun pending(title: String, line: String, fraction: Double): MakingSnapshot =
            MakingSnapshot(title, line, null, MakingSteps.fills(fraction), MakingSteps.current(fraction))
    }
}

/**
 * Clean seam for the notification work (needs backend registration and the owner's decision, so nothing is sent today): the view model reports
 * the moment a video that was being made becomes ready or failed. A future FCM / ongoing-progress implementation subscribes here.
 */
fun interface MakingEvents { fun onFinished(videoId: String, title: String, ready: Boolean) }
