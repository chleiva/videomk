package com.videomk.app.core

import com.videomk.app.R

/** What the composer's one status line says (docs/UI_DESIGN.md section e). */
enum class StatusKind { Listening, Sending, TooLong, NotAffordable, NoCredits, TooShort, PhotoHint, Ready, Idle, DeckWaiting }

/** The one-tap fix that comes with a problem: switch to a length ([minutes]), or open the credits screen. */
data class StatusFix(val minutes: Double?, val addCredits: Boolean = false) {
    fun label(): String = if (addCredits) Txt.s(R.string.composer_add_credits) else Txt.s(R.string.composer_fix_use, Lengths.short(minutes!!), Lengths.credits(minutes))
    fun description(): String = if (addCredits) Txt.s(R.string.composer_add_credits) else {
        val c = Lengths.credits(minutes!!)
        Txt.n(R.plurals.composer_fix_description, c, Lengths.long(minutes))
    }
}

data class ComposerStatus(val kind: StatusKind, val text: String, val fix: StatusFix? = null) {
    /** Send is drawn in every state; this says whether tapping it starts a video or explains why not. */
    val sendReady: Boolean get() = kind == StatusKind.Ready || kind == StatusKind.PhotoHint
    val isProblem: Boolean get() = kind == StatusKind.TooLong || kind == StatusKind.NotAffordable || kind == StatusKind.NoCredits || kind == StatusKind.TooShort
}

object ComposerLogic {
    /** "A 3 minute video" / "A 15 second video" (Spanish: "Un video de 3 minutos"). */
    internal fun videoOf(m: Double): String =
        if (m >= 1.0 - 1e-9 && m == Math.floor(m)) Txt.n(R.plurals.composer_video_minutes, m.toInt()) else Txt.n(R.plurals.composer_video_seconds, Math.round(m * 60).toInt())

    /** The longest length the balance allows (never 0 minutes); null when the balance is 0 (then the fix is "Add credits"). */
    fun affordableLength(balance: Int, lengths: List<Double>): Double? =
        lengths.sorted().lastOrNull { Lengths.credits(it) <= balance }

    /**
     * One message at a time. Priority: listening, sending, too long, not affordable, too short, photo hint, price.
     * [balance] is null for accounts with unlimited credits. [photos] counts phone and My media photos together.
     */
    fun status(text: String, options: CreateOptions, balance: Int?, photos: Int, listening: Boolean, sending: Boolean, lengths: List<Double> = Lengths.OLD_PRESETS, createScreen: Boolean = false, checking: Boolean = false, deck: DeckState? = null): ComposerStatus {
        if (checking) return ComposerStatus(StatusKind.Sending, Txt.s(R.string.composer_checking))
        if (listening) return ComposerStatus(StatusKind.Listening, Txt.s(R.string.composer_listening))
        if (sending) return ComposerStatus(StatusKind.Sending, Txt.s(R.string.composer_starting))
        val count = Brief.normalized(text).length
        val credits = options.credits
        if (count > Brief.MAX_LENGTH) return ComposerStatus(StatusKind.TooLong, Txt.s(R.string.composer_too_long, count, Brief.MAX_LENGTH))
        if (deck != null) return deckStatus(count, options, balance, lengths, deck)
        val short = text.isNotEmpty() && !Brief.isValid(text)
        val valid = Brief.isValid(text)
        if (valid && balance != null && credits > balance) {
            val fit = affordableLength(balance, lengths)
            return if (fit == null) ComposerStatus(StatusKind.NoCredits, Txt.s(R.string.composer_no_credits), StatusFix(null, addCredits = true))
            else ComposerStatus(StatusKind.NotAffordable, Txt.n(R.plurals.composer_needs_credits, credits, balance), StatusFix(fit))
        }
        if (createScreen && !valid) return ComposerStatus(StatusKind.TooShort, Txt.s(R.string.composer_describe))
        if (short) return ComposerStatus(StatusKind.TooShort, Txt.s(R.string.composer_add_words, Brief.MIN_LENGTH - count))
        if (!valid) return ComposerStatus(StatusKind.Idle, Txt.n(R.plurals.composer_idle_cost, credits, videoOf(options.minutes)))
        PhotoCapacity.hint(photos, options.minutes, lengths)?.let { hint ->
            val s = PhotoCapacity.suggestion(photos, options.minutes, lengths)
            return ComposerStatus(StatusKind.PhotoHint, hint, s?.let { StatusFix(it) })
        }
        return ComposerStatus(StatusKind.Ready, if (balance == null) Txt.n(R.plurals.composer_ready_credits, credits) else Txt.n(R.plurals.composer_ready_credits_left, credits, balance - credits))
    }
}

/**
 * With a presentation the description is optional (it only steers audience and tone): empty is fine, a few characters are not (the server wants 10 or none),
 * and Create waits until the presentation is ready.
 */
private fun deckStatus(count: Int, options: CreateOptions, balance: Int?, lengths: List<Double>, deck: DeckState): ComposerStatus {
    if (deck !is DeckState.Ready) return ComposerStatus(StatusKind.DeckWaiting, Txt.s(if (deck is DeckState.Failed) R.string.deck_status_failed else R.string.deck_status_waiting))
    if (count in 1 until Brief.MIN_LENGTH) return ComposerStatus(StatusKind.TooShort, Txt.s(R.string.deck_status_short))
    val credits = options.credits
    if (balance != null && credits > balance) {
        val fit = ComposerLogic.affordableLength(balance, lengths)
        return if (fit == null) ComposerStatus(StatusKind.NoCredits, Txt.s(R.string.composer_no_credits), StatusFix(null, addCredits = true))
        else ComposerStatus(StatusKind.NotAffordable, Txt.n(R.plurals.composer_needs_credits, credits, balance), StatusFix(fit))
    }
    return ComposerStatus(StatusKind.Ready, if (balance == null) Txt.n(R.plurals.composer_ready_credits, credits) else Txt.n(R.plurals.composer_ready_credits_left, credits, balance - credits))
}

