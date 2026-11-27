package com.videomk.app

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import com.videomk.app.core.LookChoice
import com.videomk.app.ui.ComposerViewModel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * The Look picker and the Characters picker on Create, on the debug build's fake server (no account, no network): `files/fake_backend`, `fake_intake` and
 * `fake_looks` (the backend's own capabilities answer). Run this class in its own `am instrument` call, on a freshly started app: the fakes are chosen when the
 * app's container is first used. `-e shots <folder>` also takes the captures of every state (the same list and names as the iPhone review set) into
 * `Android/data/com.videomk.app/files/looks/<folder>/`.
 */
@RunWith(AndroidJUnit4::class)
class LookUiTest {
    private val device get() = Ui.device
    private val files get() = Ui.context.filesDir
    private val prompt = "How bees make honey, explained for kids"

    private fun flag(name: String, content: String? = "") { File(files, name).let { if (content == null) it.delete() else it.writeText(content) } }

    /** An unsigned token that only looks like a session: the fake server never checks it. */
    private fun fakeToken(): String {
        val enc = java.util.Base64.getUrlEncoder().withoutPadding()
        return enc.encodeToString("{\"alg\":\"none\"}".toByteArray()) + "." + enc.encodeToString("{\"sub\":\"look-tester\",\"email\":\"look@example.com\",\"exp\":${System.currentTimeMillis() / 1000 + 86400}}".toByteArray()) + ".sig"
    }

    @Before fun setUp() {
        flag("fake_backend"); flag("fake_intake", "ok"); flag("fake_looks")
        for (other in listOf("fake_plan", "fake_deck", "fake_balance", "fake_finish", "fake_media", "fake_making", "fake_many", "fake_empty_home", "fake_social")) flag(other, null)      // what an earlier screenshot session left behind
        forget()      // the last choice is remembered: every test starts from none
        FakeDebugBackend.lastStart = null
    }

    @After fun tearDown() { flag("fake_looks", null) }

    private fun forget() { Ui.context.getSharedPreferences("videomk_create", 0).edit().clear().commit() }

    /** [fresh]: without the choices remembered from the video made a moment ago. */
    private fun open(looks: String? = "", text: String? = prompt, fresh: Boolean = false) {
        if (fresh) forget()
        flag("fake_looks", looks)
        Ui.launch(signedIn = true, tokens = fakeToken() to "")
        Ui.openCreate()
        if (text != null) Ui.require("composerField").text = text
        Ui.require("pillLook")
    }

    /** A pill says "<what it is>: <its value>" to TalkBack; the value is what is drawn. */
    private fun pillText(tag: String): String {
        repeat(10) {
            desc(tag).takeIf { it.isNotEmpty() }?.let { return it.substringAfter(": ") }
            Ui.require(tag).findObjects(By.clazz("android.widget.TextView")).firstNotNullOfOrNull { it.text?.takeIf { t -> t.isNotEmpty() } }?.let { return it }      // the word drawn in the pill
            Thread.sleep(300)
        }
        error("'$tag' says nothing")
    }
    // a tagged element that speaks as one (a pill, a tile, a face) is two nodes for UiAutomator: the tagged one and, inside it, the one that carries what TalkBack says
    private fun nodes(tag: String) = Ui.require(tag).let { listOf(it) + it.children }
    private fun desc(tag: String): String = nodes(tag).firstNotNullOfOrNull { it.contentDescription?.takeIf { d -> d.isNotEmpty() } }.orEmpty()
    private fun text(tag: String): String = nodes(tag).firstNotNullOfOrNull { it.text?.takeIf { d -> d.isNotEmpty() } }.orEmpty()
    private fun selected(tag: String) = nodes(tag).any { it.isSelected || it.isChecked }      // a chosen tile is a selected radio button
    private fun checked(tag: String) = nodes(tag).any { it.isChecked }
    private fun enabled(tag: String) = nodes(tag).all { it.isEnabled }
    private fun findVideo(title: String) = run {
        Ui.waitGone("createScreen", 10_000); Ui.require("videoList", 20_000)
        device.wait(Until.findObject(By.res("videoRow").hasDescendant(By.textContains(title))), 20_000) ?: error("'$title' is not on the list")
    }
    /** Info is there once the video's description has arrived: tapped until its sheet shows the look. */
    private fun openInfo() { Ui.require("infoButton", 20_000); repeat(8) { Ui.require("infoButton").click(); if (Ui.find("infoLook", 2_500) != null) return }; error("Info did not open") }
    private fun openNewVideo() { (device.wait(Until.findObject(By.res("runningRow").hasDescendant(By.descContains("explained for kids"))), 20_000) ?: error("the new video is not being made")).click() }
    private fun pickLook(id: String) { Ui.require("pillLook").click(); Ui.require("lookTile-$id").click(); assertTrue("the Look sheet closes by itself after a pick", Ui.waitGone("lookSheet", 4_000)) }
    private fun openCast() { Ui.require("pillCast").click(); Ui.require("castSheet"); Thread.sleep(500) }
    private fun closeCast() { Ui.require("castDone").click(); Ui.waitGone("castSheet", 4_000) }
    private fun castLine(): String = text("castLine")

    private fun composer(): ComposerViewModel {
        var vm: ComposerViewModel? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).first() as MainActivity
            vm = ViewModelProvider(activity)[ComposerViewModel::class.java]
        }
        return vm!!
    }

    /** Photos chosen after the look: three small pictures made here, attached the way the photo picker's answer is. */
    private fun attachPhotos() {
        val paths = listOf(Color.rgb(64, 160, 120), Color.rgb(160, 150, 70), Color.rgb(170, 70, 120)).mapIndexed { i, c ->
            val b = Bitmap.createBitmap(640, 480, Bitmap.Config.ARGB_8888)
            Canvas(b).apply { drawColor(c); drawCircle(380f, 150f, 40f, Paint().apply { color = Color.argb(120, 255, 255, 255) }); drawOval(-80f, 320f, 720f, 640f, Paint().apply { color = Color.argb(140, 0, 0, 0) }) }
            File(files, "look_photo_$i.jpg").also { f -> f.outputStream().use { b.compress(Bitmap.CompressFormat.JPEG, 85, it) } }.path
        }
        val vm = composer()
        InstrumentationRegistry.getInstrumentation().runOnMainSync { vm.addPhotoFiles(paths) }
        Ui.require("photoStrip")
        device.wait(Until.gone(Ui.res("photosPreparing")), 15_000)
    }

    // ---- flows

    @Test fun cartoonWithTwoCharactersAndTheBoardIsSentAndRemembered() {
        open()
        assertEquals("Auto", pillText("pillLook"))
        assertFalse("no Characters pill for Auto", Ui.has("pillCast"))
        Ui.require("pillLook").click()
        Ui.require("lookSheet")
        for (id in listOf("auto", "real", "whiteboard", "cartoon")) Ui.require("lookTile-$id")
        assertTrue(selected("lookTile-auto")); assertFalse(selected("lookTile-cartoon"))
        assertEquals("Cartoon, Characters explain it", desc("lookTile-cartoon"))
        Ui.require("lookTile-cartoon").click()
        assertTrue("one tap chooses and closes", Ui.waitGone("lookSheet", 4_000))
        assertEquals("Cartoon", pillText("pillLook"))
        assertEquals("Characters: Auto", desc("pillCast"))

        openCast()
        assertEquals("We pick for you. Or choose up to 3.", castLine())
        Ui.require("cast-fox").click(); assertEquals("Fox presents.", castLine()); assertTrue(checked("cast-fox"))
        Ui.require("cast-bear").click(); assertEquals("Fox and Bruno talk it through.", castLine())
        Ui.require("cast-cat").click(); assertEquals("Fox, Bruno and Mika talk it through.", castLine())
        assertFalse("at three the others wait, dimmed", enabled("cast-ines"))
        Ui.require("cast-ines").click(); assertEquals("Fox, Bruno and Mika talk it through.", castLine())
        Ui.require("cast-cat").click(); assertTrue(enabled("cast-ines"))
        assertTrue("the switch is labelled by the server", desc("extra-board").startsWith("Characters explain at a board"))
        Ui.require("extra-board").click()
        assertTrue("the Characters sheet stays until it is closed", Ui.has("castSheet"))
        closeCast()
        assertEquals("Characters: Fox and Bruno, Characters explain at a board", desc("pillCast"))

        Ui.require("sendButton").click()
        Ui.require("runningRow", 20_000)
        assertEquals(LookChoice("cartoon", listOf("fox", "bear"), listOf("board")), FakeDebugBackend.lastStart!!.lookChoice)
        assertEquals("auto", FakeDebugBackend.lastStart!!.style)

        // the last choice is remembered for the next video
        Ui.openCreate()
        assertEquals("Cartoon", pillText("pillLook"))
        assertEquals("Characters: Fox and Bruno, Characters explain at a board", desc("pillCast"))
    }

    @Test fun photosAfterCartoonGoBackToAutoWithOneLineAndDimTheDrawnLooks() {
        open()
        pickLook("cartoon")
        Ui.require("pillCast")
        attachPhotos()
        assertEquals("Look set to Auto. Cartoon can't use your photos.", text("lookNotice"))
        assertEquals("Auto", pillText("pillLook"))
        assertFalse(Ui.has("pillCast"))
        Ui.require("pillLook").click()
        Ui.require("lookSheet")
        assertFalse("the line leaves at the next touch of the pill", Ui.has("lookNotice"))
        assertEquals("Whiteboard, Not with photos", desc("lookTile-whiteboard"))
        assertFalse(enabled("lookTile-cartoon")); assertTrue(enabled("lookTile-real"))
        Ui.require("lookTile-cartoon").click()
        Thread.sleep(800)
        assertTrue("a dimmed tile changes nothing and closes nothing", Ui.has("lookSheet"))
        Ui.require("lookTile-real").click()
        assertTrue(Ui.waitGone("lookSheet", 4_000))
        assertEquals("Real", pillText("pillLook"))
    }

    @Test fun aConversationInATooShortVideoMovesTheLengthAndTheServersNoteShowsOnMaking() {
        open()
        Ui.pickLength("15 s")
        pickLook("cartoon")
        openCast()
        Ui.require("cast-fox").click(); Ui.require("cast-bear").click()
        assertEquals("Length changed to 30 s. A conversation needs 20 s or more.", castLine())
        closeCast()
        assertEquals("30 s", pillText("pillLength"))
        // the person shortens it again: one quiet line offers the way back, and the video is still made
        Ui.pickLength("15 s")
        Ui.require("lookLengthHint"); Ui.require("lookLengthFix")
        Ui.require("sendButton").click()
        openNewVideo()
        assertEquals("One character presents. A conversation needs 20 s or more.", Ui.require("lookNote", 20_000).text)
    }

    @Test fun aLookWithItsOwnMinimumMovesTheLengthAndSaysSoAboveThePills() {
        open(looks = "minlen")
        Ui.pickLength("15 s")
        pickLook("whiteboard")
        assertEquals("Length changed to 30 s. Whiteboard needs 30 s or more.", text("lookNotice"))
        assertEquals("30 s", pillText("pillLength"))
        assertFalse(Ui.has("pillCast"))
    }

    @Test fun aPlanLockedLookIsDimmedAndAHiddenOneIsGone() {
        open(looks = "plan")
        Ui.require("pillLook").click()
        assertEquals("Cartoon, Pro plan", desc("lookTile-cartoon"))
        assertFalse(enabled("lookTile-cartoon"))
        Ui.require("lookDone").click(); Ui.waitGone("lookSheet", 4_000)
        open(looks = "hidden")
        Ui.require("pillLook").click()
        Ui.require("lookTile-cartoon")
        assertFalse(Ui.has("lookTile-whiteboard"))
    }

    @Test fun anOlderServerKeepsTheMenuAndSendsNothingNew() {
        open(looks = null)
        assertFalse(Ui.has("pillCast"))
        Ui.require("pillLook").click()
        Ui.clickText("Midnight", exists = true)
        assertFalse(Ui.has("lookSheet"))
        Ui.clickText("Midnight")
        Ui.require("sendButton").click()
        Ui.require("runningRow", 20_000)
        assertEquals(LookChoice(), FakeDebugBackend.lastStart!!.lookChoice)
        assertEquals("midnight", FakeDebugBackend.lastStart!!.look!!.wire)
    }

    @Test fun infoSaysTheLookAndWhy() {
        open(text = null)
        Ui.require("createCancel").click()
        findVideo("How bees make honey").click()
        openInfo()
        val said = nodes("infoLook").flatMap { listOfNotNull(it.text, it.contentDescription) + it.children.mapNotNull { c -> c.text } }.joinToString(" ")
        assertTrue(said, said.contains("Whiteboard · chosen for you") && said.contains("A step-by-step process is clearest drawn."))
    }

    // ---- captures (only with `-e shots <folder>`): every state of the iPhone review set, same names

    private val shots: String? get() = InstrumentationRegistry.getArguments().getString("shots")
    private fun shot(name: String) {
        Thread.sleep(700)
        val dir = File(Ui.context.getExternalFilesDir(null), "looks/${shots ?: "run"}").apply { mkdirs() }
        device.takeScreenshot(File(dir, "$name.png"))
    }

    @Test fun captures() {
        org.junit.Assume.assumeTrue("captures are taken only when asked (-e shots <folder>)", shots != null)
        open()
        shot("look-01-create-auto")
        Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("look-02-sheet-auto")
        Ui.require("lookTile-whiteboard").click(); Ui.waitGone("lookSheet", 4_000); shot("look-03-create-whiteboard")
        Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("look-04-sheet-whiteboard")
        Ui.require("lookTile-real").click(); Ui.waitGone("lookSheet", 4_000); shot("look-03b-create-real")
        Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("look-04b-sheet-real")
        Ui.require("lookTile-cartoon").click(); Ui.waitGone("lookSheet", 4_000); shot("look-05-create-cartoon-auto")
        Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("look-05b-sheet-cartoon")
        Ui.require("lookDone").click(); Ui.waitGone("lookSheet", 4_000)
        openCast(); shot("look-06-characters-auto")
        Ui.require("cast-fox").click(); shot("look-06c-characters-one")
        Ui.require("cast-bear").click(); Ui.require("extra-board").click(); shot("look-07-characters-talk")
        swipeSheet(); shot("look-07b-characters-talk-end")      // the same as 07 unless the sheet scrolls (large text, a small phone)
        closeCast(); shot("look-08-create-cartoon-talk")
        openCast(); Ui.require("cast-ines").click(); shot("look-09-characters-three-full")
        closeCast(); shot("look-10-create-cartoon-three")

        // a conversation in a 15 second video: the length moves and the line says so
        open()
        Ui.pickLength(Ui.context.getString(R.string.len_short_seconds, 15))
        pickLook("cartoon"); openCast()
        Ui.require("cast-fox").click(); Ui.require("cast-bear").click(); shot("look-11-characters-length-moved")
        closeCast()
        Ui.pickLength(Ui.context.getString(R.string.len_short_seconds, 15))
        Ui.require("lookLengthHint"); shot("look-16b-create-length-hint")
        Ui.require("sendButton").click()
        openNewVideo()
        Ui.require("lookNote", 20_000); shot("look-17-making-note")

        open(looks = "plan", fresh = true); Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("look-12-sheet-plan-locked")
        open(looks = "hidden", fresh = true); Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("look-13-sheet-one-hidden")

        open(fresh = true, text = "My holiday in Thailand: beaches, street food and the night market")
        pickLook("cartoon"); attachPhotos(); Ui.require("lookNotice"); shot("look-14-create-photos-reset")
        Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("look-15-sheet-with-photos")

        open(looks = "minlen", fresh = true)
        Ui.pickLength(Ui.context.getString(R.string.len_short_seconds, 15))
        pickLook("whiteboard"); Ui.require("lookNotice"); shot("look-16-create-length-moved")

        open(looks = null, fresh = true); Ui.require("pillLook").click(); shot("look-18-older-server-menu")

        open(text = null, fresh = true)
        Ui.require("createCancel").click()
        findVideo("How bees make honey").click()
        openInfo(); shot("look-19-info-look")
    }

    /** Scrolls the open sheet to its end (large text, small phones); does nothing visible when everything fits. */
    private fun swipeSheet() {
        val h = device.displayHeight; val w = device.displayWidth
        device.swipe(w / 2, (h * 0.80).toInt(), w / 2, (h * 0.45).toInt(), 20)
        Thread.sleep(400)
    }
}
