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
        DebugHooks.fakeBackend(appContext) ?: if (config != null && a != null) {
            val api = ApiClient(config, a, http, appVersion = BuildConfig.VERSION_NAME)
            ApiBackend(api, PhotoUploader(api, http)) { signedOutEvents.tryEmit(Unit) }
        } else null
    }

    /** My media. Null when the app has no server address. The debug build can swap in fake data for screenshots (see DebugHooks). */
    val mediaApi: com.videomk.app.core.MediaApi? by lazy {
        val a = auth
        if (config != null && a != null) DebugHooks.fakeMedia(appContext) ?: com.videomk.app.core.ApiMediaApi(ApiClient(config, a, http, appVersion = BuildConfig.VERSION_NAME)) else null
    }
    private val appScope = kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.Default)
    val mediaUploads: com.videomk.app.data.MediaUploadController? by lazy { mediaApi?.let { com.videomk.app.data.MediaUploadController(appContext, it, http, appScope, DebugHooks.fakePoster(appContext)) } }

    /** The capabilities and the request check. The debug build can swap in fake ones (see DebugHooks). */
    val intake: com.videomk.app.core.IntakeApi? by lazy {
        val a = auth
        if (config != null && a != null) DebugHooks.fakeIntake(appContext) ?: com.videomk.app.core.ApiIntake(ApiClient(config, a, http, appVersion = BuildConfig.VERSION_NAME)) else null
    }
    /** Presentations (PowerPoint and PDF): the three calls and the streaming upload. The debug build can swap in fakes (see DebugHooks). */
    val deckApi: com.videomk.app.core.DeckApi? by lazy {
        val a = auth
        if (config != null && a != null) DebugHooks.fakeDeck(appContext) ?: com.videomk.app.core.ApiDeckApi(ApiClient(config, a, http, appVersion = BuildConfig.VERSION_NAME)) else null
    }
    val deckUploader: com.videomk.app.core.DeckUploader? by lazy { DebugHooks.fakeDeckUploader(appContext) ?: com.videomk.app.core.HttpDeckUploader(http) }
    val createPrefs: com.videomk.app.data.CreatePrefsStore by lazy { com.videomk.app.data.CreatePrefsStore(appContext) }

    val organize: com.videomk.app.data.OrganizeController? by lazy { mediaApi?.let { com.videomk.app.data.OrganizeController(appContext, it, appScope) } }

    /** The account deletion calls (the API client itself). Null when the app has no server address. */
    val accountApi: com.videomk.app.core.AccountApi? by lazy {
        val a = auth
        if (config != null && a != null) ApiClient(config, a, http, appVersion = BuildConfig.VERSION_NAME) else null
    }

    /** Everything this device keeps for the person: used once the server accepted an account deletion. Never throws; a failing step does not stop the others. */
    suspend fun wipeLocalData() = com.videomk.app.data.LocalDataWiper.wipe(
        appContext,
        stopWork = { mediaUploads?.cancel(); organize?.cancelJob() },
        deckCache = java.io.File(appContext.cacheDir, "deck"),
        clearTokens = { auth?.signOut() },
    )

    fun warmUp() { Thread { runCatching { auth } }.start() }
}
