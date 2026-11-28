package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import kotlin.coroutines.EmptyCoroutineContext

private fun capsJson(extra: String = "") = Json.parseToJsonElement("""{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}],"video_upload":{"enabled":true,"available":true,"paused":false,"clips_per_day":3,"clips_left_today":3,"clips_per_video":2,"max_bytes":26214400,"used_seconds":5,"formats":["video/mp4","video/quicktime","video/webm"],"api_url":"https://nct71w0g7b.execute-api.eu-west-1.amazonaws.com"$extra}}""").jsonObject
private val CAPS = VideoUploadCaps(true, true, false, 3, 3, 2, 25L * 1024 * 1024, 5, listOf("video/mp4", "video/quicktime", "video/webm"), "https://x.example", null)
/** A cap of 1000 bytes, so the 2 KB test file is "over the limit" without a 25 MB array. */
private val SMALL = CAPS.copy(maxBytes = 1000)
private val BYTES = ByteArray(2048) { it.toByte() }
private fun pick(size: Long? = BYTES.size.toLong(), mime: String? = "video/mp4", bytes: ByteArray = BYTES) = VideoPick("holiday.mp4", mime, size, null) { ByteArrayInputStream(bytes) }
private fun ready(id: String = "c1", useAudio: Boolean = false, audioState: String? = "off") = ClipInfo(id, "ready", useAudio, 5.0, 18.0, true, true, useAudio && audioState == "speech", audioState, 1080, 1920, null, null)

private class FakeClipMedia(var probe: ClipProbe? = ClipProbe(18_000, true, 1080, 1920, byteArrayOf(1)), var trimResult: Boolean = true, var trimmedBytes: Int = 1000) : ClipMedia {
    var trims = 0; var keptAudio: Boolean? = null
    override fun probe(pick: VideoPick) = probe
    override fun trim(src: File, dst: File, seconds: Double, keepAudio: Boolean): Boolean { trims++; keptAudio = keepAudio; if (trimResult) dst.writeBytes(ByteArray(trimmedBytes)); return trimResult }
    override fun thumbnail(file: File): ByteArray? = byteArrayOf(9)
}

private class ScriptedClipApi(var statuses: List<ClipInfo> = listOf(ClipInfo("c1", "analysing", false, null, null, false, false, false, null, null, null, null, null), ready())) : ClipApi {
    var slotError: Exception? = null; var statusError: Exception? = null; var duplicate: ClipInfo? = null
    val created = mutableListOf<Triple<Long, String, Boolean>>(); val hashes = mutableListOf<String?>(); val deleted = mutableListOf<String>(); var analysed = 0; var looks = 0; var left = 2
    override suspend fun createSlot(sizeBytes: Long, contentType: String, useAudio: Boolean, sha256: String?): ClipSlotAnswer {
        slotError?.let { throw it }
        created += Triple(sizeBytes, contentType, useAudio); hashes += sha256
        duplicate?.let { return ClipSlotAnswer.Duplicate(it) }
        return ClipSlotAnswer.Slot("c1", "https://s3.example/in", mapOf("key" to "in/u/c1", "Content-Type" to contentType), left--)
    }
    override suspend fun analyse(id: String): ClipInfo { analysed++; return ClipInfo(id, "analysing", false, null, null, false, false, false, null, null, null, null, null) }
    override suspend fun status(id: String): ClipInfo { statusError?.let { throw it }; return statuses[minOf(looks++, statuses.size - 1)] }
    override suspend fun delete(id: String) { deleted += id }
}

