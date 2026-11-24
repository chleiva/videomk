package com.videomk.app

import android.content.Context
import com.videomk.app.core.ApiBackend
import com.videomk.app.core.ApiClient
import com.videomk.app.core.AppConfig
import com.videomk.app.core.AuthService
import com.videomk.app.core.Backend
import com.videomk.app.core.PhotoUploader
import com.videomk.app.core.TokenStore
import com.videomk.app.core.defaultHttpClient
import com.videomk.app.data.SecureTokenStore
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/** Manual dependency injection: one place that builds the app-wide objects. */
class AppContainer(
    val appContext: Context,
    val config: AppConfig? = AppConfig.from(BuildConfig.API_BASE, BuildConfig.AUTH_DOMAIN, BuildConfig.CLIENT_ID, BuildConfig.AUTH_REDIRECT_URI),
    store: TokenStore? = null,
) {
    val http = defaultHttpClient()
    private val signedOutEvents = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    /** Emits when the server or the token refresh says the session is over. */
    val signedOut: SharedFlow<Unit> get() = signedOutEvents

    // Lazy: opening the Keystore-backed session store takes a moment, so it is first touched from a background thread (see warmUp).
    val auth: AuthService? by lazy { config?.let { AuthService(it, store ?: SecureTokenStore.create(appContext), http) } }
    val backend: Backend? by lazy {
        val a = auth
        if (config != null && a != null) {
            val api = ApiClient(config, a, http, appVersion = BuildConfig.VERSION_NAME)
            ApiBackend(api, PhotoUploader(api, http)) { signedOutEvents.tryEmit(Unit) }
        } else null
    }

    fun warmUp() { Thread { runCatching { auth } }.start() }
}
