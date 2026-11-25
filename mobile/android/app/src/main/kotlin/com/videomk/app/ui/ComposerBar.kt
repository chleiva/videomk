package com.videomk.app.ui

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.union
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.GraphicEq
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.PhotoAlbum
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.videomk.app.core.Brief
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.MediaLabels
import com.videomk.app.core.PhotoCapacity
import com.videomk.app.core.PhotoIntake
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.VideoLook
import com.videomk.app.data.DictationController
import kotlinx.coroutines.delay

private fun plural(n: Int) = if (n == 1) "" else "s"

/**
 * The "ask for a video" bar pinned to the bottom of the home screen: type or dictate, optionally set length and look, send.
 * Sending never leaves the screen; the new video appears as a row in the list above.
 */
@Composable
fun ComposerBar(composer: ComposerViewModel, balance: Int?, onSend: () -> Unit, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val dictationState by composer.dictation.state.collectAsState()
    val listening = dictationState is DictationController.State.Listening || dictationState is DictationController.State.Starting
    val text = composer.text
    val options = composer.options
    val credits = options.credits
    val affordable = balance == null || credits <= balance
    val valid = Brief.isValid(text)
    val canSend = valid && affordable
    val count = Brief.normalized(text).length
    val focus = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current

    LaunchedEffect(composer.focusRequests) {
        if (composer.focusRequests > 0) { runCatching { focus.requestFocus() }; keyboard?.show() }
    }
    LaunchedEffect(dictationState) {
        if (dictationState is DictationController.State.Unavailable || dictationState is DictationController.State.KeyboardHint) {
            delay(8000); composer.dictation.clearHint()
        }
    }

    val micPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        composer.dictation.start(composer.text, if (granted) DictationPlan.Permission.Granted else DictationPlan.Permission.Denied)
    }
    // the system picker has its own maximum per pick (MediaStore.getPickImagesMaxLimit()): choose in several rounds up to PhotoLimits.MAX_PHOTOS in total
    val platformMax = remember {
        if (ActivityResultContracts.PickVisualMedia.isPhotoPickerAvailable(context)) {
            runCatching { MediaStore.getPickImagesMaxLimit() }.getOrDefault(PhotoLimits.MAX_PHOTOS)
        } else PhotoLimits.MAX_PHOTOS
    }
    val pickMax = PhotoIntake.pickerMax(platformMax, composer.remaining)
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(pickMax)) { uris ->
        if (uris.isNotEmpty()) composer.addPhotos(context.contentResolver, uris)
    }

    // the user's own gallery app, Google Photos and Files side by side (a chooser around ACTION_GET_CONTENT); the system photo picker is only the fallback
    fun getContentIntent() = Intent(Intent.ACTION_GET_CONTENT).apply {
        type = "image/*"
        addCategory(Intent.CATEGORY_OPENABLE)
        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    val chooser = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val data = result.data
        if (result.resultCode == Activity.RESULT_OK && data != null) {
            val clip = data.clipData?.let { c -> (0 until c.itemCount).mapNotNull { c.getItemAt(it).uri } } ?: emptyList()
            val uris = PhotoIntake.extract(data.data, clip)
            // keep access past this screen where the provider allows it (a rotation destroys the temporary grant)
            uris.forEach { runCatching { context.contentResolver.takePersistableUriPermission(it, Intent.FLAG_GRANT_READ_URI_PERMISSION) } }
            if (uris.isNotEmpty()) composer.addPhotos(context.contentResolver, uris)
        }
    }
    fun launchPhotoSource() {
        val intent = getContentIntent()
        val handled = try { context.packageManager.queryIntentActivities(intent, 0).isNotEmpty() } catch (e: Exception) { false }
        try {
            if (handled) chooser.launch(Intent.createChooser(intent, "Choose photos"))
            else picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
        } catch (e: Exception) { /* no way to pick photos on this device */ }
    }

    val container = LocalContainerOrNull.current
    var myMedia by remember { mutableStateOf(false) }
    if (myMedia && container?.mediaApi != null) MyMediaPicker(composer, container.mediaApi!!, onDone = { myMedia = false }, tracker = container.mediaUploads?.arrivals)

    fun onMic() {
        try {
            if (composer.dictation.isListening) { composer.dictation.stop(); return }
            if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                composer.dictation.start(composer.text, DictationPlan.Permission.Granted)
            } else {
                micPermission.launch(Manifest.permission.RECORD_AUDIO)   // answers at once (as denied) when the user chose "don't ask again"
            }
        } catch (e: Exception) {
            composer.dictation.start(composer.text, DictationPlan.Permission.Denied)
        }
    }

    Surface(
        modifier = modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.navigationBars.union(WindowInsets.ime)),
        color = Vmk.colors.surface, shadowElevation = 6.dp,
    ) {
        Column(Modifier.padding(top = 8.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val hintMod = Modifier.fillMaxWidth().padding(horizontal = 20.dp)
            when (val s = dictationState) {
                is DictationController.State.Unavailable ->
                    HintLine(s.message, Icons.Filled.MicOff, Vmk.colors.warning, hintMod.testTag("dictationUnavailable"))
                is DictationController.State.KeyboardHint ->
                    HintLine(s.message, Icons.Filled.Keyboard, Vmk.colors.textSecondary, hintMod.testTag("dictationKeyboardHint"))
                else -> Unit
            }
            when {
                listening -> HintLine("Listening… tap the microphone when you're done", Icons.Filled.GraphicEq, Vmk.colors.textSecondary, hintMod.testTag("listeningHint"))
                valid && !affordable -> HintLine(
                    "This video needs $credits credit${plural(credits)} and you have $balance. Choose a shorter length.",
                    null, Vmk.colors.warning, hintMod.testTag("notEnoughCredits"),
                )
                text.isNotEmpty() && !valid -> Text(
                    if (count > Brief.MAX_LENGTH) "$count / ${Brief.MAX_LENGTH}: please shorten it." else "A few more words, please (${Brief.MIN_LENGTH - count} to go).",
                    style = MaterialTheme.typography.bodySmall, color = if (count > Brief.MAX_LENGTH) Vmk.colors.danger else Vmk.colors.textSecondary, modifier = hintMod,
                )
                valid -> Text(
                    "$credits credit${plural(credits)}${balance?.let { " · you have $it" } ?: ""}",
                    style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = hintMod.testTag("costLine"),
                )
            }

            if (composer.photos.isNotEmpty() || composer.loading > 0 || composer.library.isNotEmpty()) AttachedPhotosStrip(composer, options.minutes)

            Row(Modifier.padding(horizontal = 12.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OptionsMenu(options, onChange = { composer.options = it })
                Row(
                    Modifier.weight(1f)
                        .clip(RoundedCornerShape(24.dp)).background(Vmk.colors.background)
                        .border(1.dp, if (listening) Vmk.colors.danger.copy(alpha = 0.6f) else Vmk.colors.textSecondary.copy(alpha = 0.25f), RoundedCornerShape(24.dp)),
                    verticalAlignment = Alignment.Bottom,
                ) {
                    TextField(
                        value = text, onValueChange = { composer.text = it },
                        modifier = Modifier.weight(1f).focusRequester(focus).testTag("composerField"),
                        placeholder = { Text(if (composer.photos.isEmpty()) "Describe a video…" else "What should the video be about?") },
                        maxLines = 5,
                        keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences),
                        colors = TextFieldDefaults.colors(
                            focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent, disabledContainerColor = Color.Transparent,
                            focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent, disabledIndicatorColor = Color.Transparent,
                        ),
                    )
                    val full = composer.remaining == 0
                    IconButton(
                        onClick = {
                            launchPhotoSource()
                        },
                        enabled = !full, modifier = Modifier.size(48.dp).testTag("photoButton"),
                    ) {
                        Icon(Icons.Filled.PhotoLibrary, contentDescription = if (full) "Photo limit reached: ${PhotoLimits.MAX_PHOTOS} photos" else "Add photos. Choose up to ${composer.remaining} more of your photos to use in the video (${PhotoLimits.MAX_PHOTOS} at most)",
                            tint = if (full) Vmk.colors.textSecondary else MaterialTheme.colorScheme.primary)
                    }
                    if (container?.mediaApi != null) IconButton(onClick = { myMedia = true }, enabled = composer.libraryRoom > 0, modifier = Modifier.size(48.dp).testTag("myMediaButton")) {
                        Icon(Icons.Filled.PhotoAlbum, contentDescription = "My media. Choose photos from your private library for this video", tint = MaterialTheme.colorScheme.primary)
                    }
                    IconButton(onClick = ::onMic, modifier = Modifier.size(48.dp).testTag("micButton")) {
                        Icon(
                            if (listening) Icons.Filled.GraphicEq else Icons.Filled.Mic,
                            contentDescription = if (listening) "Stop dictation" else "Dictate. Say what video you want instead of typing",
                            tint = if (listening) Vmk.colors.danger else MaterialTheme.colorScheme.primary,
                        )
                    }
                }
                if (canSend) {
                    IconButton(
                        onClick = onSend,
                        modifier = Modifier.size(48.dp).clip(CircleShape).background(Vmk.gradient).testTag("sendButton"),
                    ) { Icon(Icons.Filled.ArrowUpward, contentDescription = "Make video", tint = Color.White) }
                }
            }
        }
    }
}

