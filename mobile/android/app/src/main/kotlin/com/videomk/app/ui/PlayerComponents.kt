package com.videomk.app.ui

import androidx.compose.material.icons.filled.Replay
import androidx.compose.material.icons.filled.Add
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import android.content.Context
import android.content.Intent
import androidx.activity.result.contract.ActivityResultContract
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Fullscreen
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView
import com.videomk.app.FullScreenPlayerActivity

/** Opens [FullScreenPlayerActivity] (landscape, closes with a button) and brings back where playback was. */
class FullScreenContract : ActivityResultContract<FullScreenArgs, FullScreenArgs?>() {
    override fun createIntent(context: Context, input: FullScreenArgs): Intent = Intent(context, FullScreenPlayerActivity::class.java)
        .putExtra(FullScreenPlayerActivity.EXTRA_URL, input.url)
        .putExtra(FullScreenPlayerActivity.EXTRA_POSITION, input.positionMs)
        .putExtra(FullScreenPlayerActivity.EXTRA_PLAYING, input.playWhenReady)
        .putExtra(FullScreenPlayerActivity.EXTRA_VERTICAL, input.vertical)

    override fun parseResult(resultCode: Int, intent: Intent?): FullScreenArgs? {
        val url = intent?.getStringExtra(FullScreenPlayerActivity.EXTRA_URL) ?: return null
        return FullScreenArgs(url, intent.getLongExtra(FullScreenPlayerActivity.EXTRA_POSITION, 0), intent.getBooleanExtra(FullScreenPlayerActivity.EXTRA_PLAYING, false), completed = intent.getBooleanExtra(FullScreenPlayerActivity.EXTRA_COMPLETED, false))
    }
}

const val MAX_TALL_DP = 460

/**
 * An inline player (16:9 unless the video says otherwise). The system controls stay (scrubber, play/pause, captions) and hide after 3 s; our one extra control, a full screen icon in
 * the same glass style, shows and hides with them. When the video ends an end card offers two icon buttons: replay and New video (docs/UX_2026_REDESIGN.md 4.1).
 */
@androidx.annotation.OptIn(UnstableApi::class)
@Composable
fun InlinePlayer(player: Player?, onFullScreen: () -> Unit, modifier: Modifier = Modifier, ratio: Float = 16f / 9f, edgeToEdge: Boolean = false, onNew: (() -> Unit)? = null) {
    var controlsVisible by remember { mutableStateOf(true) }
    var ended by remember { mutableStateOf(false) }
    androidx.compose.runtime.DisposableEffect(player) {
        val l = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) { if (state == Player.STATE_ENDED) ended = true else if (state == Player.STATE_READY && player?.isPlaying == true) ended = false }
            override fun onIsPlayingChanged(isPlaying: Boolean) { if (isPlaying) ended = false }
        }
        ended = player?.playbackState == Player.STATE_ENDED
        player?.addListener(l)
        onDispose { player?.removeListener(l) }
    }
    // a tall video (9:16, 4:5) is shown at its own shape, at most MAX_TALL dp high and centred; nothing is stretched
    androidx.compose.foundation.layout.BoxWithConstraints(modifier.fillMaxWidth().then(if (edgeToEdge) Modifier.background(Color.Black) else Modifier), contentAlignment = Alignment.Center) {
    val frame = if (ratio >= 1f) Modifier.fillMaxWidth().aspectRatio(ratio)
        else Modifier.height(minOf(maxWidth / ratio, MAX_TALL_DP.dp)).aspectRatio(ratio)
    Box(frame.clip(if (edgeToEdge) androidx.compose.ui.graphics.RectangleShape else RoundedCornerShape(Vmk.radius)).background(Color.Black).testTag("player")) {
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    useController = true
                    controllerShowTimeoutMs = 3000
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                    setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING)
                    setControllerVisibilityListener(PlayerView.ControllerVisibilityListener { v -> controlsVisible = v == android.view.View.VISIBLE })
                    this.player = player
                }
            },
            update = { if (it.player !== player) it.player = player },
            onRelease = { it.player = null },
            modifier = Modifier.matchParentSize(),
        )
        if (player != null) androidx.compose.animation.AnimatedVisibility(controlsVisible && !ended, Modifier.align(Alignment.TopEnd), enter = androidx.compose.animation.fadeIn(), exit = androidx.compose.animation.fadeOut()) {
            GlassIconButton(Icons.Filled.Fullscreen, stringResource(R.string.player_full_screen), onFullScreen, Modifier.padding(6.dp).testTag("fullScreenButton"), onDark = true)
        }
        if (ended && player != null) Box(Modifier.matchParentSize().background(Color.Black.copy(alpha = 0.62f)).testTag("endCard"), contentAlignment = Alignment.Center) {
            Row(horizontalArrangement = Arrangement.spacedBy(28.dp), verticalAlignment = Alignment.CenterVertically) {
                GlassIconButton(Icons.Filled.Replay, stringResource(R.string.video_replay), { player.seekTo(0); player.play() }, Modifier.testTag("replayButton"), onDark = true, size = 56.dp)
                if (onNew != null) Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    GlassIconButton(Icons.Filled.Add, stringResource(R.string.lib_new_video), onNew, Modifier.testTag("endNewVideo"), filled = true, size = 56.dp)
                    Text(stringResource(R.string.lib_new_video), style = MaterialTheme.typography.labelMedium, color = Color.White, modifier = Modifier.padding(top = 2.dp))
                }
            }
        }
    }
    }
}
