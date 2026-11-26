package com.videomk.app

import com.videomk.app.core.AccountDeleteResult
import com.videomk.app.core.ApiClient
import com.videomk.app.core.AppleRevoke
import com.videomk.app.core.AppleStep
import com.videomk.app.core.AuthService
import com.videomk.app.core.InMemoryTokenStore
import com.videomk.app.core.Jwt
import com.videomk.app.core.ReauthResult
import com.videomk.app.core.Tokens
import com.videomk.app.core.DeletionState
import com.videomk.app.core.ReauthStep
import com.videomk.app.data.WipeSteps
import com.videomk.app.data.deleteChildren
import com.videomk.app.data.LocalDataWiper
import com.videomk.app.ui.AppViewModel
import com.videomk.app.ui.Phase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
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
import org.junit.Before
import org.junit.Test
import java.io.File
import java.time.Instant
import java.nio.file.Files

class AccountDeletionHttpTest {
    private lateinit var server: MockWebServer
    private lateinit var api: ApiClient

    @Before fun setUp() { server = MockWebServer().apply { start() }; api = ApiClient(configFor(server), FixedAuth(), appVersion = "1.0") }
    @After fun tearDown() { server.close() }

    private fun delete(token: String = "tok-1", sub: String = "sub-9") = runBlocking { api.deleteAccount(token, sub) }

    @Test fun `the request goes to the token's own sub with the confirmation word and that token`() {
        server.enqueue(json(202, """{"status":"deleting","apple":"not_linked"}"""))
        assertEquals(AccountDeleteResult.Accepted(AppleRevoke.NotLinked), delete("the-token", "sub-9"))
        val r = server.takeRequest()
        assertEquals("POST", r.method); assertEquals("/prod/users/sub-9/account/delete", r.url.encodedPath)
        assertEquals("Bearer the-token", r.headers["Authorization"])
        assertEquals("DELETE", Json.parseToJsonElement(r.body!!.utf8()).jsonObject["confirm"]!!.jsonPrimitive.content)
    }

    @Test fun `202 apple values map, and an unknown or missing value is Unknown`() {
        for ((wire, want) in listOf("not_linked" to AppleRevoke.NotLinked, "revoke_available" to AppleRevoke.RevokeAvailable, "revoke_off" to AppleRevoke.RevokeOff, "unknown" to AppleRevoke.Unknown, "what" to AppleRevoke.Unknown)) {
            server.enqueue(json(202, """{"status":"deleting","apple":"$wire"}""")); assertEquals(AccountDeleteResult.Accepted(want), delete())
        }
        server.enqueue(json(202, """{"status":"deleting"}""")); assertEquals(AccountDeleteResult.Accepted(AppleRevoke.Unknown), delete())
        server.enqueue(json(202, "")); assertEquals(AccountDeleteResult.Accepted(AppleRevoke.Unknown), delete())
    }

    @Test fun `401 reauth_required, a plain 401, 403, 400 and 5xx map to their own results`() {
        server.enqueue(json(401, """{"message":"x","code":"reauth_required","max_age_seconds":600}""")); assertEquals(AccountDeleteResult.ReauthRequired, delete())
        server.enqueue(json(401, """{"message":"Unauthorized"}""")); assertEquals(AccountDeleteResult.Unauthorized, delete())
        server.enqueue(json(401, "not json")); assertEquals(AccountDeleteResult.Unauthorized, delete())
        server.enqueue(json(403, """{"message":"Forbidden"}""")); assertEquals(AccountDeleteResult.Forbidden, delete())
        server.enqueue(json(400, """{"message":"x","code":"confirmation_required"}""")); assertEquals(AccountDeleteResult.Rejected, delete())
        server.enqueue(json(500, """{"message":"Something went wrong."}""")); assertEquals(AccountDeleteResult.ServerError, delete())
        server.enqueue(json(502, "bad gateway")); assertEquals(AccountDeleteResult.ServerError, delete())
    }

    @Test fun `no answer at all is Offline`() {
        server.close()
        assertEquals(AccountDeleteResult.Offline, delete())
    }

