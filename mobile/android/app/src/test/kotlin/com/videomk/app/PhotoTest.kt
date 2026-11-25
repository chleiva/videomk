package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.ApiError
import com.videomk.app.core.MultipartForm
import com.videomk.app.core.PhotoGeometry
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.PhotoUploader
import com.videomk.app.core.PhotoCapacity
import com.videomk.app.core.PhotoIntake
import com.videomk.app.core.boundedMap
import com.videomk.app.core.prepareInOrder
import com.videomk.app.core.PickedCache
import com.videomk.app.core.PickedSource
import mockwebserver3.Dispatcher
import mockwebserver3.RecordedRequest
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertFalse
import java.io.IOException
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class PhotoTest {
    // geometry (the pixel work itself is covered by the instrumented PhotoPrepTest on a real decoder)

    @Test fun `photos are scaled down to at most 2048 and never up`() {
        assertEquals(2048 to 1536, PhotoGeometry.fit(4000, 3000))
        assertEquals(1536 to 2048, PhotoGeometry.fit(3000, 4000))
        assertEquals(2048 to 2048, PhotoGeometry.fit(5000, 5000))
        assertEquals(800 to 600, PhotoGeometry.fit(800, 600))
        assertEquals(2048 to 1, PhotoGeometry.fit(100_000, 40))
        assertTrue(PhotoGeometry.fit(100_000, 10).second >= 1)
    }

    @Test fun `sample size decodes small but never below the target`() {
        assertEquals(1, PhotoGeometry.sampleSize(2000, 1500)); assertEquals(1, PhotoGeometry.sampleSize(4000, 3000))
        assertEquals(2, PhotoGeometry.sampleSize(4096, 3072)); assertEquals(4, PhotoGeometry.sampleSize(8192, 6144))
        assertEquals(8, PhotoGeometry.sampleSize(16384, 12288))
        for (w in listOf(100, 3000, 4032, 9000, 12000)) assertTrue(w / PhotoGeometry.sampleSize(w, w) >= minOf(w, 2048))
    }

    @Test fun `EXIF orientations map to rotation and mirroring`() {
        assertEquals(0 to false, PhotoGeometry.orientation(1)); assertEquals(90 to false, PhotoGeometry.orientation(6))
        assertEquals(180 to false, PhotoGeometry.orientation(3)); assertEquals(270 to false, PhotoGeometry.orientation(8))
        assertEquals(0 to true, PhotoGeometry.orientation(2)); assertEquals(180 to true, PhotoGeometry.orientation(4))
        assertEquals(270 to true, PhotoGeometry.orientation(5)); assertEquals(90 to true, PhotoGeometry.orientation(7))
        assertEquals(0 to false, PhotoGeometry.orientation(0)); assertEquals(0 to false, PhotoGeometry.orientation(99))
    }

    // multipart

    @Test fun `multipart puts the signed fields first, sorted, and the file last`() {
        val file = byteArrayOf(1, 2, 3, 0, -1)
        val built = MultipartForm.body(mapOf("key" to "uploads/u/1.jpg", "Content-Type" to "image/jpeg", "policy" to "P=="), file, boundary = "BOUND")
        assertEquals("multipart/form-data; boundary=BOUND", built.contentType)
        val text = String(built.body, Charsets.ISO_8859_1)
        val keys = Regex("form-data; name=\"([^\"]+)\"").findAll(text).map { it.groupValues[1] }.toList()
        assertEquals(listOf("Content-Type", "key", "policy", "file"), keys)
        assertTrue(text.contains("name=\"file\"; filename=\"photo.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"))
        assertTrue(text.endsWith("\r\n--BOUND--\r\n"))
        // the file's bytes are in the body untouched, right before the closing boundary
        val tail = built.body.copyOfRange(built.body.size - "\r\n--BOUND--\r\n".length - file.size, built.body.size - "\r\n--BOUND--\r\n".length)
        assertTrue(tail.contentEquals(file))
    }

    // uploader

    private lateinit var server: MockWebServer
    private lateinit var storage: MockWebServer
    @Before fun setUp() { server = MockWebServer().apply { start() }; storage = MockWebServer().apply { start() } }
    @After fun tearDown() { server.close(); storage.close() }

    private fun slotsJson(n: Int) = """{"uploads":[${(1..n).joinToString(",") { """{"id":"id$it","url":"${storage.url("/bucket")}","fields":{"key":"uploads/u/id$it.jpg","policy":"P$it"}}""" }}]}"""

    @Test fun `upload requests slots, posts each photo without the login token and reports progress`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = slotsJson(3)))
        repeat(3) { storage.enqueue(MockResponse.Builder().code(204).build()) }
        val progress = mutableListOf<Pair<Int, Int>>()
        val ids = PhotoUploader(api, OkHttpClient(), parallelism = 1).upload(listOf(byteArrayOf(1), byteArrayOf(2), byteArrayOf(3))) { d, t -> progress += d to t }
        assertEquals(listOf("id1", "id2", "id3"), ids)
        assertEquals(listOf(0 to 3, 1 to 3, 2 to 3, 3 to 3), progress)
        val slotReq = server.takeRequest()
        assertEquals("/prod/users/user-1/uploads", slotReq.url.encodedPath)
        assertTrue(slotReq.body!!.utf8().contains("\"count\":3"))
        repeat(3) { i ->
            val r = storage.takeRequest()
            assertNull("the login token must never go to storage", r.headers["Authorization"])
            assertTrue(r.headers["Content-Type"]!!.startsWith("multipart/form-data; boundary="))
            assertTrue(r.body!!.utf8().contains("uploads/u/id${i + 1}.jpg"))
        }
    }

    @Test fun `a failed storage post fails the upload and a retry can run again`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = slotsJson(2)))
        repeat(PhotoLimits.UPLOAD_TRIES + 1) { storage.enqueue(MockResponse.Builder().code(403).build()) }   // photo 1 is refused on every try, photo 2 on its first
        storage.enqueue(MockResponse.Builder().code(204).build())
        storage.enqueue(MockResponse.Builder().code(204).build())
        try { PhotoUploader(api, OkHttpClient(), parallelism = 1, backoffMillis = { 0 }).upload(listOf(byteArrayOf(1), byteArrayOf(2))); fail() } catch (e: ApiError) { assertTrue(e is ApiError.Invalid) }
        server.enqueue(json(body = slotsJson(2)))
        repeat(2) { storage.enqueue(MockResponse.Builder().code(204).build()) }
        assertEquals(listOf("id1", "id2"), PhotoUploader(api, OkHttpClient(), backoffMillis = { 0 }).upload(listOf(byteArrayOf(1), byteArrayOf(2))))
    }

    @Test fun `wrong photo counts are rejected before anything is requested`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        for (n in listOf(0, PhotoLimits.MAX_PHOTOS + 1)) {
            try { PhotoUploader(api, OkHttpClient()).upload(List(n) { byteArrayOf(1) }); fail() } catch (e: ApiError.Invalid) { /* expected */ }
        }
        assertEquals(0, server.requestCount)
    }

    @Test fun `a server that returns the wrong number of slots is a server error`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = slotsJson(1)))
        try { PhotoUploader(api, OkHttpClient()).upload(listOf(byteArrayOf(1), byteArrayOf(2))); fail() } catch (e: ApiError) { assertEquals(ApiError.Server, e) }
    }

    // 100 photos

    @Test fun `the cap is 100 and the uploader accepts 100 in one presign call and refuses 101`() = runBlocking {
        assertEquals(100, PhotoLimits.MAX_PHOTOS)
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = slotsJson(100)))
        storage.dispatcher = object : Dispatcher() { override fun dispatch(request: RecordedRequest) = MockResponse.Builder().code(204).build() }
        val progress = java.util.Collections.synchronizedList(mutableListOf<Int>())
        val ids = PhotoUploader(api, OkHttpClient()).upload(List(100) { byteArrayOf(it.toByte()) }) { d, _ -> progress += d }
        assertEquals((1..100).map { "id$it" }, ids)
        assertEquals(1, server.requestCount)
        assertTrue(server.takeRequest().body!!.utf8().contains("\"count\":100"))
        assertEquals((0..100).toList(), progress.toList())
        try { PhotoUploader(api, OkHttpClient()).upload(List(101) { byteArrayOf(1) }); fail() } catch (e: ApiError.Invalid) { assertTrue(e.message.contains("100")) }
    }

    @Test fun `a photo that fails once is retried and the upload succeeds`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = slotsJson(1)))
        storage.enqueue(MockResponse.Builder().code(500).build())
        storage.enqueue(MockResponse.Builder().code(204).build())
        assertEquals(listOf("id1"), PhotoUploader(api, OkHttpClient(), backoffMillis = { 0 }).upload(listOf(byteArrayOf(1))))
        assertEquals(2, storage.requestCount)
    }

    @Test fun `photos that still fail after three tries fail the upload with a clear count, the others are uploaded`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = slotsJson(4)))
        val attempts = java.util.concurrent.ConcurrentHashMap<String, Int>()
        storage.dispatcher = object : Dispatcher() {
            override fun dispatch(request: RecordedRequest): MockResponse {
                val body = request.body!!.utf8()
                val bad = body.contains("id2.jpg") || body.contains("id4.jpg")
                attempts.merge(if (body.contains("id2.jpg")) "id2" else if (body.contains("id4.jpg")) "id4" else "ok", 1, Int::plus)
                return MockResponse.Builder().code(if (bad) 503 else 204).build()
            }
        }
        val reported = java.util.concurrent.atomic.AtomicInteger()
        try {
            PhotoUploader(api, OkHttpClient(), backoffMillis = { 0 }).upload(List(4) { byteArrayOf(it.toByte()) }) { d, _ -> reported.set(maxOf(reported.get(), d)) }
            fail()
        } catch (e: ApiError.Invalid) {
            assertTrue(e.message, e.message.startsWith("2 of 4 photos couldn't be uploaded"))
        }
        assertEquals(3, attempts["id2"]); assertEquals(3, attempts["id4"]); assertEquals(2, attempts["ok"])
        assertEquals(2, reported.get())
    }

    @Test fun `uploads never run more than the parallelism at once`() = runBlocking {
        val inFlight = java.util.concurrent.atomic.AtomicInteger(); val peak = java.util.concurrent.atomic.AtomicInteger()
        val r = boundedMap((1..30).toList(), 4) { _, n ->
            peak.accumulateAndGet(inFlight.incrementAndGet(), ::maxOf)
            kotlinx.coroutines.delay(5)
            inFlight.decrementAndGet(); n * 2
        }
        assertEquals((1..30).map { it * 2 }, r)
        assertEquals(4, peak.get())
    }

    @Test fun `preparation runs a few at a time and delivers results in order`() = runBlocking {
        val inFlight = java.util.concurrent.atomic.AtomicInteger(); val peak = java.util.concurrent.atomic.AtomicInteger()
        val seen = mutableListOf<Pair<Int, Int>>()
        prepareInOrder((0 until 100).toList(), PhotoLimits.PREP_PARALLELISM, prepare = { n ->
            peak.accumulateAndGet(inFlight.incrementAndGet(), ::maxOf)
            kotlinx.coroutines.delay(((100 - n) % 7).toLong())   // finish out of order on purpose
            inFlight.decrementAndGet(); n
        }) { i, r -> seen += i to r }
        assertEquals((0 until 100).map { it to it }, seen)
        assertEquals(PhotoLimits.PREP_PARALLELISM, peak.get())
    }

    @Test fun `a selection keeps the first photos that fit and says how many were left out`() {
        assertEquals(PhotoIntake(7, 0), PhotoIntake.plan(7, 100))
        assertEquals(PhotoIntake(30, 20), PhotoIntake.plan(50, 30))
        assertEquals(PhotoIntake(0, 5), PhotoIntake.plan(5, 0))
        assertEquals(PhotoIntake(0, 0), PhotoIntake.plan(0, 10))
        assertEquals("1 photo was left out: a video can use up to 100.", PhotoIntake.leftOutMessage(1))
        assertEquals("20 photos were left out: a video can use up to 100.", PhotoIntake.leftOutMessage(20))
    }

    @Test fun `the picker asks for at most the platform maximum per round, never more than the room left, and never fewer than 2`() {
        assertEquals(100, PhotoIntake.pickerMax(1000, 100))
        assertEquals(50, PhotoIntake.pickerMax(50, 100))      // several rounds to reach 100
        assertEquals(40, PhotoIntake.pickerMax(50, 40))
        assertEquals(2, PhotoIntake.pickerMax(50, 1))         // the contract refuses 1; the extra photo is left out by the intake plan
        assertEquals(2, PhotoIntake.pickerMax(1, 100))
    }

    @Test fun `preparing text counts the photo in progress within the batch`() {
        assertEquals("Preparing 1 of 100", PhotoIntake.preparingText(0, 100))
        assertEquals("Preparing 37 of 100", PhotoIntake.preparingText(36, 100))
        assertEquals("Preparing 100 of 100", PhotoIntake.preparingText(100, 100))
    }

    @Test fun `chooser result uses the several uris when present, else the single one, without duplicates`() {
        assertEquals(listOf("a", "b"), PhotoIntake.extract("x", listOf("a", "b", "a")))
        assertEquals(listOf("x"), PhotoIntake.extract("x", emptyList()))
        assertEquals(emptyList<String>(), PhotoIntake.extract(null, emptyList()))
        // then capped at the room left, the rest reported
        val picked = PhotoIntake.extract(null, (1..130).map { "p$it" })
        val plan = PhotoIntake.plan(picked.size, 100)
        assertEquals(PhotoIntake(100, 30), plan)
        assertEquals("p100", picked.take(plan.accepted).last())
    }

    // private copies of picked photos

    private fun tmp() = java.nio.file.Files.createTempDirectory("picked").toFile()

    @Test fun `copy streams the bytes into a private file and keeps picking order by name`() {
        val root = tmp(); val cache = PickedCache(java.io.File(root, "s"))
        val data = mapOf("a" to ByteArray(300_000) { it.toByte() }, "b" to byteArrayOf(9, 8, 7))
        val src = PickedSource<String> { data[it]?.inputStream() }
        val files = listOf("a", "b").map { cache.copy(it, src)!! }
        assertTrue(files[0].readBytes().contentEquals(data["a"]!!)); assertTrue(files[1].readBytes().contentEquals(data["b"]!!))
        assertEquals(listOf("1.src", "2.src"), files.map { it.name })
        assertEquals(2, cache.files().size)
        root.deleteRecursively()
    }

    @Test fun `an unreadable, empty, throwing or oversized source gives null and leaves no file`() {
        val root = tmp(); val cache = PickedCache(java.io.File(root, "s"), maxBytes = 10)
        assertNull(cache.copy("missing", PickedSource { null }))
        assertNull(cache.copy("boom", PickedSource { throw SecurityException("grant gone") }))
        assertNull(cache.copy("empty", PickedSource { ByteArray(0).inputStream() }))
        assertNull(cache.copy("big", PickedSource { ByteArray(11).inputStream() }))
        assertNull(cache.copy("io", PickedSource { object : java.io.InputStream() { override fun read(): Int = throw IOException("gone") } }))
        assertEquals(0, cache.files().size)
        assertNotNull(cache.copy("ok", PickedSource { ByteArray(10).inputStream() }))
        root.deleteRecursively()
    }

    @Test fun `ending the session deletes the folder, and a new start removes leftovers`() {
        val root = tmp(); val cache = PickedCache(java.io.File(root, "s"))
        val f = cache.copy("a", PickedSource { byteArrayOf(1).inputStream() })!!
        assertTrue(f.exists())
        cache.endSession(); assertFalse(f.exists()); assertEquals(0, cache.files().size)
        val crashed = PickedCache(java.io.File(root, "s2")); val g = crashed.copy("a", PickedSource { byteArrayOf(1).inputStream() })!!
        PickedCache.cleanLeftovers(root); assertFalse(g.exists()); assertFalse(root.exists())
    }

    @Test fun `copying in order with a few at a time keeps order and the unreadable ones as nulls`() = runBlocking {
        val root = tmp(); val cache = PickedCache(java.io.File(root, "s"))
        val items = (0 until 20).toList()
        val src = PickedSource<Int> { if (it % 5 == 0) null else byteArrayOf(it.toByte()).inputStream() }
        val out = mutableListOf<java.io.File?>()
        prepareInOrder(items, PhotoLimits.PREP_PARALLELISM, prepare = { cache.copy(it, src) }) { _, f -> out += f }
        assertEquals(items.map { if (it % 5 == 0) null else it.toByte() }, out.map { it?.readBytes()?.single() })
        assertEquals(4, out.count { it == null })
        root.deleteRecursively(); Unit
    }

    // length vs photos

    private val lengths = listOf(1, 2, 3, 5, 8, 12)

    @Test fun `capacity is floor of 51 per minute`() {
        assertEquals(51, PhotoCapacity.capacity(1.0)); assertEquals(102, PhotoCapacity.capacity(2.0)); assertEquals(153, PhotoCapacity.capacity(3.0))
        assertEquals(255, PhotoCapacity.capacity(5.0)); assertEquals(3, PhotoCapacity.capacity(0.0))   // never fewer than 3 photos
    }

    @Test fun `minimum minutes for 100 photos is just under two`() {
        assertEquals(118 / 60.0, PhotoCapacity.minimumMinutes(100), 0.0001)   // 118 s: floor(118 x 0.85) = 100
        assertEquals(0.0, PhotoCapacity.minimumMinutes(0), 0.0)
        for (n in 1..153) assertTrue(PhotoCapacity.capacity(PhotoCapacity.minimumMinutes(n) + 1e-6) >= n)   // the two formulas agree
    }

    @Test fun `no hint with no photos, at capacity, and a hint one over`() {
        assertNull(PhotoCapacity.hint(0, 1.0, lengths))
        assertNull(PhotoCapacity.hint(51, 1.0, lengths)); assertNull(PhotoCapacity.hint(102, 2.0, lengths))
        assertEquals("About 51 of your 52 photos fit in 1 minute (the best ones, no duplicates). Choose 2 minutes to show them all.", PhotoCapacity.hint(52, 1.0, lengths))
        assertEquals("About 102 of your 103 photos fit in 2 minutes (the best ones, no duplicates). Choose 3 minutes to show them all.", PhotoCapacity.hint(103, 2.0, lengths))
    }

    @Test fun `100 photos at each length option`() {
        assertEquals("About 51 of your 100 photos fit in 1 minute (the best ones, no duplicates). Choose 2 minutes to show them all.", PhotoCapacity.hint(100, 1.0, lengths))
        for (m in listOf(2, 3, 5, 8, 12)) assertNull(PhotoCapacity.hint(100, m.toDouble(), lengths))
    }

    @Test fun `when no option is long enough the hint says so`() {
        assertEquals("About 51 of your 100 photos fit in the longest video.", PhotoCapacity.hint(100, 1.0, listOf(1)))
        assertEquals("About 51 of your 60 photos fit in the longest video.", PhotoCapacity.hint(60, 1.0, listOf(1)))
    }
}