@Composable
private fun HintLine(message: String, icon: androidx.compose.ui.graphics.vector.ImageVector?, color: Color, modifier: Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        if (icon != null) Icon(icon, null, tint = color, modifier = Modifier.size(16.dp))
        Text(message, style = MaterialTheme.typography.bodySmall, color = color)
    }
}

@Composable
private fun OptionsMenu(options: CreateOptions, onChange: (CreateOptions) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Box {
        Column(
            Modifier.defaultMinSize(minWidth = 48.dp, minHeight = 48.dp).clip(RoundedCornerShape(24.dp)).background(Vmk.colors.background).border(1.dp, Vmk.colors.textSecondary.copy(alpha = 0.25f), RoundedCornerShape(24.dp))
                .clickable(onClickLabel = "Choose length and look") { open = true }.padding(horizontal = 4.dp)
                .semantics {
                    contentDescription = "Video options"
                    stateDescription = "${options.minutes.toInt()} minutes, ${options.credits} credits, ${options.look?.title ?: "Producer decides the look"}, subtitles ${if (options.captions) "on" else "off"}"
                }
                .testTag("optionsMenu"),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
        ) {
            Icon(Icons.Filled.Tune, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
            Text("${options.minutes.toInt()} min", fontSize = 10.sp, color = MaterialTheme.colorScheme.primary)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            Text("Length", style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
            for (m in CreateOptions.LENGTHS) {
                MenuChoice("${m.toInt()} minute${plural(m.toInt())}", "${CreateOptions(m).credits} credit${plural(CreateOptions(m).credits)}", options.minutes == m, "length-${m.toInt()}") {
                    onChange(options.copy(minutes = m)); open = false
                }
            }
            Text("Look", style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
            MenuChoice("Producer decides", null, options.look == null, "look-auto") { onChange(options.copy(look = null)); open = false }
            for (l in VideoLook.entries) MenuChoice(l.title, null, options.look == l, "look-${l.wire}") { onChange(options.copy(look = l)); open = false }
            DropdownMenuItem(
                text = { Text("Subtitles") },
                trailingIcon = { Switch(checked = options.captions, onCheckedChange = null) },
                onClick = { onChange(options.copy(captions = !options.captions)) },   // the menu stays open so the switch can be seen changing
                modifier = Modifier.heightIn(min = 48.dp).semantics { stateDescription = if (options.captions) "on" else "off" },
            )
        }
    }
}

@Composable
private fun MenuChoice(label: String, detail: String?, selected: Boolean, tag: String, onClick: () -> Unit) {
    DropdownMenuItem(
        text = {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(label)
                if (detail != null) Text(detail, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
            }
        },
        leadingIcon = { if (selected) Icon(Icons.Filled.Check, "Selected") else Box(Modifier.size(24.dp)) },
        onClick = onClick, modifier = Modifier.heightIn(min = 48.dp).testTag(tag),
    )
}

/** The strip of attached photos above the text field: a lazy row of small previews (only the visible ones are composed), so 100 photos stay smooth. */
@Composable
private fun AttachedPhotosStrip(composer: ComposerViewModel, minutes: Double) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        LazyRow(contentPadding = PaddingValues(horizontal = 20.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            itemsIndexed(composer.photos, key = { _, p -> p.id }) { index, photo ->
                Box(Modifier.size(64.dp).semantics { contentDescription = "Photo ${index + 1} of ${composer.photos.size}" }.testTag("attachedPhoto")) {
                    photo.thumbnail?.let {
                        Image(it.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.size(56.dp).align(Alignment.BottomStart).clip(RoundedCornerShape(10.dp)))
                    }
                    Box(
                        Modifier.align(Alignment.TopEnd).size(48.dp)
                            .clickable(onClickLabel = "Remove photo ${index + 1}") { composer.removePhoto(photo.id) },
                        contentAlignment = Alignment.TopEnd,
                    ) {
                        Box(Modifier.padding(top = 2.dp, end = 2.dp).size(24.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.7f)), contentAlignment = Alignment.Center) {
                            Icon(Icons.Filled.Close, "Remove photo ${index + 1}", tint = Color.White, modifier = Modifier.size(16.dp))
                        }
                    }
                }
            }
            itemsIndexed(composer.library, key = { _, p -> "lib-${p.id}" }) { index, photo ->
                Box(Modifier.size(64.dp).semantics { contentDescription = "From My media: ${MediaLabels.photo(photo)}" }.testTag("attachedLibraryPhoto")) {
                    PhotoThumb(photo, Modifier.size(56.dp).align(Alignment.BottomStart).clip(RoundedCornerShape(10.dp)))
                    Box(
                        Modifier.align(Alignment.TopEnd).size(48.dp).clickable(onClickLabel = "Remove from the video") { composer.removeLibrary(photo.id) },
                        contentAlignment = Alignment.TopEnd,
                    ) {
                        Box(Modifier.padding(top = 2.dp, end = 2.dp).size(24.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.7f)), contentAlignment = Alignment.Center) {
                            Icon(Icons.Filled.Close, "Remove from the video", tint = Color.White, modifier = Modifier.size(16.dp))
                        }
                    }
                }
            }
            if (composer.loading > 0) item(key = "preparing") {   // one placeholder, however many are still being prepared
                Box(Modifier.size(64.dp).padding(4.dp).clip(RoundedCornerShape(10.dp)).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                }
            }
        }
        if (composer.loading > 0) {
            Text(
                composer.preparingText, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary,
                modifier = Modifier.padding(horizontal = 20.dp).testTag("photosPreparing"),
            )
        }
        composer.notice?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.padding(horizontal = 20.dp).testTag("photosNotice"))
        }
        Text(
            "${composer.photos.size + composer.library.size} of ${PhotoLimits.MAX_PHOTOS} photos. Tell me what to do with them. Location data is removed, and the originals are deleted once your video is made.",
            style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 20.dp).testTag("photosNote"),
        )
        // not blocking: sending is still allowed; recomputed on every length change and every removal
        PhotoCapacity.hint(composer.totalPhotos, minutes, CreateOptions.LENGTHS.map { it.toInt() })?.let { hint ->
            Text(
                hint, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning,
                modifier = Modifier.padding(horizontal = 20.dp).semantics { contentDescription = "Video length tip. $hint" }.testTag("photoCapacityHint"),
            )
        }
    }
}
