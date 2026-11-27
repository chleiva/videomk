package com.videomk.app.ui

import androidx.compose.foundation.layout.Spacer
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import com.videomk.app.R
import androidx.compose.ui.res.stringResource
import com.videomk.app.core.ChipFit
import com.videomk.app.core.ChipLayout
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.semantics.clearAndSetSemantics
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
        // content height: a sheet is as tall as what it holds (the question sheet keeps a floor so it does not jump between questions)
        Column(Modifier.fillMaxWidth().heightIn(min = if (kind == ComposerViewModel.CreateSheetKind.Asking || kind == ComposerViewModel.CreateSheetKind.Checking) 300.dp else 0.dp).padding(horizontal = Vmk.space.sheet).navigationBarsPadding().padding(bottom = 12.dp).semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("createSheet")) {
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
        TextButton(onClick = { composer.skipCheck() }, modifier = Modifier.heightIn(min = 48.dp).testTag("makeItNow")) { Text(stringResource(R.string.question_skip_all), style = MaterialTheme.typography.titleMedium) }
    }
    val checkingText = stringResource(R.string.composer_checking)
    Column(Modifier.semantics { contentDescription = checkingText; liveRegion = LiveRegionMode.Polite }, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.fillMaxWidth(0.7f).heightIn(min = 34.dp).clip(RoundedCornerShape(10.dp)).background(Vmk.colors.surfaceRaised))
        Box(Modifier.fillMaxWidth(0.5f).heightIn(min = 18.dp).clip(RoundedCornerShape(8.dp)).background(Vmk.colors.surfaceRaised))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(top = 8.dp)) { repeat(3) { Box(Modifier.width(84.dp).heightIn(min = 50.dp).clip(CircleShape).background(Vmk.colors.surfaceRaised)) } }
        Text(checkingText, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 16.dp))
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
    val position = stringResource(R.string.question_position, f.index + 1, f.total)
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
        if (f.canGoBack) GlassIconButton(Sym.ArrowBack, stringResource(R.string.question_previous), { composer.questionBack() }, Modifier.testTag("questionBack"))
        else Box(Modifier.size(48.dp))
        Row(Modifier.weight(1f).clearAndSetSemantics { contentDescription = position }, horizontalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterHorizontally), verticalAlignment = Alignment.CenterVertically) {
            for (i in 0 until f.total) Box(Modifier.size(width = if (i == f.index) 22.dp else 8.dp, height = 8.dp).clip(CircleShape).background(if (i == f.index) Vmk.colors.primary else Vmk.colors.surface3))
        }
        // one tap starts the video with every remaining question left to us (rule 5: three taps to a first video)
        TextButton(onClick = { composer.makeItNow() }, modifier = Modifier.heightIn(min = 48.dp).testTag("makeItNow")) { Text(stringResource(R.string.question_skip_all), style = MaterialTheme.typography.titleMedium) }
    }
    Crossfade(version to f.index, animationSpec = tween(if (still) 0 else 280), label = "question", modifier = Modifier.weight(1f, fill = false)) { (_, idx) ->
        val question = f.questions.getOrNull(idx) ?: q
        QuestionContent(composer, question, f.overline(idx), f.answerOf(question.id))
    }
    val announce = stringResource(R.string.question_announce, f.index + 1, f.total, q.text)
    LaunchedEffect(f.index) { view.announceForAccessibility(announce) }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun QuestionContent(composer: ComposerViewModel, q: Question, overline: String, current: com.videomk.app.core.Answer?) {
    var picked by remember(q.id) { mutableStateOf<String?>(null) }
    var other by remember(q.id) { mutableStateOf(false) }
    var otherText by remember(q.id) { mutableStateOf("") }
    // a chip is shown selected, then the sheet moves on by itself after a beat (no Next button)
    LaunchedEffect(picked) { picked?.let { delay(250); composer.choose(it) } }
    // scrolls when the question and its chips are taller than the sheet (large text, a small phone): nothing is ever hidden
    Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(top = 4.dp)) {
        Text(q.text, style = VmkType.question, color = Vmk.colors.text, modifier = Modifier.padding(top = 4.dp).semantics { heading() }.testTag("questionTitle"))
        Box(Modifier.size(14.dp))
        if (other) {
            val shape = RoundedCornerShape(14.dp)
            BasicTextField(
                value = otherText, onValueChange = { otherText = it.take(200) }, singleLine = true, textStyle = MaterialTheme.typography.bodyLarge.copy(color = Vmk.colors.text), cursorBrush = SolidColor(Vmk.colors.primary),
                modifier = Modifier.fillMaxWidth().testTag("questionOther"),
                decorationBox = { inner -> Box(Modifier.fillMaxWidth().heightIn(min = 52.dp).clip(shape).background(Vmk.colors.surfaceRaised).border(2.dp, Vmk.colors.primary, shape).padding(horizontal = 16.dp), contentAlignment = Alignment.CenterStart) { if (otherText.isEmpty()) Text(stringResource(R.string.question_type_answer), color = Vmk.colors.textTertiary); inner() } },
            )
            Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.End) {
                TextButton(onClick = { other = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_back), color = Vmk.colors.textSecondary) }
                TextButton(onClick = { composer.answerOther(otherText) }, enabled = otherText.isNotBlank(), modifier = Modifier.heightIn(min = 48.dp).testTag("questionOtherDone")) { Text(stringResource(R.string.common_done), fontWeight = FontWeight.Bold) }
            }
        } else FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            q.options.forEachIndexed { i, o ->
                val sel = picked == o.id || ((current as? com.videomk.app.core.Answer.Option)?.option == o.id && picked == null)
                AnswerChip(o.label, sel, stringResource(R.string.question_chip_desc, o.label, i + 1, q.options.size), Modifier.testTag("answer-${o.id}")) { picked = o.id }
            }
            if (q.allowOther) AnswerChip(stringResource(R.string.question_other), false, stringResource(R.string.question_other_desc), Modifier.testTag("answer-other"), dashed = true) { other = true }
            AnswerChip(stringResource(R.string.question_you_decide), false, stringResource(R.string.question_you_decide), Modifier.testTag("answer-decide"), icon = true) { composer.youDecide() }
        }
    }
}

