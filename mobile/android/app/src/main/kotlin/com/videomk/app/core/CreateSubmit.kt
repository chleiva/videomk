package com.videomk.app.core

/**
 * What Create looks like between the tap and the answer. Two honest phases: the request check ("Checking your request") and the send itself ("Starting your video").
 * While either runs the whole form is locked (nothing can be edited or tapped twice); only the close icon works, and only during the check, where nothing exists on the
 * server yet (cancelling there is clean). Once the send is in flight it cannot be taken back without risking a duplicate video, so closing waits for the answer.
 */
object CreateSubmit {
    enum class Phase { Idle, Checking, Starting }

    fun phase(checking: Boolean, submitting: Boolean): Phase = when { submitting -> Phase.Starting; checking -> Phase.Checking; else -> Phase.Idle }

    /** Everything except the close icon ignores touches. */
    fun locked(phase: Phase): Boolean = phase != Phase.Idle

    /** The close icon cancels the check; during the send it does nothing (the answer is moments away). */
    fun closeCancelsCheck(phase: Phase): Boolean = phase == Phase.Checking
    fun closeIsBlocked(phase: Phase): Boolean = phase == Phase.Starting

    /** A second tap on Create while a phase runs is ignored. */
    fun tapAllowed(phase: Phase): Boolean = phase == Phase.Idle
}
