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
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import com.videomk.app.ui.AppViewModel
import com.videomk.app.ui.ComposerViewModel
import com.videomk.app.ui.VideoMkRoot
import com.videomk.app.ui.VideoMkTheme
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val container: AppContainer get() = (application as VideoMkApp).container

    // Lives in the ViewModelStore: a rotation gives this activity a new instance but the same view model, and start() runs its work once.
    private val app: AppViewModel by viewModels {
        object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                AppViewModel(container.backend, container.auth, container.config, container.signedOut) as T
        }
    }
    private val composer: ComposerViewModel by viewModels()
    private var abandonCheck: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val fresh = savedInstanceState == null
        // `start()` is idempotent; the debug seed (compiled out of release) only runs for a fresh launch, never on rotation.
        app.start(seed = if (fresh && DebugHooks.enabled) { a -> DebugHooks.seed(intent, a) } else null)
        if (fresh) {
            composer.applyDebugDefaults(DebugHooks.defaultMinutes(intent))
            composer.addPhotoFiles(DebugHooks.photoFiles(intent))
            DebugHooks.prompt(intent)?.let { composer.text = it; composer.requestFocus() }
            DebugHooks.mediaFiles(intent).takeIf { it.isNotEmpty() }?.let { files -> container.mediaUploads?.add(contentResolver, files.map { android.net.Uri.fromFile(java.io.File(it)) }) }
            handleAuthIntent(intent)
        }
        setContent {
            VideoMkTheme { VideoMkRoot(app, composer, container, onSignIn = ::signIn) }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
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

    private fun signIn() {
        val url = app.beginSignIn() ?: return
        try {
            wasPausedForBrowser = false
            app.browserOpen = true
            CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(this, Uri.parse(url.toString()))
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
        if (data.scheme == "com.videomk.app" && data.host == "auth") {
            abandonCheck?.cancel()
            app.browserOpen = false
            app.onAuthCallback(data.toString())
            setIntent(Intent(this, MainActivity::class.java))   // a rotation must not replay the redirect
        }
    }
}
