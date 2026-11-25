package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

private val FULL = Capabilities(
    aspects = listOf(AspectInfo("16:9", "Landscape", true, false), AspectInfo("9:16", "Vertical", true, true), AspectInfo("1:1", "Square", true, false), AspectInfo("4:5", "Portrait", true, false)),
    resolutions = listOf(ResolutionInfo("720p", "720p"), ResolutionInfo("1080p", "1080p")), platforms = emptyList(),
    languages = listOf(LanguageInfo("en", "English"), LanguageInfo("es", "Español")), intake = true,
)

private class FakeIntakeApi(var result: () -> IntakeResult = { IntakeResult.Ok(null) }) : IntakeApi {
    val requests = mutableListOf<IntakeRequest>()
    override suspend fun capabilities() = FULL
    override suspend fun brief(request: IntakeRequest): IntakeResult { requests += request; return result() }
}

private fun q(id: String, vararg opts: String) = Question(id, "Q $id?", opts.map { QuestionOption(it.lowercase(), it) })

class CreateTest {
    // capabilities and platform chips

    @Test fun `capabilities parse, and an empty answer falls back to landscape 1080p`() {
        val c = Capabilities.fromJson(Json.parseToJsonElement("""{"aspects":[{"id":"16:9","label":"Landscape","ready":true,"beta":false},{"id":"9:16","label":"Vertical","ready":true,"beta":true},{"id":"1:1","label":"Square","ready":false}],
            "resolutions":[{"id":"720p","label":"720p"},{"id":"1080p","label":"1080p"}],"platforms":[{"id":"youtube","label":"YouTube","aspect":"16:9","resolution":"1080p"}],
            "languages":[{"id":"en","label":"English"},{"id":"es","label":"Español"}],"lengths":{"min_minutes":1,"max_minutes":12},"max_photos":100,"intake":true}""").jsonObject)
        assertEquals(listOf("16:9", "9:16"), c.readyAspects.map { it.id }); assertTrue(c.aspect("9:16")!!.beta); assertEquals(2, c.languages.size); assertTrue(c.intake); assertFalse(c.isReady("1:1"))
        assertEquals(Capabilities.FALLBACK, Capabilities.fromJson(buildJsonObject { }))
        assertEquals(listOf("16:9"), Capabilities.FALLBACK.readyAspects.map { it.id }); assertEquals(listOf("1080p"), Capabilities.FALLBACK.resolutions.map { it.id }); assertFalse(Capabilities.FALLBACK.intake)
    }

    @Test fun `with only 16 by 9 the supported platforms come first and the others are dimmed`() {
        val chips = CreatePlatforms.chips(Capabilities.FALLBACK)
        assertEquals(listOf("youtube", "linkedin", "x", "other", "shorts", "instagram_feed"), chips.map { it.id })
        assertEquals(listOf(true, true, true, true, false, false), chips.map { it.enabled })
        assertTrue(chips.take(4).all { it.aspect == "16:9" && it.resolution == "1080p" })
        assertEquals(listOf("YouTube", "LinkedIn", "X", "Just a video", "Shorts · Reels · TikTok", "Instagram"), chips.map { it.label })
        assertTrue(CreatePlatforms.chips(FULL).all { it.enabled }); assertEquals("9:16", CreatePlatforms.chip(FULL, "shorts")!!.aspect); assertEquals("4:5", CreatePlatforms.chip(FULL, "instagram_feed")!!.aspect)
    }

    @Test fun `a server list for a platform overrides its recommended format`() {
        val caps = FULL.copy(platforms = listOf(PlatformInfo("linkedin", "LinkedIn", "1:1", "1080p")))
        assertEquals("1:1", CreatePlatforms.chip(caps, "linkedin")!!.aspect)
    }

