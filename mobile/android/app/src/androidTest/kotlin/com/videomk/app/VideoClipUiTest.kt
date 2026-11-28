package com.videomk.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Shader
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import com.videomk.app.core.ClipEntry
import com.videomk.app.core.ClipFailure
import com.videomk.app.core.ClipInfo
import com.videomk.app.core.ClipPhase
import com.videomk.app.core.VideoProblem
import com.videomk.app.ui.ComposerViewModel
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Assume
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * Video clips on the Create screen, every state, with fakes (no account, no network, no codec): the entries are put on screen the way the journey would.
 * `-e shots <folder>` takes the captures (Android/data/com.videomk.app/files/looks/<folder>/). Without it the test only checks that each state draws its words and marks.
 */
@RunWith(AndroidJUnit4::class)
class VideoClipUiTest {
    private val device get() = Ui.device
    private val files get() = Ui.context.filesDir
    private fun flag(name: String, content: String? = "") { File(files, name).let { if (content == null) it.delete() else it.writeText(content) } }
    private fun fakeToken(): String {
        val enc = java.util.Base64.getUrlEncoder().withoutPadding()
        return enc.encodeToString("{\"alg\":\"none\"}".toByteArray()) + "." + enc.encodeToString("{\"sub\":\"create-tester\",\"email\":\"create@example.com\",\"exp\":${System.currentTimeMillis() / 1000 + 86400}}".toByteArray()) + ".sig"
    }
    @Before fun setUp() {
        flag("fake_backend"); flag("fake_intake", "ok"); flag("fake_video", null)
        for (other in listOf("fake_plan", "fake_deck", "fake_balance", "fake_finish", "fake_media", "fake_making", "fake_many", "fake_empty_home", "fake_social", "fake_looks")) flag(other, null)
        flag("fake_no_finished", ""); flag("fake_balance", "11")
        Ui.context.getSharedPreferences("videomk_create", 0).edit().clear().commit()
    }
    @After fun tearDown() { flag("fake_video", null); flag("fake_no_finished", null); flag("fake_balance", null) }

