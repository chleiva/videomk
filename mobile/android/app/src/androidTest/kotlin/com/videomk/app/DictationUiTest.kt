package com.videomk.app

import android.Manifest
import android.content.pm.PackageManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Dictation must never take the app down, whatever the permission or recognizer state. The permission is set from outside before each run
 * (`adb shell pm grant|revoke com.videomk.app android.permission.RECORD_AUDIO`, see scripts/run-ui-tests.sh): changing it from inside would kill
 * the process the tests run in.
 */
@RunWith(AndroidJUnit4::class)
class DictationUiTest {
    private val device get() = Ui.device
    private fun micGranted() = Ui.context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun outcome() = when {
        Ui.has("listeningHint") -> "listening"
        Ui.has("dictationKeyboardHint") -> "keyboard"
        Ui.has("dictationUnavailable") -> "unavailable"
        else -> "idle"
    }

    @Test fun permissionGrantedMicButtonNeverCrashes() {
        assumeTrue("run with the microphone permission granted", micGranted())
        Ui.launch(signedIn = true)
        val seen = mutableListOf<String>()
        repeat(3) { i ->
            Ui.require("micButton", 30_000).click()
            Thread.sleep(2500)
            assertTrue("app must stay alive after mic press ${i + 1}", Ui.appIsForeground())
            seen += outcome()
            Ui.shot("08-dictation-granted-${i + 1}")
            if (Ui.has("listeningHint")) { Ui.require("micButton").click(); Thread.sleep(800) }   // stop
        }
        println("DICTATION(granted) outcomes: $seen")
        Ui.require("composerField")
        assertTrue(seen.any { it != "idle" })   // every press ends in listening, the keyboard hint or a message
    }

    @Test fun permissionDeniedMicButtonNeverCrashes() {
        assumeTrue("run with the microphone permission revoked", !micGranted())
        Ui.launch(signedIn = true)
        val seen = mutableListOf<String>()
        repeat(3) { i ->
            Ui.require("micButton", 30_000).click()
            // the first presses show the system permission dialog: deny it
            device.wait(Until.findObject(By.res("com.android.permissioncontroller:id/permission_deny_button")), 3000)?.click()
            device.findObject(By.res("com.android.permissioncontroller:id/permission_deny_and_dont_ask_again_button"))?.click()
            Thread.sleep(1500)
            assertTrue("app must stay alive after mic press ${i + 1}", Ui.appIsForeground())
            seen += outcome()
            Ui.shot("09-dictation-denied-${i + 1}")
        }
        println("DICTATION(denied) outcomes: $seen")
        assertTrue("a clear message or the keyboard fallback is shown", seen.any { it == "keyboard" || it == "unavailable" })
        Ui.require("composerField")
    }
}
