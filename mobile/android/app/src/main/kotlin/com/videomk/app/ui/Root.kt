package com.videomk.app.ui

import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import android.app.Application
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.Icon
import androidx.compose.runtime.remember
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.ui.platform.testTag
import androidx.navigation.compose.currentBackStackEntryAsState
import com.videomk.app.core.MediaCache
import com.videomk.app.data.FilePageDisk
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
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
import com.videomk.app.core.DeletionState
import com.videomk.app.core.SignInProvider
import com.videomk.app.core.SocialSwitches

val LocalContainer = compositionLocalOf<AppContainer> { error("no container") }
/** Same container, but null where a screen is shown without one (previews, tests). */
val LocalContainerOrNull = compositionLocalOf<AppContainer?> { null }

/** Everything below the activity: which screen is shown for which session phase. */
@OptIn(ExperimentalComposeUiApi::class)
@Composable
fun VideoMkRoot(app: AppViewModel, composer: ComposerViewModel, container: AppContainer, onSignIn: (SignInProvider) -> Unit, social: SocialSwitches = SocialSwitches()) {
    val state by app.state.collectAsState()
    // a presentation belongs to the account that uploaded it: signing out (or a revoked session) drops it and deletes its temporary copy
    androidx.compose.runtime.LaunchedEffect(state.phase is Phase.SignedOut) { if (state.phase is Phase.SignedOut) composer.removeDeck() }
    Surface(Modifier.fillMaxSize().semantics { if (BuildConfig.DEBUG) testTagsAsResourceId = true }, color = Vmk.colors.background) {
        val deletionState = app.deletion?.state?.collectAsState()?.value
        if (deletionState is DeletionState.Accepted) {
            DeletionDoneScreen(deletionState.apple, onOpenApple = { app.deletion?.openApple() }, onDone = { app.deletion?.dismissDone() })
        } else when (val phase = state.phase) {
            Phase.Launching -> FullScreenSpinner()
            Phase.NotConfigured, Phase.SignedOut -> SignInScreen(state, social, onSignIn)
            is Phase.SignedIn -> androidx.compose.runtime.CompositionLocalProvider(LocalContainer provides container, LocalContainerOrNull provides container) { SignedInNav(app, composer, container, phase.email) }
        }
    }
}

