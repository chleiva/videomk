package com.videomk.app

import com.videomk.app.core.*
import com.videomk.app.ui.AppViewModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.File
import java.nio.file.Files
import java.time.Instant
import kotlin.coroutines.EmptyCoroutineContext

private val CAPS = DeckCaps(maxMb = 50, maxSlides = 60, formats = listOf("pptx", "pdf"))
private val PDF_BYTES = "%PDF-1.7 a few slides".toByteArray()
private val PPTX_BYTES = byteArrayOf('P'.code.toByte(), 'K'.code.toByte(), 3, 4, 0, 0, 0, 0)

private fun pdfPick(name: String? = "Quarterly review.pdf", bytes: ByteArray = PDF_BYTES, size: Long? = bytes.size.toLong(), mime: String? = "application/pdf") =
    DeckPick(name, mime, size) { ByteArrayInputStream(bytes) }

/** The three calls, scripted: [statuses] are answered one per look, the last one repeating. */
private class ScriptedDeckApi(var statuses: List<DeckStatus> = listOf(DeckStatus.Processing, DeckStatus.Ready(DeckReady("d1", 12, 4.0, 4)))) : DeckApi {
    var slotError: Exception? = null
    var processError: Exception? = null
    var statusError: Exception? = null
    val slots = mutableListOf<Pair<DeckFormat, Long>>()
    var processed = 0
    var looks = 0
    override suspend fun createSlot(format: DeckFormat, size: Long): DeckSlot {
        slotError?.let { throw it }
        slots += format to size
        return DeckSlot("d1", format, "https://storage.example/up", mapOf("key" to "decks/u/d1"), null)
    }
    override suspend fun process(id: String) { processError?.let { throw it }; processed++ }
    override suspend fun status(id: String): DeckStatus { statusError?.let { throw it }; return statuses[minOf(looks++, statuses.size - 1)] }
}

