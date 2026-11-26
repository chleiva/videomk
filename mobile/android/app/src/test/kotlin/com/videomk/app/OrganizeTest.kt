package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/** A MediaApi with only the smart-collection calls: preview, apply (about 300 photos a call) and the preference. */
private class OrganizeFake(var total: Int = 842, var perCall: Int = 300, val groupsPerApply: Int = 5) : MediaApi {
    var remaining = total
    val applyCalls = mutableListOf<List<Any?>>()
    var failures = ArrayDeque<ApiError>()
    var pref = OrganizePref.Ask
    var gate: CompletableDeferred<Unit>? = null
    var previewResult = OrganizePreview(842, 0, 37, "London", listOf(OrganizeGroup("London · Apr 2026", 214, true, listOf("a", "b", "c")), OrganizeGroup("Jun 2025", 52, false, emptyList())))
    override suspend fun organizePreview(since: String?): OrganizePreview = previewResult
    override suspend fun organizeApply(single: Boolean, since: String?, name: String?, collectionId: String?): OrganizeApplyResult {
        applyCalls += listOf(single, since, name, collectionId)
        gate?.await()
        failures.removeFirstOrNull()?.let { throw it }
        val n = minOf(perCall, remaining); remaining -= n
        return OrganizeApplyResult(n, remaining, if (applyCalls.size == 1) groupsPerApply else 1, 0, 0, if (single) "col-1" else null)
    }
    override suspend fun setOrganizePref(pref: OrganizePref) { this.pref = pref }
    override suspend fun summary() = error("unused"); override suspend fun requestUploads(items: List<UploadRequestItem>) = error("unused")
    override suspend fun items(limit: Int, cursor: String?, filter: MediaFilter) = error("unused"); override suspend fun item(id: String) = error("unused")
    override suspend fun delete(ids: List<String>) = error("unused"); override suspend fun search(query: String, limit: Int, drop: List<String>, cursor: String?) = error("unused")
    override suspend fun collections() = error("unused"); override suspend fun createCollection(name: String, emoji: String?) = error("unused")
    override suspend fun updateCollection(id: String, name: String?, emoji: String?) = error("unused"); override suspend fun deleteCollection(id: String) = error("unused")
    override suspend fun editCollection(id: String, add: List<String>, remove: List<String>) = error("unused")
}

class OrganizeTest {
    @Test fun `when to prompt, run quietly or stay silent`() {
        for (n in listOf(0, 1, 29)) { assertEquals(OrganizePrompt.Decision.Nothing, OrganizePrompt.decide(OrganizePref.Ask, n)); assertEquals(OrganizePrompt.Decision.Nothing, OrganizePrompt.decide(OrganizePref.Never, n)) }
        assertEquals(OrganizePrompt.Decision.ShowSheet, OrganizePrompt.decide(OrganizePref.Ask, 30))
        assertEquals(OrganizePrompt.Decision.ShowSheet, OrganizePrompt.decide(OrganizePref.Ask, 842))
        assertEquals(OrganizePrompt.Decision.Nothing, OrganizePrompt.decide(OrganizePref.Never, 5000))
        assertEquals(OrganizePrompt.Decision.RunSilently, OrganizePrompt.decide(OrganizePref.Always, 12))    // under 30 with Always: silent
        assertEquals(OrganizePrompt.Decision.RunSilently, OrganizePrompt.decide(OrganizePref.Always, 299))   // one call: no bar
        assertEquals(OrganizePrompt.Decision.RunWithProgress, OrganizePrompt.decide(OrganizePref.Always, 300))
        assertEquals(OrganizePrompt.Decision.Nothing, OrganizePrompt.decide(OrganizePref.Always, 0))
    }

    @Test fun `since is the batch start in UTC minus a minute`() {
        // 2026-11-25T10:00:00Z
        assertEquals("2026-11-25T09:59:00", OrganizePrompt.since(1_795_600_800_000L))
    }

