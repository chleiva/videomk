package com.videomk.app

import com.videomk.app.core.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/** Regression guards for the "app stopped" crash in Create > My media: lists built from repeating data, and the crash log. */
class CrashSafetyTest {
    private fun photo(id: String) = MediaPhoto(id, null, "2025-03-10T12:00:00Z", null, 100, 100, 1000, "https://t/$id")
    private fun page(vararg ids: String, cursor: String? = null) = MediaPage(ids.map { photo(it) }, cursor)

    @Test fun `a page that lists a photo twice is stored once, in the order of its first appearance`() {
        val l = MediaListing()
        l.replace(page("a", "b", "a", "c", "b", cursor = "n"))
        assertEquals(listOf("a", "b", "c"), l.items.map { it.id })
    }

    @Test fun `an appended page with repeats and overlaps adds each new photo once`() {
        val l = MediaListing()
        l.replace(page("a", "b", cursor = "n"))
        l.append(page("b", "c", "c", "d", "a"))
        assertEquals(listOf("a", "b", "c", "d"), l.items.map { it.id })
    }

    @Test fun `a refreshed head with repeats keeps one copy of each id`() {
        val l = MediaListing()
        l.replace(page("a", "b", cursor = "n"))
        l.mergeHead(page("x", "x", "a"))
        assertEquals(listOf("x", "a", "b"), l.items.map { it.id })
    }

    @Test fun `list keys stay unique when labels repeat`() {
        assertEquals(listOf("Mallorca", "2024", "Mallorca#1", "Mallorca#2", "2024#1"), ListKeys.unique(listOf("Mallorca", "2024", "Mallorca", "Mallorca", "2024")))
        val k = ListKeys.unique(List(50) { "same" })
        assertEquals(50, k.toSet().size)
        assertEquals(emptyList<String>(), ListKeys.unique(emptyList()))
    }

    @Test fun `grouping a hundred photos with repeated timestamps gives one section key each`() {
        val photos = (1..100).map { MediaPhoto("p$it", "2026-11-26T10:00:00", "2026-11-26T10:00:00Z", null, 10, 10, 1, null) }
        val sections = MediaGrouping.group(photos)
        assertEquals(sections.map { it.key }.toSet().size, sections.size)
        assertEquals(100, sections.sumOf { it.items.size })
    }

    @Test fun `the crash log keeps class names and frames but not the message`() {
        val boom = IllegalStateException("secret user text " + "x".repeat(50), IndexOutOfBoundsException("Index 3 out of bounds for length 3"))
        val text = CrashLog.render(boom, "main", "0.1.0+1", 42L)
        assertTrue(text.contains("java.lang.IllegalStateException"))
        assertTrue(text.contains("java.lang.IndexOutOfBoundsException"))
        assertTrue(text.contains("thread=main"))
        assertFalse(text.contains("secret user text"))
        assertFalse(text.contains("Index 3"))
        assertTrue(text.length <= 8_000)
    }

    @Test fun `the crash log is written by the handler and read back`() {
        val dir = kotlin.io.path.createTempDirectory("crashlog").toFile()
        val before = Thread.getDefaultUncaughtExceptionHandler()
        try {
            var chained = false
            Thread.setDefaultUncaughtExceptionHandler { _, _ -> chained = true }
            CrashLog.install(dir, "0.1.0+2")
            Thread.getDefaultUncaughtExceptionHandler()!!.uncaughtException(Thread.currentThread(), RuntimeException("x"))
            assertTrue("the previous handler still runs", chained)
            assertTrue(CrashLog.last(dir)!!.contains("java.lang.RuntimeException"))
            assertNull(CrashLog.last(File(dir, "missing")))
        } finally { Thread.setDefaultUncaughtExceptionHandler(before); dir.deleteRecursively() }
    }
}
