package com.videomk.app.core

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Undo over confirm (docs/DESIGN_BAR_2026.md rule 8): a removal disappears from the screen at once and shows "Deleted · Undo" for six seconds. The server call is
 * made only when that time is over, when a newer removal takes the bar, or when the app leaves the screen ([flush]); Undo before that puts the thing back and
 * nothing was ever sent. The server has no bin, so this wait is the whole undo. One bar at a time, shared by videos, photos and collections; the same bar also
 * carries short confirmations that have nothing to undo ([say]).
 */
class UndoCenter(private val scope: CoroutineScope, private val windowMillis: Long = WINDOW_MILLIS) {
    data class Item(val id: Long, val text: String, val undoable: Boolean)
    private class Pending(val item: Item, val commit: suspend () -> Unit, val undo: () -> Unit, var timer: Job? = null)

    private val _current = MutableStateFlow<Item?>(null)
    val current: StateFlow<Item?> = _current.asStateFlow()
    private var pending: Pending? = null
    private var counter = 0L
    private val lock = Any()

    /** [hide] has already taken the thing off the screen; [commit] removes it for real; [undo] puts it back on the screen. */
    fun offer(text: String, commit: suspend () -> Unit, undo: () -> Unit) {
        val p = synchronized(lock) {
            val before = pending
            val next = Pending(Item(++counter, text, true), commit, undo)
            pending = next; _current.value = next.item
            before to next
        }
        p.first?.let { run(it) }   // the earlier removal is final now: only one can be undone at a time
        p.second.timer = scope.launch { delay(windowMillis); expire(p.second) }
    }

    /** A short message with nothing to undo ("Cancelled · 2 credits back"). An open undo is made final first. */
    fun say(text: String) {
        flush()
        val item = synchronized(lock) { Item(++counter, text, false).also { _current.value = it } }
        scope.launch { delay(windowMillis); synchronized(lock) { if (_current.value?.id == item.id) _current.value = null } }
    }

    fun undo() {
        val p = synchronized(lock) { pending.also { pending = null; if (it != null && _current.value?.id == it.item.id) _current.value = null } } ?: return
        p.timer?.cancel(); p.undo()
    }

    /** Makes an open removal final now (the app is leaving the screen, the person signed out): nothing is left half done. */
    fun flush() {
        val p = synchronized(lock) { pending.also { pending = null; if (it != null && _current.value?.id == it.item.id) _current.value = null } } ?: return
        p.timer?.cancel(); run(p)
    }

    /** True while [flush] or a timer still has something to send. */
    val hasPending: Boolean get() = synchronized(lock) { pending != null }

    private fun expire(p: Pending) {
        val mine = synchronized(lock) { if (pending === p) { pending = null; if (_current.value?.id == p.item.id) _current.value = null; true } else false }
        if (mine) run(p)
    }

    private fun run(p: Pending) { p.timer?.cancel(); scope.launch { p.commit() } }

    companion object { const val WINDOW_MILLIS = 6000L }
}
