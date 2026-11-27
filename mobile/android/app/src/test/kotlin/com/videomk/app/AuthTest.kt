package com.videomk.app

import com.videomk.app.core.AuthException
import com.videomk.app.core.AuthService
import com.videomk.app.core.InMemoryTokenStore
import com.videomk.app.core.Jwt
import com.videomk.app.core.PKCE
import com.videomk.app.core.SignInProvider
import com.videomk.app.core.SignInResult
import com.videomk.app.core.SocialSwitches
import com.videomk.app.core.label
import com.videomk.app.core.Tokens
import com.videomk.app.core.parseQuery
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.runBlocking
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
import java.time.Instant

class AuthTest {
    private lateinit var server: MockWebServer
    private val http = OkHttpClient()

    @Before fun setUp() { server = MockWebServer().apply { start() } }
    @After fun tearDown() { server.close() }

    private fun service(store: InMemoryTokenStore) = AuthService(configFor(server), store, http)

    private fun tokenBody(id: String = fakeJwt(), refresh: String? = "r-new", expiresIn: Int = 3600) =
        """{"id_token":"$id","access_token":"acc","expires_in":$expiresIn${if (refresh != null) ""","refresh_token":"$refresh"""" else ""}}"""

    // PKCE

    @Test fun `PKCE challenge matches the RFC 7636 example`() {
        val p = PKCE("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        assertEquals("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", p.challenge)
    }

    @Test fun `generated verifiers are url-safe, long enough and different every time`() {
        val a = PKCE.generate(); val b = PKCE.generate()
        assertTrue(a.verifier.length in 43..128)
        assertTrue(a.verifier.matches(Regex("[A-Za-z0-9_-]+")))
        assertTrue(a.challenge.matches(Regex("[A-Za-z0-9_-]{43}")))
        assertTrue(a.verifier != b.verifier)
    }

    @Test fun `JWT claims are read without checking the signature`() {
        val t = fakeJwt(sub = "abc", email = "x@y.z", exp = 2_000_000_000)
        assertEquals("abc", Jwt.subject(t)); assertEquals("x@y.z", Jwt.email(t))
        assertEquals(Instant.ofEpochSecond(2_000_000_000), Jwt.expiry(t))
        assertNull(Jwt.subject("garbage")); assertNull(Jwt.claims("a.b.c"))
    }

    @Test fun `query parsing decodes values and survives junk`() {
        val q = parseQuery("com.videomk.app://auth/callback?code=a%2Bb&state=s+t&flag&x=1&x=2&bad=%zz#frag")
        assertEquals("a+b", q["code"]); assertEquals("s t", q["state"]); assertEquals("1", q["x"]); assertEquals("", q["flag"]); assertFalse("bad" in q)
        assertTrue(parseQuery("com.videomk.app://auth/callback").isEmpty())
    }

    // sign in

    @Test fun `sign-in url asks for code + PKCE with the app redirect`() {
        val url = service(InMemoryTokenStore()).beginSignIn()
        assertEquals("/oauth2/authorize", url.encodedPath)
        assertEquals("code", url.queryParameter("response_type"))
        assertEquals("client-123", url.queryParameter("client_id"))
        assertEquals("com.videomk.app://auth/callback", url.queryParameter("redirect_uri"))
        assertEquals("openid email profile", url.queryParameter("scope"))
        assertEquals("S256", url.queryParameter("code_challenge_method"))
        assertNotNull(url.queryParameter("state")); assertNotNull(url.queryParameter("code_challenge"))
    }

    @Test fun `completing sign-in exchanges the code with the verifier and stores the tokens`() = runBlocking {
        val store = InMemoryTokenStore(); val auth = service(store)
        val url = auth.beginSignIn()
        server.enqueue(json(body = tokenBody()))
        auth.completeSignIn("com.videomk.app://auth/callback?code=CODE1&state=${url.queryParameter("state")}")
        val req = server.takeRequest()
        assertEquals("/oauth2/token", req.url.encodedPath)
        val form = req.body!!.utf8()
        assertTrue(form.contains("grant_type=authorization_code")); assertTrue(form.contains("code=CODE1")); assertTrue(form.contains("client_id=client-123"))
        assertTrue(form.contains("code_verifier=")); assertTrue(form.contains("redirect_uri=com.videomk.app%3A%2F%2Fauth%2Fcallback"))
        assertNotNull(store.load()); assertTrue(auth.isSignedIn); assertEquals("me@example.com", auth.email)
    }

    @Test fun `a wrong state, a cancelled page or a stray redirect never signs in`() = runBlocking {
        val store = InMemoryTokenStore(); val auth = service(store)
        auth.beginSignIn()
        try { auth.completeSignIn("com.videomk.app://auth/callback?code=C&state=WRONG"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Failed, e.kind) }
        val url = auth.beginSignIn()
        try { auth.completeSignIn("com.videomk.app://auth/callback?error=access_denied"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Failed, e.kind) }   // no state: dropped
        auth.beginSignIn()
        try { auth.completeSignIn("com.videomk.app://auth/callback?error=access_denied&state=WRONG"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Failed, e.kind) }
        val url2 = auth.beginSignIn()
        try { auth.completeSignIn("com.videomk.app://auth/callback?error=access_denied&state=${url2.queryParameter("state")}"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Cancelled, e.kind) }
        assertNotNull(url)
        try { auth.completeSignIn("com.videomk.app://auth/callback?code=C&state=S"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Failed, e.kind) }   // nothing pending
        assertNull(store.load()); assertEquals(0, server.requestCount)
    }

    @Test fun `a failed code exchange is a failure, not a session`() = runBlocking {
        val store = InMemoryTokenStore(); val auth = service(store)
        val url = auth.beginSignIn()
        server.enqueue(json(500, "{}"))
        try { auth.completeSignIn("x://y?code=C&state=${url.queryParameter("state")}"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Failed, e.kind) }
        assertNull(store.load())
    }

    // refresh

    @Test fun `a valid token is used as is`() = runBlocking {
        val tokens = Tokens(fakeJwt(sub = "u9"), "a", "r", Instant.now().plusSeconds(3000))
        val a = service(InMemoryTokenStore(tokens)).authorization()
        assertEquals("u9", a.userId); assertEquals(tokens.idToken, a.idToken); assertEquals(0, server.requestCount)
    }

    @Test fun `a token about to expire is refreshed and the new one is stored, keeping the refresh token`() = runBlocking {
        val store = InMemoryTokenStore(Tokens(fakeJwt(sub = "old"), "a", "r-old", Instant.now().plusSeconds(30)))
        server.enqueue(json(body = tokenBody(id = fakeJwt(sub = "fresh"), refresh = null)))
        val a = service(store).authorization()
        assertEquals("fresh", a.userId)
        val form = server.takeRequest().body!!.utf8()
        assertTrue(form.contains("grant_type=refresh_token")); assertTrue(form.contains("refresh_token=r-old"))
        assertEquals("r-old", store.load()!!.refreshToken)   // Cognito does not return a new refresh token
        assertTrue(store.load()!!.expiresAt.isAfter(Instant.now().plusSeconds(3000)))
    }

    @Test fun `many callers at once cause one refresh`() = runBlocking {
        val store = InMemoryTokenStore(Tokens(fakeJwt(sub = "old"), "a", "r-old", Instant.now().minusSeconds(10)))
        server.enqueue(json(body = tokenBody(id = fakeJwt(sub = "fresh"))))
        val auth = service(store)
        val results = (1..8).map { async { auth.authorization().userId } }.awaitAll()
        assertTrue(results.all { it == "fresh" })
        assertEquals(1, server.requestCount)
    }

    @Test fun `a revoked refresh token signs the user out and clears the store`() = runBlocking {
        val store = InMemoryTokenStore(Tokens(fakeJwt(), "a", "r-old", Instant.now().minusSeconds(10)))
        server.enqueue(json(400, """{"error":"invalid_grant"}"""))
        try { service(store).authorization(); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.SignedOut, e.kind) }
        assertNull(store.load())
    }

