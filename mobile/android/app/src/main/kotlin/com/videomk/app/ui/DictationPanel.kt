package com.videomk.app.ui

import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.DictationFeedback
import com.videomk.app.core.VoiceFeedback
import com.videomk.app.core.VoicePhase

/**
 * The voice panel (docs/DICTATION_FEEDBACK_2026-11-28.md): replaces the pills and tool row while the mic works, so it can never be mistaken for idle.
 * Recording: red dot, bars from the REAL input level (`MediaRecorder.maxAmplitude`), m:ss, a 52 dp Stop and Cancel. Transcribing: the same bars settle to a slow sweep in
 * the primary colour and a ring replaces Stop. Failed: Retry or the phone's own dictation. Material 3: 48 dp targets, tonal container, emphasized-decelerate easing,
 * reduced motion gives a still ramp, TalkBack gets one group and announcements at thresholds only (the visible seconds are not a live region).
 */
@Composable
fun DictationPanel(
    voice: VoiceFeedback, bars: State<List<Double>>, clip: Boolean,
    onStop: () -> Unit, onCancel: () -> Unit, onRetry: () -> Unit, onDevice: () -> Unit, modifier: Modifier = Modifier,
) {
    val failed = voice.phase == VoicePhase.Failed
    val shape = RoundedCornerShape(if (failed) 28.dp else 36.dp)
    Box(
        modifier.fillMaxWidth().heightIn(min = 72.dp).clip(shape).background(Vmk.colors.surfaceRaised).border(1.dp, Vmk.colors.outline, shape)
            .padding(horizontal = Vmk.space.m, vertical = Vmk.space.s).testTag("dictationPanel"),
        contentAlignment = Alignment.CenterStart,
    ) {
        if (failed) FailedBody(onRetry, onDevice) else LiveBody(voice, bars, clip, onStop, onCancel)
    }
}

@Composable
private fun LiveBody(voice: VoiceFeedback, bars: State<List<Double>>, clip: Boolean, onStop: () -> Unit, onCancel: () -> Unit) {
    val recording = voice.phase == VoicePhase.Recording
    val (level, remaining) = voice.warning
    val label = when {
        recording && level == DictationFeedback.Warning.None -> stringResource(R.string.voice_listening)
        recording -> stringResource(R.string.voice_left, remaining)
        voice.wait == DictationFeedback.Wait.Normal -> stringResource(R.string.voice_transcribing)
        else -> stringResource(R.string.voice_slow)
    }
    val labelColor = when { !recording -> Vmk.colors.textSecondary; level == DictationFeedback.Warning.Final -> Vmk.colors.danger; level == DictationFeedback.Warning.Soon -> Vmk.colors.warning; else -> Vmk.colors.textSecondary }
    val accent = if (recording) Vmk.colors.danger else Vmk.colors.primary
    val a11y = if (recording) stringResource(R.string.voice_rec_a11y, DictationFeedback.timer(voice.elapsed.toDouble())) else label
    val cancel: @Composable () -> Unit = {
        Box(Modifier.heightIn(min = 48.dp).widthIn(min = 48.dp).clip(CircleShape).clickable(role = Role.Button, onClick = onCancel).testTag("voiceCancel"), contentAlignment = Alignment.Center) {
            Text(stringResource(R.string.voice_cancel), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.textSecondary, maxLines = 1, modifier = Modifier.padding(horizontal = Vmk.space.s))
        }
    }
    val trailing: @Composable () -> Unit = {
        if (recording) {
            val stop = stringResource(if (clip) R.string.voice_stop else R.string.voice_stop_native)
            Box(Modifier.size(52.dp).clip(CircleShape).background(Vmk.colors.danger).clickable(onClickLabel = stop, role = Role.Button, onClick = onStop).semantics { contentDescription = stop }.testTag("voiceStop"), contentAlignment = Alignment.Center) {
                Icon(Sym.Stop, null, tint = Vmk.colors.background, modifier = Modifier.size(22.dp))
            }
        } else Box(Modifier.size(52.dp), contentAlignment = Alignment.Center) { LiveRing(size = 24.dp) }
    }
    val graphic: @Composable () -> Unit = { if (clip || !recording) Waveform(bars, sweeping = !recording, color = accent) else PulsingMic() }
    val status: @Composable () -> Unit = {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(accent).clearAndSetSemantics { })
            Text(label, style = MaterialTheme.typography.labelLarge, color = labelColor, maxLines = 3, modifier = Modifier.weight(1f, fill = false).testTag("voiceLabel"))
            Spacer(Modifier.weight(1f))
            if (recording) Text(DictationFeedback.timer(voice.elapsed.toDouble()), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.text, modifier = Modifier.clearAndSetSemantics { })
        }
    }
    if (isLargeText()) {   // big text: bars, then the words, then the two buttons on their own row (nothing wraps letter by letter)
        Column(Modifier.fillMaxWidth().semantics { contentDescription = a11y }, verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            graphic(); status()
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) { cancel(); Spacer(Modifier.weight(1f)); trailing() }
        }
    } else Row(Modifier.fillMaxWidth().semantics { contentDescription = a11y }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
        cancel()
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) { graphic(); status() }
        trailing()
    }
}

