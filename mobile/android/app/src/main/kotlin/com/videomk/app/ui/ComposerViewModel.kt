package com.videomk.app.ui

import android.app.Application
import android.content.ContentResolver
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshots.SnapshotStateList
import androidx.compose.runtime.mutableStateListOf
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.videomk.app.DebugHooks
import com.videomk.app.core.Brief
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.PhotoLimits
import com.videomk.app.data.DictationController
import com.videomk.app.data.PhotoPrep
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.UUID

class AttachedPhoto(val id: String = UUID.randomUUID().toString(), val data: ByteArray, val thumbnail: Bitmap?)

/**
 * Everything about the video being composed: the text, the length and look, the attached photos (up to 10) and dictation.
 * Lives in the ViewModelStore, so a rotation keeps the half-typed brief, the photos and a running dictation.
 */
class ComposerViewModel(app: Application) : AndroidViewModel(app) {
    var text by mutableStateOf("")
    var options by mutableStateOf(CreateOptions())
    val photos: SnapshotStateList<AttachedPhoto> = mutableStateListOf()
    var loading by mutableIntStateOf(0)
        private set
    /** Bumps when dictation wants the text field focused (the keyboard's own mic is the fallback). */
    var focusRequests by mutableIntStateOf(0)
        private set

    val dictation = DictationController(app).also { d ->
        d.onText = { text = it }
        d.onKeyboardFallback = { focusRequests++ }
    }

    val remaining: Int get() = maxOf(0, PhotoLimits.MAX_PHOTOS - photos.size - loading)

    fun requestFocus() { focusRequests++ }

    fun applyDebugDefaults(minutes: Double?) { if (minutes != null) options = options.copy(minutes = minutes) }

    fun addPhotos(resolver: ContentResolver, uris: List<Uri>) {
        val batch = uris.take(remaining)
        if (batch.isEmpty()) return
        loading += batch.size
        viewModelScope.launch {
            for (uri in batch) {
                val photo = withContext(Dispatchers.Default) { PhotoPrep.jpeg(resolver, uri)?.let { AttachedPhoto(data = it, thumbnail = PhotoPrep.thumbnail(it)) } }
                if (photo != null && photos.size < PhotoLimits.MAX_PHOTOS) photos.add(photo)
                loading -= 1
            }
        }
    }

    fun addPhotoFiles(paths: List<String>) {
        val batch = paths.take(remaining)
        if (batch.isEmpty()) return
        loading += batch.size
        viewModelScope.launch {
            for (path in batch) {
                val photo = withContext(Dispatchers.Default) {
                    runCatching { java.io.File(path).readBytes() }.getOrNull()?.let { raw -> PhotoPrep.jpeg(raw)?.let { AttachedPhoto(data = it, thumbnail = PhotoPrep.thumbnail(it)) } }
                }
                if (photo != null && photos.size < PhotoLimits.MAX_PHOTOS) photos.add(photo)
                loading -= 1
            }
        }
    }

    fun removePhoto(id: String) { photos.removeAll { it.id == id } }

    val canSend: Boolean get() = Brief.isValid(text)

    /** Hands back what to send and clears the composer, ready for the next request. */
    fun takeForSend(): Pair<String, List<ByteArray>> {
        dictation.stop()
        val out = text to photos.map { it.data }
        photos.clear()
        text = ""
        return out
    }

    override fun onCleared() {
        dictation.release()
    }
}