/** An answer chip: sizes to its text, wraps to two lines, or becomes a full-width row (three lines, then an ellipsis); the full text is always in its description. */
@Composable
private fun AnswerChip(label: String, selected: Boolean, description: String, modifier: Modifier, dashed: Boolean = false, icon: Boolean = false, onClick: () -> Unit) {
    val dash = Vmk.colors.outline
    androidx.compose.foundation.layout.BoxWithConstraints {
        val fit = ChipLayout.fit(label, maxWidth.value, LocalDensity.current.fontScale, extraDp = if (icon) 26f else 0f)
        val shape = if (fit == ChipFit.SingleLine) CircleShape else RoundedCornerShape(26.dp)
        Row(
            modifier.then(if (fit == ChipFit.FullWidth) Modifier.fillMaxWidth() else Modifier.widthIn(max = maxWidth)).heightIn(min = 50.dp).clip(shape)
                .background(if (selected) Vmk.colors.primaryContainer else if (dashed) Color.Transparent else Vmk.colors.surfaceRaised)
                .then(if (selected) Modifier.border(1.5.dp, Vmk.colors.primary, shape) else Modifier)
                .then(if (dashed) Modifier.drawBehind { drawRoundRect(dash, cornerRadius = CornerRadius(if (fit == ChipFit.SingleLine) size.height / 2 else 26.dp.toPx()), style = Stroke(2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)))) } else Modifier)
                .clickable(role = Role.RadioButton, onClick = onClick).padding(horizontal = 20.dp, vertical = 8.dp)
                .semantics { this.selected = selected; contentDescription = description },
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            if (icon) Icon(Sym.AutoAwesome, null, tint = Vmk.colors.text, modifier = Modifier.size(18.dp))
            Text(
                label, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = if (selected) Vmk.colors.primary else if (dashed) Vmk.colors.textSecondary else Vmk.colors.text,
                maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false),
            )
        }
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
        Text(stringResource(R.string.summary_title), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() }.testTag("summaryTitle"))
        GlassIconButton(Sym.Close, stringResource(R.string.summary_edit_request), { composer.dismissSheet() }, Modifier.testTag("editRequest"))
    }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(Vmk.colors.primaryContainer).padding(16.dp)) {
        Text(composer.text, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, maxLines = 4)
    }
    val changeAnswer = stringResource(R.string.summary_change_answer)
    FlowRow(Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (c in chips) Row(
            Modifier.widthIn(max = 600.dp).heightIn(min = 48.dp).clip(CircleShape).background(Vmk.colors.primaryContainer).clickable(role = Role.Button, onClickLabel = changeAnswer) { composer.editAnswer(c.questionId) }.padding(horizontal = 16.dp, vertical = 6.dp).semantics { contentDescription = "${c.label}. $changeAnswer" }.testTag("summaryChip"),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) { Text(c.label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false)); Icon(Sym.Edit, null, tint = Vmk.colors.primary, modifier = Modifier.size(14.dp)) }
    }
    Box(Modifier.weight(1f, fill = false).heightIn(min = 16.dp))
    StatusLine(status, 0f, 0f) { if (status.fix?.addCredits == true) onWallet() else status.fix?.minutes?.let { composer.setLength(it) } }
    val ready = status.sendReady
    Box(
        Modifier.fillMaxWidth().padding(top = 6.dp).heightIn(min = 54.dp).clip(CircleShape).then(if (ready) Modifier.background(Vmk.gradientNow) else Modifier.background(Vmk.colors.surface3))
            .clickable(enabled = ready, role = Role.Button) { composer.confirmSummary() }.testTag("summaryCreate"),
        contentAlignment = Alignment.Center,
    ) {
        val c = if (ready) Vmk.colors.onPrimary else Vmk.colors.textSecondary
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(stringResource(R.string.create_create_video), style = VmkType.cta, color = c, modifier = Modifier.weight(1f, fill = false)); Text("·", style = VmkType.cta, color = c)
            Icon(Sym.Bolt, null, tint = c, modifier = Modifier.size(20.dp)); Text("${options.credits}", style = VmkType.cta, color = c)
        }
    }
    if (version < 0) Box(Modifier)   // read above so the summary refreshes after an edit
}

