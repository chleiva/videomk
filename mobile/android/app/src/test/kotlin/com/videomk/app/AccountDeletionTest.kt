package com.videomk.app

import com.videomk.app.core.AccountApi
import com.videomk.app.core.AccountDeleteResult
import com.videomk.app.core.AccountDeletionFlow
import com.videomk.app.core.AppleRevoke
import com.videomk.app.core.AppleStep
import com.videomk.app.core.AuthException
import com.videomk.app.core.Authorization
import com.videomk.app.core.DeletionFailure
import com.videomk.app.core.DeletionSession
import com.videomk.app.core.DeletionState
import com.videomk.app.core.DeletionText
import com.videomk.app.core.LocalWiper
import com.videomk.app.core.ReauthResult
import com.videomk.app.core.ReauthStep
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.time.Instant

private const val NOW = 2_000_000_000L

private class FakeSession(var current: Authorization) : DeletionSession {
    val log = mutableListOf<String>()
    var inProgress = false
    var reauthResult: ReauthResult = ReauthResult.Cancelled
    var failAuthorization: AuthException? = null
    var completeCalls = 0
    override suspend fun authorization(): Authorization { failAuthorization?.let { throw it }; return current }
    override fun logoutUrl(): HttpUrl { log += "logout"; return "https://auth.example.com/logout?client_id=c&logout_uri=x".toHttpUrl() }
    override fun beginReauth(expectedSub: String): HttpUrl { log += "authorize:$expectedSub"; inProgress = true; return "https://auth.example.com/oauth2/authorize?prompt=login&max_age=0".toHttpUrl() }
    override val reauthInProgress: Boolean get() = inProgress
    override suspend fun completeReauth(callback: String): ReauthResult {
        completeCalls++; inProgress = false
        (reauthResult as? ReauthResult.Completed)?.let { current = it.authorization }
        return reauthResult
    }
    override fun cancelReauth() { log += "cancel"; inProgress = false }
}

private class FakeApi : AccountApi {
    val results = ArrayDeque<AccountDeleteResult>()
    val calls = mutableListOf<Pair<String, String>>()
    var appleUrl: String? = "https://appleid.apple.com/auth/authorize?x=1"
    var appleHangs = false
    var appleCalls = 0
    var gate: CompletableDeferred<Unit>? = null
    val events = mutableListOf<String>()
    override suspend fun deleteAccount(idToken: String, sub: String): AccountDeleteResult {
        calls += idToken to sub; events += "delete"
        gate?.await()
        return results.removeFirstOrNull() ?: AccountDeleteResult.Accepted(AppleRevoke.NotLinked)
    }
    override suspend fun appleRevokeUrl(idToken: String, sub: String): String? {
        appleCalls++; events += "apple"
        if (appleHangs) awaitCancellation()
        return appleUrl
    }
}

class AccountDeletionTest {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private lateinit var api: FakeApi
    private lateinit var session: FakeSession
    private var wipes = 0
    private var wiped = 0
    private var ended = 0
    private var wipeFails = false
    private val requests = mutableListOf<HttpUrl>()

    private fun token(ageSeconds: Long?, sub: String = "user-1") = fakeJwt(sub = sub, authTime = ageSeconds?.let { NOW - it })
    private fun auth(ageSeconds: Long?, sub: String = "user-1") = Authorization(token(ageSeconds, sub), sub)

    @Before fun setUp() { api = FakeApi(); session = FakeSession(auth(30)) }
    @After fun tearDown() { scope.coroutineContext[kotlinx.coroutines.Job]?.cancel() }

    private fun flow(appleTimeout: Long = 8000) = AccountDeletionFlow(
        session, api,
        LocalWiper { api.events += "wipe"; wipes++; if (wipeFails) error("disk") },
        scope, onWiped = { api.events += "signedOut"; wiped++ }, onSessionEnded = { ended++ }, now = { Instant.ofEpochSecond(NOW) }, appleTimeoutMillis = appleTimeout,
    ).also { f -> scope.launch(Dispatchers.Unconfined) { f.requests.collect { requests += it } } }

    private fun awaitRequests(n: Int) { val end = System.currentTimeMillis() + 3000; while (requests.size < n && System.currentTimeMillis() < end) Thread.sleep(5); Thread.sleep(20) }

    private fun AccountDeletionFlow.await(pred: (DeletionState) -> Boolean = { it !is DeletionState.Working }): DeletionState = runBlocking { withTimeout(5000) { state.first(pred) } }

    // fresh token

