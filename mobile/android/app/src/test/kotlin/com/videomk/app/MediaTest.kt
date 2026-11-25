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
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.time.ZoneId
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger

private fun photo(id: String, taken: String? = null, added: String = "2025-03-10T12:00:00Z", place: String? = null) =
    MediaPhoto(id, taken, added, place, 100, 100, 1000, "https://t/$id")

private class FakeMedia : MediaApi {
    val uploadCalls = mutableListOf<List<UploadRequestItem>>()
    var answer: (List<UploadRequestItem>) -> UploadsResponse = { items -> UploadsResponse(items.mapIndexed { i, _ -> UploadSlotResult(i, SlotStatus.Upload, "m$i-${uploadCalls.size}", "https://s3/x", mapOf("key" to "k$i"), null, null) }, 10, 100) }
    var failure: ApiError? = null
    override suspend fun requestUploads(items: List<UploadRequestItem>): UploadsResponse { uploadCalls += items; failure?.let { throw it }; return answer(items) }
    override suspend fun summary() = error("unused")
    override suspend fun items(limit: Int, cursor: String?, filter: MediaFilter) = error("unused")
    override suspend fun item(id: String) = error("unused")
    override suspend fun delete(ids: List<String>) = error("unused")
    override suspend fun search(query: String, limit: Int, drop: List<String>, cursor: String?) = error("unused")
    override suspend fun collections() = error("unused")
    override suspend fun createCollection(name: String, emoji: String?) = error("unused")
    override suspend fun updateCollection(id: String, name: String?, emoji: String?) = error("unused")
    override suspend fun deleteCollection(id: String) = error("unused")
    override suspend fun editCollection(id: String, add: List<String>, remove: List<String>) = error("unused")
    override suspend fun organizePreview(since: String?) = error("unused")
    override suspend fun organizeApply(single: Boolean, since: String?, name: String?, collectionId: String?) = error("unused")
    override suspend fun setOrganizePref(pref: OrganizePref) = error("unused")
}

private class Blobs : BlobSource {
    val files = HashMap<String, ByteArray>()
    override fun read(path: String) = files[path]
    override fun delete(path: String) { files.remove(path) }
}

class MediaTest {
    // ---- storage meter

    @Test fun `meter is ok below 85 percent, warning from 85, full at the limit`() {
        assertEquals(StorageMeter.State.Ok, StorageMeter.state(849, 1000))
        assertEquals(StorageMeter.State.Warning, StorageMeter.state(850, 1000))
        assertEquals(StorageMeter.State.Warning, StorageMeter.state(999, 1000))
        assertEquals(StorageMeter.State.Full, StorageMeter.state(1000, 1000))
        assertEquals(StorageMeter.State.Full, StorageMeter.state(1200, 1000))
        assertEquals(StorageMeter.State.Ok, StorageMeter.state(0, 0))
        assertEquals("1.2 GB of 2 GB", StorageMeter.label(1_200_000_000, 2_000_000_000))
        assertEquals("640 MB", StorageMeter.format(640_000_000)); assertEquals("12 KB", StorageMeter.format(12_000))
    }

    // ---- grouping

    private val utc = ZoneId.of("UTC")

    @Test fun `photos group under month headers newest first, by taken day else added day`() {
        val items = listOf(
            photo("a", taken = "2025-03-02T10:00:00"), photo("b", taken = "2025-03-20T10:00:00"), photo("c", taken = "2025-01-05T09:00:00"),
            photo("d", taken = null, added = "2025-02-14T08:00:00Z"),
        )
        val g = MediaGrouping.group(items, utc, Locale.ENGLISH)
        assertEquals(listOf("March 2025", "February 2025", "January 2025"), g.map { it.title })
        assertEquals(listOf("b", "a"), g[0].items.map { it.id })
        assertEquals(listOf("d"), g[1].items.map { it.id })
    }

    @Test fun `added time is read in the persons time zone`() {
        val p = photo("x", taken = null, added = "2025-03-01T01:30:00Z")
        assertEquals("March 2025", MediaGrouping.group(listOf(p), ZoneId.of("UTC"), Locale.ENGLISH).single().title)
        assertEquals("February 2025", MediaGrouping.group(listOf(p), ZoneId.of("America/Los_Angeles"), Locale.ENGLISH).single().title)
        // taken is wall-clock time and is never shifted
        val t = photo("y", taken = "2025-03-01T01:30:00")
        assertEquals("March 2025", MediaGrouping.group(listOf(t), ZoneId.of("America/Los_Angeles"), Locale.ENGLISH).single().title)
    }

