package com.videomk.app

import com.videomk.app.core.DictationLanguage
import com.videomk.app.core.DictationLocale
import com.videomk.app.core.DictationRestartPolicy
import com.videomk.app.core.DictationText
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.DictationPlan.Permission.Denied
import com.videomk.app.core.DictationPlan.Permission.Granted
import com.videomk.app.core.DictationPlan.Permission.Undetermined
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class DictationTest {
    private fun plan(speech: DictationPlan.Permission, mic: DictationPlan.Permission, recognizer: Boolean, keyboard: Boolean) =
        DictationPlan.decide(speech, mic, recognizer, keyboard)

    @Test fun `everything allowed uses our own recognizer`() {
        assertEquals(DictationPlan.UseApp, plan(Granted, Granted, true, true))
        assertEquals(DictationPlan.UseApp, plan(Granted, Granted, true, false))
    }

    @Test fun `an undecided permission still tries our recognizer (the system asks first)`() {
        assertEquals(DictationPlan.UseApp, plan(Undetermined, Undetermined, true, false))
    }

    @Test fun `denied microphone falls back to the keyboard when it has voice typing`() {
        val p = plan(Denied, Denied, true, true)
        assertTrue(p is DictationPlan.UseKeyboard)
        assertTrue((p as DictationPlan.UseKeyboard).message.contains("Microphone access is off"))
    }

    @Test fun `no recognizer on the phone falls back to the keyboard and says why`() {
        val p = plan(Granted, Granted, false, true) as DictationPlan.UseKeyboard
        assertTrue(p.message.contains("isn't available on this phone"))
    }

    @Test fun `nothing usable is blocked with a way to fix it, never an exception`() {
        val denied = plan(Denied, Denied, true, false) as DictationPlan.Blocked
        assertTrue(denied.message.contains("Allow microphone access"))
        val speechDenied = plan(Denied, Granted, true, false) as DictationPlan.Blocked
        assertTrue(speechDenied.message.contains("speech recognition"))
        val none = plan(Granted, Granted, false, false) as DictationPlan.Blocked
        assertTrue(none.message.contains("isn't available"))
    }

    @Test fun `every combination yields a plan`() {
        val perms = listOf(Undetermined, Granted, Denied)
        var n = 0
        for (s in perms) for (m in perms) for (r in listOf(true, false)) for (k in listOf(true, false)) { plan(s, m, r, k); n++ }
        assertEquals(36, n)
    }

    // language

    @Test fun `saved choice wins, else first supported preferred language, else English`() {
        assertEquals(DictationLanguage.Spanish, DictationLanguage.initial("es", listOf("en-US")))
        assertEquals(DictationLanguage.Spanish, DictationLanguage.initial(null, listOf("fr-FR", "es-ES", "en-US")))
        assertEquals(DictationLanguage.English, DictationLanguage.initial(null, listOf("en-GB", "es-ES")))
        assertEquals(DictationLanguage.English, DictationLanguage.initial(null, listOf("fr-FR", "de-DE")))
        assertEquals(DictationLanguage.English, DictationLanguage.initial(null, emptyList()))
        assertEquals(DictationLanguage.English, DictationLanguage.initial("xx", listOf("zh-CN")))
    }

    @Test fun `locale prefers the phone's region, then the biggest audience`() {
        val supported = listOf("en-US", "en-GB", "es-ES", "es-MX", "fr-FR")
        assertEquals("en-GB", DictationLanguage.English.locale("GB", supported))
        assertEquals("es-ES", DictationLanguage.Spanish.locale("ES", supported))
        assertEquals("es-MX", DictationLanguage.Spanish.locale("US", supported))
        assertEquals("en-US", DictationLanguage.English.locale(null, supported))
        assertEquals("es-AR", DictationLanguage.Spanish.locale(null, listOf("es-AR", "es-CL")))
        assertEquals("es-MX", DictationLanguage.Spanish.locale("ES", emptyList()))
        assertEquals("en-US", DictationLanguage.English.locale("FR", listOf("fr-FR")))
    }

    // ---- appending, rebasing, restarts, language (pure: no microphone)

    @Test fun `compose adds one space and never doubles it`() {
        assertEquals("hello", DictationText.compose("", "hello"))
        assertEquals("A video about bees", DictationText.compose("A video", "about bees"))
        assertEquals("A video about bees", DictationText.compose("A video  ", "about bees"))
        assertEquals("Line one\nline two", DictationText.compose("Line one\n", "line two"))
        assertEquals("keep", DictationText.compose("keep", "   "))
    }

    @Test fun `speaking again appends instead of replacing`() {
        val d = DictationText("About bees")
        var field = "About bees"
        fun hear(s: String, final: Boolean = false) {
            val step = if (final) d.fold(s, field) else d.hear(s, field)
            if (step is DictationText.Step.Write) field = step.text
        }
        hear("and"); hear("and honey"); hear("and honey", final = true)
        assertEquals("About bees and honey", field)
        hear("for"); hear("for kids", final = true)          // a new recognizer session: its transcript starts empty again
        assertEquals("About bees and honey for kids", field)
    }

    @Test fun `a hand edit while listening rebases and is never overwritten`() {
        val d = DictationText("Bees")
        var field = "Bees"
        (d.hear("and honey", field) as DictationText.Step.Write).also { field = it.text }
        field = "Bees and honey, no wasps"
        assertEquals(DictationText.Step.Rebased, d.hear("and honey and more", field))
        assertEquals("Bees and honey, no wasps", d.base)
        assertEquals(DictationText.Step.Write("Bees and honey, no wasps flowers"), d.hear("flowers", field))
    }

    @Test fun `text typed before the first word arrives is kept`() {
        val d = DictationText("x")
        assertEquals(DictationText.Step.Rebased, d.hear("y", "x typed"))
        assertEquals("x typed", d.base)
    }

    @Test fun `pauses restart the recognizer, long silence and the maximum stop it`() {
        val p = DictationRestartPolicy(maxMillis = 300_000, idleMillis = 90_000)
        p.sessionStarted(0); p.recognizerStarted(0); p.textArrived(10_000)
        assertEquals(DictationRestartPolicy.Action.Restart, p.ended(hadText = true, now = 12_000))      // result after a phrase
        p.recognizerStarted(12_300)
        assertEquals(DictationRestartPolicy.Action.Restart, p.ended(hadText = false, now = 20_000))     // NO_MATCH while thinking
        p.recognizerStarted(20_300)
        assertEquals(DictationRestartPolicy.Action.StopIdle, p.ended(hadText = false, now = 101_000))   // 90 s with nothing said
        val q = DictationRestartPolicy(); q.sessionStarted(0); q.recognizerStarted(0)
        assertEquals(DictationRestartPolicy.Action.StopTimeLimit, q.ended(hadText = true, now = 300_001))
    }

    @Test fun `a recognizer that fails at once does not loop`() {
        val p = DictationRestartPolicy(); p.sessionStarted(0)
        val actions = (0 until 4).map { i -> p.recognizerStarted(i * 1_000L); p.ended(hadText = false, now = i * 1_000L + 100) }
        assertEquals(listOf(DictationRestartPolicy.Action.Restart, DictationRestartPolicy.Action.Restart, DictationRestartPolicy.Action.Restart, DictationRestartPolicy.Action.StopFailing), actions)
    }

    @Test fun `silence errors are the normal end of a pause and busy waits longer`() {
        assertTrue(DictationRestartPolicy.isSilence(android.speech.SpeechRecognizer.ERROR_NO_MATCH))
        assertTrue(DictationRestartPolicy.isSilence(android.speech.SpeechRecognizer.ERROR_SPEECH_TIMEOUT))
        assertEquals(1_000L, DictationRestartPolicy.delayMillis(android.speech.SpeechRecognizer.ERROR_RECOGNIZER_BUSY))
        assertEquals(300L, DictationRestartPolicy.delayMillis(null))
    }

    @Test fun `dictation language follows the app, the phone only picks the variant`() {
        assertEquals("es-MX", DictationLocale.tag("es", listOf("en-US")))          // Spanish app on an English phone: Spanish
        assertEquals("es-ES", DictationLocale.tag("es", listOf("es-ES", "en-US")))
        assertEquals("en-GB", DictationLocale.tag("en", listOf("en-GB", "es-ES")))
        assertEquals("en-US", DictationLocale.tag("en", listOf("es-ES")))          // English app on a Spanish phone: English
        assertEquals("en-US", DictationLocale.tag("fr", listOf("fr-FR")))          // an unknown app language never picks a third language
    }
}