    @Test fun `the Apple link is returned only for Apple's own https page`() {
        server.enqueue(json(200, """{"authorize_url":"https://appleid.apple.com/auth/authorize?a=b","expires_in":600}"""))
        assertEquals("https://appleid.apple.com/auth/authorize?a=b", runBlocking { api.appleRevokeUrl("t", "sub-9") })
        val r = server.takeRequest()
        assertEquals("/prod/users/sub-9/account/apple-revoke", r.url.encodedPath); assertEquals("app", Json.parseToJsonElement(r.body!!.utf8()).jsonObject["return"]!!.jsonPrimitive.content)
        server.enqueue(json(200, """{"authorize_url":"https://evil.example.com/x"}""")); assertNull(runBlocking { api.appleRevokeUrl("t", "s") })
        server.enqueue(json(404, """{"code":"apple_revoke_off"}""")); assertNull(runBlocking { api.appleRevokeUrl("t", "s") })
        server.enqueue(json(409, """{"code":"not_deleting"}""")); assertNull(runBlocking { api.appleRevokeUrl("t", "s") })
        server.enqueue(json(200, "[]")); assertNull(runBlocking { api.appleRevokeUrl("t", "s") })
    }
}

class ReauthAuthTest {
    private lateinit var server: MockWebServer
    private val store = InMemoryTokenStore()
    private val old = Tokens(fakeJwt(sub = "user-1", authTime = 1), "a", "r-old", Instant.now().plusSeconds(3000))

    @Before fun setUp() { server = MockWebServer().apply { start() }; store.save(old) }
    @After fun tearDown() { server.close() }
    private fun service() = AuthService(configFor(server), store, OkHttpClient())
    private fun tokenBody(sub: String) = """{"id_token":"${fakeJwt(sub = sub, authTime = Instant.now().epochSecond)}","access_token":"a2","expires_in":3600,"refresh_token":"r-new"}"""

    @Test fun `auth_time is read from the id token`() {
        assertEquals(Instant.ofEpochSecond(1234), Jwt.authTime(fakeJwt(authTime = 1234)))
        assertNull(Jwt.authTime(fakeJwt()))
    }

    @Test fun `the logout page is the hosted logout with the app's client and registered sign-out uri`() {
        val u = service().logoutUrl()
        assertEquals("/logout", u.encodedPath); assertEquals("client-123", u.queryParameter("client_id")); assertEquals("com.videomk.app://auth/signout", u.queryParameter("logout_uri"))
    }

    @Test fun `the re-authentication page is a normal PKCE authorize with prompt login and max_age 0 and no provider`() {
        val u = service().beginReauth("user-1")
        assertEquals("/oauth2/authorize", u.encodedPath)
        assertEquals("login", u.queryParameter("prompt")); assertEquals("0", u.queryParameter("max_age"))
        assertEquals("code", u.queryParameter("response_type")); assertEquals("S256", u.queryParameter("code_challenge_method")); assertNotNull(u.queryParameter("state"))
        assertNull(u.queryParameter("identity_provider"))
    }

    @Test fun `a normal sign-in does not carry prompt or max_age`() {
        val u = service().beginSignIn()
        assertNull(u.queryParameter("prompt")); assertNull(u.queryParameter("max_age"))
    }

    @Test fun `the same account replaces the stored tokens and the old ones stay until then`() = runBlocking {
        val s = service(); val u = s.beginReauth("user-1")
        assertEquals(old, store.load()); assertTrue(s.reauthInProgress)
        server.enqueue(json(200, tokenBody("user-1")))
        val r = s.completeReauth("com.videomk.app://auth/callback?code=c1&state=${u.queryParameter("state")}")
        assertTrue(r is ReauthResult.Completed); assertEquals("user-1", (r as ReauthResult.Completed).authorization.userId)
        assertEquals(r.authorization.idToken, store.load()!!.idToken); assertFalse(s.reauthInProgress)
        val body = server.takeRequest().body!!.utf8()
        assertTrue(body.contains("code_verifier=") && body.contains("grant_type=authorization_code"))
    }

    @Test fun `a different account is refused and nothing is stored`() = runBlocking {
        val s = service(); val u = s.beginReauth("user-1")
        server.enqueue(json(200, tokenBody("someone-else")))
        assertEquals(ReauthResult.WrongAccount, s.completeReauth("com.videomk.app://auth/callback?code=c&state=${u.queryParameter("state")}"))
        assertEquals(old, store.load())
    }

