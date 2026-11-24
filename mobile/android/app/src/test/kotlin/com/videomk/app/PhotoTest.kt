package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.ApiError
import com.videomk.app.core.MultipartForm
import com.videomk.app.core.PhotoGeometry
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.PhotoUploader
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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
        val ids = PhotoUploader(api, OkHttpClient()).upload(listOf(byteArrayOf(1), byteArrayOf(2), byteArrayOf(3))) { d, t -> progress += d to t }
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
        storage.enqueue(MockResponse.Builder().code(403).build())
        try { PhotoUploader(api, OkHttpClient()).upload(listOf(byteArrayOf(1), byteArrayOf(2))); fail() } catch (e: ApiError) { assertTrue(e is ApiError.Invalid) }
        server.enqueue(json(body = slotsJson(2)))
        repeat(2) { storage.enqueue(MockResponse.Builder().code(204).build()) }
        assertEquals(listOf("id1", "id2"), PhotoUploader(api, OkHttpClient()).upload(listOf(byteArrayOf(1), byteArrayOf(2))))
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
}
