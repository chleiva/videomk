package com.videomk.app

import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import com.videomk.app.ui.AppViewModel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * ONE real request against the QA backend (it costs a credit and makes a 30 second video): Cartoon with Fox and Bruno, chosen through the pickers.
 * Needs the QA tokens (`-e vmk_id_token ... -e vmk_refresh_token ...`, see scripts/run-ui-tests.sh) and an app started without the fake-server files.
 * What the server answers (`look` in the 202) is what it read from the request, so it proves the body.
 */
@RunWith(AndroidJUnit4::class)
class LookQaTest {
    @Test fun cartoonWithFoxAndBearStartsOnTheRealServer() {
        Ui.requireTokens()
        for (f in listOf("fake_backend", "fake_intake", "fake_looks", "fake_media", "fake_deck", "fake_plan", "fake_balance", "fake_finish")) File(Ui.context.filesDir, f).delete()
        Ui.launch(signedIn = true)
        Ui.openCreate()
        Ui.require("composerField").text = "How bees make honey, explained for kids"
        Ui.pickLength("30 s")
        Ui.require("pillLook").click()
        Ui.require("lookSheet", 20_000)      // the real server lists looks.look
        for (id in listOf("auto", "real", "whiteboard", "cartoon")) Ui.require("lookTile-$id")
        Ui.shot("qa-look-sheet")
        Ui.require("lookTile-cartoon").click()
        assertTrue(Ui.waitGone("lookSheet", 5_000))
        Ui.require("pillCast").click()
        Ui.require("castSheet"); Thread.sleep(500)
        Ui.require("cast-fox").click(); Ui.require("cast-bear").click()
        Ui.shot("qa-characters")
        Ui.require("castDone").click(); Ui.waitGone("castSheet", 5_000)
        Ui.shot("qa-create")
        Ui.require("sendButton").click()
        // a question from the request check is skipped: the video is made as asked
        val deadline = System.currentTimeMillis() + 90_000
        while (System.currentTimeMillis() < deadline && !Ui.has("runningRow")) {
            Ui.device.findObject(By.res("makeItNow"))?.click()
            Ui.device.findObject(By.res("summaryCreate"))?.click()
            Ui.device.wait(Until.hasObject(Ui.res("runningRow")), 2_000)
        }
        Ui.shot("qa-after-create")
        var looks: Map<String, com.videomk.app.core.AppliedLook> = emptyMap()
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).first() as MainActivity
            looks = ViewModelProvider(activity)[AppViewModel::class.java].state.value.startedLooks
        }
        val look = looks.values.lastOrNull()
        assertNotNull("the server's 202 carried no look: $looks", look)
        android.util.Log.i("LookQaTest", "started video ${looks.keys.last()} look=$look")
        assertEquals("cartoon", look!!.chosen); assertEquals("cartoon", look.applied); assertEquals(listOf("fox", "bear"), look.cast)
    }
}
