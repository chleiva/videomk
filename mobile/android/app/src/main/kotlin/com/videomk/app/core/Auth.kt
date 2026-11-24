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
 * Cognito hosted UI with authorization code + PKCE. The browser (Custom Tab) is driven by the UI; this type builds the URL, exchanges the code,
 * stores and refreshes tokens.
 */
class AuthService(
    private val config: AppConfig,
    private val store: TokenStore,
    private val http: OkHttpClient,
    private val now: () -> Instant = { Instant.now() },
) : AuthorizationProviding {
    private data class PendingSignIn(val pkce: PKCE, val state: String)

    private val lock = Mutex()
    private var refreshJob: Deferred<Tokens>? = null
    private val scope = CoroutineScope(Dispatchers.IO)
    @Volatile private var pending: PendingSignIn? = null

    val isSignedIn: Boolean get() = store.load() != null
    val email: String? get() = store.load()?.let { Jwt.email(it.idToken) }

    // sign in

    fun beginSignIn(): HttpUrl {
        val pkce = PKCE.generate()
        val state = PKCE.generate().verifier
        pending = PendingSignIn(pkce, state)
        return config.authDomain.newBuilder().addPathSegments("oauth2/authorize")
            .addQueryParameter("response_type", "code")
            .addQueryParameter("client_id", config.clientId)
            .addQueryParameter("redirect_uri", config.redirectUri)
            .addQueryParameter("scope", "openid email profile")
            .addQueryParameter("state", state)
            .addQueryParameter("code_challenge_method", "S256")
            .addQueryParameter("code_challenge", pkce.challenge)
            .build()
    }

    /** True while a sign-in has been started and its redirect has not arrived yet. */
    val signInInProgress: Boolean get() = pending != null

    /** [callback] is the full redirect, e.g. `com.videomk.app://auth/callback?code=...&state=...` (not an http URL, so it is parsed here). */
    suspend fun completeSignIn(callback: String) {
        val p = pending ?: throw AuthException(AuthException.Kind.Failed)
        pending = null
        val query = parseQuery(callback)
        if (query["error"] != null) throw AuthException(AuthException.Kind.Cancelled)
        val code = query["code"]
        if (code == null || query["state"] != p.state) throw AuthException(AuthException.Kind.Failed)
        val t = tokenRequest(
            mapOf("grant_type" to "authorization_code", "client_id" to config.clientId, "code" to code, "redirect_uri" to config.redirectUri, "code_verifier" to p.pkce.verifier),
            previous = null,
        )
        store.save(t)
    }

    fun cancelSignIn() { pending = null }

    fun signOut() { pending = null; store.clear() }

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
