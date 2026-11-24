package com.videomk.app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.FixMethodOrder
import org.junit.Test
import org.junit.runners.MethodSorters
import org.junit.runner.RunWith

/**
 * The whole product on the QA backend. Step a makes ONE real 1-minute video from 4 photos (a few cents, about 5 minutes); b plays the newest ready video, goes full screen
 * and back; c opens the editor, edits a narration and renders a preview. b and c can be run alone with `E2ETest#b_...` (they reuse a ready video). Needs `vmk_id_token` and the photos in the app's files dir.
 */
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
@RunWith(AndroidJUnit4::class)
class E2ETest {
    private val device get() = Ui.device
    private fun photos() = (1..4).joinToString(":") { "${Ui.context.filesDir}/p$it.jpg" }

    @Test fun a_makeAVideoFromFourPhotos() {
        Ui.launch(signedIn = true, minutes = "1", photoFiles = photos())
        Ui.require("photosNote", 30_000)
        assertEquals(4, device.findObjects(Ui.res("attachedPhoto")).size)
        Ui.require("composerField").apply { click(); text = "A short video about these four photos and what they show." }
        Ui.shot("20-before-send")
        assertTrue(Ui.require("costLine").text.startsWith("1 credit"))
        Ui.require("sendButton").click()

        // a placeholder row at once (uploading photos), the composer is free again
        val appeared = Ui.find("pendingRow", 10_000) ?: Ui.find("runningRow", 30_000)
        assertFalse("the request failed", Ui.has("failedRow"))
        assertTrue("a row for the new video appears", appeared != null)
        assertFalse("composer cleared", Ui.has("sendButton"))
        assertFalse("photos cleared", Ui.has("attachedPhoto"))
        Ui.shot("21-uploading")
        Ui.require("runningRow", 90_000)
        Ui.shot("22-running")

        // it finishes in place
        val deadline = System.currentTimeMillis() + 12 * 60_000
        while ((Ui.has("runningRow") || Ui.has("pendingRow")) && System.currentTimeMillis() < deadline) Thread.sleep(5000)
        assertFalse("video did not finish in time", Ui.has("runningRow") || Ui.has("pendingRow"))
        assertFalse("the video failed", Ui.has("failedRow"))
        Ui.require("videoRow")
        assertTrue("Ready", device.hasObject(By.res("videoRow").hasDescendant(By.text("Ready"))))
        Ui.shot("23-ready")
    }

    private fun openReadyVideo() {
        Ui.launch(signedIn = true)
        val ready = device.wait(Until.findObject(By.res("videoRow").hasDescendant(By.text("Ready"))), 30_000) ?: error("needs a Ready video in the library (run a_makeAVideoFromFourPhotos first)")
        ready.click()
        Ui.require("player", 30_000)
        Ui.require("fullScreenButton", 30_000)
    }

    @Test fun b_playAndFullScreen() {
        openReadyVideo()
        Thread.sleep(4000)
        Ui.shot("24-player")
        Ui.require("fullScreenButton").click()
        Ui.require("closeFullScreenButton", 15_000)
        val t = System.currentTimeMillis() + 10_000
        while (device.displayWidth <= device.displayHeight && System.currentTimeMillis() < t) Thread.sleep(300)
        Thread.sleep(2500)
        assertTrue("full screen is landscape", device.displayWidth > device.displayHeight)
        Ui.shot("25-fullscreen")
        Ui.require("closeFullScreenButton").click()
        Ui.require("fullScreenButton", 15_000)
        val t2 = System.currentTimeMillis() + 10_000
        while (device.displayWidth > device.displayHeight && System.currentTimeMillis() < t2) Thread.sleep(300)
        assertTrue("back to portrait", device.displayHeight > device.displayWidth)
        assertTrue(Ui.appIsForeground())
        Ui.shot("25b-back")
    }

    @Test fun c_editorEditsANarrationAndRendersAPreview() {
        openReadyVideo()
        Ui.require("editButton", 20_000).click()
        Ui.require("beatRow", 30_000)
        Ui.shot("26-editor")
        assertFalse("nothing edited yet", device.findObject(By.res("previewButton"))!!.isEnabled)
        assertTrue("the editor shows the Subtitles switch", Ui.has("captionsToggle") && device.hasObject(By.text("Subtitles")))
        device.findObjects(Ui.res("beatRow")).first().click()
        val field = Ui.require("narrationField")
        field.click()
        field.text = "This is my edited narration for the very first scene of the video."
        Ui.shot("27-scene")
        Ui.require("beatDone").click()
        Ui.require("beatRow")
        assertTrue("Edited marker", device.hasObject(By.text("Edited")))
        assertTrue("Preview is enabled after an edit", device.findObject(By.res("previewButton"))!!.isEnabled)
        Ui.shot("28-edited")
        Ui.require("previewButton").click()
        Ui.require("renderingView", 30_000)
        Ui.shot("29-rendering")
        Ui.require("doneTitle", 10 * 60_000)
        Ui.shot("30-preview-ready")
        assertTrue(device.hasObject(By.text("Preview ready")))
    }
}
