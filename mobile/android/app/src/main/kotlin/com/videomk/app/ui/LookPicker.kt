package com.videomk.app.ui

import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.disabled
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.videomk.app.R
import com.videomk.app.core.CastCaps
import com.videomk.app.core.CastMember
import com.videomk.app.core.DataUri
import com.videomk.app.core.DesignTokens
import com.videomk.app.core.LookExtra
import com.videomk.app.core.LookOption
import com.videomk.app.core.LookRules
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/*
 * The Look of a video, chosen by its picture (docs/CREATE_API.md, "Video look (chosen and enforced)"), in two small sheets that each do one thing: the same
 * design as the iPhone app after its expert review. Words, faces and limits are the server's. Selection is one ring and nothing else (no tick, no recoloured
 * label). A look the plan does not include, or that is not made from the attached photos or slides, stays in place, dimmed, with its reason where the note was;
 * only a look this stage does not have is hidden.
 */

private val Ring = 2.5.dp
private val RingGap = 4.dp

/** The head of a sheet stays; only what is under it scrolls (and only when it has to: large text, a small phone). */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
private fun PickerSheet(title: String, tag: String, closeTag: String, onDismiss: () -> Unit, content: @Composable (close: () -> Unit) -> Unit) {
    val state = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val scope = rememberCoroutineScope()
    // closing from inside (a pick, the close icon) slides the sheet away like a swipe does, then tells Create
    val close: () -> Unit = { scope.launch { runCatching { state.hide() } }.invokeOnCompletion { onDismiss() } }
    ModalBottomSheet(
        onDismissRequest = onDismiss, sheetState = state,
        shape = RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet), containerColor = Vmk.colors.surface,
    ) {
        Column(Modifier.fillMaxWidth().navigationBarsPadding().semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag(tag)) {
            SheetHeader(title, close, Modifier.padding(horizontal = Vmk.space.sheet), closeTag = closeTag, closeLabel = stringResource(R.string.common_done))
            // the gutter is inside the scrolling part, so the ring of a chosen picture (drawn outside it) is never cut by the scroll's own edge
            Column(Modifier.weight(1f, fill = false).verticalScroll(rememberScrollState()).padding(horizontal = Vmk.space.sheet).padding(top = Vmk.space.m, bottom = Vmk.space.xxl)) { content(close) }
        }
    }
}

/**
 * The Look sheet: the four tiles and nothing else, always the same height. One tap chooses and the sheet steps aside after a beat (so the ring is seen), for
 * every look. A look with characters shows its Characters pill on Create. With TalkBack the sheet stays: "selected" is heard first and the person closes it.
 */
@Composable
fun LookSheet(composer: ComposerViewModel, onDismiss: () -> Unit) {
    val looks = composer.caps.lookPicker ?: return
    val haptics = rememberHaptics()
    val view = LocalView.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    PickerSheet(stringResource(R.string.create_look), "lookSheet", "lookDone", onDismiss) { close ->
        LookTiles(LookRules.tiles(looks, composer.attached), composer.options.lookChoice.look) { tile ->
            haptics.play(DesignTokens.Haptic.Selection)
            if (tile.locked) return@LookTiles          // a dimmed tile answers softly and changes nothing
            composer.pickLook(tile.id)?.let { view.announceForAccessibility(it) }      // the look needs a longer video: the length was moved, Create says so above the pills
            if (!touchExploration(context)) scope.launch { delay(320); close() }
        }
    }
}