    @Test fun `a wrong or missing state, a missing code, a repeat and a callback with no re-authentication all fail without touching the session`() = runBlocking {
        val s = service()
        assertEquals(ReauthResult.Failed, s.completeReauth("com.videomk.app://auth/callback?code=c&state=x"))   // none pending
        s.beginReauth("user-1"); assertEquals(ReauthResult.Failed, s.completeReauth("com.videomk.app://auth/callback?code=c&state=wrong"))
        val u = s.beginReauth("user-1"); assertEquals(ReauthResult.Failed, s.completeReauth("com.videomk.app://auth/callback?state=${u.queryParameter("state")}"))
        val v = s.beginReauth("user-1"); assertEquals(ReauthResult.Failed, s.completeReauth("com.videomk.app://auth/callback?error=access_denied"))   // no state: dropped
        assertEquals(0, server.requestCount); assertEquals(old, store.load())
    }

    @Test fun `access_denied is a cancel, other errors a failure, and a token endpoint failure keeps the old session`() = runBlocking {
        val s = service()
        var u = s.beginReauth("user-1"); assertEquals(ReauthResult.Cancelled, s.completeReauth("com.videomk.app://auth/callback?error=access_denied&state=${u.queryParameter("state")}"))
        u = s.beginReauth("user-1"); assertEquals(ReauthResult.Failed, s.completeReauth("com.videomk.app://auth/callback?error=server_error&state=${u.queryParameter("state")}"))
        u = s.beginReauth("user-1"); server.enqueue(json(400, """{"error":"invalid_grant"}"""))
        assertEquals(ReauthResult.Failed, s.completeReauth("com.videomk.app://auth/callback?code=c&state=${u.queryParameter("state")}"))
        assertEquals(old, store.load())
    }

    @Test fun `the already-found-entry quirk retries once, a second one fails`() = runBlocking {
        val s = service(); var u = s.beginReauth("user-1")
        val cb = { url: okhttp3.HttpUrl -> "com.videomk.app://auth/callback?error=invalid_request&error_description=Already+found+an+entry+for+username+Google_1&state=${url.queryParameter("state")}" }
        val r = s.completeReauth(cb(u)); assertTrue(r is ReauthResult.Retry)
        u = (r as ReauthResult.Retry).url; assertEquals("login", u.queryParameter("prompt"))
        assertEquals(ReauthResult.Failed, s.completeReauth(cb(u)))
    }

