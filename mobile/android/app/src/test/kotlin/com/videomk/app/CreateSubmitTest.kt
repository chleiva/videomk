package com.videomk.app

import com.videomk.app.core.CreateCapsule
import com.videomk.app.core.CreateCapsule.End
import com.videomk.app.core.CreateCapsule.Event as E
import com.videomk.app.core.CreateSubmit
import com.videomk.app.core.CreateSubmit.Phase
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The locked state of Create between the tap and the answer (docs/UX_2026_REDESIGN.md, the submit journey). */
class CreateSubmitTest {
    @Test fun `phase follows the check and the send`() {
        assertEquals(Phase.Idle, CreateSubmit.phase(checking = false, submitting = false))
        assertEquals(Phase.Checking, CreateSubmit.phase(checking = true, submitting = false))
        assertEquals(Phase.Starting, CreateSubmit.phase(checking = false, submitting = true))
        assertEquals(Phase.Starting, CreateSubmit.phase(checking = true, submitting = true))   // the send wins
    }

    @Test fun `the form is locked in both running phases and open when idle`() {
        assertFalse(CreateSubmit.locked(Phase.Idle)); assertTrue(CreateSubmit.locked(Phase.Checking)); assertTrue(CreateSubmit.locked(Phase.Starting))
    }

    @Test fun `a second tap on Create is ignored while anything runs`() {
        assertTrue(CreateSubmit.tapAllowed(Phase.Idle)); assertFalse(CreateSubmit.tapAllowed(Phase.Checking)); assertFalse(CreateSubmit.tapAllowed(Phase.Starting))
    }

    @Test fun `close cancels the check but waits during the send`() {
        assertTrue(CreateSubmit.closeCancelsCheck(Phase.Checking)); assertFalse(CreateSubmit.closeCancelsCheck(Phase.Starting)); assertFalse(CreateSubmit.closeCancelsCheck(Phase.Idle))
        assertTrue(CreateSubmit.closeIsBlocked(Phase.Starting)); assertFalse(CreateSubmit.closeIsBlocked(Phase.Checking)); assertFalse(CreateSubmit.closeIsBlocked(Phase.Idle))
    }
}

/** The capsule that replaces the Create button after the tap (docs/DESIGN_BAR_2026.md signature 2, rule 7). */
class CreateCapsuleTest {
    private val idle = CreateCapsule.State()
    private fun run(vararg events: E) = events.fold(idle) { s, e -> CreateCapsule.next(s, e) }

    @Test fun `idle shows the button, a running phase shows the live capsule`() {
        assertEquals(CreateCapsule.View.Button, CreateCapsule.view(Phase.Idle))
        val checking = CreateCapsule.view(Phase.Checking) as CreateCapsule.View.Live
        assertEquals(CreateCapsule.Step.Checking, checking.step); assertTrue(checking.canCancel)
        val starting = CreateCapsule.view(Phase.Starting) as CreateCapsule.View.Live
        assertEquals(CreateCapsule.Step.Starting, starting.step); assertFalse("the send cannot be taken back", starting.canCancel)
    }

    @Test fun `photos going up are counted from one and never past the total`() {
        val first = CreateCapsule.view(Phase.Starting, 0 to 45) as CreateCapsule.View.Live
        assertEquals(1, first.photo); assertEquals(45, first.photos)
        val last = CreateCapsule.view(Phase.Starting, 45 to 45) as CreateCapsule.View.Live
        assertEquals(45, last.photo)
        assertEquals(null, (CreateCapsule.view(Phase.Checking, 3 to 9) as CreateCapsule.View.Live).photo)   // nothing is uploaded during the check
    }

    @Test fun `the happy path is check, start, Making`() {
        assertEquals(Phase.Checking, run(E.Tap(true)).phase)
        assertEquals(Phase.Starting, run(E.Tap(true), E.CheckDone).phase)
        val done = run(E.Tap(true), E.CheckDone, E.Accepted)
        assertEquals(Phase.Idle, done.phase); assertEquals(End.Making, done.end)
        assertFalse(CreateCapsule.keepsDraft(done.end))
    }

    @Test fun `without a request check the tap goes straight to starting`() {
        assertEquals(Phase.Starting, run(E.Tap(false)).phase)
    }

    @Test fun `every other end leaves the capsule and keeps the draft`() {
        val ends = mapOf(
            run(E.Tap(true), E.CheckAsks) to End.Question, run(E.Tap(true), E.CheckRefuses) to End.Refusal, run(E.Tap(true), E.Cancel) to End.Restored,
            run(E.Tap(true), E.CheckDone, E.SendRefused) to End.Refusal, run(E.Tap(true), E.CheckDone, E.SendFailed) to End.Restored, run(E.Tap(false), E.SendFailed) to End.Restored,
        )
        for ((state, end) in ends) {
            assertEquals(Phase.Idle, state.phase); assertEquals(end, state.end)
            assertTrue(CreateCapsule.keepsDraft(state.end))
            assertEquals(CreateCapsule.View.Button, CreateCapsule.view(state.phase))
        }
    }

    @Test fun `while something runs a second tap changes nothing, and Cancel only works during the check`() {
        assertEquals(run(E.Tap(true)), run(E.Tap(true), E.Tap(true)))
        assertEquals(run(E.Tap(false)), run(E.Tap(false), E.Tap(true)))
        val sending = run(E.Tap(true), E.CheckDone)
        assertEquals(sending, CreateCapsule.next(sending, E.Cancel))
        assertEquals(End.Running, sending.end)
    }

    @Test fun `a late answer after the run ended is ignored`() {
        val cancelled = run(E.Tap(true), E.Cancel)
        assertEquals(cancelled, CreateCapsule.next(cancelled, E.CheckDone))
        assertEquals(cancelled, CreateCapsule.next(cancelled, E.Accepted))
    }

    @Test fun `no state is both running and showing the button`() {
        for (p in Phase.entries) assertEquals(p == Phase.Idle, CreateCapsule.view(p) is CreateCapsule.View.Button)
        for (p in Phase.entries) assertEquals(p != Phase.Idle, CreateSubmit.locked(p))
    }
}
