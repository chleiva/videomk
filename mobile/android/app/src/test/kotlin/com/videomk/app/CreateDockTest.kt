package com.videomk.app

import com.videomk.app.core.CreateDock
import com.videomk.app.core.CreateDock.Caption
import com.videomk.app.core.CreateDock.CreateState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The decisions of the Create v2 dock (docs/design_bar/CREATE_SCREEN_ANDROID_VALUES.md). */
class CreateDockTest {
    @Test fun `create is inactive until it can send, active with a fix on offer, creating once sent`() {
        assertEquals(CreateState.Inactive, CreateDock.createState(ready = false, hasOffer = false, creating = false))
        assertEquals(CreateState.Active, CreateDock.createState(ready = true, hasOffer = false, creating = false))
        assertEquals(CreateState.Active, CreateDock.createState(ready = false, hasOffer = true, creating = false))
        assertEquals(CreateState.Creating, CreateDock.createState(ready = true, hasOffer = false, creating = true))
    }

    @Test fun `the first video teaches the price once`() {
        assertEquals(Caption.FirstVideo(2, 11), CreateDock.caption(calm = true, balance = 11, cost = 2, hasFinishedVideo = false))
        assertEquals(Caption.FirstVideo(1, 1), CreateDock.caption(calm = true, balance = 1, cost = 1, hasFinishedVideo = false))
    }

    @Test fun `after the first video the caption returns only when the balance is low`() {
        assertEquals(Caption.None, CreateDock.caption(true, balance = 11, cost = 2, hasFinishedVideo = true))
        assertEquals(Caption.None, CreateDock.caption(true, balance = 4, cost = 2, hasFinishedVideo = true))
        assertEquals(Caption.Low(3), CreateDock.caption(true, balance = 3, cost = 2, hasFinishedVideo = true))
    }

    @Test fun `no caption when something is wrong, the price is unknown, the balance is unlimited or cannot pay`() {
        assertEquals(Caption.None, CreateDock.caption(calm = false, balance = 11, cost = 2, hasFinishedVideo = false))
        assertEquals(Caption.None, CreateDock.caption(true, balance = 11, cost = 2, hasFinishedVideo = false, priceKnown = false))
        assertEquals(Caption.None, CreateDock.caption(true, balance = null, cost = 2, hasFinishedVideo = false))
        assertEquals(Caption.None, CreateDock.caption(true, balance = 1, cost = 2, hasFinishedVideo = false))   // "needs 2 credits, you have 1" takes over
    }

    @Test fun `an unreadable list counts as a finished video so nothing guesses`() {
        assertTrue(CreateDock.hasFinishedVideo(listLoaded = false, anyComplete = false))
        assertFalse(CreateDock.hasFinishedVideo(listLoaded = true, anyComplete = false))
        assertTrue(CreateDock.hasFinishedVideo(listLoaded = true, anyComplete = true))
    }

    @Test fun `chips are three, two on a short window, none where one row does not fit`() {
        assertEquals(3, CreateDock.chipCount(800f)); assertEquals(3, CreateDock.chipCount(640f)); assertEquals(2, CreateDock.chipCount(639f)); assertEquals(2, CreateDock.chipCount(340f)); assertEquals(0, CreateDock.chipCount(339f))
    }

    @Test fun `chips only while the field is empty and before the first finished video`() {
        assertTrue(CreateDock.showExamples(textEmpty = true, typing = false, attached = false, listening = false, locked = false, hasFinishedVideo = false))
        assertFalse(CreateDock.showExamples(false, false, false, false, false, false))
        assertFalse(CreateDock.showExamples(true, true, false, false, false, false))
        assertFalse(CreateDock.showExamples(true, false, true, false, false, false))
        assertFalse(CreateDock.showExamples(true, false, false, true, false, false))
        assertFalse(CreateDock.showExamples(true, false, false, false, true, false))
        assertFalse(CreateDock.showExamples(true, false, false, false, false, true))
    }

    @Test fun `create drops to its own row at 150 percent text or when it does not fit`() {
        assertFalse(CreateDock.createOnOwnRow(1.0f, toolsWidth = 200, createWidth = 112, gap = 4, available = 320))
        assertFalse(CreateDock.createOnOwnRow(1.3f, 200, 112, 4, 320))
        assertTrue(CreateDock.createOnOwnRow(1.5f, 100, 100, 4, 800))
        assertTrue(CreateDock.createOnOwnRow(1.0f, 210, 112, 4, 320))   // 326 > 320
        assertFalse(CreateDock.createOnOwnRow(1.0f, 204, 112, 4, 320))  // exactly 320
    }
}
