package com.videomk.app.ui

import com.videomk.app.core.Txt
import androidx.compose.animation.Crossfade
import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.ColorMatrix
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.DayBucket
import com.videomk.app.core.MakingSnapshot
import com.videomk.app.core.MakingSteps
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus

/*
 * The component library of docs/UX_REVIEW.md section 6.2 item 8 (VideoRow, MakingCard, CostLine, EmptyState pieces, section headers).
 * Rules: heights follow the text (never a fixed height around text), every label wraps, targets are at least 48 dp, colours come from Vmk.colors.
 */

/** Text-size aware switch: from 1.5x the compact side-by-side layouts stack, so nothing is squeezed. */
@Composable
fun isLargeText(): Boolean = LocalDensity.current.fontScale >= 1.5f

@Composable
fun dayLabel(b: DayBucket): String = stringResource(when (b) { DayBucket.Today -> R.string.lib_group_today; DayBucket.Yesterday -> R.string.lib_group_yesterday; DayBucket.Earlier -> R.string.lib_group_earlier })

/** A day group title ("Today"). */
@Composable
fun DayHeader(bucket: DayBucket, modifier: Modifier = Modifier) {
    Text(dayLabel(bucket), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary, modifier = modifier.padding(top = Vmk.space.s).semantics { heading() }.testTag("dayHeader"))
}

// VideoRow

/** A finished video: a 128x72 poster with the duration, then the title (two lines) and when it was made. Stacks the poster above the text at large font sizes. */
@Composable
fun VideoRow(video: VideoItem, meta: String?, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(Vmk.radii.card)
    val desc = stringResource(R.string.lib_ready_desc, video.displayTitle) + (meta?.let { " $it." } ?: "")
    val large = isLargeText()
    Box(
        modifier.fillMaxWidth().clip(shape).background(Vmk.colors.surface).border(1.dp, Vmk.colors.outline, shape)
            .clickable(role = Role.Button, onClickLabel = stringResource(R.string.lib_status_ready), onClick = onClick)
            .semantics(mergeDescendants = true) { contentDescription = desc }.testTag("videoRow"),
    ) {
        if (large) Column(Modifier.padding(Vmk.space.m), verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
            Poster(video, Modifier.width(112.dp).height(63.dp))
            RowText(video, meta)
        } else Row(Modifier.padding(Vmk.space.m), horizontalArrangement = Arrangement.spacedBy(Vmk.space.m), verticalAlignment = Alignment.CenterVertically) {
            Poster(video, Modifier.width(112.dp).height(63.dp))
            Column(Modifier.weight(1f)) { RowText(video, meta) }
        }
    }
}

@Composable
private fun RowText(video: VideoItem, meta: String?) {
    Text(video.displayTitle, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
    meta?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 2.dp)) }
}

/** The poster with a play mark and the duration chip; a gradient while there is no picture. */
@Composable
fun Poster(video: VideoItem, modifier: Modifier = Modifier, grey: Boolean = false) {
    val shape = RoundedCornerShape(Vmk.radii.thumb)
    val filter = if (grey) ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(0f) }) else null
    Box(modifier.clip(shape).background(Brush.linearGradient(listOf(Vmk.colors.gradientStart, Vmk.colors.gradientEnd))).clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
        if (video.previewGifUrl != null) StableImage(video.previewGifUrl!!, ContentScale.Crop, Modifier.fillMaxSize(), filter)
        if (!grey) Box(Modifier.size(32.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.38f)), contentAlignment = Alignment.Center) {
            Icon(Sym.PlayArrow, null, tint = Color.White, modifier = Modifier.size(22.dp))
        }
        // the shape of a vertical, square or 4:5 video, as numbers, top left of the picture (landscape is the default and says nothing)
        if (!grey && video.aspect != null && video.aspect != "16:9") Text(video.aspect!!, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 1,
            modifier = Modifier.align(Alignment.TopStart).padding(6.dp).clip(RoundedCornerShape(6.dp)).background(Color.Black.copy(alpha = 0.55f)).padding(horizontal = 6.dp, vertical = 2.dp).semantics { contentDescription = Txt.s(R.string.lib_format_badge, video.aspect!!) })
        video.durationSeconds?.let {
            Text(duration(it), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 1,
                modifier = Modifier.align(Alignment.BottomEnd).padding(6.dp).clip(RoundedCornerShape(6.dp)).background(Color.Black.copy(alpha = 0.55f)).padding(horizontal = 6.dp, vertical = 2.dp))
        }
    }
}

