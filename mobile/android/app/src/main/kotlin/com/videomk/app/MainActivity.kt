package com.videomk.app

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import com.videomk.app.core.SignInProvider
import com.videomk.app.core.SocialSwitches
import com.videomk.app.ui.AppViewModel
import com.videomk.app.ui.ComposerViewModel
import com.videomk.app.ui.VideoMkRoot
import com.videomk.app.ui.VideoMkTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.withContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val container: AppContainer get() = (application as VideoMkApp).container

    // Lives in the ViewModelStore: a rotation gives this activity a new instance but the same view model, and start() runs its work once.
    private val app: AppViewModel by viewModels {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                AppViewModel(container.backend, container.auth, container.config, container.signedOut, accountApi = container.accountApi, wiper = { container.wipeLocalData(); withContext(Dispatchers.Main) { composer.clearAfterSend() } }) as T
        }
    }
    private val composer: ComposerViewModel by viewModels()
    private var abandonCheck: Job? = null
    /** Debug screenshots only: the intent whose `vmk_debug_fixture` extra picks a screen to draw (replaced by a newer intent, no restart needed). */
    private var fixtureIntent by androidx.compose.runtime.mutableStateOf<Intent?>(null)

    /** Android 12 and older apply the explicit app language here; 13+ is handled by the system (AppLanguage). */
    override fun attachBaseContext(newBase: android.content.Context) { super.attachBaseContext(com.videomk.app.data.AppLanguage(newBase).wrap(newBase)) }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val fresh = savedInstanceState == null
        if (DebugHooks.enabled) fixtureIntent = intent
        // `start()` is idempotent; the debug seed (compiled out of release) only runs for a fresh launch, never on rotation.
        app.start(seed = if (fresh && DebugHooks.enabled) { a -> DebugHooks.seed(intent, a) } else null)
        if (fresh) {
            composer.applyDebugDefaults(DebugHooks.defaultMinutes(intent))
            composer.addPhotoFiles(DebugHooks.photoFiles(intent))
            DebugHooks.prompt(intent)?.let { composer.text = it }
            DebugHooks.mediaFiles(intent).takeIf { it.isNotEmpty() }?.let { files -> container.mediaUploads?.add(contentResolver, files.map { android.net.Uri.fromFile(java.io.File(it)) }) }
            handleAuthIntent(intent)
        }
        lifecycleScope.launch { app.browserRequests.collect { openBrowser(it.toString()) } }
        app.deletion?.let { d -> lifecycleScope.launch { d.requests.collect { openBrowser(it.toString()) } } }
        setContent {
            val fixture = fixtureIntent?.let { DebugHooks.fixture(it) }   // always null in a release build
            VideoMkTheme { if (fixture != null) androidx.compose.runtime.key(fixtureIntent) { fixture() } else VideoMkRoot(app, composer, container, onSignIn = ::signIn, social = socialSwitches()) }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (DebugHooks.enabled && intent.hasExtra("vmk_debug_fixture")) fixtureIntent = intent
        handleAuthIntent(intent)
    }

    override fun onStop() {
        super.onStop()
        composer.dictation.stop()
    }

    override fun onResume() {
        super.onResume()
        // Back from the sign-in browser: if the redirect arrives it comes through onNewIntent first. If it does not arrive shortly,
        // the user closed the tab: stop the spinner and say nothing.
        if (app.browserOpen && wasPausedForBrowser) {
            abandonCheck?.cancel()
            abandonCheck = lifecycleScope.launch {
                delay(1200)
                if (app.browserOpen) { app.browserOpen = false; app.signInAbandoned() }
            }
        }
    }

    private var wasPausedForBrowser = false
    override fun onPause() {
        super.onPause()
        if (app.browserOpen) wasPausedForBrowser = true
    }

    /** The build's switches; a debug build can force both on for screenshots (DebugHooks.social). */
    private fun socialSwitches() = DebugHooks.social(this) ?: SocialSwitches(BuildConfig.VMK_AUTH_GOOGLE, BuildConfig.VMK_AUTH_APPLE)

    private fun signIn(provider: SignInProvider) {
        // a button that is switched off never reaches here, but a stale tap must not start a provider the build does not offer
        if (provider !in socialSwitches().options) return
        val url = app.beginSignIn(provider) ?: return
        openBrowser(url.toString())
    }

    private fun openBrowser(url: String) {
        try {
            wasPausedForBrowser = false
            app.browserOpen = true
            CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(this, Uri.parse(url))
        } catch (e: ActivityNotFoundException) {
            app.browserOpen = false
            app.signInAbandoned()
        } catch (e: Exception) {
            app.browserOpen = false
            app.signInAbandoned()
        }
    }

    private fun handleAuthIntent(intent: Intent?) {
        val data = intent?.data ?: return
        if (data.scheme != "com.videomk.app" || data.host != "auth") return
        // None of these starts anything: they only move an already running sign-in or account deletion one step on, and are ignored otherwise.
        if (data.path != "/callback" && data.path != "/signout" && data.path != "/apple-revoked") return
        // first, so that a page the handler asks for next (the sign-in page after the sign-out page) is not marked closed again
        abandonCheck?.cancel()
        app.browserOpen = false
        setIntent(Intent(this, MainActivity::class.java))   // a rotation must not replay the redirect
        when (data.path) {
            "/callback" -> app.onAuthCallback(data.toString())
            "/signout" -> app.deletion?.onLogoutReturned()
            "/apple-revoked" -> app.deletion?.onAppleReturn(data.getQueryParameter("status"))
        }
    }
}
