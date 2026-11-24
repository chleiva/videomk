package com.videomk.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.videomk.app.core.ApiError
import com.videomk.app.core.Backend
import com.videomk.app.core.EditOp
import com.videomk.app.core.EditState
import com.videomk.app.core.EditorBeat
import com.videomk.app.core.EditorDiff
import com.videomk.app.core.EditorLimits
import com.videomk.app.core.EditorSnapshot
import com.videomk.app.core.PhotoCandidate
import com.videomk.app.core.RenderMode
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

sealed interface EditorPhase {
    data object Loading : EditorPhase
    data object Editing : EditorPhase
    data class Rendering(val mode: RenderMode) : EditorPhase
    data class Done(val mode: RenderMode) : EditorPhase
    data class Failed(val message: String) : EditorPhase
}

data class EditorState(
    val phase: EditorPhase = EditorPhase.Loading,
    val snapshot: EditorSnapshot? = null,
    val title: String = "",
    val captions: Boolean = true,
    val beats: List<EditorBeat> = emptyList(),
    val picks: Map<String, String> = emptyMap(),
    /** A conflict, validation or network message the user can act on. */
    val banner: String? = null,
    val resultUrl: String? = null,
) {
    val limits: EditorLimits get() = snapshot?.limits ?: EditorLimits()
    val ops: List<EditOp> get() = snapshot?.let { EditorDiff.ops(it.title, it.beats, title, beats, picks, it.captions, captions) } ?: emptyList()
    val isDirty: Boolean get() = ops.isNotEmpty()
    val canPublishWithoutChanges: Boolean get() = snapshot?.let { it.previewRev != null && it.previewRev == it.rev && it.finalRev != it.rev } ?: false
    val isLocked: Boolean get() = phase is EditorPhase.Rendering

    fun isEdited(id: String): Boolean {
        val server = snapshot?.beats?.firstOrNull { it.id == id } ?: return false
        val local = beats.firstOrNull { it.id == id } ?: return false
        return EditorDiff.normalize(server.narration) != EditorDiff.normalize(local.narration) || picks[id] != null
    }

    fun narrationError(id: String): String? = beats.firstOrNull { it.id == id }?.let { EditorDiff.narrationError(it.narration, limits, it.silent) }
}

class EditorViewModel(private val videoId: String, private val backend: Backend?, private val onChanged: () -> Unit = {}, private val pollMillis: Long = 4000) : ViewModel() {
    private val _state = MutableStateFlow(EditorState())
    val state: StateFlow<EditorState> = _state.asStateFlow()
    private var loadJob: Job? = null

    init { load() }

    private fun backendOrFail(): Backend = backend ?: throw ApiError.Server

    fun load() {
        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            _state.update { it.copy(phase = EditorPhase.Loading, banner = null) }
            try {
                val s = backendOrFail().editorSnapshot(videoId)
                adopt(s)
                if (s.editState == EditState.Rendering) {
                    val mode = if (s.editMode == "final") RenderMode.Final else RenderMode.Preview
                    _state.update { it.copy(phase = EditorPhase.Rendering(mode)) }
                    waitForRender(mode)
                } else _state.update { it.copy(phase = EditorPhase.Editing) }
            } catch (e: CancellationException) { throw e }
            catch (e: ApiError) { _state.update { it.copy(phase = EditorPhase.Failed(e.message)) } }
            catch (e: Exception) { _state.update { it.copy(phase = EditorPhase.Failed(ApiError.Server.message)) } }
        }
    }

    private fun adopt(s: EditorSnapshot) = _state.update { it.copy(snapshot = s, title = s.title, captions = s.captions, beats = s.beats, picks = emptyMap()) }

    // edit

    fun setTitle(t: String) = _state.update { it.copy(title = t) }
    fun setCaptions(on: Boolean) = _state.update { it.copy(captions = on) }

    fun setNarration(id: String, text: String) = _state.update { st ->
        st.copy(beats = st.beats.map { if (it.id == id) it.copy(narration = text) else it })
    }

    fun pick(candidate: PhotoCandidate, id: String) = _state.update { it.copy(picks = it.picks + (id to candidate.key)) }
    fun clearPick(id: String) = _state.update { it.copy(picks = it.picks - id) }

    fun move(id: String, delta: Int) = _state.update { st ->
        val i = st.beats.indexOfFirst { it.id == id }
        val j = i + delta
        if (i < 0 || j !in st.beats.indices) st
        else st.copy(beats = st.beats.toMutableList().also { val b = it.removeAt(i); it.add(j, b) })
    }

    fun delete(id: String) = _state.update { st ->
        if (st.beats.size - 1 < 1) st.copy(banner = "A video needs at least one scene.")
        else st.copy(beats = st.beats.filterNot { it.id == id }, picks = st.picks - id)
    }

    fun discard() { _state.value.snapshot?.let { adopt(it); _state.update { s -> s.copy(banner = null) } } }
    fun dismissBanner() = _state.update { it.copy(banner = null) }
    fun keepEditing() = _state.update { it.copy(phase = EditorPhase.Editing) }

    // render

    /** Preview renders a quick draft; final renders the full-quality version and replaces the published video. */
    fun submit(mode: RenderMode) {
        val st = _state.value
        val s = st.snapshot ?: return
        if (st.isLocked) return
        st.beats.firstNotNullOfOrNull { st.narrationError(it.id) }?.let { msg -> _state.update { it.copy(banner = msg) }; return }
        _state.update { it.copy(banner = null) }
        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            try {
                backendOrFail().applyEdits(videoId, s.rev, st.ops, mode)
                _state.update { it.copy(phase = EditorPhase.Rendering(mode)) }
                waitForRender(mode)
            } catch (e: CancellationException) { throw e }
            catch (e: ApiError.Conflict) { _state.update { it.copy(banner = e.message + " Your edits on this screen are kept until you reload.") } }
            catch (e: ApiError) { _state.update { it.copy(banner = e.message) } }
            catch (e: Exception) { _state.update { it.copy(banner = ApiError.Server.message) } }
        }
    }

    private suspend fun waitForRender(mode: RenderMode) {
        repeat(150) {   // about 10 minutes
            delay(pollMillis)
            if (!currentCoroutineContextActive()) return
            val s = try { backendOrFail().editorSnapshot(videoId) } catch (e: CancellationException) { throw e } catch (e: Exception) { null }
            if (s == null || s.editState == EditState.Rendering) return@repeat
            adopt(s)
            if (s.editState == EditState.Failed) {
                _state.update { it.copy(phase = EditorPhase.Failed("The render didn't finish. Your changes are saved; try again.")) }
                return
            }
            _state.update { it.copy(resultUrl = if (mode == RenderMode.Final) s.finalUrl else s.previewUrl, phase = EditorPhase.Done(mode)) }
            onChanged()
            return
        }
        _state.update { it.copy(phase = EditorPhase.Failed("This is taking longer than usual. Close the editor and check back in a few minutes.")) }
    }

    private suspend fun currentCoroutineContextActive() = kotlin.coroutines.coroutineContext.isActive
}
