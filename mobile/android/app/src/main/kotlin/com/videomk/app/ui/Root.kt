package com.videomk.app.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import android.app.Application
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.selection.selectable
import androidx.compose.ui.semantics.isTraversalGroup
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
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
import com.videomk.app.core.FeedbackContext
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
    var feedbackFrom by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf<FeedbackContext?>(null) }
    // photos picked in My media and sent to Create stay selected until the video is sent or the draft is discarded: back from Create returns to the same selection
    var mediaSelecting by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(false) }
    var madeFromSelection by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(false) }
    val showTabs = (route == "library" || route == "media") && !(route == "media" && mediaSelecting)
    val mediaFactory = viewModelFactory { initializer { MediaViewModel(container.mediaApi, null, MediaCache(FilePageDisk(java.io.File(application.cacheDir, "media-pages"))), Int.MAX_VALUE, container.mediaUploads?.arrivals ?: com.videomk.app.core.ArrivalTracker()) } }
    // the tab bar and the New video button float over the content; the page fades out beneath them (docs/DESIGN_BAR_2026.md: glass only for what floats)
    val navBottom = with(androidx.compose.ui.platform.LocalDensity.current) { WindowInsets.navigationBars.getBottom(this).toDp() }
    val barSpace = if (showTabs) BAR_HEIGHT + navBottom else 0.dp
    Box(Modifier.fillMaxSize().background(Vmk.colors.background)) {
    androidx.compose.runtime.CompositionLocalProvider(LocalBarSpace provides barSpace) {
    NavHost(nav, startDestination = "library", modifier = Modifier.fillMaxSize()) {
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
            CreateScreen(app, composer, onClose = { nav.popBackStack() }, onOpenWallet = { nav.navigate("wallet") }, onSent = { nav.popBackStack("library", inclusive = false) })   // straight to Videos, where the Making card is (navigateTab would save Create and restore it at once)
        }
        composable("media") { entry ->
            val vm: MediaViewModel = viewModel(entry, key = "media-home", factory = mediaFactory)
            SelectionAfterCreate(vm, composer, madeFromSelection) { madeFromSelection = false }
            MediaScreen(vm, container.mediaUploads, onOpenCollection = { nav.navigate("media/collection/$it") }, onMakeVideo = { madeFromSelection = vm.selecting; makeVideoFrom(nav, composer, container, email, it) }, organize = container.organize, onOpenCollections = { nav.navigate("media/collections") }, onSelectingChange = { mediaSelecting = it })
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
            SelectionAfterCreate(vm, composer, madeFromSelection) { madeFromSelection = false }
            CollectionScreen(vm, id, onBack = { nav.popBackStack() }, onMakeVideo = { madeFromSelection = vm.selecting; makeVideoFrom(nav, composer, container, email, it) })
        }
        composable("video/{id}", arguments = listOf(navArgument("id") { type = NavType.StringType })) { entry ->
            val id = entry.arguments?.getString("id").orEmpty()
            val detail: VideoDetailViewModel = viewModel(entry, key = "video-$id", factory = viewModelFactory { initializer { VideoDetailViewModel(application, container.backend, id) { container.ratingPrompt.recordCompletion(it) } } })
            VideoDetailScreen(app, detail, container.http, onFeedback = { feedbackFrom = FeedbackContext.AfterVideo }, onBack = { nav.popBackStack() }, onEdit = { nav.navigate("editor/$id") }, onMakeAnother = {
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
                onFeedback = { feedbackFrom = FeedbackContext.Settings },
                deletion = ds, onDeleteAccount = d?.let { f -> { typed: String -> f.start(typed) } }, onCancelDeletion = { d?.cancel() }, onDeletionClosed = { d?.reset() },
            )
        }
    }
    }
    if (showTabs) FloatingBar(
        route, showMedia = container.mediaApi != null, onTab = { navigateTab(nav, it) },
        onNew = { composer.openCreate(container.createPrefs?.load(email)); nav.navigate("create") }, modifier = Modifier.align(Alignment.BottomCenter),
    )
    }
    feedbackFrom?.let { FeedbackSheet(container.feedbackApi, container.feedbackDraft, it, onClose = { feedbackFrom = null }) }
    val appState = app.state.collectAsState().value
    RatingHost(container, onLibrary = route == "library", creating = route == "create" || appState.pending.any { it.state == com.videomk.app.core.PendingVideo.State.Sending })
    androidx.compose.runtime.LaunchedEffect(Unit) { container.mediaUploads?.resumeIfAny(); container.organize?.resumeIfAny() }   // an interrupted upload queue continues on the next launch
}

