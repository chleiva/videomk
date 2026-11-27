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

/**
 * The capsule at the bottom of Create (docs/DESIGN_BAR_2026.md signature 2) as a small state machine with no UI in it, so it is unit tested.
 * The button morphs into a live capsule on the tap ("Checking your request", then "Starting your video"); a run ends in exactly one of four ways:
 * a question, a refusal, the Making screen, or the form restored intact. There is no fifth, and no state in which the form is editable while something runs.
 */
object CreateCapsule {
    /** What is drawn where the Create button is. */
    sealed interface View {
        /** The gradient button with its price. */
        data object Button : View
        /** The live capsule: three words, a moving ring, and Cancel while cancelling is clean. [photo]/[photos]: the photo going up (1-based) while photos are sent, else null. */
        data class Live(val step: Step, val canCancel: Boolean, val photo: Int? = null, val photos: Int? = null) : View
    }
    enum class Step { Checking, Starting }

    /** The four ends of a run, plus [Running] while it is not over. */
    enum class End { Running, Question, Refusal, Making, Restored }

    sealed interface Event {
        /** Create was tapped with a valid request. [willCheck]: this server checks the request first (no check for a presentation or an older server). */
        data class Tap(val willCheck: Boolean) : Event
        /** The check passed, failed or timed out: all three go on (a failed check never blocks a video). */
        data object CheckDone : Event
        data object CheckAsks : Event
        data object CheckRefuses : Event
        data object Cancel : Event
        data object Accepted : Event
        data object SendRefused : Event
        data object SendFailed : Event
    }

    data class State(val phase: CreateSubmit.Phase = CreateSubmit.Phase.Idle, val end: End = End.Restored)

    fun view(phase: CreateSubmit.Phase, uploading: Pair<Int, Int>? = null): View = when (phase) {
        CreateSubmit.Phase.Idle -> View.Button
        CreateSubmit.Phase.Checking -> View.Live(Step.Checking, canCancel = true)
        // once the send is in flight it cannot be taken back without risking a video nobody asked to keep: no Cancel, the answer is moments away
        CreateSubmit.Phase.Starting -> View.Live(Step.Starting, canCancel = false, photo = uploading?.let { minOf(it.first + 1, it.second) }, photos = uploading?.second)
    }

    fun next(s: State, e: Event): State = when (s.phase) {
        CreateSubmit.Phase.Idle -> when (e) {
            is Event.Tap -> State(if (e.willCheck) CreateSubmit.Phase.Checking else CreateSubmit.Phase.Starting, End.Running)
            else -> s   // nothing is running: a late answer or a stray Cancel changes nothing
        }
        CreateSubmit.Phase.Checking -> when (e) {
            Event.CheckDone -> State(CreateSubmit.Phase.Starting, End.Running)
            Event.CheckAsks -> State(CreateSubmit.Phase.Idle, End.Question)
            Event.CheckRefuses -> State(CreateSubmit.Phase.Idle, End.Refusal)
            Event.Cancel -> State(CreateSubmit.Phase.Idle, End.Restored)
            else -> s   // a second tap is ignored; nothing was sent yet, so there is no send answer
        }
        CreateSubmit.Phase.Starting -> when (e) {
            Event.Accepted -> State(CreateSubmit.Phase.Idle, End.Making)
            Event.SendRefused -> State(CreateSubmit.Phase.Idle, End.Refusal)
            Event.SendFailed -> State(CreateSubmit.Phase.Idle, End.Restored)
            else -> s   // Cancel and a second tap are ignored while the send is in flight
        }
    }

    /** True when the draft (prompt, photos, options) must still be exactly what the person entered: every end except the Making screen. */
    fun keepsDraft(end: End): Boolean = end != End.Making
}
