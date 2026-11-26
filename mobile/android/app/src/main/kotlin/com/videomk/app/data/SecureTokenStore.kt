package com.videomk.app.data

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.videomk.app.core.InMemoryTokenStore
import com.videomk.app.core.TokenStore
import com.videomk.app.core.Tokens
import java.time.Instant

/**
 * The sign-in session, encrypted with a key held in the Android Keystore (EncryptedSharedPreferences, AES-256).
 * The Keystore can fail on a handful of devices (a restored backup, a changed lock screen, a corrupted key): in that case the stored
 * session is dropped and the user simply signs in again. Storage problems never crash the app.
 */
@Suppress("DEPRECATION")   // androidx.security.crypto is deprecated but is still the supported way to get Keystore-backed preferences without a custom cipher
class SecureTokenStore private constructor(private val prefs: SharedPreferences?, private val fallback: InMemoryTokenStore = InMemoryTokenStore()) : TokenStore {

    override fun load(): Tokens? {
        val p = prefs ?: return fallback.load()
        return try {
            val id = p.getString(ID, null) ?: return null
            Tokens(id, p.getString(ACCESS, "") ?: "", p.getString(REFRESH, null), Instant.ofEpochMilli(p.getLong(EXPIRES, 0)))
        } catch (e: Exception) {
            Log.w(TAG, "token read failed, treating as signed out", e)
            null
        }
    }

    override fun save(tokens: Tokens) {
        val p = prefs
        if (p == null) { fallback.save(tokens); return }
        try {
            p.edit().putString(ID, tokens.idToken).putString(ACCESS, tokens.accessToken).putString(REFRESH, tokens.refreshToken)
                .putLong(EXPIRES, tokens.expiresAt.toEpochMilli()).apply()
        } catch (e: Exception) {
            Log.w(TAG, "token write failed, keeping the session in memory only", e)
            fallback.save(tokens)
        }
    }

    override fun clear() {
        fallback.clear()
        // commit, not apply: a wipe must be on disk before the app says it is done
        try { prefs?.edit()?.clear()?.commit() } catch (e: Exception) { Log.w(TAG, "token clear failed", e) }
    }

    companion object {
        private const val TAG = "SecureTokenStore"
        private const val FILE = "vmk_session"
        private const val ID = "id_token"
        private const val ACCESS = "access_token"
        private const val REFRESH = "refresh_token"
        private const val EXPIRES = "expires_at_ms"

        fun create(context: Context): SecureTokenStore {
            val app = context.applicationContext
            fun open(): SharedPreferences {
                val key = MasterKey.Builder(app).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
                return EncryptedSharedPreferences.create(
                    app, FILE, key,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
                )
            }
            val prefs = try { open() } catch (first: Exception) {
                Log.w(TAG, "keystore problem, resetting the session store", first)
                try {
                    app.deleteSharedPreferences(FILE)
                    open()
                } catch (second: Exception) {
                    Log.e(TAG, "secure storage unavailable, session will not survive a restart", second)
                    null
                }
            }
            return SecureTokenStore(prefs)
        }
    }
}