private class RecordingUploader(var error: Exception? = null, val gate: CompletableDeferred<Unit>? = null) : DeckUploader {
    val seen = mutableListOf<Pair<Boolean, Long>>()   // (the copy existed while uploading, its size)
    override suspend fun upload(slot: DeckSlot, file: File, progress: (Long, Long) -> Unit) {
        seen += file.exists() to file.length()
        progress(file.length() / 2, file.length())
        gate?.await()
        error?.let { throw it }
        progress(file.length(), file.length())
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class DeckTest {
    private lateinit var root: File
    private var clock = 0L
    private val states = mutableListOf<DeckState>()

    @Before fun setUp() { root = Files.createTempDirectory("deck").toFile().resolve("deck"); clock = 0; states.clear() }
    @After fun tearDown() { root.parentFile.deleteRecursively() }

    private fun journey(scope: kotlinx.coroutines.CoroutineScope, api: DeckApi? = ScriptedDeckApi(), up: DeckUploader? = RecordingUploader()) =
        DeckJourney(scope, root, onState = { states += it }, wait = { clock += it }, nowMillis = { clock }, io = EmptyCoroutineContext).also { it.attach(api, up) }

    // ---- capabilities: the feature exists only when the server says so

    @Test fun `capabilities carry deck only when the server sends it`() {
        val without = Capabilities.fromJson(Json.parseToJsonElement("""{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}]}""").jsonObject)
        assertNull(without.deck)
        val with = Capabilities.fromJson(Json.parseToJsonElement("""{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}],"deck":{"max_mb":40,"max_slides":30,"formats":["pdf","keynote"]}}""").jsonObject)
        assertEquals(DeckCaps(40, 30, listOf("pdf")), with.deck)   // a format this app cannot send is dropped
        assertEquals(listOf("application/pdf"), with.deck!!.mimeTypes.toList())
        assertEquals(40L * 1024 * 1024, with.deck!!.maxBytes)
        assertEquals(listOf("pptx", "pdf"), Capabilities.fromJson(Json.parseToJsonElement("""{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}],"deck":{}}""").jsonObject).deck!!.formats)
        assertEquals(2, CAPS.mimeTypes.size)
    }

    // ---- format and size checks before anything is uploaded

    @Test fun `format and size are checked on the phone first`() {
        fun check(name: String?, mime: String?, size: Long?) = DeckRules.check(name, mime, size, CAPS)
        assertEquals(DeckCheck.Ok(DeckFormat.Pptx), check("Deck.PPTX", null, 1000))
        assertEquals(DeckCheck.Ok(DeckFormat.Pdf), check("deck.pdf", "application/pdf", 1000))
        assertEquals(DeckCheck.Ok(DeckFormat.Pdf), check(null, "application/pdf", null))   // a provider that gives no name: the type decides
        assertEquals(DeckCheck.Ok(DeckFormat.Pdf), check("deck.pdf", null, null))   // a provider that gives no size: the copy counts for itself
        for (n in listOf("old.ppt", "macro.pptm", "show.ppsx", "talk.key", "deck.odp", "x.docx")) assertEquals(n, DeckCheck.Rejected(DeckProblem.Unsupported), check(n, null, 1000))
        assertEquals(DeckCheck.Rejected(DeckProblem.Unsupported), check("photo.jpg", "image/jpeg", 1000))
        assertEquals(DeckCheck.Rejected(DeckProblem.Unsupported), check(null, null, 1000))
        assertEquals(DeckCheck.Rejected(DeckProblem.Empty), check("a.pdf", null, 0))
        assertEquals(DeckCheck.Ok(DeckFormat.Pdf), check("a.pdf", null, CAPS.maxBytes))
        assertEquals(DeckCheck.Rejected(DeckProblem.TooLarge), check("a.pdf", null, CAPS.maxBytes + 1))
        assertEquals(DeckCheck.Rejected(DeckProblem.Unsupported), DeckRules.check("a.pptx", null, 10, DeckCaps(50, 60, listOf("pdf"))))   // the server lists pdf only
    }

    @Test fun `the first bytes must fit the format`() {
        assertNull(DeckRules.sniff(DeckFormat.Pdf, PDF_BYTES)); assertNull(DeckRules.sniff(DeckFormat.Pptx, PPTX_BYTES))
        assertEquals(DeckProblem.Corrupt, DeckRules.sniff(DeckFormat.Pdf, PPTX_BYTES))
        assertEquals(DeckProblem.Corrupt, DeckRules.sniff(DeckFormat.Pptx, "hello".toByteArray()))
        assertEquals(DeckProblem.Unsupported, DeckRules.sniff(DeckFormat.Pptx, byteArrayOf(0xD0.toByte(), 0xCF.toByte(), 0x11, 0xE0.toByte())))   // an old .ppt renamed
        assertEquals(DeckProblem.Corrupt, DeckRules.sniff(DeckFormat.Pdf, ByteArray(0)))
    }

    // ---- the server's codes become calm, specific messages with the right next step

    @Test fun `every server code has its own message and action`() {
        val expect = mapOf(
            "deck_too_large" to (DeckProblem.TooLarge to DeckAction.PickAgain), "deck_too_many_slides" to (DeckProblem.TooManySlides to DeckAction.PickAgain),
            "deck_encrypted" to (DeckProblem.Encrypted to DeckAction.PickAgain), "deck_macro" to (DeckProblem.Macro to DeckAction.PickAgain),
            "deck_corrupt" to (DeckProblem.Corrupt to DeckAction.PickAgain), "deck_unsupported" to (DeckProblem.Unsupported to DeckAction.PickAgain),
            "deck_empty" to (DeckProblem.Empty to DeckAction.PickAgain), "deck_unsafe" to (DeckProblem.Unsafe to DeckAction.PickAgain),
            "deck_convert_timeout" to (DeckProblem.Timeout to DeckAction.PickAgain), "deck_convert_failed" to (DeckProblem.ConvertFailed to DeckAction.PickAgain),
            "too_many_decks" to (DeckProblem.DailyLimit to DeckAction.None), "unavailable" to (DeckProblem.Unavailable to DeckAction.None),
        )
        val titles = HashSet<String>()
        for ((code, want) in expect) {
            val p = DeckProblem.fromCode(code)
            assertEquals(code, want.first, p); assertEquals(code, want.second, p.action)
            val f = DeckFailure(p, "server words")
            assertTrue(code, f.title().isNotBlank() && f.body(CAPS).isNotBlank() && !f.body(CAPS).contains("server words"))
            assertTrue("title of $code is its own", titles.add(f.title()))
        }
        assertEquals(DeckProblem.Other, DeckProblem.fromCode("deck_from_the_future"))
        assertEquals("Please try a smaller one.", DeckFailure(DeckProblem.Other, "Please try a smaller one.").body(CAPS))   // an unknown code shows the server's words
        assertTrue(DeckFailure(DeckProblem.TooLarge).body(DeckCaps(30, 60, listOf("pdf"))).contains("30 MB"))
        assertTrue(DeckFailure(DeckProblem.TooManySlides).body(DeckCaps(50, 25, listOf("pdf"))).contains("25"))
        assertEquals(DeckAction.Retry, DeckProblem.Offline.action); assertEquals(DeckAction.Retry, DeckProblem.UploadFailed.action); assertEquals(DeckAction.KeepWaiting, DeckProblem.Stalled.action)
    }

    @Test fun `the messages also exist in Spanish`() {
        val old = Txt.provider
        try {
            Txt.provider = JvmStringProvider("es")
            for (p in DeckProblem.entries) { assertTrue(p.name, DeckFailure(p).title().isNotBlank()); assertFalse(p.name, DeckFailure(p).body(CAPS).contains("deck_err")) }
            assertEquals("Ese archivo tiene contraseña", DeckFailure(DeckProblem.Encrypted).title())
            assertEquals("Leyendo tus diapositivas.", MakingSteps.deckSentence(VideoStatus.DeckStage.Reading))
            assertEquals("Escribiendo la narración.", MakingSteps.deckSentence(VideoStatus.DeckStage.Writing))
        } finally { Txt.provider = old }
    }

    // ---- the journey

    @Test fun `a good file is copied, uploaded with progress, processed, polled and ready, and nothing stays on the phone`() = runTest {
        val api = ScriptedDeckApi(); val up = RecordingUploader()
        val j = journey(this, api, up)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        val ready = j.state as DeckState.Ready
        assertEquals(DeckReady("d1", 12, 4.0, 4), ready.info); assertEquals("Quarterly review.pdf", ready.name)
        assertEquals(listOf(DeckFormat.Pdf to PDF_BYTES.size.toLong()), api.slots)   // the real size and format were asked for
        assertEquals(listOf(true to PDF_BYTES.size.toLong()), up.seen)   // the private copy existed during the upload
        assertEquals(1, api.processed)
        assertEquals(0, j.filesOnDisk())   // deleted as soon as the upload finished
        val kinds = states.map { it::class.simpleName }
        assertTrue(kinds.indexOf("Copying") < kinds.indexOf("Uploading") && kinds.indexOf("Uploading") < kinds.indexOf("Processing") && kinds.indexOf("Processing") < kinds.indexOf("Ready"))
        assertTrue(states.filterIsInstance<DeckState.Uploading>().any { it.percent in 40..60 })
        assertEquals(ready.info, j.ready)
    }

    @Test fun `a pptx goes up as pptx`() = runTest {
        val api = ScriptedDeckApi()
        journey(this, api).start(pdfPick("Plan.pptx", PPTX_BYTES, mime = null), CAPS); advanceUntilIdle()
        assertEquals(DeckFormat.Pptx, api.slots.single().first)
    }

    @Test fun `polling backs off, stays quiet on the network and never goes past five seconds`() {
        assertEquals(2000, DeckBackoff.intervalMillis(0)); assertEquals(2000, DeckBackoff.intervalMillis(4)); assertEquals(2500, DeckBackoff.intervalMillis(5))
        assertEquals(5000, DeckBackoff.intervalMillis(500))
        var last = 0L; for (i in 0..200) { val v = DeckBackoff.intervalMillis(i); assertTrue(v >= last && v <= 5000); last = v }
    }

    @Test fun `a deck the server rejects shows its specific message`() = runTest {
        for (code in listOf("deck_encrypted", "deck_macro", "deck_too_many_slides", "deck_corrupt", "deck_empty", "deck_unsafe", "deck_convert_timeout", "deck_convert_failed", "deck_unsupported", "deck_too_large")) {
            states.clear()
            val api = ScriptedDeckApi(listOf(DeckStatus.Processing, DeckStatus.Failed(code, "server text")))
            val j = journey(this, api)
            j.start(pdfPick(), CAPS); advanceUntilIdle()
            val f = (j.state as DeckState.Failed).failure
            assertEquals(code, DeckProblem.fromCode(code), f.problem)
            assertEquals(0, j.filesOnDisk())
        }
    }

    @Test fun `too large or the wrong kind is refused before any request`() = runTest {
        val api = ScriptedDeckApi()
        val j = journey(this, api)
        j.start(pdfPick(size = CAPS.maxBytes + 1), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.TooLarge, (j.state as DeckState.Failed).failure.problem)
        j.start(pdfPick(name = "talk.key", mime = null), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.Unsupported, (j.state as DeckState.Failed).failure.problem)
        j.start(pdfPick(bytes = ByteArray(0), size = null), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.Empty, (j.state as DeckState.Failed).failure.problem)
        j.start(pdfPick(bytes = PPTX_BYTES, size = null), CAPS); advanceUntilIdle()   // a zip named .pdf
        assertEquals(DeckProblem.Corrupt, (j.state as DeckState.Failed).failure.problem)
        assertTrue(api.slots.isEmpty()); assertEquals(0, j.filesOnDisk())
    }

    @Test fun `a provider that lies about the size is stopped while copying`() = runTest {
        val small = DeckCaps(1, 60, listOf("pdf"))
        val big = ByteArray(1024 * 1024 + 10) { 'x'.code.toByte() }.also { System.arraycopy(PDF_BYTES, 0, it, 0, 4) }
        val api = ScriptedDeckApi()
        val j = journey(this, api)
        j.start(DeckPick("a.pdf", "application/pdf", 10) { ByteArrayInputStream(big) }, small); advanceUntilIdle()
        assertEquals(DeckProblem.TooLarge, (j.state as DeckState.Failed).failure.problem)
        assertTrue(api.slots.isEmpty()); assertEquals(0, j.filesOnDisk())
    }

    @Test fun `an unreadable file is a calm failure`() = runTest {
        val j = journey(this)
        j.start(DeckPick("a.pdf", null, null) { null }, CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.Corrupt, (j.state as DeckState.Failed).failure.problem)
        j.start(DeckPick("a.pdf", null, null) { throw java.io.IOException("gone") }, CAPS); advanceUntilIdle()
        assertTrue(j.state is DeckState.Failed)
    }

    @Test fun `cancelling mid upload stops, deletes the copy and returns to idle`() = runTest {
        val gate = CompletableDeferred<Unit>()
        val api = ScriptedDeckApi(); val up = RecordingUploader(gate = gate)
        val j = journey(this, api, up)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        assertTrue(j.state is DeckState.Uploading); assertEquals(1, j.filesOnDisk())
        j.cancel(); advanceUntilIdle()
        assertEquals(DeckState.Idle, j.state); assertEquals(0, j.filesOnDisk()); assertEquals(0, api.processed)
        gate.complete(Unit); advanceUntilIdle()
        assertEquals(DeckState.Idle, j.state)   // nothing resurrects it
    }

    @Test fun `an upload that fails offline keeps the copy for Try again and then succeeds`() = runTest {
        val api = ScriptedDeckApi(); val up = RecordingUploader(error = ApiError.Network)
        val j = journey(this, api, up)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        val f = (j.state as DeckState.Failed).failure
        assertEquals(DeckProblem.Offline, f.problem); assertEquals(DeckAction.Retry, f.problem.action)
        assertEquals(1, j.filesOnDisk())   // kept only for the retry
        up.error = null
        j.retry(); advanceUntilIdle()
        assertTrue(j.state is DeckState.Ready); assertEquals(0, j.filesOnDisk()); assertEquals(2, api.slots.size)
        j.cancel()
    }

    @Test fun `a storage refusal says the upload did not finish and the daily limit has no retry`() = runTest {
        val up = RecordingUploader(error = ApiError.Invalid(""))
        val j = journey(this, ScriptedDeckApi(), up)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.UploadFailed, (j.state as DeckState.Failed).failure.problem)
        j.cancel()
        val api = ScriptedDeckApi().also { it.slotError = ApiError.Deck("too_many_decks", "x") }
        val k = journey(this, api)
        k.start(pdfPick(), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.DailyLimit, (k.state as DeckState.Failed).failure.problem)
        assertEquals(0, k.filesOnDisk())   // nothing to retry: the copy goes
    }

    @Test fun `losing the connection after the upload means keep waiting, never a second upload`() = runTest {
        val api = ScriptedDeckApi().also { it.processError = ApiError.Network }
        val up = RecordingUploader()
        val j = journey(this, api, up)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.Stalled, (j.state as DeckState.Failed).failure.problem)
        assertEquals(0, j.filesOnDisk()); assertEquals(1, up.seen.size)
        api.processError = null
        j.keepWaiting(); advanceUntilIdle()
        assertTrue(j.state is DeckState.Ready); assertEquals(1, up.seen.size); assertEquals(1, api.processed)   // process was asked again (harmless)
    }

