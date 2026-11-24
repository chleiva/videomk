package com.videomk.app

import com.videomk.app.core.ApiError
import com.videomk.app.core.EditOp
import com.videomk.app.core.EditState
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.EditorBeat
import com.videomk.app.core.EditorDiff
import com.videomk.app.core.EditorLimits
import com.videomk.app.core.EditorSnapshot
import com.videomk.app.core.PhotoCandidate
import com.videomk.app.core.RenderMode
import com.videomk.app.core.SceneKind
import com.videomk.app.core.parseObject
import com.videomk.app.ui.EditorPhase
import com.videomk.app.ui.EditorViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

private fun beat(id: String, narration: String = "one two three four five six seven", kind: SceneKind? = SceneKind.Title) = EditorBeat(id, narration, kind)

class EditorDiffTest {
    private val server = listOf(beat("a", "alpha alpha alpha alpha alpha alpha"), beat("b", "bravo bravo bravo bravo bravo bravo"), beat("c", "charlie charlie charlie charlie charlie charlie"))

    @Test fun `no changes means no operations`() = assertTrue(EditorDiff.ops("T", server, "T", server).isEmpty())

    @Test fun `whitespace-only changes are not changes`() {
        val local = server.map { it.copy(narration = "  " + it.narration.replace(" ", "  ") + "\n") }
        assertTrue(EditorDiff.ops("T", server, " T ", local).isEmpty())
    }

    @Test fun `edited narration becomes a normalized set_narration`() {
        val local = server.map { if (it.id == "b") it.copy(narration = "  new   words here now and then ") else it }
        assertEquals(listOf<EditOp>(EditOp.SetNarration("b", "new words here now and then")), EditorDiff.ops("T", server, "T", local))
    }

    @Test fun `picks, deletes, moves and the title are emitted in order`() {
        val local = listOf(server[2], server[0].copy(narration = "changed changed changed changed changed changed"))   // b deleted, c moved before a, a edited
        val ops = EditorDiff.ops("Old", server, "New", local, picks = mapOf("c" to "unsplash:1", "ghost" to "x"))
        assertEquals(
            listOf(
                EditOp.PickImage("c", "unsplash:1"),                               // content first (c comes first in local)
                EditOp.SetNarration("a", "changed changed changed changed changed changed"),
                EditOp.Delete("b"),
                EditOp.Move("c", 0),
                EditOp.SetTitle("New"),
            ),
            ops,
        )
    }

    @Test fun `applying the moves to the server order gives the local order`() {
        val local = listOf(server[2], server[0], server[1])
        val ops = EditorDiff.ops("T", server, "T", local).filterIsInstance<EditOp.Move>()
        val order = server.map { it.id }.toMutableList()
        for (m in ops) { order.remove(m.id); order.add(m.to, m.id) }
        assertEquals(local.map { it.id }, order)
    }

    @Test fun `an empty title is never sent`() = assertTrue(EditorDiff.ops("Old", server, "   ", server).isEmpty())

    @Test fun `narration limits are checked beside the field`() {
        val limits = EditorLimits(6, 10, 90)
        assertEquals("Needs at least 6 words (now 3).", EditorDiff.narrationError("one two three", limits))
        assertNull(EditorDiff.narrationError("one two three four five six", limits))
        assertTrue(EditorDiff.narrationError(List(11) { "w" }.joinToString(" "), limits)!!.contains("Limited to 10 words"))
        assertEquals(0, EditorDiff.wordCount("  ")); assertEquals(5.0, EditorDiff.spokenSeconds("a b c d e f g h i j k l"), 0.5)
    }
}

