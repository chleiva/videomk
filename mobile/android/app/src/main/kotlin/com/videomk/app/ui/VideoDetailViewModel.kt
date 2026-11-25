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
import com.videomk.app.core.ApiError
import com.videomk.app.core.Backend
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed interface PlaybackState {
    data object Idle : PlaybackState
    data object Loading : PlaybackState
    data class Ready(val url: String, val description: String?) : PlaybackState
    data class Error(val message: String) : PlaybackState
}

data class FullScreenArgs(val url: String, val positionMs: Long, val playWhenReady: Boolean, val vertical: Boolean = false)

/**
 * One video's player. Lives with the video page (not the composition), so a rotation keeps the picture and the position, and releases the
 * player when the page is left. Narration plays whatever the ringer mode is: the player uses the media audio stream (USAGE_MEDIA), which the
 * ringer/silent switch does not mute, and it takes audio focus so other audio gives way.
 */
class VideoDetailViewModel(app: Application, private val backend: Backend?, val videoId: String) : AndroidViewModel(app) {
    private val _playback = MutableStateFlow<PlaybackState>(PlaybackState.Idle)
    val playback: StateFlow<PlaybackState> = _playback.asStateFlow()
    var player: ExoPlayer? = null
        private set
    private var loadJob: Job? = null

    fun load() {
        if (_playback.value is PlaybackState.Ready || loadJob?.isActive == true) return
        _playback.value = PlaybackState.Loading
        loadJob = viewModelScope.launch {
            try {
                val info = (backend ?: throw ApiError.Server).playback(videoId)
                _playback.value = PlaybackState.Ready(info.url, info.description)
                createPlayer(info.url)
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

    private fun createPlayer(url: String) {
        releasePlayer()
        val p = ExoPlayer.Builder(getApplication())
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), true)
            .setHandleAudioBecomingNoisy(true)
            .build()
        p.addListener(object : Player.Listener {
            override fun onPlayerError(error: PlaybackException) {
                // most often an expired link: show "try again", which fetches a new one
                _playback.value = PlaybackState.Error("This video couldn't be played. Check your connection and try again.")
                releasePlayer()
            }
        })
        p.setMediaItem(MediaItem.fromUri(url))
        p.prepare()
        player = p
    }

    private fun releasePlayer() {
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

    fun returnFromFullScreen(positionMs: Long, playing: Boolean) {
        val p = player ?: return
        p.seekTo(positionMs)
        p.playWhenReady = playing
    }

    override fun onCleared() { releasePlayer() }
}