    @Test fun `the recommendation line, custom format and whether Change is offered`() {
        val o = CreateOptions()
        assertEquals("Just a video · Landscape 16:9 · 1080p", CreatePlatforms.recommendation(o, Capabilities.FALLBACK))
        val yt = CreatePlatforms.select(o, CreatePlatforms.chip(Capabilities.FALLBACK, "youtube")!!)
        assertEquals("YouTube · Landscape 16:9 · 1080p", CreatePlatforms.recommendation(yt, Capabilities.FALLBACK)); assertFalse(CreatePlatforms.isCustom(yt, Capabilities.FALLBACK))
        val vertical = yt.copy(aspect = "9:16", resolution = "720p")
        assertTrue(CreatePlatforms.isCustom(vertical, FULL)); assertEquals("Custom · Vertical 9:16 · 720p", CreatePlatforms.recommendation(vertical, FULL))
        assertFalse(CreatePlatforms.canChangeFormat(Capabilities.FALLBACK)); assertTrue(CreatePlatforms.canChangeFormat(FULL))
        assertEquals(o, CreatePlatforms.select(o, CreatePlatforms.chip(Capabilities.FALLBACK, "shorts")!!))   // a "Soon" chip changes nothing
        val v = CreatePlatforms.select(o, CreatePlatforms.chip(FULL, "shorts")!!); assertEquals("shorts", v.platform); assertEquals("9:16", v.aspect)
    }

    @Test fun `the more options summary line`() {
        assertEquals("Auto look · Subtitles on · Same language as description", CreatePlatforms.moreSummary(CreateOptions(), FULL))
        assertEquals("Paper look · Subtitles off · Español", CreatePlatforms.moreSummary(CreateOptions(look = VideoLook.Paper, captions = false, language = "es"), FULL))
        assertEquals("Same as my description", CreatePlatforms.languageLabel(CreateOptions(), FULL)); assertEquals("English", CreatePlatforms.languageLabel(CreateOptions(language = "en"), FULL))
    }

    // defaults and memory

    @Test fun `first launch defaults and what is remembered`() {
        val d = CreateDefaults.resolve(null, Capabilities.FALLBACK)
        assertEquals(CreateOptions(minutes = 3.0, look = null, captions = true, platform = "other", aspect = "16:9", resolution = "1080p", language = "auto"), d)
        val stored = CreatePrefs.of(CreateOptions(minutes = 5.0, look = VideoLook.Paper, captions = false, platform = "shorts", aspect = "9:16", resolution = "720p", language = "es"))
        val back = CreatePrefs.fromJson(stored.toJson())!!
        assertEquals(stored, back)
        val full = CreateDefaults.resolve(back, FULL)
        assertEquals("shorts", full.platform); assertEquals("9:16", full.aspect); assertEquals("720p", full.resolution); assertEquals(5.0, full.minutes, 0.0); assertEquals(VideoLook.Paper, full.look); assertFalse(full.captions); assertEquals("es", full.language)
        assertNull(CreatePrefs.fromJson("garbage")); assertNull(CreatePrefs.fromJson(null))
    }

    @Test fun `a remembered choice the server no longer offers falls back quietly`() {
        val stored = CreatePrefs("shorts", "9:16", "720p", 5, "paper", false, "es")
        val o = CreateDefaults.resolve(stored, Capabilities.FALLBACK)
        assertEquals("16:9", o.aspect); assertEquals("1080p", o.resolution); assertEquals("auto", o.language); assertEquals("other", o.platform)
        assertEquals(VideoLook.Paper, o.look); assertEquals(5.0, o.minutes, 0.0)
        assertEquals(3.0, CreateDefaults.resolve(stored.copy(minutes = 7), FULL).minutes, 0.0)   // not one of the six lengths
    }

    // the status line on the Create screen

