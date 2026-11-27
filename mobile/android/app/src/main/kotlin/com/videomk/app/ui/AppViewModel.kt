package com.videomk.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.videomk.app.R
import com.videomk.app.core.RetryResult
import com.videomk.app.core.ApiError
import com.videomk.app.core.Txt
import com.videomk.app.core.SubmitOutcome
import com.videomk.app.core.AppConfig
import com.videomk.app.core.AuthException
import com.videomk.app.core.AuthService
import com.videomk.app.core.SignInProvider
import com.videomk.app.core.SignInResult
import com.videomk.app.core.Backend
import com.videomk.app.core.Brief
import com.videomk.app.core.PhotoMeta
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.LibraryEntry
import com.videomk.app.core.LibraryMerge
import com.videomk.app.core.PendingVideo
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import com.videomk.app.core.WalletInfo
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl

sealed interface Phase {
    data object Launching : Phase
    data object NotConfigured : Phase
    data object SignedOut : Phase
    data class SignedIn(val email: String?) : Phase
}

sealed interface LoadState {
    data object Idle : LoadState
    data object Loading : LoadState
    data object Loaded : LoadState
    data class Failed(val message: String) : LoadState
}

data class StageInfo(val stage: VideoStatus.Stage, val sinceMillis: Long, val deck: VideoStatus.DeckStage? = null)

data class AppState(
    val phase: Phase = Phase.Launching,
    val videos: List<VideoItem> = emptyList(),
    val loadState: LoadState = LoadState.Idle,
    val pending: List<PendingVideo> = emptyList(),
    val wallet: WalletInfo? = null,
    /** Bumps when a video finishes. */
    val completions: Int = 0,
    val signInError: String? = null,
    val isSigningIn: Boolean = false,
    /** Which button started the running sign-in (it shows the spinner), null when none is running. */
    val signInProvider: SignInProvider? = null,
    /** The last refresh could not reach the server: what is on screen may be out of date. */
    val offline: Boolean = false,
    val stageSince: Map<String, StageInfo> = emptyMap(),
    val briefs: Map<String, String> = emptyMap(),
    val minutes: Map<String, Double> = emptyMap(),
    /** Videos made from a presentation (their deck is gone once planning starts, so a failed one is made again from Create, not retried from its text). */
    val deckVideos: Set<String> = emptySet(),
    /** A message about "Try again" or removing a failed video (shown once, then dismissed): the server's own text, or that it cannot be done from here. */
    val retryNotice: String? = null,
    /** Failed videos whose Try again is being sent (the button waits; the server also answers a second tap with the current state). */
    val retrying: Set<String> = emptySet(),
) {
    val entries: List<LibraryEntry> get() = LibraryMerge.entries(pending, videos)
    val hasRunningVideos: Boolean get() = videos.any { it.status.isRunning } || pending.any { it.state == PendingVideo.State.Sending }
    fun video(id: String): VideoItem? = videos.firstOrNull { it.id == id }
}

/**
 * The session and the library, shared by every screen. It lives in the activity's ViewModelStore, so a rotation never rebuilds it and
 * [start] runs its work exactly once per process (the iOS app had a bug where the root task ran twice after a rotation).
 */
