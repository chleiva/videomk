package com.videomk.app

import com.videomk.app.core.AspectInfo
import com.videomk.app.core.Capabilities
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.LanguageInfo
import com.videomk.app.core.PlatformInfo
import com.videomk.app.core.Remix
import com.videomk.app.core.RemixKind
import com.videomk.app.core.ResolutionInfo
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** "Make another" chips only exist when they can really open Create with the idea and one choice changed (no dead buttons). */
class RemixTest {
    private val caps = Capabilities(
        aspects = listOf(AspectInfo("16:9", "Landscape", true, false), AspectInfo("9:16", "Vertical", true, false)), resolutions = listOf(ResolutionInfo("1080p", "1080p")),
        platforms = listOf(PlatformInfo("shorts", "YouTube Shorts", "9:16", "1080p", 0.75, 3.0), PlatformInfo("other", "Just a video", "16:9", "1080p", 3.0, null)),
        languages = listOf(LanguageInfo("en", "English"), LanguageInfo("es", "Español")), presets = listOf(0.5, 1.0, 3.0),
    )
    private val wide = VideoItem("v", VideoStatus.Complete, "How a forest breathes", 91.0, aspect = "16:9")

    @Test fun `the idea is what was written, else the title, else nothing`() {
        assertEquals("A calm story about forests", Remix.prompt("  A calm   story about forests ", "Forests"))
        assertEquals("How a forest breathes", Remix.prompt(null, "How a forest breathes"))
        assertNull(Remix.prompt(null, "Bees")); assertNull(Remix.prompt(null, null)); assertNull(Remix.prompt("short", ""))
    }

    @Test fun `a full server offers a Short, the other language and a 30-second cut`() {
        assertEquals(listOf(RemixKind.Short, RemixKind.Spanish, RemixKind.Cut30), Remix.offers(wide, caps, "en", true))
        assertEquals(listOf(RemixKind.Short, RemixKind.English, RemixKind.Cut30), Remix.offers(wide, caps, "es", true))
    }

    @Test fun `nothing is offered that cannot be done`() {
        assertTrue(Remix.offers(wide, caps, "en", hasPrompt = false).isEmpty())
        assertTrue(Remix.offers(wide, Capabilities.FALLBACK, "en", true).isEmpty())   // an older server: landscape only, no languages listed, no 30 s
        assertTrue(Remix.offers(wide.copy(status = VideoStatus.Failed), caps, "en", true).isEmpty())
        assertEquals(listOf(RemixKind.Spanish), Remix.offers(wide.copy(aspect = "9:16", durationSeconds = 30.0), caps, "en", true))   // already a short Short
        assertEquals(listOf(RemixKind.Short, RemixKind.Cut30), Remix.offers(wide, caps.copy(languages = emptyList()), "en", true))
    }

    @Test fun `a chip changes one choice and leaves the rest`() {
        val base = CreateOptions(minutes = 3.0, captions = false)
        val short = Remix.apply(base, RemixKind.Short, caps)!!
        assertEquals("shorts", short.platform); assertEquals("9:16", short.aspect); assertEquals(false, short.captions)
        val es = Remix.apply(base, RemixKind.Spanish, caps)!!
        assertEquals("es", es.language); assertEquals(3.0, es.minutes, 0.0); assertEquals(base.aspect, es.aspect)
        val cut = Remix.apply(base, RemixKind.Cut30, caps)!!
        assertEquals(0.5, cut.minutes, 0.0); assertEquals(1, cut.credits); assertEquals(base.language, cut.language)
        assertNull(Remix.apply(base, RemixKind.Short, Capabilities.FALLBACK)); assertNull(Remix.apply(base, RemixKind.English, Capabilities.FALLBACK))
    }
}
