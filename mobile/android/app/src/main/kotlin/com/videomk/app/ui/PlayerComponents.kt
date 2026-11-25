package com.videomk.app.ui

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
        return FullScreenArgs(url, intent.getLongExtra(FullScreenPlayerActivity.EXTRA_POSITION, 0), intent.getBooleanExtra(FullScreenPlayerActivity.EXTRA_PLAYING, false))
    }
}

const val MAX_TALL_DP = 460

/** An inline player (16:9 unless the video says otherwise) with a full screen button. */
@androidx.annotation.OptIn(UnstableApi::class)
@Composable
fun InlinePlayer(player: Player?, onFullScreen: () -> Unit, modifier: Modifier = Modifier, ratio: Float = 16f / 9f) {
    // a tall video (9:16, 4:5) is shown at its own shape, at most MAX_TALL dp high and centred; nothing is stretched
    androidx.compose.foundation.layout.BoxWithConstraints(modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
    val frame = if (ratio >= 1f) Modifier.fillMaxWidth().aspectRatio(ratio)
        else Modifier.height(minOf(maxWidth / ratio, MAX_TALL_DP.dp)).aspectRatio(ratio)
    Box(frame.clip(RoundedCornerShape(Vmk.radius)).background(Color.Black).testTag("player")) {
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    useController = true
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                    setShowBuffering(PlayerView.SHOW_BUFFERING_WHEN_PLAYING)
                    this.player = player
                }
            },
            update = { if (it.player !== player) it.player = player },
            onRelease = { it.player = null },
            modifier = Modifier.matchParentSize(),
        )
        if (player != null) {
            IconButton(
                onClick = onFullScreen,
                modifier = Modifier.align(Alignment.TopEnd).padding(6.dp).size(48.dp).testTag("fullScreenButton"),
            ) {
                Box(Modifier.size(40.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.55f)), contentAlignment = Alignment.Center) {
                    Icon(Icons.Filled.Fullscreen, contentDescription = "Full screen", tint = Color.White)
                }
            }
        }
    }
    }
}