// Failed or refused

/** "Didn't finish" (danger container) or "Not allowed" (warning container): the reason, what happened to credits, and the way out. Never near-black. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FailedRow(
    title: String, rejected: Boolean, detail: String?, thumb: String?, tag: String,
    onRetry: (() -> Unit)?, onDismiss: (() -> Unit)?, modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(Vmk.radii.card)
    val container = if (rejected) Vmk.colors.warningContainer else Vmk.colors.dangerContainer
    val accent = if (rejected) Vmk.colors.warning else Vmk.colors.danger
    val statusLabel = stringResource(if (rejected) R.string.lib_status_not_allowed else R.string.lib_status_didnt_finish)
    val desc = stringResource(R.string.lib_failed_desc, title, statusLabel)
    val grey = remember { ColorFilter.colorMatrix(ColorMatrix().apply { setToSaturation(0f) }) }
    Column(
        modifier.fillMaxWidth().clip(shape).background(container).padding(Vmk.space.m).semantics(mergeDescendants = false) { contentDescription = desc }.testTag(tag),
        verticalArrangement = Arrangement.spacedBy(Vmk.space.s),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(Vmk.space.m), verticalAlignment = Alignment.Top) {
            if (!isLargeText()) Box(Modifier.width(72.dp).height(72.dp).clip(RoundedCornerShape(Vmk.radii.thumb)).background(Vmk.colors.surface3).clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
                if (thumb != null) StableImage(thumb, ContentScale.Crop, Modifier.fillMaxSize().alpha(0.6f), grey)
                Icon(Sym.Warning, null, tint = accent, modifier = Modifier.size(24.dp))
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (isLargeText()) Icon(Sym.Warning, null, tint = accent, modifier = Modifier.size(18.dp))
                    Text(statusLabel, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = accent)
                }
                Text(title, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = 3, overflow = TextOverflow.Ellipsis)
                detail?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary) }
            }
        }
        if (onRetry != null || onDismiss != null) FlowRow(horizontalArrangement = Arrangement.spacedBy(Vmk.space.s), verticalArrangement = Arrangement.spacedBy(0.dp)) {
            if (onRetry != null) TextButton(onClick = onRetry, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("retryButton")) {
                Icon(Sym.Refresh, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp)); Spacer(Modifier.width(6.dp))
                Text(stringResource(R.string.common_try_again), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.primary)
            }
            if (onDismiss != null) TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("removeButton")) {
                Text(stringResource(R.string.common_remove), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
            }
        }
    }
}

/** A slow diagonal shimmer; a still lighter wash when animations are off (reduced motion: no shimmer). */
@Composable
fun MakingShimmer(modifier: Modifier) {
    val still = reduceMotion(LocalContext.current)
    if (still) { Box(modifier.background(Color.White.copy(alpha = 0.05f))); return }
    val t by rememberInfiniteTransition(label = "shimmer").animateFloat(0f, 1f, infiniteRepeatable(tween(com.videomk.app.core.DesignTokens.Motion.shimmer, easing = LinearEasing), RepeatMode.Restart), label = "x")
    Box(
        modifier.drawBehind {
            val w = size.width * 0.5f
            val x = -w + (size.width + w) * t
            drawRect(Brush.linearGradient(listOf(Color.Transparent, Color.White.copy(alpha = 0.14f), Color.Transparent), start = Offset(x, 0f), end = Offset(x + w, size.height)))
        },
    )
}