    @Test fun `create screen status lines`() {
        fun st(text: String, balance: Int? = 5, photos: Int = 0, minutes: Double = 3.0, checking: Boolean = false) = ComposerLogic.status(text, CreateOptions(minutes), balance, photos, false, false, createScreen = true, checking = checking)
        assertEquals("Describe your video to continue", st("").text); assertEquals("Describe your video to continue", st("trip").text); assertFalse(st("").sendReady)
        assertEquals("3 credits · you'll have 2 left", st("How bees make honey, explained for kids").text)
        assertEquals("Needs 3 credits, you have 1", st("How bees make honey, explained for kids", balance = 1).text); assertEquals(1, st("How bees make honey, explained for kids", balance = 1).fix!!.minutes)
        assertEquals("You have no credits", st("How bees make honey, explained for kids", balance = 0).text)
        assertEquals("Checking your request…", st("How bees make honey, explained for kids", checking = true).text)
        assertEquals(StatusKind.PhotoHint, st("How bees make honey, explained for kids", photos = 100, minutes = 1.0).kind)
    }

    // the request check and its budgets

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `the check shows its skeleton after 2 and a half seconds and gives up after 8`() = runTest {
        val api = FakeIntakeApi { IntakeResult.Ok(null) }
        val slowApi = object : IntakeApi by api { override suspend fun brief(request: IntakeRequest): IntakeResult { delay(60_000); return IntakeResult.Questions(listOf(q("a", "x"))) } }
        var slow = 0; var result: IntakeResult? = null
        val job = launch { result = IntakeCheck(slowApi).run(IntakeRequest("p", CreateOptions(), 0)) { slow++ } }
        advanceTimeBy(2400); runCurrent(); assertEquals(0, slow); assertNull(result)
        advanceTimeBy(200); runCurrent(); assertEquals(1, slow); assertNull(result)
        advanceTimeBy(5300); runCurrent(); assertNull(result)
        advanceTimeBy(200); runCurrent(); job.join()
        assertEquals(IntakeResult.Ok(null), result)   // proceed without a brief: never an error
    }

    @Test fun `a fast check never shows the skeleton`() = runBlocking {
        var slow = 0
        val r = IntakeCheck(FakeIntakeApi { IntakeResult.Ok(buildJsonObject { put("tone", "calm") }) }).run(IntakeRequest("p", CreateOptions(), 0)) { slow++ }
        assertEquals("calm", (r as IntakeResult.Ok).brief!!["tone"]!!.jsonPrimitive.content); assertEquals(0, slow)
    }

    @Test fun `any failure of the check means proceed, a block or a pause is reported`() = runBlocking {
        for (e in listOf(ApiError.Network, ApiError.Server, ApiError.NotFound, ApiError.Unauthorized, ApiError.Invalid("x"))) {
            assertEquals(e.toString(), IntakeResult.Ok(null), IntakeCheck(FakeIntakeApi { throw e }).run(IntakeRequest("p", CreateOptions(), 0)))
        }
        assertEquals(IntakeResult.Ok(null), IntakeCheck(null).run(IntakeRequest("p", CreateOptions(), 0)))   // no check on this server
        assertEquals(IntakeResult.Paused("Wait", 3600), IntakeCheck(FakeIntakeApi { throw ApiError.Paused("Wait", 3600) }).run(IntakeRequest("p", CreateOptions(), 0)))
        assertEquals(IntakeResult.Blocked("No"), IntakeCheck(FakeIntakeApi { throw ApiError.Blocked("No") }).run(IntakeRequest("p", CreateOptions(), 0)))
    }

