package com.videomk.app

import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import com.videomk.app.core.DictationEngine
import com.videomk.app.ui.ComposerViewModel
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Create v2 on Android (R167): one dock, a row of pills with glyphs, one tool row (photos, mic, Options; Create at the trailing end), Create states, chips and caption
 * only before the first finished video, recording, large text. Debug build's fake server, no account. Run in its own `am instrument` call on a freshly started app.
 * `-e shots <folder>` also takes the captures (Android/data/com.videomk.app/files/looks/<folder>/).
 */
@RunWith(AndroidJUnit4::class)
class CreateV2UiTest {
    private val device get() = Ui.device
    private val files get() = Ui.context.filesDir
    private val prompt = "How bees make honey, explained for kids"
    private val density get() = Ui.context.resources.displayMetrics.density
    private fun flag(name: String, content: String? = "") { File(files, name).let { if (content == null) it.delete() else it.writeText(content) } }

    private fun fakeToken(): String {
        val enc = java.util.Base64.getUrlEncoder().withoutPadding()
        return enc.encodeToString("{\"alg\":\"none\"}".toByteArray()) + "." + enc.encodeToString("{\"sub\":\"create-tester\",\"email\":\"create@example.com\",\"exp\":${System.currentTimeMillis() / 1000 + 86400}}".toByteArray()) + ".sig"
    }

    @Before fun setUp() {
        flag("fake_backend"); flag("fake_intake", "ok"); flag("fake_looks")
        for (other in listOf("fake_plan", "fake_deck", "fake_balance", "fake_finish", "fake_media", "fake_making", "fake_many", "fake_empty_home", "fake_social", "fake_no_finished")) flag(other, null)
        Ui.context.getSharedPreferences("videomk_create", 0).edit().clear().commit()
        FakeDebugBackend.lastStart = null
    }
    @After fun tearDown() { flag("fake_looks", null); flag("fake_no_finished", null); flag("fake_balance", null); flag("fake_intake", "ok") }

    private fun open(text: String? = null, firstVideo: Boolean = false, balance: Int? = null, intake: String = "ok", looks: String? = "") {
        flag("fake_no_finished", if (firstVideo) "" else null); flag("fake_balance", balance?.toString()); flag("fake_intake", intake); flag("fake_looks", looks)
        Ui.context.getSharedPreferences("videomk_create", 0).edit().clear().commit()
        Ui.launch(signedIn = true, tokens = fakeToken() to "")
        try { Ui.openCreate() } catch (e: Throwable) { if (shots != null) shot("FAIL-open"); throw e }
        if (text != null) Ui.require("composerField").text = text
        Ui.require("sendButton")
        Thread.sleep(600)
    }

