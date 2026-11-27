package com.videomk.app

import com.videomk.app.core.MakingInfo
import com.videomk.app.core.MakingScene
import com.videomk.app.core.MakingSnapshot
import com.videomk.app.core.MakingStrip
import com.videomk.app.core.MakingTile.State
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The optional `making` object (docs/CREATE_API.md "Making status"): read leniently, drawn as far as it goes, never a crash. */
class MakingTest {
    private fun obj(s: String) = Json.parseToJsonElement(s).jsonObject
    private fun making(s: String) = MakingInfo.fromJson(obj(s))

    @Test fun `the documented object is read whole`() {
        val m = making("""{"scene_total": 9, "scene_done": 4, "live_line": "Adding footage of sunlit canopies", "narration_line": "Sunlight pours through the canopy.",
            "scenes": [{"index": 1, "done": true, "thumb_url": "https://x/1.jpg?sig=a"}, {"index": 2, "done": true}, {"index": 3, "done": false}]}""")!!
        assertEquals(9, m.sceneTotal); assertEquals(4, m.sceneDone)
        assertEquals("Adding footage of sunlit canopies", m.liveLine); assertEquals("Sunlight pours through the canopy.", m.narrationLine)
        assertEquals(MakingScene(5, 9), m.counter)
        val tiles = m.tiles()
        assertEquals(9, tiles.size)
        assertEquals(listOf(State.Done, State.Done, State.Current, State.Waiting), tiles.take(4).map { it.state })
        assertEquals("https://x/1.jpg?sig=a", tiles[0].thumbUrl); assertNull(tiles[1].thumbUrl)
        assertEquals(1, m.heroTile()!!.index)
    }

    @Test fun `absent, empty or wrongly typed never crashes and means no making`() {
        assertNull(MakingInfo.fromJson(null))
        assertNull(making("{}"))
        assertNull(making("""{"scene_total": "nine", "scene_done": [], "live_line": 7, "scenes": "no"}"""))
        assertNull(making("""{"scene_total": 0}""")); assertNull(making("""{"scene_total": -3, "live_line": "  "}"""))
        val v = VideoItem.fromJson(obj("""{"video_id": "v", "status": "ASSETS_CREATION", "making": 5}"""))
        assertNull(v.making); assertTrue(v.status.isRunning)
        assertNull(VideoItem.fromJson(obj("""{"video_id": "v", "status": "ASSETS_CREATION"}""")).making)
    }

    @Test fun `every field is optional`() {
        val line = making("""{"live_line": "Recording the narration"}""")!!
        assertEquals("Recording the narration", line.liveLine); assertNull(line.counter); assertTrue(line.tiles().isEmpty()); assertNull(line.heroTile())
        val counts = making("""{"scene_total": 3, "scene_done": 1}""")!!
        assertEquals(listOf(State.Done, State.Current, State.Waiting), counts.tiles().map { it.state })   // without the list the first scene_done tiles are filled
        val listOnly = making("""{"scenes": [{"done": true}, {"done": false}, {"done": true}]}""")!!
        assertEquals(3, listOnly.sceneTotal); assertEquals(2, listOnly.sceneDone)
        assertEquals(listOf(State.Done, State.Current, State.Done), listOnly.tiles().map { it.state })   // scenes do not finish in story order
    }

    @Test fun `absurd values are clamped and junk entries skipped`() {
        val m = making("""{"scene_total": 4, "scene_done": 99, "unknown": {"a": 1}, "scenes": [7, null, {"index": 2, "done": true, "thumb_url": "javascript:alert(1)", "extra": true}, {"index": 2, "done": false}, {"index": 50, "done": true}]}""")!!
        assertEquals(4, m.sceneDone); assertEquals(MakingScene(4, 4), m.counter); assertTrue(m.allDone)
        assertEquals(1, m.scenes.size); assertNull(m.scenes[0].thumbUrl)   // only https pictures, one entry per index, none past the total
        assertNull(making("""{"scene_total": 100000}"""))
        val long = making("""{"live_line": "${"word ".repeat(80)}", "narration_line": "a\n\n  b"}""")!!
        assertTrue(long.liveLine!!.length <= 140); assertTrue(long.liveLine!!.endsWith("…")); assertEquals("a b", long.narrationLine)
    }

    @Test fun `the counter never passes the total and nothing is in work once all is done`() {
        val m = making("""{"scene_total": 9, "scene_done": 9, "live_line": "Putting the scenes together"}""")!!
        assertEquals(MakingScene(9, 9), m.counter)
        assertTrue(m.tiles().all { it.state == State.Done })
        assertEquals(MakingScene(1, 9), making("""{"scene_total": 9}""")!!.counter)
    }

    @Test fun `the card window keeps the scene in work in view`() {
        val tiles = making("""{"scene_total": 20, "scene_done": 12}""")!!.tiles()
        val w = MakingStrip.window(tiles, 7)
        assertEquals(7, w.size); assertEquals(State.Current, w[4].state); assertEquals(13, w[4].index)
        assertEquals(tiles.take(5), MakingStrip.window(tiles.take(5), 7))
        val end = MakingStrip.window(making("""{"scene_total": 20, "scene_done": 20}""")!!.tiles(), 7)
        assertEquals(20, end.last().index)
        assertEquals((1..7).toList(), MakingStrip.window(making("""{"scene_total": 20}""")!!.tiles(), 7).map { it.index })
    }

    @Test fun `the snapshot keeps the calm fallback for whatever the server does not say`() {
        val base = MakingSnapshot.of("Bees", VideoStatus.Stage.VoiceAndVisuals, 10.0, 1.0)
        assertEquals(base, base.with(null))
        assertTrue(base.tiles.isEmpty()); assertFalse(base.live)
        val counts = base.with(making("""{"scene_total": 3, "scene_done": 1}"""))
        assertEquals(base.stageLine, counts.stageLine); assertEquals(MakingScene(2, 3), counts.scene); assertEquals(3, counts.tiles.size)
        val full = base.with(making("""{"scene_total": 3, "scene_done": 1, "live_line": "Placing your photos", "narration_line": "Hello."}"""))
        assertEquals("Placing your photos", full.stageLine); assertTrue(full.live); assertEquals("Hello.", full.narrationLine)
        assertNotNull(full.etaShort); assertFalse(full.etaShort!!.endsWith("."))
        assertTrue(full.spoken().contains("Scene 2 of 3")); assertTrue(full.spoken().contains("Placing your photos"))
    }
}
