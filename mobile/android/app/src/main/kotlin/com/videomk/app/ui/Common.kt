package com.videomk.app.ui

import android.content.Context
import android.provider.Settings
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle

/** Animations off (developer options, battery saver, accessibility "remove animations"): the shimmer and similar effects stand still. */
fun reduceMotion(context: Context): Boolean = try {
    Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
} catch (e: Exception) { false }

@Composable
fun FullScreenSpinner(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

@Composable
fun MessageState(title: String, body: String, actionLabel: String? = null, onAction: (() -> Unit)? = null, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(title, style = MaterialTheme.typography.titleLarge, textAlign = TextAlign.Center, color = Vmk.colors.text)
        Text(body, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center, color = Vmk.colors.textSecondary)
        if (actionLabel != null && onAction != null) Button(onClick = onAction) { Text(actionLabel) }
    }
}

/**
 * While the screen is visible: the list is read the moment it becomes visible (first show, back from another app, the phone unlocked) and then for as long
 * as something is being made. [running] is not a key on purpose: the loop itself waits for the next video, so nothing restarts it and no return is missed.
 */
@Composable
fun PollWhileRunning(app: AppViewModel, @Suppress("UNUSED_PARAMETER") running: Boolean = false) {
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(app, lifecycle) {
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) { app.pollWhileRunning() }
    }
}

private val urlRegex = Regex("https?://[^\\s<>\"')]+[^\\s<>\"').,;:!?]")

/** Makes every URL in the text tappable (photographer and Unsplash links in the credits, Wikipedia sources). */
fun linkified(text: String, linkColor: androidx.compose.ui.graphics.Color): AnnotatedString = buildAnnotatedString {
    var last = 0
    for (m in urlRegex.findAll(text)) {
        append(text.substring(last, m.range.first))
        withLink(LinkAnnotation.Url(m.value, TextLinkStyles(SpanStyle(color = linkColor, textDecoration = TextDecoration.Underline)))) { append(m.value) }
        last = m.range.last + 1
    }
    append(text.substring(last))
}

/** The system photo picker's own limit (Android 13+ / R extensions 2); callers wrap it in runCatching and fall back to the app's limit. */
@android.annotation.SuppressLint("NewApi")
internal fun pickImagesMaxLimit(): Int = android.provider.MediaStore.getPickImagesMaxLimit()
