package com.videomk.app.ui

import androidx.compose.animation.Crossfade
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
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.videomk.app.core.ComposerLogic
import com.videomk.app.core.CreateErrors
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.CreatePlatforms
import com.videomk.app.core.CreateStop
import com.videomk.app.core.Question
import kotlinx.coroutines.delay

/** The sheets of the request check (docs/UI_DESIGN.md section o.3): the slow-check skeleton, one question at a time, the summary, and the kind "we can't make this" sheet. */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun CreateSheetsHost(composer: ComposerViewModel, balance: Int?, options: CreateOptions, onSubmitEdit: () -> Unit, onWallet: () -> Unit) {
    val kind = composer.sheetKind
    if (kind == ComposerViewModel.CreateSheetKind.None) return
    val shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
    ModalBottomSheet(
        onDismissRequest = { composer.dismissSheet() }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), shape = shape, containerColor = Vmk.colors.surface,
    ) {
        Column(Modifier.fillMaxWidth().heightIn(min = 470.dp).padding(horizontal = 20.dp).navigationBarsPadding().padding(bottom = 12.dp).semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("createSheet")) {
            when (kind) {
                ComposerViewModel.CreateSheetKind.Checking -> CheckingBody(composer)
                ComposerViewModel.CreateSheetKind.Asking -> AskingBody(composer)
                ComposerViewModel.CreateSheetKind.Summary -> SummaryBody(composer, balance, options, onWallet)
                ComposerViewModel.CreateSheetKind.Stop -> composer.stop?.let { StopBody(composer, it) }
                ComposerViewModel.CreateSheetKind.None -> Unit
            }
        }
    }
}

@Composable
private fun CheckingBody(composer: ComposerViewModel) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.weight(1f))
        TextButton(onClick = { composer.skipCheck() }, modifier = Modifier.heightIn(min = 48.dp).testTag("makeItNow")) { Text("Make it now", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold) }
    }
    Column(Modifier.semantics { contentDescription = "Checking your request"; liveRegion = LiveRegionMode.Polite }, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.fillMaxWidth(0.7f).heightIn(min = 34.dp).clip(RoundedCornerShape(10.dp)).background(Vmk.colors.surfaceRaised))
        Box(Modifier.fillMaxWidth(0.5f).heightIn(min = 18.dp).clip(RoundedCornerShape(8.dp)).background(Vmk.colors.surfaceRaised))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 8.dp)) { repeat(3) { Box(Modifier.width(84.dp).heightIn(min = 50.dp).clip(CircleShape).background(Vmk.colors.surfaceRaised)) } }
        Text("Checking your request…", style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 16.dp))
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun androidx.compose.foundation.layout.ColumnScope.AskingBody(composer: ComposerViewModel) {
    val f = composer.flow ?: return
    val version = composer.flowVersion   // the flow is mutable: this re-reads it after every answer
    val q = f.current ?: return
    val still = reduceMotion(LocalContext.current)
    val view = LocalView.current
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
        if (f.canGoBack) IconButton(onClick = { composer.questionBack() }, modifier = Modifier.size(48.dp).testTag("questionBack")) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Previous question", tint = Vmk.colors.text) }
        else Box(Modifier.size(48.dp))
        Row(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically) {
            for (i in 0 until f.total) Box(Modifier.size(width = if (i == f.index) 22.dp else 8.dp, height = 8.dp).clip(CircleShape).background(if (i == f.index) Vmk.colors.primary else Vmk.colors.surface3))
        }
        TextButton(onClick = { composer.makeItNow() }, modifier = Modifier.heightIn(min = 48.dp).testTag("makeItNow")) { Text("Make it now", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold) }
    }
    Crossfade(version to f.index, animationSpec = tween(if (still) 0 else 280), label = "question", modifier = Modifier.weight(1f, fill = false)) { (_, idx) ->
        val question = f.questions.getOrNull(idx) ?: q
        QuestionContent(composer, question, f.overline.takeIf { idx == f.index } ?: "QUESTION ${idx + 1} OF ${f.total}", f.answerOf(question.id))
    }
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        TextButton(onClick = { composer.skipQuestion() }, modifier = Modifier.heightIn(min = 48.dp).testTag("questionSkip")) { Text("Skip", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.textSecondary) }
    }
    LaunchedEffect(f.index) { view.announceForAccessibility("Question ${f.index + 1} of ${f.total}. ${q.text}") }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun QuestionContent(composer: ComposerViewModel, q: Question, overline: String, current: com.videomk.app.core.Answer?) {
    var picked by remember(q.id) { mutableStateOf<String?>(null) }
    var other by remember(q.id) { mutableStateOf(false) }
    var otherText by remember(q.id) { mutableStateOf("") }
    // a chip is shown selected, then the sheet moves on by itself after a beat (no Next button)
    LaunchedEffect(picked) { picked?.let { delay(250); composer.choose(it) } }
    Column(Modifier.fillMaxWidth().padding(top = 4.dp)) {
        Overline(overline)
        Text(q.text, style = MaterialTheme.typography.headlineSmall.copy(fontSize = 27.sp, lineHeight = 33.sp), fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.padding(top = 4.dp).semantics { heading() }.testTag("questionTitle"))
        q.helper?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp)) }
        Box(Modifier.size(14.dp))
        if (other) {
            val shape = RoundedCornerShape(14.dp)
            BasicTextField(
                value = otherText, onValueChange = { otherText = it.take(200) }, singleLine = true, textStyle = MaterialTheme.typography.bodyLarge.copy(color = Vmk.colors.text), cursorBrush = SolidColor(Vmk.colors.primary),
                modifier = Modifier.fillMaxWidth().testTag("questionOther"),
                decorationBox = { inner -> Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(shape).background(Vmk.colors.surfaceRaised).border(2.dp, Vmk.colors.primary, shape).padding(horizontal = 16.dp), contentAlignment = Alignment.CenterStart) { if (otherText.isEmpty()) Text("Type your answer", color = Vmk.colors.textTertiary); inner() } },
            )
            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = { other = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Back", color = Vmk.colors.textSecondary) }
                TextButton(onClick = { composer.answerOther(otherText) }, enabled = otherText.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp).testTag("questionOtherDone")) { Text("Done", fontWeight = FontWeight.Bold) }
            }
        } else FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            q.options.forEachIndexed { i, o ->
                val sel = picked == o.id || ((current as? com.videomk.app.core.Answer.Option)?.option == o.id && picked == null)
                AnswerChip(o.label, sel, "${o.label}, ${i + 1} of ${q.options.size}", Modifier.testTag("answer-${o.id}")) { picked = o.id }
            }
            if (q.allowOther) AnswerChip("Other...", false, "Other, type your own answer", Modifier.testTag("answer-other"), dashed = true) { other = true }
            AnswerChip("You decide", false, "You decide", Modifier.testTag("answer-decide"), icon = true) { composer.youDecide() }
        }
    }
}

