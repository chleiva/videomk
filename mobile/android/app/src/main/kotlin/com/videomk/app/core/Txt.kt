package com.videomk.app.core

import androidx.annotation.PluralsRes
import androidx.annotation.StringRes
import java.util.Locale
import java.util.ServiceLoader

/** Resolves string resources for code that is not a composable (logic objects, view models, error mappers). In the app it reads the localized Android resources; in plain JVM tests the test source set supplies an English reader. */
interface StringProvider {
    fun string(@StringRes id: Int, args: Array<out Any>): String
    /** [args] already starts with the count. */
    fun plural(@PluralsRes id: Int, count: Int, args: Array<out Any>): String
    /** The locale of the strings returned (also what dates and numbers use). */
    val locale: Locale
}

/**
 * The single door to client-owned text outside Compose. Never concatenate: one sentence is one resource with placeholders.
 *  - `Txt.s(R.string.x, a, b)` for `%1$s %2$d`;
 *  - `Txt.n(R.plurals.x, count, extra...)`: `%1$d` is the count, the extra arguments follow as `%2$...`.
 */
object Txt {
    @Volatile private var installed: StringProvider? = null

    var provider: StringProvider
        get() = installed ?: ServiceLoader.load(StringProvider::class.java).firstOrNull()?.also { installed = it }
            ?: error("No StringProvider installed (VideoMkApp installs one; JVM tests get JvmStringProvider from the test source set)")
        set(value) { installed = value }

    fun s(@StringRes id: Int, vararg args: Any): String = provider.string(id, args)
    fun n(@PluralsRes id: Int, count: Int, vararg args: Any): String = provider.plural(id, count, arrayOf<Any>(count, *args))
    val locale: Locale get() = provider.locale
    /** `en` or `es`: what goes in the `X-Locale` header. */
    val localeTag: String get() = AppLocale.tagOf(locale)
}

/** The locale policy of docs/I18N.md: explicit choice, then the device language, then English; any `es-*` is Spanish, everything else English. */
object AppLocale {
    const val SYSTEM = "system"
    val choices = listOf(SYSTEM, "en", "es")

    /** `es` for es, es-MX, es_AR, es-419; `en` for everything else (including languages we do not have). */
    fun tagOf(locale: Locale?): String = tagOf(locale?.language)
    fun tagOf(language: String?): String = if (language?.lowercase()?.substringBefore('-')?.substringBefore('_') == "es") "es" else "en"

    /** [explicit] is `en`, `es` or null/[SYSTEM]; [deviceLanguages] is the device's ordered list (language tags). */
    fun effective(explicit: String?, deviceLanguages: List<String>): String = when (explicit) {
        "en", "es" -> explicit
        else -> tagOf(deviceLanguages.firstOrNull())
    }
}
