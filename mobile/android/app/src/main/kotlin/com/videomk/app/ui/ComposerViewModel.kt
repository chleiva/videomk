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
import com.videomk.app.core.PhotoIntake
import com.videomk.app.core.PickedCache
import com.videomk.app.core.PickedSource
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.prepareInOrder
import com.videomk.app.data.DictationController
import com.videomk.app.data.PhotoPrep
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.util.UUID

class AttachedPhoto(val id: String = UUID.randomUUID().toString(), val data: ByteArray, val thumbnail: Bitmap?)

/**
 * Everything about the video being composed: the text, the length and look, the attached photos (up to 100) and dictation.
 * Lives in the ViewModelStore, so a rotation keeps the half-typed brief, the photos and a running dictation.
 */
class ComposerViewModel(app: Application) : AndroidViewModel(app) {
    var text by mutableStateOf("")
    var options by mutableStateOf(CreateOptions())
    val photos: SnapshotStateList<AttachedPhoto> = mutableStateListOf()
    /** Bumps when dictation wants the text field focused (the keyboard's own mic is the fallback). */
    var focusRequests by mutableIntStateOf(0)
        private set

    val dictation = DictationController(app).also { d ->
        d.onText = { text = it }
        d.onKeyboardFallback = { focusRequests++ }
    }

    /** Photos being prepared in the current batch (the "Preparing N of M" text) and how many of them are finished. */
    var preparing by mutableIntStateOf(0)
        private set
    var prepared by mutableIntStateOf(0)
        private set
    /** A short message about the last selection (photos left out, photos that couldn't be read). Cleared by the next selection or send. */
    var notice by mutableStateOf<String?>(null)
        private set

    var copied by mutableIntStateOf(0)
        private set
    private val cacheRoot = java.io.File(app.cacheDir, "picked")
    private val cache = PickedCache(java.io.File(cacheRoot, "session")).also { PickedCache.cleanLeftovers(cacheRoot) }   // an app start removes what a crashed session left
    private val copyLock = kotlinx.coroutines.sync.Mutex()
    private var unreadable = 0
    private val prepLock = kotlinx.coroutines.sync.Mutex()   // batches queue up, so at most PREP_PARALLELISM photos are ever in flight

    val loading: Int get() = preparing - prepared
    val remaining: Int get() = maxOf(0, PhotoLimits.MAX_PHOTOS - photos.size - loading)

    fun requestFocus() { focusRequests++ }

    fun applyDebugDefaults(minutes: Double?) { if (minutes != null) options = options.copy(minutes = minutes) }

    fun addPhotos(resolver: ContentResolver, uris: List<Uri>) =
        enqueue(uris, PickedSource { uri -> resolver.openInputStream(uri) })

    fun addPhotoFiles(paths: List<String>) =
        enqueue(paths, PickedSource { path -> java.io.FileInputStream(path) })

    /**
     * Keeps the first selected photos that fit in the room left and tells how many were left out. Then, at once (the gallery's read grant is only
     * valid for a while), each original is streamed into a private cache file a couple at a time; after that the files are prepared a couple at a
     * time off the main thread, each source file deleted as soon as its photo is prepared. Only the prepared JPEG and a small preview are kept.
     */
    private fun <T> enqueue(items: List<T>, source: PickedSource<T>) {
        val plan = PhotoIntake.plan(items.size, remaining)
        if (items.isEmpty()) return
        notice = if (plan.leftOut > 0) PhotoIntake.leftOutMessage(plan.leftOut) else null
        if (plan.accepted == 0) return
        val batch = items.take(plan.accepted)
        if (loading == 0) { preparing = 0; prepared = 0; copied = 0; unreadable = 0 }
        preparing += batch.size
        viewModelScope.launch {
            val files = ArrayList<java.io.File?>(batch.size)
            copyLock.withLock {
                prepareInOrder(batch, PhotoLimits.PREP_PARALLELISM, prepare = { item -> withContext(Dispatchers.IO) { cache.copy(item, source) } }) { _, f ->
                    files += f; copied += 1
                }
            }
            prepLock.withLock { prepareInOrder(
                files, PhotoLimits.PREP_PARALLELISM,
                prepare = { f ->
                    withContext(Dispatchers.Default) {
                        if (f == null) null else try {
                            PhotoPrep.jpeg(f.readBytes())?.let { AttachedPhoto(data = it, thumbnail = PhotoPrep.thumbnail(it)) }
                        } catch (e: Exception) { null } finally { f.delete() }
                    }
                },
            ) { _, photo ->
                if (photo != null && photos.size < PhotoLimits.MAX_PHOTOS) photos.add(photo) else unreadable++
                prepared += 1
                if (loading == 0) {
                    if (unreadable > 0) notice = listOfNotNull(notice, PhotoIntake.unreadableMessage(unreadable)).joinToString(" ")
                    cleanupIfIdle()
                }
            } }
        }
    }

    /** Copying counts as half of preparing a photo, so the number moves from the first copy on. */
    val preparingText: String get() = PhotoIntake.preparingText((copied + prepared) / 2, preparing)

    private fun cleanupIfIdle() { if (loading == 0) cache.endSession() }

    fun removePhoto(id: String) { photos.removeAll { it.id == id }; cleanupIfIdle() }

    val canSend: Boolean get() = Brief.isValid(text)

    /** Hands back what to send and clears the composer, ready for the next request. */
    fun takeForSend(): Pair<String, List<ByteArray>> {
        dictation.stop()
        val out = text to photos.map { it.data }
        photos.clear()
        cleanupIfIdle()
        notice = null
        text = ""
        return out
    }

    override fun onCleared() {
        cache.endSession()
        dictation.release()
    }
}