    @Test fun `a busy month gets day headers`() {
        val items = (1..35).map { photo("p$it", taken = "2025-03-${"%02d".format(1 + it % 28)}T10:00:00") }
        val g = MediaGrouping.group(items, utc, Locale.ENGLISH)
        assertTrue(g.size > 1); assertTrue(g.all { it.title.contains("March 2025") })
        assertEquals(35, g.sumOf { it.items.size })
        assertEquals(g.map { it.key }, g.map { it.key }.sortedDescending())   // days newest first
    }

    @Test fun `photos with no usable time go to an undated group and labels read date and place`() {
        val g = MediaGrouping.group(listOf(photo("z", taken = "garbage", added = "")), utc, Locale.ENGLISH)
        assertEquals("Undated", g.single().title)
        assertEquals("Photo from 2 March 2025 in Phuket, Thailand", MediaLabels.photo(photo("a", taken = "2025-03-02T10:00:00", place = "Phuket, Thailand"), utc, Locale.ENGLISH))
    }

    // ---- search debounce

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `typing fires one search after the pause, a blank query fires at once`() = runTest {
        val fired = mutableListOf<String>()
        val d = SearchDebouncer(this, 400) { fired += it }
        d.submit("b"); advanceTimeBy(100); d.submit("be"); advanceTimeBy(100); d.submit("beach "); advanceTimeBy(399)
        assertEquals(emptyList<String>(), fired)
        advanceTimeBy(2); runCurrent()
        assertEquals(listOf("beach"), fired)
        d.submit(""); runCurrent()
        assertEquals(listOf("beach", ""), fired)
    }

    @Test fun `dropping a chip keeps the question, a new question forgets the drops`() {
        val s = SearchState("holidays in Thailand 2024").drop("2024").drop("2024")
        assertEquals(listOf("2024"), s.dropped); assertEquals("holidays in Thailand 2024", s.query)
        assertEquals(emptyList<String>(), s.withQuery("cats").dropped)
    }

    @Test fun `the prompt looks like photos from the library`() {
        assertTrue(PromptSearch.looksLikePhotoRequest("a video of my holidays in Thailand in 2024"))
        assertTrue(PromptSearch.looksLikePhotoRequest("Photos of the kids at the beach"))
        assertFalse(PromptSearch.looksLikePhotoRequest("Explain how rainbows form"))
        assertFalse(PromptSearch.looksLikePhotoRequest("my"))
    }

    // ---- listing cache

    @Test fun `listing pages append without duplicates and the cursor is kept exactly`() {
        val l = MediaListing()
        l.replace(MediaPage(listOf(photo("a"), photo("b")), "opaque/+=%"))
        assertEquals("opaque/+=%", l.cursor); assertTrue(l.hasMore)
        l.append(MediaPage(listOf(photo("b"), photo("c")), null))
        assertEquals(listOf("a", "b", "c"), l.items.map { it.id }); assertFalse(l.hasMore)
        l.remove(listOf("b")); assertEquals(listOf("a", "c"), l.items.map { it.id })
    }

    @Test fun `links go stale after about 50 minutes and a refresh swaps links without moving photos`() {
        var now = 0L
        val l = MediaListing { now }
        l.replace(MediaPage(listOf(photo("a"), photo("b")), null))
        assertFalse(l.linksStale()); now = 51 * 60_000L; assertTrue(l.linksStale())
        l.refreshLinks(listOf(photo("b").copy(thumbUrl = "https://new/b")))
        assertEquals(listOf("a", "b"), l.items.map { it.id }); assertEquals("https://new/b", l.get("b")!!.thumbUrl); assertEquals("https://t/a", l.get("a")!!.thumbUrl)
        assertFalse(l.linksStale())
    }

