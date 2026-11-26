package com.videomk.app.core

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import okhttp3.FormBody
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.Instant
import java.util.Base64

/** The query parameters of a redirect URL (any scheme), percent-decoded. A repeated name keeps its first value. */
fun parseQuery(url: String): Map<String, String> {
    val q = url.substringAfter('?', "").substringBefore('#')
    if (q.isEmpty()) return emptyMap()
    val out = LinkedHashMap<String, String>()
    for (pair in q.split('&')) {
        if (pair.isEmpty()) continue
        val name = pair.substringBefore('=')
        val value = pair.substringAfter('=', "")
        try {
            out.putIfAbsent(java.net.URLDecoder.decode(name, "UTF-8"), java.net.URLDecoder.decode(value, "UTF-8"))
        } catch (e: IllegalArgumentException) { /* malformed escape: ignore this pair */ }
    }
    return out
}

data class PKCE(val verifier: String) {
    val challenge: String = base64Url(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))

    companion object {
        fun generate(random: SecureRandom = SecureRandom()): PKCE {
            val bytes = ByteArray(48).also { random.nextBytes(it) }
            return PKCE(base64Url(bytes))
        }

        fun base64Url(bytes: ByteArray): String = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    }
}

/** Reads claims from a JWT we received over TLS from our own auth server. Not a signature check: the API validates tokens. */
object Jwt {
    fun claims(token: String): JsonObject? {
        val parts = token.split(".")
        if (parts.size != 3) return null
        return try {
            val bytes = Base64.getUrlDecoder().decode(parts[1])
            parseObject(String(bytes, Charsets.UTF_8))
        } catch (e: Exception) { null }
    }

    fun subject(token: String): String? = claims(token)?.str("sub")
    fun email(token: String): String? = claims(token)?.str("email")
    fun expiry(token: String): Instant? = epochSeconds(claims(token)?.num("exp"))

    /** When the person last signed in interactively (`auth_time`); null when the token does not say. */
    fun authTime(token: String): Instant? = epochSeconds(claims(token)?.num("auth_time"))
}

data class Tokens(val idToken: String, val accessToken: String, val refreshToken: String?, val expiresAt: Instant)

interface TokenStore {
    fun load(): Tokens?
    fun save(tokens: Tokens)
    fun clear()
}

class InMemoryTokenStore(initial: Tokens? = null) : TokenStore {
    @Volatile private var tokens: Tokens? = initial
    override fun load() = tokens
    override fun save(tokens: Tokens) { this.tokens = tokens }
    override fun clear() { tokens = null }
}

fun interface AuthorizationProviding {
    /** A valid ID token (refreshed if needed) and the user id (the token's `sub`). */
    suspend fun authorization(): Authorization
}

data class Authorization(val idToken: String, val userId: String)

/**
 * How the hosted UI is entered. [Email] shows the hosted page; the others add `identity_provider=<idp>` (case-sensitive, exactly as the Cognito
 * identity provider is named) so the hosted page is skipped and the provider's own page opens in the same Custom Tab.
 */
enum class SignInProvider(val idp: String?) { Email(null), Google("Google"), Apple("SignInWithApple") }

/** The wording on the button. Google and Apple use their approved "Continue with ..." wording; email keeps today's wording when no social button is shown. */
fun SignInProvider.label(withSocial: Boolean): String = when (this) {
    SignInProvider.Google -> "Continue with Google"
    SignInProvider.Apple -> "Continue with Apple"
    SignInProvider.Email -> if (withSocial) "Continue with email" else "Sign in or create account"
}

/** Which social buttons this build shows (BuildConfig switches, all off by default). Email is always there. */
data class SocialSwitches(val google: Boolean = false, val apple: Boolean = false) {
    /** The buttons in the order they are drawn: Google, Apple, then email. With both switches off this is just email, i.e. today's screen. */
    val options: List<SignInProvider> get() = buildList {
        if (google) add(SignInProvider.Google)
        if (apple) add(SignInProvider.Apple)
        add(SignInProvider.Email)
    }
    val anySocial: Boolean get() = google || apple
}

sealed interface ReauthResult {
    data class Completed(val authorization: Authorization) : ReauthResult
    data class Retry(val url: HttpUrl) : ReauthResult
    /** The person signed in as somebody else: nothing was stored. */
    data object WrongAccount : ReauthResult
    data object Cancelled : ReauthResult
    data object Failed : ReauthResult
}

sealed interface SignInResult {
    data object Completed : SignInResult
    /** Cognito's known first-federated-sign-in quirk: the same authorize request is sent once more (with fresh PKCE and state). */
    data class Retry(val url: HttpUrl) : SignInResult
}