/** Where a chosen photo comes from. */
enum class PhotoSource { Phone, Library }

/** Counts and wording for the Add photos sheet's selection bar. One selection across both tabs, at most [PhotoLimits.MAX_PHOTOS] in total with what is already attached. */
object AddPhotosLogic {
    fun total(phone: Int, library: Int) = phone + library
    fun room(phone: Int, library: Int) = maxOf(0, PhotoLimits.MAX_PHOTOS - total(phone, library))
    fun limitReached(phone: Int, library: Int) = total(phone, library) >= PhotoLimits.MAX_PHOTOS

    val LIMIT_MESSAGE: String get() = Txt.s(R.string.composer_limit_message, PhotoLimits.MAX_PHOTOS)

    fun title(selected: Int) = if (selected == 0) Txt.s(R.string.composer_choose_photos) else Txt.n(R.plurals.composer_selected, selected)

    fun subline(phone: Int, library: Int, minutes: Double): String {
        val n = total(phone, library)
        if (n == 0) return Txt.s(R.string.composer_choose_up_to, PhotoLimits.MAX_PHOTOS)
        val parts = buildList {
            if (phone > 0) add(Txt.s(R.string.composer_from_phone, phone))
            if (library > 0) add(Txt.s(R.string.composer_from_library, library))
        }.joinToString(", ")
        val fit = PhotoCapacity.capacity(minutes)
        val tail = if (n > PhotoLimits.MAX_PHOTOS * 8 / 10) " " + Txt.s(R.string.composer_n_of_max, n, PhotoLimits.MAX_PHOTOS) else ""
        val fitText = " " + Txt.s(R.string.composer_about_fit, fit, PhotoCapacity.minutesText(minutes))
        return "$parts.$tail$fitText"
    }

    fun addLabel(selected: Int) = if (selected == 0) Txt.s(R.string.composer_add) else Txt.s(R.string.composer_add_n, selected)

    /** The attach button's badge: total photos from both sources, "99+" never needed (the cap is 100). */
    fun badge(total: Int): String? = if (total <= 0) null else total.toString()
}

/** The look of one tile in the Media grid while uploading (docs/UI_DESIGN.md section m). */
enum class TileState { Queued, Uploading, Processing, Done, Failed, AlreadyThere, Waiting }

object UploadTiles {
    /**
     * [listed]: the server already lists this photo (so its thumbnail can take over). [stopped]: the queue is paused, offline or out of space.
     */
    fun state(state: UploadState, listed: Boolean, stopped: Boolean): TileState = when (state) {
        UploadState.Duplicate -> TileState.AlreadyThere
        UploadState.NoSpace -> TileState.Waiting
        UploadState.Failed -> TileState.Failed
        UploadState.Queued -> if (stopped) TileState.Waiting else TileState.Queued
        UploadState.Uploading -> TileState.Uploading
        UploadState.Done -> if (listed) TileState.Done else TileState.Processing
    }

    fun processingLabel(secondsSinceUploaded: Long): String = when {
        secondsSinceUploaded >= 120 -> Txt.s(R.string.composer_processing_long)
        secondsSinceUploaded >= 30 -> Txt.s(R.string.composer_processing_still)
        else -> Txt.s(R.string.composer_processing)
    }

    /** The four numbers in the expanded upload panel. */
    data class Stats(val added: Int, val gettingReady: Int, val waiting: Int, val needYou: Int)

    fun stats(items: List<QueueItem>, listedIds: Set<String>): Stats = Stats(
        added = items.count { it.state == UploadState.Done && it.mediaId in listedIds },
        gettingReady = items.count { it.state == UploadState.Done && it.mediaId !in listedIds },
        waiting = items.count { it.state == UploadState.Queued || it.state == UploadState.Uploading || it.state == UploadState.NoSpace },
        needYou = items.count { it.state == UploadState.Failed },
    )

    /** The one summary per batch: "120 photos added. 12 were already there." */
    fun summary(added: Int, duplicates: Int, failed: Int, noSpace: Int = 0): String {
        val parts = ArrayList<String>()
        parts.add(if (added == 0 && (duplicates > 0 || failed > 0 || noSpace > 0)) Txt.s(R.string.composer_summary_none_added) else Txt.n(R.plurals.composer_summary_added, added))
        if (duplicates > 0) parts.add(Txt.n(R.plurals.composer_summary_duplicates, duplicates))
        if (failed > 0) parts.add(Txt.n(R.plurals.composer_summary_failed, failed))
        if (noSpace > 0) parts.add(Txt.n(R.plurals.composer_summary_no_space, noSpace))
        return parts.joinToString(" ")
    }

    /** "about 4 min" from the average speed so far; null until there is something to measure. */
    fun etaText(bytesLeft: Long, bytesDone: Long, elapsedMillis: Long): String? {
        if (bytesDone <= 0 || elapsedMillis < 3000 || bytesLeft <= 0) return null
        val seconds = bytesLeft.toDouble() / (bytesDone.toDouble() / (elapsedMillis / 1000.0))
        return if (seconds < 60) Txt.s(R.string.composer_eta_under_minute) else Txt.s(R.string.composer_eta_minutes, Math.round(seconds / 60).toInt())
    }
}