    @Test fun `the disk copy keeps photos by id and no links`() {
        val c = MediaCache(MemoryPageDisk())
        c.savePage("first", MediaPage(listOf(photo("a", taken = "2025-03-02T10:00:00", place = "Lisbon, Portugal")), "cur"))
        val back = c.loadPage("first")!!
        assertEquals("a", back.items.single().id); assertNull(back.items.single().thumbUrl); assertEquals("Lisbon, Portugal", back.items.single().place); assertNull(back.cursor)
        assertNull(c.loadPage("missing"))
    }

    // ---- models and the real client

    private lateinit var server: MockWebServer
    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() { server.close() }
    private fun client() = ApiMediaApi(ApiClient(configFor(server), FixedAuth()))

    @Test fun `summary parses and every call goes under users slash me slash library`() = runBlocking {
        server.enqueue(json(body = """{"plan":"pro","limit_bytes":100000000000,"used_bytes":1200000000,"count":42,"can_upgrade":false,"years":[{"year":2024,"count":10}],"places":[{"name":"Phuket","country":"Thailand","count":4}],"collections":[{"id":"c1","name":"Family","emoji":"x","count":3,"cover_id":"p1"}]}"""))
        val s = client().summary()
        assertEquals("pro", s.plan); assertEquals(100_000_000_000L, s.limitBytes); assertFalse(s.canUpgrade)
        assertEquals(YearCount(2024, 10), s.years.single()); assertEquals("Thailand", s.places.single().country); assertEquals("p1", s.collections.single().coverId)
        assertEquals("/prod/users/user-1/library/summary", server.takeRequest().url.encodedPath)
    }

    @Test fun `items pass the opaque cursor and filters through untouched`() = runBlocking {
        server.enqueue(json(body = """{"items":[{"id":"a","added":"2025-03-10T12:00:00Z","w":10,"h":20,"bytes":5,"thumb_url":"https://t/a","collections":["c1"],"taken":"2025-03-02T10:00:00","place":"Phuket, Thailand"}],"cursor":"A+b/c=="}"""))
        val page = client().items(60, "x+y/z==", MediaFilter(from = "2025-01-01", to = "2025-12-31", collection = "c1", place = "Phuket"))
        assertEquals("A+b/c==", page.cursor); assertEquals(listOf("c1"), page.items.single().collections); assertEquals("Phuket, Thailand", page.items.single().place)
        val u = server.takeRequest().url
        assertEquals("/prod/users/user-1/library/items", u.encodedPath)
        assertEquals("x+y/z==", u.queryParameter("cursor")); assertEquals("60", u.queryParameter("limit")); assertEquals("c1", u.queryParameter("collection")); assertEquals("2025-01-01", u.queryParameter("from"))
    }

    @Test fun `search sends drop only when chips were removed and parses the chips`() = runBlocking {
        val body = """{"understood":{"text":"","from":"2024-01-01","to":"2024-12-31","places":["Thailand"],"chips":[{"kind":"place","label":"Thailand"},{"kind":"date","label":"2024"}]},"items":[],"mode":"timeline"}"""
        server.enqueue(json(body = body)); server.enqueue(json(body = body))
        val r = client().search("holidays in Thailand 2024")
        assertEquals(listOf("Thailand", "2024"), r.understood.chips.map { it.label }); assertEquals("timeline", r.mode); assertNull(r.understood.text)
        assertFalse("drop" in Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject)
        client().search("holidays in Thailand 2024", drop = listOf("2024"))
        val b = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals(listOf("2024"), b["drop"]!!.jsonArray.map { it.jsonPrimitive.content }); assertEquals("holidays in Thailand 2024", b["query"]!!.jsonPrimitive.content)
    }

