package com.videomk.app.data

import android.app.LocaleManager
import android.content.Context
import android.content.res.Configuration
import android.os.Build
import android.os.LocaleList
import com.videomk.app.core.AppLocale
import com.videomk.app.core.StringProvider
import java.util.Locale

/**
 * The app language (docs/I18N.md): the person's explicit choice in Settings, else the device language, else English.
 * Android 13+ keeps the choice in the system (LocaleManager, so the system "App languages" screen and Settings agree);
 * older versions keep it here and the activities wrap their context ([wrap]).
 */
class AppLanguage(context: Context) {
    private val app = context.applicationContext
    private val prefs = app.getSharedPreferences("app_language", Context.MODE_PRIVATE)

    /** [AppLocale.SYSTEM], `en` or `es`. */
    val choice: String get() {
        if (Build.VERSION.SDK_INT >= 33) {
            val l = app.getSystemService(LocaleManager::class.java)?.applicationLocales
            return if (l == null || l.isEmpty) AppLocale.SYSTEM else AppLocale.tagOf(l[0])
        }
        return prefs.getString("choice", AppLocale.SYSTEM)?.takeIf { it in AppLocale.choices } ?: AppLocale.SYSTEM
    }

    /** `en` or `es`. */
    val effective: String get() = AppLocale.effective(choice, deviceLanguages())

    /** Stores the choice. Returns true when the caller must recreate its activity (Android 13+ does that itself). */
    fun set(value: String): Boolean {
        val v = value.takeIf { it in AppLocale.choices } ?: AppLocale.SYSTEM
        prefs.edit().putString("choice", v).apply()
        Locale.setDefault(Locale.forLanguageTag(AppLocale.effective(v, deviceLanguages())))   // code that still asks Locale.getDefault() agrees with the app
        if (Build.VERSION.SDK_INT >= 33) {
            app.getSystemService(LocaleManager::class.java)?.applicationLocales = if (v == AppLocale.SYSTEM) LocaleList.getEmptyLocaleList() else LocaleList.forLanguageTags(v)
            return false
        }
        return true
    }

    /** For `attachBaseContext` of every activity: on Android 12 and older, an explicit choice is applied here. */
    fun wrap(base: Context): Context {
        if (Build.VERSION.SDK_INT >= 33) return base
        val c = choice
        if (c == AppLocale.SYSTEM) return base
        return localized(base, c)
    }

    private fun deviceLanguages(): List<String> {
        val l = android.content.res.Resources.getSystem().configuration.locales
        return (0 until l.size()).map { l[it].toLanguageTag() }
    }

    /** Called once at start: makes `Locale.getDefault()` the app language. */
    fun applyDefault() = Locale.setDefault(Locale.forLanguageTag(effective))

    /** What non-composable code resolves strings with: always the effective language. */
    fun provider(): StringProvider = object : StringProvider {
        private var cached: Pair<String, Context>? = null
        private fun ctx(): Context {
            val tag = effective
            cached?.let { if (it.first == tag) return it.second }
            return localized(app, tag).also { cached = tag to it }
        }
        override val locale: Locale get() = Locale.forLanguageTag(effective)
        override fun string(id: Int, args: Array<out Any>): String = ctx().resources.getString(id, *args)
        override fun plural(id: Int, count: Int, args: Array<out Any>): String = ctx().resources.getQuantityString(id, count, *args)
    }

    companion object {
        fun localized(base: Context, tag: String): Context {
            val cfg = Configuration(base.resources.configuration)
            val locale = Locale.forLanguageTag(tag)
            cfg.setLocales(LocaleList(locale))
            return base.createConfigurationContext(cfg)
        }
    }
}
