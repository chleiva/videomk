package com.videomk.app

import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import com.videomk.app.ui.AppViewModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Fast checks against the QA backend (no video is made). Needs `vmk_id_token` for the signed-in ones; those are skipped without it. */
@RunWith(AndroidJUnit4::class)
class QuickUiTest {
    private val device get() = Ui.device

    @Test fun signedOutUserSeesSignIn() {
        Ui.launch(signedIn = false)
        Ui.require("signInButton")
        assertTrue(device.hasObject(By.text("videomk")))
        assertFalse(Ui.has("composerField"))
        Ui.shot("01-signin")
    }

    @Test fun signedInLibraryLoadsWithComposerAndCredits() {
        Ui.launch(signedIn = true)
        Ui.require("composerField", 30_000)
        Ui.require("micButton"); Ui.require("photoButton"); Ui.require("optionsMenu")
        Ui.require("balanceChip", 20_000)
        Ui.require("sendButton")   // the send button is always drawn (tonal until there is something to send)
        assertTrue(Ui.require("costLine").text.startsWith("A 3 minute video"))
        assertFalse(Ui.has("signInButton"))
        Ui.shot("02-library")
    }

    @Test fun composerShowsCostAndLengthMenuChangesIt() {
        Ui.launch(signedIn = true)
        val field = Ui.require("composerField", 30_000)
        field.click(); field.text = "Why is the sky blue? A short explanation."
        Ui.require("sendButton")
        assertTrue(Ui.require("costLine").text.startsWith("3 credits"))   // default length is 3 minutes
        Ui.require("optionsMenu").click()
        Ui.require("length-1").click()
        Ui.require("optionsDone").click()
        assertTrue(Ui.require("costLine").text.startsWith("1 credit"))
        Ui.require("optionsMenu").click(); Ui.shot("03-options")
        Ui.require("look-paper").click()
        Ui.require("optionsDone").click()
        Ui.shot("04-composer-filled")
    }

    @Test fun optionsMenuHasASubtitlesSwitchThatIsOnByDefault() {
        Ui.launch(signedIn = true)
        Ui.require("optionsMenu", 30_000).click()
        val sw = device.wait(Until.findObject(By.text("Subtitles")), 10_000) ?: error("Subtitles item not in the options menu")
        Ui.shot("14-options-subtitles")
        sw.click()   // turn off: the menu stays open
        Thread.sleep(500)
        Ui.shot("14b-options-subtitles-off")
        device.pressBack()
        Ui.require("optionsMenu").click()   // reopening keeps the choice
        assertTrue(device.wait(Until.hasObject(By.text("Subtitles")), 5_000))
        Ui.shot("14c-options-reopened")
        device.pressBack()
        assertTrue(Ui.appIsForeground())
    }

    /** Needs a Ready video in the QA library (E2ETest.a makes one). Toggling the switch makes Preview and Publish available; nothing is sent. */
    @Test fun editorShowsASubtitlesSwitchThatCountsAsAChange() {
        Ui.launch(signedIn = true)
        (device.wait(Until.findObject(By.res("videoRow").hasDescendant(By.text("Ready"))), 30_000) ?: error("needs a Ready video")).click()
        Ui.require("editButton", 30_000).click()
        Ui.require("captionsToggle", 30_000)
        assertTrue(device.hasObject(By.text("Subtitles")))
        assertFalse(device.findObject(By.res("previewButton"))!!.isEnabled)
        Ui.require("captionsToggle").click()
        Thread.sleep(500)
        assertTrue("turning subtitles off is an edit", device.findObject(By.res("previewButton"))!!.isEnabled)
        Ui.shot("15-editor-subtitles")
        Ui.require("captionsToggle").click()
        Thread.sleep(500)
        assertFalse("turning them back on is no edit", device.findObject(By.res("previewButton"))!!.isEnabled)
    }

    @Test fun creditsScreenShowsBalanceAndSettingsCanSignOut() {
        Ui.launch(signedIn = true)
        Ui.require("balanceChip", 30_000).click()
        val value = Ui.require("balanceValue")
        assertEquals("∞", value.text)   // the QA test user has unlimited credits
        Ui.require("bucketRow"); Ui.shot("05-credits")
        device.pressBack()
        Ui.require("settingsButton").click()
        assertEquals("qa-android@videomk.test", Ui.require("accountEmail").text)
        Ui.shot("06-settings")
        Ui.require("signOutButton").click(); Ui.clickText("Sign out of videomk?", exists = true); device.findObjects(By.text("Sign out")).last().click()
        Ui.require("signInButton")
        assertFalse(Ui.has("composerField"))
    }

