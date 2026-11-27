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
import androidx.compose.runtime.mutableStateOf
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
import androidx.compose.foundation.layout.widthIn
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
 * The phone's photos, straight from the system Photo Picker (no storage permission, no explainer in between): one tap on "Photo library" in Create's photo menu
 * opens it, and what comes back lands in Create's strip. Returns the function that opens it; when there is no room left it says so instead.
 */
@Composable
fun rememberPhonePhotoPicker(composer: ComposerViewModel): () -> Unit {
    val context = LocalContext.current
    val platformMax = remember {
        if (ActivityResultContracts.PickVisualMedia.isPhotoPickerAvailable(context)) runCatching { pickImagesMaxLimit() }.getOrDefault(PhotoLimits.MAX_PHOTOS) else PhotoLimits.MAX_PHOTOS
    }
    val phoneCount = composer.photos.size + composer.loading
    val room = AddPhotosLogic.room(phoneCount, composer.library.size)
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(PhotoIntake.pickerMax(platformMax, room))) { uris ->
        if (uris.isNotEmpty()) composer.addPhotos(context.contentResolver, uris)
    }
    val chooser = rememberPhotoChooser { uris -> composer.addPhotos(context.contentResolver, uris) }
    return {
        if (room == 0) composer.flagLimit()
        else try {
            if (ActivityResultContracts.PickVisualMedia.isPhotoPickerAvailable(context)) picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) else chooser()
        } catch (e: Exception) { chooser() }
    }
}

/**
 * Photos from Media, picked for the video being written: the same grid as the Media tab under one header and one button, "Add · 3". The selection is written into
 * Create's strip live, so the strip behind the sheet is always the truth and the 100 total holds across the phone's photos and these. Closing with the X puts
 * back what was chosen before the sheet opened.
 */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun AddPhotosSheet(composer: ComposerViewModel, api: MediaApi?, tracker: ArrivalTracker?, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val vm: MediaViewModel = viewModel(key = "media-picker", factory = viewModelFactory { initializer { MediaViewModel(api, null, null, PhotoLimits.MAX_PHOTOS, tracker ?: ArrivalTracker()) } })
    val initialLibrary = remember { composer.library.toList() }
    val phoneCount = composer.photos.size + composer.loading
    val prompt = composer.text
    val container = LocalContainerOrNull.current

    // the picker is "ready" once it has taken over what is already chosen; before that the selection is empty and writing it into the composer would wipe the
    // library behind the sheet for a frame (the strip then measured items that were gone)
    var ready by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { vm.start(); vm.startPicker(initialLibrary); ready = true; vm.onVisible() }
    LaunchedEffect(phoneCount) { vm.setLimit(PhotoLimits.MAX_PHOTOS - phoneCount) }
    // live: the strip behind the sheet is always what is chosen
    LaunchedEffect(vm.selection.toList(), ready) { if (ready) composer.setLibrary(vm.selectedPhotos()) }
    DisposableEffect(vm) { onDispose { vm.stopWaiting() } }
    val addToLibrary = rememberPhotoChooser { uris -> container?.mediaUploads?.add(context.contentResolver, uris) }

    ModalBottomSheet(
        onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), shape = RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet), containerColor = Vmk.colors.surface,
    ) {
        Column(Modifier.fillMaxHeight(0.94f).fillMaxWidth().semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("addPhotosSheet")) {
            SheetHeader(stringResource(R.string.nav_tab_media), { composer.setLibrary(initialLibrary); onDismiss() }, Modifier.padding(start = Vmk.space.sheet, end = Vmk.space.m), closeTag = "addPhotosCancel", closeLabel = stringResource(R.string.common_cancel))
            Box(Modifier.weight(1f).fillMaxWidth()) {
                MyMediaTab(vm, composer, phoneCount, prompt, onAddToLibrary = if (container?.mediaUploads != null) addToLibrary else null)
                // a tap that cannot be honoured always says why
                val note = vm.notice ?: composer.notice
                if (note != null) Snack(note, Modifier.align(Alignment.BottomCenter).padding(16.dp))
            }
            SelectionBar(vm.selection.size, onDone = onDismiss, selectAll = vm)
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
    Surface(modifier, shape = RoundedCornerShape(16.dp), color = Vmk.colors.inverseSurface) {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.inverseOnSurface, modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp).testTag("addPhotosNote"))
    }
}

/** The one bar under the grid: Select all on the left, and the ONE primary, "Add · 3" (opaque and quiet until something is chosen). */
@Composable
private fun SelectionBar(count: Int, onDone: () -> Unit, selectAll: MediaViewModel) {
    Row(
        Modifier.fillMaxWidth().background(Vmk.colors.surface).navigationBarsPadding().padding(horizontal = Vmk.space.sheet, vertical = Vmk.space.m),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.m),
    ) {
        SelectAllButton(selectAll)
        androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
        PrimaryButton(AddPhotosLogic.addLabel(count), onDone, Modifier.widthIn(min = 132.dp).testTag("addPhotosDone").semantics { liveRegion = LiveRegionMode.Polite }, enabled = count > 0, fill = false)
    }
}
