package com.videomk.app

import com.videomk.app.core.ApiError
import com.videomk.app.core.AuthService
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.InMemoryTokenStore
import com.videomk.app.core.LibraryEntry
import com.videomk.app.core.PendingVideo
import com.videomk.app.core.RetryResult
import com.videomk.app.core.Tokens
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import com.videomk.app.ui.AppState
import com.videomk.app.ui.AppViewModel
import com.videomk.app.core.SignInProvider
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.async
import com.videomk.app.ui.LoadState
import com.videomk.app.ui.Phase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import mockwebserver3.MockWebServer
import okhttp3.OkHttpClient
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.time.Instant

@OptIn(ExperimentalCoroutinesApi::class)
class AppViewModelTest {
    private lateinit var backend: FakeBackend
    private lateinit var server: MockWebServer
    private lateinit var store: InMemoryTokenStore
    private val signedOut = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    private var now = 1_000_000L

    @Before fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
        backend = FakeBackend(); server = MockWebServer().apply { start() }; store = InMemoryTokenStore()
    }
    @After fun tearDown() { Dispatchers.resetMain(); server.close() }

    private fun vm(signedIn: Boolean = true): AppViewModel {
        if (signedIn) store.save(Tokens(fakeJwt(email = "me@example.com"), "a", "r", Instant.now().plusSeconds(3000)))
        val auth = AuthService(configFor(server), store, OkHttpClient())
        return AppViewModel(backend, auth, configFor(server), signedOut, clock = { now })
    }

    private fun AppViewModel.await(pred: (AppState) -> Boolean) = runBlocking { withTimeout(5000) { state.first(pred) } }

    @Test fun `start decides the phase from the stored session`() {
        val a = vm(); a.start(); assertEquals(Phase.SignedIn("me@example.com"), a.await { it.phase != Phase.Launching }.phase)
        val b = vm(signedIn = false).also { store.clear() }; b.start(); assertEquals(Phase.SignedOut, b.await { it.phase != Phase.Launching }.phase)
    }

    @Test fun `start does its work once however many times the activity is recreated`() {
        var seeds = 0
        val a = vm(); repeat(5) { a.start(seed = { seeds++ }) }   // five rotations
        a.await { it.phase != Phase.Launching }
        assertEquals(1, seeds); assertEquals(1, a.startCount)
    }

    @Test fun `without a configuration the app says not configured instead of crashing`() {
        val a = AppViewModel(null, null, null, signedOut); a.start()
        assertEquals(Phase.NotConfigured, a.state.value.phase)
        assertNull(a.beginSignIn())
    }

    @Test fun `refresh loads videos and credits, and tracks stage changes and completions`() = runBlocking {
        backend.videos = listOf(VideoItem("v1", VideoStatus.Running(VideoStatus.Stage.Writing)))
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        a.refresh()
        assertEquals(LoadState.Loaded, a.state.value.loadState); assertEquals(5, a.state.value.wallet!!.balance)
        assertEquals(1_000_000L, a.state.value.stageSince["v1"]!!.sinceMillis)
        now += 5000
        a.refresh()
        assertEquals(1_000_000L, a.state.value.stageSince["v1"]!!.sinceMillis)   // same stage: the clock keeps running
        backend.videos = listOf(VideoItem("v1", VideoStatus.Running(VideoStatus.Stage.Rendering)))
        a.refresh(); assertEquals(1_005_000L, a.state.value.stageSince["v1"]!!.sinceMillis)
        backend.videos = listOf(VideoItem("v1", VideoStatus.Complete))
        a.refresh(); assertEquals(1, a.state.value.completions); assertTrue(a.state.value.stageSince.isEmpty())
        a.refresh(); assertEquals(1, a.state.value.completions)   // not counted twice
    }

    @Test fun `a first load that fails shows an error, a later failure keeps the list and flags offline`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.listError = ApiError.Network
        a.refresh()
        assertTrue(a.state.value.loadState is LoadState.Failed); assertTrue(a.state.value.offline)
        backend.listError = null; backend.videos = listOf(VideoItem("v1", VideoStatus.Complete))
        a.refresh(); assertEquals(LoadState.Loaded, a.state.value.loadState); assertFalse(a.state.value.offline)
        backend.listError = ApiError.Network
        a.refresh()
        assertEquals(LoadState.Loaded, a.state.value.loadState); assertEquals(1, a.state.value.videos.size); assertTrue(a.state.value.offline)
    }

    @Test fun `an expired session during refresh signs the user out and clears everything`() = runBlocking {
        backend.videos = listOf(VideoItem("v1", VideoStatus.Complete))
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }; a.refresh()
        backend.listError = ApiError.Unauthorized
        a.refresh()
        assertEquals(Phase.SignedOut, a.state.value.phase); assertTrue(a.state.value.videos.isEmpty()); assertNull(store.load())
    }

    @Test fun `the backend's signed-out event signs out too`() {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        signedOut.tryEmit(Unit)
        assertEquals(Phase.SignedOut, a.state.value.phase)
    }

    @Test fun `submitting adds a placeholder at once, then the accepted video takes its place`() = runBlocking {
        backend.videos = emptyList()
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.videos = listOf(VideoItem("new-video", VideoStatus.Running(VideoStatus.Stage.Starting)))
        a.submit("  Explain   rainbows please ", CreateOptions(minutes = 1.0))
        assertEquals("Explain rainbows please", backend.startCalls.single().first)
        // after the request was accepted and the list refreshed, the placeholder is gone and the server's row is there
        val entries = a.state.value.entries
        assertEquals(listOf("new-video"), entries.map { it.id }); assertTrue(entries[0] is LibraryEntry.Video)
        assertEquals("Explain rainbows please", a.state.value.briefs["new-video"]); assertEquals(1.0, a.state.value.minutes["new-video"]!!, 0.0)
        assertTrue(a.state.value.pending.isEmpty())
    }

    @Test fun `create waits for generate and a blocked answer leaves no card and nothing charged`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.startError = ApiError.Blocked("We can't make this one.")
        val r = a.submitAwait("A request the safety gate refuses", CreateOptions())
        assertEquals(com.videomk.app.core.SubmitOutcome.Stopped(ApiError.Blocked("We can't make this one.")), r)
        assertTrue(a.state.value.pending.isEmpty())
        assertEquals(com.videomk.app.core.CreateStop.Blocked("We can't make this one."), com.videomk.app.core.CreateErrors.fromGenerate((r as com.videomk.app.core.SubmitOutcome.Stopped).error))
    }

    @Test fun `a paused answer from generate carries the retry time and leaves no card`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.startError = ApiError.Paused("Paused for now.", 3600)
        val r = a.submitAwait("Anything at all please", CreateOptions()) as com.videomk.app.core.SubmitOutcome.Stopped
        assertEquals(com.videomk.app.core.CreateStop.Paused("Paused for now.", 3600), com.videomk.app.core.CreateErrors.fromGenerate(r.error))
        assertTrue(a.state.value.pending.isEmpty())
    }

    @Test fun `offline at create keeps the draft with an offline outcome, no failed card, and tapping again works`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.startError = ApiError.Network
        val r = a.submitAwait("Explain rainbows please", CreateOptions(), listOf(byteArrayOf(1)))
        assertEquals(com.videomk.app.core.SubmitOutcome.Offline(ApiError.Network.message), r)
        assertTrue(a.state.value.pending.isEmpty())
        backend.startError = null
        assertEquals(com.videomk.app.core.SubmitOutcome.Accepted, a.submitAwait("Explain rainbows please", CreateOptions(), listOf(byteArrayOf(1))))
        assertEquals(2, backend.startCalls.size)
    }

    @Test fun `an accepted create returns Accepted and other errors still end on a failed card`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        assertEquals(com.videomk.app.core.SubmitOutcome.Accepted, a.submitAwait("Explain rainbows please", CreateOptions()))
        backend.startError = ApiError.Server
        assertEquals(com.videomk.app.core.SubmitOutcome.Accepted, a.submitAwait("Explain clouds please", CreateOptions()))
        assertTrue(a.state.value.pending.any { it.state is PendingVideo.State.Failed })
    }

    @Test fun `photos are uploaded first and their ids go into the request`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        a.submit("Tell the story of my trip", CreateOptions(), listOf(byteArrayOf(1), byteArrayOf(2), byteArrayOf(3)))
        assertEquals(1, backend.uploadCalls); assertEquals(listOf("media0", "media1", "media2"), backend.startCalls.single().third)
    }

    @Test fun `what was read from each photo goes into the request keyed by the uploaded ids`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        a.submit("Tell the story of my trip", CreateOptions(), listOf(byteArrayOf(1), byteArrayOf(2)), listOf(com.videomk.app.core.PhotoMeta("2025-01-02T03:04:05", 48.86, 2.29), null))
        assertEquals(setOf("media0"), backend.startMeta.single()!!.keys)
        a.submit("A brief about photos with nothing", CreateOptions(), listOf(byteArrayOf(1)))
        assertEquals(null, backend.startMeta.last())
    }

    @Test fun `a failed request stays as a row with the reason, and retry sends the same request id (no second video)`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.startError = ApiError.Quota("Daily limit reached")
        a.submit("A perfectly fine brief", CreateOptions())
        val failed = a.state.value.pending.single()
        assertEquals(PendingVideo.State.Failed("Daily limit reached"), failed.state)
        assertEquals(1, a.state.value.entries.size)
        backend.startError = null
        a.retry(failed.id)
        assertEquals(2, backend.startCalls.size); assertEquals(failed.id, backend.startCalls[0].second); assertEquals(failed.id, backend.startCalls[1].second)
    }

    @Test fun `a failed photo upload keeps the photos so a retry needs no new selection`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.uploadError = ApiError.Network
        a.submit("A brief about my photos", CreateOptions(), listOf(byteArrayOf(1), byteArrayOf(2)))
        val p = a.state.value.pending.single()
        assertEquals(PendingVideo.State.Failed(ApiError.Network.message), p.state); assertEquals(2, p.photoCount); assertTrue(backend.startCalls.isEmpty())
        backend.uploadError = null
        a.retry(p.id)
        assertEquals(2, backend.uploadCalls); assertEquals(listOf("media0", "media1"), backend.startCalls.single().third)
    }

    @Test fun `not enough credits is reported on the row and the balance is re-read`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.startError = ApiError.InsufficientCredits(0, 3); backend.wallet = backend.wallet.copy(balance = 0)
        a.submit("A brief that costs too much", CreateOptions())
        assertTrue((a.state.value.pending.single().state as PendingVideo.State.Failed).message.contains("needs 3 credits"))
        assertEquals(0, a.state.value.wallet!!.balance)
    }

    @Test fun `dismissing a failed row removes it`() = runBlocking {
        val a = vm(); a.start(); a.await { it.phase is Phase.SignedIn }
        backend.startError = ApiError.Server
        a.submit("A brief that fails to send", CreateOptions())
        a.dismissPending(a.state.value.pending.single().id)
        assertTrue(a.state.value.pending.isEmpty())
    }

    @Test fun `a stray sign-in redirect is ignored and the sign-in flow reports failure`() = runBlocking {
        val a = vm(signedIn = false); a.start(); a.await { it.phase == Phase.SignedOut }
        a.onAuthCallback("com.videomk.app://auth/callback?code=x&state=y")   // nothing pending
        assertEquals(Phase.SignedOut, a.state.value.phase); assertEquals(0, server.requestCount)
        val url = a.beginSignIn()!!
        assertTrue(a.state.value.isSigningIn); assertNull(a.beginSignIn())   // a second tap does not start a second sign-in
        a.onAuthCallback("com.videomk.app://auth/callback?code=x&state=WRONG")
        val s = a.await { !it.isSigningIn }
        assertEquals(AppViewModel.SIGN_IN_FAILED, s.signInError); assertEquals(Phase.SignedOut, s.phase)
        assertTrue(url.toString().contains("code_challenge"))
        a.beginSignIn(); a.signInAbandoned(); assertFalse(a.state.value.isSigningIn); assertNull(a.state.value.signInError)
    }

    @Test fun `the already-found-entry error opens the same provider page once more, keeps the spinner and the second one shows a message`() = runBlocking {
        val a = vm(signedIn = false); a.start(); a.await { it.phase == Phase.SignedOut }
        val first = a.beginSignIn(SignInProvider.Google)!!
        assertEquals(SignInProvider.Google, a.state.value.signInProvider)
        val quirk = "error=invalid_request&error_description=Already+found+an+entry+for+username+Google_1"
        val next = async { a.browserRequests.first() }
        kotlinx.coroutines.yield()
        a.onAuthCallback("com.videomk.app://auth/callback?$quirk&state=${first.queryParameter("state")}")
        val retry = kotlinx.coroutines.withTimeout(5000) { next.await() }
        assertEquals("Google", retry.queryParameter("identity_provider")); assertTrue(a.state.value.isSigningIn)
        a.onAuthCallback("com.videomk.app://auth/callback?$quirk&state=${retry.queryParameter("state")}")
        val s = a.await { !it.isSigningIn }
        assertEquals(AppViewModel.ACCOUNT_LINK_FAILED, s.signInError); assertEquals(Phase.SignedOut, s.phase)
    }

    // ---- "Try again" reuses the failed video (docs/CREATE_API.md, "Retry a video")

    private fun failed(id: String = "v-failed") = VideoItem(id = id, status = VideoStatus.Failed, title = "Mattia", createdAt = Instant.now())

    @Test fun `try again asks the server to restart the SAME video and never creates a new request`() = runBlocking {
        backend.videos = listOf(failed()); val a = vm(); a.start(); runBlocking { a.refresh() }; a.await { it.videos.size == 1 }
        a.tryAgain(a.state.value.videos.single())
        a.await { it.videos.single().status.isRunning }
        assertEquals(listOf("v-failed"), backend.retryCalls)
        assertTrue(backend.startCalls.isEmpty())                 // nothing is built from the phone: no prompt, no photos, no new row
        assertEquals(1, a.state.value.videos.size)
    }

    @Test fun `a refused retry says why and starts nothing`() = runBlocking {
        backend.videos = listOf(failed()); backend.retryResult = RetryResult.Refused("attachments_unavailable", "Your photos are no longer stored.")
        val a = vm(); a.start(); runBlocking { a.refresh() }; a.await { it.videos.size == 1 }
        a.tryAgain(a.state.value.videos.single())
        a.await { it.retryNotice != null }
        assertEquals("Your photos are no longer stored.", a.state.value.retryNotice)
        assertTrue(backend.startCalls.isEmpty()); assertEquals(VideoStatus.Failed, a.state.value.videos.single().status)
        a.dismissRetryNotice(); assertNull(a.state.value.retryNotice)
    }

    @Test fun `an older server without the route never rebuilds a request that may have had photos`() = runBlocking {
        backend.videos = listOf(failed()); backend.retryResult = RetryResult.Unsupported
        val a = vm(); a.start(); runBlocking { a.refresh() }; a.await { it.videos.size == 1 }
        a.tryAgain(a.state.value.videos.single())
        a.await { it.retryNotice != null }
        assertTrue(backend.startCalls.isEmpty())                  // INVARIANT: no photo-less copy of a video that had attachments (or that we cannot tell about)
    }

    @Test fun `an older server is asked the old way only for a video made without attachments in this session`() = runBlocking {
        backend.retryResult = RetryResult.Unsupported; backend.newVideoId = "v-made"
        val a = vm(); a.start()
        a.submit("A short explainer about how black holes form", CreateOptions(2.0))
        a.await { it.pending.any { p -> p.state is PendingVideo.State.Accepted } }
        backend.videos = listOf(VideoItem(id = "v-made", status = VideoStatus.Failed))
        a.refresh(); a.await { it.videos.any { v -> v.id == "v-made" } }
        backend.startCalls.clear()
        a.tryAgain(a.state.value.videos.first { it.id == "v-made" })
        a.await { backend.startCalls.size == 1 }
        assertEquals("A short explainer about how black holes form", backend.startCalls.single().first)
        assertTrue(backend.startCalls.single().third.isEmpty())
    }

    @Test fun `with photos the old way is never used even when the video is known`() = runBlocking {
        backend.retryResult = RetryResult.Unsupported; backend.newVideoId = "v-photos"
        val a = vm(); a.start()
        a.submit("The story of the trip, with my photos", CreateOptions(2.0), photos = List(64) { byteArrayOf(1) })
        a.await { it.pending.any { p -> p.state is PendingVideo.State.Accepted } }
        backend.videos = listOf(VideoItem(id = "v-photos", status = VideoStatus.Failed))
        a.refresh(); a.await { it.videos.any { v -> v.id == "v-photos" } }
        val calls = backend.startCalls.size
        a.tryAgain(a.state.value.videos.first { it.id == "v-photos" })
        a.await { it.retryNotice != null }
        assertEquals(calls, backend.startCalls.size)
    }

    @Test fun `removing a failed video takes the row away`() = runBlocking {
        backend.videos = listOf(failed("a"), failed("b")); val a = vm(); a.start(); runBlocking { a.refresh() }; a.await { it.videos.size == 2 }
        a.removeFailed(a.state.value.videos.first { it.id == "a" })
        a.await { it.videos.size == 1 }
        assertEquals(listOf("a"), backend.deleteCalls); assertEquals("b", a.state.value.videos.single().id)
    }
}
