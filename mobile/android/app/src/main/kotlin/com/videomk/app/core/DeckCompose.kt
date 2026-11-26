package com.videomk.app.core

/** Pure rules for how a presentation changes the Create form (the ViewModel just applies them). */
object DeckOptions {
    /** A presentation became ready: it is made at the suggested length (and price) unless the person picks another length. */
    fun onReady(o: CreateOptions, info: DeckReady): CreateOptions = o.copy(minutes = info.suggestedMinutes, suggestedCredits = info.suggestedCredits)

    /** The presentation went away (removed, replaced, failed): the length the person had before comes back. */
    fun onGone(o: CreateOptions, before: Double?): CreateOptions = o.copy(minutes = if (o.useSuggestedLength && before != null) before else o.minutes, suggestedCredits = null)

    /** Choosing a length from the list: that exact length is asked for (and priced by the usual rule). */
    fun chooseLength(o: CreateOptions, minutes: Double): CreateOptions = o.copy(minutes = minutes, suggestedCredits = null)

    /** Back to the suggestion. */
    fun useSuggestion(o: CreateOptions, info: DeckReady): CreateOptions = onReady(o, info)

    /** Slides are wide: landscape 16:9 (the "Just a video" platform, at 1080p) keeping whatever length is set. */
    fun landscape(o: CreateOptions, caps: Capabilities): CreateOptions {
        val chip = CreatePlatforms.chip(caps, "other")?.takeIf { it.enabled && it.aspect == "16:9" } ?: return if (caps.isReady("16:9")) o.copy(aspect = "16:9") else o
        return CreatePlatforms.select(o, chip, lengthChosen = true, presets = caps.presets)
    }

    /** A vertical or portrait picture with a presentation: a gentle warning (square is fine). */
    fun verticalWarning(o: CreateOptions, deckAttached: Boolean): Boolean = deckAttached && VideoItem.ratioOf(o.aspect) < 0.99f

    /** The title a card shows when the request has no description: the file's name without its extension. */
    fun title(fileName: String?): String? = fileName?.substringBeforeLast('.', fileName)?.trim()?.take(80)?.takeIf { it.isNotEmpty() }
}

/**
 * A video is made from photos OR from a presentation. Choosing one removes the other: the caller asks first when photos exist ([add] returns false
 * and changes nothing until [replacePhotos] is true).
 */
class DeckAttachment(private val journey: DeckJourney, private val photoCount: () -> Int, private val clearPhotos: () -> Unit) {
    fun add(pick: DeckPick, caps: DeckCaps, replacePhotos: Boolean): Boolean {
        if (photoCount() > 0 && !replacePhotos) return false
        clearPhotos()
        journey.start(pick, caps)
        return true
    }

    /** Photos were chosen: a presentation (in any state, even still uploading) is dropped and its copy deleted. */
    fun photosChosen() { if (journey.state.attached) journey.cancel() }
}
