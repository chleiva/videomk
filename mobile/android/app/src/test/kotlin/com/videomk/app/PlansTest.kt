package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.ApiError
import com.videomk.app.core.CancelResult
import com.videomk.app.core.Capabilities
import com.videomk.app.core.CreateDefaults
import com.videomk.app.core.CreateErrors
import com.videomk.app.core.CreateGate
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.CreateStop
import com.videomk.app.core.PlanState
import com.videomk.app.core.UndoCenter
import com.videomk.app.core.WalletInfo
import com.videomk.app.core.parseObject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
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

/** Plans, looks, the watermark, cancel, the gallery and undo (docs/PLANS.md, docs/CREATE_API.md, docs/WATERMARK.md). */
class PlansTest {
    private lateinit var server: MockWebServer
    private lateinit var api: ApiClient

    @Before fun setUp() { server = MockWebServer().apply { start() }; api = ApiClient(configFor(server), FixedAuth(), appVersion = "9.9", timeZone = { "Europe/Madrid" }) }
    @After fun tearDown() { server.close() }

    private val freeCaps = """{"aspects":[{"id":"16:9","label":"Landscape","ready":true}],
      "resolutions":[{"id":"720p","label":"720p","credits_multiplier":1,"available":true},{"id":"1080p","label":"1080p","credits_multiplier":1,"available":true},{"id":"2160p","label":"4K","credits_multiplier":2,"available":false,"requires_plan":"max"}],
      "platforms":[{"id":"youtube","label":"YouTube","aspect":"16:9","resolution":"1080p","recommended_minutes":3}],
      "lengths":{"min_minutes":0.25,"max_minutes":12,"presets":[0.25,0.5,0.75,1,2,3],"plan_max_seconds":30,"locked":[{"over_seconds":30,"max_seconds":300,"requires_plan":"pro"}]},
      "plan":{"id":"free","name":"Free","limits":{"max_seconds":30,"resolutions":["720p","1080p"],"watermark_forced":true,"photos_per_video":10,"storage_bytes":2000000000}},
      "free_creation":"welcome","free":{"available":true,"credits_left":2,"max_seconds":30},"can_upgrade":false,"plan_max_photos":10,
      "looks":{"style":{"param":"style","default":"auto","options":[{"id":"auto","label":"Auto","note":"We choose.","available":true},{"id":"cartoon","label":"Illustrated","available":false},{"id":"real","label":"Real","available":true},{"id":"whiteboard","label":"Whiteboard","available":true}]},
               "backgrounds":{"animated":true,"ask":[{"id":"gas-brand-dark","label":"Purple 3D gas","say":"with a purple 3D background"},{"id":"none","label":"Still background","say":"no moving background"}]}},
      "watermark":{"forced":true,"forced_note":"The videomk watermark is included on this plan.","modes":[{"id":"none","available":false,"label":"None","requires_plan":"pro"},{"id":"videomk","available":true,"label":"videomk"}],
                   "presences":[{"id":"always","available":true,"label":"Always visible","note":"Stays in the corner."},{"id":"moments","available":false,"label":"Now and then"}],"default_presence":"always"}}"""

    @Test fun `capabilities carry the plan, what it locks, the looks and the watermark - all optional`() {
        val c = Capabilities.fromJson(parseObject(freeCaps))
        assertEquals("Free", c.plans.plan!!.name); assertTrue(c.plans.plan!!.isFree); assertEquals(30, c.planMaxSeconds); assertEquals("pro", c.longerPlan); assertEquals(10, c.planMaxPhotos)
        assertTrue(c.lengthAllowed(0.5)); assertFalse(c.lengthAllowed(1.0))
        assertFalse(c.resolution("2160p")!!.available); assertEquals("max", c.resolution("2160p")!!.requiresPlan); assertEquals(2, c.resolution("2160p")!!.multiplier)
        assertEquals(listOf("auto", "cartoon", "real", "whiteboard"), c.looks!!.styles.map { it.id }); assertTrue(c.looks!!.hasStyleChoice); assertFalse(c.looks!!.style("cartoon")!!.available)
        assertEquals("with a purple 3D background", c.looks!!.wishes.first().say)
        assertTrue(c.watermark!!.forced); assertEquals("The videomk watermark is included on this plan.", c.watermark!!.forcedNote)
        // an older server: none of it, and nothing breaks
        val old = Capabilities.fromJson(parseObject("""{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}]}"""))
        assertNull(old.looks); assertNull(old.watermark); assertNull(old.plans.plan); assertTrue(old.lengthAllowed(12.0)); assertEquals(PlanState.NONE, old.plans)
    }

