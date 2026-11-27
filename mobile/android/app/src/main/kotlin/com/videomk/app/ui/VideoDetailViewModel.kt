package com.videomk.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.videomk.app.R
import com.videomk.app.core.ApiError
import com.videomk.app.core.Txt
import com.videomk.app.core.Backend
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import com.videomk.app.core.WatchTracker

/** Signed video links stop working after a while (an hour today): one that old is replaced when the page is looked at again. elapsedRealtime, so time asleep counts. */
object PlaybackLink {
    const val MAX_AGE_MILLIS = 45 * 60_000L
    fun isStale(loadedAtMillis: Long, nowMillis: Long): Boolean = loadedAtMillis > 0 && nowMillis - loadedAtMillis >= MAX_AGE_MILLIS
}

sealed interface PlaybackState {
    data object Idle : PlaybackState
    data object Loading : PlaybackState
    data class Ready(val url: String, val description: String?) : PlaybackState
    data class Error(val message: String) : PlaybackState
}

/** [completed]: the full screen player saw the video played to its end (see WatchTracker); only set on the way back. */
data class FullScreenArgs(val url: String, val positionMs: Long, val playWhenReady: Boolean, val vertical: Boolean = false, val completed: Boolean = false)

/**
 * One video's player. Lives with the video page (not the composition), so a rotation keeps the picture and the position, and releases the
 * player when the page is left. Narration plays whatever the ringer mode is: the player uses the media audio stream (USAGE_MEDIA), which the
 * ringer/silent switch does not mute, and it takes audio focus so other audio gives way.
 */
class VideoDetailViewModel(app: Application, private val backend: Backend?, val videoId: String, private val onFullyWatched: (String) -> Unit = {}) : AndroidViewModel(app) {
    private val _playback = MutableStateFlow<PlaybackState>(PlaybackState.Idle)
    val playback: StateFlow<PlaybackState> = _playback.asStateFlow()
    var player: ExoPlayer? = null
        private set
    private var loadJob: Job? = null
    // the rating prompt counts a video only when it was played from start to end (WatchTracker has the rule)
    private var tracker: WatchTracker? = null
    private var tickJob: Job? = null
    private var reported = false
    private var autoRetried = false

    private fun checkWatched() {
        if (!reported && tracker?.completed == true) { reported = true; onFullyWatched(videoId) }
    }

    fun load() {
        if (_playback.value is PlaybackState.Ready || loadJob?.isActive == true) return
        _playback.value = PlaybackState.Loading
        loadJob = viewModelScope.launch {
            try {
                val info = (backend ?: throw ApiError.Server).playback(videoId)
                // the player exists before the page is told it is ready: the page reads `player` when it draws the ready state (the other order drew a player with no controls)
                createPlayer(info.url)
                _playback.value = PlaybackState.Ready(info.url, info.description)
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiError) {
                _playback.value = PlaybackState.Error(e.message)
            } catch (e: Exception) {
                _playback.value = PlaybackState.Error(ApiError.Server.message)
            }
        }
    }

    /** The video was replaced (an edit was published) or the link expired: forget the player and fetch a fresh link. */
    fun reload() {
        loadJob?.cancel()
        releasePlayer()
        _playback.value = PlaybackState.Idle
        load()
    }

    private var loadedAtMillis = 0L

    /**
     * The page is visible again. A playback error is retried with a fresh link, and so is a link old enough to have expired (the phone slept on this page):
     * the position is kept. A video that is playing or was loaded moments ago is left alone.
     */
    fun onVisible(nowMillis: Long = android.os.SystemClock.elapsedRealtime()) {
        when (_playback.value) {
            is PlaybackState.Error -> reload()
            is PlaybackState.Ready -> if (PlaybackLink.isStale(loadedAtMillis, nowMillis) && player?.isPlaying != true) {
                val at = player?.currentPosition ?: 0L
                resumeAtMs = at
                reload()
            }
            else -> Unit
        }
    }
    private var resumeAtMs = 0L

    private fun createPlayer(url: String) {
        releasePlayer()
        val p = ExoPlayer.Builder(getApplication())
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), true)
            .setHandleAudioBecomingNoisy(true)
            .build()
        p.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY && tracker == null && p.duration > 0) tracker = WatchTracker(p.duration).also { it.seek(p.currentPosition) }
                if (state == Player.STATE_ENDED) { tracker?.ended(); checkWatched() }
            }
            override fun onPositionDiscontinuity(oldPosition: Player.PositionInfo, newPosition: Player.PositionInfo, reason: Int) {
                if (reason == Player.DISCONTINUITY_REASON_SEEK || reason == Player.DISCONTINUITY_REASON_SEEK_ADJUSTMENT) tracker?.seek(newPosition.positionMs)
            }
            override fun onPlayerError(error: PlaybackException) {
                // most often an expired link: fetch a new one once by itself, at the same place; only a second failure shows "try again"
                val at = p.currentPosition
                if (!autoRetried) { autoRetried = true; resumeAtMs = at; reload(); return }
                _playback.value = PlaybackState.Error(Txt.s(R.string.video_play_failed))
                releasePlayer()
            }
            override fun onIsPlayingChanged(isPlaying: Boolean) { if (isPlaying) autoRetried = false }
        })
        p.setMediaItem(MediaItem.fromUri(url))
        if (resumeAtMs > 0) { p.seekTo(resumeAtMs); resumeAtMs = 0 }
        p.prepare()
        loadedAtMillis = android.os.SystemClock.elapsedRealtime()
        player = p
        tracker = null; reported = false
        tickJob = viewModelScope.launch { while (true) { delay(500); tracker?.sample(p.currentPosition, p.isPlaying); checkWatched() } }
    }

    private fun releasePlayer() {
        tickJob?.cancel(); tickJob = null
        player?.release()
        player = null
    }

    fun pause() { player?.pause() }

    fun enterFullScreen(vertical: Boolean = false): FullScreenArgs? {
        val p = player ?: return null
        val args = FullScreenArgs((playback.value as? PlaybackState.Ready)?.url ?: return null, p.currentPosition, p.playWhenReady, vertical)
        p.pause()
        return args
    }

    fun returnFromFullScreen(positionMs: Long, playing: Boolean, completed: Boolean = false) {
        if (completed && !reported) { reported = true; onFullyWatched(videoId) }
        val p = player ?: return
        p.seekTo(positionMs)
        p.playWhenReady = playing
    }

    override fun onCleared() { releasePlayer() }
}
