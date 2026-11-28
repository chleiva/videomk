package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.BetterDictationEngine
import com.videomk.app.core.BetterDictationRules
import com.videomk.app.core.BetterFailure
import com.videomk.app.core.BetterNote
import com.videomk.app.core.BetterResolution
import com.videomk.app.core.Capabilities
import com.videomk.app.core.ClipRecorder
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.DictateResult
import com.videomk.app.core.DictationAnswer
import com.videomk.app.core.DictationCaps
import com.videomk.app.core.DictationClip
import com.videomk.app.core.DictationEngine
import com.videomk.app.core.DictationIds
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.DictationService
import com.videomk.app.core.placeBetterText
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File

private const val ID1 = "0123456789abcdef0123456789abcdef"
private const val ID2 = "fedcba9876543210fedcba9876543210"

@OptIn(ExperimentalCoroutinesApi::class)
class BetterDictationTest {
    // ---- pure rules

    @Test fun `capabilities block parses leniently`() {
        val c = Capabilities.fromJson(Json.parseToJsonElement(CAPS.replace("%D", """{"premium":true,"available":true,"paused":false,"seconds_left_today":540,"max_clip_seconds":400,"max_clip_bytes":9999999,"requires_plan":null,"provider":"openai"}""")).jsonObject)
        val d = c.dictation!!
        assertTrue(d.isUsable); assertTrue(d.premium); assertFalse(d.showsUpgradeHint); assertEquals(540, d.secondsLeft)
        assertEquals(360.0, d.limitSeconds, 0.0)          // never over 6 minutes
        assertEquals(3 * 1024 * 1024, d.byteLimit)       // never over 3 MB
        assertNull(Capabilities.fromJson(Json.parseToJsonElement(CAPS.replace("\"dictation\": %D,", "")).jsonObject).dictation)
        assertNull(Capabilities.fromJson(Json.parseToJsonElement(CAPS.replace("%D", "\"nope\"")).jsonObject).dictation)   // not an object: not offered
    }

    @Test fun `free sees no switch and only a plan hint, paused and used up are not usable`() {
        val free = DictationCaps(premium = false, available = false, requiresPlan = "pro")
        assertFalse(free.isUsable); assertTrue(free.showsUpgradeHint)
        assertFalse(DictationCaps(premium = true, available = true, paused = true).isUsable)
        assertFalse(DictationCaps(premium = true, available = false).showsUpgradeHint)   // the plan has it: never the Pro line
        assertFalse(DictationCaps(premium = false, available = false, requiresPlan = null).showsUpgradeHint)
    }

    @Test fun `better dictation is used only when offered and wanted`() {
        val ok = DictationCaps(premium = true, available = true)
        assertTrue(BetterDictationRules.uses(ok, preferred = true))
        assertFalse(BetterDictationRules.uses(ok, preferred = false))
        assertFalse(BetterDictationRules.uses(null, preferred = true))
        assertFalse(BetterDictationRules.uses(ok.copy(paused = true), preferred = true))
    }

    @Test fun `ids keep 20 newest without repeats and only 32 hex`() {
        val ids = DictationIds()
        ids.add(ID1); ids.add(ID1); ids.add("short"); ids.add("z".repeat(32))
        assertEquals(listOf(ID1), ids.list)
        for (i in 0 until 25) ids.add(i.toString(16).padStart(32, '0'))
        assertEquals(20, ids.list.size)
        assertEquals(24.toString(16).padStart(32, '0'), ids.list.last())
        assertFalse(ID1 in ids.list)
        ids.clear(); assertTrue(ids.list.isEmpty())
    }

    @Test fun `text placement replaces the preview, never a hand edit`() {
        assertEquals("Please make it fun. For my niece", placeBetterText("Please make it fun.", "Please make it fun. for my niece", "Please make it fun. for my niece", "For my niece"))
        assertEquals("Better words", placeBetterText("", "", "", "Better words"))                     // no preview: a plain append
        assertNull(placeBetterText("a", "a b", "a b typed", "Better"))                                 // edited meanwhile: untouched
        assertNull(placeBetterText("a", "a b", "a b", "  "))                                           // blank text
        assertEquals("line\nBetter", placeBetterText("line\n", "line\nb", "line\nb", "Better"))
    }