/** The Characters sheet of a look that has them: the faces, the one line, the board switch. It stays until it is closed. */
@Composable
fun CharactersSheet(composer: ComposerViewModel, onDismiss: () -> Unit) {
    val looks = composer.caps.lookPicker ?: return
    val choice = composer.options.lookChoice
    val option = looks.option(choice.look)
    val cast = looks.cast?.takeIf { option?.cast == true && it.available && it.members.isNotEmpty() }
    val extras = option?.extras?.filter { it.available }.orEmpty()
    val haptics = rememberHaptics()
    val view = LocalView.current
    var lengthLine by remember { mutableStateOf<String?>(null) }      // for this visit: a conversation moved the length
    PickerSheet(stringResource(R.string.looks_cast), "castSheet", "castDone", onDismiss) {
        Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
            if (cast != null) {
                val full = LookRules.castIsFull(choice, looks)
                val scale = androidx.compose.ui.platform.LocalDensity.current.fontScale
                // five across; fewer only where a name at this text size would not fit its face (the largest text: four, three on a small phone)
                androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxWidth()) {
                    val gap = if (scale >= 1.5f) Vmk.space.m else Vmk.space.s
                    val columns = ((maxWidth + gap) / (40.dp * maxOf(1f, scale) + gap)).toInt().coerceIn(3, 5)
                    FaceGrid(cast.grouped, columns, gap) { m ->
                        val selected = m.id in choice.cast
                        FaceCell(m, selected, inert = full && !selected) {
                            val (tap, line) = composer.toggleCast(m.id)
                            if (tap != LookRules.CastTap.Full) haptics.play(DesignTokens.Haptic.Selection)
                            if (line != null) { lengthLine = line; view.announceForAccessibility(line) }
                        }
                    }
                }
                val line = lengthLine ?: LookRules.castLine(choice, looks)
                Text(line, style = MaterialTheme.typography.bodySmall, color = if (lengthLine == null) Vmk.colors.textSecondary else Vmk.colors.text, modifier = Modifier.fillMaxWidth().semantics { liveRegion = LiveRegionMode.Polite }.testTag("castLine"))
            }
            for (extra in extras) ExtraSwitch(extra, extra.id in choice.extras) { on -> haptics.play(DesignTokens.Haptic.Selection); composer.setLookExtra(extra.id, on) }
        }
    }
}

private fun touchExploration(context: android.content.Context): Boolean =
    runCatching { (context.getSystemService(android.content.Context.ACCESSIBILITY_SERVICE) as android.view.accessibility.AccessibilityManager).isTouchExplorationEnabled }.getOrDefault(false)

// ---- tiles

/** The looks as pictures, two across. At large text they are rows (a small picture, the name beside it), so all four fit one screen. */
@Composable
fun LookTiles(tiles: List<LookRules.Tile>, selected: String, onPick: (LookRules.Tile) -> Unit) {
    if (isLargeText()) Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.m)) { for (t in tiles) LookTile(t, selected == t.id, row = true, Modifier.fillMaxWidth(), onPick) }
    else Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
        for (pair in tiles.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
            for (t in pair) LookTile(t, selected == t.id, row = false, Modifier.weight(1f), onPick)
            if (pair.size == 1) Spacer(Modifier.weight(1f))
        }
    }
}