    @Test fun `a fresh sign-in sends the delete at once with the token's own sub, then clears everything and signs out`() {
        val f = flow(); f.start("DELETE")
        assertEquals(DeletionState.Accepted(AppleStep.None), f.await())
        assertEquals(listOf(session.current.idToken to "user-1"), api.calls)
        assertEquals(listOf("delete", "wipe", "signedOut"), api.events)
        assertTrue(requests.isEmpty()); assertEquals(0, ended)
    }

    @Test fun `without the exact word nothing is sent`() {
        val f = flow()
        for (w in listOf("", "delete", "Delete", "DELET", "DELETE ME", "DELETEX")) f.start(w)
        f.start("  DELETE ")   // surrounding spaces from a keyboard are forgiven
        f.await()
        assertEquals(1, api.calls.size)
        val g = flow(); api.calls.clear(); g.start("nope"); Thread.sleep(100)
        assertEquals(DeletionState.Idle, g.state.value); assertTrue(api.calls.isEmpty())
    }

    // stale token

    @Test fun `a sign-in older than the limit goes through hosted logout and a fresh authorize before anything is sent`() {
        session.current = auth(20 * 60)
        val f = flow(); f.start("DELETE")
        assertEquals(DeletionState.Reauth(ReauthStep.LoggingOut), f.await { it is DeletionState.Reauth })
        awaitRequests(1); assertEquals(listOf("logout"), session.log); assertEquals(1, requests.size); assertTrue(requests[0].encodedPath.endsWith("/logout"))
        assertTrue(api.calls.isEmpty())
        f.onLogoutReturned()
        assertEquals(DeletionState.Reauth(ReauthStep.SigningIn), f.state.value)
        awaitRequests(2); assertEquals(listOf("logout", "authorize:user-1"), session.log); assertEquals(2, requests.size)
        assertTrue(api.calls.isEmpty() && wipes == 0)
        val fresh = auth(5)
        session.reauthResult = ReauthResult.Completed(fresh)
        assertTrue(f.reauthPending)
        f.onReauthCallback("com.videomk.app://auth/callback?code=c&state=s")
        assertEquals(DeletionState.Accepted(AppleStep.None), f.await { it is DeletionState.Accepted })
        assertEquals(listOf(fresh.idToken to "user-1"), api.calls)   // the NEW token
    }

    @Test fun `a token without auth_time is treated as stale`() {
        session.current = auth(null)
        val f = flow(); f.start("DELETE")
        assertEquals(DeletionState.Reauth(ReauthStep.LoggingOut), f.await { it is DeletionState.Reauth })
        assertTrue(api.calls.isEmpty())
    }

    @Test fun `the freshness limit is nine minutes, one under the server's ten`() {
        session.current = auth(539); flow().also { it.start("DELETE"); it.await() }
        assertEquals(1, api.calls.size)
        api.calls.clear(); session.current = auth(541)
        val g = flow(); g.start("DELETE"); g.await { it is DeletionState.Reauth }
        assertTrue(api.calls.isEmpty())
    }

    @Test fun `a 401 reauth_required re-authenticates once and retries with the new token, a second one is reported`() {
        api.results += AccountDeleteResult.ReauthRequired
        val f = flow(); f.start("DELETE")
        f.await { it is DeletionState.Reauth }
        assertEquals(1, api.calls.size)
        f.onLogoutReturned()
        api.results += AccountDeleteResult.ReauthRequired
        session.reauthResult = ReauthResult.Completed(auth(2))
        f.onReauthCallback("com.videomk.app://auth/callback?code=c&state=s")
        assertEquals(DeletionState.Failed(DeletionFailure.StillStale), f.await { it is DeletionState.Failed })
        assertEquals(2, api.calls.size)              // not a third
        assertEquals(0, wipes); assertEquals(0, wiped); assertEquals(0, ended)
        assertEquals(1, session.log.count { it == "logout" })   // no loop
    }

    @Test fun `a plain 401 is handled like reauth_required`() {
        api.results += AccountDeleteResult.Unauthorized
        val f = flow(); f.start("DELETE")
        assertEquals(DeletionState.Reauth(ReauthStep.LoggingOut), f.await { it is DeletionState.Reauth })
    }

    // cancelled / failed re-auth: signed in, nothing sent

