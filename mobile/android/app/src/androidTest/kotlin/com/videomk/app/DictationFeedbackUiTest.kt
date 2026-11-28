package com.videomk.app

import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import com.videomk.app.core.DictationFeedback
import com.videomk.app.core.LevelMeter
import com.videomk.app.core.VoiceEvent
import com.videomk.app.core.VoiceFeedback
import com.videomk.app.ui.ComposerViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.After
import org.junit.Assume
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

/**
 * Dictation feedback (docs/DICTATION_FEEDBACK_2026-11-28.md): the emulator has no microphone and no speech service, so each state is put on screen by setting the engine's
 * state the way a recorder would (synthetic speech-like levels). `-e shots <folder>` takes the captures (Android/data/com.videomk.app/files/looks/<folder>/).
 */
@RunWith(AndroidJUnit4::class)
class DictationFeedbackUiTest {
    private val device get() = Ui.device
    private val files get() = Ui.context.filesDir
    private fun flag(name: String, content: String? = "") { File(files, name).let { if (content == null) it.delete() else it.writeText(content) } }
    private fun fakeToken(): String {
        val enc = java.util.Base64.getUrlEncoder().withoutPadding()
        return enc.encodeToString("{\"alg\":\"none\"}".toByteArray()) + "." + enc.encodeToString("{\"sub\":\"create-tester\",\"email\":\"create@example.com\",\"exp\":${System.currentTimeMillis() / 1000 + 86400}}".toByteArray()) + ".sig"
    }
    @Before fun setUp() {
        flag("fake_backend"); flag("fake_intake", "ok"); flag("fake_looks")
        for (other in listOf("fake_plan", "fake_deck", "fake_balance", "fake_finish", "fake_media", "fake_making", "fake_many", "fake_empty_home", "fake_social")) flag(other, null)
        flag("fake_no_finished", ""); flag("fake_balance", "11")
        Ui.context.getSharedPreferences("videomk_create", 0).edit().clear().commit()
    }
    @After fun tearDown() { flag("fake_looks", null); flag("fake_no_finished", null); flag("fake_balance", null) }

    private fun composer(): ComposerViewModel {
        var vm: ComposerViewModel? = null
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            val activity = ActivityLifecycleMonitorRegistry.getInstance().getActivitiesInStage(Stage.RESUMED).first() as MainActivity
            vm = ViewModelProvider(activity)[ComposerViewModel::class.java]
        }
        return vm!!
    }
    @Suppress("UNCHECKED_CAST")
    private fun <T> field(o: Any, name: String): T = o.javaClass.getDeclaredField(name).apply { isAccessible = true }.get(o) as T
    private fun setField(o: Any, name: String, v: Any?) { o.javaClass.getDeclaredField(name).apply { isAccessible = true }.set(o, v) }

    private fun show(name: String) {
        val engine = composer().better
        var f = VoiceFeedback().apply(VoiceEvent.Request)
        val t0 = 1_000_000L
        fun recording(elapsed: Long, limit: Int = 360) { f = f.apply(VoiceEvent.Granted(t0, limit)).apply(VoiceEvent.Tick(t0 + elapsed * 1000)) }
        when (name) {
            "recording" -> recording(47); "soon" -> recording(335); "final" -> recording(352); "native" -> recording(12, 300)
            "transcribing", "slow", "failed" -> { recording(47); f = f.apply(VoiceEvent.Stop(t0 + 47_000)).apply(VoiceEvent.Tick(t0 + 47_000 + if (name == "slow") 12_000 else 1_000)); if (name == "failed") f = f.apply(VoiceEvent.Fail("network")) }
        }
        val m = LevelMeter()
        for (i in 0 until 80) { val env = maxOf(0.0, Math.sin(i / 5.3) * 0.5 + Math.sin(i / 1.7) * 0.25 + 0.15); m.push(env * 0.22) }
        InstrumentationRegistry.getInstrumentation().runOnMainSync {
            field<MutableStateFlow<VoiceFeedback>>(engine, "_voice").value = f
            field<MutableStateFlow<List<Double>>>(engine, "_bars").value = m.heights()
            setField(engine, "recording", name != "native" && (name == "recording" || name == "soon" || name == "final"))
            if (name != "recording" && name != "soon" && name != "final" && name != "native") setField(engine, "clip", ByteArray(1) to 1.0)
        }
        Thread.sleep(900)
    }
    private val shots: String? get() = InstrumentationRegistry.getArguments().getString("shots")
    private fun shot(name: String) {
        val dir = File(Ui.context.getExternalFilesDir(null), "looks/${shots ?: "run"}").apply { mkdirs() }
        device.takeScreenshot(File(dir, "$name.png"))
    }

    @Test fun captures() {
        Assume.assumeTrue("captures are taken only when asked (-e shots <folder>)", shots != null)
        Ui.launch(signedIn = true, tokens = fakeToken() to "")
        Ui.openCreate(); Ui.require("sendButton"); Thread.sleep(600)
        for (s in listOf("recording", "soon", "final", "native", "transcribing", "slow", "failed")) { show(s); Ui.find("dictationPanel", 3_000); shot(s) }
    }
}
