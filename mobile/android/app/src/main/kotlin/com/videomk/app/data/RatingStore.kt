package com.videomk.app.data

import android.content.Context
import com.videomk.app.core.RatingState
import com.videomk.app.core.RatingStorage

/** The rating prompt's counters in plain preferences (nothing secret: counts, ids of videos the person watched, a flag). */
class RatingStore(context: Context) : RatingStorage {
    private val prefs = context.applicationContext.getSharedPreferences("videomk_rating", Context.MODE_PRIVATE)
    override fun load(): RatingState = RatingState.decode(runCatching { prefs.getString(KEY, null) }.getOrNull())
    override fun save(state: RatingState) { runCatching { prefs.edit().putString(KEY, state.encode()).apply() } }
    private companion object { const val KEY = "state" }
}
