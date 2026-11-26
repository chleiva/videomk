package com.videomk.app.ui

import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import android.provider.MediaStore
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.itemsIndexed
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.PhoneAndroid
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.videomk.app.core.AddPhotosLogic
import com.videomk.app.core.ArrivalTracker
import com.videomk.app.core.MediaApi
import com.videomk.app.core.PhotoIntake
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.PromptSearch

/**
 * ONE sheet for adding photos (docs/UI_DESIGN.md section f): a segmented control (This phone | My media) over ONE selection and ONE selection bar.
 *
 * How "This phone" works without any storage permission: the grid shows the photos already chosen from the phone; its first tile opens the system Photo
 * Picker (PickMultipleVisualMedia, or the app's chooser when the picker is missing), and what comes back lands in the composer's strip at once and is
 * numbered here. "My media" is a real grid of the private library. Both tabs write into the composer live, so the strip behind the sheet is always the
 * truth, the numbers run across both sources, and the 100 total is enforced for both.
 */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun AddPhotosSheet(composer: ComposerViewModel, api: MediaApi?, tracker: ArrivalTracker?, startOnMyMedia: Boolean, onDismiss: () -> Unit, onAddDeck: (() -> Unit)? = null) {
    val context = LocalContext.current
    var tab by rememberSaveable { mutableIntStateOf(if (startOnMyMedia && api != null) 1 else 0) }
    val vm: MediaViewModel? = if (api != null) viewModel(key = "media-picker", factory = viewModelFactory { initializer { MediaViewModel(api, null, null, PhotoLimits.MAX_PHOTOS, tracker ?: ArrivalTracker()) } }) else null
    val initialLibrary = remember { composer.library.toList() }
    val phoneCount = composer.photos.size + composer.loading
    val libraryCount = composer.library.size
    val total = AddPhotosLogic.total(phoneCount, libraryCount)
    val prompt = composer.text
    val container = LocalContainerOrNull.current

    if (vm != null) {
        LaunchedEffect(Unit) { vm.start(); vm.startPicker(initialLibrary); vm.onVisible() }
        LaunchedEffect(phoneCount) { vm.setLimit(PhotoLimits.MAX_PHOTOS - phoneCount) }
        // live: the strip behind the sheet is always what is chosen
        LaunchedEffect(vm.selection.toList()) { composer.setLibrary(vm.selectedPhotos()) }
        DisposableEffect(vm) { onDispose { vm.stopWaiting() } }
    }

    // the system Photo Picker: no READ_MEDIA_IMAGES, no storage permission. Opened from inside the sheet; its result goes straight into the strip.
    val platformMax = remember {
        if (ActivityResultContracts.PickVisualMedia.isPhotoPickerAvailable(context)) runCatching { pickImagesMaxLimit() }.getOrDefault(PhotoLimits.MAX_PHOTOS) else PhotoLimits.MAX_PHOTOS
    }
    val room = AddPhotosLogic.room(phoneCount, libraryCount)
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(PhotoIntake.pickerMax(platformMax, room))) { uris ->
        if (uris.isNotEmpty()) composer.addPhotos(context.contentResolver, uris)
    }
    val chooser = rememberPhotoChooser { uris -> composer.addPhotos(context.contentResolver, uris) }
    fun pickFromPhone() {
        if (room == 0) { vm?.notice = AddPhotosLogic.LIMIT_MESSAGE; composer.flagLimit(); return }
        try {
            if (ActivityResultContracts.PickVisualMedia.isPhotoPickerAvailable(context)) picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) else chooser()
        } catch (e: Exception) { chooser() }
    }
    val addToLibrary = rememberPhotoChooser { uris -> container?.mediaUploads?.add(context.contentResolver, uris) }

    val shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
    ModalBottomSheet(
        onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), shape = shape, containerColor = Vmk.colors.surface,
    ) {
        Column(Modifier.fillMaxHeight(0.94f).fillMaxWidth().semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("addPhotosSheet")) {
            Row(Modifier.fillMaxWidth().padding(start = 20.dp, end = 8.dp).heightIn(min = 52.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.media_add_photos), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.weight(1f))
                TextButton(onClick = { composer.setLibrary(initialLibrary); onDismiss() }, modifier = Modifier.heightIn(min = 44.dp).testTag("addPhotosCancel")) { Text(stringResource(R.string.common_cancel), fontWeight = FontWeight.SemiBold) }
            }
            // only where the server offers presentations; it closes this sheet and opens the system document picker
            if (onAddDeck != null) DeckEntryRow(onClick = { onDismiss(); onAddDeck() }, modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp))
            if (api != null) Segmented(tab, onTab = { tab = it }, Modifier.padding(horizontal = 20.dp, vertical = 4.dp))
            Box(Modifier.weight(1f).fillMaxWidth()) {
                when {
                    tab == 1 && vm != null -> MyMediaTab(vm, composer, phoneCount, prompt, onAddToLibrary = if (container?.mediaUploads != null) addToLibrary else null)
                    else -> PhoneTab(composer, onPick = ::pickFromPhone)
                }
                // a tap that cannot be honoured always says why
                val note = vm?.notice ?: composer.notice
                if (note != null) Snack(note, Modifier.align(Alignment.BottomCenter).padding(16.dp))
            }
            SelectionBar(composer, total, phoneCount, libraryCount, onDone = onDismiss, selectAll = if (tab == 1 && vm != null) vm else null)
        }
    }
}

