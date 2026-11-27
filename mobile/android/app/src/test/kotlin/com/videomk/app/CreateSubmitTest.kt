package com.videomk.app

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
