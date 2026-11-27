package com.videomk.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.DesignTokens
import com.videomk.app.core.FeedbackContext
import com.videomk.app.core.FeedbackDraft
import com.videomk.app.core.FeedbackApi
import com.videomk.app.core.FeedbackFlow
import com.videomk.app.core.FeedbackKind
import com.videomk.app.core.FeedbackResult
import com.videomk.app.core.FeedbackRules
import com.videomk.app.core.FeedbackStage
import kotlinx.coroutines.launch

/** A Settings row: "Send feedback" with a one-line promise under it. */
@Composable
internal fun FeedbackRow(onOpen: () -> Unit) {
    val open = stringResource(R.string.feedback_open)
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(onClickLabel = open, role = androidx.compose.ui.semantics.Role.Button, onClick = onOpen).testTag("feedbackRow"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(Sym.Chat, null, tint = Vmk.colors.primary, modifier = Modifier.size(22.dp))
        Text(stringResource(R.string.feedback_title), color = Vmk.colors.text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
        Icon(Sym.ChevronRight, null, tint = Vmk.colors.textSecondary)
    }
}

/** The quiet link under a finished video. */
@Composable
internal fun FeedbackLink(onOpen: () -> Unit, modifier: Modifier = Modifier) {
    TextButton(onClick = onOpen, modifier = modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("feedbackLink")) {
        Text(stringResource(R.string.feedback_after_video), color = Vmk.colors.textSecondary, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
    }
}

/**
 * The feedback sheet: a friendly line, one multi-line field (3 to 2000 characters, with a counter), optional kind chips and Send. A failed send
 * keeps the text (and the draft outlives the sheet); success shows a calm thank-you with a check and "Done". [unhappy] is the "Not really" path:
 * it opens with "Sorry about that. What would make it better?". Nothing animates, so reduce-motion needs no special case.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun FeedbackSheet(api: FeedbackApi?, draft: FeedbackDraft, context: FeedbackContext, onClose: () -> Unit, unhappy: Boolean = false) {
    val flow = remember { FeedbackFlow(api, draft, context) }
    val stage by flow.stage.collectAsState()
    var text by remember { mutableStateOf(draft.text) }
    var kind by remember { mutableStateOf(draft.kind) }
    val scope = rememberCoroutineScope()
    val haptics = rememberHaptics()
    val sending = stage is FeedbackStage.Sending
    ModalBottomSheet(
        onDismissRequest = { if (!sending) onClose() },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true, confirmValueChange = { !sending }),
        shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp), containerColor = Vmk.colors.surface,
    ) {
        Column(
            Modifier.fillMaxWidth().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 16.dp).navigationBarsPadding()
                .semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("feedbackSheet"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (stage is FeedbackStage.Sent) {
                Column(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(Modifier.size(64.dp).clip(CircleShape).background(Vmk.colors.successContainer), contentAlignment = Alignment.Center) {
                        Icon(Sym.Check, stringResource(R.string.feedback_sent_a11y), tint = Vmk.colors.success, modifier = Modifier.size(36.dp))
                    }
                    Text(stringResource(R.string.feedback_thanks_title), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading(); liveRegion = LiveRegionMode.Polite }.testTag("feedbackThanks"))
                    Text(stringResource(R.string.feedback_thanks_body), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center)
                    PrimaryButton(stringResource(R.string.common_done), onClose, Modifier.testTag("feedbackDone"))
                }
                return@Column
            }
            SheetHeader(stringResource(R.string.feedback_title), { if (!sending) onClose() }, closeTag = "feedbackClose")
            Text(stringResource(if (unhappy) R.string.feedback_intro_unhappy else R.string.feedback_intro), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary)
            val label = stringResource(R.string.feedback_field_label)
            val trimmedLength = FeedbackRules.clean(text).length
            val counter = stringResource(R.string.feedback_counter, text.length, FeedbackRules.MAX)
            val counterA11y = stringResource(R.string.feedback_counter_a11y, text.length, FeedbackRules.MAX)
            VmkField(text, { text = FeedbackRules.clamp(it); flow.edit(text) }, Modifier.semantics { contentDescription = label }.testTag("feedbackField"), placeholder = stringResource(R.string.feedback_field_hint), singleLine = false, minHeight = 132.dp, enabled = !sending, keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(if (trimmedLength in 1 until FeedbackRules.MIN) stringResource(R.string.feedback_min_hint, FeedbackRules.MIN) else "", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f))
                Text(counter, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.semantics { contentDescription = counterA11y }.testTag("feedbackCounter"))
            }
            Text(stringResource(R.string.feedback_kind_label), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for ((k, res) in listOf(FeedbackKind.Idea to R.string.feedback_kind_idea, FeedbackKind.Problem to R.string.feedback_kind_problem, FeedbackKind.Other to R.string.feedback_kind_other)) {
                    ChoiceChip(stringResource(res), kind == k, Modifier.testTag("feedbackKind-${k.wire}")) { kind = if (kind == k) null else k; flow.pick(kind) }
                }
            }
            (stage as? FeedbackStage.Failed)?.let { f ->
                Text(
                    stringResource(when (f.reason) {
                        FeedbackResult.Offline -> R.string.feedback_err_offline
                        FeedbackResult.RateLimited -> R.string.feedback_err_rate_limited
                        FeedbackResult.Invalid -> R.string.feedback_err_invalid
                        else -> R.string.feedback_err_failed
                    }),
                    style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text,
                    modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Vmk.colors.dangerContainer).padding(12.dp).semantics { liveRegion = LiveRegionMode.Polite }.testTag("feedbackError"),
                )
            }
            val failed = stage is FeedbackStage.Failed
            PrimaryButton(
                stringResource(if (sending) R.string.feedback_sending else if (failed) R.string.common_try_again else R.string.feedback_send),
                onClick = { haptics.play(DesignTokens.Haptic.Send); scope.launch { flow.send() } },
                enabled = FeedbackRules.isValid(text) && !sending, modifier = Modifier.testTag("feedbackSend"),
            ) {
                if (sending) { CircularProgressIndicator(Modifier.size(20.dp), color = androidx.compose.material3.LocalContentColor.current, strokeWidth = 2.dp); androidx.compose.foundation.layout.Spacer(Modifier.padding(4.dp)) }
                Text(stringResource(if (sending) R.string.feedback_sending else if (failed) R.string.common_try_again else R.string.feedback_send), style = MaterialTheme.typography.titleMedium, color = androidx.compose.material3.LocalContentColor.current, textAlign = TextAlign.Center)
            }
        }
    }
}