@Composable
private fun Segmented(selected: Int, onTab: (Int) -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(12.dp)
    Row(modifier.fillMaxWidth().heightIn(min = 40.dp).clip(shape).background(Vmk.colors.surfaceRaised).padding(3.dp)) {
        listOf(stringResource(R.string.photos_tab_phone) to Icons.Filled.PhoneAndroid, stringResource(R.string.photos_tab_media) to Icons.Filled.Shield).forEachIndexed { i, (label, icon) ->
            val sel = i == selected
            val tabDesc = stringResource(R.string.photos_tab_desc, label, i + 1)
            val selectedText = stringResource(R.string.media_state_selected)
            Row(
                Modifier.weight(1f).heightIn(min = 40.dp).clip(RoundedCornerShape(10.dp)).then(if (sel) Modifier.background(if (Vmk.colors.dark) Vmk.colors.surface3 else Vmk.colors.surface) else Modifier)
                    .clickable(role = Role.Tab, onClickLabel = label) { onTab(i) }
                    .semantics { this.selected = sel; contentDescription = tabDesc; stateDescription = if (sel) selectedText else "" }
                    .testTag(if (i == 0) "tabThisPhone" else "tabMyMedia"),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
            ) {
                Icon(icon, null, tint = if (sel) Vmk.colors.text else Vmk.colors.textSecondary, modifier = Modifier.size(18.dp))
                Text(label, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold, color = if (sel) Vmk.colors.text else Vmk.colors.textSecondary)
            }
        }
    }
}

@Composable
private fun PhoneTab(composer: ComposerViewModel, onPick: () -> Unit) {
    if (composer.photos.isEmpty() && composer.loading == 0) {
        // nothing chosen yet: one clear way in
        Column(Modifier.fillMaxSize().padding(32.dp), verticalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterVertically), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.size(72.dp).clip(CircleShape).background(Vmk.colors.primaryContainer), contentAlignment = Alignment.Center) { Icon(Icons.Filled.AddPhotoAlternate, null, tint = Vmk.colors.primary, modifier = Modifier.size(36.dp)) }
            Text(stringResource(R.string.photos_choose_title), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text)
            Text(stringResource(R.string.photos_picker_explain), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
            Box(Modifier.padding(top = 6.dp).heightIn(min = 48.dp).clip(CircleShape).background(Vmk.gradientNow).clickable(role = Role.Button, onClick = onPick).padding(horizontal = 26.dp).testTag("pickFromPhone"), contentAlignment = Alignment.Center) {
                Text(stringResource(R.string.photos_open_picker), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = Color.White)
            }
        }
        return
    }
    Column(Modifier.fillMaxSize()) {
        Text(
            stringResource(R.string.photos_picker_note),
            style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
        )
        LazyVerticalGrid(
            GridCells.Fixed(3), Modifier.fillMaxSize().testTag("phoneGrid"), contentPadding = PaddingValues(bottom = 16.dp),
            horizontalArrangement = Arrangement.spacedBy(2.dp), verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            item(key = "pick") {
                val chooseDesc = stringResource(R.string.photos_choose_desc)
                Column(
                    Modifier.aspectRatio(1f).background(Vmk.colors.primaryContainer).clickable(role = Role.Button, onClickLabel = stringResource(R.string.photos_open_picker_label), onClick = onPick)
                        .semantics { contentDescription = chooseDesc }.testTag("pickFromPhone"),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
                ) {
                    Icon(Icons.Filled.AddPhotoAlternate, null, tint = Vmk.colors.primary, modifier = Modifier.size(32.dp))
                    Text(stringResource(R.string.photos_choose), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = Vmk.colors.primary, modifier = Modifier.padding(top = 6.dp))
                }
            }
            itemsIndexed(composer.photos, key = { _, p -> p.id }) { index, photo ->
                val tileDesc = stringResource(R.string.photos_tile_desc, index + 1)
                Box(
                    Modifier.aspectRatio(1f).clickable(role = Role.Checkbox, onClickLabel = stringResource(R.string.common_remove)) { composer.removePhoto(photo.id) }
                        .semantics { contentDescription = tileDesc; selected = true }.testTag("phoneTile"),
                ) {
                    photo.thumbnail?.let { androidx.compose.foundation.Image(it.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize().padding(8.dp).clip(RoundedCornerShape(10.dp))) }
                    Box(Modifier.fillMaxSize().border(3.dp, MaterialTheme.colorScheme.primary).background(MaterialTheme.colorScheme.primary.copy(alpha = 0.12f)))
                    NumberBadge(index + 1, Modifier.align(Alignment.TopEnd).padding(6.dp))
                }
            }
            if (composer.loading > 0) item(key = "preparing") {
                Box(Modifier.aspectRatio(1f).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) { androidx.compose.material3.CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp) }
            }
        }
    }
}