    @Test fun `a deck still processing after a sensible time stops waiting and offers to keep waiting`() = runTest {
        val api = ScriptedDeckApi(listOf(DeckStatus.Processing))
        val j = journey(this, api)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        val f = (j.state as DeckState.Failed).failure
        assertEquals(DeckProblem.Stalled, f.problem); assertTrue(clock >= DeckBackoff.GIVE_UP_MILLIS && clock < DeckBackoff.GIVE_UP_MILLIS + 10_000)
        api.statuses = listOf(DeckStatus.Ready(DeckReady("d1", 3, 1.0, 1)))
        j.keepWaiting(); advanceUntilIdle()
        assertEquals(3, (j.state as DeckState.Ready).info.slides)
    }

    @Test fun `a flaky status call is tolerated and a run of failures gives up`() = runTest {
        val api = ScriptedDeckApi()
        val j = journey(this, api)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        assertTrue(j.state is DeckState.Ready)
        val bad = ScriptedDeckApi().also { it.statusError = ApiError.Network }
        val k = journey(this, bad)
        k.start(pdfPick(), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.Stalled, (k.state as DeckState.Failed).failure.problem)
        assertTrue(clock < 20_000)
    }

    @Test fun `a missing deck while polling ends the wait with the server code`() = runTest {
        val api = ScriptedDeckApi().also { it.statusError = ApiError.Deck("missing", "gone") }
        val j = journey(this, api)
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        assertEquals(DeckProblem.Other, (j.state as DeckState.Failed).failure.problem)
    }