/** 24 bars, newest on the right. Recording: heights follow the level (read in the draw phase, so no recomposition per frame). Transcribing: a calm sweep, a still ramp with reduced motion. */
@Composable
private fun Waveform(bars: State<List<Double>>, sweeping: Boolean, color: Color) {
    val still = reduceMotion(LocalContext.current)
    val sweep = if (sweeping && !still) rememberInfiniteTransition(label = "sweep").animateFloat(0f, 1f, infiniteRepeatable(tween(2400, easing = CubicBezierEasing(0.2f, 0f, 0f, 1f)), RepeatMode.Restart), label = "p").value else 0f
    Canvas(Modifier.fillMaxWidth().height(28.dp).clearAndSetSemantics { }) {
        val n = DictationFeedback.BAR_COUNT; val w = 3.dp.toPx(); val gap = (size.width - w * n) / (n - 1).coerceAtLeast(1)
        val data = bars.value
        for (i in 0 until n) {
            val h = when {
                !sweeping -> data.getOrElse(i) { DictationFeedback.MIN_BAR }
                still -> 0.2 + 0.25 * i / n
                else -> { val p = ((sweep - i * 0.025) % 1f + 1f) % 1f; if (p < 0.6f) 0.22 + 0.38 * (Math.sin(p / 0.6 * Math.PI * 2 - Math.PI / 2) * 0.5 + 0.5) else 0.22 }
            }
            val bh = (size.height * h).toFloat().coerceAtLeast(3.dp.toPx())
            drawRoundRect(color, Offset(i * (w + gap), (size.height - bh) / 2), Size(w, bh), CornerRadius(1.5.dp.toPx()))
        }
    }
}

/** The phone's recognizer gives no level: a mic with a soft ring, so it is still clearly listening. */
@Composable
private fun PulsingMic() {
    val still = reduceMotion(LocalContext.current)
    val p = if (still) 0f else rememberInfiniteTransition(label = "pulse").animateFloat(0f, 1f, infiniteRepeatable(tween(1600, easing = CubicBezierEasing(0.2f, 0f, 0f, 1f)), RepeatMode.Restart), label = "r").value
    val c = Vmk.colors.danger
    Box(Modifier.height(28.dp).size(28.dp).clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(28.dp)) { drawCircle(c.copy(alpha = 0.5f * (1 - p)), radius = (12.dp.toPx()) * (1 + 0.2f * p), style = Stroke(2.dp.toPx(), cap = StrokeCap.Round)) }
        Icon(Sym.Mic, null, tint = c, modifier = Modifier.size(18.dp))
    }
}

@Composable
private fun FailedBody(onRetry: () -> Unit, onDevice: () -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            Icon(Sym.Warning, null, tint = Vmk.colors.warning, modifier = Modifier.size(18.dp))
            Text(stringResource(R.string.voice_failed), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.text)
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            Box(Modifier.weight(1f).heightIn(min = 48.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button, onClick = onRetry).testTag("voiceRetry"), contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.voice_retry), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.primary, textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = Vmk.space.m))
            }
            Box(Modifier.weight(1f).heightIn(min = 48.dp).clip(CircleShape).background(Vmk.colors.surface).clickable(role = Role.Button, onClick = onDevice).testTag("voiceDevice"), contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.voice_device), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.text, textAlign = TextAlign.Center, modifier = Modifier.padding(horizontal = Vmk.space.m, vertical = Vmk.space.xs))
            }
        }
    }
}