@Composable
private fun MyMediaTab(vm: MediaViewModel, composer: ComposerViewModel, phoneCount: Int, prompt: String, onAddToLibrary: (() -> Unit)?) {
    val order = remember(vm.selection.toList(), phoneCount) { vm.selection.withIndex().associate { it.value to phoneCount + it.index + 1 } }
    val atLimit = AddPhotosLogic.limitReached(phoneCount, vm.selection.size)
    Column(Modifier.fillMaxSize()) {
        Column(Modifier.padding(horizontal = 20.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            MediaSearchBar(vm, label = if (vm.fromPrompt) stringResource(R.string.photos_from_prompt) else null)
            if (!vm.fromPrompt && PromptSearch.looksLikePhotoRequest(prompt)) {
                TextButton(onClick = { vm.promptSearch(prompt) }, modifier = Modifier.heightIn(min = 44.dp).testTag("photosFromPrompt")) { Text(stringResource(R.string.photos_from_prompt)) }
            }
            // album chips: All, then each collection
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                item { AlbumChip(stringResource(R.string.photos_all), vm.activeCollection == null) { vm.setCollectionFilter(null) } }
                items(vm.collections, key = { it.id }) { c -> AlbumChip(c.name, vm.activeCollection == c.id) { vm.setCollectionFilter(c.id) } }
            }
        }
        MediaBody(vm, onAdd = onAddToLibrary, onOpenCollection = {}, onMakeVideo = {}, header = null, order = order, dimUnselected = atLimit)
    }
}

@Composable
private fun AlbumChip(label: String, selected: Boolean, onClick: () -> Unit) {
    val shape = CircleShape
    Box(
        Modifier.heightIn(min = 44.dp).clickable(role = Role.Button, onClick = onClick).semantics { this.selected = selected }, contentAlignment = Alignment.Center,
    ) {
        Text(
            label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold, color = if (selected) Vmk.colors.primary else Vmk.colors.text,
            modifier = Modifier.heightIn(min = 34.dp).clip(shape).then(if (selected) Modifier.background(Vmk.colors.primaryContainer) else Modifier.border(1.dp, Vmk.colors.outline, shape))
                .padding(horizontal = 16.dp, vertical = 7.dp),
        )
    }
}

@Composable
private fun NumberBadge(n: Int, modifier: Modifier = Modifier) {
    Box(modifier.size(24.dp).clip(CircleShape).background(Vmk.gradientNow).border(2.dp, Color.White, CircleShape), contentAlignment = Alignment.Center) {
        Text("$n", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = Color.White)
    }
}

@Composable
private fun Snack(text: String, modifier: Modifier = Modifier) {
    Surface(modifier, shape = RoundedCornerShape(16.dp), color = if (Vmk.colors.dark) Color(0xFFE9EAF6) else Color(0xFF23263F)) {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = if (Vmk.colors.dark) Color(0xFF23263F) else Color.White, modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp).testTag("addPhotosNote"))
    }
}

/** The one selection bar under both tabs: "7 selected", where they come from, and the button that closes the sheet with them in the strip. */
@Composable
private fun SelectionBar(composer: ComposerViewModel, total: Int, phone: Int, library: Int, onDone: () -> Unit, selectAll: MediaViewModel? = null) {
    Column(Modifier.fillMaxWidth().background(Vmk.colors.surface).navigationBarsPadding()) {
        Box(Modifier.fillMaxWidth().size(1.dp).background(Vmk.colors.outline))
        Row(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f).semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(AddPhotosLogic.title(total), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.testTag("selectedCount"))
                    if (selectAll != null) { Text("  ·", color = Vmk.colors.textTertiary); SelectAllButton(selectAll) }
                }
                Text(AddPhotosLogic.subline(phone, library, composer.options.minutes), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("selectionSubline"))
            }
            val on = total > 0
            Box(
                Modifier.heightIn(min = 48.dp).clip(CircleShape).then(if (on) Modifier.background(Vmk.gradientNow) else Modifier.background(Vmk.colors.surface3))
                    .clickable(enabled = on, role = Role.Button, onClick = onDone).padding(horizontal = 26.dp).testTag("addPhotosDone"),
                contentAlignment = Alignment.Center,
            ) { Text(AddPhotosLogic.addLabel(total), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, color = if (on) Color.White else Vmk.colors.textTertiary) }
        }
    }
}

