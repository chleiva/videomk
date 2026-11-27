package com.videomk.app.ui

import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.clickable

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
    Box(frame.clip(if (edgeToEdge) androidx.compose.ui.graphics.RectangleShape else RoundedCornerShape(Vmk.radii.videoCard)).background(Color.Black).testTag("player")) {
        AndroidView(
            factory = { ctx ->
                PlayerView(ctx).apply {
                    useController = false   // our own controls below: one vocabulary (play or pause, the time bar, full screen)
                    resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
                    setShowBuffering(PlayerView.SHOW_BUFFERING_NEVER)
                    this.player = player
                }
            },
            update = { if (it.player !== player) it.player = player },
            onRelease = { it.player = null },
            modifier = Modifier.matchParentSize(),
        )
        if (player != null && !ended) PlayerControls(player, onFullScreen, Modifier.matchParentSize())
        // the end card: Replay (a quiet glass icon) and New video (a labelled white pill with the play-sparkle glyph)
        if (ended && player != null) Box(Modifier.matchParentSize().background(Color.Black.copy(alpha = 0.55f)).testTag("endCard"), contentAlignment = Alignment.Center) {
            Row(horizontalArrangement = Arrangement.spacedBy(Vmk.space.l), verticalAlignment = Alignment.CenterVertically) {
                GlassIconButton(Sym.Replay, stringResource(R.string.video_replay), { player.seekTo(0); player.play() }, Modifier.testTag("replayButton"), onDark = true, size = 56.dp)
                if (onNew != null) Row(
                    Modifier.heightIn(min = 52.dp).clip(androidx.compose.foundation.shape.CircleShape).background(Color.White).clickable(role = androidx.compose.ui.semantics.Role.Button, onClick = onNew).padding(horizontal = Vmk.space.xl, vertical = Vmk.space.m).testTag("endNewVideo"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s),
                ) {
                    Icon(Sym.PlaySparkle, null, tint = Color(0xFF000000L or com.videomk.app.core.DesignTokens.primary.light.toLong()), modifier = Modifier.size(22.dp))
                    Text(stringResource(R.string.lib_new_video), style = VmkType.cta, color = Color(0xFF000000L or com.videomk.app.core.DesignTokens.text.light.toLong()))
                }
            }
        }
    }
    }
}


/** "1:05" for a position in milliseconds. */
private fun clock(ms: Long): String { val t = (maxOf(0L, ms) / 1000).toInt(); return "%d:%02d".format(t / 60, t % 60) }

/**
 * The ONE set of player controls, for the inline player and for full screen: play or pause in the middle, and along the bottom the time, the bar to scrub and
 * (inline) the full-screen button. No skip buttons and no settings gear. A tap on the picture shows or hides them; they leave by themselves after three seconds
 * of playing and stay while paused. Everything is a 48 dp target with a spoken label; the bar is a slider TalkBack can move.
 */
@Composable
fun PlayerControls(player: Player, onFullScreen: (() -> Unit)?, modifier: Modifier = Modifier, bottomInset: androidx.compose.ui.unit.Dp = 0.dp) {
    var visible by remember { mutableStateOf(true) }
    var playing by remember { mutableStateOf(player.isPlaying) }
    var buffering by remember { mutableStateOf(false) }
    var position by remember { androidx.compose.runtime.mutableLongStateOf(0L) }
    var duration by remember { androidx.compose.runtime.mutableLongStateOf(0L) }
    var scrub by remember { mutableStateOf<Float?>(null) }
    var touched by remember { androidx.compose.runtime.mutableIntStateOf(0) }
    androidx.compose.runtime.LaunchedEffect(player) {
        while (true) {
            playing = player.playWhenReady && player.playbackState != Player.STATE_ENDED; buffering = player.playbackState == Player.STATE_BUFFERING
            position = player.currentPosition; duration = player.duration.takeIf { it > 0 } ?: 0L
            kotlinx.coroutines.delay(250)
        }
    }
    androidx.compose.runtime.LaunchedEffect(visible, playing, touched, scrub != null) { if (visible && playing && scrub == null) { kotlinx.coroutines.delay(3000); visible = false } }
    val showHide = stringResource(R.string.player_controls)
    Box(modifier.clickable(interactionSource = remember { androidx.compose.foundation.interaction.MutableInteractionSource() }, indication = null, onClickLabel = showHide) { visible = !visible; touched++ }) {
        if (buffering && !visible) LiveRing(Modifier.align(Alignment.Center), size = 36.dp, track = Color.White.copy(alpha = 0.3f), color = Color.White)
        androidx.compose.animation.AnimatedVisibility(visible, Modifier.matchParentSize(), enter = androidx.compose.animation.fadeIn(), exit = androidx.compose.animation.fadeOut()) {
            Box(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Brush.verticalGradient(0f to Color.Transparent, 0.55f to Color.Transparent, 1f to Color.Black.copy(alpha = 0.6f)))) {
                if (buffering) LiveRing(Modifier.align(Alignment.Center), size = 36.dp, track = Color.White.copy(alpha = 0.3f), color = Color.White)
                else GlassIconButton(if (playing) Sym.Pause else Sym.PlayArrow, stringResource(if (playing) R.string.player_pause else R.string.player_play), { if (playing) player.pause() else player.play(); touched++ }, Modifier.align(Alignment.Center).testTag("playPause"), onDark = true, size = 64.dp)
                Row(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(start = Vmk.space.l, end = Vmk.space.xs, bottom = bottomInset), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                    val shown = scrub?.let { (it * duration).toLong() } ?: position
                    Text(clock(shown) + " / " + clock(duration), style = MaterialTheme.typography.labelMedium, color = Color.White, maxLines = 1, modifier = Modifier.testTag("playerTime"))
                    val seekLabel = stringResource(R.string.player_seek)
                    androidx.compose.material3.Slider(
                        value = scrub ?: if (duration > 0) (position.toFloat() / duration).coerceIn(0f, 1f) else 0f,
                        onValueChange = { scrub = it; touched++ }, onValueChangeFinished = { scrub?.let { player.seekTo((it * duration).toLong()) }; scrub = null },
                        enabled = duration > 0, modifier = Modifier.weight(1f).heightIn(min = Vmk.minTouch).semantics { contentDescription = seekLabel }.testTag("playerSeek"),
                        colors = androidx.compose.material3.SliderDefaults.colors(thumbColor = Color.White, activeTrackColor = Color.White, inactiveTrackColor = Color.White.copy(alpha = 0.35f)),
                    )
                    if (onFullScreen != null) GlassIconButton(Sym.Fullscreen, stringResource(R.string.player_full_screen), onFullScreen, Modifier.testTag("fullScreenButton"), onDark = true)
                    else Spacer(Modifier.width(Vmk.space.s))
                }
            }
        }
    }
}
