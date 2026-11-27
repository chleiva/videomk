package com.videomk.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The product name is written VideoMK wherever a person reads it (docs/BRAND.md): every string resource in every language, the name under the app icon, and the
 * text literals of the screens. Lowercase `videomk` is only an identifier: a domain or address (`videomk.com`, `hello@videomk.com`), the package and its URL
 * scheme (`com.videomk.app`), a resource or file name (`videomk-qa-...`), a wire value. Any other spelling fails here.
 */
class BrandTest {
    private val any = Regex("videomk", RegexOption.IGNORE_CASE)

    /** True when this occurrence is part of an identifier (so lowercase is right). */
    private fun identifier(text: String, at: Int): Boolean {
        val before = text.getOrNull(at - 1); val after = text.substring(at + 7)
        if (before != null && (before == '.' || before == '@' || before == '/' || before == '-' || before == '_' || before.isLetterOrDigit())) return true
        return after.startsWith(".com") || after.startsWith(".app") || after.startsWith(".test") || after.startsWith("://") || after.startsWith("-") || after.startsWith("_") || after.firstOrNull()?.isLetterOrDigit() == true
    }

    private fun wrong(text: String): List<String> = any.findAll(text).filter { m ->
        when {
            text == "videomk" -> false                                                  // a whole literal that is the wire value (the watermark mode id)
            text.getOrNull(m.range.first - 1) == '/' && m.value == "VideoMK" -> false   // a folder a person sees ("Movies/VideoMK" in the gallery)
            identifier(text, m.range.first) -> m.value != "videomk"                     // an identifier is all lowercase
            else -> m.value != "VideoMK"
        }
    }.map { text.substring(maxOf(0, it.range.first - 20), minOf(text.length, it.range.last + 21)).replace("\n", " ") }.toList()

    @Test fun `the rule itself - what passes and what fails`() {
        for (ok in listOf("Enjoying VideoMK?", "Write to VideoMK at hello@videomk.com", "https://videomk.com/terms", "com.videomk.app://auth/callback", "Hecho con VideoMK", "videomk-qa-assets"))
            assertTrue(ok, wrong(ok).isEmpty())
        for (bad in listOf("Enjoying videomk?", "Videomk", "VideoMk makes it", "Video MK".replace(" ", ""), "VIDEOMK", "videoMK", "Made with videomk."))
            if (bad != "VideoMK") assertTrue(bad, wrong(bad).isNotEmpty())
    }

    @Test fun `every string resource spells the name VideoMK, in English and Spanish`() {
        val bad = ArrayList<String>()
        for (dir in File("src/main/res").listFiles { f -> f.isDirectory && f.name.startsWith("values") }!!) for (f in dir.listFiles { x -> x.name.startsWith("strings") && x.extension == "xml" }!!) {
            // the text between the tags only: resource names (`name="..."`) are identifiers
            for (m in Regex("<(?:string|item)[^>]*>(.*?)</(?:string|item)>", RegexOption.DOT_MATCHES_ALL).findAll(f.readText())) for (w in wrong(m.groupValues[1])) bad += "${dir.name}/${f.name}: $w"
        }
        assertEquals("the name must be written VideoMK:\n" + bad.joinToString("\n"), 0, bad.size)
    }

    @Test fun `the name under the app icon is VideoMK`() {
        val name = Regex("<string name=\"app_name\"[^>]*>(.*?)</string>").find(File("src/main/res/values/strings.xml").readText())!!.groupValues[1]
        assertEquals("VideoMK", name)
        assertTrue(File("src/main/AndroidManifest.xml").readText().contains("android:label=\"@string/app_name\""))
    }

    @Test fun `text written in the screens' code spells it VideoMK too`() {
        val bad = ArrayList<String>()
        val literal = Regex("\"((?:[^\"\\\\]|\\\\.)*)\"")
        for (f in File("src/main/kotlin/com/videomk/app").walkTopDown().filter { it.extension == "kt" }) for ((n, line) in f.readLines().withIndex()) {
            val code = line.substringBefore("//")
            if (code.trimStart().startsWith("package ") || code.trimStart().startsWith("import ") || code.trimStart().startsWith("*") || code.trimStart().startsWith("/*")) continue
            for (m in literal.findAll(code)) for (w in wrong(m.groupValues[1])) bad += "${f.name}:${n + 1}: $w"
        }
        assertEquals("a person reads these: write VideoMK\n" + bad.joinToString("\n"), 0, bad.size)
    }
}