    @Test fun `picking another file replaces the first and removing deletes everything`() = runTest {
        val gate = CompletableDeferred<Unit>()
        val j = journey(this, ScriptedDeckApi(), RecordingUploader(gate = gate))
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        assertEquals(1, j.filesOnDisk())
        j.start(pdfPick("Second.pdf"), CAPS); advanceUntilIdle()
        assertEquals(1, j.filesOnDisk()); assertEquals("Second.pdf", (j.state as DeckState.Uploading).name)
        j.cancel(); advanceUntilIdle()
        assertEquals(0, j.filesOnDisk()); assertEquals(DeckState.Idle, j.state)
    }

    @Test fun `release and the app start clear leftovers`() = runTest {
        val gate = CompletableDeferred<Unit>()
        val j = journey(this, ScriptedDeckApi(), RecordingUploader(gate = gate))
        j.start(pdfPick(), CAPS); advanceUntilIdle()
        assertEquals(1, j.filesOnDisk())
        j.release(); advanceUntilIdle()
        assertFalse(root.exists())
        root.mkdirs(); File(root, "left-behind.tmp").writeText("x")
        DeckJourney.cleanLeftovers(root)
        assertFalse(root.exists())
    }

    @Test fun `the temporary copy has no readable name and nothing is written outside the folder`() = runTest {
        val gate = CompletableDeferred<Unit>()
        val j = journey(this, ScriptedDeckApi(), RecordingUploader(gate = gate))
        j.start(pdfPick("Salary plan 2027 - CONFIDENTIAL.pdf"), CAPS); advanceUntilIdle()
        val names = root.listFiles()!!.map { it.name }
        assertEquals(1, names.size); assertTrue(names.single().endsWith(".tmp")); assertFalse(names.single().contains("Salary") || names.single().contains("pdf"))
        j.cancel()
    }

    // ---- photos and a presentation exclude each other

    @Test fun `a presentation replaces photos only after the person agreed`() = runTest {
        var photos = 3
        val j = journey(this)
        val a = DeckAttachment(j, { photos }, { photos = 0 })
        assertFalse(a.add(pdfPick(), CAPS, replacePhotos = false))
        assertEquals(3, photos); assertEquals(DeckState.Idle, j.state)   // nothing changed
        assertTrue(a.add(pdfPick(), CAPS, replacePhotos = true)); advanceUntilIdle()
        assertEquals(0, photos); assertTrue(j.state is DeckState.Ready)
        photos = 0
        assertTrue(a.add(pdfPick("Other.pdf"), CAPS, replacePhotos = false))   // no photos: no question
        j.cancel()
    }