    @Test fun `an expired token without a refresh token is signed out and a network failure keeps the session`() = runBlocking {
        val noRefresh = InMemoryTokenStore(Tokens(fakeJwt(), "a", null, Instant.now().minusSeconds(10)))
        try { service(noRefresh).authorization(); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.SignedOut, e.kind) }
        assertNull(noRefresh.load())

        val offline = InMemoryTokenStore(Tokens(fakeJwt(), "a", "r", Instant.now().minusSeconds(10)))
        server.close()   // nothing is listening any more
        try { service(offline).authorization(); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Failed, e.kind) }
        assertNotNull(offline.load())   // offline is not "signed out"
    }

    @Test fun `no tokens means signed out and sign out clears`() = runBlocking {
        val store = InMemoryTokenStore(); val auth = service(store)
        try { auth.authorization(); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.SignedOut, e.kind) }
        store.save(Tokens(fakeJwt(), "a", "r", Instant.now().plusSeconds(3000)))
        assertTrue(auth.isSignedIn); auth.signOut(); assertFalse(auth.isSignedIn)
    }

    // social providers

    @Test fun `email sign-in has no provider parameter and is exactly today's request`() {
        val url = service(InMemoryTokenStore()).beginSignIn()
        assertNull(url.queryParameter("identity_provider"))
        assertEquals(setOf("response_type", "client_id", "redirect_uri", "scope", "state", "code_challenge_method", "code_challenge"), url.queryParameterNames)
    }

    @Test fun `Google and Apple add only identity_provider, with the exact Cognito names, and keep PKCE and state`() {
        val auth = service(InMemoryTokenStore())
        val g = auth.beginSignIn(SignInProvider.Google); val a = auth.beginSignIn(SignInProvider.Apple)
        assertEquals("Google", g.queryParameter("identity_provider")); assertEquals("SignInWithApple", a.queryParameter("identity_provider"))
        for (u in listOf(g, a)) {
            assertEquals("code", u.queryParameter("response_type")); assertEquals("S256", u.queryParameter("code_challenge_method"))
            assertEquals("com.videomk.app://auth/callback", u.queryParameter("redirect_uri")); assertTrue(u.queryParameter("state")!!.length >= 43)
            assertEquals(8, u.queryParameterNames.size)
        }
        assertTrue(g.queryParameter("state") != a.queryParameter("state") && g.queryParameter("code_challenge") != a.queryParameter("code_challenge"))
    }

    private val quirk = "error=invalid_request&error_description=Already+found+an+entry+for+username+Google_123"

    @Test fun `the already-found-entry error retries the same request once with fresh PKCE and state, then reports`() = runBlocking {
        val store = InMemoryTokenStore(); val auth = service(store)
        val first = auth.beginSignIn(SignInProvider.Google)
        val r = auth.completeSignIn("com.videomk.app://auth/callback?$quirk&state=${first.queryParameter("state")}")
        val retry = (r as SignInResult.Retry).url
        assertEquals("Google", retry.queryParameter("identity_provider"))
        assertTrue(retry.queryParameter("state") != first.queryParameter("state") && retry.queryParameter("code_challenge") != first.queryParameter("code_challenge"))
        assertTrue(auth.signInInProgress)
        try { auth.completeSignIn("com.videomk.app://auth/callback?$quirk&state=${retry.queryParameter("state")}"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.AccountLink, e.kind) }
        assertFalse(auth.signInInProgress); assertNull(store.load()); assertEquals(0, server.requestCount)
    }

    @Test fun `the retry still completes when the second attempt succeeds, and a quirk without matching state is not retried`() = runBlocking {
        val store = InMemoryTokenStore(); val auth = service(store)
        val first = auth.beginSignIn(SignInProvider.Apple)
        val retry = (auth.completeSignIn("com.videomk.app://auth/callback?$quirk&state=${first.queryParameter("state")}") as SignInResult.Retry).url
        server.enqueue(json(body = tokenBody()))
        assertEquals(SignInResult.Completed, auth.completeSignIn("com.videomk.app://auth/callback?code=C&state=${retry.queryParameter("state")}"))
        assertNotNull(store.load())
        auth.beginSignIn(SignInProvider.Apple)
        try { auth.completeSignIn("com.videomk.app://auth/callback?$quirk"); fail() } catch (e: AuthException) { assertEquals(AuthException.Kind.Failed, e.kind) }
        assertFalse(auth.signInInProgress)
    }

    @Test fun `build switches decide which buttons are drawn, in order, with email always last`() {
        assertEquals(listOf(SignInProvider.Email), SocialSwitches().options)
        assertEquals(listOf(SignInProvider.Google, SignInProvider.Email), SocialSwitches(google = true).options)
        assertEquals(listOf(SignInProvider.Apple, SignInProvider.Email), SocialSwitches(apple = true).options)
        assertEquals(listOf(SignInProvider.Google, SignInProvider.Apple, SignInProvider.Email), SocialSwitches(true, true).options)
        assertEquals("Sign in or create account", SignInProvider.Email.label(SocialSwitches().anySocial))   // off: today's wording
        assertEquals("Use email", SignInProvider.Email.label(SocialSwitches(google = true).anySocial))
        assertEquals("Continue with Google", SignInProvider.Google.label(true)); assertEquals("Continue with Apple", SignInProvider.Apple.label(true))
    }
}