    @Test fun `the form never starts on something the plan refuses - Free opens on YouTube 30 s at 1080p`() {
        val c = Capabilities.fromJson(parseObject(freeCaps))
        val o = CreateDefaults.resolve(null, c)
        assertEquals("youtube", o.platform); assertEquals(0.5, o.minutes, 0.0); assertEquals("1080p", o.resolution); assertEquals(1, o.credits)
        // a remembered 4K and 3 minutes from a time on a larger plan fall back quietly
        val back = CreateDefaults.resolve(com.videomk.app.core.CreatePrefs("youtube", "16:9", "2160p", 3.0, null, true, "auto", "cartoon"), c)
        assertEquals("1080p", back.resolution); assertEquals(0.5, back.minutes, 0.0); assertEquals("auto", back.style)   // cartoon is not available on this stage
        assertEquals(2, CreateDefaults.priced(CreateOptions(minutes = 1.0, resolution = "2160p"), c).credits)             // the server's multiplier prices 4K
    }

    @Test fun `a plan refusal is a message on Create and never the end of the session`() = runBlocking {
        server.enqueue(json(403, """{"code":"plan_length","message":"Videos on your plan can be up to 0:30 long. Pro makes longer ones.","feature":"length","plan":"free","requires_plan":"pro","limit":{"max_seconds":30},"can_upgrade":false}"""))
        try { api.startGeneration("Explain rainbows please", "r1", CreateOptions(minutes = 1.0)); fail() } catch (e: ApiError.Plan) {
            assertEquals("plan_length", e.code); assertEquals("pro", e.requiresPlan); assertEquals(30, e.maxSeconds); assertTrue(e.message.startsWith("Videos on your plan"))
            val stop = CreateErrors.withFix(CreateErrors.fromGenerate(e)!!, Capabilities.fromJson(parseObject(freeCaps)), e) as CreateStop.Plan
            assertEquals(0.5, stop.shorterMinutes!!, 0.0)                         // the one-tap fix: the longest length the plan makes
        }
        for (code in listOf("plan_resolution", "plan_watermark", "plan_photos", "watermark_premium", "free_not_available")) {
            server.enqueue(json(403, """{"code":"$code","message":"Server text for $code."}"""))
            try { api.startGeneration("Explain rainbows please", "r1", CreateOptions()); fail() } catch (e: ApiError) { assertEquals(ApiError.Plan(code, "Server text for $code."), e) }
        }
        server.enqueue(json(429, """{"code":"free_budget_spent","message":"Free videos are done for today.","reason":"paused","resumes_at":"2026-11-28T00:00:00Z"}"""))
        try { api.startGeneration("Explain rainbows please", "r1", CreateOptions()); fail() } catch (e: ApiError.Plan) { assertEquals(java.time.Instant.parse("2026-11-28T00:00:00Z"), e.resumesAt) }
        // API Gateway's own 403 (no code) is still what it was
        server.enqueue(json(403, """{"message":"Forbidden"}"""))
        try { api.wallet(); fail() } catch (e: ApiError) { assertEquals(ApiError.Unauthorized, e) }
    }