/** Cross-fades between two states of one thing (Making to Ready); a short fade only when animations are off. */
@Composable
fun <T> SettleCrossfade(state: T, modifier: Modifier = Modifier, content: @Composable (T) -> Unit) {
    val still = reduceMotion(LocalContext.current)
    Crossfade(state, modifier.animateContentSize(tween(if (still) 0 else com.videomk.app.core.DesignTokens.Motion.insert)), animationSpec = tween(if (still) com.videomk.app.core.DesignTokens.Motion.reducedFade else com.videomk.app.core.DesignTokens.Motion.insert), label = "settle") { content(it) }
}

// CostLine

/**
 * The receipt line under the Create button: the status text ("3 credits · you'll have 39 left", or what is wrong and the fix) with the bolt, then the 4K rule when it
 * applies and "What does this cost?" ([text] null: only the last two, used on Create where the status bar already shows the receipt). [onWhy] opens the "How credits work" sheet (the same text the wallet shows).
 */
@Composable
fun CostLine(text: String?, fourK: Boolean, onWhy: () -> Unit, modifier: Modifier = Modifier, showWhy: Boolean = true) {
    Column(modifier.fillMaxWidth().testTag("costHelp"), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        if (text != null) Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Icon(Sym.Bolt, null, tint = Vmk.colors.primary, modifier = Modifier.size(18.dp).padding(top = 2.dp))
            Text(text, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, modifier = Modifier.weight(1f))
        }
        if (fourK) Text(stringResource(R.string.create_cost_4k_double), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        if (showWhy) TextButton(onClick = onWhy, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("costWhy")) {
            Text(stringResource(R.string.create_cost_why), style = MaterialTheme.typography.labelLarge, color = Vmk.colors.primary)
        }
    }
}

/** "How credits work": the one explanation, shown in the wallet body and in the sheet behind CostLine. */
@Composable
fun CreditsExplainer(modifier: Modifier = Modifier, showTitle: Boolean = true, fourK: Boolean = false) {
    Column(modifier.fillMaxWidth().testTag("creditsExplainer"), verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
        if (showTitle) Text(stringResource(R.string.wallet_cost_title), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
        // the 4K rule is only told where a 4K resolution can be chosen (the app offers 720p and 1080p unless the server lists more)
        for (id in listOfNotNull(R.string.wallet_cost_minute, R.string.wallet_cost_example, R.string.wallet_cost_4k.takeIf { fourK }, R.string.wallet_cost_expiry))
            Text(stringResource(id), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
    }
}

// WalletHero

/** The balance as the hero of the wallet: a gradient surface, the number at 56 sp (tabular), the word under it. */
@Composable
fun WalletHero(balanceText: String, label: String, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(Vmk.radii.videoCard)
    val spoken = stringResource(R.string.wallet_hero_desc, "$balanceText $label")
    Column(
        modifier.fillMaxWidth().clip(shape).background(Vmk.gradientNow).padding(horizontal = Vmk.space.xl, vertical = Vmk.space.xxl)
            .semantics(mergeDescendants = true) { contentDescription = spoken }.testTag("balanceCard"),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Icon(Sym.Bolt, null, tint = Vmk.colors.onPrimary, modifier = Modifier.size(40.dp))
            Text(balanceText, style = VmkType.hero, color = Vmk.colors.onPrimary, modifier = Modifier.testTag("balanceValue"))
        }
        Text(label, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.onPrimary.copy(alpha = 0.92f), textAlign = TextAlign.Center)
    }
}

/** The "How credits work" sheet behind "What does this cost?". */
@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun CostSheet(fourK: Boolean, onDismiss: () -> Unit) {
    androidx.compose.material3.ModalBottomSheet(onDismissRequest = onDismiss, containerColor = Vmk.colors.surface, modifier = Modifier.testTag("costSheet")) {
        Column(Modifier.padding(horizontal = Vmk.space.sheet).padding(bottom = Vmk.space.xxl), verticalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
            CreditsExplainer(fourK = fourK)
            androidx.compose.material3.TextButton(onClick = onDismiss, modifier = Modifier.heightIn(min = Vmk.minTouch).align(Alignment.End)) { Text(stringResource(R.string.common_done), color = Vmk.colors.primary) }
        }
    }
}