@Composable
private fun SignedInNav(app: AppViewModel, composer: ComposerViewModel, container: AppContainer, email: String?) {
    val nav = rememberNavController()
    val application = LocalContext.current.applicationContext as Application
    val backStack by nav.currentBackStackEntryAsState()
    val route = backStack?.destination?.route
    // one success haptic when a video that was being made becomes ready while the app is open
    val completions = app.state.collectAsState().value.completions
    val haptics = rememberHaptics()
    var seenCompletions by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableIntStateOf(completions) }
    androidx.compose.runtime.LaunchedEffect(completions) { if (completions > seenCompletions) haptics.play(com.videomk.app.core.DesignTokens.Haptic.VideoReady); seenCompletions = completions }
    val showTabs = route == "library" || route == "media"
    val mediaFactory = viewModelFactory { initializer { MediaViewModel(container.mediaApi, null, MediaCache(FilePageDisk(java.io.File(application.cacheDir, "media-pages"))), Int.MAX_VALUE, container.mediaUploads?.arrivals ?: com.videomk.app.core.ArrivalTracker()) } }
    Scaffold(
        containerColor = Vmk.colors.background, contentWindowInsets = WindowInsets(0),
        bottomBar = {
            if (showTabs && container.mediaApi != null) NavigationBar(containerColor = Vmk.colors.surface) {
                NavigationBarItem(selected = route == "library", onClick = { navigateTab(nav, "library") }, icon = { Icon(Icons.Filled.Movie, null) }, label = { Text(stringResource(R.string.nav_tab_videos)) }, colors = tabColors(), modifier = Modifier.testTag("tabVideos"))
                NavigationBarItem(selected = route == "media", onClick = { navigateTab(nav, "media") }, icon = { Icon(Icons.Filled.PhotoLibrary, null) }, label = { Text(stringResource(R.string.nav_tab_media)) }, colors = tabColors(), modifier = Modifier.testTag("tabMedia"))
            }
        },
    ) { inner ->
    NavHost(nav, startDestination = "library", modifier = Modifier.padding(inner).consumeWindowInsets(inner)) {
        composable("library") {
            LibraryScreen(
                app, composer,
                onOpenVideo = { nav.navigate("video/$it") },
                onOpenWallet = { nav.navigate("wallet") },
                onOpenSettings = { nav.navigate("settings") },
                onOpenMedia = { navigateTab(nav, "media") },
                onNewVideo = { nav.navigate("create") },
            )
        }
        composable("create") {
            CreateScreen(app, composer, onClose = { nav.popBackStack() }, onOpenWallet = { nav.navigate("wallet") })
        }
        composable("media") { entry ->
            val vm: MediaViewModel = viewModel(entry, key = "media-home", factory = mediaFactory)
            MediaScreen(vm, container.mediaUploads, onOpenCollection = { nav.navigate("media/collection/$it") }, onMakeVideo = { composer.addLibrary(it); navigateTab(nav, "library") }, organize = container.organize, onOpenCollections = { nav.navigate("media/collections") })
        }
        composable("media/collections") {
            val parent = remember(it) { nav.getBackStackEntry("media") }
            val vm: MediaViewModel = viewModel(parent, key = "media-home", factory = mediaFactory)
            val pref = container.organize?.pref?.collectAsState()?.value ?: com.videomk.app.core.OrganizePref.Ask
            CollectionsScreen(vm, pref, onBack = { nav.popBackStack() }, onOpen = { id -> nav.navigate("media/collection/$id") })
        }
        composable("media/collection/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) { entry ->
            val id = entry.arguments?.getString("id").orEmpty()
            val vm: MediaViewModel = viewModel(entry, key = "media-collection-$id", factory = viewModelFactory { initializer { MediaViewModel(container.mediaApi, id, null) } })
            CollectionScreen(vm, id, onBack = { nav.popBackStack() }, onMakeVideo = { composer.addLibrary(it); navigateTab(nav, "library") })
        }
        composable("video/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) { entry ->
            val id = entry.arguments?.getString("id").orEmpty()
            val detail: VideoDetailViewModel = viewModel(entry, key = "video-$id", factory = viewModelFactory { initializer { VideoDetailViewModel(application, container.backend, id) } })
            VideoDetailScreen(app, detail, container.http, onBack = { nav.popBackStack() }, onEdit = { nav.navigate("editor/$id") }, onMakeAnother = {
                composer.openCreate(container.createPrefs?.load(email)); nav.navigate("create")
            })
        }
        composable("editor/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) { entry ->
            val id = entry.arguments?.getString("id").orEmpty()
            val vm: EditorViewModel = viewModel(entry, key = "editor-$id", factory = viewModelFactory { initializer { EditorViewModel(id, container.backend, onChanged = { app.noteEdited() }) } })
            EditorScreen(vm, onClose = { nav.popBackStack() })
        }
        composable("wallet") { WalletScreen(app, onBack = { nav.popBackStack() }) }
        composable("settings") {
            val d = app.deletion
            val ds = d?.state?.collectAsState()?.value ?: DeletionState.Idle
            SettingsScreen(
                email, onBack = { nav.popBackStack() }, onSignOut = { app.signOut() },
                deletion = ds, onDeleteAccount = d?.let { f -> { typed: String -> f.start(typed) } }, onCancelDeletion = { d?.cancel() }, onDeletionClosed = { d?.reset() },
            )
        }
    }
    }
    androidx.compose.runtime.LaunchedEffect(Unit) { container.mediaUploads?.resumeIfAny(); container.organize?.resumeIfAny() }   // an interrupted upload queue continues on the next launch
}

@Composable
private fun tabColors() = androidx.compose.material3.NavigationBarItemDefaults.colors(
    selectedIconColor = Vmk.colors.primary, selectedTextColor = Vmk.colors.primary, indicatorColor = Vmk.colors.primaryContainer,
    unselectedIconColor = Vmk.colors.textSecondary, unselectedTextColor = Vmk.colors.textSecondary,
)

private fun navigateTab(nav: androidx.navigation.NavHostController, route: String) {
    nav.navigate(route) { popUpTo("library") { saveState = true }; launchSingleTop = true; restoreState = true }
}
