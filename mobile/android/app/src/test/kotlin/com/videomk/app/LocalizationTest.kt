package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.AppLocale
import com.videomk.app.core.Txt
import mockwebserver3.MockWebServer
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.Locale
import javax.xml.parsers.DocumentBuilderFactory

/** The localization gates (docs/I18N.md): key, placeholder and plural parity of the two catalogs, the locale policy, the X-Locale header, and a scan for new hard-coded text. */
class LocalizationTest {
    private class Entry(val name: String, val translatable: Boolean, val text: String?, val plurals: Map<String, String>?)

    private fun load(dir: String): List<Entry> {
        val files = File("src/main/res/$dir").listFiles { f -> f.name.startsWith("strings") && f.name.endsWith(".xml") }!!.sortedBy { it.name }
        return files.flatMap { f ->
            val nodes = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(f).documentElement.childNodes
            (0 until nodes.length).mapNotNull { nodes.item(it) as? org.w3c.dom.Element }.mapNotNull { e ->
                val tr = e.getAttribute("translatable") != "false"
                when (e.tagName) {
                    "string" -> Entry(e.getAttribute("name"), tr, e.textContent, null)
                    "plurals" -> Entry(e.getAttribute("name"), tr, null, e.getElementsByTagName("item").let { items -> (0 until items.length).associate { (items.item(it) as org.w3c.dom.Element).getAttribute("quantity") to items.item(it).textContent } })
                    else -> null
                }
            }
        }
    }

    private val en by lazy { load("values") }
    private val es by lazy { load("values-es") }

    /** `%1$s %2$d` as the list of (index, conversion) ordered by index; unindexed placeholders are numbered in order of appearance. */
    private fun placeholders(text: String): List<Pair<Int, Char>> {
        var next = 1
        return Regex("%(?:(\\d+)\\$)?[-#+ 0,(]*\\d*(?:\\.\\d+)?([sdfSDxXc])").findAll(text.replace("%%", "")).map { m ->
            (m.groupValues[1].toIntOrNull() ?: next++) to m.groupValues[2].lowercase()[0]
        }.sortedBy { it.first }.toList()
    }

    @Test fun `names are unique within each catalog`() {
        for (c in listOf(en, es)) assertEquals("duplicate names", emptyList<String>(), c.groupBy { it.name }.filter { it.value.size > 1 }.keys.toList())
    }

    @Test fun `every translatable English string has a Spanish twin and nothing extra`() {
        val e = en.filter { it.translatable }.map { it.name }.toSet(); val s = es.map { it.name }.toSet()
        assertEquals("missing in values-es", emptySet<String>(), e - s)
        assertEquals("extra in values-es", emptySet<String>(), s - e)
        assertEquals("translatable=false entries in values-es", emptyList<String>(), es.filter { !it.translatable }.map { it.name })
    }

    @Test fun `placeholders match in type and order`() {
        val sp = es.associateBy { it.name }
        val bad = en.filter { it.translatable }.mapNotNull { a ->
            val b = sp[a.name] ?: return@mapNotNull null
            if (a.text != null) { if (b.text == null || placeholders(a.text) != placeholders(b.text)) a.name else null }
            else a.plurals!!.entries.firstNotNullOfOrNull { (q, t) -> val bt = b.plurals?.get(q) ?: b.plurals?.get("other"); if (bt == null || placeholders(t) != placeholders(bt)) "${a.name}/$q" else null }
        }
        assertEquals("placeholder mismatch", emptyList<String>(), bad)
    }

    @Test fun `plurals have one and other in both languages`() {
        for ((lang, c) in listOf("en" to en, "es" to es)) {
            val bad = c.filter { it.plurals != null }.filter { "other" !in it.plurals!!.keys || "one" !in it.plurals.keys || !(it.plurals.keys - setOf("one", "other", "many")).isEmpty() }.map { it.name }
            assertEquals("plurals incomplete in $lang", emptyList<String>(), bad)
        }
    }

    @Test fun `no escaped-apostrophe or raw ASCII quote mistakes in Spanish`() {
        val bad = es.mapNotNull { it.text?.let { t -> if (Regex("[¿¡]").containsMatchIn(t) && !Regex("[?!]").containsMatchIn(t)) it.name else null } }
        assertEquals(emptyList<String>(), bad)
    }

    @Test fun `any es locale maps to Spanish and everything else to English`() {
        for (t in listOf("es", "es-ES", "es-MX", "es-419", "es_AR", "ES")) assertEquals(t, "es", AppLocale.tagOf(t))
        for (t in listOf("en", "en-GB", "fr", "pt-BR", "zh-Hans", "", null)) assertEquals(t, "en", AppLocale.tagOf(t as String?))
        assertEquals("es", AppLocale.tagOf(Locale("es", "MX")))
    }

