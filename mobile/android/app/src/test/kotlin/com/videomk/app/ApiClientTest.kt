package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.ApiError
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.EditOp
import com.videomk.app.core.RenderMode
import com.videomk.app.core.VideoLook
import com.videomk.app.core.VideoStatus
import kotlinx.coroutines.runBlocking
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
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class ApiClientTest {
    private lateinit var server: MockWebServer
    private lateinit var api: ApiClient

    @Before fun setUp() {
        server = MockWebServer().apply { start() }
        api = ApiClient(configFor(server), FixedAuth(), appVersion = "9.9", region = { "es" }, timeZone = { "Europe/Madrid" })
    }

    @After fun tearDown() { server.close() }

    private fun <T> expectError(expected: ApiError, block: suspend () -> T) {
        try { runBlocking { block() }; fail("expected $expected") } catch (e: ApiError) { assertEquals(expected, e) }
    }

    @Test fun `every request carries the bearer token and the platform, version, timezone and region headers`() = runBlocking {
        server.enqueue(json(body = """{"items":[]}"""))
        api.listVideos()
        val r = server.takeRequest()
        assertEquals("GET", r.method)
        assertEquals("/prod/users/user-1/videos", r.url.encodedPath)
        assertEquals("Bearer tok-abc", r.headers["Authorization"])
        assertEquals("android", r.headers["X-Platform"])
        assertEquals("9.9", r.headers["X-App-Version"])
        assertEquals("Europe/Madrid", r.headers["X-Timezone"])
        assertEquals("ES", r.headers["X-Region"])
    }

    @Test fun `region header is left out when the device has no valid region`() = runBlocking {
        val noRegion = ApiClient(configFor(server), FixedAuth(), region = { null })
        server.enqueue(json(body = """{"items":[]}"""))
        noRegion.listVideos()
        assertNull(server.takeRequest().headers["X-Region"])
        val bad = ApiClient(configFor(server), FixedAuth(), region = { "XYZ" })
        server.enqueue(json(body = """{"items":[]}"""))
        bad.listVideos()
        assertNull(server.takeRequest().headers["X-Region"])
    }

    @Test fun `list videos maps server statuses and tolerates missing fields`() = runBlocking {
        server.enqueue(json(body = """{"items":[
            {"video_id":"a","status":"COMPLETE","title":"Clouds","duration_s":95.5,"created_at":"2026-11-24T10:00:00Z","video_url":"https://x/v.mp4","preview_gif_url":"https://x/p.gif","editable":true},
            {"video_id":"b","status":"RENDERING"},
            {"video_id":"c","status":"REJECTED","reject_reason":"English and Spanish only"},
            {"video_id":"d","status":"EDIT_FAILED"},
            {"video_id":"e","status":"SOMETHING_NEW"},
            {"no_id":true}
        ]}"""))
        val items = api.listVideos()
        assertEquals(listOf("a", "b", "c", "d", "e"), items.map { it.id })   // a malformed row is skipped, not fatal
        assertEquals(VideoStatus.Complete, items[0].status)
        assertEquals("Clouds", items[0].title)
        assertEquals(95.5, items[0].durationSeconds!!, 0.001)
        assertTrue(items[0].editable)
        assertNotNull(items[0].createdAt)
        assertEquals(VideoStatus.Running(VideoStatus.Stage.Rendering), items[1].status)
        assertEquals("Untitled video", items[1].displayTitle)
        assertFalse(items[1].editable)
        assertEquals(VideoStatus.Rejected, items[2].status)
        assertEquals("English and Spanish only", items[2].rejectReason)
        assertEquals(VideoStatus.Failed, items[3].status)
        assertEquals(VideoStatus.Running(VideoStatus.Stage.Starting), items[4].status)
    }

    @Test fun `start generation sends the normalized brief, idempotency key, minutes, look and media`() = runBlocking {
        server.enqueue(json(body = """{"video_id":"v-1"}"""))
        val id = api.startGeneration("  Explain   rainbows\n in simple terms ", "req-1", CreateOptions(minutes = 1.0, look = VideoLook.Paper), listOf("m1", "m2"))
        assertEquals("v-1", id)
        val r = server.takeRequest()
        assertEquals("POST", r.method)
        assertEquals("/prod/users/user-1/videos/generate", r.url.encodedPath)
        assertEquals("application/json", r.headers["Content-Type"]?.substringBefore(";"))
        val body = Json.parseToJsonElement(r.body!!.utf8()).jsonObject
        assertEquals("Explain rainbows in simple terms", body["prompt"]!!.jsonPrimitive.content)
        assertEquals("req-1", body["client_request_id"]!!.jsonPrimitive.content)
        assertEquals(1.0, body["target_minutes"]!!.jsonPrimitive.content.toDouble(), 0.0)
        assertEquals("paper", body["theme"]!!.jsonPrimitive.content)
        assertEquals(listOf("m1", "m2"), body["media"]!!.jsonArray.map { it.jsonPrimitive.content })
    }

    @Test fun `start generation leaves out media and theme when there are none`() = runBlocking {
        server.enqueue(json(body = """{"video_id":"v-2"}"""))
        api.startGeneration("A visual tour of Paris", "req-2")
        val body = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertFalse("media" in body)
        assertFalse("theme" in body)
        assertEquals(3.0, body["target_minutes"]!!.jsonPrimitive.content.toDouble(), 0.0)
    }

    @Test fun `subtitles are only sent when the creator turns them off`() = runBlocking {
        server.enqueue(json(body = """{"video_id":"v-3"}"""))
        api.startGeneration("A day out with the family", "r1", CreateOptions(captions = false))
        assertEquals("false", Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject["captions"]!!.jsonPrimitive.content)
        server.enqueue(json(body = """{"video_id":"v-4"}"""))
        api.startGeneration("A day out with the family", "r2", CreateOptions())
        assertFalse("captions" in Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject)   // on is the server default
    }

    @Test fun `playback returns the url and description, and not-ready carries the status`() = runBlocking {
        server.enqueue(json(body = """{"url":"https://s3/v.mp4","description":"Credits"}"""))
        val p = api.playback("v-1")
        assertEquals("https://s3/v.mp4", p.url)
        assertEquals("Credits", p.description)
        assertEquals("/prod/users/user-1/videos/v-1", server.takeRequest().url.encodedPath)
        server.enqueue(json(409, """{"message":"not ready","status":"PLOT_CREATION"}"""))
        expectError(ApiError.NotReady(VideoStatus.Running(VideoStatus.Stage.Writing))) { api.playback("v-1") }
    }

    @Test fun `http errors map to typed errors`() {
        server.enqueue(json(401, "{}")); expectError(ApiError.Unauthorized) { api.wallet() }
        server.enqueue(json(403, "{}")); expectError(ApiError.Unauthorized) { api.wallet() }
        server.enqueue(json(400, """{"message":"Brief too short"}""")); expectError(ApiError.Invalid("Brief too short")) { api.wallet() }
        server.enqueue(json(400, "not json")); expectError(ApiError.Invalid("That brief can't be used.")) { api.wallet() }
        server.enqueue(json(402, """{"balance":1,"needed":3}""")); expectError(ApiError.InsufficientCredits(1, 3)) { api.wallet() }
        server.enqueue(json(402, "{}")); expectError(ApiError.InsufficientCredits(0, 1)) { api.wallet() }
        server.enqueue(json(429, """{"message":"Daily limit"}""")); expectError(ApiError.Quota("Daily limit")) { api.wallet() }
        server.enqueue(json(429, "{}")); expectError(ApiError.Quota("You've reached today's limit. Try again tomorrow.")) { api.wallet() }
        server.enqueue(json(500, "oops")); expectError(ApiError.Server) { api.wallet() }
        server.enqueue(json(200, "this is not json")); expectError(ApiError.Server) { api.wallet() }
        server.enqueue(json(200, """{"nobalance":1}""")); expectError(ApiError.Server) { api.wallet() }
    }

    @Test fun `editor conflicts are conflicts only on editor calls`() {
        server.enqueue(json(409, """{"message":"Changed since you loaded it"}"""))
        expectError(ApiError.Conflict("Changed since you loaded it")) { api.editorSnapshot("v-1") }
        server.enqueue(json(409, "{}"))
        expectError(ApiError.Conflict("This video changed. Reload to continue.")) { api.applyEdits("v-1", 3, emptyList(), RenderMode.Preview) }
        server.enqueue(json(409, """{"status":"RENDERING"}"""))
        expectError(ApiError.NotReady(VideoStatus.Running(VideoStatus.Stage.Rendering))) { api.playback("v-1") }
    }

    @Test fun `a dropped connection is a network error and messages are human`() {
        server.close()   // nothing is listening: the connection is refused
        expectError(ApiError.Network) { api.wallet() }
        assertTrue(ApiError.Network.message.contains("Check your connection"))
        assertEquals("This video needs 2 credits and you have 1.", ApiError.InsufficientCredits(1, 2).message)
        assertEquals("This video needs 1 credit and you have 0.", ApiError.InsufficientCredits(0, 1).message)
    }

    @Test fun `apply edits sends base revision, operations and mode`() = runBlocking {
        server.enqueue(json(body = """{"rev":4}"""))
        val rev = api.applyEdits("v-1", 3, listOf(EditOp.SetNarration("b1", "Hello there friends"), EditOp.PickImage("b2", "unsplash:xyz"), EditOp.Delete("b3"), EditOp.Move("b4", 0), EditOp.SetTitle("New")), RenderMode.Final)
        assertEquals(4, rev)
        val r = server.takeRequest()
        assertEquals("/prod/users/user-1/videos/v-1/edits", r.url.encodedPath)
        val body = Json.parseToJsonElement(r.body!!.utf8()).jsonObject
        assertEquals(3, body["base_rev"]!!.jsonPrimitive.content.toInt())
        assertEquals("final", body["mode"]!!.jsonPrimitive.content)
        val ops = body["ops"]!!.jsonArray.map { it.jsonObject }
        assertEquals(listOf("set_narration", "pick_image", "delete", "move", "set_meta"), ops.map { it["op"]!!.jsonPrimitive.content })
        assertEquals("unsplash:xyz", ops[1]["candidate"]!!.jsonPrimitive.content)
        assertEquals(0, ops[3]["to"]!!.jsonPrimitive.content.toInt())
        assertEquals("New", ops[4]["title"]!!.jsonPrimitive.content)
    }

    @Test fun `wallet decodes buckets, rules and the unlimited flag`() = runBlocking {
        server.enqueue(json(body = """{"balance":6,"unlimited":false,"next_daily_at":1788000000,"rules":{"daily":2,"signup":5},
            "buckets":[{"kind":"daily","remaining":1,"expires_at":1787990000},{"kind":"signup","remaining":5},{"kind":"weird","remaining":0}]}"""))
        val w = api.wallet()
        assertEquals(6, w.balance)
        assertEquals(2, w.dailyCredits)
        assertEquals(3, w.buckets.size)
        assertEquals(com.videomk.app.core.WalletBucket.Kind.Daily, w.buckets[0].kind)
        assertNotNull(w.buckets[0].expiresAt)
        assertNull(w.buckets[1].expiresAt)
        assertEquals(com.videomk.app.core.WalletBucket.Kind.Other, w.buckets[2].kind)
        assertNotNull(w.nextFreeAt)
        assertTrue(w.canAfford(6)); assertFalse(w.canAfford(7))
        server.enqueue(json(body = """{"balance":999,"unlimited":true}"""))
        assertTrue(api.wallet().canAfford(1000))
    }
}
