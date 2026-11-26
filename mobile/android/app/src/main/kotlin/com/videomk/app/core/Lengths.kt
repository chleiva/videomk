package com.videomk.app.core

import com.videomk.app.R
import java.text.NumberFormat

/** Names for video lengths in minutes: 0.25 is "15 s", 1 is "1 min" (the server sends the presets; 15, 30 and 45 seconds exist). All text is in the app language. */
object Lengths {
    /** The old fixed choices, used when the server sends no `lengths.presets`. */
    val OLD_PRESETS = listOf(1.0, 2.0, 3.0, 5.0, 8.0, 12.0)

    /** "15 s", "45 s", "1 min", "12 min". */
    fun short(m: Double): String = if (m < 1.0 - 1e-9) Txt.s(R.string.len_short_seconds, Math.round(m * 60).toInt()) else Txt.s(R.string.len_short_minutes, trim(m))

    /** "15 seconds", "1 minute", "2 minutes". */
    fun long(m: Double): String =
        if (m < 1.0 - 1e-9) Txt.n(R.plurals.len_long_seconds, Math.round(m * 60).toInt())
        else if (m == Math.floor(m)) Txt.n(R.plurals.len_long_minutes, m.toInt())
        else Txt.s(R.string.len_long_minutes_fraction, trim(m))

    /** The length as it reads before "video": "3 minute" / "15 second" in English, "de 3 minutos" in Spanish ("A 3 minute video", "Un video de 3 minutos"). */
    fun adjective(m: Double): String =
        if (m < 1.0 - 1e-9) Txt.n(R.plurals.len_adj_seconds, Math.round(m * 60).toInt())
        else if (m == Math.floor(m)) Txt.n(R.plurals.len_adj_minutes, m.toInt())
        else Txt.s(R.string.len_adj_minutes_fraction, trim(m))

    /** "2:20" for 2 minutes 20 seconds. */
    fun clock(m: Double): String { val s = Math.round(m * 60).toInt(); return "%d:%02d".format(s / 60, s % 60) }

    /** 1 credit per started minute, at least 1 (61 s costs 2). */
    fun credits(m: Double): Int = maxOf(1, minOf(12, Math.ceil(m - 1e-9).toInt()))

    private fun trim(m: Double): String = if (m == Math.floor(m)) m.toInt().toString() else NumberFormat.getNumberInstance(Txt.locale).apply { maximumFractionDigits = 2 }.format(m)
}