    @Test fun `cancelling and signing out forget a pending re-authentication`() = runBlocking {
        val s = service(); val u = s.beginReauth("user-1"); s.cancelReauth(); assertFalse(s.reauthInProgress)
        assertEquals(ReauthResult.Failed, s.completeReauth("com.videomk.app://auth/callback?code=c&state=${u.queryParameter("state")}"))
        s.beginReauth("user-1"); s.signOut(); assertFalse(s.reauthInProgress)
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class AccountDeletionViewModelTest {
    private lateinit var server: MockWebServer
    private val store = InMemoryTokenStore()
    private var wipes = 0

    @Before fun setUp() { Dispatchers.setMain(UnconfinedTestDispatcher()); server = MockWebServer().apply { start() } }
    @After fun tearDown() { Dispatchers.resetMain(); server.close() }

    private val fakeApi = object : com.videomk.app.core.AccountApi {
        val sent = mutableListOf<String>()
        var next: AccountDeleteResult = AccountDeleteResult.Accepted(AppleRevoke.RevokeOff)
        override suspend fun deleteAccount(idToken: String, sub: String): AccountDeleteResult { sent += idToken; return next }
        override suspend fun appleRevokeUrl(idToken: String, sub: String): String? = null
    }

    @Test fun `the whole stale-token path through the view model, ending signed out with the done screen and everything wiped`() {
        store.save(Tokens(fakeJwt(sub = "user-1", authTime = 5), "a", "r", Instant.now().plusSeconds(3000)))   // signed in long ago
        val auth = AuthService(configFor(server), store, OkHttpClient())
        val vm = AppViewModel(FakeBackend(), auth, configFor(server), MutableSharedFlow(extraBufferCapacity = 1), accountApi = fakeApi, wiper = { wipes++ })
        vm.start(); runBlocking { withTimeout(5000) { vm.state.first { it.phase is Phase.SignedIn } } }
        val d = vm.deletion!!
        val seen = mutableListOf<String>()
        val job = kotlinx.coroutines.CoroutineScope(Dispatchers.Unconfined).let { sc -> sc.launch { d.requests.collect { seen += it.toString() } } }
        d.start("DELETE")
        runBlocking { withTimeout(5000) { d.state.first { it is DeletionState.Reauth } } }
        assertTrue(fakeApi.sent.isEmpty()); assertNotNull(store.load())   // still signed in, nothing sent
        vm.onAuthCallback("com.videomk.app://auth/callback?code=x&state=y")   // a stray callback while the logout page is open: dropped
        assertTrue(fakeApi.sent.isEmpty())
        d.onLogoutReturned()
        val t0 = System.currentTimeMillis(); while (seen.size < 2 && System.currentTimeMillis() - t0 < 3000) Thread.sleep(5)
        val authorize = seen.last().toHttpUrlOrNullForTest()!!
        server.enqueue(json(200, """{"id_token":"${fakeJwt(sub = "user-1", authTime = Instant.now().epochSecond)}","access_token":"a","expires_in":3600,"refresh_token":"r2"}"""))
        vm.onAuthCallback("com.videomk.app://auth/callback?code=c&state=${authorize.queryParameter("state")}")
        val done = runBlocking { withTimeout(5000) { d.state.first { it is DeletionState.Accepted } } }
        assertEquals(DeletionState.Accepted(AppleStep.Manual), done)
        assertEquals(1, fakeApi.sent.size); assertEquals(1, wipes)
        runBlocking { withTimeout(5000) { vm.state.first { it.phase == Phase.SignedOut } } }   // set right after the done state
        assertNull(store.load())
        job.cancel()
    }
}

private fun String.toHttpUrlOrNullForTest() = okhttp3.HttpUrl.Companion.run { this@toHttpUrlOrNullForTest.toHttpUrlOrNull() }

class LocalWipeTest {
    @Test fun `deleteChildren empties nested folders and keeps the folder itself`() {
        val dir = Files.createTempDirectory("wipe").toFile()
        File(dir, "a/b").mkdirs(); File(dir, "a/b/c.jpg").writeText("x"); File(dir, "q.json").writeText("y")
        assertTrue(deleteChildren(dir)); assertTrue(dir.exists()); assertEquals(0, dir.listFiles()!!.size)
        assertTrue(deleteChildren(File(dir, "missing"))); assertTrue(deleteChildren(null))
        dir.delete()
    }

    @Test fun `a failing step does not stop the others and only its name is kept`() {
        val s = WipeSteps(); var ran = 0
        s.step("one") { ran++ }; s.step("boom") { error("secret path /x") }; s.step("three") { ran++ }
        assertEquals(2, ran); assertEquals(listOf("boom"), s.failures)
    }

    @Test fun `every preference file the app writes is on the wipe list`() {
        val src = File("src/main/kotlin")
        assertTrue("run from the module folder", src.isDirectory)
        val names = src.walkTopDown().filter { it.extension == "kt" }.flatMap { f -> Regex("""getSharedPreferences\("([^"]+)"""").findAll(f.readText()).map { it.groupValues[1] } }.toSet()
        assertTrue(names.isNotEmpty())
        assertTrue("unlisted: ${names - LocalDataWiper.PREFERENCE_FILES.toSet()}", LocalDataWiper.PREFERENCE_FILES.containsAll(names))
        assertTrue(LocalDataWiper.PREFERENCE_FILES.contains("vmk_session"))   // the encrypted token file (SecureTokenStore.FILE)
    }

    @Test fun `no code outside the wiper stores data in a place it does not clear`() {
        val src = File("src/main/kotlin")
        val dirs = setOf("cacheDir", "filesDir")   // both are emptied by the wiper
        val bad = src.walkTopDown().filter { it.extension == "kt" }.flatMap { f -> Regex("""(getExternalFilesDir|getDir\(|openFileOutput|createDatabase|Room\.|DataStore)""").findAll(f.readText()).map { f.name + ":" + it.value } }.toList()
        assertEquals("a new kind of storage needs a wiper step: $bad", emptyList<String>(), bad.filter { !it.startsWith("LocalDataWiper") })
    }
}