    @Test fun `choosing photos removes the presentation in any state and deletes its copy`() = runTest {
        val gate = CompletableDeferred<Unit>()
        val j = journey(this, ScriptedDeckApi(), RecordingUploader(gate = gate))
        val a = DeckAttachment(j, { 0 }, {})
        a.add(pdfPick(), CAPS, false); advanceUntilIdle()
        assertTrue(j.state is DeckState.Uploading); assertEquals(1, j.filesOnDisk())
        a.photosChosen(); advanceUntilIdle()
        assertEquals(DeckState.Idle, j.state); assertEquals(0, j.filesOnDisk())
        a.photosChosen()   // nothing attached: nothing happens
        assertEquals(DeckState.Idle, j.state)
    }

    // ---- the form: suggested length, price, the landscape default and the vertical warning

    @Test fun `a ready presentation uses its suggested length and price until another length is picked`() {
        val info = DeckReady("d1", 12, 4.0, 4)
        val base = CreateOptions(minutes = 0.5)
        val o = DeckOptions.onReady(base, info)
        assertEquals(4.0, o.minutes, 0.0); assertEquals(4, o.credits); assertTrue(o.useSuggestedLength)
        val picked = DeckOptions.chooseLength(o, 2.0)
        assertEquals(2, picked.credits); assertFalse(picked.useSuggestedLength)   // the usual rule (started minutes), no server price
        assertTrue(DeckOptions.useSuggestion(picked, info).useSuggestedLength)
        assertEquals(0.5, DeckOptions.onGone(o, 0.5).minutes, 0.0); assertFalse(DeckOptions.onGone(o, 0.5).useSuggestedLength)
        assertEquals(2.0, DeckOptions.onGone(picked, 0.5).minutes, 0.0)   // a length the person chose stays
        assertEquals(DeckOptions.onReady(base, DeckReady("d", 5, 0.5, 1)).credits, 1)
        assertEquals(2, DeckOptions.onReady(base, DeckReady("d", 40, 11.2, 2)).credits)   // the server's number is the one shown, whatever the local rule says
    }

    @Test fun `slides default to landscape and a vertical or portrait picture warns, square does not`() {
        val caps = Capabilities(
            aspects = listOf(AspectInfo("16:9", "Landscape", true, false), AspectInfo("9:16", "Vertical", true, true), AspectInfo("1:1", "Square", true, false), AspectInfo("4:5", "Portrait", true, false)),
            resolutions = listOf(ResolutionInfo("1080p", "1080p")), platforms = emptyList(), languages = emptyList(), deck = CAPS,
        )
        val shorts = CreateOptions(platform = "shorts", aspect = "9:16")
        assertTrue(DeckOptions.verticalWarning(shorts, true)); assertFalse(DeckOptions.verticalWarning(shorts, false))
        assertTrue(DeckOptions.verticalWarning(CreateOptions(aspect = "4:5"), true))
        assertFalse(DeckOptions.verticalWarning(CreateOptions(aspect = "1:1"), true)); assertFalse(DeckOptions.verticalWarning(CreateOptions(), true))
        val fixed = DeckOptions.landscape(shorts.copy(minutes = 3.0, suggestedCredits = 4), caps)
        assertEquals("16:9", fixed.aspect); assertEquals(3.0, fixed.minutes, 0.0); assertEquals(4, fixed.credits)
        assertFalse(DeckOptions.verticalWarning(fixed, true))
    }

    @Test fun `a card without a description is titled with the file name`() {
        assertEquals("Quarterly review", DeckOptions.title("Quarterly review.pptx")); assertEquals("noext", DeckOptions.title("noext")); assertNull(DeckOptions.title(null)); assertNull(DeckOptions.title("   "))
    }

    // ---- the Create button and its status line

    private fun st(text: String, deck: DeckState?, o: CreateOptions = CreateOptions(minutes = 4.0, suggestedCredits = 4), balance: Int? = 20) =
        ComposerLogic.status(text, o, balance, 0, listening = false, sending = false, createScreen = true, deck = deck)
    private val ready = DeckState.Ready("a.pdf", DeckReady("d1", 12, 4.0, 4))

    @Test fun `with a presentation the description is optional and Create waits for the deck`() {
        assertTrue(st("", ready).sendReady); assertEquals("4 credits · you'll have 16 left", st("", ready).text)
        assertTrue(st("for executives, short and direct", ready).sendReady)
        assertEquals(StatusKind.TooShort, st("for kids", ready).kind); assertFalse(st("for kids", ready).sendReady)   // the server wants 10 characters or none
        for (s in listOf(DeckState.Copying("a"), DeckState.Uploading("a", 1, 2), DeckState.Processing("a"))) { assertEquals(StatusKind.DeckWaiting, st("", s).kind); assertFalse(st("", s).sendReady) }
        assertEquals(StatusKind.DeckWaiting, st("", DeckState.Failed("a", DeckFailure(DeckProblem.Macro))).kind)
        assertEquals(StatusKind.TooLong, st("x".repeat(2100), ready).kind)
        // without a presentation nothing changed: an empty description still blocks
        assertEquals(StatusKind.TooShort, st("", null, CreateOptions()).kind)
    }

    @Test fun `the price and the balance check use the suggested credits`() {
        assertEquals(StatusKind.NotAffordable, st("", ready, balance = 3).kind)
        assertEquals(3.0, st("", ready, balance = 3).fix!!.minutes!!, 0.0)   // the longest length that fits what is left
        assertEquals(StatusKind.NoCredits, st("", ready, balance = 0).kind)
        assertTrue(st("", ready, balance = null).sendReady)
        assertTrue(st("", ready, CreateOptions(minutes = 2.0), balance = 2).sendReady)   // a shorter length the person picked fits
    }

    // ---- the API

    private lateinit var server: MockWebServer
    private fun api() = ApiClient(configFor(server), FixedAuth(), locale = { "es" })