    @Test fun `failures map to the same answers as the other clients`() {
        assertEquals(BetterFailure.Plan, BetterFailure.from(403, """{"code":"dictation_plan"}"""))
        assertEquals(BetterFailure.Quota, BetterFailure.from(429, """{"code":"dictation_quota"}"""))
        assertEquals(BetterFailure.Quota, BetterFailure.from(429, null))
        assertEquals(BetterFailure.TooLong, BetterFailure.from(413, "{}"))
        assertEquals(BetterFailure.Paused, BetterFailure.from(503, """{"code":"dictation_paused"}"""))
        assertEquals(BetterFailure.BadAudio, BetterFailure.from(400, """{"code":"bad_audio"}"""))
        assertEquals(BetterFailure.Auth, BetterFailure.from(401, "no json"))
        assertEquals(BetterFailure.Auth, BetterFailure.from(403, """{"message":"x"}"""))
        assertEquals(BetterFailure.Failed, BetterFailure.from(502, """{"code":"dictation_failed"}"""))
        assertEquals(BetterFailure.Failed, BetterFailure.from(500, null))
        assertEquals(listOf(BetterNote.Quota, BetterNote.Limit, BetterNote.Failed, BetterNote.Failed, BetterNote.Failed, null, null, null),
            listOf(BetterFailure.Quota, BetterFailure.TooLong, BetterFailure.Failed, BetterFailure.Network, BetterFailure.BadAudio, BetterFailure.Plan, BetterFailure.Paused, BetterFailure.Auth).map { it.note })
    }

    @Test fun `resolution is text, id and line`() {
        val ok = DictateResult.Success(DictationAnswer(ID1, "Hello there"))
        assertEquals(BetterResolution("Hello there", ID1, null), BetterResolution.resolve("", "hallo", "hallo", ok, false))
        assertEquals(BetterResolution(null, ID1, null), BetterResolution.resolve("", "hallo", "hallo typed", ok, false))      // hand edit: id still kept, the clip was paid
        assertEquals(BetterResolution(null, null, null), BetterResolution.resolve("", "", "", DictateResult.Success(DictationAnswer(ID1, " ")), false))
        assertEquals(BetterNote.Limit, BetterResolution.resolve("", "", "", ok, limitHit = true).note)
        assertEquals(BetterResolution(null, null, BetterNote.Quota), BetterResolution.resolve("", "x", "x", DictateResult.Failure(BetterFailure.Quota), true))
        assertEquals(BetterNote.Limit, BetterResolution.resolve("", "x", "x", DictateResult.Failure(BetterFailure.Failed), true).note)
        assertNull(BetterResolution.resolve("", "x", "x", DictateResult.Failure(BetterFailure.Plan), false).note)
    }

    @Test fun `clip body has base64 audio, mime, one decimal, one language and the last 400 characters`() {
        val body = DictationClip(byteArrayOf(1, 2, 3), 23.46, listOf("es", "en", "fr", "de", "it"), "x".repeat(300) + "y".repeat(300)).body()
        assertEquals("AQID", body["audio"]!!.jsonPrimitive.content)
        assertEquals("audio/mp4", body["mime"]!!.jsonPrimitive.content)
        assertEquals(23.5, body["seconds"]!!.jsonPrimitive.content.toDouble(), 0.0)
        assertEquals(4, body["languages"]!!.jsonArray.size)
        assertEquals("x".repeat(100) + "y".repeat(300), body["prompt"]!!.jsonPrimitive.content)
        assertFalse(DictationClip(byteArrayOf(1), 1.0, listOf("en"), "   ").body().containsKey("prompt"))
    }

    // ---- the API call against a fake server

    private lateinit var server: MockWebServer
    private lateinit var api: ApiClient
    @Before fun setUp() { server = MockWebServer().apply { start() }; api = ApiClient(configFor(server), FixedAuth(), appVersion = "9.9", locale = { "es" }) }
    @After fun tearDown() { server.close() }

    private fun clip() = DictationClip(byteArrayOf(9, 9), 4.0, listOf("es"), "un video")

    @Test fun `dictate posts the clip and answers the text`() = runBlocking {
        server.enqueue(json(body = """{"id":"$ID1","text":"Hola, mundo","language":"es","seconds":4.0,"seconds_left_today":577,"max_clip_seconds":360}"""))
        val r = api.dictate(clip())
        assertEquals(DictateResult.Success(DictationAnswer(ID1, "Hola, mundo", 4.0, 577)), r)
        val req = server.takeRequest()
        assertEquals("POST", req.method); assertEquals("/prod/users/user-1/dictation", req.url.encodedPath)
        assertEquals("Bearer tok-abc", req.headers["Authorization"]); assertEquals("es", req.headers["X-Locale"])
        val sent = Json.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals("CQk=", sent["audio"]!!.jsonPrimitive.content); assertEquals("audio/mp4", sent["mime"]!!.jsonPrimitive.content)
        assertEquals("es", sent["languages"]!!.jsonArray[0].jsonPrimitive.content); assertEquals("un video", sent["prompt"]!!.jsonPrimitive.content)
    }

