package com.videomk.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.DeckAction
import com.videomk.app.core.DeckCaps
import com.videomk.app.core.DeckState
import com.videomk.app.core.Lengths

/** The "Add a presentation" row of the attach sheet. Only drawn where the server offers presentations. */
@Composable
fun DeckEntryRow(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(Vmk.radii.card)
    val desc = stringResource(R.string.deck_add_desc)
    Row(
        modifier.fillMaxWidth().heightIn(min = 60.dp).clip(shape).background(Vmk.colors.surfaceRaised)
            .clickable(role = Role.Button, onClickLabel = stringResource(R.string.deck_add_title), onClick = onClick).padding(horizontal = 12.dp, vertical = 8.dp)
            .semantics(mergeDescendants = true) { contentDescription = desc }.testTag("addDeck"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        DeckIcon()
        Column(Modifier.weight(1f)) {
            Text(stringResource(R.string.deck_add_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
            Text(stringResource(R.string.deck_add_subtitle), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        }
        Icon(Sym.ChevronRight, null, tint = Vmk.colors.textSecondary)
    }
}

@Composable
private fun DeckIcon(tint: Color = Vmk.colors.primary) {
    Box(Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(Sym.Slideshow, null, tint = tint) }
}

/**
 * The presentation on the Create screen, in the place of the photos row (a video is made from one or the other): picked, uploading with progress and Cancel,
 * preparing, ready (file name, slides, suggested length, credits, and the promise), or a calm failure with its one next step.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DeckCard(
    state: DeckState, caps: DeckCaps?, onRemove: () -> Unit, onPickAgain: () -> Unit, onRetry: () -> Unit, onKeepWaiting: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val shape = RoundedCornerShape(20.dp)
    val name = when (state) {
        is DeckState.Copying -> state.name; is DeckState.Uploading -> state.name; is DeckState.Processing -> state.name; is DeckState.Ready -> state.name; is DeckState.Failed -> state.name.orEmpty()
        DeckState.Idle -> ""
    }
    val failed = state as? DeckState.Failed
    Column(
        modifier.fillMaxWidth().clip(shape).background(Vmk.colors.surface).border(1.dp, if (failed != null) Vmk.colors.warning else Vmk.colors.outline, shape).padding(12.dp).testTag("deckCard"),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            DeckIcon()
            Column(Modifier.weight(1f).padding(top = 2.dp)) {
                Text(stringResource(R.string.deck_card_label), style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textSecondary)
                if (name.isNotEmpty()) Text(name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.testTag("deckName"))
            }
            // while it is going up or being prepared the way out is the labelled Cancel below; once there is a result, the X removes it (48 dp)
            val removeLabel = stringResource(R.string.deck_remove_desc)
            if (state is DeckState.Ready || state is DeckState.Failed) Box(
                Modifier.size(48.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = removeLabel, onClick = onRemove).semantics { contentDescription = removeLabel }.testTag("deckRemove"),
                contentAlignment = Alignment.Center,
            ) { Icon(Sym.Close, null, tint = Vmk.colors.textSecondary) }
        }
        when (state) {
            is DeckState.Copying -> Working(stringResource(R.string.deck_copying), null, null, onRemove)
            is DeckState.Uploading -> Working(stringResource(R.string.deck_uploading, state.percent), state.percent / 100f, null, onRemove)
            is DeckState.Processing -> Working(stringResource(R.string.deck_processing), null, stringResource(R.string.deck_processing_hint), onRemove)
            is DeckState.Ready -> {
                val info = state.info
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Sym.CheckCircle, null, tint = Vmk.colors.success, modifier = Modifier.size(20.dp))
                    Text(
                        stringResource(R.string.deck_ready_line, pluralStringResource(R.plurals.deck_slides, info.slides, info.slides), Lengths.long(info.suggestedMinutes)),
                        style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, modifier = Modifier.testTag("deckSummary"),
                    )
                }
                CostLine(pluralStringResource(R.plurals.deck_cost, info.suggestedCredits, info.suggestedCredits), false, onWhy = {}, showWhy = false, modifier = Modifier.testTag("deckCost"))
                Text(stringResource(R.string.deck_promise), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("deckPromise"))
            }
            is DeckState.Failed -> {
                val f = state.failure
                Column(Modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Sym.Warning, null, tint = Vmk.colors.warning, modifier = Modifier.size(20.dp).padding(top = 2.dp))
                        Text(f.title(), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.testTag("deckErrorTitle"))
                    }
                    Text(f.body(caps), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("deckErrorBody"))
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    when (f.problem.action) {
                        DeckAction.Retry -> PillButton(stringResource(R.string.common_try_again), onRetry, "deckRetry")
                        DeckAction.KeepWaiting -> { PillButton(stringResource(R.string.deck_keep_waiting), onKeepWaiting, "deckKeepWaiting"); TextButton(onClick = onPickAgain, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("deckPickAnother")) { Text(stringResource(R.string.deck_choose_another), fontWeight = FontWeight.SemiBold) } }
                        DeckAction.PickAgain -> PillButton(stringResource(if (f.problem == com.videomk.app.core.DeckProblem.Timeout || f.problem == com.videomk.app.core.DeckProblem.ConvertFailed) R.string.deck_choose_again else R.string.deck_choose_another), onPickAgain, "deckPickAnother")
                        DeckAction.None -> {}
                    }
                    TextButton(onClick = onRemove, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("deckRemoveText")) { Text(stringResource(R.string.common_remove), color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
                }
            }
            DeckState.Idle -> {}
        }
    }
}

@Composable
private fun Working(text: String, progress: Float?, hint: String?, onCancel: () -> Unit) {
    Column(Modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }.testTag("deckWorking"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (progress != null) LinearProgressIndicator(progress = { progress }, Modifier.fillMaxWidth().heightIn(min = 4.dp), color = Vmk.colors.primary, trackColor = Vmk.colors.surface3)
        else LinearProgressIndicator(Modifier.fillMaxWidth().heightIn(min = 4.dp), color = Vmk.colors.primary, trackColor = Vmk.colors.surface3)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(text, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            TextButton(onClick = onCancel, modifier = Modifier.heightIn(min = Vmk.minTouch).testTag("deckCancel")) { Text(stringResource(R.string.deck_cancel_upload), fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary) }
        }
        if (hint != null) Text(hint, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
    }
}

@Composable
private fun PillButton(label: String, onClick: () -> Unit, tag: String) {
    Box(
        Modifier.heightIn(min = Vmk.minTouch).clip(CircleShape).background(Vmk.gradientNow).clickable(role = Role.Button, onClick = onClick).padding(horizontal = 22.dp).testTag(tag),
        contentAlignment = Alignment.Center,
    ) { Text(label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.onPrimary, maxLines = 2) }
}