@Composable
private fun LookTile(tile: LookRules.Tile, chosen: Boolean, row: Boolean, modifier: Modifier, onPick: (LookRules.Tile) -> Unit) {
    val o = tile.option
    val why = LookRules.reason(tile)
    val note = LookRules.note(o)
    val spoken = listOfNotNull(o.label, why ?: note).joinToString(", ")
    val source = remember { MutableInteractionSource() }
    val words: @Composable () -> Unit = {
        Column(Modifier.clearAndSetSemantics { }, verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(o.label, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, maxLines = if (row) 2 else 1, overflow = TextOverflow.Ellipsis)
            if (why != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.xs)) {
                if (tile.blocked == LookRules.Block.Plan) Icon(Sym.Lock, null, tint = Vmk.colors.text, modifier = Modifier.size(with(androidx.compose.ui.platform.LocalDensity.current) { 12.sp.toDp() }))
                // the whole tile is at 40 percent: the reason starts from the text colour so it stays readable
                Text(why, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.text, maxLines = if (row) 2 else 1, overflow = TextOverflow.Ellipsis)
            } else if (!row && note != null) Text(note, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
    val base = modifier.testTag("lookTile-${o.id}").pressScale(source)
    // "You cannot have this" has one look: in place, dimmed, with the reason where the note was. TalkBack says it is not available; a tap changes nothing.
    val behaviour = if (tile.locked) base.alpha(0.4f).clickable(interactionSource = source, indication = null, role = Role.RadioButton) { onPick(tile) }.semantics(mergeDescendants = true) { contentDescription = spoken; disabled() }
        else base.selectable(selected = chosen, interactionSource = source, indication = null, role = Role.RadioButton) { onPick(tile) }.semantics(mergeDescendants = true) { contentDescription = spoken }
    if (row) Row(behaviour.heightIn(min = Vmk.minTouch), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.l)) { LookPicture(o, chosen, row = true, Modifier.size(96.dp, 60.dp)); Box(Modifier.weight(1f)) { words() } }
    else Column(behaviour, verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) { LookPicture(o, chosen, row = false, Modifier.fillMaxWidth().aspectRatio(1.6f)); words() }
}

/**
 * The picture of a look, on the gutter: the server's preview cropped to the tile with a hairline edge (a white picture still has one on a white sheet).
 * Auto has no photograph: it is the brand tint with the sparkle of "we choose", as everywhere else. Chosen: one ring around it, outside the picture.
 */
@Composable
private fun LookPicture(o: LookOption, selected: Boolean, row: Boolean, modifier: Modifier) {
    val radius = if (row) Vmk.radii.thumb else Vmk.radii.card
    val shape = RoundedCornerShape(radius)
    val ring = Vmk.colors.primary
    val image = remember(o.preview) { if (o.isAuto) null else InlineImage.image(o.preview) }
    Box(
        modifier.drawBehind {
            if (selected) {
                val g = RingGap.toPx(); val w = Ring.toPx()
                drawRoundRect(ring, Offset(-g + w / 2, -g + w / 2), Size(size.width + 2 * g - w, size.height + 2 * g - w), CornerRadius(radius.toPx() + g - w / 2), style = Stroke(w))
            }
        }.clip(shape).background(if (o.isAuto) Vmk.colors.primaryContainer else Vmk.colors.surfaceRaised).border(1.dp, Vmk.colors.text.copy(alpha = 0.08f), shape).clearAndSetSemantics { },
        contentAlignment = Alignment.Center,
    ) {
        when {
            o.isAuto -> Icon(Sym.AutoAwesome, null, tint = Vmk.colors.primary, modifier = Modifier.size(if (row) 22.dp else 30.dp))
            image != null -> Image(image, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
            else -> Box(Modifier.fillMaxSize().background(Vmk.makingGradient), contentAlignment = Alignment.Center) {
                Icon(when (o.id) { "real" -> Sym.Image; "whiteboard" -> Sym.Edit; "cartoon" -> Sym.Person; else -> Sym.Movie }, null, tint = Color.White.copy(alpha = 0.9f), modifier = Modifier.size(if (row) 22.dp else 30.dp))
            }
        }
    }
}

// ---- cast

/** Rows of equal cells, edge to edge: ten faces five across (people, then animals); four across at larger text, three at the largest. */
@Composable
private fun FaceGrid(members: List<CastMember>, columns: Int, gap: Dp, cell: @Composable (CastMember) -> Unit) {
    Column(Modifier.testTag("castGrid"), verticalArrangement = Arrangement.spacedBy(Vmk.space.m)) {
        for (rowMembers in members.chunked(columns)) Row(horizontalArrangement = Arrangement.spacedBy(gap)) {
            for (m in rowMembers) Box(Modifier.weight(1f)) { cell(m) }
            repeat(columns - rowMembers.size) { Spacer(Modifier.weight(1f)) }
        }
    }
}

/**
 * A face and its name. Chosen: a ring drawn on the edge of the face itself, so no face is ever larger or smaller than its neighbours and the first one sits
 * on the gutter. The name never changes colour or weight. At the limit the faces that are not chosen are dimmed and do nothing.
 */
@Composable
private fun FaceCell(m: CastMember, selected: Boolean, inert: Boolean, onTap: () -> Unit) {
    val source = remember { MutableInteractionSource() }
    val ring = Vmk.colors.primary; val gap = Vmk.colors.surface
    val spoken = listOfNotNull(m.name, m.role, m.topic).joinToString(", ")
    Column(
        Modifier.fillMaxWidth().heightIn(min = Vmk.minTouch).alpha(if (inert) 0.4f else 1f).pressScale(source)
            .toggleable(value = selected, interactionSource = source, indication = null, enabled = !inert, role = Role.Checkbox) { onTap() }
            .semantics(mergeDescendants = true) { contentDescription = spoken }.testTag("cast-${m.id}"),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        CastFace(m, Modifier.fillMaxWidth().aspectRatio(1f).drawWithContent {
            drawContent()
            if (selected) {
                val outer = 4.5.dp.toPx(); val w = Ring.toPx()
                drawCircle(gap, radius = size.minDimension / 2 - outer / 2, style = Stroke(outer))
                drawCircle(ring, radius = size.minDimension / 2 - w / 2, style = Stroke(w))
            }
        })
        // a name is whole on one line at every text size: where it would not fit its column it is drawn a little smaller, never broken in two and never cut
        Text(m.name, style = MaterialTheme.typography.labelMedium, fontWeight = androidx.compose.ui.text.font.FontWeight.Normal, color = Vmk.colors.text, textAlign = TextAlign.Center, maxLines = 1, softWrap = false,
            autoSize = androidx.compose.foundation.text.TextAutoSize.StepBased(minFontSize = 8.sp, maxFontSize = MaterialTheme.typography.labelMedium.fontSize, stepSize = 1.sp), modifier = Modifier.fillMaxWidth().clearAndSetSemantics { })
    }
}

/** The face of a character: the server's drawing, or a plain mark when it sent none. */
@Composable
fun CastFace(m: CastMember, modifier: Modifier = Modifier) {
    val image = remember(m.thumbnail) { InlineImage.image(m.thumbnail) }
    Box(modifier.clip(CircleShape).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
        if (image != null) Image(image, null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        else Icon(Sym.Person, null, tint = Vmk.colors.textSecondary, modifier = Modifier.fillMaxSize(0.5f))
    }
}

/** One switch per extra the look allows (the board), labelled by the server. The whole row is the target. */
@Composable
private fun ExtraSwitch(extra: LookExtra, on: Boolean, onChange: (Boolean) -> Unit) {
    val stateOn = stringResource(R.string.create_state_on); val stateOff = stringResource(R.string.create_state_off)
    val spoken = listOfNotNull(extra.label, extra.note).joinToString(". ")
    Row(
        Modifier.fillMaxWidth().heightIn(min = 52.dp).toggleable(value = on, interactionSource = null, indication = null, role = Role.Switch, onValueChange = onChange)
            .semantics(mergeDescendants = true) { contentDescription = spoken; stateDescription = if (on) stateOn else stateOff }.testTag("extra-${extra.id}"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m),
    ) {
        Text(extra.label, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f).clearAndSetSemantics { })
        Switch(on, onCheckedChange = null, colors = vmkSwitchColors())
    }
}

/** The chosen characters in a pill: up to three small faces that overlap, in the order they were chosen. */
@Composable
fun PillFaces(members: List<CastMember>, modifier: Modifier = Modifier) {
    Row(modifier.clearAndSetSemantics { }, horizontalArrangement = Arrangement.spacedBy((-6).dp)) {
        for (m in members.take(3)) CastFace(m, Modifier.size(22.dp).border(1.5.dp, Vmk.colors.surfaceRaised, CircleShape).padding(1.dp))
    }
}

/** A tile or a face under the finger: a touch smaller, no grey flash. Reduced motion: nothing moves. */
@Composable
private fun Modifier.pressScale(source: MutableInteractionSource): Modifier {
    val pressed by source.collectIsPressedAsState()
    val still = reduceMotion(LocalContext.current)
    val scale by animateFloatAsState(if (pressed && !still) 0.97f else 1f, tween(DesignTokens.Motion.press), label = "press")
    return this.graphicsLayer { scaleX = scale; scaleY = scale; alpha = if (pressed) 0.85f else 1f }
}

/** Pictures the server sends inline (the look previews and the faces): decoded once, kept in memory. */
object InlineImage {
    private val cache = LruCache<String, ImageBitmap>(32)
    fun image(uri: String?): ImageBitmap? {
        uri ?: return null
        cache.get(uri)?.let { return it }
        val bytes = DataUri.bytes(uri) ?: return null
        val image = runCatching { BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap() }.getOrNull() ?: return null
        cache.put(uri, image)
        return image
    }
}
