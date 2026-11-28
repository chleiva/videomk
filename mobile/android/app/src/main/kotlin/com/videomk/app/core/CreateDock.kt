package com.videomk.app.core

/**
 * The decisions of the Create dock (docs/design_bar/CREATE_SCREEN_ANDROID_VALUES.md), kept apart from Compose so they can be tested on the JVM:
 * what the one caption under the tool row says, when the example chips show, how many, and when Create drops to its own row.
 */
object CreateDock {
    /** The state of the Create pill: [Inactive] is opaque and quiet but still takes the tap (it says what is missing); [Creating] is the live capsule. */
    enum class CreateState { Inactive, Active, Creating }

    fun createState(ready: Boolean, hasOffer: Boolean, creating: Boolean): CreateState = when {
        creating -> CreateState.Creating
        ready || hasOffer -> CreateState.Active
        else -> CreateState.Inactive
    }

    /** What the caption under the tool row says: nothing, the price taught once ("2 credits. You have 11."), or the balance running low. */
    sealed interface Caption {
        data object None : Caption
        data class FirstVideo(val cost: Int, val balance: Int) : Caption
        data class Low(val balance: Int) : Caption
    }

    /**
     * [calm]: nothing is wrong (a status or error sentence has its own place and the caption steps aside). [balance] is null for an unlimited account (never a caption).
     * [hasFinishedVideo]: from the Videos list; when the list could not be read it is treated as "yes", so neither the caption nor the chips guess. Low = the balance
     * could not pay for a second video like this one; below the price the "needs N credits" sentence takes over instead.
     */
    fun caption(calm: Boolean, balance: Int?, cost: Int, hasFinishedVideo: Boolean, priceKnown: Boolean = true): Caption {
        if (!calm || !priceKnown || balance == null || balance < cost) return Caption.None
        return when {
            !hasFinishedVideo -> Caption.FirstVideo(cost, balance)
            balance < 2 * cost -> Caption.Low(balance)
            else -> Caption.None
        }
    }

    /** Whether the account has a finished video; unknown (list not loaded or unreadable) counts as yes. */
    fun hasFinishedVideo(listLoaded: Boolean, anyComplete: Boolean): Boolean = !listLoaded || anyComplete

    const val SHORT_WINDOW_DP = 640
    const val TIGHT_WINDOW_DP = 340
    /** Example chips: three, two on a short window, none where not even one row fits above the dock (a small phone with the keyboard up: a clipped chip is worse than none). */
    fun chipCount(windowHeightDp: Float): Int = when { windowHeightDp < TIGHT_WINDOW_DP -> 0; windowHeightDp < SHORT_WINDOW_DP -> 2; else -> 3 }

    /** Chips only while the field is empty, nothing is attached, nothing is being dictated or sent, and the account has no finished video yet. */
    fun showExamples(textEmpty: Boolean, typing: Boolean, attached: Boolean, listening: Boolean, locked: Boolean, hasFinishedVideo: Boolean): Boolean =
        textEmpty && !typing && !attached && !listening && !locked && !hasFinishedVideo

    /** Create goes to its own full-width row at font scale 1.5 and up, or whenever it does not fit beside the tools (measured, [toolsWidth] + gap + [createWidth] > [available]). */
    fun createOnOwnRow(fontScale: Float, toolsWidth: Int, createWidth: Int, gap: Int, available: Int): Boolean =
        fontScale >= 1.5f || toolsWidth + gap + createWidth > available
}
