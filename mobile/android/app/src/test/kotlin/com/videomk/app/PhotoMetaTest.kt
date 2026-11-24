package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.PhotoMeta
import com.videomk.app.core.PhotoMetaPolicy

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
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

class PhotoMetaTest {
    private val on = PhotoMetaPolicy()

    @Test fun `exif dates become local wall-clock iso text, bad ones are ignored`() {
        assertEquals("2025-01-02T03:04:05", PhotoMeta.parseDate("2025:01:02 03:04:05"))
        assertEquals("2025-01-02T03:04:05", PhotoMeta.parseDate(" 2025:01:02 03:04:05 "))
        assertNull(PhotoMeta.parseDate("0000:00:00 00:00:00"))
        assertNull(PhotoMeta.parseDate("2025:13:02 03:04:05")); assertNull(PhotoMeta.parseDate("garbage")); assertNull(PhotoMeta.parseDate(null)); assertNull(PhotoMeta.parseDate(""))
    }

    @Test fun `the original capture time wins over the file time`() {
        assertEquals("2024-06-01T10:00:00", PhotoMeta.fromExif("2024:06:01 10:00:00", "2025:01:01 00:00:00", null, on).taken)
        assertEquals("2025-01-01T00:00:00", PhotoMeta.fromExif(null, "2025:01:01 00:00:00", null, on).taken)
        assertEquals("2025-01-01T00:00:00", PhotoMeta.fromExif("0000:00:00 00:00:00", "2025:01:01 00:00:00", null, on).taken)
    }

    @Test fun `places are rounded to two decimals and keep north south east west signs`() {
        val paris = PhotoMeta.fromExif(null, null, doubleArrayOf(48.858844, 2.294351), on)
        assertEquals(48.86, paris.lat!!, 0.0); assertEquals(2.29, paris.lon!!, 0.0)
        val rio = PhotoMeta.fromExif(null, null, doubleArrayOf(-22.951916, -43.210487), on)   // south and west are negative
        assertEquals(-22.95, rio.lat!!, 0.0); assertEquals(-43.21, rio.lon!!, 0.0)
        val sydney = PhotoMeta.fromExif(null, null, doubleArrayOf(-33.8688, 151.2093), on)
        assertEquals(-33.87, sydney.lat!!, 0.0); assertEquals(151.21, sydney.lon!!, 0.0)
        assertEquals(0.0, PhotoMeta.round2(-0.004), 0.0); assertEquals("0.0", PhotoMeta.round2(-0.004).toString())   // no negative zero
    }

    @Test fun `out of range or incomplete places are dropped`() {
        assertNull(PhotoMeta.place(90.5, 10.0)); assertNull(PhotoMeta.place(10.0, 181.0)); assertNull(PhotoMeta.place(Double.NaN, 1.0)); assertNull(PhotoMeta.place(1.0, null))
        assertEquals(90.0 to 180.0, PhotoMeta.place(90.0, 180.0)); assertEquals(-90.0 to -180.0, PhotoMeta.place(-90.0, -180.0))
        assertTrue(PhotoMeta.fromExif(null, null, doubleArrayOf(95.0, 0.0), on).isEmpty)
    }

    @Test fun `switches off mean nothing is read or sent`() {
        val ll = doubleArrayOf(48.8588, 2.2943)
        val noDates = PhotoMeta.fromExif("2025:01:02 03:04:05", null, ll, PhotoMetaPolicy(useDates = false))
        assertNull(noDates.taken); assertEquals(48.86, noDates.lat!!, 0.0)
        val noPlaces = PhotoMeta.fromExif("2025:01:02 03:04:05", null, ll, PhotoMetaPolicy(useLocations = false))
        assertEquals("2025-01-02T03:04:05", noPlaces.taken); assertNull(noPlaces.lat); assertNull(noPlaces.lon)
        assertTrue(PhotoMeta.fromExif("2025:01:02 03:04:05", null, ll, PhotoMetaPolicy(false, false)).isEmpty)
        // photos prepared while a switch was on are filtered again when the request is built
        val full = PhotoMeta("2025-01-02T03:04:05", 48.86, 2.29)
        assertNull(PhotoMeta.requestJson(listOf("a"), listOf(full), PhotoMetaPolicy(false, false)))
        assertEquals(setOf("lat", "lon"), PhotoMeta.requestJson(listOf("a"), listOf(full), PhotoMetaPolicy(useDates = false))!!["a"]!!.jsonObject.keys)
    }

    @Test fun `request json is keyed by media id with only the entries and fields that exist`() {
        val metas = listOf(PhotoMeta("2025-01-02T03:04:05", 48.86, 2.29), null, PhotoMeta(taken = "2025-01-03T00:00:00"), PhotoMeta(lat = 1.0, lon = 2.0), PhotoMeta(lat = 1.0))
        val o = PhotoMeta.requestJson(listOf("m0", "m1", "m2", "m3", "m4"), metas)!!
        assertEquals(setOf("m0", "m2", "m3"), o.keys)   // m1 has nothing, m4 has half a place
        assertEquals(setOf("taken", "lat", "lon"), o["m0"]!!.jsonObject.keys)
        assertEquals(setOf("taken"), o["m2"]!!.jsonObject.keys)
        assertEquals(setOf("lat", "lon"), o["m3"]!!.jsonObject.keys)
        assertEquals("48.86", o["m0"]!!.jsonObject["lat"]!!.jsonPrimitive.content)
        assertNull(PhotoMeta.requestJson(listOf("a", "b"), listOf(null, PhotoMeta())))   // photos without metadata: no field at all
    }

    // the real request body

    private lateinit var server: MockWebServer
    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() { server.close() }

    @Test fun `generate carries media_meta only when there is something to say`() = runBlocking {
        val api = ApiClient(configFor(server), FixedAuth())
        server.enqueue(json(body = """{"video_id":"v1"}"""))
        api.startGeneration("A trip to Paris and Rio", "r1", CreateOptions(), listOf("m0", "m1"), PhotoMeta.requestJson(listOf("m0", "m1"), listOf(PhotoMeta("2025-01-02T03:04:05", 48.86, 2.29), null)))
        val body = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals(setOf("m0"), body["media_meta"]!!.jsonObject.keys)
        assertEquals("2025-01-02T03:04:05", body["media_meta"]!!.jsonObject["m0"]!!.jsonObject["taken"]!!.jsonPrimitive.content)
        server.enqueue(json(body = """{"video_id":"v2"}"""))
        api.startGeneration("A trip to Paris and Rio", "r2", CreateOptions(), listOf("m0"), null)
        assertFalse("media_meta" in Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject)
    }
}
