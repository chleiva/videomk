package com.videomk.app.core

import kotlinx.serialization.json.JsonObject

/**
 * The optional `making` object of a video that is being made (docs/CREATE_API.md "Making status"): scenes done, one plain line about what is happening now and the
 * sentence being narrated. Every field is optional and read leniently: a missing, mistyped or absurd value is simply absent, never a crash, and the screens draw what is there.
 */
data class MakingInfo(
    val sceneTotal: Int? = null,
    val sceneDone: Int? = null,
    val liveLine: String? = null,
    val narrationLine: String? = null,
    val scenes: List<Scene> = emptyList(),
) {
    /** [index] counts from 1 in story order. [thumbUrl] is a private, short-lived link: cache the picture by video id and index, never by the link. */
    data class Scene(val index: Int, val done: Boolean, val thumbUrl: String? = null)

    /** "Scene 5 of 9": the scene in work is the one after the last finished, never past the total. Null while the total is unknown. */
    val counter: MakingScene? get() {
        val total = sceneTotal ?: return null
        return MakingScene(minOf((sceneDone ?: 0) + 1, total), total)
    }

    /** True once every scene is stored (the render: only the live line changes then). */
    val allDone: Boolean get() = sceneTotal != null && (sceneDone ?: 0) >= sceneTotal

    /**
     * One tile per planned scene, in story order. Scenes do not finish in order, so `scenes[].done` decides each tile when the list is there; without it the first
     * `scene_done` tiles are filled. The first scene not done is the one in work. Empty while the total is unknown.
     */
    fun tiles(): List<MakingTile> {
        val total = sceneTotal ?: return emptyList()
        val byIndex = scenes.associateBy { it.index }
        val done = (1..total).map { i -> byIndex[i]?.done ?: (scenes.isEmpty() && i <= (sceneDone ?: 0)) }
        val current = done.indexOfFirst { !it }
        return (1..total).map { i ->
            MakingTile(i, when { done[i - 1] -> MakingTile.State.Done; i - 1 == current -> MakingTile.State.Current; else -> MakingTile.State.Waiting }, byIndex[i]?.thumbUrl?.takeIf { done[i - 1] })
        }
    }

    /** The picture for the large frame: the newest finished scene that has one (the scene in work has no picture yet). */
    fun heroTile(): MakingTile? = tiles().lastOrNull { it.state == MakingTile.State.Done && it.thumbUrl != null }

    companion object {
        const val MAX_SCENES = 200
        private const val MAX_LINE = 140
        private const val MAX_NARRATION = 240

        fun fromJson(o: JsonObject?): MakingInfo? {
            o ?: return null
            return try {
                val scenes = o.arr("scenes").orEmpty().take(MAX_SCENES).mapIndexedNotNull { i, e ->
                    val s = e.asObject() ?: return@mapIndexedNotNull null
                    val index = s.int("index")?.takeIf { it in 1..MAX_SCENES } ?: (i + 1)
                    Scene(index, s.bool("done") ?: false, s.str("thumb_url")?.trim()?.takeIf { it.startsWith("https://") })
                }.distinctBy { it.index }.sortedBy { it.index }
                val total = (o.int("scene_total") ?: scenes.size.takeIf { it > 0 })?.takeIf { it in 1..MAX_SCENES }
                val done = (o.int("scene_done") ?: scenes.count { it.done }.takeIf { scenes.isNotEmpty() })?.coerceIn(0, total ?: MAX_SCENES)
                val info = MakingInfo(total, done, line(o.str("live_line"), MAX_LINE), line(o.str("narration_line"), MAX_NARRATION), if (total == null) emptyList() else scenes.filter { it.index <= total })
                info.takeIf { it.sceneTotal != null || it.liveLine != null || it.narrationLine != null }
            } catch (e: Exception) { null }
        }

        private fun line(s: String?, max: Int): String? = s?.replace(Regex("\\s+"), " ")?.trim()?.takeIf { it.isNotEmpty() }?.let { if (it.length > max) it.take(max - 1).trimEnd() + "…" else it }
    }
}

data class MakingTile(val index: Int, val state: State, val thumbUrl: String? = null) {
    enum class State { Done, Current, Waiting }
}

object MakingStrip {
    /**
     * The tiles a card with room for [max] shows: all of them when they fit, else a window that keeps the scene in work in view with finished scenes before it
     * and what is coming after it (the strip on the Making screen scrolls instead).
     */
    fun window(tiles: List<MakingTile>, max: Int): List<MakingTile> {
        if (tiles.size <= max || max <= 0) return tiles
        val current = tiles.indexOfFirst { it.state == MakingTile.State.Current }.let { if (it < 0) tiles.lastIndex else it }
        val start = (current - (max - 3)).coerceIn(0, tiles.size - max)
        return tiles.subList(start, start + max)
    }
}
