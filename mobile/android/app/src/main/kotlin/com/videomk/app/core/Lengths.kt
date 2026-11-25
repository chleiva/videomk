package com.videomk.app.core

/** Names for video lengths in minutes: 0.25 is "15 s", 1 is "1 min" (the server sends the presets; 15, 30 and 45 seconds exist). */
object Lengths {
    /** The old fixed choices, used when the server sends no `lengths.presets`. */
    val OLD_PRESETS = listOf(1.0, 2.0, 3.0, 5.0, 8.0, 12.0)

    /** "15 s", "45 s", "1 min", "12 min". */
    fun short(m: Double): String = if (m < 1.0 - 1e-9) "${Math.round(m * 60)} s" else "${trim(m)} min"

    /** "15 seconds", "1 minute", "2 minutes". */
    fun long(m: Double): String = if (m < 1.0 - 1e-9) "${Math.round(m * 60)} seconds" else "${trim(m)} minute${if (Math.abs(m - 1.0) < 1e-9) "" else "s"}"

    /** "3 minute" / "15 second", for "A 3 minute video". */
    fun adjective(m: Double): String = if (m < 1.0 - 1e-9) "${Math.round(m * 60)} second" else "${trim(m)} minute"

    /** "2:20" for 2 minutes 20 seconds. */
    fun clock(m: Double): String { val s = Math.round(m * 60).toInt(); return "%d:%02d".format(s / 60, s % 60) }

    /** 1 credit per started minute, at least 1 (61 s costs 2). */
    fun credits(m: Double): Int = maxOf(1, minOf(12, Math.ceil(m - 1e-9).toInt()))

    private fun trim(m: Double) = if (m == Math.floor(m)) m.toInt().toString() else m.toString()
}