    private inline fun withServer(block: () -> Unit) { server = MockWebServer().also { it.start() }; try { block() } finally { server.close() } }

    @Test fun `the slot request sends format and size with the locale, and parses the presigned post`() = withServer {
        runBlocking {
            server.enqueue(json(body = """{"deck":{"id":"d-9","format":"pptx","url":"https://s3.example/b","fields":{"key":"k","Content-Type":"x","policy":"p"}},"max_bytes":52428800,"expires_in":900}"""))
            val slot = ApiDeckApi(api()).createSlot(DeckFormat.Pptx, 12345)
            val r = server.takeRequest()
            assertEquals("POST", r.method); assertEquals("/prod/users/user-1/decks", r.url.encodedPath); assertEquals("es", r.headers["X-Locale"])
            val body = Json.parseToJsonElement(r.body!!.utf8()).jsonObject
            assertEquals("pptx", body["format"]!!.jsonPrimitive.content); assertEquals(12345L, body["size"]!!.jsonPrimitive.content.toLong())
            assertEquals("d-9", slot.id); assertEquals(listOf("key", "Content-Type", "policy"), slot.fields.keys.toList()); assertEquals(52428800L, slot.maxBytes)
        }
    }

    @Test fun `process and status use the documented paths`() = withServer {
        runBlocking {
            server.enqueue(json(202, """{"status":"processing"}"""))
            server.enqueue(json(body = """{"id":"d-9","status":"processing","format":"pdf"}"""))
            server.enqueue(json(body = """{"id":"d-9","status":"ready","slides":12,"suggested_minutes":4.0,"suggested_credits":4}"""))
            server.enqueue(json(body = """{"id":"d-9","status":"failed","code":"deck_macro","message":"Macros inside"}"""))
            val a = ApiDeckApi(api())
            a.process("d-9"); assertEquals("/prod/users/user-1/decks/d-9/process", server.takeRequest().url.encodedPath)
            assertEquals(DeckStatus.Processing, a.status("d-9")); val g = server.takeRequest(); assertEquals("GET", g.method); assertEquals("/prod/users/user-1/decks/d-9", g.url.encodedPath); assertEquals("es", g.headers["X-Locale"])
            assertEquals(DeckStatus.Ready(DeckReady("d-9", 12, 4.0, 4)), a.status("d-9")); server.takeRequest()
            assertEquals(DeckStatus.Failed("deck_macro", "Macros inside"), a.status("d-9"))
        }
    }

    @Test fun `deck errors keep the server code`() = withServer {
        runBlocking {
            server.enqueue(json(400, """{"code":"deck_too_large","message":"Too big"}"""))
            server.enqueue(json(429, """{"code":"too_many_decks","message":"Ten a day"}"""))
            server.enqueue(json(404, """{"code":"unavailable","message":"Off"}"""))
            server.enqueue(json(404, """{"code":"missing","message":"Gone"}"""))
            server.enqueue(json(400, """{"code":"missing","message":"Upload first"}"""))
            val a = ApiDeckApi(api())
            for (want in listOf("deck_too_large", "too_many_decks", "unavailable", "missing", "missing")) {
                try { a.createSlot(DeckFormat.Pdf, 10); fail() } catch (e: ApiError.Deck) { assertEquals(want, e.code) }
            }
            assertEquals("Ten a day", ApiError.Deck("too_many_decks", "Ten a day").message)
        }
    }

    @Test fun `generate with a deck sends the id, no empty prompt, and a length only when the person chose one`() = withServer {
        runBlocking {
            server.enqueue(json(body = """{"video_id":"v-1"}""")); server.enqueue(json(body = """{"video_id":"v-2"}""")); server.enqueue(json(body = """{"video_id":"v-3"}"""))
            val c = api()
            c.startGeneration("", "r1", CreateOptions(minutes = 4.0, suggestedCredits = 4), deck = "d-9")
            val a = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
            assertEquals("d-9", a["deck"]!!.jsonPrimitive.content); assertFalse("prompt" in a); assertFalse("target_minutes" in a); assertFalse("media" in a)
            c.startGeneration("  for  executives and a long enough text ", "r2", CreateOptions(minutes = 2.0), deck = "d-9")
            val b = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
            assertEquals("for executives and a long enough text", b["prompt"]!!.jsonPrimitive.content); assertEquals(2.0, b["target_minutes"]!!.jsonPrimitive.content.toDouble(), 0.0)
            c.startGeneration("A plain video about bees", "r3", CreateOptions(minutes = 2.0))   // a normal video is exactly as before
            val p = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
            assertFalse("deck" in p); assertEquals(2.0, p["target_minutes"]!!.jsonPrimitive.content.toDouble(), 0.0)
        }
    }

    @Test fun `generate with a deck maps the deck refusals`() = withServer {
        runBlocking {
            server.enqueue(json(400, """{"code":"deck_missing","message":"That presentation expired"}"""))
            server.enqueue(json(409, """{"code":"deck_not_ready","message":"Not ready"}"""))
            server.enqueue(json(402, """{"balance":1,"needed":4}"""))
            server.enqueue(json(400, """{"message":"Choose photos or a presentation"}"""))
            val c = api()
            try { c.startGeneration("", "r", CreateOptions(), deck = "d"); fail() } catch (e: ApiError.Deck) { assertEquals("deck_missing", e.code) }
            try { c.startGeneration("", "r", CreateOptions(), deck = "d"); fail() } catch (e: ApiError.Deck) { assertEquals("deck_not_ready", e.code) }
            try { c.startGeneration("", "r", CreateOptions(), deck = "d"); fail() } catch (e: ApiError.InsufficientCredits) { assertEquals(4, e.needed) }
            try { c.startGeneration("", "r", CreateOptions(), deck = "d"); fail() } catch (e: ApiError.Invalid) { assertEquals("Choose photos or a presentation", e.text) }
        }
    }