    @Test fun `preference wire values map both ways, unknown means ask`() {
        assertEquals(OrganizePref.Always, OrganizePref.fromWire("always")); assertEquals(OrganizePref.Never, OrganizePref.fromWire("never"))
        assertEquals(OrganizePref.Ask, OrganizePref.fromWire(null)); assertEquals(OrganizePref.Ask, OrganizePref.fromWire("weird"))
        assertEquals(listOf("ask", "always", "never"), OrganizePref.entries.map { it.wire })
    }

    @Test fun `sheet titles, more line and the quiet skipped line`() {
        val p = OrganizePreview(842, 0, 37, null, List(14) { OrganizeGroup("G$it", 10, false, emptyList()) })
        assertEquals("Organize 842 new photos?", OrganizePrompt.title(p, false)); assertEquals("Organize 842 photos?", OrganizePrompt.title(p, true))
        assertEquals(5, OrganizePrompt.visibleGroups(p, false).size); assertEquals(14, OrganizePrompt.visibleGroups(p, true).size)
        assertEquals("+ 9 more collections", OrganizePrompt.moreLabel(p)); assertEquals("37 photos had no clear group and stay as they are.", OrganizePrompt.skippedLine(p))
        assertNull(OrganizePrompt.skippedLine(p.copy(skipped = 0)))
        assertEquals("Add 214 new photos to your collections?".replace("new ", ""), OrganizePrompt.title(OrganizePreview(214, 0, 0, null, listOf(OrganizeGroup("x", 214, true, emptyList()))), false))
        assertEquals("+ 1 more collection", OrganizePrompt.moreLabel(OrganizePreview(1, 0, 0, null, List(6) { OrganizeGroup("g", 1, false, emptyList()) })))
    }

    @Test fun `done messages`() {
        assertEquals("Organized into 14 collections", OrganizePrompt.doneMessage(14, 0)); assertEquals("Organized into 1 collection", OrganizePrompt.doneMessage(1, 3))
        assertEquals("Everything is already organized", OrganizePrompt.doneMessage(0, 0)); assertEquals("Added to 2 collections", OrganizePrompt.doneMessage(0, 2))
        assertTrue(OrganizePrompt.nameValid("Thailand")); assertFalse(OrganizePrompt.nameValid("   ")); assertFalse(OrganizePrompt.nameValid("x".repeat(61))); assertTrue(OrganizePrompt.nameValid("x".repeat(60)))
    }

    @Test fun `suggested names come from the place and the dates`() {
        val thai = OrganizePreview(100, 0, 0, null, listOf(OrganizeGroup("Phuket · 14-21 Jul 2024", 80, false, emptyList()), OrganizeGroup("Krabi · 22-25 Jul 2024", 20, false, emptyList())))
        assertEquals(listOf("Phuket Jul 2024", "Jul 2024"), OrganizeNames.suggest(thai))
        val spread = OrganizePreview(100, 0, 0, null, listOf(OrganizeGroup("London · Apr 2026", 70, false, emptyList()), OrganizeGroup("Jun 2025", 30, false, emptyList())))
        assertEquals(listOf("London 2025-2026", "Jun 2025 - Apr 2026"), OrganizeNames.suggest(spread))
        val noPlace = OrganizePreview(100, 0, 0, null, listOf(OrganizeGroup("Jun 2025", 60, false, emptyList()), OrganizeGroup("Jul 2026", 40, false, emptyList())))
        assertEquals(listOf("Jun 2025 - Jul 2026"), OrganizeNames.suggest(noPlace))
        val mixed = OrganizePreview(100, 0, 0, null, listOf(OrganizeGroup("London · Apr 2026", 40, false, emptyList()), OrganizeGroup("Lisbon · 3-6 Oct 2025", 30, false, emptyList()), OrganizeGroup("Jun 2025", 30, false, emptyList())))
        assertEquals(listOf("Jun 2025 - Apr 2026"), OrganizeNames.suggest(mixed))   // no place holds 60 percent
        assertTrue(OrganizeNames.suggest(OrganizePreview(1, 0, 0, null, emptyList())).isEmpty())
    }

    // the chunk loop

