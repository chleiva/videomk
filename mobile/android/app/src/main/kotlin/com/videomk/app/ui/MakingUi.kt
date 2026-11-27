package com.videomk.app.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.DesignTokens
import com.videomk.app.core.MakingSnapshot
import com.videomk.app.core.MakingStrip
import com.videomk.app.core.MakingTile
import com.videomk.app.data.ReadyNotifier

/*
 * Making is a story, not a progress bar (docs/DESIGN_BAR_2026.md signature 3): the scene being built is shown large, finished scenes fill a film strip one by one,
 * one plain line says what is happening now and the sentence being narrated sits beneath. No step names, no percentages. The card on Videos and the Making screen
 * draw the same MakingSnapshot, so they cannot disagree. Everything the server may not send yet is optional: without scenes there is no strip, only the calm line.
 */

enum class MakingLayout { List, Detail }

/** One scene of the film strip. Finished: its picture, or a filled tile when it has none. In work: the live ring. Waiting: an empty outline. */
@Composable
fun SceneTile(tile: MakingTile, videoId: String?, onBrand: Boolean, modifier: Modifier = Modifier, radius: Dp = Vmk.radii.tile) {
    val shape = RoundedCornerShape(radius)
    val still = reduceMotion(LocalContext.current)
    val done = tile.state == MakingTile.State.Done
    // a tile fills with a short scale-and-fade (reduced motion: a plain fade)
    val fill by animateFloatAsState(if (done) 1f else 0f, tween(if (still) DesignTokens.Motion.reducedFade else DesignTokens.Motion.tile), label = "tile")
    val empty = if (onBrand) Color.White.copy(alpha = 0.34f) else Vmk.colors.outline
    Box(
        modifier.clip(shape).then(when (tile.state) {
            MakingTile.State.Current -> Modifier.background(if (onBrand) Color.White.copy(alpha = 0.18f) else Vmk.colors.surfaceRaised).border(2.dp, Vmk.liveRing, shape)
            MakingTile.State.Waiting -> Modifier.border(1.5.dp, empty, shape)
            MakingTile.State.Done -> Modifier
        }).clearAndSetSemantics { },
    ) {
        if (fill > 0f) Box(Modifier.fillMaxSize().graphicsLayer { alpha = fill; if (!still) { scaleX = 0.9f + 0.1f * fill; scaleY = 0.9f + 0.1f * fill } }.clip(shape).then(if (onBrand) Modifier.background(Color.White.copy(alpha = 0.86f)) else Modifier.background(Vmk.makingGradient))) {
            val url = tile.thumbUrl
            if (url != null && videoId != null) StableImage(url, ContentScale.Crop, Modifier.fillMaxSize(), key = "making/$videoId/${tile.index}")
        }
    }
}

/** The line that says what is happening now: the sparkle (live work) and the words; announced politely when it changes, never on every tick. */
@Composable
private fun LiveLine(text: String, color: Color, sparkle: Color, modifier: Modifier = Modifier, style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.bodyMedium, announce: Boolean = false) {
    Row(modifier, verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
        Sparkle(Modifier.padding(top = 2.dp), tint = sparkle, size = 16.dp)
        Text(text, style = style, color = color, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f).then(if (announce) Modifier.semantics { liveRegion = LiveRegionMode.Polite } else Modifier).testTag("liveLine"))
    }
}

/**
 * The Making card on Videos: the title, how long is left, the scene tiles filling, and one live line. Without scenes from the server it is the title and one calm line.
 * [MakingLayout.Detail] draws the whole Making screen body instead (used by the video screen and by tests).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MakingCard(snapshot: MakingSnapshot, modifier: Modifier = Modifier, layout: MakingLayout = MakingLayout.List, onClick: (() -> Unit)? = null, videoId: String? = null) {
    if (layout == MakingLayout.Detail) { MakingBody(snapshot, videoId, 16f / 9f, null, modifier); return }
    val shape = RoundedCornerShape(Vmk.radii.making)
    val spoken = snapshot.spoken()
    Box(
        modifier.fillMaxWidth().vmkGlow(shape).clip(shape)
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
            .semantics(mergeDescendants = true) { contentDescription = spoken },
    ) {
        Box(Modifier.matchParentSize().background(Vmk.makingGradient))
        if (snapshot.tiles.isEmpty()) MakingShimmer(Modifier.matchParentSize())
        Column(Modifier.fillMaxWidth().padding(Vmk.space.xl), verticalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
            FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Vmk.space.m, Alignment.Start), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(snapshot.title, style = VmkType.makingTitle, color = Color.White, maxLines = if (isLargeText()) 4 else 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = !isLargeText()))
                snapshot.etaShort?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Color.White.copy(alpha = 0.86f), modifier = Modifier.padding(top = 2.dp)) }
            }
            if (snapshot.tiles.isNotEmpty()) Row(Modifier.fillMaxWidth().testTag("sceneTiles"), horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                val shown = MakingStrip.window(snapshot.tiles, CARD_TILES)
                for (t in shown) SceneTile(t, videoId, onBrand = true, modifier = Modifier.weight(1f).aspectRatio(1f))
                repeat(CARD_TILES - shown.size) { Spacer(Modifier.weight(1f)) }
            }
            val counter = snapshot.scene?.let { stringResource(R.string.making_scene_counter, it.index, it.total) }
            LiveLine(listOfNotNull(counter, snapshot.stageLine.trimEnd('.')).joinToString(" · "), Color.White.copy(alpha = 0.94f), Vmk.colors.live)
        }
    }
}

private const val CARD_TILES = 7

/**
 * The Making screen: the current scene large (the newest finished picture, inside the live ring), the title, the live line, the film strip, "Scene 5 of 9" and the
 * time left, the sentence being narrated, and one switch: "Tell me when it's ready".
 */