@Composable
private fun AnswerChip(label: String, selected: Boolean, description: String, modifier: Modifier, dashed: Boolean = false, icon: Boolean = false, onClick: () -> Unit) {
    val dash = Vmk.colors.outline
    Row(
        modifier.heightIn(min = 50.dp).clip(CircleShape).background(if (selected) Vmk.colors.primaryContainer else if (dashed) Color.Transparent else Vmk.colors.surfaceRaised)
            .then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, CircleShape) else Modifier)
            .then(if (dashed) Modifier.drawBehind { drawRoundRect(dash, cornerRadius = CornerRadius(size.height / 2), style = Stroke(2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)))) } else Modifier)
            .clickable(role = Role.RadioButton, onClick = onClick).padding(horizontal = 20.dp)
            .semantics { this.selected = selected; contentDescription = description },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        if (icon) Icon(Icons.Filled.AutoAwesome, null, tint = Vmk.colors.text, modifier = Modifier.size(18.dp))
        Text(label, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = if (selected) Vmk.colors.primary else if (dashed) Vmk.colors.textSecondary else Vmk.colors.text)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun androidx.compose.foundation.layout.ColumnScope.SummaryBody(composer: ComposerViewModel, balance: Int?, options: CreateOptions, onWallet: () -> Unit) {
    val f = composer.flow ?: return
    val version = composer.flowVersion
    val chips = f.chips(composer.summaryBrief?.get("summary")?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content })
    val status = ComposerLogic.status(composer.text, options, balance, 0, false, false, createScreen = true)
    Row(Modifier.fillMaxWidth().heightIn(min = 52.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("Ready when you are", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() }.testTag("summaryTitle"))
        TextButton(onClick = { composer.dismissSheet() }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Close", color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
    }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Vmk.colors.primaryContainer).padding(16.dp)) {
        Overline("Your request")
        Text(composer.text, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, maxLines = 4, modifier = Modifier.padding(top = 4.dp))
    }
    FlowRow(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (c in chips) Row(
            Modifier.heightIn(min = 44.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button, onClickLabel = "Change this answer") { composer.editAnswer(c.questionId) }.padding(horizontal = 16.dp).testTag("summaryChip"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) { Text(c.label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary); Icon(Icons.Filled.Edit, null, tint = Vmk.colors.primary, modifier = Modifier.size(14.dp)) }
    }
    Text("Tap an answer to change it.", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 6.dp))
    Box(Modifier.fillMaxWidth().padding(vertical = 12.dp).size(1.dp).background(Vmk.colors.outline))
    Text("${CreatePlatforms.recommendation(options, composer.caps)} · ${options.minutes.toInt()} min", style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
    Box(Modifier.weight(1f, fill = false).heightIn(min = 16.dp))
    StatusLine(status, 0f, 0f) { if (status.fix?.addCredits == true) onWallet() else status.fix?.minutes?.let { composer.updateOptions(options.copy(minutes = it.toDouble())) } }
    val ready = status.sendReady
    Box(
        Modifier.fillMaxWidth().padding(top = 6.dp).heightIn(min = 54.dp).clip(CircleShape).then(if (ready) Modifier.background(Vmk.gradientNow) else Modifier.background(Vmk.colors.surface3))
            .clickable(enabled = ready, role = Role.Button) { composer.confirmSummary() }.testTag("summaryCreate"),
        contentAlignment = Alignment.Center,
    ) {
        val c = if (ready) Color.White else Vmk.colors.textTertiary
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Create video", style = MaterialTheme.typography.titleMedium.copy(fontSize = 19.sp), fontWeight = FontWeight.Bold, color = c); Text("·", color = c)
            Icon(Icons.Filled.Bolt, null, tint = c, modifier = Modifier.size(20.dp)); Text("${options.credits}", style = MaterialTheme.typography.titleMedium.copy(fontSize = 19.sp), fontWeight = FontWeight.Bold, color = c)
        }
    }
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        TextButton(onClick = { composer.dismissSheet() }, modifier = Modifier.heightIn(min = 48.dp).testTag("editRequest")) { Text("Edit request", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold) }
    }
    if (version < 0) Box(Modifier)   // read above so the summary refreshes after an edit
}