    @Test fun `apply is called until nothing remains, with real cumulative progress`() = runBlocking {
        val api = OrganizeFake(); val store = MemoryJobStore(); val r = OrganizeRunner(api, store)
        val seen = mutableListOf<Int>()
        val watcher = launch { r.state.collect { if (it is OrganizeState.Running) seen += it.done } }
        r.start(false, 842, "2026-11-25T09:59:00")
        assertEquals(3, api.applyCalls.size)
        assertEquals(OrganizeState.Done(created = 7, updated = 0), r.state.value)
        assertTrue(seen.all { it <= 842 }); assertNull("the saved job is gone when finished", store.text)
        assertEquals(listOf(false, "2026-11-25T09:59:00", null, null), api.applyCalls[0])
        watcher.cancel()
    }

    @Test fun `single mode sends the returned collection id on the following calls`() = runBlocking {
        val api = OrganizeFake(); val r = OrganizeRunner(api, MemoryJobStore())
        r.start(true, 842, null, "Thailand Jul 2024")
        assertEquals(listOf(true, null, "Thailand Jul 2024", null), api.applyCalls[0])
        assertEquals(listOf(true, null, "Thailand Jul 2024", "col-1"), api.applyCalls[1]); assertEquals("col-1", api.applyCalls[2][3])
    }

    @Test fun `the saved job lets a restarted app continue where it stopped`() = runBlocking {
        val api = OrganizeFake(); val store = MemoryJobStore()
        api.failures.add(ApiError.Server)   // the first call fails: the job was saved before it started
        val r1 = OrganizeRunner(api, store)
        r1.start(false, 842, "S")        // first call throws Server -> Failed, job saved at its start
        assertTrue(r1.state.value is OrganizeState.Failed)
        val job = OrganizeRunner(api, store).pendingJob()!!
        assertEquals("S", job.since); assertEquals(842, job.total)
        val r2 = OrganizeRunner(api, store); r2.resume()
        assertTrue(r2.state.value is OrganizeState.Done); assertNull(store.text)
        assertNull(OrganizeRunner(api, MemoryJobStore()).pendingJob())
    }