    @Test fun `uploads body carries size hash and only the metadata that exists, slots parse`() = runBlocking {
        server.enqueue(json(body = """{"uploads":[{"index":0,"status":"upload","id":"m1","url":"https://s3/b","fields":{"key":"k"}},{"index":1,"status":"duplicate","duplicate_of":"m0"},{"index":2,"status":"no_space"},{"index":3,"status":"rejected","reason":"bad"}],"used_bytes":5,"limit_bytes":9}"""))
        val r = client().requestUploads(listOf(UploadRequestItem(10, "aa", "2025-01-02T03:04:05", 48.86, 2.29), UploadRequestItem(11, "bb"), UploadRequestItem(12, "cc"), UploadRequestItem(13, "dd")))
        assertEquals(listOf(SlotStatus.Upload, SlotStatus.Duplicate, SlotStatus.NoSpace, SlotStatus.Rejected), r.uploads.map { it.status })
        assertEquals("m0", r.uploads[1].duplicateOf); assertEquals(mapOf("key" to "k"), r.uploads[0].fields); assertEquals("bad", r.uploads[3].reason)
        val items = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject["items"]!!.jsonArray
        assertEquals(setOf("size", "sha256", "taken", "lat", "lon"), items[0].jsonObject.keys); assertEquals(setOf("size", "sha256"), items[1].jsonObject.keys)
    }

    @Test fun `402 storage_full and 404 are told apart for the library`() = runBlocking {
        server.enqueue(json(402, """{"code":"storage_full","used_bytes":9,"limit_bytes":9}""")); server.enqueue(json(404, "{}"))
        try { client().requestUploads(listOf(UploadRequestItem(1, "a"))); fail() } catch (e: ApiError.StorageFull) { assertEquals(9L, e.limitBytes) }
        try { client().item("nope"); fail() } catch (e: ApiError) { assertEquals(ApiError.NotFound, e) }
    }

    @Test fun `collections and deletes use the contract paths and bodies`() = runBlocking {
        server.enqueue(json(body = """{"id":"c9","name":"Trip","count":0}""")); server.enqueue(json(body = "{}")); server.enqueue(json(body = "{}")); server.enqueue(json(body = """{"deleted":2,"used_bytes":7}"""))
        assertEquals("c9", client().createCollection("Trip").id)
        client().editCollection("c9", add = listOf("a", "b")); client().deleteCollection("c9"); assertEquals(2, client().delete(listOf("a", "b")).deleted)
        val r1 = server.takeRequest(); assertEquals("/prod/users/user-1/library/collections", r1.url.encodedPath)
        val r2 = server.takeRequest(); assertEquals("/prod/users/user-1/library/collections/c9/items", r2.url.encodedPath); assertFalse("remove" in Json.parseToJsonElement(r2.body!!.utf8()).jsonObject)
        assertEquals("/prod/users/user-1/library/collections/c9/delete", server.takeRequest().url.encodedPath)
        assertEquals("/prod/users/user-1/library/items/delete", server.takeRequest().url.encodedPath)
    }

