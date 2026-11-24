package com.videomk.app

import com.videomk.app.core.DictationLanguage
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
}
