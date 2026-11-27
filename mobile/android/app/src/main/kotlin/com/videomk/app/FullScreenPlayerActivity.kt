package com.videomk.app

import androidx.compose.ui.res.stringResource
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.displayCutoutPadding
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import com.videomk.app.ui.Sym

/**
 * Full screen video: always landscape (declared in the manifest), system bars hidden, a close button, and playback continues from the
 * moment the inline player was at. On close it hands the position back to the page it came from.
 */
@androidx.annotation.OptIn(UnstableApi::class)
class FullScreenPlayerActivity : ComponentActivity() {
    private var player: ExoPlayer? = null
    private var closing = false
    // the rating prompt counts a full screen watch too (WatchTracker has the rule); the result goes back to the video page
    private var tracker: com.videomk.app.core.WatchTracker? = null
    private val ticker = android.os.Handler(android.os.Looper.getMainLooper())
    private val tick = object : Runnable {
        override fun run() { player?.let { tracker?.sample(it.currentPosition, it.isPlaying) }; ticker.postDelayed(this, 500) }
    }

    override fun attachBaseContext(newBase: android.content.Context) { super.attachBaseContext(com.videomk.app.data.AppLanguage(newBase).wrap(newBase)) }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        val url = intent.getStringExtra(EXTRA_URL)
        if (url == null) { finish(); return }
        if (intent.getBooleanExtra(EXTRA_VERTICAL, false)) requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT   // a vertical video fills a portrait screen
        val start = savedInstanceState?.getLong(EXTRA_POSITION) ?: intent.getLongExtra(EXTRA_POSITION, 0)

        val p = ExoPlayer.Builder(this)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MOVIE).build(), true)
            .setHandleAudioBecomingNoisy(true)
            .build()
        p.setMediaItem(MediaItem.fromUri(url), start)
        p.playWhenReady = true   // full screen is opened to watch: always starts playing (iOS does the same)
        p.addListener(object : androidx.media3.common.Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == androidx.media3.common.Player.STATE_READY && tracker == null && p.duration > 0) tracker = com.videomk.app.core.WatchTracker(p.duration).also { it.seek(p.currentPosition) }
                if (state == androidx.media3.common.Player.STATE_ENDED) tracker?.ended()
            }
            override fun onPositionDiscontinuity(o: androidx.media3.common.Player.PositionInfo, n: androidx.media3.common.Player.PositionInfo, reason: Int) {
                if (reason == androidx.media3.common.Player.DISCONTINUITY_REASON_SEEK || reason == androidx.media3.common.Player.DISCONTINUITY_REASON_SEEK_ADJUSTMENT) tracker?.seek(n.positionMs)
            }
        })
        p.prepare()
        player = p
        ticker.post(tick)

        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, window.decorView).apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            hide(WindowInsetsCompat.Type.systemBars())
        }
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) { override fun handleOnBackPressed() = close() })

        setContent {
            Box(Modifier.fillMaxSize().background(Color.Black).semantics { if (BuildConfig.DEBUG) testTagsAsResourceId = true }) {
                AndroidView(
                    factory = { ctx ->
                        PlayerView(ctx).apply {
                            useController = true
                            resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                            this.player = p
                        }
                    },
                    onRelease = { it.player = null },
                    modifier = Modifier.fillMaxSize(),
                )
                IconButton(
                    onClick = ::close,
                    modifier = Modifier.align(Alignment.TopStart).displayCutoutPadding().padding(12.dp).size(48.dp).testTag("closeFullScreenButton"),
                ) {
                    Box(Modifier.size(40.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.55f)), contentAlignment = Alignment.Center) {
                        Icon(Sym.Close, contentDescription = stringResource(R.string.player_close_full_screen), tint = Color.White)
                    }
                }
            }
        }
    }

    private fun close() {
        if (closing) return
        closing = true
        val p = player
        val data = Intent()
            .putExtra(EXTRA_URL, intent.getStringExtra(EXTRA_URL))
            .putExtra(EXTRA_POSITION, p?.currentPosition ?: 0L)
            .putExtra(EXTRA_PLAYING, p?.playWhenReady ?: false)
            .putExtra(EXTRA_COMPLETED, tracker?.completed == true)
        setResult(RESULT_OK, data)
        finish()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putLong(EXTRA_POSITION, player?.currentPosition ?: 0)
        outState.putBoolean(EXTRA_PLAYING, player?.playWhenReady ?: false)
    }

    override fun onStop() {
        super.onStop()
        player?.pause()   // leaving the app: stop the narration
    }

    override fun onDestroy() {
        ticker.removeCallbacks(tick)
        player?.release()
        player = null
        super.onDestroy()
    }

    companion object {
        const val EXTRA_URL = "url"
        const val EXTRA_POSITION = "position"
        const val EXTRA_PLAYING = "playing"
        const val EXTRA_VERTICAL = "vertical"
        const val EXTRA_COMPLETED = "completed"
    }
}
