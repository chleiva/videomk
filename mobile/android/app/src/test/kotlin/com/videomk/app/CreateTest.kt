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
        assertEquals(CreateOptions(minutes = 1.0, look = null, captions = true, platform = "other", aspect = "16:9", resolution = "1080p", language = "auto"), d)   // the old six lengths have no 30 s: 1 min, 1 credit
        assertEquals(0.5, CreateDefaults.resolve(null, FULL.copy(presets = listOf(0.25, 0.5, 1.0, 3.0))).minutes, 0.0)   // a server with the short presets: the first video is 30 s
        val stored = CreatePrefs.of(CreateOptions(minutes = 5.0, look = VideoLook.Paper, captions = false, platform = "shorts", aspect = "9:16", resolution = "720p", language = "es"))
        val back = CreatePrefs.fromJson(stored.toJson())!!
        assertEquals(stored, back)
        val full = CreateDefaults.resolve(back, FULL)
        assertEquals("shorts", full.platform); assertEquals("9:16", full.aspect); assertEquals("720p", full.resolution); assertEquals(5.0, full.minutes, 0.0); assertEquals(VideoLook.Paper, full.look); assertFalse(full.captions); assertEquals("es", full.language)
        assertNull(CreatePrefs.fromJson("garbage")); assertNull(CreatePrefs.fromJson(null))
    }

    @Test fun `a remembered choice the server no longer offers falls back quietly`() {
        val stored = CreatePrefs("shorts", "9:16", "720p", 5.0, "paper", false, "es")
        val o = CreateDefaults.resolve(stored, Capabilities.FALLBACK)
        assertEquals("16:9", o.aspect); assertEquals("1080p", o.resolution); assertEquals("auto", o.language); assertEquals("other", o.platform)
        assertEquals(VideoLook.Paper, o.look); assertEquals(5.0, o.minutes, 0.0)
        assertEquals(3.0, CreateDefaults.resolve(stored.copy(minutes = 7.0), FULL).minutes, 0.0)   // not one of the six lengths
    }

    // the status line on the Create screen

    @Test fun `create screen status lines`() {
        fun st(text: String, balance: Int? = 5, photos: Int = 0, minutes: Double = 3.0, checking: Boolean = false) = ComposerLogic.status(text, CreateOptions(minutes), balance, photos, false, false, createScreen = true, checking = checking)
        assertEquals("Describe your video to continue", st("").text); assertEquals("Describe your video to continue", st("trip").text); assertFalse(st("").sendReady)
        assertEquals("3 credits · you'll have 2 left", st("How bees make honey, explained for kids").text)
        assertEquals("Needs 3 credits, you have 1", st("How bees make honey, explained for kids", balance = 1).text); assertEquals(1.0, st("How bees make honey, explained for kids", balance = 1).fix!!.minutes!!, 0.0)
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

    @Test fun `a video's aspect from the real list response sizes the frame`() {
        val v = com.videomk.app.core.VideoItem.fromJson(com.videomk.app.core.parseObject("""{"video_id":"a","status":"COMPLETE","aspect":"9:16","resolution":"1080p","duration_s":61}"""))
        assertEquals("9:16", v.aspect); assertEquals("1080p", v.resolution)
        assertTrue(v.isTall); assertEquals(9f / 16f, v.frameRatio, 0.001f)
        val old = com.videomk.app.core.VideoItem.fromJson(com.videomk.app.core.parseObject("""{"video_id":"b","status":"COMPLETE"}"""))
        assertEquals(16f / 9f, old.frameRatio, 0.001f); assertFalse(old.isTall)
        assertEquals(1f, com.videomk.app.core.VideoItem.ratioOf("1:1"), 0.001f)
        assertEquals(0.8f, com.videomk.app.core.VideoItem.ratioOf("4:5"), 0.001f)
        assertEquals(16f / 9f, com.videomk.app.core.VideoItem.ratioOf("nonsense"), 0.001f)
    }

    @Test fun `the real capabilities response parses with beta aspects and the Shorts platform`() {
        val c = Capabilities.fromJson(com.videomk.app.core.parseObject("""{"aspects":[{"id":"16:9","label":"Landscape","ready":true,"beta":false},{"id":"9:16","label":"Vertical","ready":true,"beta":true}],"resolutions":[{"id":"720p","label":"720p"},{"id":"1080p","label":"1080p"}],"platforms":[{"id":"shorts","label":"YouTube Shorts","aspect":"9:16","resolution":"1080p","note":"x"},{"id":"tiktok","label":"TikTok","aspect":"9:16","resolution":"1080p","note":"x"}],"languages":[{"id":"en","label":"English"}],"lengths":{"min_minutes":1,"max_minutes":12},"max_photos":100,"intake":true}"""))
        assertTrue(c.intake); assertTrue(c.aspect("9:16")!!.beta)
        val shorts = com.videomk.app.core.CreatePlatforms.chip(c, "shorts")!!
        assertTrue(shorts.enabled); assertEquals("9:16", shorts.aspect)
        val o = com.videomk.app.core.CreatePlatforms.select(CreateOptions(), shorts)
        assertEquals("9:16", o.aspect); assertEquals("1080p", o.resolution)
    }

    private fun v(id: String, sig: String, date: String = "20261125T120000Z", title: String = "T") = com.videomk.app.core.VideoItem(
        id, com.videomk.app.core.VideoStatus.Complete, title,
        previewGifUrl = "https://b.s3.amazonaws.com/u/$id/preview.gif?X-Amz-Date=$date&X-Amz-Signature=$sig", videoUrl = "https://b.s3.amazonaws.com/u/$id/v.mp4?X-Amz-Date=$date&X-Amz-Signature=$sig")

    @Test fun `the image key ignores the signature and differs per video`() {
        val a = com.videomk.app.core.ImageKeys.stable(v("one", "AAA").previewGifUrl!!)
        val b = com.videomk.app.core.ImageKeys.stable(v("one", "BBB", "20261125T120400Z").previewGifUrl!!)
        val c = com.videomk.app.core.ImageKeys.stable(v("two", "AAA").previewGifUrl!!)
        assertEquals(a, b); assertTrue(a != c)
        assertEquals("https://x/y.png", com.videomk.app.core.ImageKeys.stable("https://x/y.png"))
        assertEquals(1_795_608_000L, com.videomk.app.core.ImageKeys.signedAtSeconds(v("one", "A").previewGifUrl))
    }

    @Test fun `a refresh with the same data keeps the same instances, only real changes replace one`() {
        val old = listOf(v("one", "AAA"), v("two", "AAA"))
        val same = com.videomk.app.core.VideoMerge.reuse(old, listOf(v("one", "BBB", "20261125T120004Z"), v("two", "CCC", "20261125T120004Z")))
        assertTrue(same === old)
        val changed = com.videomk.app.core.VideoMerge.reuse(old, listOf(v("one", "DDD", "20261125T120008Z"), v("two", "DDD", "20261125T120008Z", title = "New")))
        assertTrue(changed[0] === old[0]); assertTrue(changed[1] !== old[1]); assertEquals("New", changed[1].title)
        // links are renewed after ten minutes even when nothing changed (they expire after an hour)
        val renewed = com.videomk.app.core.VideoMerge.reuse(old, listOf(v("one", "EEE", "20261125T121100Z"), v("two", "EEE", "20261125T121100Z")))
        assertTrue(renewed[0] !== old[0])
        // a new video in front, a removed one: the list changes, the others stay the same instances
        val grown = com.videomk.app.core.VideoMerge.reuse(old, listOf(v("zero", "A"), v("one", "B"), v("two", "B")))
        assertEquals(3, grown.size); assertTrue(grown[1] === old[0])
    }

    @Test fun `the new video button does not oscillate on bounce or small changes`() {
        val f = com.videomk.app.core.FabCollapse()
        assertTrue(f.update(0)); assertTrue(f.update(30)); assertTrue(f.update(47))
        assertFalse(f.update(48))
        // a bouncing or clamped list near the threshold, or a few px of extent change, never flips it
        for (o in listOf(49, 47, 50, 40, 20, 12, 9, 40, 12)) assertFalse("offset $o", f.update(o))
        assertFalse(f.update(Int.MAX_VALUE))   // far down or at the bottom edge: stays collapsed
        assertTrue(f.update(8)); for (o in listOf(0, 20, 47, 5, 30)) assertTrue("offset $o", f.update(o))
    }

    @Test fun `select all respects the limit, mixed sources and the view`() {
        val view = (1..38).map { "p$it" }
        // everything fits
        assertEquals(view, com.videomk.app.core.SelectAll.toAdd(view, emptyList(), 100))
        // 6 already chosen (in view or not): only the missing ones are added, in view order
        val have = listOf("p3", "p5", "other1")
        val add = com.videomk.app.core.SelectAll.toAdd(view, have, 100)
        assertEquals(36, add.size); assertFalse("p3" in add); assertEquals("p1", add.first())
        // photos from the phone use up room: limit 100 - 90 = 10 for My media
        val tight = com.videomk.app.core.SelectAll.toAdd((1..60).map { "q$it" }, emptyList(), 10)
        assertEquals((1..10).map { "q$it" }, tight)
        assertEquals(0, com.videomk.app.core.SelectAll.toAdd(view, (1..10).map { "z$it" }, 10).size)
        // labels
        assertEquals("Select all 38", com.videomk.app.core.SelectAll.label(false, 38))
        assertEquals("Select all", com.videomk.app.core.SelectAll.label(false, null))
        assertEquals("Clear", com.videomk.app.core.SelectAll.label(true, 38))
        // all selected: Clear; more pages not loaded and below the limit: not all
        assertTrue(com.videomk.app.core.SelectAll.allSelected(view, view, 100, false))
        assertFalse(com.videomk.app.core.SelectAll.allSelected(view, view, 100, true))
        assertTrue(com.videomk.app.core.SelectAll.allSelected(view, view, 38, true))   // the limit stopped it
        assertFalse(com.videomk.app.core.SelectAll.allSelected(emptyList(), emptyList(), 100, false))
        assertTrue(com.videomk.app.core.SelectAll.allSelected(view, (1..10).map { "p$it" }, 10, true))   // 10 of 38 selected and the limit is 10
        // another view (a collection, a search) is judged on its own photos
        assertFalse(com.videomk.app.core.SelectAll.allSelected(listOf("c1", "c2"), view, 100, false))
        // counts: exact when nothing more to load, else the known total, else unknown
        assertEquals(38, com.videomk.app.core.SelectAll.viewCount(38, false, 500))
        assertEquals(240, com.videomk.app.core.SelectAll.viewCount(60, true, 240))
        assertEquals(null, com.videomk.app.core.SelectAll.viewCount(60, true, null))
        assertEquals("Selected the first 100: the limit for one video.", com.videomk.app.core.SelectAll.limitNote(100))
        assertTrue(com.videomk.app.core.SelectAll.limitNote(60).contains("40 come from your phone"))
    }

    private val PAYLOAD = """{"aspects":[{"id":"16:9","label":"Landscape","ready":true,"beta":false},{"id":"9:16","label":"Vertical","ready":true,"beta":true},{"id":"1:1","label":"Square","ready":true,"beta":true},{"id":"4:5","label":"Portrait","ready":true,"beta":true}],
        "resolutions":[{"id":"720p","label":"720p"},{"id":"1080p","label":"1080p"}],
        "platforms":[{"id":"linkedin","label":"LinkedIn","aspect":"4:5","resolution":"1080p","recommended_minutes":1,"max_minutes":10,"other_aspects":["1:1","16:9"],"note":"Portrait 4:5 · 1080p · about 1 min"},
          {"id":"x","label":"X","aspect":"16:9","resolution":"1080p","recommended_minutes":0.75,"max_minutes":2.3333,"other_aspects":[],"note":"Landscape 16:9 · 1080p · about 45 s"},
          {"id":"shorts","label":"YouTube Shorts","aspect":"9:16","resolution":"1080p","recommended_minutes":0.5,"max_minutes":3,"other_aspects":[],"note":"Vertical 9:16 · 1080p · about 30 s"},
          {"id":"youtube","label":"YouTube","aspect":"16:9","resolution":"1080p","recommended_minutes":3,"max_minutes":null,"other_aspects":[],"note":"Landscape 16:9 · 1080p · about 3 min"}],
        "languages":[],"lengths":{"min_minutes":0.25,"max_minutes":12,"presets":[0.25,0.5,0.75,1,2,3,5,8,12]},"max_photos":100,"intake":true}"""

    @Test fun `short lengths with presets credits labels and capacity`() {
        val c = Capabilities.fromJson(com.videomk.app.core.parseObject(PAYLOAD))
        assertEquals(listOf(0.25, 0.5, 0.75, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0), c.presets); assertEquals(0.25, c.minMinutes, 0.0)
        assertEquals(listOf("15 s", "30 s", "45 s", "1 min", "2 min"), c.presets.take(5).map { com.videomk.app.core.Lengths.short(it) })
        assertEquals(listOf(1, 1, 1, 1, 2), c.presets.take(5).map { com.videomk.app.core.Lengths.credits(it) })
        assertEquals(2, CreateOptions(61.0 / 60).credits); assertEquals(1, CreateOptions(0.25).credits)
        assertEquals(12, com.videomk.app.core.PhotoCapacity.capacity(0.25)); assertEquals(25, com.videomk.app.core.PhotoCapacity.capacity(0.5))
        assertEquals(38, com.videomk.app.core.PhotoCapacity.capacity(0.75)); assertEquals(51, com.videomk.app.core.PhotoCapacity.capacity(1.0))
        assertEquals("About 12 of your 30 photos fit in 15 seconds (the best ones, no duplicates). Choose 45 seconds to show them all.", com.videomk.app.core.PhotoCapacity.hint(30, 0.25, c.presets)!!.replace("Choose 45 seconds", "Choose 45 seconds"))
        // no `lengths` in the payload: the old presets
        assertEquals(com.videomk.app.core.Lengths.OLD_PRESETS, Capabilities.fromJson(com.videomk.app.core.parseObject(PAYLOAD.replace(Regex("\"lengths\":\\{[^}]*\\},"), ""))).presets)
        // the old whole-minute choice is still remembered; 45 s too
        assertEquals(0.75, CreateDefaults.resolve(CreatePrefs("other", "16:9", "1080p", 0.75, null, true, "auto"), c).minutes, 0.0)
        assertEquals(com.videomk.app.core.CreatePrefs.fromJson(CreatePrefs("other", "16:9", "1080p", 0.25, null, true, "auto").toJson())!!.minutes, 0.25, 0.0)
    }

    @Test fun `LinkedIn and X recommend different formats and lengths, and a length chosen first is kept`() {
        val c = Capabilities.fromJson(com.videomk.app.core.parseObject(PAYLOAD))
        val linkedin = com.videomk.app.core.CreatePlatforms.chip(c, "linkedin")!!; val x = com.videomk.app.core.CreatePlatforms.chip(c, "x")!!
        val a = com.videomk.app.core.CreatePlatforms.select(CreateOptions(), linkedin, false, c.presets)
        assertEquals("4:5", a.aspect); assertEquals(1.0, a.minutes, 0.0)
        assertEquals("LinkedIn · Portrait 4:5 · 1080p · about 1 min", com.videomk.app.core.CreatePlatforms.recommendation(a, c))
        val b = com.videomk.app.core.CreatePlatforms.select(a, x, false, c.presets)
        assertEquals("16:9", b.aspect); assertEquals(0.75, b.minutes, 0.0)
        assertEquals("X · Landscape 16:9 · 1080p · about 45 s", com.videomk.app.core.CreatePlatforms.recommendation(b, c))
        // the person chose 5 min first: the platform pick keeps it, only the recommendation changes
        val kept = com.videomk.app.core.CreatePlatforms.select(CreateOptions(5.0), x, true, c.presets)
        assertEquals(5.0, kept.minutes, 0.0); assertEquals("16:9", kept.aspect)
        // also works: other formats, never the one in use; picking one makes the line "Custom"
        assertEquals(listOf("1:1", "16:9"), com.videomk.app.core.CreatePlatforms.alsoWorks(a, c).map { it.id })
        assertEquals(listOf("16:9"), com.videomk.app.core.CreatePlatforms.alsoWorks(a.copy(aspect = "1:1"), c).map { it.id }.filter { it == "16:9" })
        assertTrue(com.videomk.app.core.CreatePlatforms.recommendation(a.copy(aspect = "1:1"), c).startsWith("Custom"))
        // over the platform's maximum: a gentle hint with the longest preset that fits
        val over = com.videomk.app.core.CreatePlatforms.overMax(b.copy(minutes = 3.0), c)!!
        assertEquals("X allows up to 2:20", over.text); assertEquals(2.0, over.useMinutes!!, 0.0)
        assertEquals(null, com.videomk.app.core.CreatePlatforms.overMax(b.copy(minutes = 2.0), c))
        assertEquals(null, com.videomk.app.core.CreatePlatforms.overMax(CreateOptions(12.0, platform = "youtube"), c))
    }

    @Test fun `chips never get a fixed width that crops and fit by label length`() {
        val en = "Biological evolution and early hominids"; val es = "Civilizaciones antiguas hasta la edad media"
        assertEquals(com.videomk.app.core.ChipFit.SingleLine, com.videomk.app.core.ChipLayout.fit("Kids", 340f, 1f))
        assertEquals(com.videomk.app.core.ChipFit.SingleLine, com.videomk.app.core.ChipLayout.fit("Making honey", 340f, 1f))
        // 40 to 43 characters on a phone: not one line, never cut
        for (label in listOf(en, es, "Evolución biológica y primeros homínidos")) {
            assertTrue(label, com.videomk.app.core.ChipLayout.fit(label, 340f, 1f) != com.videomk.app.core.ChipFit.SingleLine)
        }
        // bigger text only ever needs more room, never less
        val order = listOf(com.videomk.app.core.ChipFit.SingleLine, com.videomk.app.core.ChipFit.Wrapped, com.videomk.app.core.ChipFit.FullWidth)
        for (label in listOf("Kids", "Beginners and experts alike", en, es)) {
            var last = 0
            for (scale in listOf(1f, 1.3f, 1.5f, 2f)) { val f = order.indexOf(com.videomk.app.core.ChipLayout.fit(label, 320f, scale)); assertTrue("$label @ $scale", f >= last); last = f }
        }
        // at 2x text a 36-character label gets a full-width row (three lines at most)
        assertEquals(com.videomk.app.core.ChipFit.FullWidth, com.videomk.app.core.ChipLayout.fit(es, 320f, 2f))
        assertEquals(3, com.videomk.app.core.ChipLayout.maxLines(com.videomk.app.core.ChipFit.FullWidth))
        assertEquals(1, com.videomk.app.core.ChipLayout.maxLines(com.videomk.app.core.ChipFit.SingleLine))
        // a narrow container (360 x 640 phone, small sheet) is handled the same way
        assertTrue(com.videomk.app.core.ChipLayout.fit("Beginners", 120f, 1.5f) != com.videomk.app.core.ChipFit.SingleLine)
    }
}