    /** An expired ID token with a good refresh token: the app refreshes silently and the library loads, as if nothing happened. */
    @Test fun expiredIdTokenIsRefreshedTransparently() {
        Ui.launch(signedIn = true, tokens = Ui.staleIdToken() to Ui.refreshTokenOrSkip())
        Ui.require("composerField", 30_000)
        Ui.require("balanceChip", 20_000)   // the wallet call needed the refreshed token
        assertFalse(Ui.has("signInButton"))
        Ui.shot("11-after-silent-refresh")
    }

    /** A revoked/invalid refresh token: back to the sign-in screen with no crash and no error spam. */
    @Test fun revokedRefreshTokenSignsOutGracefully() {
        Ui.launch(signedIn = true, tokens = Ui.staleIdToken() to "not-a-real-refresh-token")
        Ui.require("signInButton", 30_000)
        assertFalse(Ui.has("composerField"))
        assertTrue(Ui.appIsForeground())
        Ui.shot("12-signed-out-after-revoked")
    }

    /** The iOS root task ran twice after a rotation. Here the start work must run once however often the activity is recreated. */
    @Test fun rotationKeepsTheSessionAndDoesNotRestartTheApp() {
        Ui.launch(signedIn = true)
        Ui.require("composerField", 30_000).apply { click(); text = "A half typed brief that survives" }
        fun startCount(): Int {
            var n = -1
            instrumentationActivity { n = ViewModelProvider(it)[AppViewModel::class.java].startCount }
            return n
        }
        assertEquals(1, startCount())
        repeat(3) {
            device.setOrientationLandscape(); Thread.sleep(1500)
            Ui.require("composerField")
            device.setOrientationPortrait(); Thread.sleep(1500)
            Ui.require("composerField")
        }
        device.unfreezeRotation()
        assertEquals("start() must not run again after rotations", 1, startCount())
        assertFalse(Ui.has("signInButton"))
        assertEquals("A half typed brief that survives", Ui.require("composerField").text)
        Ui.shot("07-after-rotation")
    }

    private fun instrumentationActivity(block: (MainActivity) -> Unit) {
        val am = Ui.instrumentation
        am.runOnMainSync {
            val resumed = androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(androidx.test.runner.lifecycle.Stage.RESUMED)
            (resumed.firstOrNull { it is MainActivity } as? MainActivity)?.let(block)
        }
    }

    /** The real system photo picker (no permission needed): pick the pushed photos, they appear cleaned in the composer, and one can be removed. */
    @Test fun systemPhotoPickerAttachesPhotos() {
        Ui.launch(signedIn = true)
        Ui.require("photoButton", 30_000).click()
        Ui.require("pickFromPhone", 10_000).click()   // the Add photos sheet opens the system picker from its This phone tab
        val picker = "com.google.android.providers.media.module"
        val tiles = device.wait(Until.findObjects(By.res("$picker:id/icon_thumbnail")), 15_000)
        org.junit.Assume.assumeTrue("no photos on the device (push p1..p4.jpg to /sdcard/Pictures)", !tiles.isNullOrEmpty())
        tiles.take(4).forEach { it.click() }
        device.wait(Until.findObject(By.res("$picker:id/button_add")), 5_000)!!.click()
        Ui.require("addPhotosDone", 30_000).click()   // the photos are in the strip already; Add closes the sheet
        Ui.require("photosNote", 30_000)
        assertTrue("all four picked photos get attached", device.wait(Until.hasObject(By.res("photosNote").textStartsWith("4 of 100 photos")), 30_000))
        assertEquals(4, device.findObjects(Ui.res("attachedPhoto")).size)
        Ui.shot("13-picker-attached")
        device.findObjects(By.desc("Remove photo 1")).first().click()
        Thread.sleep(500)
        assertEquals(3, device.findObjects(Ui.res("attachedPhoto")).size)
    }

    @Test fun attachedPhotosShowInTheComposerAndCanBeRemoved() {
        Ui.launch(signedIn = true, photoFiles = "${Ui.context.filesDir}/p1.jpg:${Ui.context.filesDir}/p2.jpg:${Ui.context.filesDir}/p3.jpg")
        Ui.require("photosNote", 30_000)
        assertEquals(3, device.findObjects(Ui.res("attachedPhoto")).size)
        Ui.require("composerField").apply { click(); text = "Tell the story of these three photos." }
        Ui.shot("10-photos-attached")
        assertTrue(Ui.require("photosNote").text.startsWith("3 of 100 photos"))
        ActivityScenario.launch(MainActivity::class.java).close()   // a second launch must not duplicate anything
    }
}
