package com.videomk.app.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.videomk.app.AppContainer
import com.videomk.app.BuildConfig
import com.videomk.app.DebugHooks
import com.videomk.app.R
import com.videomk.app.core.FeedbackContext
import com.videomk.app.core.RatingContext
import com.videomk.app.data.StoreReview
import kotlinx.coroutines.delay

private enum class RatingStep { None, Ask, Love, Feedback }

/**
 * Hosts the rating prompt while the library is on screen (so never while a video plays, and calmly: a short pause after arriving). The state
 * machine and its rules are in RatingPrompt (docs/FEEDBACK.md). Leaving the sheet any way other than a button (swipe, back, tap outside) means "later".
 */
@Composable
internal fun RatingHost(container: AppContainer, onLibrary: Boolean, creating: Boolean) {
    var step by rememberSaveable { mutableStateOf(RatingStep.None) }
    val prompt = container.ratingPrompt
    val context = LocalContext.current
    val force = BuildConfig.DEBUG && DebugHooks.forceRating(context)
    LaunchedEffect(onLibrary, creating) {
        if (!onLibrary || creating || step != RatingStep.None) return@LaunchedEffect
        delay(1500)   // let the person arrive at the library first
        while (step == RatingStep.None && (force || prompt.eligible)) {
            if (prompt.shouldShow(RatingContext(videoPlaying = false, creating = creating, suppressed = container.ratingSuppressed), debugForce = force)) {
                prompt.onShown(); step = RatingStep.Ask; break
            }
            delay(15_000)   // still inside the first two minutes after launch: look again later
        }
    }
    if (step == RatingStep.None) return
    val later = { step = RatingStep.None }
    when (step) {
        RatingStep.Feedback -> FeedbackSheet(container.feedbackApi, container.feedbackDraft, FeedbackContext.RatingPrompt, onClose = later, unhappy = true)
        RatingStep.Ask, RatingStep.Love -> RatingSheet(love = step == RatingStep.Love, onDismiss = later,
            onYes = { step = RatingStep.Love }, onNotReally = { step = RatingStep.Feedback },
            onRate = later, container = container, onAlready = { prompt.onAlreadyRated(); later() })
        else -> Unit
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RatingSheet(love: Boolean, onDismiss: () -> Unit, onYes: () -> Unit, onNotReally: () -> Unit, onRate: () -> Unit, container: AppContainer, onAlready: () -> Unit) {
    val activity = LocalContext.current.findActivity()
    ModalBottomSheet(
        onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp), containerColor = Vmk.colors.surface,
    ) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 16.dp).navigationBarsPadding().testTag(if (love) "ratingLoveSheet" else "ratingAskSheet"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (!love) {
                Text(stringResource(R.string.rating_ask_title), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
                PrimaryButton(stringResource(R.string.rating_yes), onYes, Modifier.testTag("ratingYes"))
                OutlinedButton(onClick = onNotReally, modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("ratingNotReally")) { Text(stringResource(R.string.rating_not_really)) }
            } else {
                Text(stringResource(R.string.rating_love_title), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
                Text(stringResource(R.string.rating_love_body), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary)
                PrimaryButton(stringResource(R.string.rating_rate), {
                    onRate()
                    if (activity != null) container.launchReview(activity)
                }, Modifier.testTag("ratingRate"))
                TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("ratingLater")) { Text(stringResource(R.string.rating_later), color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
                TextButton(onClick = onAlready, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("ratingAlready")) { Text(stringResource(R.string.rating_already), color = Vmk.colors.textSecondary, textAlign = TextAlign.Center) }
            }
        }
    }
}

internal fun Context.findActivity(): Activity? { var c = this; while (c is ContextWrapper) { if (c is Activity) return c; c = c.baseContext }; return null }
