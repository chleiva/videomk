package com.videomk.app.core

/** How a text chip lays out: on one line, wrapped to two lines, or as a full-width row (three lines at most; ellipsis only after that). */
enum class ChipFit { SingleLine, Wrapped, FullWidth }

/**
 * Decides single line, wrapped or full width from the label length and the room, never a fixed width that crops (docs/UI_DESIGN.md: text wraps, chips grow).
 * It is an estimate of text width (average glyph width x font scale), made on the safe side: when unsure the chip gets more room, not less.
 */
object ChipLayout {
    const val AVERAGE_GLYPH_DP = 10f      // semibold 16 sp text, a little wide on purpose
    const val PADDING_DP = 40f            // 20 dp each side

    fun estimatedTextDp(label: String, fontScale: Float, extraDp: Float = 0f): Float = label.length * AVERAGE_GLYPH_DP * fontScale.coerceAtLeast(1f) + extraDp

    fun fit(label: String, availableDp: Float, fontScale: Float, extraDp: Float = 0f): ChipFit {
        val room = (availableDp - PADDING_DP - extraDp).coerceAtLeast(40f)
        val need = estimatedTextDp(label, fontScale)
        return when {
            need <= room -> ChipFit.SingleLine
            need <= room * 1.7f -> ChipFit.Wrapped      // two lines with a margin for ragged breaks
            else -> ChipFit.FullWidth
        }
    }

    fun maxLines(fit: ChipFit): Int = when (fit) { ChipFit.SingleLine -> 1; ChipFit.Wrapped -> 2; ChipFit.FullWidth -> 3 }
}