/**
 * Cognito hosted UI with authorization code + PKCE. The browser (Custom Tab) is driven by the UI; this type builds the URL, exchanges the code,
 * stores and refreshes tokens.
 */
class AuthService(
    private val config: AppConfig,
    private val store: TokenStore,
    private val http: OkHttpClient,
    private val now: () -> Instant = { Instant.now() },
) : DeletionSession {
    private data class PendingSignIn(val pkce: PKCE, val state: String, val provider: SignInProvider, val retried: Boolean)

    private val lock = Mutex()
    private var refreshJob: Deferred<Tokens>? = null
    private val scope = CoroutineScope(Dispatchers.IO)
    @Volatile private var pending: PendingSignIn? = null
    private data class PendingReauth(val pkce: PKCE, val state: String, val expectedSub: String, val retried: Boolean)
    @Volatile private var reauth: PendingReauth? = null

    val isSignedIn: Boolean get() = store.load() != null
    val email: String? get() = store.load()?.let { Jwt.email(it.idToken) }

    // sign in

    fun beginSignIn(provider: SignInProvider = SignInProvider.Email): HttpUrl = authorizeUrl(provider, retried = false)

    private fun authorizeUrl(provider: SignInProvider, retried: Boolean): HttpUrl {
        val pkce = PKCE.generate()
        val state = PKCE.generate().verifier
        pending = PendingSignIn(pkce, state, provider, retried)
        return buildAuthorizeUrl(pkce, state, provider.idp, forceLogin = false)
    }

    private fun buildAuthorizeUrl(pkce: PKCE, state: String, idp: String?, forceLogin: Boolean): HttpUrl =
        config.authDomain.newBuilder().addPathSegments("oauth2/authorize")
            .addQueryParameter("response_type", "code")
            .addQueryParameter("client_id", config.clientId)
            .addQueryParameter("redirect_uri", config.redirectUri)
            .addQueryParameter("scope", "openid email profile")
            .addQueryParameter("state", state)
            .addQueryParameter("code_challenge_method", "S256")
            .addQueryParameter("code_challenge", pkce.challenge)
            .also { b ->
                idp?.let { b.addQueryParameter("identity_provider", it) }
                // The classic hosted UI ignores both (docs/ACCOUNT_DELETION.md section 2); they make a later move to managed login correct without an app change.
                if (forceLogin) { b.addQueryParameter("prompt", "login"); b.addQueryParameter("max_age", "0") }
            }
            .build()

    // re-authentication (account deletion): the stored session is left untouched until the new sign-in is proven to be the same account

    /** The hosted-UI sign-out page (ends the browser session only; the app's own tokens are not touched). Returns to `com.videomk.app://auth/signout`. */
    override fun logoutUrl(): HttpUrl = config.authDomain.newBuilder().addPathSegments("logout")
        .addQueryParameter("client_id", config.clientId)
        .addQueryParameter("logout_uri", config.signOutUri)
        .build()

    /** A normal authorize (code + PKCE, hosted page: no identity provider, so any way of signing in is offered) with `prompt=login&max_age=0`. */
    override fun beginReauth(expectedSub: String): HttpUrl = reauthUrl(expectedSub, retried = false)

    private fun reauthUrl(expectedSub: String, retried: Boolean): HttpUrl {
        val pkce = PKCE.generate()
        val state = PKCE.generate().verifier
        reauth = PendingReauth(pkce, state, expectedSub, retried)
        return buildAuthorizeUrl(pkce, state, null, forceLogin = true)
    }

    override val reauthInProgress: Boolean get() = reauth != null
    override fun cancelReauth() { reauth = null }

    /**
     * Finishes the re-authentication. The new tokens replace the stored ones only when their `sub` is the one that asked to delete; a
     * different account is refused and nothing is stored. The state is checked first, for every callback.
     */
    override suspend fun completeReauth(callback: String): ReauthResult {
        val p = reauth ?: return ReauthResult.Failed
        reauth = null
        val query = parseQuery(callback)
        val state = query["state"]
        if (state == null || !MessageDigest.isEqual(state.toByteArray(), p.state.toByteArray())) return ReauthResult.Failed
        if (query["error"] != null) {
            if (isAlreadyFoundEntry(query["error_description"]) && !p.retried) return ReauthResult.Retry(reauthUrl(p.expectedSub, retried = true))
            return if (query["error"] == "access_denied") ReauthResult.Cancelled else ReauthResult.Failed
        }
        val code = query["code"] ?: return ReauthResult.Failed
        val t = try {
            tokenRequest(
                mapOf("grant_type" to "authorization_code", "client_id" to config.clientId, "code" to code, "redirect_uri" to config.redirectUri, "code_verifier" to p.pkce.verifier),
                previous = null,
            )
        } catch (e: AuthException) { return ReauthResult.Failed }
        val sub = Jwt.subject(t.idToken) ?: return ReauthResult.Failed
        if (sub != p.expectedSub) return ReauthResult.WrongAccount
        store.save(t)
        return ReauthResult.Completed(Authorization(t.idToken, sub))
    }

    /** True while a sign-in has been started and its redirect has not arrived yet. */
    val signInInProgress: Boolean get() = pending != null

    /** [callback] is the full redirect, e.g. `com.videomk.app://auth/callback?code=...&state=...` (not an http URL, so it is parsed here). */
    suspend fun completeSignIn(callback: String): SignInResult {
        val p = pending ?: throw AuthException(AuthException.Kind.Failed)
        pending = null
        val query = parseQuery(callback)
        // the state must match for every callback, error or not: a redirect that cannot prove it belongs to this sign-in is dropped
        val state = query["state"]
        if (state == null || !java.security.MessageDigest.isEqual(state.toByteArray(), p.state.toByteArray())) throw AuthException(AuthException.Kind.Failed)
        if (query["error"] != null) {
            if (isAlreadyFoundEntry(query["error_description"])) {
                if (!p.retried) return SignInResult.Retry(authorizeUrl(p.provider, retried = true))   // once; a second occurrence is reported
                throw AuthException(AuthException.Kind.AccountLink)
            }
            throw AuthException(AuthException.Kind.Cancelled)
        }
        val code = query["code"] ?: throw AuthException(AuthException.Kind.Failed)
        val t = tokenRequest(
            mapOf("grant_type" to "authorization_code", "client_id" to config.clientId, "code" to code, "redirect_uri" to config.redirectUri, "code_verifier" to p.pkce.verifier),
            previous = null,
        )
        store.save(t)
        return SignInResult.Completed
    }

    private fun isAlreadyFoundEntry(description: String?) = description?.contains("Already found an entry for username", ignoreCase = true) == true

    fun cancelSignIn() { pending = null }

    fun signOut() { pending = null; reauth = null; store.clear() }

    /** For automated tests and QA builds only: seed a session from tokens obtained out of band. */
    fun seed(tokens: Tokens) = store.save(tokens)

    // AuthorizationProviding

    override suspend fun authorization(): Authorization {
        var t = store.load() ?: throw AuthException(AuthException.Kind.SignedOut)
        if (java.time.Duration.between(now(), t.expiresAt).seconds < 120) t = refreshed(t)
        val sub = Jwt.subject(t.idToken) ?: throw AuthException(AuthException.Kind.Failed)
        return Authorization(t.idToken, sub)
    }

    private suspend fun refreshed(old: Tokens): Tokens {
        val job = lock.withLock {
            // another caller may have refreshed while this one waited for the lock
            store.load()?.let { cur -> if (cur != old && java.time.Duration.between(now(), cur.expiresAt).seconds >= 120) return cur }
            refreshJob?.takeIf { it.isActive } ?: run {
                val rt = old.refreshToken
                if (rt == null) { signOut(); throw AuthException(AuthException.Kind.SignedOut) }
                // one refresh in flight at a time, and it must outlive the caller that happened to start it
                scope.async {
                    try {
                        val t = tokenRequest(mapOf("grant_type" to "refresh_token", "client_id" to config.clientId, "refresh_token" to rt), previous = old)
                        store.save(t)
                        t
                    } catch (e: AuthException) {
                        if (e.kind == AuthException.Kind.SignedOut) signOut()   // refresh token revoked or expired
                        throw e
                    }
                }.also { refreshJob = it }
            }
        }
        return job.await()
    }

    private suspend fun tokenRequest(params: Map<String, String>, previous: Tokens?): Tokens = withContext(Dispatchers.IO) {
        val form = FormBody.Builder().also { b -> params.forEach { (k, v) -> b.add(k, v) } }.build()
        val req = Request.Builder().url(config.authDomain.newBuilder().addPathSegments("oauth2/token").build()).post(form).build()
        val (status, body) = try {
            http.newCall(req).execute().use { it.code to (it.body.string()) }
        } catch (e: java.io.IOException) { throw AuthException(AuthException.Kind.Failed) }
        if (status == 400 && previous != null) throw AuthException(AuthException.Kind.SignedOut)
        val j = if (status == 200) try { parseObject(body) } catch (e: Exception) { null } else null
        val id = j?.str("id_token"); val access = j?.str("access_token"); val expiresIn = j?.int("expires_in")
        if (id == null || access == null || expiresIn == null) throw AuthException(AuthException.Kind.Failed)
        Tokens(id, access, j.str("refresh_token") ?: previous?.refreshToken, now().plusSeconds(expiresIn.toLong()))
    }
}