    @Test fun `closing the browser during re-authentication leaves the person signed in and nothing sent`() {
        session.current = auth(3600)
        val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Reauth }
        f.onLogoutReturned(); f.onBrowserAbandoned()
        assertEquals(DeletionState.Failed(DeletionFailure.ReauthCancelled), f.state.value)
        assertTrue(api.calls.isEmpty()); assertEquals(0, wipes); assertEquals(0, wiped); assertEquals(0, ended)
        assertFalse(session.inProgress)
        // and the person can try again
        session.current = auth(10); f.start("DELETE")
        assertEquals(DeletionState.Accepted(AppleStep.None), f.await { it is DeletionState.Accepted })
    }

    @Test fun `the cancel button in the sign-in step does the same`() {
        session.current = auth(3600)
        val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Reauth }
        f.cancel()
        assertEquals(DeletionState.Failed(DeletionFailure.ReauthCancelled), f.state.value); assertTrue(api.calls.isEmpty())
    }

    @Test fun `declined, failed and wrong-account sign-ins are told apart and send nothing`() {
        for ((result, reason) in listOf(ReauthResult.Cancelled to DeletionFailure.ReauthCancelled, ReauthResult.Failed to DeletionFailure.ReauthFailed, ReauthResult.WrongAccount to DeletionFailure.WrongAccount)) {
            session.current = auth(3600); session.reauthResult = result
            val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Reauth }
            f.onLogoutReturned(); f.onReauthCallback("com.videomk.app://auth/callback?error=x&state=s")
            assertEquals(DeletionState.Failed(reason), f.await { it is DeletionState.Failed })
        }
        assertTrue(api.calls.isEmpty()); assertEquals(0, wipes)
    }

    @Test fun `the quirk retry of the sign-in opens one more page and keeps waiting`() {
        session.current = auth(3600)
        val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Reauth }
        f.onLogoutReturned()
        session.reauthResult = ReauthResult.Retry("https://auth.example.com/oauth2/authorize?again=1".toHttpUrl())
        f.onReauthCallback("com.videomk.app://auth/callback?error=server_error&state=s")
        assertEquals(DeletionState.Reauth(ReauthStep.SigningIn), f.await { it is DeletionState.Reauth })
        awaitRequests(3); assertEquals(3, requests.size)
    }

    // failures with a session that stays

    @Test fun `offline keeps the person signed in, says it may or may not have started, and a retry is accepted (idempotent)`() {
        api.results += AccountDeleteResult.Offline
        val f = flow(); f.start("DELETE")
        assertEquals(DeletionState.Failed(DeletionFailure.Offline), f.await { it is DeletionState.Failed })
        assertEquals(0, wipes); assertEquals(0, wiped)
        assertTrue(DeletionText.message(DeletionFailure.Offline).contains("Trying again is safe"))
        f.start("DELETE")   // 202 "already deleting" comes back as Accepted
        assertEquals(DeletionState.Accepted(AppleStep.None), f.await { it is DeletionState.Accepted })
        assertEquals(2, api.calls.size)
    }

    @Test fun `403, 400 and 500 each fail with their own message and lose nothing`() {
        for ((r, reason) in listOf(AccountDeleteResult.Forbidden to DeletionFailure.Forbidden, AccountDeleteResult.Rejected to DeletionFailure.Rejected, AccountDeleteResult.ServerError to DeletionFailure.Server)) {
            api.results += r
            val f = flow(); f.start("DELETE")
            assertEquals(DeletionState.Failed(reason), f.await { it is DeletionState.Failed })
        }
        assertEquals(0, wipes); assertEquals(0, wiped); assertEquals(0, ended)
        assertEquals(DeletionFailure.entries.size, DeletionFailure.entries.map { DeletionText.message(it) }.toSet().size)
    }

    @Test fun `reset after a failure goes back to the form`() {
        api.results += AccountDeleteResult.ServerError
        val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Failed }
        f.reset(); assertEquals(DeletionState.Idle, f.state.value)
    }

    @Test fun `a revoked session before anything is sent signs the app out`() {
        session.failAuthorization = AuthException(AuthException.Kind.SignedOut)
        val f = flow(); f.start("DELETE"); Thread.sleep(200)
        assertEquals(1, ended); assertTrue(api.calls.isEmpty()); assertEquals(DeletionState.Idle, f.state.value)
    }

    // idempotence and re-entrancy

    @Test fun `a second start after 202 and a start while one is running do nothing`() {
        api.gate = CompletableDeferred()
        val f = flow(); f.start("DELETE"); f.start("DELETE"); f.start("DELETE")
        Thread.sleep(150)
        assertEquals(1, api.calls.size)
        api.gate!!.complete(Unit)
        assertEquals(DeletionState.Accepted(AppleStep.None), f.await { it is DeletionState.Accepted })
        f.start("DELETE"); Thread.sleep(100)
        assertEquals(1, api.calls.size); assertEquals(1, wipes); assertEquals(1, wiped)
    }

    @Test fun `a failing wipe step does not stop the done screen, and the person is signed out`() {
        wipeFails = true
        val f = flow(); f.start("DELETE")
        assertEquals(DeletionState.Accepted(AppleStep.None), f.await { it is DeletionState.Accepted })
        assertEquals(1, wiped)
    }

    @Test fun `dismissing the done screen returns to idle and a later call is harmless`() {
        val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Accepted }
        f.dismissDone(); assertEquals(DeletionState.Idle, f.state.value)
    }

    // links and redirects do nothing unless a deletion is waiting for them

    @Test fun `redirects with no deletion running are ignored and never send a request`() {
        val f = flow()
        f.onLogoutReturned(); f.onReauthCallback("com.videomk.app://auth/callback?code=c&state=s"); f.onAppleReturn("ok"); f.openApple(); f.onBrowserAbandoned(); f.cancel()
        Thread.sleep(100)
        assertEquals(DeletionState.Idle, f.state.value)
        assertTrue(api.calls.isEmpty() && requests.isEmpty() && session.log.isEmpty() && session.completeCalls == 0 && wipes == 0)
    }

    @Test fun `a sign-out redirect in the wrong step, or twice, does not skip the sign-in`() {
        session.current = auth(3600)
        val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Reauth }
        f.onReauthCallback("com.videomk.app://auth/callback?code=c&state=s")   // sign-in callback while the logout page is still open
        assertEquals(DeletionState.Reauth(ReauthStep.LoggingOut), f.state.value); assertEquals(0, session.completeCalls)
        f.onLogoutReturned(); f.onLogoutReturned()
        awaitRequests(2); assertEquals(2, requests.size)   // logout + one authorize
    }

    // Apple

    private fun accepted(a: AppleRevoke): AccountDeletionFlow { api.results += AccountDeleteResult.Accepted(a); val f = flow(); f.start("DELETE"); f.await { it is DeletionState.Accepted }; return f }

    @Test fun `not_linked and unknown skip the Apple step, revoke_off shows the manual text, none asks the server for a link`() {
        assertEquals(DeletionState.Accepted(AppleStep.None), accepted(AppleRevoke.NotLinked).state.value)
        assertEquals(DeletionState.Accepted(AppleStep.None), accepted(AppleRevoke.Unknown).state.value)
        assertEquals(DeletionState.Accepted(AppleStep.Manual), accepted(AppleRevoke.RevokeOff).state.value)
        assertEquals(0, api.appleCalls)
    }

    @Test fun `revoke_available asks for the link before the tokens are wiped, then offers it`() {
        val f = accepted(AppleRevoke.RevokeAvailable)
        assertEquals(DeletionState.Accepted(AppleStep.Available("https://appleid.apple.com/auth/authorize?x=1")), f.state.value)
        assertEquals(listOf("delete", "apple", "wipe", "signedOut"), api.events)
        f.openApple(); awaitRequests(1)
        assertEquals("appleid.apple.com", requests.last().host)
    }

    @Test fun `the return from Apple is accepted only while the step waits, ok finishes it and anything else shows the manual text`() {
        val a = accepted(AppleRevoke.RevokeAvailable); a.onAppleReturn("ok")
        assertEquals(DeletionState.Accepted(AppleStep.Done), a.state.value)
        for (s in listOf("cancelled", "mismatch", "failed", "invalid", "whatever", null)) {
            val f = accepted(AppleRevoke.RevokeAvailable); f.onAppleReturn(s)
            assertEquals(DeletionState.Accepted(AppleStep.Manual), f.state.value)
        }
        val none = accepted(AppleRevoke.NotLinked); none.onAppleReturn("ok")
        assertEquals(DeletionState.Accepted(AppleStep.None), none.state.value)   // nothing was waiting
        val manual = accepted(AppleRevoke.RevokeOff); manual.onAppleReturn("ok")
        assertEquals(DeletionState.Accepted(AppleStep.Manual), manual.state.value)
    }

    @Test fun `the Apple link failing, missing, hanging or pointing elsewhere never blocks or delays the deletion much`() {
        api.appleUrl = null; assertEquals(DeletionState.Accepted(AppleStep.Manual), accepted(AppleRevoke.RevokeAvailable).state.value)
        api.appleUrl = "https://evil.example.com/auth/authorize"; assertEquals(DeletionState.Accepted(AppleStep.Manual), accepted(AppleRevoke.RevokeAvailable).state.value)
        api.appleUrl = "http://appleid.apple.com/auth/authorize"; assertEquals(DeletionState.Accepted(AppleStep.Manual), accepted(AppleRevoke.RevokeAvailable).state.value)
        api.appleHangs = true
        api.results += AccountDeleteResult.Accepted(AppleRevoke.RevokeAvailable)
        val f = flow(appleTimeout = 100); val t0 = System.currentTimeMillis(); f.start("DELETE")
        assertEquals(DeletionState.Accepted(AppleStep.Manual), f.await { it is DeletionState.Accepted })
        assertTrue(System.currentTimeMillis() - t0 < 3000); assertEquals(4, wipes)
    }
}