    @Test fun `the upload form streams the fields first and the file last, with progress`() {
        val dir = Files.createTempDirectory("form").toFile()
        try {
            val f = File(dir, "x.tmp").also { it.writeBytes(ByteArray(200_000) { i -> (i % 251).toByte() }) }
            val slot = DeckSlot("d", DeckFormat.Pdf, "https://s3.example/b", linkedMapOf("key" to "decks/u/d", "policy" to "p", "x-amz-signature" to "s"), null)
            val seen = mutableListOf<Long>()
            val body = DeckFormBody(slot, f, { sent, _ -> seen += sent }, boundary = "BOUND")
            val buf = okio.Buffer(); body.writeTo(buf)
            assertEquals(buf.size, body.contentLength())
            assertEquals("multipart/form-data; boundary=BOUND", body.contentType().toString())
            val text = buf.readByteString().utf8()
            val order = listOf("name=\"key\"", "name=\"policy\"", "name=\"x-amz-signature\"", "name=\"Content-Type\"", "name=\"file\"").map { text.indexOf(it) }
            assertTrue(order.all { it >= 0 }); assertEquals(order.sorted(), order)   // the server's fields in its order, the missing content type added, the file last
            assertTrue(text.contains("Content-Type: application/pdf") && text.endsWith("--BOUND--\r\n"))
            assertEquals(200_000L, seen.last()); assertEquals(0L, seen.first()); assertEquals(seen.sorted(), seen)
            val own = DeckSlot("d", DeckFormat.Pdf, "https://s3.example/b", mapOf("Content-Type" to "application/pdf"), null)
            val b2 = okio.Buffer(); DeckFormBody(own, f, { _, _ -> }, "B").writeTo(b2)
            assertEquals(1, Regex("name=\"Content-Type\"").findAll(b2.readUtf8()).count())   // not doubled when the server already has it
        } finally { dir.deleteRecursively() }
    }

    @Test fun `the upload goes to the storage address without any login token`() = withServer {
        runBlocking {
            server.enqueue(json(204, ""))
            val dir = Files.createTempDirectory("up").toFile()
            try {
                val f = File(dir, "x.tmp").also { it.writeBytes(PDF_BYTES) }
                var last = 0L
                HttpDeckUploader(OkHttpClient()).upload(DeckSlot("d", DeckFormat.Pdf, server.url("/bucket").toString(), mapOf("key" to "k"), null), f) { sent, _ -> last = sent }
                val r = server.takeRequest()
                assertNull(r.headers["Authorization"]); assertEquals(PDF_BYTES.size.toLong(), last)
                assertTrue(r.body!!.utf8().contains("%PDF"))
                server.enqueue(json(403, "<Error/>"))
                try { HttpDeckUploader(OkHttpClient()).upload(DeckSlot("d", DeckFormat.Pdf, server.url("/bucket").toString(), emptyMap(), null), f) { _, _ -> }; fail() } catch (e: ApiError.Invalid) { }
            } finally { dir.deleteRecursively() }
        }
    }

    // ---- the waiting experience

    @Test fun `the server's deck stages become the stage line and then the usual steps`() {
        assertEquals(VideoStatus.Running(VideoStatus.Stage.Writing, VideoStatus.DeckStage.Reading), VideoStatus.fromServer("PLOT_CREATION", "deck_reading"))
        assertEquals(VideoStatus.Running(VideoStatus.Stage.Writing, VideoStatus.DeckStage.Writing), VideoStatus.fromServer("PLOT_CREATION", "deck_writing"))
        assertEquals(VideoStatus.Running(VideoStatus.Stage.Writing), VideoStatus.fromServer("PLOT_CREATION", null))
        assertEquals(VideoStatus.Running(VideoStatus.Stage.VoiceAndVisuals), VideoStatus.fromServer("ASSETS_CREATION", "deck_writing"))   // afterwards the stage is ignored
        assertEquals(VideoStatus.Running(VideoStatus.Stage.Rendering), VideoStatus.fromServer("RENDERING", "deck_reading"))
        val item = VideoItem.fromJson(Json.parseToJsonElement("""{"video_id":"v","status":"PLOT_CREATION","stage":"deck_reading"}""").jsonObject)
        assertEquals(VideoStatus.DeckStage.Reading, (item.status as VideoStatus.Running).deck)

        val reading = MakingSnapshot.ofDeck("Q3 review", VideoStatus.DeckStage.Reading, 0.0, 4.0)
        val writing = MakingSnapshot.ofDeck("Q3 review", VideoStatus.DeckStage.Writing, 0.0, 4.0)
        assertEquals("Reading your slides.", reading.stageLine); assertEquals("Writing the narration.", writing.stageLine)
        assertEquals(0, reading.current); assertEquals(0, writing.current)   // still inside the first usual step (Script)
        assertTrue(reading.fills.sum() < writing.fills.sum() + 1e-6 || writing.fills[0] > 0f)
        // the bar never goes backwards from reading to writing to the usual steps, and never passes the end of its slice
        var last = -1.0
        for (d in VideoStatus.DeckStage.entries) for (t in listOf(0.0, 10.0, 100.0, 1_000_000.0)) {
            val f = ProgressEstimator.deckFraction(d, t); val (lo, hi) = ProgressEstimator.deckSlice(d)
            assertTrue(f >= lo && f < hi); if (t == 0.0) assertTrue(f >= last - 1e-9); last = f
        }
        assertEquals(ProgressEstimator.deckSlice(VideoStatus.DeckStage.Reading).second, ProgressEstimator.deckSlice(VideoStatus.DeckStage.Writing).first, 1e-9)
        assertEquals(ProgressEstimator.slice(VideoStatus.Stage.Writing).second, ProgressEstimator.deckSlice(VideoStatus.DeckStage.Writing).second, 1e-9)
        assertTrue(reading.eta!!.isNotBlank())
    }