class AppViewModel(
    private val backend: Backend?,
    private val auth: AuthService?,
    val config: AppConfig?,
    signedOutEvents: Flow<Unit>,
    private val clock: () -> Long = System::currentTimeMillis,
    accountApi: com.videomk.app.core.AccountApi? = null,
    private val wiper: com.videomk.app.core.LocalWiper = com.videomk.app.core.LocalWiper { },
) : ViewModel() {
    private val _state = MutableStateFlow(AppState())
    val state: StateFlow<AppState> = _state.asStateFlow()
    /** Bumps whenever an edit was published or previewed, so an open video page reloads its player. */
    private val _editRevision = MutableStateFlow(0)
    val editRevision: StateFlow<Int> = _editRevision.asStateFlow()

    private val photoData = HashMap<String, List<ByteArray>>()   // photos waiting to be uploaded, kept until the video is accepted (a retry needs no new selection)
    private val libraryData = HashMap<String, List<String>>()   // My media photos of a pending request (ids only: nothing to upload)
    private val briefData = HashMap<String, kotlinx.serialization.json.JsonObject>()   // the answers of the request check, kept for a retry
    private val deckData = HashMap<String, String>()   // the ready presentation's id of a pending request (the file is already on the server)
    private val photoMeta = HashMap<String, List<PhotoMeta?>>()   // what was read from each photo, same order as photoData
    private val attachments = HashMap<String, Int>()   // videos made in this session: how many photos (uploaded, library) and presentations they were made with, so an older server's fallback never drops them
    private val refreshLock = Mutex()
    private var started = false
    /** True while the sign-in browser tab is open (so the screen can tell "came back without finishing" from "redirect arriving"). Survives rotation. */
    var browserOpen = false
    var startCount = 0
        private set

    /** Account deletion (Settings > Delete account). Null when the app has no server or sign-in configured. */
    val deletion: com.videomk.app.core.AccountDeletionFlow? = if (auth != null && accountApi != null) {
        com.videomk.app.core.AccountDeletionFlow(auth, accountApi, wiper, viewModelScope, onWiped = { signOut() }, onSessionEnded = { signOut() })
    } else null

    init {
        viewModelScope.launch { signedOutEvents.collect { signOut() } }
    }

    /** Once per process. Safe to call from every `onCreate`. */
    fun start(seed: ((AuthService) -> Unit)? = null) {
        if (started) return
        started = true
        startCount++
        val a = auth
        if (a == null) { update { it.copy(phase = Phase.NotConfigured) }; return }
        viewModelScope.launch {
            val phase = withContext(Dispatchers.IO) {
                seed?.invoke(a)
                if (a.isSignedIn) Phase.SignedIn(a.email) else Phase.SignedOut
            }
            update { it.copy(phase = phase) }
        }
    }

    private inline fun update(f: (AppState) -> AppState) = _state.update { f(it) }

    // sign in / out

    /** The Cognito page to show in a Custom Tab, or null when sign-in is already running or the app isn't configured. */
    fun beginSignIn(provider: SignInProvider = SignInProvider.Email): HttpUrl? {
        val a = auth ?: return null
        if (_state.value.isSigningIn) return null
        update { it.copy(isSigningIn = true, signInProvider = provider, signInError = null) }
        return a.beginSignIn(provider)
    }

    /** Pages the activity must open in the Custom Tab besides the first one: the automatic retry of Cognito's "Already found an entry" quirk. */
    private val _browserRequests = MutableSharedFlow<HttpUrl>(extraBufferCapacity = 1)
    val browserRequests: SharedFlow<HttpUrl> = _browserRequests

    /** The user left the browser without finishing. Nothing to report. */
    fun signInAbandoned() {
        deletion?.onBrowserAbandoned()   // only acts while the deletion's sign-in step is open
        auth?.cancelSignIn()
        update { it.copy(isSigningIn = false, signInProvider = null) }
    }

    fun onAuthCallback(callback: String) {
        val a = auth ?: return
        val d = deletion
        if (d != null && d.reauthPending) { d.onReauthCallback(callback); return }   // the redirect of the "sign in again" step of an account deletion
        if (!a.signInInProgress) return   // a stray or repeated redirect
        viewModelScope.launch {
            try {
                when (val r = a.completeSignIn(callback)) {
                    is SignInResult.Retry -> _browserRequests.emit(r.url)   // still signing in: the spinner stays
                    SignInResult.Completed -> {
                        val email = withContext(Dispatchers.IO) { a.email }
                        update { it.copy(phase = Phase.SignedIn(email), isSigningIn = false, signInProvider = null) }
                    }
                }
            } catch (e: AuthException) {
                val message = when (e.kind) { AuthException.Kind.Cancelled -> null; AuthException.Kind.AccountLink -> ACCOUNT_LINK_FAILED; else -> SIGN_IN_FAILED }
                update { it.copy(isSigningIn = false, signInProvider = null, signInError = message) }
            } catch (e: CancellationException) { throw e } catch (e: Exception) {
                update { it.copy(isSigningIn = false, signInProvider = null, signInError = SIGN_IN_FAILED) }
            }
        }
    }

    fun signOut() {
        auth?.signOut()
        photoData.clear(); photoMeta.clear(); libraryData.clear(); briefData.clear(); deckData.clear()
        update { AppState(phase = Phase.SignedOut) }
    }

    // library

    suspend fun refresh() {
        val b = backend ?: return
        refreshLock.withLock {
            if (_state.value.videos.isEmpty() && _state.value.loadState !is LoadState.Loaded) update { it.copy(loadState = LoadState.Loading) }
            try {
                viewModelScope.launch { refreshWallet() }   // credits load alongside the list
                val fresh = b.listVideos()
                announceFinished(_state.value, fresh)
                update { s ->
                    val (stages, completions) = track(s, fresh)
                    s.copy(
                        videos = com.videomk.app.core.VideoMerge.reuse(s.videos, fresh), stageSince = stages, completions = s.completions + completions, offline = false,
                        pending = LibraryMerge.stillPending(s.pending, fresh), loadState = LoadState.Loaded,
                    )
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError.Unauthorized) {
                signOut()
            } catch (e: Exception) {
                val offline = e is ApiError.Network
                // keep what we have on screen; only a first load shows a full-screen error
                update { s ->
                    s.copy(offline = offline, loadState = if (s.videos.isEmpty() && s.loadState !is LoadState.Loaded) LoadState.Failed((e as? ApiError)?.message ?: Txt.s(R.string.nav_load_videos_failed)) else LoadState.Loaded)
                }
            }
        }
    }

    suspend fun refreshWallet() {
        val b = backend ?: return
        try { b.wallet().let { w -> update { it.copy(wallet = w) } } } catch (e: CancellationException) { throw e } catch (e: Exception) { /* keep the last balance */ }
    }

    /** Seam for notifications (needs backend registration and the owner's decision, so nothing subscribes today): told once when a video that was being made finishes or fails. */
    @Volatile var makingEvents: com.videomk.app.core.MakingEvents? = null

    private fun announceFinished(s: AppState, fresh: List<VideoItem>) {
        val listener = makingEvents ?: return
        val before = s.videos.associate { it.id to it.status }
        for (v in fresh) {
            if (before[v.id]?.isRunning != true || v.status.isRunning) continue
            listener.onFinished(v.id, s.briefs[v.id] ?: v.displayTitle, v.status == VideoStatus.Complete)
        }
    }

    /** Remembers when each running video entered its current stage (for the progress estimate) and notices completions. */
    private fun track(s: AppState, fresh: List<VideoItem>): Pair<Map<String, StageInfo>, Int> {
        val before = s.videos.associate { it.id to it.status }
        val stages = s.stageSince.toMutableMap()
        var completions = 0
        val now = clock()
        for (v in fresh) {
            val st = v.status
            if (st is VideoStatus.Running) {
                if (stages[v.id]?.stage != st.stage || stages[v.id]?.deck != st.deck) stages[v.id] = StageInfo(st.stage, now, st.deck)
            } else {
                stages.remove(v.id)
                if (before[v.id]?.isRunning == true && st == VideoStatus.Complete) completions++
            }
        }
        return stages to completions
    }

    private var backgroundWatch: Job? = null
    /** Off screen with "Tell me when it's ready" on: keep checking, slowly, until everything has settled or half an hour has passed (then Android may well have stopped the app anyway). */
    fun onBackground(watch: Boolean) {
        backgroundWatch?.cancel()
        if (!watch || !_state.value.hasRunningVideos) return
        backgroundWatch = viewModelScope.launch {
            val until = clock() + BACKGROUND_WATCH_MILLIS
            while (isActive && _state.value.hasRunningVideos && clock() < until) { delay(BACKGROUND_POLL_MILLIS); refresh() }
        }
    }
    fun onForeground() { backgroundWatch?.cancel(); backgroundWatch = null }

    /** Polls while anything is running; ends when the caller's coroutine is cancelled or everything has settled. */
    suspend fun pollWhileRunning() {
        while (currentIsActive() && _state.value.hasRunningVideos) {
            delay(POLL_MILLIS)
            if (!currentIsActive()) break
            refresh()
        }
    }

    private suspend fun currentIsActive() = kotlin.coroutines.coroutineContext.isActive

    // ask for a video without leaving the home screen

    /** Adds a placeholder row immediately and sends the request in the background; the user can keep browsing or ask for more. */
    private fun register(brief: String, options: CreateOptions, photos: List<ByteArray>, meta: List<PhotoMeta?>, libraryMedia: List<String>, intake: kotlinx.serialization.json.JsonObject?, deck: String? = null, title: String? = null): PendingVideo {
        val p = PendingVideo(
            brief = Brief.normalized(brief), options = options, photoCount = photos.size, createdAtMillis = clock(), title = title,
            state = if (photos.isEmpty()) PendingVideo.State.Sending else PendingVideo.State.Uploading(0, photos.size),
        )
        if (photos.isNotEmpty()) { photoData[p.id] = photos; photoMeta[p.id] = meta }
        if (libraryMedia.isNotEmpty()) libraryData[p.id] = libraryMedia
        if (intake != null) briefData[p.id] = intake
        if (deck != null) deckData[p.id] = deck
        update { it.copy(pending = listOf(p) + it.pending) }
        return p
    }

    fun submit(brief: String, options: CreateOptions, photos: List<ByteArray> = emptyList(), meta: List<PhotoMeta?> = emptyList(), libraryMedia: List<String> = emptyList(), intake: kotlinx.serialization.json.JsonObject? = null) {
        val p = register(brief, options, photos, meta, libraryMedia, intake)
        viewModelScope.launch { send(p.id) }
    }

    /**
     * The Create screen's send: waits for generate's answer. Blocked, paused and network errors leave no card behind
     * (the caller keeps the draft and shows the sheet or a message); anything else ends on the Making card as before.
     */
    suspend fun submitAwait(brief: String, options: CreateOptions, photos: List<ByteArray> = emptyList(), meta: List<PhotoMeta?> = emptyList(), libraryMedia: List<String> = emptyList(), intake: kotlinx.serialization.json.JsonObject? = null, deck: String? = null, deckTitle: String? = null): SubmitOutcome {
        val p = register(brief, options, photos, meta, libraryMedia, intake, deck, deckTitle)
        return send(p.id, interactive = true)
    }

    fun retry(id: String) {
        val p = _state.value.pending.firstOrNull { it.id == id } ?: return
        setPendingState(id, if (p.photoCount > 0) PendingVideo.State.Uploading(0, p.photoCount) else PendingVideo.State.Sending)
        viewModelScope.launch { send(id) }
    }

    /**
     * "Try again" on a video the server could not finish: the SAME video starts again on the server with everything it was made with (every photo, option, language,
     * watermark): no new row, nothing resent from the phone. An older server without the route: only a video known to have had no attachments is asked for again the old
     * way; any other is never rebuilt without its photos (that is how a 60-photo video once came back with none): the person is told instead.
     */
    fun tryAgain(video: VideoItem) {
        val b = backend ?: return
        if (video.id in _state.value.retrying) return
        update { it.copy(retrying = it.retrying + video.id) }
        viewModelScope.launch {
            try {
                when (val r = b.retryVideo(video.id)) {
                    is RetryResult.Started, RetryResult.AlreadyRunning -> {
                        update { s -> s.copy(videos = s.videos.map { if (it.id == video.id) it.copy(status = VideoStatus.Running(VideoStatus.Stage.Starting), canRetry = null) else it }) }   // the row turns into the making card at once
                        refresh()
                        if (r is RetryResult.Started && r.unusable > 0) update { it.copy(retryNotice = Txt.n(R.plurals.retry_photos_unusable, r.unusable, r.unusable)) }
                    }
                    RetryResult.Unsupported -> {
                        val brief = _state.value.briefs[video.id]
                        if (attachments[video.id] == 0 && brief != null && video.id !in _state.value.deckVideos) submit(brief, CreateOptions(_state.value.minutes[video.id] ?: CreateOptions.DEFAULT_MINUTES))
                        else update { it.copy(retryNotice = Txt.s(R.string.retry_unavailable)) }
                    }
                    is RetryResult.Refused -> { update { it.copy(retryNotice = r.message) }; refresh() }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError.Unauthorized) {
                signOut()
            } catch (e: ApiError) {
                if (e is ApiError.InsufficientCredits) refreshWallet()
                update { it.copy(retryNotice = e.message) }
            } catch (e: Exception) {
                update { it.copy(retryNotice = ApiError.Server.message) }
            } finally {
                update { it.copy(retrying = it.retrying - video.id) }
            }
        }
    }

    /** Removes a video that did not finish from the list (and from the server). */
    fun removeFailed(video: VideoItem) {
        val b = backend ?: return
        viewModelScope.launch {
            try {
                if (b.deleteVideo(video.id)) update { s -> s.copy(videos = s.videos.filterNot { it.id == video.id }) }
                else update { it.copy(retryNotice = Txt.s(R.string.retry_remove_unavailable)) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError.Unauthorized) {
                signOut()
            } catch (e: ApiError) {
                update { it.copy(retryNotice = e.message) }
                refresh()
            } catch (e: Exception) {
                update { it.copy(retryNotice = ApiError.Server.message) }
            }
        }
    }

    fun dismissRetryNotice() = update { it.copy(retryNotice = null) }

    fun dismissPending(id: String) {
        photoData.remove(id); photoMeta.remove(id); libraryData.remove(id); briefData.remove(id); deckData.remove(id)
        update { s -> s.copy(pending = s.pending.filterNot { it.id == id }) }
    }

    private fun setPendingState(id: String, state: PendingVideo.State) =
        update { s -> s.copy(pending = s.pending.map { if (it.id == id) it.copy(state = state) else it }) }

    private fun setProgress(id: String, done: Int, total: Int) =
        update { s -> s.copy(pending = s.pending.map { if (it.id == id && it.state is PendingVideo.State.Uploading) it.copy(state = PendingVideo.State.Uploading(done, total)) else it }) }

    private suspend fun send(id: String, interactive: Boolean = false): SubmitOutcome {
        val p = _state.value.pending.firstOrNull { it.id == id } ?: return SubmitOutcome.Accepted
        val b = backend ?: run { setPendingState(id, PendingVideo.State.Failed(ApiError.Server.message)); return SubmitOutcome.Accepted }
        try {
            var media = emptyList<String>()
            photoData[id]?.let { photos ->
                media = b.uploadPhotos(photos) { done, total -> setProgress(id, done, total) }
                if (_state.value.pending.any { it.id == id }) setPendingState(id, PendingVideo.State.Sending)
            }
            val videoId = b.startGeneration(p.brief, p.id, p.options, media, PhotoMeta.requestJson(media, photoMeta[id].orEmpty()), libraryData[id].orEmpty(), briefData[id], deckData[id])
            val wasDeck = deckData[id] != null
            attachments[videoId] = media.size + libraryData[id].orEmpty().size + (if (wasDeck) 1 else 0)
            photoData.remove(id); photoMeta.remove(id); libraryData.remove(id); briefData.remove(id); deckData.remove(id)
            update { s ->
                s.copy(
                    briefs = s.briefs + (videoId to p.shownTitle), minutes = s.minutes + (videoId to p.options.minutes),
                    deckVideos = if (wasDeck) s.deckVideos + videoId else s.deckVideos,
                    pending = s.pending.map { if (it.id == id) it.copy(state = PendingVideo.State.Accepted(videoId)) else it },
                )
            }
            refresh()   // also re-reads the credits the video just used
            return SubmitOutcome.Accepted
        } catch (e: CancellationException) {
            throw e
        } catch (e: ApiError) {
            if (interactive && (e is ApiError.Blocked || e is ApiError.Paused)) { dismissPending(id); return SubmitOutcome.Stopped(e) }
            if (interactive && e is ApiError.Network) { dismissPending(id); return SubmitOutcome.Offline(e.message) }
            if (e is ApiError.InsufficientCredits) refreshWallet()
            if (e !is ApiError.Unauthorized) setPendingState(id, PendingVideo.State.Failed(e.message))
        } catch (e: Exception) {
            setPendingState(id, PendingVideo.State.Failed(ApiError.Server.message))
        }
        return SubmitOutcome.Accepted
    }

    // play / edit

    suspend fun playback(id: String) = (backend ?: throw ApiError.Server).playback(id)

    fun noteEdited() { _editRevision.update { it + 1 } }

    companion object {
        const val POLL_MILLIS = 4000L
        const val BACKGROUND_POLL_MILLIS = 15_000L
        const val BACKGROUND_WATCH_MILLIS = 30 * 60_000L
        val SIGN_IN_FAILED: String get() = Txt.s(R.string.auth_sign_in_failed)
        val ACCOUNT_LINK_FAILED: String get() = Txt.s(R.string.auth_account_link_failed)
    }
}
