package com.videomk.app

import com.videomk.app.core.StringProvider
import java.io.File
import java.util.Locale
import javax.xml.parsers.DocumentBuilderFactory

/**
 * Reads the real strings files under `res/values` and `res/values-es`, so plain JVM tests see exactly the text the app ships. English by default;
 * a test can install `JvmStringProvider("es")` in `Txt.provider` (and put `JvmStringProvider()` back in a finally).
 */
class JvmStringProvider(tag: String = "en") : StringProvider {
    override val locale: Locale = Locale.forLanguageTag(tag)
    private val en = Catalog.load("values")
    private val local = if (tag == "en") en else Catalog.load("values-$tag")
    private val ids = Ids

    override fun string(id: Int, args: Array<out Any>): String {
        val name = ids.string[id] ?: error("Unknown string id $id")
        val text = local.strings[name] ?: en.strings[name] ?: error("Missing string $name")
        return if (args.isEmpty()) text else String.format(locale, text, *args)
    }

    override fun plural(id: Int, count: Int, args: Array<out Any>): String {
        val name = ids.plural[id] ?: error("Unknown plurals id $id")
        val forms = local.plurals[name] ?: en.plurals[name] ?: error("Missing plurals $name")
        val text = (if (count == 1) forms["one"] else null) ?: forms["other"] ?: error("Plurals $name has no other")
        return String.format(locale, text, *args)
    }

    object Ids {
        val string: Map<Int, String> = ids("com.videomk.app.R\$string")
        val plural: Map<Int, String> = ids("com.videomk.app.R\$plurals")
        private fun ids(cls: String): Map<Int, String> = Class.forName(cls).fields.filter { it.type == Int::class.javaPrimitiveType }.associate { it.getInt(null) to it.name }
    }

    class Catalog(val strings: Map<String, String>, val plurals: Map<String, Map<String, String>>) {
        companion object {
            fun load(dir: String): Catalog {
                val res = File("src/main/res/$dir")
                val strings = LinkedHashMap<String, String>(); val plurals = LinkedHashMap<String, Map<String, String>>()
                res.listFiles { f -> f.name.startsWith("strings") && f.name.endsWith(".xml") }?.sortedBy { it.name }?.forEach { f ->
                    val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(f)
                    val nodes = doc.documentElement.childNodes
                    for (i in 0 until nodes.length) {
                        val n = nodes.item(i) as? org.w3c.dom.Element ?: continue
                        when (n.tagName) {
                            "string" -> strings[n.getAttribute("name")] = unescape(n.textContent)
                            "plurals" -> {
                                val items = n.getElementsByTagName("item")
                                plurals[n.getAttribute("name")] = (0 until items.length).associate { (items.item(it) as org.w3c.dom.Element).getAttribute("quantity") to unescape(items.item(it).textContent) }
                            }
                        }
                    }
                }
                return Catalog(strings, plurals)
            }
        }
    }

    companion object {
        /** Android resource text rules (what aapt does to the raw XML text): surrounding quotes, backslash escapes. Whitespace runs collapse. */
        fun unescape(raw: String): String {
            var s = raw.trim()
            if (s.length >= 2 && s.startsWith("\"") && s.endsWith("\"")) return s.substring(1, s.length - 1)
            s = s.replace(Regex("\\s+"), " ")
            val out = StringBuilder(); var i = 0
            while (i < s.length) {
                val c = s[i]
                if (c == '\\' && i + 1 < s.length) {
                    when (val d = s[i + 1]) {
                        'n' -> out.append('\n'); 't' -> out.append('\t')
                        'u' -> { out.append(s.substring(i + 2, i + 6).toInt(16).toChar()); i += 4 }
                        else -> out.append(d)
                    }
                    i += 2
                } else { out.append(c); i++ }
            }
            return out.toString()
        }
    }
}