    @Test fun `dictate maps every server error to a typed failure and never throws`() = runBlocking {
        fun fail(code: Int, body: String, expected: BetterFailure) { server.enqueue(json(code, body)); assertEquals(DictateResult.Failure(expected), runBlocking { api.dictate(clip()) }) }
        fail(403, """{"code":"dictation_plan","message":"x"}""", BetterFailure.Plan)
        fail(429, """{"code":"dictation_quota"}""", BetterFailure.Quota)
        fail(413, """{"code":"dictation_too_long"}""", BetterFailure.TooLong)
        fail(502, """{"code":"dictation_failed"}""", BetterFailure.Failed)
        fail(503, """{"code":"dictation_paused"}""", BetterFailure.Paused)
        fail(400, """{"code":"bad_audio"}""", BetterFailure.BadAudio)
        fail(403, """{"message":"Forbidden"}""", BetterFailure.Auth)
        fail(200, "not json", BetterFailure.Failed)
        server.close()
        assertEquals(DictateResult.Failure(BetterFailure.Network), api.dictate(clip()))    // offline
    }

    @Test fun `create sends dictation_ids and leaves the key out when there are none`() = runBlocking {
        server.enqueue(json(202, """{"video_id":"v1"}""")); server.enqueue(json(202, """{"video_id":"v2"}"""))
        api.startVideo("A video about how bees make honey", "r1", CreateOptions(minutes = 1.0), dictationIds = listOf(ID1, ID2))
        api.startVideo("A video about how bees make honey", "r2", CreateOptions(minutes = 1.0))
        val a = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals(listOf(ID1, ID2), a["dictation_ids"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertFalse(Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject.containsKey("dictation_ids"))
    }

    // ---- the engine: native preview + clip + upload, with fakes

    private class FakeNative : DictationEngine {
        override val state = MutableStateFlow<DictationEngine.State>(DictationEngine.State.Idle)
        var canListen = true
        var started = 0; var stopped = 0; var released = 0
        override val isListening get() = state.value is DictationEngine.State.Listening
        override var onText: ((String) -> Unit)? = null
        override var textProvider: (() -> String)? = null
        override var onKeyboardFallback: (() -> Unit)? = null
        override fun start(currentText: String, permission: DictationPlan.Permission) {
            started++
            state.value = if (canListen && permission == DictationPlan.Permission.Granted) DictationEngine.State.Listening else DictationEngine.State.Unavailable("no")
        }
        override fun stop() { stopped++; state.value = DictationEngine.State.Idle }
        override fun clearHint() { if (state.value is DictationEngine.State.Unavailable) state.value = DictationEngine.State.Idle }
        override fun release() { released++; state.value = DictationEngine.State.Idle }
    }

    private class FakeRecorder(var canStart: Boolean = true, var bytes: Int = 2000, var usable: Boolean = true) : ClipRecorder {
        var file: File? = null; var aborted = false
        override fun start(file: File): Boolean { if (!canStart) return false; this.file = file; return true }
        override fun stop(): Boolean { file!!.writeBytes(ByteArray(bytes) { 1 }); return usable }
        override fun abort() { aborted = true }
    }

    private class FakeService(var result: DictateResult) : DictationService {
        val clips = mutableListOf<DictationClip>(); var gate: kotlinx.coroutines.CompletableDeferred<Unit>? = null
        override suspend fun dictate(clip: DictationClip): DictateResult { clips += clip; gate?.await(); return result }
    }

    private val tmp = java.nio.file.Files.createTempDirectory("dict").toFile()
    private class Rig(val engine: BetterDictationEngine, val native: FakeNative, val rec: FakeRecorder, val svc: FakeService, val field: Field, val scope: TestScope, val clock: LongArray)
    private class Field { var text = "" }

    private fun rig(
        caps: DictationCaps? = DictationCaps(premium = true, available = true), preferred: Boolean = true, service: FakeService? = FakeService(DictateResult.Success(DictationAnswer(ID1, "Better words"))),
        rec: FakeRecorder = FakeRecorder(), native: FakeNative = FakeNative(),
    ): Rig {
        val scope = TestScope(UnconfinedTestDispatcher())
        val clock = longArrayOf(0L)
        val field = Field()
        val e = BetterDictationEngine(native, rec, scope, { tmp }, { service }, { caps }, { preferred }, { "es" }, { clock[0] }, io = UnconfinedTestDispatcher(scope.testScheduler))
        e.onText = { field.text = it }; e.textProvider = { field.text }
        return Rig(e, native, rec, service ?: FakeService(DictateResult.Failure(BetterFailure.Failed)), field, scope, clock)
    }

    private fun Rig.dictate(typedFirst: String = "", preview: String = "worse wordz") {
        field.text = typedFirst
        engine.start(typedFirst, DictationPlan.Permission.Granted)
        field.text = DictationTextCompose(typedFirst, preview); native.onText?.invoke(field.text)
    }
    private fun DictationTextCompose(base: String, seg: String) = com.videomk.app.core.DictationText.compose(base, seg)

    @Test fun `stop uploads the clip and the better text replaces the preview on top of the typed text`() {
        val r = rig()
        r.dictate("Please make it fun.")
        assertTrue(r.engine.isListening); assertEquals(DictationEngine.State.Listening, r.engine.state.value)
        r.clock[0] = 12_345
        r.engine.stop()
        assertEquals("Please make it fun. Better words", r.field.text)
        val clip = r.svc.clips.single()
        assertEquals(listOf("es"), clip.languages); assertEquals("Please make it fun.", clip.prompt); assertEquals(12.3, clip.seconds, 0.1); assertEquals(2000, clip.audio.size)
        assertEquals(listOf(ID1), r.engine.ids.list)
        assertFalse(r.engine.working.value); assertNull(r.engine.note.value)
        assertTrue("temp file is deleted right after the upload", tmp.listFiles()!!.isEmpty())
        assertTrue(r.native.released > 0)
    }

    @Test fun `the field is read at the end - a hand edit while improving is never overwritten, but the id is kept`() {
        val gate = kotlinx.coroutines.CompletableDeferred<Unit>()
        val svc = FakeService(DictateResult.Success(DictationAnswer(ID1, "Better words"))).also { it.gate = gate }
        val r = rig(service = svc)
        r.dictate()
        r.engine.stop()
        assertTrue(r.engine.working.value)
        r.field.text += " typed"                      // typed while "Improving..."
        gate.complete(Unit)
        assertEquals("worse wordz typed", r.field.text)
        assertEquals(listOf(ID1), r.engine.ids.list)
        assertFalse(r.engine.working.value)
    }

    @Test fun `every error keeps the native text and says the right line`() {
        for ((failure, note) in listOf(BetterFailure.Quota to BetterNote.Quota, BetterFailure.Failed to BetterNote.Failed, BetterFailure.Network to BetterNote.Failed, BetterFailure.BadAudio to BetterNote.Failed,
            BetterFailure.TooLong to BetterNote.Limit, BetterFailure.Plan to null, BetterFailure.Paused to null, BetterFailure.Auth to null)) {
            val r = rig(service = FakeService(DictateResult.Failure(failure)))
            r.dictate(); r.engine.stop()
            assertEquals("$failure", "worse wordz", r.field.text); assertEquals("$failure", note, r.engine.note.value); assertTrue(r.engine.ids.list.isEmpty())
            r.engine.clearNote(); assertNull(r.engine.note.value)
        }
    }

    @Test fun `six minute stop uploads by itself and tells the person`() {
        val r = rig()
        r.dictate()
        r.clock[0] = 361_000
        r.scope.testScheduler.advanceTimeBy(360_001); r.scope.testScheduler.runCurrent()
        assertEquals("Better words", r.field.text)
        assertEquals(BetterNote.Limit, r.engine.note.value)
        assertEquals(360.0, r.svc.clips.single().seconds, 0.0)
        assertFalse(r.engine.isListening)
    }

    @Test fun `a clip over the byte limit is not uploaded and keeps the phone's text`() {
        val r = rig(caps = DictationCaps(premium = true, available = true, maxClipBytes = 1000), rec = FakeRecorder(bytes = 1001))
        r.dictate(); r.engine.stop()
        assertTrue(r.svc.clips.isEmpty()); assertEquals("worse wordz", r.field.text); assertEquals(BetterNote.Failed, r.engine.note.value)
        assertTrue(tmp.listFiles()!!.isEmpty())
    }

    @Test fun `a recorder that cannot start leaves the native engine alone, no crash`() {
        val r = rig(rec = FakeRecorder(canStart = false))
        r.dictate(); assertTrue(r.engine.isListening)
        r.engine.stop()
        assertTrue(r.svc.clips.isEmpty()); assertEquals("worse wordz", r.field.text); assertFalse(r.engine.working.value); assertNull(r.engine.note.value)
        assertEquals(1, r.native.stopped)
    }

    @Test fun `a recorder that throws is the same as one that cannot start`() {
        val boom = object : ClipRecorder { override fun start(file: File): Boolean = throw IllegalStateException("mic busy"); override fun stop() = false; override fun abort() {} }
        val scope = TestScope(UnconfinedTestDispatcher()); val native = FakeNative()
        val e = BetterDictationEngine(native, boom, scope, { tmp }, { FakeService(DictateResult.Failure(BetterFailure.Failed)) }, { DictationCaps(premium = true, available = true) }, { true }, { "en" })
        e.start("", DictationPlan.Permission.Granted)
        assertTrue(e.isListening); assertEquals(1, native.started)
    }

    @Test fun `no live preview still records and the better text is appended`() {
        val r = rig(native = FakeNative().also { it.canListen = false })
        r.field.text = "Intro."
        r.engine.start("Intro.", DictationPlan.Permission.Granted)
        assertTrue(r.engine.isListening); assertEquals(DictationEngine.State.Listening, r.engine.state.value)   // the recorder carries it; the recognizer's complaint is not shown
        r.engine.stop()
        assertEquals("Intro. Better words", r.field.text)
    }

    @Test fun `not offered, switched off or no permission means the native engine only`() {
        for (r in listOf(rig(caps = null), rig(preferred = false), rig(caps = DictationCaps(premium = false, available = false, requiresPlan = "pro")), rig(caps = DictationCaps(premium = true, available = true, paused = true)), rig(service = null))) {
            r.dictate(); assertNull(r.rec.file); r.engine.stop()
            assertTrue(r.svc.clips.isEmpty()); assertEquals("worse wordz", r.field.text); assertNull(r.engine.note.value)
        }
        val r = rig(); r.engine.start("", DictationPlan.Permission.Denied)
        assertNull(r.rec.file); assertTrue(r.engine.state.value is DictationEngine.State.Unavailable)   // the native path explains the denied permission
    }

    @Test fun `abandon throws the clip away and nothing lands afterwards`() {
        val gate = kotlinx.coroutines.CompletableDeferred<Unit>()
        val r = rig(service = FakeService(DictateResult.Success(DictationAnswer(ID1, "Late"))).also { it.gate = gate })
        r.dictate(); r.engine.stop()
        r.engine.abandon(); r.field.text = ""
        gate.complete(Unit)
        assertEquals("", r.field.text); assertTrue(r.engine.ids.list.isEmpty()); assertFalse(r.engine.working.value)
        val r2 = rig(); r2.dictate(); r2.engine.abandon()
        assertTrue(r2.rec.aborted); assertFalse(r2.engine.isListening)
    }

    @Test fun `a second start while improving is ignored`() {
        val gate = kotlinx.coroutines.CompletableDeferred<Unit>()
        val r = rig(service = FakeService(DictateResult.Success(DictationAnswer(ID1, "x"))).also { it.gate = gate })
        r.dictate(); r.engine.stop()
        val before = r.native.started
        r.engine.start("", DictationPlan.Permission.Granted)
        assertEquals(before, r.native.started)
    }

    @Test fun `ids from two dictations are all kept for the next create`() {
        val r = rig()
        r.dictate(); r.engine.stop()
        r.svc.result = DictateResult.Success(DictationAnswer(ID2, "More")); r.dictate(r.field.text, "more wordz"); r.engine.stop()
        assertEquals(listOf(ID1, ID2), r.engine.ids.list)
        r.engine.clearIds(); assertTrue(r.engine.ids.list.isEmpty())
    }

    companion object {
        private const val CAPS = """{"aspects":[{"id":"16:9","label":"Landscape","ready":true}],"resolutions":[{"id":"1080p","label":"1080p"}],"dictation": %D, "lengths":{"min_minutes":1,"max_minutes":5}}"""
    }
}