    @Test fun `style, a background wish and a changed watermark go into the request - nothing when untouched`() = runBlocking {
        server.enqueue(json(body = """{"video_id":"v1"}""")); server.enqueue(json(body = """{"video_id":"v2"}"""))
        api.startGeneration("Explain rainbows please", "r1", CreateOptions())
        val plain = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertFalse(plain.containsKey("style")); assertFalse(plain.containsKey("watermark")); assertEquals("Explain rainbows please", plain["prompt"]!!.jsonPrimitive.content)
        api.startGeneration("Explain rainbows please", "r2", CreateOptions(style = "whiteboard", backgroundWish = "with a purple 3D background", watermarkMode = "videomk", watermarkPresence = "moments"))
        val b = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("whiteboard", b["style"]!!.jsonPrimitive.content); assertEquals("Explain rainbows please with a purple 3D background", b["prompt"]!!.jsonPrimitive.content)
        assertEquals("""{"mode":"videomk","presence":"moments"}""", b["watermark"].toString())
    }

    @Test fun `the wallet says when the next free credit arrives and names the plan`() {
        val w = WalletInfo.fromJson(parseObject("""{"balance":2,"unlimited":false,"buckets":[{"kind":"plan","remaining":2,"expires_at":1800000000}],"next_daily_at":1795000000,"next_free_credit_at":"2026-11-28T23:00:00Z","next_free_credits":1,
            "plan":{"id":"pro","name":"Pro","limits":{"max_seconds":300}},"free_creation":"daily","free":{"available":false,"reason":"used","message":"No free credits left."},"can_upgrade":false}"""))
        assertEquals(java.time.Instant.parse("2026-11-28T23:00:00Z"), w.nextFreeAt); assertEquals("Pro", w.plans.plan!!.name); assertFalse(w.plans.canUpgrade)
        val off = WalletInfo.fromJson(parseObject("""{"balance":0,"next_daily_at":null,"next_free_credit_at":null,"next_free_credits":0}"""))
        assertNull(off.nextFreeAt)                                              // the daily credit is off: the line is hidden
        val older = WalletInfo.fromJson(parseObject("""{"balance":1,"next_daily_at":1795000000}"""))
        assertNotNull(older.nextFreeAt); assertNull(older.plans.plan)
    }

    @Test fun `Create is locked only when nothing can be spent AND free creation is not available`() {
        fun wallet(balance: Int, free: String, plan: String = "free", unlimited: Boolean = false) = WalletInfo.fromJson(parseObject("""{"balance":$balance,"unlimited":$unlimited,"plan":{"id":"$plan","name":"$plan"},"free":$free}"""))
        val off = """{"available":false,"reason":"off","message":"Free videos are not offered right now."}"""
        assertEquals("Free videos are not offered right now.", CreateGate.locked(wallet(0, off), PlanState.NONE)!!.message)
        // QA finding: a Free account that holds paid credits reads available false / reason used, and the server still lets it create
        assertNull(CreateGate.locked(wallet(3, """{"available":false,"reason":"used"}"""), PlanState.NONE))
        assertNull(CreateGate.locked(wallet(0, """{"available":true}"""), PlanState.NONE))
        assertNull(CreateGate.locked(wallet(0, off, plan = "pro"), PlanState.NONE))        // a paid plan out of credits is the usual "not enough credits"
        assertNull(CreateGate.locked(wallet(0, off, unlimited = true), PlanState.NONE))
        assertNull(CreateGate.locked(WalletInfo(balance = 0), PlanState.NONE))             // a server without plans
        assertNotNull(CreateGate.locked(wallet(0, """{"available":false,"reason":"paused","resumes_at":"2026-11-28T00:00:00Z"}"""), PlanState.NONE)!!.resumesAt)
    }

    @Test fun `cancel gives the credits back, repeats harmlessly, retries a try_again once and knows an older server`() = runBlocking {
        server.enqueue(json(body = """{"message":"cancelled","video_id":"v1","status":"CANCELLED","refunded":2}"""))
        assertEquals(CancelResult.Cancelled(2), api.cancelVideo("v1"))
        val r = server.takeRequest(); assertEquals("POST", r.method); assertEquals("/prod/users/user-1/videos/v1/cancel", r.url.encodedPath); assertEquals("android", r.headers["X-Platform"])
        server.enqueue(json(body = """{"message":"already cancelled","status":"CANCELLED","refunded":0}"""))
        assertEquals(CancelResult.Cancelled(0), api.cancelVideo("v1"))
        server.enqueue(json(409, """{"code":"try_again","message":"Busy."}""")); server.enqueue(json(body = """{"refunded":1}"""))
        assertEquals(CancelResult.Cancelled(1), api.cancelVideo("v1"))
        server.enqueue(json(409, """{"code":"not_cancellable","message":"This video is already finished."}"""))
        assertEquals(CancelResult.NotCancellable("This video is already finished."), api.cancelVideo("v1"))
        server.enqueue(json(403, """{"message":"Missing Authentication Token"}"""))
        assertEquals(CancelResult.Unsupported, api.cancelVideo("v1"))
    }

