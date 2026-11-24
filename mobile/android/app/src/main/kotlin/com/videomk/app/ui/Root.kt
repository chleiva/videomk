package com.videomk.app.ui

import android.app.Application
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.videomk.app.AppContainer
import com.videomk.app.BuildConfig
import com.videomk.app.VideoMkApp

val LocalContainer = compositionLocalOf<AppContainer> { error("no container") }

/** Everything below the activity: which screen is shown for which session phase. */
@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun VideoMkRoot(app: AppViewModel, composer: ComposerViewModel, container: AppContainer, onSignIn: () -> Unit) {
    val state by app.state.collectAsState()
    Surface(Modifier.fillMaxSize().semantics { if (BuildConfig.DEBUG) testTagsAsResourceId = true }, color = Vmk.colors.background) {
        when (val phase = state.phase) {
            Phase.Launching -> FullScreenSpinner()
            Phase.NotConfigured, Phase.SignedOut -> SignInScreen(state, onSignIn)
            is Phase.SignedIn -> SignedInNav(app, composer, container, phase.email)
        }
    }
}

@Composable
private fun SignedInNav(app: AppViewModel, composer: ComposerViewModel, container: AppContainer, email: String?) {
    val nav = rememberNavController()
    val application = LocalContext.current.applicationContext as Application
    NavHost(nav, startDestination = "library") {
        composable("library") {
            LibraryScreen(
                app, composer,
                onOpenVideo = { nav.navigate("video/$it") },
                onOpenWallet = { nav.navigate("wallet") },
                onOpenSettings = { nav.navigate("settings") },
            )
        }
        composable("video/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) { entry ->
            val id = entry.arguments?.getString("id").orEmpty()
            val detail: VideoDetailViewModel = viewModel(entry, key = "video-$id", factory = viewModelFactory { initializer { VideoDetailViewModel(application, container.backend, id) } })
            VideoDetailScreen(app, detail, container.http, onBack = { nav.popBackStack() }, onEdit = { nav.navigate("editor/$id") })
        }
        composable("editor/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) { entry ->
            val id = entry.arguments?.getString("id").orEmpty()
            val vm: EditorViewModel = viewModel(entry, key = "editor-$id", factory = viewModelFactory { initializer { EditorViewModel(id, container.backend, onChanged = { app.noteEdited() }) } })
            EditorScreen(vm, onClose = { nav.popBackStack() })
        }
        composable("wallet") { WalletScreen(app, onBack = { nav.popBackStack() }) }
        composable("settings") { SettingsScreen(email, onBack = { nav.popBackStack() }, onSignOut = { app.signOut() }) }
    }
}
