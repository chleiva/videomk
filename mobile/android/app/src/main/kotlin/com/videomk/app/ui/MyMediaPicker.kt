package com.videomk.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.videomk.app.core.MediaApi
import com.videomk.app.core.MediaCache
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.PromptSearch
import com.videomk.app.data.FilePageDisk
import java.io.File

/** "My media" in the composer: the same grid with search and selection, up to what is left of the 100, a count and Done. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MyMediaPicker(composer: ComposerViewModel, api: MediaApi, onDone: () -> Unit) {
    val limit = composer.libraryRoom
    val vm: MediaViewModel = viewModel(key = "media-picker", factory = viewModelFactory { initializer { MediaViewModel(api, null, null, limit) } })
    val existing = remember { composer.library.map { it.id } }
    val prompt = composer.text
    val offerPrompt = remember { PromptSearch.looksLikePhotoRequest(prompt) }
    LaunchedEffect(Unit) {
        vm.start(); vm.startPicker(existing)
        if (offerPrompt && existing.isEmpty()) vm.promptSearch(prompt)   // opens already searched and preselected, chips visible
    }
    fun done() {
        val byId = (vm.photos + composer.library).associateBy { it.id }
        val chosen = vm.selection.mapNotNull { byId[it] ?: vm.selectedPhotos().firstOrNull { p -> p.id == it } }
        composer.setLibrary(chosen)
        onDone()
    }
    ModalBottomSheet(onDismissRequest = onDone, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Vmk.colors.background) {
        Column(Modifier.fillHeightSheet().testTag("myMediaPicker")) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("My media", style = MaterialTheme.typography.titleLarge, color = Vmk.colors.text)
                    Text("${vm.selection.size} of $limit chosen (up to ${PhotoLimits.MAX_PHOTOS} photos in a video)", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("pickerCount"))
                }
                Button(onClick = ::done, modifier = Modifier.heightIn(min = 48.dp).testTag("pickerDone")) { Text("Done (${vm.selection.size})") }
            }
            Row(Modifier.padding(horizontal = 16.dp)) {
                MediaSearchBar(vm, Modifier.weight(1f).padding(vertical = 8.dp), label = if (vm.fromPrompt) "Photos from your prompt" else null)
            }
            if (!vm.fromPrompt && PromptSearch.looksLikePhotoRequest(prompt)) {
                TextButton(onClick = { vm.promptSearch(prompt) }, modifier = Modifier.padding(horizontal = 8.dp).heightIn(min = 48.dp).testTag("photosFromPrompt")) { Text("Photos from your prompt") }
            }
            vm.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = 16.dp)) }
            MediaBody(vm, onAdd = null, onOpenCollection = {}, onMakeVideo = {}, header = null)
        }
    }
}

private fun Modifier.fillHeightSheet(): Modifier = this.fillMaxHeight(0.92f).fillMaxWidth()