    @Test fun `check answers parse from the contract`() {
        fun parse(s: String) = IntakeResult.fromJson(Json.parseToJsonElement(s).jsonObject)
        assertEquals("kids", ((parse("""{"status":"ok","brief":{"audience":"kids"}}""") as IntakeResult.Ok).brief!!["audience"] as kotlinx.serialization.json.JsonPrimitive).content)
        val qs = parse("""{"status":"questions","questions":[{"id":"audience","text":"Who is this for?","options":[{"id":"kids","label":"Kids"},{"id":"adults","label":"Adults"}],"allow_other":true},
            {"id":"tone","text":"Tone?","options":[{"id":"calm","label":"Calm"},{"id":"fun","label":"Funny"}]},{"id":"c","text":"C?","options":[{"id":"x","label":"X"}]},{"id":"d","text":"D?","options":[{"id":"x","label":"X"}]},{"id":"e","text":"E","options":[]}]}""") as IntakeResult.Questions
        assertEquals(listOf("audience", "tone", "c"), qs.questions.map { it.id }.take(3)); assertEquals(3, qs.questions.size.coerceAtMost(3)); assertEquals("Kids", qs.questions[0].options[0].label)
        assertEquals(IntakeResult.NotSupported("Sorry", "Try this"), parse("""{"status":"not_supported","message":"Sorry","suggestion":"Try this"}"""))
        assertEquals(IntakeResult.NotSupported(null, null), parse("""{"status":"unsafe"}"""))
        assertEquals(IntakeResult.Blocked("Nope"), parse("""{"status":"blocked","message":"Nope"}"""))
        assertEquals(IntakeResult.Ok(null), parse("""{"status":"questions","questions":[]}""")); assertEquals(IntakeResult.Ok(null), parse("""{"status":"weird"}"""))
    }

    @Test fun `check request body has the options, the media count and all answers`() {
        val body = IntakeRequest("  How bees make honey ", CreateOptions(minutes = 3.0, platform = "youtube", aspect = "16:9", resolution = "1080p", captions = false, language = "es"), 4,
            listOf(Answer.Option("audience", "kids", "Kids"), Answer.Text("tone", "warm"), Answer.Skip("focus"))).toJson()
        assertEquals("How bees make honey", body["prompt"]!!.jsonPrimitive.content); assertEquals(4, body["media_count"]!!.jsonPrimitive.content.toInt())
        val o = body["options"]!!.jsonObject; assertEquals("youtube", o["platform"]!!.jsonPrimitive.content); assertEquals("es", o["language"]!!.jsonPrimitive.content); assertEquals("false", o["captions"]!!.jsonPrimitive.content); assertEquals(3.0, o["target_minutes"]!!.jsonPrimitive.content.toDouble(), 0.0)
        val a = body["answers"]!!.jsonArray
        assertEquals("kids", a[0].jsonObject["option"]!!.jsonPrimitive.content); assertEquals("warm", a[1].jsonObject["text"]!!.jsonPrimitive.content); assertEquals("true", a[2].jsonObject["skip"]!!.jsonPrimitive.content)
    }

    // the question flow

    private fun flow() = QuestionFlow(listOf(q("audience", "Kids", "Beginners"), q("tone", "Calm", "Funny"), q("focus", "Making honey", "Pollination")))

    @Test fun `answers advance one question at a time and end in the summary`() {
        val f = flow()
        assertEquals("QUESTION 1 OF 3", f.overline); assertEquals("audience", f.current!!.id); assertFalse(f.canGoBack)
        f.choose("kids"); assertEquals("QUESTION 2 OF 3", f.overline); assertTrue(f.canGoBack)
        f.other("  warm and gentle "); assertEquals("focus", f.current!!.id)
        f.choose("pollination"); assertTrue(f.inSummary); assertNull(f.current)
        assertEquals(listOf("audience", "tone", "focus"), f.answerList().map { it.id }); assertEquals("warm and gentle", (f.answerOf("tone") as Answer.Text).text)
        assertEquals(listOf("Kids", "warm and gentle", "Pollination"), f.chips(null).map { it.label })
        assertEquals(listOf("For kids", "Calm", "Focus: Making honey"), f.chips("For kids · Calm · Focus: Making honey").map { it.label })
        assertEquals(listOf("Kids", "warm and gentle", "Pollination"), f.chips("only two · parts").map { it.label })   // does not line up: the answers' own labels
    }