    private fun composer(): ComposerViewModel {
        var vm: ComposerViewModel? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).first() as MainActivity
            vm = ViewModelProvider(activity)[ComposerViewModel::class.java]
        }
        return vm!!
    }
    private val shots: String? get() = InstrumentationRegistry.getArguments().getString("shots")
    private fun shot(name: String) {
        if (shots == null) return
        val dir = File(Ui.context.getExternalFilesDir(null), "looks/${shots}").apply { mkdirs() }
        device.takeScreenshot(File(dir, "$name.png"))
    }

    /** A stand-in poster: a soft two-colour scene, any shape. */
    private fun poster(w: Int, h: Int, a: Int, b: Int): ByteArray {
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        Canvas(bmp).apply {
            drawPaint(Paint().apply { shader = LinearGradient(0f, 0f, w.toFloat(), h.toFloat(), a, b, Shader.TileMode.CLAMP) })
            drawCircle(w * 0.7f, h * 0.35f, h * 0.16f, Paint().apply { color = 0xFFFFE9A8.toInt() })
            drawRect(0f, h * 0.72f, w.toFloat(), h.toFloat(), Paint().apply { color = 0x66000000 })
        }
        return ByteArrayOutputStream().also { bmp.compress(Bitmap.CompressFormat.JPEG, 85, it) }.toByteArray()
    }
    private val land = poster(640, 360, 0xFF2E6FA7.toInt(), 0xFF8EC6A0.toInt())
    private val port = poster(360, 640, 0xFFB5543C.toInt(), 0xFF3A2A5C.toInt())

    private fun info(id: String, audio: Boolean, state: String = if (audio) "speech" else "off", used: Boolean = audio, w: Int = 1920, h: Int = 1080) =
        ClipInfo(id, "ready", audio, 5.0, 18.0, true, true, used, state, w, h, null, null)

    private fun entry(id: String, phase: ClipPhase, portrait: Boolean = false, audio: Boolean? = false, info: ClipInfo? = null, dur: Long = 18_000) =
        ClipEntry(id, "clip", phase, audio, true, dur, if (portrait) 1080 else 1920, if (portrait) 1920 else 1080, if (portrait) port else land, if (info != null) id else null, info)

    private fun put(vararg e: ClipEntry) { val vm = composer(); InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.debugSetClips(e.toList()) }; Thread.sleep(700) }
    private fun failed(p: VideoProblem, msg: String? = null) = ClipPhase.Failed(ClipFailure(p, msg))

    /** The photo menu is a popup window: its rows are found by their text. */
    private fun menuRow() = device.wait(androidx.test.uiautomator.Until.findObject(androidx.test.uiautomator.By.text("Add a video")), 5_000) ?: error("no Add a video row")

    private fun openCreate() { Ui.launch(signedIn = true, tokens = fakeToken() to ""); Ui.openCreate(); Ui.require("sendButton"); Thread.sleep(600) }

    @Test fun states() {
        openCreate()
        // 1. the photo menu offers "Add a video"
        Ui.require("photoButton").click(); menuRow(); shot("01-menu"); device.pressBack(); Thread.sleep(300)
        // 2. the sound question, a long file (the notice names its length), nothing preselected
        put(entry("a", ClipPhase.AskSound, audio = null))
        Ui.require("clipSoundSheet", 5_000); Ui.require("clipNotice"); Ui.require("clipNoticeLonger"); Ui.require("clipKeepSound"); Ui.require("clipNoSound"); shot("02-sheet-long")
        // 3. a short file: only the one-line notice
        put(entry("a", ClipPhase.AskSound, audio = null, dur = 4_000))
        Ui.require("clipNotice"); assertTrue(Ui.waitGone("clipNoticeLonger", 4_000)); shot("03-sheet-short")
        // 4. getting ready, uploading, checking, slow (the same row, the status line says each in words)
        put(entry("a", ClipPhase.Preparing, audio = true)); Ui.require("clipStatusLine"); shot("04-preparing")
        put(entry("a", ClipPhase.Uploading(4_300_000, 10_000_000), audio = true)); Ui.require("clipStatusLine"); shot("05-uploading")
        put(entry("a", ClipPhase.Analysing(), audio = true)); Ui.require("clipStatusLine"); shot("06-checking")
        put(entry("a", ClipPhase.Analysing(slow = true), audio = true)); Ui.require("clipStatusLine"); shot("07-slow")
        // 5. ready: a landscape clip with sound and a portrait one without, each at its own shape
        put(entry("a", ClipPhase.Ready, audio = true, info = info("a", true)), entry("b", ClipPhase.Ready, portrait = true, audio = false, info = info("b", false, w = 1080, h = 1920)))
        Ui.require("clipTile"); Ui.require("clipChip"); Ui.require("clipSoundOn"); Ui.require("clipSoundOff"); Ui.require("clipCaption"); Ui.require("clipUsage"); shot("08-ready-two")
        // 6. one ready, one still being checked
        put(entry("a", ClipPhase.Ready, audio = true, info = info("a", true)), entry("b", ClipPhase.Analysing(), portrait = true, audio = false)); Ui.require("clipStatusLine"); shot("09-ready-and-checking")
        // 7. the sound could not be used: the clip is still there, one calm line
        put(entry("a", ClipPhase.Ready, audio = true, info = info("a", true, state = "unscreened", used = false))); Ui.require("clipStatusLine"); shot("10-sound-dropped")
        // 8. each failure, with its one action
        put(entry("a", failed(VideoProblem.Rejected))); Ui.require("clipFailure"); assertTrue(!Ui.has("clipRetry")); shot("11-rejected")
        put(entry("a", failed(VideoProblem.CheckFailed))); Ui.require("clipRetry"); shot("12-check-failed")
        put(entry("a", failed(VideoProblem.Offline))); Ui.require("clipRetry"); shot("13-offline")
        put(entry("a", failed(VideoProblem.TooLarge))); Ui.require("clipFailure"); shot("14-too-large")
        put(entry("a", failed(VideoProblem.Stalled))); Ui.require("clipKeepWaiting"); shot("15-stalled")
        put(entry("a", failed(VideoProblem.DailyLimit))); Ui.require("clipFailure"); shot("16-daily")
        put()
    }

    @Test fun limits() {
        for (mode in listOf("paused", "daily", "plan")) {
            flag("fake_video", mode)
            openCreate()
            Ui.require("photoButton").click(); menuRow(); shot("20-menu-$mode"); device.pressBack(); Thread.sleep(300)
        }
        flag("fake_video", "off"); openCreate()
        Ui.require("photoButton").click(); Thread.sleep(500)
        assertTrue("the row is absent where the server does not offer the feature", !device.hasObject(androidx.test.uiautomator.By.text("Add a video"))); shot("20-menu-off"); device.pressBack()
    }
}