    // ---- a request made from a presentation

    @Test fun `a presentation request carries the deck, shows its name and cannot be retried from its text`() = runBlocking {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        val backend = FakeBackend(); val s = MockWebServer().apply { start() }
        try {
            val store = InMemoryTokenStore().also { it.save(Tokens(fakeJwt(), "a", "r", Instant.now().plusSeconds(3000))) }
            val vm = AppViewModel(backend, AuthService(configFor(s), store, OkHttpClient()), configFor(s), MutableSharedFlow(extraBufferCapacity = 1))
            val out = vm.submitAwait("", CreateOptions(minutes = 4.0, suggestedCredits = 4), deck = "d-9", deckTitle = "Q3 review")
            assertEquals(SubmitOutcome.Accepted, out)
            assertEquals(listOf<String?>("d-9"), backend.startDecks); assertEquals("", backend.startCalls.single().first)
            assertTrue(backend.startOptions.single().useSuggestedLength)
            val st = vm.state.value
            assertEquals("Q3 review", st.briefs[backend.newVideoId]); assertTrue(backend.newVideoId in st.deckVideos)
            vm.submitAwait("A plain video about bees", CreateOptions(), intake = null)
            assertEquals(null, backend.startDecks.last()); assertEquals(1, vm.state.value.deckVideos.size)
        } finally { Dispatchers.resetMain(); s.close() }
    }

    @Test fun `a running deck video moves its stage clock when the stage changes`() = runBlocking {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        val backend = FakeBackend(); val s = MockWebServer().apply { start() }
        try {
            val store = InMemoryTokenStore().also { it.save(Tokens(fakeJwt(), "a", "r", Instant.now().plusSeconds(3000))) }
            var now = 1000L
            val vm = AppViewModel(backend, AuthService(configFor(s), store, OkHttpClient()), configFor(s), MutableSharedFlow(extraBufferCapacity = 1), clock = { now })
            fun v(d: VideoStatus.DeckStage?) = VideoItem("v", VideoStatus.Running(VideoStatus.Stage.Writing, d))
            backend.videos = listOf(v(VideoStatus.DeckStage.Reading)); vm.refresh()
            assertEquals(1000L, vm.state.value.stageSince["v"]!!.sinceMillis)
            now = 9000L; backend.videos = listOf(v(VideoStatus.DeckStage.Reading)); vm.refresh()
            assertEquals(1000L, vm.state.value.stageSince["v"]!!.sinceMillis)   // same stage: the clock keeps running
            backend.videos = listOf(v(VideoStatus.DeckStage.Writing)); vm.refresh()
            assertEquals(9000L, vm.state.value.stageSince["v"]!!.sinceMillis); assertEquals(VideoStatus.DeckStage.Writing, vm.state.value.stageSince["v"]!!.deck)
        } finally { Dispatchers.resetMain(); s.close() }
    }

    // ---- account deletion and sign-out

    @Test fun `the wiper removes the presentation's temporary copies and the source says so`() {
        val src = File("src/main/kotlin/com/videomk/app/data/LocalDataWiper.kt").readText()
        assertTrue("deck cache step", src.contains("deck-cache") && src.contains("deckCache"))
        val container = File("src/main/kotlin/com/videomk/app/AppContainer.kt").readText()
        assertTrue(container.contains("deckCache = java.io.File(appContext.cacheDir, \"deck\")"))
        // the journey stores its copies only under the cache folder, which the wiper empties as well
        val vm = File("src/main/kotlin/com/videomk/app/ui/ComposerViewModel.kt").readText()
        assertTrue(vm.contains("java.io.File(app.cacheDir, \"deck\")"))
        val root = File("src/main/kotlin/com/videomk/app/ui/Root.kt").readText()
        assertTrue("sign-out drops the presentation", root.contains("composer.removeDeck()"))
        val main = File("src/main/kotlin/com/videomk/app/MainActivity.kt").readText()
        assertTrue("deletion cancels an upload before wiping", main.indexOf("composer.clearAfterSend()") < main.indexOf("container.wipeLocalData()"))
    }

    @Test fun `deck code never logs and never keeps a permission`() {
        val files = listOf("core/Deck.kt", "core/DeckCompose.kt", "data/DeckPicker.kt", "ui/DeckUi.kt").map { File("src/main/kotlin/com/videomk/app/$it").readText() }
        for (t in files) { assertFalse(t.contains("Log.")); assertFalse(t.contains("println(")); assertFalse(t.contains("takePersistableUriPermission(")) }
        assertTrue(File("src/main/kotlin/com/videomk/app/ui/CreateScreen.kt").readText().contains("ActivityResultContracts.OpenDocument()"))
        assertFalse(File("src/main/AndroidManifest.xml").readText().contains("READ_EXTERNAL_STORAGE"))
    }
}