    @Test fun `back reopens the previous question and an answer can be replaced`() {
        val f = flow(); f.choose("kids"); f.back(); assertEquals("audience", f.current!!.id); f.choose("beginners")
        assertEquals("beginners", (f.answerOf("audience") as Answer.Option).option); assertEquals("tone", f.current!!.id)
    }

    @Test fun `skip and you decide leave no chip, and all skipped means nothing to confirm`() {
        val f = flow(); f.skip(); f.youDecide(); f.skip()
        assertTrue(f.inSummary); assertTrue(f.allSkipped()); assertTrue(f.chips(null).isEmpty()); assertTrue((f.answerOf("tone") as Answer.Skip).youDecide)
        val g = flow(); g.choose("kids"); g.skip(); g.skip(); assertFalse(g.allSkipped()); assertEquals(1, g.chips(null).size)
    }

    @Test fun `make it now skips what is left and goes to the summary`() {
        val f = flow(); f.choose("kids"); f.makeItNow()
        assertTrue(f.inSummary); assertEquals(3, f.answerList().size); assertTrue(f.answerOf("tone") is Answer.Skip); assertEquals(1, f.answered().size)
        val g = flow(); g.makeItNow(); assertTrue(g.allSkipped())
    }

    @Test fun `editing a chip returns to the summary after one answer`() {
        val f = flow(); f.choose("kids"); f.choose("calm"); f.choose("making honey")
        f.edit("tone"); assertFalse(f.inSummary); assertEquals("tone", f.current!!.id)
        f.choose("funny"); assertTrue(f.inSummary); assertEquals("funny", (f.answerOf("tone") as Answer.Option).option)
        assertEquals(listOf("Kids", "Funny", "Making honey"), f.chips(null).map { it.label })
    }

    // stops and errors

    @Test fun `check stops become kind sheets, with the server's words when there are some`() {
        assertEquals(CreateStop.NotSupported("Sorry", "Try this"), CreateErrors.fromCheck(IntakeResult.NotSupported("Sorry", "Try this")))
        assertEquals(CreateStop.NotSupported(CreateErrors.DEFAULT_NOT_SUPPORTED, null), CreateErrors.fromCheck(IntakeResult.NotSupported(null, " ")))
        assertEquals(CreateStop.Blocked("We can't make this one."), CreateErrors.fromCheck(IntakeResult.Blocked("We can't make this one.")))
        assertEquals(CreateStop.Blocked(CreateErrors.DEFAULT_BLOCKED), CreateErrors.fromCheck(IntakeResult.Blocked(null)))
        assertEquals(CreateStop.Paused("Paused", 3600), CreateErrors.fromCheck(IntakeResult.Paused("Paused", 3600)))
        assertNull(CreateErrors.fromCheck(IntakeResult.Ok(null))); assertNull(CreateErrors.fromCheck(IntakeResult.Questions(listOf(q("a", "x")))))
        assertEquals(CreateStop.Blocked("No"), CreateErrors.fromGenerate(ApiError.Blocked("No"))); assertEquals(CreateStop.Paused("P", 60), CreateErrors.fromGenerate(ApiError.Paused("P", 60))); assertNull(CreateErrors.fromGenerate(ApiError.Server))
        assertEquals("You can try again in about 1 hour.", CreateErrors.retryText(3600)); assertEquals("You can try again in about 24 hours.", CreateErrors.retryText(86400))
        assertEquals("You can try again in about 5 minutes.", CreateErrors.retryText(300)); assertEquals("You can try again in a minute.", CreateErrors.retryText(30)); assertNull(CreateErrors.retryText(null))
    }

    // the real client

    private lateinit var server: MockWebServer
    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() { server.close() }
    private fun api() = ApiClient(configFor(server), FixedAuth())