@Composable
private fun androidx.compose.foundation.layout.ColumnScope.StopBody(composer: ComposerViewModel, stop: CreateStop) {
    val (title, message, suggestion, retry) = when (stop) {
        is CreateStop.NotSupported -> StopText("We can't make this one", stop.message, stop.suggestion, null)
        is CreateStop.Blocked -> StopText("We can't make this one", stop.message, null, null)
        is CreateStop.Paused -> StopText("Creating videos is paused", stop.message, null, CreateErrors.retryText(stop.retryAfterSeconds))
    }
    Column(Modifier.fillMaxWidth().padding(top = 12.dp)) {
        Box(Modifier.size(56.dp).clip(CircleShape).background(Vmk.colors.warningContainer), contentAlignment = Alignment.Center) { Icon(Icons.Filled.Warning, null, tint = Vmk.colors.warning, modifier = Modifier.size(28.dp)) }
        Text(title, style = MaterialTheme.typography.headlineMedium.copy(fontSize = 28.sp), fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.padding(top = 14.dp).semantics { heading() }.testTag("stopTitle"))
        Text(message, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 6.dp).semantics { liveRegion = LiveRegionMode.Polite }.testTag("stopMessage"))
        retry?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 6.dp)) }
        if (suggestion != null) Row(Modifier.fillMaxWidth().padding(top = 14.dp).clip(RoundedCornerShape(18.dp)).background(Vmk.colors.primaryContainer).padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f)) { Overline("For example"); Text(suggestion, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text) }
            Text("Use this", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.primary, modifier = Modifier.clip(CircleShape).background(Vmk.colors.surface).clickable(role = Role.Button) { composer.useSuggestion(suggestion) }.padding(horizontal = 14.dp, vertical = 10.dp).testTag("useSuggestion"))
        }
        Text("Nothing was charged.", style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 12.dp, bottom = 8.dp).testTag("nothingCharged"))
        Box(Modifier.weight(1f, fill = false))
        PrimaryButton("Edit request", { composer.dismissSheet() }, Modifier.testTag("editRequest"))
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { TextButton(onClick = { composer.dismissSheet() }, modifier = Modifier.heightIn(min = 48.dp).testTag("stopClose")) { Text("Close", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.textSecondary) } }
    }
}

private data class StopText(val title: String, val message: String, val suggestion: String?, val retry: String?)