@Composable
fun MakingBody(snapshot: MakingSnapshot, videoId: String?, ratio: Float, notifier: ReadyNotifier?, modifier: Modifier = Modifier) {
    val heroShape = RoundedCornerShape(Vmk.radii.making)
    Column(modifier.fillMaxWidth().padding(horizontal = Vmk.space.screen).padding(bottom = Vmk.space.xxl), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
        // the frame has the video's own shape (a tall video is kept to a sensible height and centred)
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            val frame = if (ratio >= 1f) Modifier.fillMaxWidth().aspectRatio(ratio) else Modifier.heightIn(max = 380.dp).aspectRatio(ratio)
            Box(frame.vmkShadow(2, heroShape, Vmk.colors.dark).clip(heroShape).background(Vmk.makingGradient).border(3.dp, Vmk.liveRing, heroShape).clearAndSetSemantics { }.testTag("makingHero")) {
                MakingShimmer(Modifier.matchParentSize())
                val hero = snapshot.hero
                androidx.compose.animation.Crossfade(hero?.index, animationSpec = tween(DesignTokens.Motion.insert), label = "hero") { index ->
                    val t = snapshot.tiles.firstOrNull { it.index == index }
                    if (t?.thumbUrl != null && videoId != null) StableImage(t.thumbUrl, ContentScale.Crop, Modifier.fillMaxSize().padding(3.dp).clip(RoundedCornerShape(Vmk.radii.making - 3.dp)), key = "making/$videoId/${t.index}")
                    else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { LogoMark(size = 56.dp) }
                }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            Text(snapshot.title, style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, maxLines = 4, overflow = TextOverflow.Ellipsis, modifier = Modifier.semantics { heading() }.testTag("makingTitle"))
            LiveLine(snapshot.stageLine.trimEnd('.'), Vmk.colors.textSecondary, Vmk.colors.primary, style = MaterialTheme.typography.bodyLarge, announce = true)
            // the chosen look was adapted: the server's one sentence, as sent, quietly
            snapshot.note?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("lookNote")) }
        }
        if (snapshot.tiles.isNotEmpty()) {
            val scroll = rememberScrollState()
            val current = snapshot.tiles.indexOfFirst { it.state == MakingTile.State.Current }
            val density = androidx.compose.ui.platform.LocalDensity.current
            // keep the scene in work in view as the strip fills
            LaunchedEffect(current) { if (current > 4) scroll.animateScrollTo(with(density) { ((current - 4) * (STRIP_TILE + 8.dp).toPx()).toInt() }) }
            Row(Modifier.fillMaxWidth().horizontalScroll(scroll).testTag("filmStrip"), horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                for (t in snapshot.tiles) SceneTile(t, videoId, onBrand = false, modifier = Modifier.size(STRIP_TILE))
            }
        }
        val counter = snapshot.scene?.let { stringResource(R.string.making_scene_counter, it.index, it.total) }
        if (counter != null || snapshot.etaShort != null) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
            Text(counter.orEmpty(), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f).testTag("sceneCounter"))
            snapshot.etaShort?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, textAlign = TextAlign.End) }
        }
        snapshot.narrationLine?.let {
            Text(stringResource(R.string.quoted, it), style = VmkType.narration, color = Vmk.colors.textSecondary, maxLines = 6, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = Vmk.space.l).testTag("narrationLine"))
        }
        Spacer(Modifier.size(Vmk.space.s))
        if (notifier != null) NotifySwitch(notifier)
        Text(stringResource(R.string.making_keeps_going), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().testTag("leavePromise"))
    }
}

private val STRIP_TILE = 56.dp

/** The one switch: "Tell me when it's ready". Turning it on asks for the notification permission (Android 13 and later); a refusal turns it back off and says why in one line. */
@Composable
private fun NotifySwitch(notifier: ReadyNotifier) {
    val wanted by notifier.wanted.collectAsState()
    var refused by remember { mutableStateOf(false) }
    val on = wanted && notifier.permitted()
    val haptics = rememberHaptics()
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted -> notifier.set(granted); refused = !granted }
    fun toggle(v: Boolean) {
        haptics.play(DesignTokens.Haptic.Selection)
        if (!v) { notifier.set(false); refused = false; return }
        if (notifier.permitted()) { notifier.set(true); refused = false }
        else if (Build.VERSION.SDK_INT >= 33) ask.launch(Manifest.permission.POST_NOTIFICATIONS)
        else refused = true
    }
    val label = stringResource(R.string.making_notify)
    Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 64.dp).vmkShadow(1, RoundedCornerShape(Vmk.radii.card), Vmk.colors.dark).clip(RoundedCornerShape(Vmk.radii.card)).background(Vmk.colors.surface)
                .toggleable(on, role = Role.Switch, onValueChange = ::toggle).padding(horizontal = Vmk.space.xl, vertical = Vmk.space.m).testTag("notifySwitch"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m),
        ) {
            Icon(Sym.Notifications, null, tint = Vmk.colors.primary, modifier = Modifier.size(24.dp))
            Text(label, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            Switch(on, onCheckedChange = null, colors = SwitchDefaults.colors(checkedTrackColor = Vmk.colors.primary, checkedThumbColor = MaterialTheme.colorScheme.onPrimary))
        }
        if (refused) Text(stringResource(R.string.making_notify_off), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite })
    }
}