    @Test fun `generate sends the creation options only when they differ from the defaults, and the brief`() = runBlocking {
        server.enqueue(json(body = """{"video_id":"v1"}""")); server.enqueue(json(body = """{"video_id":"v2"}"""))
        api().startGeneration("How bees make honey for kids", "r1", CreateOptions(), emptyList())
        val plain = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        for (k in listOf("platform", "aspect", "resolution", "language", "brief")) assertFalse(k, k in plain)
        api().startGeneration("How bees make honey for kids", "r2", CreateOptions(platform = "shorts", aspect = "9:16", resolution = "720p", language = "es"), emptyList(), null, emptyList(), buildJsonObject { put("audience", "kids") })
        val b = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("shorts", b["platform"]!!.jsonPrimitive.content); assertEquals("9:16", b["aspect"]!!.jsonPrimitive.content); assertEquals("720p", b["resolution"]!!.jsonPrimitive.content); assertEquals("es", b["language"]!!.jsonPrimitive.content)
        assertEquals("kids", b["brief"]!!.jsonObject["audience"]!!.jsonPrimitive.content)
    }

    @Test fun `generate can answer blocked or paused`() = runBlocking {
        server.enqueue(json(400, """{"status":"blocked","message":"We can't make this video."}""")); server.enqueue(json(429, """{"status":"paused","message":"Paused for a day.","retry_after":86400}"""))
        server.enqueue(json(400, """{"message":"bad"}""")); server.enqueue(json(429, """{"message":"Daily limit"}"""))
        try { api().startGeneration("A fine request about bees", "r", CreateOptions()); fail() } catch (e: ApiError.Blocked) { assertEquals("We can't make this video.", e.text) }
        try { api().startGeneration("A fine request about bees", "r", CreateOptions()); fail() } catch (e: ApiError.Paused) { assertEquals(86400, e.retryAfterSeconds) }
        try { api().startGeneration("A fine request about bees", "r", CreateOptions()); fail() } catch (e: ApiError.Invalid) { assertEquals("bad", e.text) }
        try { api().startGeneration("A fine request about bees", "r", CreateOptions()); fail() } catch (e: ApiError.Quota) { assertEquals("Daily limit", e.text) }
    }

    @Test fun `a missing capabilities or check endpoint degrades, it never errors`() = runBlocking {
        val intake = ApiIntake(api())
        server.enqueue(json(404, "{}")); assertEquals(Capabilities.FALLBACK, intake.capabilities())
        server.enqueue(json(403, """{"message":"Missing Authentication Token"}""")); assertEquals(Capabilities.FALLBACK, intake.capabilities())
        server.enqueue(json(403, "{}"))
        assertEquals(IntakeResult.Ok(null), IntakeCheck(intake).run(IntakeRequest("A fine request about bees", CreateOptions(), 0)))
        server.enqueue(json(404, "{}"))
        assertEquals(IntakeResult.Ok(null), IntakeCheck(intake).run(IntakeRequest("A fine request about bees", CreateOptions(), 0)))
    }

    @Test fun `capabilities and the check use the contract paths, and a paused account is reported`() = runBlocking {
        val intake = ApiIntake(api())
        server.enqueue(json(body = """{"aspects":[{"id":"16:9","label":"Landscape","ready":true}],"resolutions":[{"id":"1080p","label":"1080p"}],"intake":true}"""))
        assertTrue(intake.capabilities().intake); assertEquals("/prod/users/user-1/capabilities", server.takeRequest().url.encodedPath)
        server.enqueue(json(body = """{"status":"questions","questions":[{"id":"a","text":"Who?","options":[{"id":"k","label":"Kids"}]}]}"""))
        assertTrue(intake.brief(IntakeRequest("p", CreateOptions(), 0)) is IntakeResult.Questions)
        val r = server.takeRequest(); assertEquals("/prod/users/user-1/videos/brief", r.url.encodedPath); assertEquals("POST", r.method)
        server.enqueue(json(429, """{"status":"paused","message":"Paused","retry_after":3600}"""))
        assertEquals(IntakeResult.Paused("Paused", 3600), intake.brief(IntakeRequest("p", CreateOptions(), 0)))
    }
}
