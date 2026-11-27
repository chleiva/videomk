package com.videomk.app.data

import android.content.Context
import com.videomk.app.core.PhotoMetaPolicy

/** The two Photos switches in Settings (plain preferences: nothing secret in them). Both default to on. */
class PhotoSettings(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("videomk_settings", Context.MODE_PRIVATE)

    var useDates: Boolean
        get() = runCatching { prefs.getBoolean(DATES, true) }.getOrDefault(true)
        set(v) { runCatching { prefs.edit().putBoolean(DATES, v).apply() } }
    var useLocations: Boolean
        get() = runCatching { prefs.getBoolean(LOCATIONS, true) }.getOrDefault(true)
        set(v) { runCatching { prefs.edit().putBoolean(LOCATIONS, v).apply() } }

    /** The first-visit privacy note of My media was read. */
    var mediaPrivacySeen: Boolean
        get() = runCatching { prefs.getBoolean(MEDIA_PRIVACY, false) }.getOrDefault(false)
        set(v) { runCatching { prefs.edit().putBoolean(MEDIA_PRIVACY, v).apply() } }

    /** The one-time "Tap Select, choose photos, then Make a video" tip of My media was seen. */
    var mediaSelectHintSeen: Boolean
        get() = runCatching { prefs.getBoolean(MEDIA_SELECT_HINT, false) }.getOrDefault(false)
        set(v) { runCatching { prefs.edit().putBoolean(MEDIA_SELECT_HINT, v).apply() } }

    val policy: PhotoMetaPolicy get() = PhotoMetaPolicy(useDates, useLocations)

    private companion object { const val DATES = "photo_use_dates"; const val LOCATIONS = "photo_use_locations"; const val MEDIA_PRIVACY = "media_privacy_seen"; const val MEDIA_SELECT_HINT = "media_select_hint_seen" }
}

/** What Create remembers per person (platform, format, resolution, length, look, subtitles, language), in plain preferences. Prompt and photos never. */
class CreatePrefsStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("videomk_create", Context.MODE_PRIVATE)
    fun load(person: String?): com.videomk.app.core.CreatePrefs? = runCatching { com.videomk.app.core.CreatePrefs.fromJson(prefs.getString(key(person), null)) }.getOrNull()
    fun save(person: String?, p: com.videomk.app.core.CreatePrefs) { runCatching { prefs.edit().putString(key(person), p.toJson()).apply() } }
    private fun key(person: String?) = "create_${person ?: "me"}"
}
