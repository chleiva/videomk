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

    val policy: PhotoMetaPolicy get() = PhotoMetaPolicy(useDates, useLocations)

    private companion object { const val DATES = "photo_use_dates"; const val LOCATIONS = "photo_use_locations" }
}