    @Test fun `generate carries library_media only when photos were chosen from My media`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = """{"video_id":"v1"}""")); server.enqueue(json(body = """{"video_id":"v2"}"""))
        api.startGeneration("A trip to Lisbon with friends", "r1", CreateOptions(), emptyList(), null, listOf("L1", "L2"))
        assertEquals(listOf("L1", "L2"), Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject["library_media"]!!.jsonArray.map { it.jsonPrimitive.content })
        api.startGeneration("A trip to Lisbon with friends", "r2", CreateOptions(), listOf("m1"), null)
        assertFalse("library_media" in Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject)
    }

    @Test fun `the length hint counts library and phone photos together`() {
        assertNull(PhotoCapacity.hint(60 + 40, 2.0, listOf(1, 2, 3)))
        assertNotNull(PhotoCapacity.hint(60 + 50, 2.0, listOf(1, 2, 3)))
    }

    // ---- upload queue

    private fun items(n: Int, prefix: String = "i") = (0 until n).map { QueueItem("$prefix$it", "/f/$prefix$it", 100L + it, "h$prefix$it", taken = if (it == 0) "2025-01-02T03:04:05" else null) }
    private fun queue(api: MediaApi, blobs: Blobs, storage: QueueStorage = MemoryQueueStorage(), poster: SlotPoster = SlotPoster { _, _, _ -> }, concurrency: Int = 3, batch: Int = 100) =
        MediaUploadQueue(api, storage, blobs, poster, concurrency, 3, { 0L }, batch)
    private fun Blobs.put(list: List<QueueItem>) = list.forEach { files[it.path] = byteArrayOf(1, 2, 3) }

    @Test fun `250 photos go in slot batches of at most 100 and finish with progress counts`() = runBlocking {
        val api = FakeMedia(); val blobs = Blobs(); val q = queue(api, blobs)
        val list = items(250); blobs.put(list); q.enqueue(list); q.run()
        assertEquals(listOf(100, 100, 50), api.uploadCalls.map { it.size })
        val p = q.progress.value
        assertEquals(250, p.total); assertEquals(250, p.finished); assertEquals(250, p.uploaded); assertFalse(p.active)
        assertEquals(list.sumOf { it.size }, p.bytesDone)
        assertEquals("the prepared files stay as local pictures until the batch is dismissed", 250, blobs.files.size)
        q.dismissFinished(); assertTrue(blobs.files.isEmpty()); assertEquals(0, q.items.value.size)
        assertEquals(10L to 100L, q.usage.value)
    }

    @Test fun `uploads run three at a time and the file is the last form part`() = runBlocking {
        val api = FakeMedia(); val blobs = Blobs()
        val now = AtomicInteger(); val peak = AtomicInteger()
        val q = queue(api, blobs, poster = SlotPoster { _, _, _ -> peak.accumulateAndGet(now.incrementAndGet(), ::maxOf); delay(5); now.decrementAndGet() })
        val list = items(12); blobs.put(list); q.enqueue(list); q.run()
        assertEquals(3, peak.get())
        // the real poster over HTTP: signed fields first, the file part last, no login token
        val storage = MockWebServer().apply { start() }
        storage.enqueue(mockwebserver3.MockResponse.Builder().code(204).build())
        HttpSlotPoster(okhttp3.OkHttpClient()).post(storage.url("/b").toString(), mapOf("key" to "k1", "policy" to "P"), byteArrayOf(9, 9))
        val r = storage.takeRequest(); val text = r.body!!.utf8()
        assertTrue(text.indexOf("name=\"key\"") < text.indexOf("name=\"file\"")); assertTrue(text.indexOf("name=\"policy\"") < text.indexOf("name=\"file\""))
        assertNull(r.headers["Authorization"]); storage.close()
    }

    @Test fun `duplicates no_space and rejected are counted and never silently dropped`() = runBlocking {
        val api = FakeMedia()
        api.answer = { items -> UploadsResponse(items.indices.map { i -> when (i) {
            0 -> UploadSlotResult(0, SlotStatus.Upload, "m0", "https://s3/x", emptyMap(), null, null)
            1 -> UploadSlotResult(1, SlotStatus.Duplicate, null, null, emptyMap(), "old", null)
            2 -> UploadSlotResult(2, SlotStatus.NoSpace, null, null, emptyMap(), null, null)
            else -> UploadSlotResult(3, SlotStatus.Rejected, null, null, emptyMap(), null, "not a photo")
        } }, 90, 100) }
        val blobs = Blobs(); val q = queue(api, blobs); val list = items(4); blobs.put(list); q.enqueue(list); q.run()
        val p = q.progress.value
        assertEquals(1, p.uploaded); assertEquals(1, p.duplicates); assertEquals(1, p.noSpace); assertEquals(1, p.failed); assertTrue(p.storageFullMessageNeeded)
        assertEquals("not a photo", q.items.value[3].error); assertEquals("old", q.items.value[1].mediaId)
        // every file is kept (as the tile's local picture and for a retry) until the batch is dismissed
        assertEquals(4, blobs.files.size)
        q.dismissFinished(); assertEquals(0, q.items.value.size); assertTrue(blobs.files.isEmpty())
    }

    @Test fun `when nothing fits the whole batch is marked no_space and usage is known`() = runBlocking {
        val api = FakeMedia(); api.failure = ApiError.StorageFull(100, 100)
        val blobs = Blobs(); val q = queue(api, blobs); val list = items(5); blobs.put(list); q.enqueue(list); q.run()
        assertEquals(5, q.progress.value.noSpace); assertEquals(100L to 100L, q.usage.value)
    }

    @Test fun `a photo is tried three times then fails, and try again asks for a fresh slot`() = runBlocking {
        val api = FakeMedia(); val blobs = Blobs(); val tries = AtomicInteger()
        var broken = true
        val q = queue(api, blobs, poster = SlotPoster { _, _, _ -> tries.incrementAndGet(); if (broken) throw ApiError.Invalid("refused") })
        val list = items(2); blobs.put(list); q.enqueue(list); q.run()
        assertEquals(6, tries.get()); assertEquals(2, q.progress.value.failed); assertNull(q.items.value[0].slotUrl)
        assertTrue("failed photos keep their file so nothing is lost", blobs.files.size == 2)
        broken = false; q.retryFailed(); q.run()
        assertEquals(2, api.uploadCalls.size); assertEquals(2, q.progress.value.uploaded)
    }

    @Test fun `offline stops the run, keeps the photos queued and resumes later`() = runBlocking {
        val api = FakeMedia(); api.failure = ApiError.Network
        val blobs = Blobs(); val q = queue(api, blobs); val list = items(3); blobs.put(list); q.enqueue(list); q.run()
        assertTrue(q.progress.value.offline); assertEquals(0, q.progress.value.finished); assertTrue(q.hasWork())
        api.failure = null; q.run(); assertEquals(3, q.progress.value.uploaded); assertFalse(q.progress.value.offline)
    }

    @Test fun `the queue is saved and a new queue resumes it, an interrupted photo goes back to queued`() = runBlocking {
        val storage = MemoryQueueStorage(); val blobs = Blobs(); val api = FakeMedia()
        val q1 = queue(api, blobs, storage); val list = items(3, "s"); blobs.put(list); q1.enqueue(list)
        val raw = storage.text!!
        val interrupted = raw.replace("\"state\":\"Queued\"", "\"state\":\"Uploading\"")   // as if the app died mid-upload
        storage.text = interrupted
        val q2 = queue(api, blobs, storage)
        assertEquals(3, q2.items.value.size); assertTrue(q2.items.value.all { it.state == UploadState.Queued })
        assertEquals("2025-01-02T03:04:05", q2.items.value[0].taken); assertEquals(100L, q2.items.value[0].size); assertEquals("hs0", q2.items.value[0].sha256)
        q2.run(); assertEquals(3, q2.progress.value.uploaded)
        // finished items survive a restart too, so the summary is not lost
        val q3 = queue(api, blobs, storage); assertEquals(3, q3.progress.value.uploaded)
    }

    @Test fun `pause stops new uploads and cancel removes what is waiting`() = runBlocking {
        val api = FakeMedia(); val blobs = Blobs()
        lateinit var q: MediaUploadQueue
        val posted = AtomicInteger()
        q = queue(api, blobs, concurrency = 1, poster = SlotPoster { _, _, _ -> if (posted.incrementAndGet() == 2) q.pause() })
        val list = items(6); blobs.put(list); q.enqueue(list); q.run()
        assertEquals(2, q.progress.value.uploaded); assertTrue(q.progress.value.paused); assertTrue(q.hasWork())
        q.cancel()
        assertEquals(2, q.items.value.size); assertEquals(2, q.progress.value.total)   // only the finished ones stay
        assertEquals("cancelled photos' files are deleted, finished ones are kept until dismissed", 2, blobs.files.size)
    }

    @Test fun `a missing prepared file fails that photo without stopping the others`() = runBlocking {
        val api = FakeMedia(); val blobs = Blobs(); val q = queue(api, blobs); val list = items(3); blobs.put(list); blobs.files.remove("/f/i1"); q.enqueue(list); q.run()
        assertEquals(2, q.progress.value.uploaded); assertEquals(1, q.progress.value.failed); assertEquals("The photo file is gone.", q.items.value[1].error)
    }

    @Test fun `read only, collection cover links and search paging follow the updated contract`() = runBlocking {
        server.enqueue(json(body = """{"plan":"free","limit_bytes":10,"used_bytes":20,"read_only":true,"count":1,"can_upgrade":true,"collections":[{"id":"c1","name":"F","count":1,"cover_id":"p1","cover_thumb_url":"https://t/p1"}]}"""))
        val s = client().summary()
        assertTrue(s.readOnly); assertEquals("https://t/p1", s.collections.single().coverThumbUrl)
        server.enqueue(json(body = """{"understood":{"places":[],"chips":[]},"items":[],"mode":"timeline","cursor":"NEXT=="}"""))
        server.enqueue(json(body = """{"understood":{"places":[],"chips":[]},"items":[],"mode":"semantic"}"""))
        val first = client().search("thailand"); assertEquals("NEXT==", first.cursor); assertFalse(first.isSemantic)
        client().search("thailand", cursor = first.cursor).also { assertTrue(it.isSemantic); assertNull(it.cursor) }
        server.takeRequest()
        assertFalse("cursor" in Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject)
        assertEquals("NEXT==", Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject["cursor"]!!.jsonPrimitive.content)
    }

    // ---- waiting for uploaded photos to be listed

    /** A library that lists new photos only after [readyAfterCalls] calls, like a server still preparing them. */
    private class SlowLibrary(var count: Int, val newPhotos: Int, val readyAfterCalls: Int) {
        var calls = 0
        fun fetch(): Int { calls++; if (calls >= readyAfterCalls) count = newPhotos; return count }
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `new photos appear within the polling window and polling stops once they are listed`() = runTest {
        val t = ArrivalTracker(); t.expect(listedNow = 10, added = 3)
        val lib = SlowLibrary(10, 13, readyAfterCalls = 3)
        val p = ArrivalPoller(this, t, { lib.fetch() })
        p.start(); advanceTimeBy(1999); assertEquals(0, lib.calls); assertEquals(3, t.missing(10))
        advanceTimeBy(6000); runCurrent()
        assertEquals(3, lib.calls); assertFalse(t.pending); assertFalse(p.running)
        advanceTimeBy(60_000); runCurrent(); assertEquals(3, lib.calls)   // no more calls
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `polling gives up after about 90 seconds and then stops saying photos are getting ready`() = runTest {
        val t = ArrivalTracker(); t.expect(10, 5)
        var calls = 0
        val p = ArrivalPoller(this, t, { calls++; 10 })
        p.start(); advanceTimeBy(89_000); runCurrent(); assertTrue(t.pending)
        advanceTimeBy(10_000); runCurrent()
        assertFalse(t.pending); assertFalse(p.running)
        val after = calls; advanceTimeBy(120_000); runCurrent(); assertEquals(after, calls)
        assertTrue("about 5 fast then 4-second polls, not hundreds: $calls", calls in 20..30)
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `restarting never runs two polling jobs at once`() = runTest {
        val t = ArrivalTracker(); t.expect(0, 4)
        var calls = 0
        val p = ArrivalPoller(this, t, { calls++; 0 })
        p.start(); advanceTimeBy(1000); p.start(); advanceTimeBy(1000); p.start()
        advanceTimeBy(2001); runCurrent()
        assertEquals("one job, one call per 2 seconds after the last restart", 1, calls)
        p.stop(); advanceTimeBy(30_000); runCurrent(); assertEquals(1, calls)
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `a batch of only duplicates expects nothing and does not poll`() = runTest {
        val t = ArrivalTracker(); t.expect(listedNow = 10, added = 0)
        var calls = 0
        val p = ArrivalPoller(this, t, { calls++; 10 })
        p.start(); advanceTimeBy(120_000); runCurrent()
        assertFalse(t.pending); assertEquals(0, calls); assertEquals(0, t.missing(10))
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `a failed poll is tried again and later batches add to what is expected`() = runTest {
        val t = ArrivalTracker(); t.expect(10, 2); t.expect(10, 3)   // the baseline is only taken the first time
        assertEquals(5, t.missing(10)); assertEquals(1, t.missing(14))
        var calls = 0
        val p = ArrivalPoller(this, t, { calls++; if (calls == 1) null else 15 })
        p.start(); advanceTimeBy(5000); runCurrent()
        assertEquals(2, calls); assertFalse(t.pending)
    }

    @Test fun `merging the fresh first page keeps loaded pages, order and the paging cursor`() {
        val l = MediaListing()
        l.replace(MediaPage(listOf(photo("b"), photo("c")), "CUR"))
        l.append(MediaPage(listOf(photo("d")), "CUR2"))
        l.mergeHead(MediaPage(listOf(photo("a"), photo("b"), photo("c")), "FIRST"))
        assertEquals(listOf("a", "b", "c", "d"), l.items.map { it.id }); assertEquals("CUR2", l.cursor)
        val empty = MediaListing(); empty.mergeHead(MediaPage(listOf(photo("x")), "N")); assertEquals("N", empty.cursor)
    }
}