    @Test fun `a server error fails the job and try again resumes it`() = runBlocking {
        val api = OrganizeFake(); val store = MemoryJobStore()
        val r = OrganizeRunner(api, store)
        // first call fine, second fails
        var n = 0
        val flaky = object : MediaApi by api {
            override suspend fun organizeApply(single: Boolean, since: String?, name: String?, collectionId: String?): OrganizeApplyResult { if (++n == 2) throw ApiError.Server; return api.organizeApply(single, since, name, collectionId) }
        }
        val rr = OrganizeRunner(flaky, store)
        rr.start(false, 842, "S")
        val failed = rr.state.value as OrganizeState.Failed
        assertEquals(300, failed.done); assertEquals(842, failed.total); assertNotNull(store.text)
        rr.resume(); assertTrue(rr.state.value is OrganizeState.Done)
        r.acknowledge()
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `offline pauses the job and it carries on by itself`() = runTest {
        val api = OrganizeFake(); api.failures.add(ApiError.Network); api.failures.add(ApiError.Network)
        val r = OrganizeRunner(api, MemoryJobStore(), retryDelayMs = 5000)
        val job = launch { r.start(false, 842, "S") }
        runCurrent()
        assertTrue(r.state.value is OrganizeState.Offline); assertEquals("Waiting for a connection", r.progressText())
        advanceTimeBy(5001); runCurrent(); assertTrue(r.state.value is OrganizeState.Offline)
        advanceTimeBy(5001); runCurrent()
        job.join()
        assertTrue(r.state.value is OrganizeState.Done)
    }

    @OptIn(ExperimentalCoroutinesApi::class)
    @Test fun `cancel stops calling apply and keeps what was made`() = runTest {
        val api = OrganizeFake(); val store = MemoryJobStore(); val r = OrganizeRunner(api, store)
        api.gate = CompletableDeferred()
        val job = launch { r.start(false, 842, "S") }
        runCurrent()
        assertTrue(r.isActive); assertEquals(1, api.applyCalls.size)
        r.cancel(); api.gate!!.complete(Unit); job.join()
        assertEquals(1, api.applyCalls.size); assertEquals(OrganizeState.Idle, r.state.value); assertNull(store.text)
    }

    @Test fun `progress text uses thousands separators`() = runBlocking {
        val api = OrganizeFake(total = 9800, perCall = 300); api.remaining = 9800
        lateinit var r: OrganizeRunner
        val texts = mutableListOf<String?>()
        val spy = object : MediaApi by api {
            override suspend fun organizeApply(single: Boolean, since: String?, name: String?, collectionId: String?): OrganizeApplyResult { texts += r.progressText(); return api.organizeApply(single, since, name, collectionId) }
        }
        r = OrganizeRunner(spy, MemoryJobStore())
        r.start(false, 9800, null)
        assertEquals("Organizing… 0 of 9,800", texts[0]); assertEquals("Organizing… 1,200 of 9,800", texts[4])
    }

    // the real client

    private lateinit var server: MockWebServer
    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() { server.close() }
    private fun client() = ApiMediaApi(ApiClient(configFor(server), FixedAuth()))

    @Test fun `preview, apply and prefs use the contract paths and bodies`() = runBlocking {
        server.enqueue(json(body = """{"total":842,"organized":0,"skipped":37,"home":"London","groups":[{"name":"London · Apr 2026","count":214,"existing":true,"sample_ids":["a","b"]}]}"""))
        server.enqueue(json(body = """{"applied":300,"remaining":542,"created":3,"updated":1,"skipped":2}"""))
        server.enqueue(json(body = """{"collection_id":"c9","applied":300,"remaining":0,"created":1}"""))
        server.enqueue(json(body = "{}"))
        val p = client().organizePreview("2026-11-25T09:59:00")
        assertEquals(842, p.total); assertEquals("London", p.home); assertTrue(p.groups.single().existing); assertEquals(listOf("a", "b"), p.groups.single().sampleIds)
        val a = client().organizeApply(false, "2026-11-25T09:59:00"); assertEquals(542, a.remaining); assertEquals(3, a.created)
        val s = client().organizeApply(true, null, "Trip", "c1"); assertEquals("c9", s.collectionId)
        client().setOrganizePref(OrganizePref.Always)
        val r1 = server.takeRequest(); assertEquals("/prod/users/user-1/library/organize/preview", r1.url.encodedPath); assertEquals("2026-11-25T09:59:00", Json.parseToJsonElement(r1.body!!.utf8()).jsonObject["since"]!!.jsonPrimitive.content)
        val b2 = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("auto", b2["mode"]!!.jsonPrimitive.content); assertFalse("name" in b2)
        val b3 = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals("single", b3["mode"]!!.jsonPrimitive.content); assertEquals("Trip", b3["name"]!!.jsonPrimitive.content); assertEquals("c1", b3["collection_id"]!!.jsonPrimitive.content); assertFalse("since" in b3)
        val r4 = server.takeRequest(); assertEquals("/prod/users/user-1/library/prefs", r4.url.encodedPath); assertEquals("always", Json.parseToJsonElement(r4.body!!.utf8()).jsonObject["organize"]!!.jsonPrimitive.content)
    }

    @Test fun `summary carries the preference and collections carry the auto mark`() = runBlocking {
        server.enqueue(json(body = """{"plan":"free","limit_bytes":1,"used_bytes":0,"count":0,"can_upgrade":false,"prefs":{"organize":"always"},"collections":[{"id":"c1","name":"London · Apr 2026","count":214,"auto":true},{"id":"c2","name":"Family","count":3}]}"""))
        val s = client().summary()
        assertEquals(OrganizePref.Always, s.organizePref); assertTrue(s.collections[0].auto); assertFalse(s.collections[1].auto)
        server.enqueue(json(body = """{"plan":"free","limit_bytes":1,"used_bytes":0,"count":0,"can_upgrade":false,"collections":[]}"""))
        assertEquals(OrganizePref.Ask, client().summary().organizePref)
    }
}