/**
 * "We can't make this one", a pause, or a plan refusal: one icon, a title that says it, the server's own sentence (never drawn when it only repeats the title),
 * and ONE primary that can actually help: "Edit request" where editing helps, the shorter length where the plan's limit is the problem, "OK" for a pause.
 */
@Composable
private fun androidx.compose.foundation.layout.ColumnScope.StopBody(composer: ComposerViewModel, stop: CreateStop) {
    val t = when (stop) {
        is CreateStop.NotSupported -> StopText(stringResource(R.string.stop_title), stop.message, stop.suggestion, null)
        is CreateStop.Blocked -> StopText(stringResource(R.string.stop_title), stop.message, null, null)
        is CreateStop.Paused -> StopText(CreateErrors.pausedTitle(stop.retryAfterSeconds), stop.message, null, null)
        is CreateStop.Plan -> StopText(
            stringResource(when { stop.code == "free_budget_spent" -> R.string.stop_free_paused_title; stop.code.startsWith("free_") -> R.string.stop_free_unavailable_title; else -> R.string.stop_plan_title }),
            stop.message, null,
            stop.resumesAt?.let { stringResource(R.string.stop_resumes, com.videomk.app.core.PlanText.moment(it)) } ?: composer.caps.planName(stop.requiresPlan)?.let { stringResource(R.string.plan_coming_soon, it) },
        )
    }
    val calm = stop is CreateStop.Paused || stop is CreateStop.Plan
    Column(Modifier.fillMaxWidth().padding(top = 4.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(56.dp).clip(CircleShape).background(if (calm) Vmk.colors.primaryContainer else Vmk.colors.warningContainer), contentAlignment = Alignment.Center) { Icon(if (calm) Sym.HourglassTop else Sym.Warning, null, tint = if (calm) Vmk.colors.primary else Vmk.colors.warning, modifier = Modifier.size(28.dp)) }
            Spacer(Modifier.weight(1f))
            GlassIconButton(Sym.Close, stringResource(R.string.common_close), { composer.dismissSheet() }, Modifier.testTag("stopClose"))
        }
        Text(t.title, style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text, modifier = Modifier.padding(top = Vmk.space.l).semantics { heading() }.testTag("stopTitle"))
        if (!CreateErrors.repeats(t.title, t.message)) Text(t.message, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 6.dp).semantics { liveRegion = LiveRegionMode.Polite }.testTag("stopMessage"))
        t.extra?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 6.dp).testTag("stopExtra")) }
        if (t.suggestion != null) Row(Modifier.fillMaxWidth().padding(top = 14.dp).clip(RoundedCornerShape(Vmk.radii.card)).background(Vmk.colors.primaryContainer).padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t.suggestion, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            TonalButton(stringResource(R.string.stop_use_this), { composer.useSuggestion(t.suggestion) }, Modifier.testTag("useSuggestion"), onSurface = true)
        }
        Text(stringResource(R.string.stop_nothing_charged), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = Vmk.space.m, bottom = Vmk.space.l).testTag("nothingCharged"))
        val shorter = (stop as? CreateStop.Plan)?.shorterMinutes
        when {
            shorter != null -> PrimaryButton(stringResource(R.string.create_use_length, com.videomk.app.core.Lengths.short(shorter)), { composer.useShorter(shorter) }, Modifier.testTag("stopUseShorter"))
            calm -> PrimaryButton(stringResource(R.string.common_ok), { composer.dismissSheet() }, Modifier.testTag("stopOk"))
            else -> PrimaryButton(stringResource(R.string.summary_edit_request), { composer.dismissSheet() }, Modifier.testTag("editRequest"))
        }
    }
}

private data class StopText(val title: String, val message: String, val suggestion: String?, val extra: String?)