private class RecordingClipUploader(var error: Exception? = null) : ClipUploader {
    val seen = mutableListOf<Triple<Boolean, Long, String>>(); var fields: Map<String, String> = emptyMap()
    override suspend fun upload(url: String, fields: Map<String, String>, contentType: String, file: File, progress: (Long, Long) -> Unit) {
        seen += Triple(file.exists(), file.length(), contentType); this.fields = fields
        progress(file.length() / 2, file.length()); error?.let { throw it }; progress(file.length(), file.length())
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class VideoClipTest {
    private lateinit var root: File
    private var clock = 0L
    private val lists = mutableListOf<List<ClipEntry>>()

    @Before fun setUp() { root = Files.createTempDirectory("clips").toFile().resolve("clips"); clock = 0; lists.clear() }
    @After fun tearDown() { root.parentFile.deleteRecursively() }

    private fun ctl(scope: kotlinx.coroutines.CoroutineScope, api: ClipApi? = ScriptedClipApi(), up: ClipUploader? = RecordingClipUploader(), media: ClipMedia = FakeClipMedia(), caps: VideoUploadCaps = CAPS) =
        ClipController(scope, root, media, onState = { lists += it }, wait = { clock += it }, nowMillis = { clock }, io = EmptyCoroutineContext).also { it.attach(api, up); it.setCaps(caps) }

    private fun TestScope.addAndAnswer(c: ClipController, keep: Boolean, p: VideoPick = pick()): String {
        assertTrue(c.add(p)); advanceUntilIdle()
        val id = c.entries.last().id
        c.answer(id, keep); advanceUntilIdle()
        return id
    }

    // ---- capabilities: where the feature shows

    @Test fun `capabilities carry video_upload only when the server sends it`() {
        assertNull(Capabilities.fromJson(Json.parseToJsonElement("""{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}]}""").jsonObject).videoUpload)
        val v = Capabilities.fromJson(capsJson()).videoUpload!!
        assertEquals(25L * 1024 * 1024, v.maxBytes); assertEquals(2, v.clipsPerVideo); assertEquals(3, v.clipsLeftToday); assertEquals("https://nct71w0g7b.execute-api.eu-west-1.amazonaws.com", v.apiUrl); assertEquals(25, v.maxMb)
        assertEquals(listOf("video/mp4", "video/quicktime", "video/webm"), v.formats)
    }

    @Test fun `the add a video row follows the switches, the plan, the day and the video`() {
        assertEquals(VideoEntry.Hidden, VideoRules.entry(null, null, 0))
        assertEquals(VideoEntry.Hidden, VideoRules.entry(CAPS.copy(enabled = false), null, 0))
        assertEquals(VideoEntry.Enabled, VideoRules.entry(CAPS, null, 0))
        assertEquals(VideoEntry.Disabled(VideoEntry.Reason.Paused), VideoRules.entry(CAPS.copy(available = false, paused = true), null, 0))   // the kill switch: 503 video_upload_paused
        assertEquals(VideoEntry.Disabled(VideoEntry.Reason.DailyLimit), VideoRules.entry(CAPS.copy(clipsLeftToday = 0), null, 0))
        assertEquals(VideoEntry.Disabled(VideoEntry.Reason.DailyLimit), VideoRules.entry(CAPS, 0, 0))   // counted down on this phone as slots are taken
        assertEquals(VideoEntry.Disabled(VideoEntry.Reason.RequiresPlan, "pro"), VideoRules.entry(CAPS.copy(available = false, clipsLeftToday = 0, requiresPlan = "pro"), null, 0))
        assertEquals(VideoEntry.Disabled(VideoEntry.Reason.VideoFull), VideoRules.entry(CAPS, null, 2))
    }

    // ---- the checks on the phone before any upload

    @Test fun `size, type and length are checked first and a big file is cut before it goes up`() {
        assertEquals(ClipDecision.AsIs, VideoRules.decide(5_000_000, "video/mp4", 18_000, CAPS))
        assertEquals(ClipDecision.AsIs, VideoRules.decide(CAPS.maxBytes, "video/quicktime", null, CAPS))
        assertEquals(ClipDecision.AsIs, VideoRules.decide(null, "VIDEO/MP4; codecs=avc1", null, CAPS))   // a provider that gives no size: the copy counts for itself
        assertEquals(ClipDecision.TrimFirst, VideoRules.decide(CAPS.maxBytes + 1, "video/mp4", 30_000, CAPS))
        assertEquals(ClipDecision.TrimFirst, VideoRules.decide(400L * 1024 * 1024, "video/mp4", 90_000, CAPS))
        assertEquals(ClipDecision.Reject(VideoProblem.TooLarge), VideoRules.decide(VideoRules.ABSURD_BYTES + 1, "video/mp4", 30_000, CAPS))
        assertEquals(ClipDecision.Reject(VideoProblem.TooLong), VideoRules.decide(5_000_000, "video/mp4", VideoRules.ABSURD_MILLIS + 1, CAPS))
        assertEquals(ClipDecision.Reject(VideoProblem.BadFile), VideoRules.decide(5_000_000, "image/jpeg", 1000, CAPS))
        assertEquals(ClipDecision.Reject(VideoProblem.BadFile), VideoRules.decide(5_000_000, null, 1000, CAPS))
        assertEquals(ClipDecision.Reject(VideoProblem.BadFile), VideoRules.decide(0, "video/mp4", 1000, CAPS))
        assertNull(VideoRules.afterTrim(1_000_000, CAPS))
        assertEquals(VideoProblem.TooLarge, VideoRules.afterTrim(CAPS.maxBytes + 1, CAPS))
        assertEquals(VideoProblem.TooLarge, VideoRules.afterTrim(null, CAPS))   // the phone could not cut it: blocked with the size message
    }

    @Test fun `the notice always says five seconds and names the length when the file is longer`() {
        assertFalse(VideoRules.notice(4_000).longer); assertFalse(VideoRules.notice(5_200).longer); assertFalse(VideoRules.notice(null).longer)
        assertEquals(18, VideoRules.notice(18_000).longerSeconds); assertEquals(6, VideoRules.notice(5_400).longerSeconds); assertEquals(19, VideoRules.notice(18_600).longerSeconds)
    }

    // ---- request building

    @Test fun `the create body has exactly the wire fields and the choice cannot be left empty`() {
        val o = ClipRequests.createBody(123, "video/mp4", true, "ab12")
        assertEquals(setOf("size_bytes", "content_type", "use_audio", "sha256"), o.keys)
        assertEquals("123", o["size_bytes"]!!.jsonPrimitive.content); assertEquals("true", o["use_audio"]!!.jsonPrimitive.content)
        assertFalse(ClipRequests.createBody(1, "video/mp4", false, null).containsKey("sha256"))
        assertEquals("false", ClipRequests.createBody(1, "video/mp4", false, null)["use_audio"]!!.jsonPrimitive.content)
    }

    @Test fun `video_assets carries ready ids only, in order, at most the plan allows`() {
        fun e(id: String, phase: ClipPhase, sid: String?) = ClipEntry(id, phase = phase, serverId = sid)
        val list = listOf(e("a", ClipPhase.Ready, "s1"), e("b", ClipPhase.Analysing(), "s2"), e("c", ClipPhase.Ready, "s3"), e("d", ClipPhase.Failed(ClipFailure(VideoProblem.Rejected)), "s4"), e("e", ClipPhase.Ready, "s5"), e("f", ClipPhase.Uploading(1, 2), null))
        assertEquals(listOf("s1", "s3"), ClipRequests.videoAssets(list, 2))
        assertEquals(listOf("s1", "s3", "s5"), ClipRequests.videoAssets(list, 6))
        assertEquals(emptyList<String>(), ClipRequests.videoAssets(emptyList(), 2))
    }

    @Test fun `generate sends video_assets only when there are clips`() = runBlocking {
        val server = MockWebServer().apply { start() }
        try {
            val api = ApiClient(configFor(server), FixedAuth())
            server.enqueue(json(body = """{"video_id":"v1"}""")); server.enqueue(json(body = """{"video_id":"v2"}"""))
            api.startVideo("A story about bees and honey in the garden", "req-1", clipIds = listOf("s1", "s3"))
            api.startVideo("A story about bees and honey in the garden", "req-2")
            val a = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject; val b = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
            assertEquals(listOf("s1", "s3"), a["video_assets"]!!.jsonArray.map { it.jsonPrimitive.content }); assertEquals("req-1", a["client_request_id"]!!.jsonPrimitive.content)
            assertFalse(b.containsKey("video_assets"))
        } finally { server.close() }
    }

    // ---- the wire: another base, same token, the server's codes

    @Test fun `clip calls go to the clip api with the same token and map the live API's shapes`() = runBlocking {
        val main = MockWebServer().apply { start() }; val clips = MockWebServer().apply { start() }
        try {
            val client = ApiClient(configFor(main), FixedAuth(), appVersion = "9.9")
            val api = ApiClipApi(client, clips.url("/"))
            clips.enqueue(json(201, """{"id":"c9","upload":{"url":"https://s3.example/b","fields":{"key":"in/u/c9","Content-Type":"video/mp4","policy":"p"}},"expires_in":900,"max_bytes":26214400,"used_seconds":5,"use_audio":true,"clips_left_today":2}"""))
            val slot = api.createSlot(2048, "video/mp4", true, "deadbeef") as ClipSlotAnswer.Slot
            assertEquals("c9", slot.id); assertEquals(2, slot.clipsLeftToday); assertEquals(listOf("key", "Content-Type", "policy"), slot.fields.keys.toList())   // the server's order is kept
            val r = clips.takeRequest()
            assertEquals("/users/user-1/video-uploads", r.url.encodedPath); assertEquals("POST", r.method); assertEquals("Bearer tok-abc", r.headers["Authorization"]); assertEquals("9.9", r.headers["X-App-Version"])
            assertEquals(0, main.requestCount)
            val body = Json.parseToJsonElement(r.body!!.utf8()).jsonObject
            assertEquals(setOf("size_bytes", "content_type", "use_audio", "sha256"), body.keys)
            clips.enqueue(json(200, """{"duplicate":true,"clip":{"id":"c1","status":"ready","ready":true,"use_audio":false,"width":1920,"height":1080,"duration":5.0,"source_duration":5.0,"trimmed":false,"has_audio":false,"audio_used":false,"audio_state":"none"}}"""))
            val dup = api.createSlot(10, "video/mp4", false, "aa") as ClipSlotAnswer.Duplicate
            assertTrue(dup.clip.ready); assertEquals(1920, dup.clip.width)
            clips.enqueue(json(202, """{"clip":{"id":"c9","status":"analysing","ready":false,"use_audio":true}}""")); assertEquals("analysing", api.analyse("c9").status)
            clips.takeRequest(); assertEquals("/users/user-1/video-uploads/c9/analyse", clips.takeRequest().url.encodedPath)
            clips.enqueue(json(200, """{"clip":{"id":"c9","status":"rejected","ready":false,"use_audio":true,"code":"rejected","message":"x"}}""")); assertEquals("rejected", api.status("c9").status)
            clips.takeRequest(); clips.enqueue(MockResponse204()); api.delete("c9"); assertEquals("DELETE", clips.takeRequest().method)
        } finally { main.close(); clips.close() }
    }

    private fun MockResponse204() = mockwebserver3.MockResponse.Builder().code(204).build()

    @Test fun `every refusal of the clip api becomes the right problem`() = runBlocking {
        val clips = MockWebServer().apply { start() }
        try {
            val api = ApiClipApi(ApiClient(configFor(clips), FixedAuth()), clips.url("/"))
            suspend fun refuse(code: Int, body: String): ClipRefusal { clips.enqueue(json(code, body)); try { api.createSlot(1, "video/mp4", false, null); error("no refusal") } catch (e: ClipRefusal) { return e } }
            assertEquals(VideoProblem.Paused, VideoRules.failureOf(refuse(503, """{"code":"video_upload_paused","message":"m"}""")).problem)
            assertEquals(VideoProblem.DailyLimit, VideoRules.failureOf(refuse(429, """{"code":"video_upload_quota","message":"m","can_upgrade":true}""")).problem)
            assertEquals(VideoProblem.Plan, VideoRules.failureOf(refuse(403, """{"code":"video_upload_plan","message":"Needs Pro"}""")).problem)
            assertEquals("Needs Pro", VideoRules.failureOf(refuse(403, """{"code":"video_upload_plan","message":"Needs Pro"}""")).serverMessage)
            assertEquals(VideoProblem.TooLarge, VideoRules.failureOf(refuse(413, """{"code":"too_big","message":"m"}""")).problem)
            assertEquals(VideoProblem.BadFile, VideoRules.failureOf(refuse(400, """{"code":"bad_request","message":"m"}""")).problem)
            assertEquals(VideoProblem.Rejected, VideoRules.failureOf(refuse(400, """{"code":"rejected","message":"m"}""")).problem)
            val safety = VideoRules.failureOf(refuse(429, """{"status":"paused","message":"Your account is paused for a while.","retry_after":3600}"""))
            assertEquals("Your account is paused for a while.", safety.body(CAPS))   // the same account message as video creation
            assertEquals(VideoProblem.Paused, VideoRules.failureOf(refuse(503, "")).problem)   // a bare gateway answer still maps by status
        } finally { clips.close() }
    }

    // ---- every state of the journey (with fakes)

    @Test fun `a clip with sound waits for the answer, then uploads with progress, is checked and ready`() = runTest {
        val api = ScriptedClipApi(); val up = RecordingClipUploader()
        val c = ctl(this, api, up)
        assertTrue(c.add(pick())); advanceUntilIdle()
        val asking = c.entries.single()
        assertEquals(ClipPhase.AskSound, asking.phase); assertNull(asking.useAudio)   // nothing is chosen for the person
        assertEquals(0, api.created.size)   // nothing leaves the phone before the answer
        assertEquals(18_000L, asking.durationMs); assertTrue(asking.longer)
        c.answer(asking.id, keepSound = true); advanceUntilIdle()
        val e = c.entries.single()
        assertEquals(ClipPhase.Ready, e.phase); assertEquals("c1", e.serverId); assertEquals(listOf("c1"), c.readyIds)
        assertEquals(Triple(BYTES.size.toLong(), "video/mp4", true), api.created.single())
        assertEquals(64, api.hashes.single()!!.length)
        assertEquals(listOf(Triple(true, BYTES.size.toLong(), "video/mp4")), up.seen)
        assertEquals(1, api.analysed)
        val kinds = lists.map { it.single().phase::class.simpleName }
        for ((a, b) in listOf("Inspecting" to "AskSound", "AskSound" to "Preparing", "Preparing" to "Uploading", "Uploading" to "Analysing", "Analysing" to "Ready")) assertTrue("$a before $b", kinds.indexOf(a) < kinds.indexOf(b))
        assertTrue(lists.map { it.single().phase }.filterIsInstance<ClipPhase.Uploading>().any { it.percent in 40..60 })
        assertEquals(2, c.leftToday)   // the slot answer says how many are left today
    }

    @Test fun `a file without sound is never asked about sound and goes up silent`() = runTest {
        val api = ScriptedClipApi()
        val c = ctl(this, api, media = FakeClipMedia(ClipProbe(4_000, false, 1920, 1080, null)))
        assertTrue(c.add(pick())); advanceUntilIdle()
        assertEquals(ClipPhase.Ready, c.entries.single().phase)
        assertEquals(false, api.created.single().third)
    }

    @Test fun `no sound is sent as no sound`() = runTest {
        val api = ScriptedClipApi(); ctl(this, api).let { addAndAnswer(it, keep = false) }
        assertEquals(false, api.created.single().third)
    }

    @Test fun `the sheet cannot be skipped - closing it without an answer drops the pick`() = runTest {
        val api = ScriptedClipApi(); val c = ctl(this, api)
        assertTrue(c.add(pick())); advanceUntilIdle()
        c.dismissSheet(c.entries.single().id); advanceUntilIdle()
        assertTrue(c.entries.isEmpty()); assertEquals(0, api.created.size); assertEquals(0, c.filesOnDisk())
    }

    @Test fun `an already ready file is ready at once without a slot or an upload (duplicate)`() = runTest {
        val api = ScriptedClipApi().apply { duplicate = ready("c7") }; val up = RecordingClipUploader()
        val c = ctl(this, api, up); addAndAnswer(c, keep = false)
        assertEquals(ClipPhase.Ready, c.entries.single().phase); assertEquals("c7", c.entries.single().serverId)
        assertTrue(up.seen.isEmpty()); assertEquals(0, api.analysed); assertEquals(3, c.leftToday)   // a duplicate takes no slot
    }

    @Test fun `a file over the limit is cut to the first seconds on the phone before upload`() = runTest {
        val media = FakeClipMedia(trimmedBytes = 600); val api = ScriptedClipApi(); val up = RecordingClipUploader()
        val c = ctl(this, api, up, media, caps = SMALL)
        addAndAnswer(c, keep = false)
        assertEquals(1, media.trims); assertEquals(false, media.keptAudio)   // no sound chosen: the cut drops it too
        assertEquals(600L, api.created.single().first); assertEquals("video/mp4", api.created.single().second)
        assertEquals(listOf(Triple(true, 600L, "video/mp4")), up.seen)   // the trimmed copy goes up, not the original
        assertEquals(ClipPhase.Ready, c.entries.single().phase); assertTrue(c.entries.single().trimmedOnPhone)
        assertEquals(1, c.filesOnDisk())   // only the cut copy is on disk; the original was deleted
    }

    @Test fun `when the phone cannot cut a big file it is blocked with the size message and nothing is sent`() = runTest {
        val media = FakeClipMedia(trimResult = false); val api = ScriptedClipApi()
        val c = ctl(this, api, media = media, caps = SMALL)
        addAndAnswer(c, keep = true)
        val f = (c.entries.single().phase as ClipPhase.Failed).failure
        assertEquals(VideoProblem.TooLarge, f.problem); assertEquals("The limit is 25 MB. Try a shorter clip.", f.body(CAPS)); assertEquals(0, api.created.size); assertEquals(0, c.filesOnDisk())
        assertEquals(true, media.keptAudio)   // sound was chosen: the cut keeps it
    }

    @Test fun `a cut that is still too big is blocked too`() = runTest {
        val api = ScriptedClipApi(); val c = ctl(this, api, media = FakeClipMedia(trimmedBytes = (SMALL.maxBytes + 1).toInt()), caps = SMALL)
        addAndAnswer(c, keep = false)
        assertEquals(VideoProblem.TooLarge, (c.entries.single().phase as ClipPhase.Failed).failure.problem)
    }

    @Test fun `an absurd original or length is refused before anything is copied`() = runTest {
        val c = ctl(this, media = FakeClipMedia(ClipProbe(700_000, true, 1920, 1080, null)))
        assertTrue(c.add(pick())); advanceUntilIdle()
        assertEquals(VideoProblem.TooLong, (c.entries.single().phase as ClipPhase.Failed).failure.problem); assertEquals(0, c.filesOnDisk())
        val c2 = ctl(this)
        assertTrue(c2.add(pick(size = VideoRules.ABSURD_BYTES + 1))); advanceUntilIdle()
        assertEquals(VideoProblem.TooLarge, (c2.entries.single().phase as ClipPhase.Failed).failure.problem)
        val c3 = ctl(this); assertTrue(c3.add(pick(mime = "image/png"))); advanceUntilIdle()
        assertEquals(VideoProblem.BadFile, (c3.entries.single().phase as ClipPhase.Failed).failure.problem)
    }

    @Test fun `a refused clip says only the generic words and offers no retry`() = runTest {
        val api = ScriptedClipApi(listOf(ClipInfo("c1", "rejected", false, null, null, false, false, false, null, null, null, "rejected", "internal detail")))
        val c = ctl(this, api); addAndAnswer(c, keep = false)
        val f = (c.entries.single().phase as ClipPhase.Failed).failure
        assertEquals(VideoProblem.Rejected, f.problem); assertFalse(f.problem.retry)
        assertEquals("We could not use this clip", f.title()); assertEquals("Please choose a different one.", f.body(CAPS))
        assertFalse((f.title() + f.body(CAPS)).contains("internal detail"))
        assertTrue(c.readyIds.isEmpty())
    }

    @Test fun `a check that could not run can be tried again with a fresh upload`() = runTest {
        val api = ScriptedClipApi(listOf(ClipInfo("c1", "failed", false, null, null, false, false, false, null, null, null, "check_failed", "x")))
        val up = RecordingClipUploader()
        val c = ctl(this, api, up); val id = addAndAnswer(c, keep = false)
        assertEquals(VideoProblem.CheckFailed, (c.entries.single().phase as ClipPhase.Failed).failure.problem)
        api.statuses = listOf(ready("c2")); api.looks = 0
        c.retry(id); advanceUntilIdle()
        assertEquals(ClipPhase.Ready, c.entries.single().phase); assertEquals(2, up.seen.size); assertEquals(listOf("c1"), api.deleted)
    }

    @Test fun `a lost connection during the upload is a retry with the same private copy`() = runTest {
        val up = RecordingClipUploader(error = ApiError.Network); val api = ScriptedClipApi()
        val c = ctl(this, api, up); val id = addAndAnswer(c, keep = false)
        assertEquals(VideoProblem.Offline, (c.entries.single().phase as ClipPhase.Failed).failure.problem)
        assertEquals("Check your connection and try again.", (c.entries.single().phase as ClipPhase.Failed).failure.body(CAPS))
        assertEquals(1, c.filesOnDisk())   // still here for the retry
        up.error = null; api.statuses = listOf(ready("c1")); api.looks = 0
        c.retry(id); advanceUntilIdle()
        assertEquals(ClipPhase.Ready, c.entries.single().phase)
    }

    @Test fun `quota, pause and plan refusals at the door fail the clip with their own message`() = runTest {
        for ((e, want) in listOf(ClipRefusal(429, "video_upload_quota", "m", true) to VideoProblem.DailyLimit, ClipRefusal(503, "video_upload_paused", "m", false) to VideoProblem.Paused, ClipRefusal(403, "video_upload_plan", "Pro needed", false) to VideoProblem.Plan)) {
            val api = ScriptedClipApi().apply { slotError = e }
            val c = ctl(this, api); addAndAnswer(c, keep = false)
            assertEquals(want, (c.entries.single().phase as ClipPhase.Failed).failure.problem); assertFalse(want.retry)
        }
    }

    @Test fun `polling follows 1_5 s then 3 s, says taking longer after 90 s, and stops at 5 minutes`() = runTest {
        assertEquals(1500, VideoRules.pollIntervalMillis(0)); assertEquals(1500, VideoRules.pollIntervalMillis(19_999)); assertEquals(3000, VideoRules.pollIntervalMillis(20_000))
        val still = ClipInfo("c1", "analysing", false, null, null, false, false, false, null, null, null, null, null)
        val api = ScriptedClipApi(listOf(still)); val c = ctl(this, api); val id = addAndAnswer(c, keep = false)
        val f = (c.entries.single().phase as ClipPhase.Failed).failure
        assertEquals(VideoProblem.Stalled, f.problem)
        assertTrue(lists.any { l -> (l.single().phase as? ClipPhase.Analysing)?.slow == true })   // "taking longer than usual" came first
        assertTrue(clock >= VideoRules.GIVE_UP_MILLIS)
        api.statuses = listOf(ready("c1")); api.looks = 0
        c.keepWaiting(id); advanceUntilIdle()
        assertEquals(ClipPhase.Ready, c.entries.single().phase)
    }

    @Test fun `five failed looks in a row stop the wait`() = runTest {
        val api = ScriptedClipApi().apply { statusError = ApiError.Network }
        val c = ctl(this, api); addAndAnswer(c, keep = false)
        assertEquals(VideoProblem.Stalled, (c.entries.single().phase as ClipPhase.Failed).failure.problem)
    }

    @Test fun `removing a clip stops it, deletes the private copy and asks the server to delete the record`() = runTest {
        val api = ScriptedClipApi(); val c = ctl(this, api); val id = addAndAnswer(c, keep = false)
        assertEquals(1, c.filesOnDisk())
        c.remove(id); advanceUntilIdle()
        assertTrue(c.entries.isEmpty()); assertEquals(0, c.filesOnDisk()); assertEquals(listOf("c1"), api.deleted); assertTrue(c.readyIds.isEmpty())
    }

    @Test fun `changing the sound on a ready clip makes it again with the other choice`() = runTest {
        val api = ScriptedClipApi(); val c = ctl(this, api); val id = addAndAnswer(c, keep = false)
        api.statuses = listOf(ready("c2", useAudio = true, audioState = "speech")); api.looks = 0
        c.askAgain(id); assertEquals(ClipPhase.AskSound, c.entries.single().phase)
        c.answer(id, keepSound = true); advanceUntilIdle()
        assertEquals(listOf(false, true), api.created.map { it.third }); assertEquals(listOf("c1"), api.deleted)
        assertEquals(ClipPhase.Ready, c.entries.single().phase); assertTrue(c.entries.single().soundOn)
        c.askAgain(id); c.dismissSheet(id); assertEquals(ClipPhase.Ready, c.entries.single().phase)   // closing the sheet on a ready clip keeps it
    }

    @Test fun `a clip whose sound could not be used says so and stays usable`() {
        val info = ready("c1", useAudio = true, audioState = "unscreened")
        assertTrue(info.soundDropped); assertFalse(info.audioUsed)
        assertFalse(ready("c1", useAudio = true, audioState = "speech").soundDropped)
        assertFalse(ready("c1", useAudio = false).soundDropped)
        assertEquals("We used your clip without its sound.", Txt.s(com.videomk.app.R.string.vclip_status_dropped))
    }

    @Test fun `the video holds at most the plan's clips, and a failed one does not count`() = runTest {
        val c = ctl(this, caps = CAPS.copy(clipsPerVideo = 1), media = FakeClipMedia(ClipProbe(3_000, false, 100, 100, null)))
        assertTrue(c.add(pick())); advanceUntilIdle()
        assertFalse(c.add(pick())); assertEquals(1, c.entries.size)
        assertEquals(0, c.vacancies)
        val bad = ctl(this, caps = CAPS.copy(clipsPerVideo = 1)); assertTrue(bad.add(pick(mime = "image/png"))); advanceUntilIdle()
        assertTrue(bad.add(pick(mime = "image/png")))   // the failed one does not hold the place
    }

    @Test fun `after a video is started the local copies go and the list is empty`() = runTest {
        val c = ctl(this); addAndAnswer(c, keep = false)
        c.clearAfterSend(); assertTrue(c.entries.isEmpty()); assertEquals(0, c.filesOnDisk())
    }

    @Test fun `no api means a calm failure, never a crash`() = runTest {
        val c = ctl(this, api = null); addAndAnswer(c, keep = false)
        assertEquals(VideoProblem.Other, (c.entries.single().phase as ClipPhase.Failed).failure.problem)
    }

    // ---- the words, in both languages

    @Test fun `every problem has its title and body in English and Spanish`() {
        val old = Txt.provider
        try {
            for (tag in listOf("en", "es")) {
                Txt.provider = JvmStringProvider(tag)
                val titles = HashSet<String>()
                for (p in VideoProblem.entries) { val f = ClipFailure(p); assertTrue("$tag ${p.name}", f.title().isNotBlank() && f.body(CAPS).isNotBlank() && titles.add(f.title())) }
            }
            Txt.provider = JvmStringProvider("es")
            assertEquals("Ese clip es demasiado grande", ClipFailure(VideoProblem.TooLarge).title())
            assertEquals("Solo se usan los primeros 5 segundos de un clip.", Txt.s(com.videomk.app.R.string.vclip_notice_first))
        } finally { Txt.provider = old }
    }

    @Test fun `limit words`() {
        assertEquals("2 clips per video", Txt.n(com.videomk.app.R.plurals.vclip_count_caption, 2, 2))
        assertEquals("Your clip is 18 seconds. We will use the first 5.", Txt.s(com.videomk.app.R.string.vclip_notice_longer, 18))
        assertEquals("Your clips are used for up to 5 seconds each, where your story talks about them.", Txt.s(com.videomk.app.R.string.vclip_usage_note))
    }
}