class EditorSnapshotTest {
    private val sample = """{
      "video_id":"v1","rev":7,"edit_state":"READY","title":"The Golden Rule",
      "limits":{"max_beats":50,"min_words":5,"max_words":60},
      "final":{"url":"https://x/final.mp4","rev":6},"preview":{"url":"https://x/p.mp4","rev":7},
      "beats":[
        {"id":"b1","narration":"Hello there everyone watching","scene":{"type":"title","props":{"title":"Welcome"}},"duration":12.4,"chapter":"Intro"},
        {"id":"b2","narration":"A photo scene","scene":{"type":"image","props":{"alt":"A cat"}},"photo":{"url":"https://x/c.jpg","credit":"Photo by Jo","chosen":"unsplash:1"},
          "candidates":[{"provider":"unsplash","id":"1","thumb_url":"https://x/t.jpg","creator":"Jo","license":"unsplash","alt":"cat"},{"provider":"openverse","id":"2"}]},
        {"id":"b3","narration":"Footage of the sea","scene":{"type":"clip","props":{"clip_query":"waves"}},"stale":true},
        {"id":"b4","narration":"Several pictures together","scene":{"type":"gallery","props":{"title":"Our trip"}}},
        {"id":"b5","narration":"A scene from the future","scene":{"type":"hologram","props":{"title":"Whoa"}}},
        {"id":"b6","narration":"No scene at all"}
      ]}"""

    @Test fun `known, newly added and unknown scene types all decode, unknown ones with a generic label`() {
        val s = EditorSnapshot.fromJson(parseObject(sample))
        assertEquals(7, s.rev); assertEquals(EditState.Ready, s.editState); assertEquals(EditorLimits(5, 60, 50), s.limits)
        assertEquals(6, s.finalRev); assertEquals(7, s.previewRev)
        val beats = s.beats.associateBy { it.id }
        assertEquals("Title", beats["b1"]!!.label); assertEquals("Welcome", beats["b1"]!!.summary); assertEquals("Intro", beats["b1"]!!.chapter)
        assertEquals("Photo", beats["b2"]!!.label); assertEquals("A cat", beats["b2"]!!.summary)
        assertEquals(listOf("unsplash:1", "openverse:2"), beats["b2"]!!.candidates.map { it.key })
        assertEquals("Unknown", beats["b2"]!!.candidates[1].creator)
        assertEquals("Video clip", beats["b3"]!!.label); assertEquals("waves", beats["b3"]!!.summary); assertTrue(beats["b3"]!!.stale)
        assertEquals("Photo gallery", beats["b4"]!!.label)
        assertNull(beats["b5"]!!.kind); assertEquals("Scene", beats["b5"]!!.label); assertEquals("hologram", beats["b5"]!!.sceneType); assertEquals("Whoa", beats["b5"]!!.summary)
        assertEquals("Scene", beats["b6"]!!.label); assertEquals("", beats["b6"]!!.summary)
    }

    @Test fun `a beat missing its id or narration fails the snapshot as a server error, not a crash`() {
        try { EditorSnapshot.fromJson(parseObject("""{"video_id":"v","rev":1,"beats":[{"id":"x"}]}""")); org.junit.Assert.fail() } catch (e: ApiError) { assertEquals(ApiError.Server, e) }
    }