    private fun bounds(tag: String) = Ui.require(tag).visibleBounds
    private fun composer(): ComposerViewModel {
        var vm: ComposerViewModel? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).first() as MainActivity
            vm = ViewModelProvider(activity)[ComposerViewModel::class.java]
        }
        return vm!!
    }
    /** The emulator has no speech service: the recording state is put on screen by setting the controller's state, as a recognizer that started would. */
    private fun fakeListening(on: Boolean) {
        val engine = composer().dictation
        val f = engine.javaClass.getDeclaredField("_state").apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST") val flow = f.get(engine) as kotlinx.coroutines.flow.MutableStateFlow<DictationEngine.State>
        InstrumentationRegistry.getInstrumentation().runOnMainSync { flow.value = if (on) DictationEngine.State.Listening else DictationEngine.State.Idle }
        Thread.sleep(500)
    }
    private fun disabled(tag: String) = Ui.require(tag).let { listOf(it) + it.children }.any { !it.isEnabled }
    private fun text(tag: String) = Ui.require(tag).let { listOf(it) + it.children }.firstNotNullOfOrNull { it.text?.takeIf { t -> t.isNotEmpty() } }.orEmpty()

    // ---- behaviour

    @Test fun oneDockPillsThenToolRowWithCreateAtTheTrailingEnd() {
        open(prompt)
        val pills = listOf("pillFor", "pillLength", "pillLook").map { bounds(it) }
        // the pills are above the tools; the helper line is gone
        val tools = listOf("photoButton", "micButton", "optionsMenu").map { bounds(it) }
        val create = bounds("sendButton")
        assertTrue("pills sit above the tool row", pills.all { it.bottom <= tools[0].top + 4 })
        assertTrue("photos, mic, Options left to right", tools[0].left < tools[1].left && tools[1].left < tools[2].left)
        assertTrue("Create is at the trailing end of the SAME row", create.left > tools[2].right && Math.abs(create.centerY() - tools[1].centerY()) < 16 * density)
        assertTrue("Create is at least 112 dp wide and 48 dp high", create.width() >= 112 * density - 2 && create.height() >= 48 * density - 2)
        assertTrue("tools are 48 dp targets", tools.all { it.height() >= 48 * density - 2 })
        assertTrue("pills are 48 dp targets", pills.all { it.height() >= 48 * density - 2 })
        assertFalse("no Characters pill for Auto", Ui.has("pillCast"))
        assertTrue("the helper line is gone", device.findObject(By.text("Describe your video")) == null)
    }

    @Test fun exampleChipsAndTheCaptionOnlyBeforeTheFirstFinishedVideo() {
        open(firstVideo = true, balance = 9)
        Ui.require("createExamples", 15_000)
        assertTrue(text("costLine").matches(Regex("\\d+ credits?\\. You have 9\\.")))
        Ui.require("composerField").text = prompt
        assertTrue("typing takes the chips away", Ui.waitGone("createExamples", 5_000))
        assertTrue("the caption stays while the price is being taught", Ui.has("costLine"))
        open(firstVideo = false, balance = 9)
        Thread.sleep(2000)
        assertFalse("a returning account has no chips", Ui.has("createExamples"))
        assertFalse("and no caption while the balance is fine", Ui.has("costLine"))
        open(firstVideo = false, balance = 1)
        assertTrue("low balance brings the caption back", text("costLine").contains("1 credit left"))
    }

    @Test fun createIsOpaqueButTappableWhenEmptyAndSaysWhatIsMissing() {
        open()
        Ui.require("sendButton").click()
        Ui.require("statusLine", 5_000)
        assertTrue(device.wait(Until.hasObject(By.textContains("Describe your video")), 5_000))
    }

    @Test fun creatingReplacesTheDockWithTheLiveCapsule() {
        open(prompt, intake = "slow")
        Ui.require("sendButton").click()
        Ui.require("createCapsule", 10_000)
        assertFalse("pills are gone while creating", Ui.has("pillFor"))
        assertFalse(Ui.has("sendButton"))
        Ui.require("capsuleCancel")
    }

    @Test fun recordingTurnsTheMicIntoStopAndCentresListening() {
        open(prompt)
        fakeListening(true)
        Ui.require("listeningHint")
        assertTrue("the mic is named Stop", device.wait(Until.hasObject(By.desc("Stop dictation")), 5_000))
        assertTrue("photos are off while recording", disabled("photoButton"))
        assertTrue("Options is off while recording", disabled("optionsMenu"))
        val hint = bounds("listeningHint"); val mic = bounds("micButton"); val create = bounds("sendButton")
        assertTrue("Listening sits between the tools and Create", hint.left > mic.right && hint.right < create.left)
        fakeListening(false)
        assertFalse(Ui.has("listeningHint"))
    }

    @Test fun optionsNoLongerRepeatsFormatChipsAndTheLookPill() {
        open(prompt)
        Ui.require("optionsMenu").click(); Ui.require("optionsSheet")
        assertFalse("the 'made for' chips are gone from Options", Ui.has("platformChips"))
    }

    @Test fun createDropsToItsOwnFullWidthRowAtLargeText() {
        val scale = Settings.fontScale()
        org.junit.Assume.assumeTrue("run with font_scale >= 1.5", scale >= 1.5f)
        open(prompt)
        val tools = bounds("optionsMenu"); val create = bounds("sendButton"); val screen = device.displayWidth
        assertTrue("Create is under the tools", create.top >= tools.bottom - 2)
        assertTrue("and spans the dock", create.width() > screen * 0.8)
        assertTrue("52 dp at least", create.height() >= 52 * density - 2)
    }

    private object Settings { fun fontScale(): Float = Ui.context.resources.configuration.fontScale }

    // ---- captures (only with `-e shots <folder>`)

    private val shots: String? get() = InstrumentationRegistry.getArguments().getString("shots")
    private fun shot(name: String) {
        Thread.sleep(700)
        val dir = File(Ui.context.getExternalFilesDir(null), "looks/${shots ?: "run"}").apply { mkdirs() }
        device.takeScreenshot(File(dir, "$name.png"))
    }

    @Test fun captures() {
        org.junit.Assume.assumeTrue("captures are taken only when asked (-e shots <folder>)", shots != null)
        open(firstVideo = true, balance = 11); Ui.find("createExamples", 6_000); shot("01-empty-first-video")
        Ui.require("composerField").text = "Bees"; shot("02-typing-short")
        Ui.require("composerField").text = prompt; shot("03-active")
        fakeListening(true); shot("05-recording"); fakeListening(false)
        if (Ui.find("pillFor", 2_000) == null) { device.pressBack(); Thread.sleep(800) }      // largest text on a small phone: the pills scroll with the prompt while the keyboard is up; closing it brings them back to the dock
        Ui.require("pillFor").click(); shot("07a-format-menu"); device.pressBack()
        Ui.require("pillLook").click(); Ui.require("lookSheet"); shot("07b-look-sheet")
        Ui.require("lookTile-cartoon").click(); Ui.waitGone("lookSheet", 4_000); Ui.require("pillCast"); shot("06-look-with-cast")
        Ui.require("pillCast").click(); Ui.require("castSheet"); Thread.sleep(500); Ui.require("cast-fox").click(); Ui.require("cast-bear").click(); Ui.require("castDone").click(); Ui.waitGone("castSheet", 4_000); shot("06b-look-with-two-characters")
        Ui.require("optionsMenu").click(); Ui.require("optionsSheet"); shot("08-options-sheet")
        device.pressBack(); Thread.sleep(500)
        open(prompt, firstVideo = true, balance = 11, intake = "slow"); Ui.require("sendButton").click(); Ui.require("createCapsule", 10_000); shot("04-creating")
        open(prompt, balance = 11); shot("09-returning-user-active")
        open(balance = 1); shot("10-returning-user-low-balance-empty")
    }
}