    @Test fun `a finished video can be deleted and a second delete is still a success`() = runBlocking {
        server.enqueue(json(body = """{"message":"deleted","video_id":"v1"}""")); assertTrue(api.deleteVideo("v1"))
        server.enqueue(json(404, """{"code":"not_found"}""")); assertTrue(api.deleteVideo("v1"))
        server.enqueue(json(409, """{"code":"busy","message":"An edit is rendering."}"""))
        try { api.deleteVideo("v1"); fail() } catch (e: ApiError) { assertEquals(ApiError.Conflict("An edit is rendering."), e) }
    }

    @Test fun `the gallery is read without a token and an empty or failing answer is just empty`() = runBlocking {
        server.enqueue(json(body = """{"videos":[{"id":"forest","title":"How a forest breathes","aspect":"16:9","seconds":28,"video_url":"https://x/v.mp4","poster_url":null},{"title":"no id"}],"count":1,"expires_in":3600}"""))
        val g = api.gallery()
        assertEquals(1, g.size); assertEquals("How a forest breathes", g[0].title); assertNull(g[0].posterUrl)
        val r = server.takeRequest(); assertEquals("/prod/gallery", r.url.encodedPath); assertNull(r.headers["Authorization"]); assertEquals("android", r.headers["X-Platform"]); assertNotNull(r.headers["X-Locale"])
        server.enqueue(json(500, "{}")); assertTrue(api.gallery().isEmpty())
    }

    // ---- undo over confirm

    @Test fun `a removal is sent only after the undo time, and undo sends nothing`() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val undo = UndoCenter(scope, windowMillis = 80)
        val sent = java.util.concurrent.CopyOnWriteArrayList<String>(); val restored = java.util.concurrent.CopyOnWriteArrayList<String>()
        undo.offer("Deleted", commit = { sent += "a" }, undo = { restored += "a" })
        assertEquals("Deleted", undo.current.value!!.text); assertTrue(undo.current.value!!.undoable); assertTrue(sent.isEmpty())
        undo.undo()
        delay(200); assertTrue(sent.isEmpty()); assertEquals(listOf("a"), restored.toList()); assertNull(undo.current.value)
        undo.offer("Deleted", commit = { sent += "b" }, undo = { restored += "b" })
        delay(300); assertEquals(listOf("b"), sent.toList()); assertNull(undo.current.value)
        undo.undo(); assertEquals(listOf("a"), restored.toList())               // too late: nothing to undo, nothing breaks
    }

    @Test fun `a newer removal makes the earlier one final, leaving the screen sends at once, and a plain message has no undo`() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        val undo = UndoCenter(scope, windowMillis = 5_000)
        val sent = java.util.concurrent.CopyOnWriteArrayList<String>()
        undo.offer("Deleted", commit = { sent += "a" }, undo = {})
        undo.offer("Deleted", commit = { sent += "b" }, undo = {})
        delay(100); assertEquals(listOf("a"), sent.toList())
        undo.flush(); delay(100); assertEquals(listOf("a", "b"), sent.toList()); assertFalse(undo.hasPending)
        undo.offer("Deleted", commit = { sent += "c" }, undo = {})
        undo.say("Cancelled · 2 credits back")
        delay(100); assertEquals(listOf("a", "b", "c"), sent.toList()); assertFalse(undo.current.value!!.undoable); assertEquals("Cancelled · 2 credits back", undo.current.value!!.text)
    }
}