    @Test fun `edit state and defaults`() {
        val s = EditorSnapshot.fromJson(parseObject("""{"video_id":"v","rev":1,"edit_state":"RENDERING","edit_mode":"final","beats":[]}"""))
        assertEquals(EditState.Rendering, s.editState); assertEquals("final", s.editMode); assertEquals(EditorLimits(), s.limits); assertNull(s.finalUrl)
        assertEquals(EditState.Failed, EditorSnapshot.fromJson(parseObject("""{"video_id":"v","rev":1,"edit_state":"FAILED","beats":[]}""")).editState)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class CaptionsOptionTest {
    private fun snap(extra: String) = EditorSnapshot.fromJson(parseObject("""{"video_id":"v","rev":1,"edit_state":"READY","title":"T","beats":[]$extra}"""))

    @Test fun `the snapshot carries the subtitles choice and defaults to on`() {
        assertFalse(snap(",\"captions\":false").captions)
        assertTrue(snap(",\"captions\":true").captions)
        assertTrue(snap("").captions)                       // an older server that does not send it
        assertTrue(snap(",\"captions\":\"no\"").captions)    // a wrongly typed value is ignored
    }

    @Test fun `toggling subtitles in the editor is one set_meta operation, both ways`() {
        assertTrue(EditorDiff.ops("T", emptyList(), "T", emptyList()).isEmpty())
        val off = EditorDiff.ops("T", emptyList(), "T", emptyList(), serverCaptions = true, localCaptions = false)
        assertEquals(listOf<EditOp>(EditOp.SetCaptions(false)), off)
        val json = off[0].json.jsonObject
        assertEquals("set_meta", json["op"]!!.jsonPrimitive.content); assertEquals("false", json["captions"]!!.jsonPrimitive.content)
        assertEquals(listOf<EditOp>(EditOp.SetCaptions(true)), EditorDiff.ops("T", emptyList(), "T", emptyList(), serverCaptions = false, localCaptions = true))
        assertTrue(EditorDiff.ops("T", emptyList(), "T", emptyList(), serverCaptions = false, localCaptions = false).isEmpty())
    }

    @Test fun `new videos have subtitles on unless the creator turns them off`() {
        assertTrue(CreateOptions().captions); assertFalse(CreateOptions(captions = false).captions)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class EditorViewModelTest {
    private lateinit var backend: FakeBackend
    private val words = "one two three four five six seven"

    private fun snapshot(rev: Int = 1, state: EditState = EditState.Ready, previewRev: Int? = null, finalRev: Int? = null, mode: String? = null) = EditorSnapshot(
        "v1", rev, state, mode, "Title", true, listOf(beat("a", "$words a"), beat("b", "$words b", kind = SceneKind.Image).copy(candidates = listOf(PhotoCandidate("unsplash", "9", creator = "Jo")))),
        EditorLimits(), finalUrl = "https://x/final.mp4", finalRev = finalRev, previewUrl = "https://x/preview.mp4", previewRev = previewRev,
    )

    @Before fun setUp() { Dispatchers.setMain(Dispatchers.Unconfined); backend = FakeBackend().also { it.snapshots.add(snapshot()) } }
    @After fun tearDown() { Dispatchers.resetMain() }

    private fun vm(onChanged: () -> Unit = {}) = EditorViewModel("v1", backend, onChanged, pollMillis = 1)
    private fun EditorViewModel.await(pred: (com.videomk.app.ui.EditorState) -> Boolean) = runBlocking { withTimeout(5000) { state.first(pred) } }

    @Test fun `loads into the editing phase, clean`() {
        val m = vm(); val s = m.await { it.phase == EditorPhase.Editing }
        assertEquals(2, s.beats.size); assertFalse(s.isDirty); assertEquals("Title", s.title)
    }

    @Test fun `editing narration makes it dirty and the diff is exactly that edit`() {
        val m = vm(); m.await { it.phase == EditorPhase.Editing }
        m.setNarration("a", "brand new narration with enough words")
        val s = m.state.value
        assertTrue(s.isDirty); assertTrue(s.isEdited("a")); assertFalse(s.isEdited("b"))
        assertEquals(listOf<EditOp>(EditOp.SetNarration("a", "brand new narration with enough words")), s.ops)
        m.discard(); assertFalse(m.state.value.isDirty)
    }

    @Test fun `too-short narration blocks submit with a message and sends nothing`() {
        val m = vm(); m.await { it.phase == EditorPhase.Editing }
        m.setNarration("a", "too short")
        assertNotNull(m.state.value.narrationError("a"))
        m.submit(RenderMode.Preview)
        assertTrue(m.state.value.banner!!.contains("Needs at least")); assertTrue(backend.editCalls.isEmpty())
    }

    @Test fun `a picked photo becomes a pick_image operation and can be undone`() {
        val m = vm(); m.await { it.phase == EditorPhase.Editing }
        m.pick(PhotoCandidate("unsplash", "9"), "b")
        assertEquals(listOf<EditOp>(EditOp.PickImage("b", "unsplash:9")), m.state.value.ops)
        m.clearPick("b"); assertTrue(m.state.value.ops.isEmpty())
    }

    @Test fun `move and delete work, and the last scene cannot be deleted`() {
        val m = vm(); m.await { it.phase == EditorPhase.Editing }
        m.move("b", -1); assertEquals(listOf("b", "a"), m.state.value.beats.map { it.id })
        m.move("b", -1); assertEquals(listOf("b", "a"), m.state.value.beats.map { it.id })   // already first
        assertTrue(m.state.value.ops.any { it is EditOp.Move })
        m.delete("b"); assertEquals(listOf("a"), m.state.value.beats.map { it.id })
        m.delete("a"); assertEquals(1, m.state.value.beats.size); assertEquals("A video needs at least one scene.", m.state.value.banner)
    }

    @Test fun `submitting applies the edits against the loaded revision, waits for the render, then shows the result`() {
        backend.snapshots.clear()
        backend.snapshots.add(snapshot(rev = 1))
        var changed = 0
        val m = vm { changed++ }; m.await { it.phase == EditorPhase.Editing }
        m.setNarration("a", "brand new narration with enough words")
        backend.snapshots.clear()
        backend.snapshots.add(snapshot(rev = 2, state = EditState.Rendering, mode = "preview"))
        backend.snapshots.add(snapshot(rev = 2, state = EditState.Ready, previewRev = 2))
        m.submit(RenderMode.Preview)
        val done = m.await { it.phase is EditorPhase.Done }
        assertEquals(RenderMode.Preview, (done.phase as EditorPhase.Done).mode)
        assertEquals("https://x/preview.mp4", done.resultUrl)
        assertEquals(1, backend.editCalls.size); assertEquals(1, backend.editCalls[0].first); assertEquals(RenderMode.Preview, backend.editCalls[0].third)
        assertEquals(1, changed)
        assertTrue(done.canPublishWithoutChanges)   // the preview is current and nothing is published yet: Publish is allowed with no new edits
    }

    @Test fun `the subtitles switch makes the editor dirty and goes out as one set_meta op`() {
        val m = vm(); m.await { it.phase == EditorPhase.Editing }
        assertTrue(m.state.value.captions)
        m.setCaptions(false)
        assertEquals(listOf<EditOp>(EditOp.SetCaptions(false)), m.state.value.ops); assertTrue(m.state.value.isDirty)
        m.setCaptions(true); assertFalse(m.state.value.isDirty)
        m.setCaptions(false); m.submit(RenderMode.Preview)
        m.await { it.phase is EditorPhase.Rendering || it.phase is EditorPhase.Done || it.banner != null }
        assertEquals(listOf<EditOp>(EditOp.SetCaptions(false)), backend.editCalls.single().second)
    }

    @Test fun `a conflict keeps the user's edits and says how to recover`() {
        val m = vm(); m.await { it.phase == EditorPhase.Editing }
        m.setNarration("a", "brand new narration with enough words")
        backend.editError = ApiError.Conflict("This video changed.")
        m.submit(RenderMode.Final)
        val s = m.await { it.banner != null }
        assertTrue(s.banner!!.contains("This video changed.") && s.banner!!.contains("kept")); assertTrue(s.isDirty); assertEquals(EditorPhase.Editing, s.phase)
    }

    @Test fun `a failed render shows the failure and a failed load shows a reload state`() {
        val m = vm(); m.await { it.phase == EditorPhase.Editing }
        m.setNarration("a", "brand new narration with enough words")
        backend.snapshots.clear(); backend.snapshots.add(snapshot(rev = 2, state = EditState.Failed))
        m.submit(RenderMode.Final)
        assertTrue(m.await { it.phase is EditorPhase.Failed }.phase.let { (it as EditorPhase.Failed).message.contains("didn't finish") })

        backend.snapshots.clear()   // the server now fails
        val failing = vm()
        assertTrue(failing.await { it.phase is EditorPhase.Failed }.phase is EditorPhase.Failed)
    }

    @Test fun `opening an editor whose video is already rendering waits for it`() {
        backend.snapshots.clear()
        backend.snapshots.add(snapshot(rev = 3, state = EditState.Rendering, mode = "final"))
        backend.snapshots.add(snapshot(rev = 3, state = EditState.Ready, finalRev = 3))
        val m = vm()
        assertEquals(RenderMode.Final, (m.await { it.phase is EditorPhase.Done }.phase as EditorPhase.Done).mode)
    }
}