    @Test fun `explicit choice beats device language beats English`() {
        assertEquals("en", AppLocale.effective("en", listOf("es-ES")))
        assertEquals("es", AppLocale.effective("es", listOf("en-US")))
        assertEquals("es", AppLocale.effective(AppLocale.SYSTEM, listOf("es-MX", "en")))
        assertEquals("es", AppLocale.effective(null, listOf("es-419")))
        assertEquals("en", AppLocale.effective(null, listOf("fr-FR", "es")))   // the first device language decides: French is not offered, so English
        assertEquals("en", AppLocale.effective(null, emptyList()))
    }

    @Test fun `X-Locale goes on every API call from the effective language`() = runBlocking {
        val server = MockWebServer(); server.start()
        try {
            repeat(2) { server.enqueue(json(body = """{"balance":1,"buckets":[]}""")) }
            val en = ApiClient(configFor(server), FixedAuth())
            en.wallet(); assertEquals("en", server.takeRequest().headers["X-Locale"])
            val es = ApiClient(configFor(server), FixedAuth(), locale = { "es" })
            es.wallet(); assertEquals("es", server.takeRequest().headers["X-Locale"])
        } finally { server.close() }
    }

    @Test fun `the account deletion calls carry X-Locale too`() = runBlocking {
        val server = MockWebServer(); server.start()
        try {
            server.enqueue(json(body = """{"apple":"none"}"""))
            ApiClient(configFor(server), FixedAuth(), locale = { "es" }).deleteAccount("tok", "user-1")
            assertEquals("es", server.takeRequest().headers["X-Locale"])
        } finally { server.close() }
    }

    @Test fun `Txt resolves Spanish when the Spanish provider is installed`() {
        val old = Txt.provider
        try {
            Txt.provider = JvmStringProvider("es")
            assertEquals("Cancelar", Txt.s(R.string.common_cancel)); assertEquals("es", Txt.localeTag)
        } finally { Txt.provider = old }
        assertEquals("Cancel", Txt.s(R.string.common_cancel)); assertEquals("en", Txt.localeTag)
    }

    // ---- the source scan: no new user-visible literals in Compose code ----

    private val uiDir = File("src/main/kotlin/com/videomk/app/ui")
    /** A string literal that looks like text a person reads: starts with a capital letter or contains a space between letters. */
    private val readable = Regex("^[A-Z][a-z]+|[A-Za-z]{2,} [A-Za-z]{2,}")
    private val callPatterns = listOf(
        Regex("""\bText\(\s*(?:text\s*=\s*)?"((?:[^"\\]|\\.)*)""""),
        Regex("""contentDescription\s*=\s*"((?:[^"\\]|\\.)*)""""),
        Regex("""\bIcon\([^()]*?,\s*"((?:[^"\\]|\\.)*)""""),
        Regex("""\b(?:label|placeholder|title|onClickLabel|stateDescription|text|description|hint|message)\s*=\s*"((?:[^"\\]|\\.)*)""""),
        Regex("""onClickLabel\s*=\s*"((?:[^"\\]|\\.)*)""""),
        Regex("""\bcontentDescription\s*=\s*if\s*\([^)]*\)\s*"((?:[^"\\]|\\.)*)""""),
    )
    private val allowed = Regex("^(https?://.*|[a-z][A-Za-z0-9_.:-]*|[^A-Za-z]*|%[0-9$.sdf%]+|\\$\\{?[A-Za-z].*)$")

    @Test fun `no user-visible English literals in the Compose files`() {
        val offenders = mutableListOf<String>()
        uiDir.walkTopDown().filter { it.extension == "kt" }.forEach { f ->
            f.readLines().forEachIndexed { i, line ->
                val code = line.substringBefore(" // ").trimEnd()
                if (code.trimStart().startsWith("//") || code.trimStart().startsWith("*") || "testTag(" in code && callPatterns.none { it.containsMatchIn(code.replace(Regex("""testTag\("[^"]*"\)"""), "")) }) return@forEachIndexed
                val clean = code.replace(Regex("""testTag\("[^"]*"\)"""), "")
                for (p in callPatterns) for (m in p.findAll(clean)) {
                    val lit = m.groupValues[1]
                    if (lit.isNotBlank() && readable.containsMatchIn(lit) && !allowed.matches(lit)) offenders += "${f.name}:${i + 1}: \"$lit\""
                }
            }
        }
        assertTrue("User-visible text must live in res/values/strings*.xml (and values-es):\n" + offenders.joinToString("\n"), offenders.isEmpty())
    }
}
