package com.videomk.app.data

import android.content.Context
import com.videomk.app.core.ApiError
import com.videomk.app.core.JobStore
import com.videomk.app.core.MediaApi
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.OrganizeNames
import com.videomk.app.core.OrganizePref
import com.videomk.app.core.OrganizePreview
import com.videomk.app.core.OrganizePrompt
import com.videomk.app.core.OrganizeRunner
import com.videomk.app.core.OrganizeState
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import java.io.File

/** The organise job saved in the app's private folder, so it can resume after the app was killed. */
class FileJobStore(private val file: File) : JobStore {
    override fun load() = runCatching { file.readText() }.getOrNull()
    override fun save(text: String?) { if (text == null) file.delete() else runCatching { file.writeText(text) } }
}

/** What the "Organize" sheet shows. */
sealed interface OrganizeSheet {
    data object Hidden : OrganizeSheet
    data class Loading(val wholeLibrary: Boolean) : OrganizeSheet
    data class Offer(val preview: OrganizePreview, val wholeLibrary: Boolean, val since: String?, val single: Boolean = false, val suggestions: List<String> = emptyList()) : OrganizeSheet
    data class Failed(val wholeLibrary: Boolean) : OrganizeSheet
    /** From "Organize my library": nothing to do right now. */
    data object Nothing : OrganizeSheet
}

/**
 * Smart collections, app-wide: the post-upload prompt (once per batch, shown when Media is visible), the preference, and the organise job that survives leaving
 * the screen. The rules of when to ask and how to loop live in the pure code of `core/OrganizeLogic.kt`.
 */
class OrganizeController(context: Context, private val api: MediaApi, private val scope: CoroutineScope) {
    val runner = OrganizeRunner(api, FileJobStore(File(context.applicationContext.filesDir, "organize-job.json")))

    private val _pref = MutableStateFlow(OrganizePref.Ask)
    val pref: StateFlow<OrganizePref> = _pref.asStateFlow()

    private val pending = MutableStateFlow<OrganizeSheet>(OrganizeSheet.Hidden)
    private val mediaVisible = MutableStateFlow(false)
    private val _sheet = MutableStateFlow<OrganizeSheet>(OrganizeSheet.Hidden)
    /** The sheet to show now: an automatic offer waits until Media is on screen; one the person asked for shows at once. */
    val sheet: StateFlow<OrganizeSheet> = _sheet.asStateFlow()

    /** What the bar shows (a quiet run for a small batch shows nothing). */
    private val _bar = MutableStateFlow<OrganizeState>(OrganizeState.Idle)
    val bar: StateFlow<OrganizeState> = _bar.asStateFlow()
    private val _doneMessage = MutableStateFlow<String?>(null)
    /** The finished message ("Organized into 14 collections"); the screen shows it once and calls [consumeDone]. */
    val doneMessage: StateFlow<String?> = _doneMessage.asStateFlow()
    /** Bumps whenever collections changed, so the Media tab reloads. */
    private val _changes = MutableStateFlow(0)
    val changes: StateFlow<Int> = _changes.asStateFlow()

    private var silent = false
    private var handledBatch = Long.MIN_VALUE
    private var wholeLibrarySheet = false
    private val photoCache = HashMap<String, MediaPhoto?>()

    init {
        scope.launch {
            runner.state.collect { s ->
                _bar.value = if (silent && (s is OrganizeState.Running || s is OrganizeState.Offline)) OrganizeState.Idle else s
                if (s is OrganizeState.Done) {
                    _changes.update { it + 1 }
                    if (!silent) _doneMessage.value = OrganizePrompt.doneMessage(s.created, s.updated)
                    silent = false
                    runner.acknowledge(); _bar.value = OrganizeState.Idle
                }
            }
        }
    }

    fun consumeDone() { _doneMessage.value = null }

    // preference

    fun refreshPref() { scope.launch { runCatching { api.summary().organizePref }.getOrNull()?.let { _pref.value = it } } }
    fun setPref(p: OrganizePref) {
        val old = _pref.value; _pref.value = p
        scope.launch { try { api.setOrganizePref(p) } catch (e: Exception) { _pref.value = old } }
    }

    // after an upload batch

    /** The batch finished and its photos are ready. [batchStartMillis] identifies the batch (one decision per batch). */
    fun onBatchReady(batchStartMillis: Long) {
        if (batchStartMillis == handledBatch || runner.isActive) return
        handledBatch = batchStartMillis
        scope.launch {
            val pref = runCatching { api.summary().organizePref }.getOrNull() ?: _pref.value
            _pref.value = pref
            if (pref == OrganizePref.Never) return@launch
            val since = OrganizePrompt.since(batchStartMillis)
            val preview = try { api.organizePreview(since) } catch (e: Exception) { return@launch }
            when (OrganizePrompt.decide(pref, preview.total)) {
                OrganizePrompt.Decision.Nothing -> Unit
                OrganizePrompt.Decision.ShowSheet -> if (preview.groups.isNotEmpty()) { wholeLibrarySheet = false; pending.value = OrganizeSheet.Offer(preview, false, since, suggestions = OrganizeNames.suggest(preview)); publish() }
                OrganizePrompt.Decision.RunSilently -> { silent = true; runner.start(false, preview.total, since) }
                OrganizePrompt.Decision.RunWithProgress -> { silent = false; runner.start(false, preview.total, since) }
            }
        }
    }

    fun setMediaVisible(v: Boolean) { mediaVisible.value = v; publish() }
    private fun publish() { _sheet.value = if (wholeLibrarySheet) _sheet.value else if (mediaVisible.value) pending.value else OrganizeSheet.Hidden }

    // explicit: "Organize my library"

    fun organizeLibrary() {
        wholeLibrarySheet = true
        _sheet.value = OrganizeSheet.Loading(true)
        scope.launch {
            val p = withTimeoutOrNull(15_000) { try { api.organizePreview(null) } catch (e: Exception) { null } }
            _sheet.value = when {
                p == null -> OrganizeSheet.Failed(true)
                p.groups.isEmpty() -> OrganizeSheet.Nothing
                else -> OrganizeSheet.Offer(p, true, null, suggestions = OrganizeNames.suggest(p))
            }
        }
    }

    fun retryPreview() { if (wholeLibrarySheet) organizeLibrary() }

    // sheet actions

    fun showSingle(on: Boolean) { (_sheet.value as? OrganizeSheet.Offer)?.let { _sheet.value = it.copy(single = on) } }

    fun organize(single: Boolean, name: String? = null) {
        val offer = _sheet.value as? OrganizeSheet.Offer ?: return
        closeSheet(rememberNotNow = false)
        silent = false
        scope.launch { runner.start(single, offer.preview.total, offer.since, name?.trim()) }
    }

    /** Not now (or back / outside tap): no re-ask for this batch. */
    fun closeSheet(rememberNotNow: Boolean = true) {
        pending.value = OrganizeSheet.Hidden; wholeLibrarySheet = false; _sheet.value = OrganizeSheet.Hidden
    }

    // the job

    fun cancelJob() { runner.cancel(); _bar.value = OrganizeState.Idle }
    fun retryJob() { scope.launch { runner.resume() } }
    fun resumeIfAny() { if (!runner.isActive && runner.pendingJob() != null) scope.launch { runner.resume() } }

    // thumbnails for the sample ids (fetched once; the image itself is cached by photo id)
    suspend fun photo(id: String): MediaPhoto? {
        if (photoCache.containsKey(id)) return photoCache[id]
        val p = try { api.item(id) } catch (e: ApiError) { null } catch (e: Exception) { null }
        photoCache[id] = p; return p
    }
}