/** How much of the bottom of a top-level screen the floating bar covers (0 where there is no bar): lists add it to their bottom padding so the last row can scroll clear. */
val LocalBarSpace = compositionLocalOf { 0.dp }
private val BAR_HEIGHT = 84.dp

/**
 * The floating bar: a pill with the two places (Videos, Media) and, apart from it, the round New video button with the play-sparkle glyph (never a bare plus).
 * The page fades into the background beneath it, so content never ends in a hard line.
 */
@Composable
private fun FloatingBar(route: String?, showMedia: Boolean, onTab: (String) -> Unit, onNew: () -> Unit, modifier: Modifier = Modifier) {
    val bg = Vmk.colors.background
    Row(
        modifier.fillMaxWidth().background(androidx.compose.ui.graphics.Brush.verticalGradient(0f to bg.copy(alpha = 0f), 0.55f to bg.copy(alpha = 0.92f), 1f to bg))
            .navigationBarsPadding().padding(horizontal = Vmk.space.screen).padding(top = Vmk.space.xl, bottom = Vmk.space.s),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m),
    ) {
        if (showMedia) Row(
            Modifier.vmkShadow(2, CircleShape, Vmk.colors.dark).clip(CircleShape).background(Vmk.colors.surface).padding(4.dp).semantics { isTraversalGroup = true },
            horizontalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            BarTab(stringResource(R.string.nav_tab_videos), if (route == "library") Sym.VideosFilled else Sym.Videos, route == "library", "tabVideos") { onTab("library") }
            BarTab(stringResource(R.string.nav_tab_media), if (route == "media") Sym.MediaFilled else Sym.PhotoLibrary, route == "media", "tabMedia") { onTab("media") }
        }
        Spacer(Modifier.weight(1f))
        val newVideo = stringResource(R.string.lib_new_video)
        Box(
            Modifier.size(Vmk.primaryButton).vmkGlow(CircleShape).clip(CircleShape).background(Vmk.gradient)
                .clickable(role = Role.Button, onClickLabel = newVideo, onClick = onNew).semantics { contentDescription = newVideo }.testTag("newVideoFab"),
            contentAlignment = Alignment.Center,
        ) { Icon(Sym.PlaySparkle, null, tint = Vmk.colors.onPrimary, modifier = Modifier.size(28.dp)) }
    }
}

/** One place in the bar: icon over its name; the selected one sits on a tonal pill and says so to TalkBack (state is never colour alone: the icon fills too). */
@Composable
private fun BarTab(label: String, icon: androidx.compose.ui.graphics.vector.ImageVector, selected: Boolean, tag: String, onClick: () -> Unit) {
    val haptics = rememberHaptics()
    val c = if (selected) Vmk.colors.primary else Vmk.colors.textSecondary
    androidx.compose.foundation.layout.Column(
        Modifier.heightIn(min = Vmk.minTouch).widthIn(min = 88.dp).clip(CircleShape).background(if (selected) Vmk.colors.primaryContainer else androidx.compose.ui.graphics.Color.Transparent)
            .selectable(selected, role = Role.Tab) { haptics.play(com.videomk.app.core.DesignTokens.Haptic.Selection); onClick() }.padding(horizontal = Vmk.space.l, vertical = 6.dp).testTag(tag),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(icon, null, tint = c, modifier = Modifier.size(22.dp))
        Text(label, style = androidx.compose.material3.MaterialTheme.typography.labelSmall, color = c, maxLines = 1)
    }
}

private fun navigateTab(nav: androidx.navigation.NavHostController, route: String) {
    nav.navigate(route) { popUpTo("library") { saveState = true }; launchSingleTop = true; restoreState = true }
}

/** "Make a video" from photos: they join the draft, Create opens with the prompt focused, and Media stays underneath (back returns to it). */
private fun makeVideoFrom(nav: androidx.navigation.NavHostController, composer: ComposerViewModel, container: AppContainer, email: String?, photos: List<com.videomk.app.core.MediaPhoto>) {
    composer.addLibrary(photos)
    composer.openCreate(container.createPrefs?.load(email))
    composer.requestFocus()
    nav.navigate("create")
}

/**
 * Back on a Media screen after Create: if the video was sent or the draft discarded (no photos left in the draft) the selection ends; if the draft still holds photos
 * (the person pressed back and kept it) the selection becomes exactly those photos, so what Media shows matches what Create will use.
 */
@Composable
private fun SelectionAfterCreate(vm: MediaViewModel, composer: ComposerViewModel, made: Boolean, onDone: () -> Unit) {
    androidx.compose.runtime.LaunchedEffect(made, composer.library.size) {
        if (!made) return@LaunchedEffect
        if (composer.library.isEmpty()) { vm.clearSelection(); onDone() }
        else vm.startPicker(composer.library.toList())
    }
}
