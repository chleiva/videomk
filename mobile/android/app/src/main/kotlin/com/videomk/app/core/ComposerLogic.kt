package com.videomk.app.core

/** What the composer's one status line says (docs/UI_DESIGN.md section e). */
enum class StatusKind { Listening, Sending, TooLong, NotAffordable, NoCredits, TooShort, PhotoHint, Ready, Idle }

/** The one-tap fix that comes with a problem: switch to a length ([minutes]), or open the credits screen. */
data class StatusFix(val minutes: Int?, val addCredits: Boolean = false) {
    fun label(): String = if (addCredits) "Add credits" else "Use $minutes min · ⚡${CreateOptions(minutes!!.toDouble()).credits}"
    fun description(): String = if (addCredits) "Add credits" else {
        val c = CreateOptions(minutes!!.toDouble()).credits
        "Use $minutes minute${if (minutes == 1) "" else "s"} instead, $c credit${if (c == 1) "" else "s"}"
    }
}

data class ComposerStatus(val kind: StatusKind, val text: String, val fix: StatusFix? = null) {
    /** Send is drawn in every state; this says whether tapping it starts a video or explains why not. */
    val sendReady: Boolean get() = kind == StatusKind.Ready || kind == StatusKind.PhotoHint
    val isProblem: Boolean get() = kind == StatusKind.TooLong || kind == StatusKind.NotAffordable || kind == StatusKind.NoCredits || kind == StatusKind.TooShort
}

object ComposerLogic {
    /** The longest length the balance allows (never 0 minutes); null when the balance is 0 (then the fix is "Add credits"). */
    fun affordableLength(balance: Int, lengths: List<Int>): Int? =
        lengths.sorted().lastOrNull { CreateOptions(it.toDouble()).credits <= balance }

    /**
     * One message at a time. Priority: listening, sending, too long, not affordable, too short, photo hint, price.
     * [balance] is null for accounts with unlimited credits. [photos] counts phone and My media photos together.
     */
    fun status(text: String, options: CreateOptions, balance: Int?, photos: Int, listening: Boolean, sending: Boolean, lengths: List<Int> = CreateOptions.LENGTHS.map { it.toInt() }, createScreen: Boolean = false, checking: Boolean = false): ComposerStatus {
        if (checking) return ComposerStatus(StatusKind.Sending, "Checking your request…")
        if (listening) return ComposerStatus(StatusKind.Listening, "Listening…")
        if (sending) return ComposerStatus(StatusKind.Sending, "Starting your video…")
        val count = Brief.normalized(text).length
        val credits = options.credits
        val mins = options.minutes.toInt()
        if (count > Brief.MAX_LENGTH) return ComposerStatus(StatusKind.TooLong, "%,d of %,d. Please shorten it.".format(count, Brief.MAX_LENGTH))
        val short = text.isNotEmpty() && !Brief.isValid(text)
        val valid = Brief.isValid(text)
        if (valid && balance != null && credits > balance) {
            val fit = affordableLength(balance, lengths)
            return if (fit == null) ComposerStatus(StatusKind.NoCredits, "You have no credits", StatusFix(null, addCredits = true))
            else ComposerStatus(StatusKind.NotAffordable, "Needs $credits credit${if (credits == 1) "" else "s"}, you have $balance", StatusFix(fit))
        }
        if (createScreen && !valid) return ComposerStatus(StatusKind.TooShort, "Describe your video to continue")
        if (short) return ComposerStatus(StatusKind.TooShort, "Add a few more words (${Brief.MIN_LENGTH - count} to go)")
        if (!valid) return ComposerStatus(StatusKind.Idle, "A $mins minute video costs $credits credit${if (credits == 1) "" else "s"}")
        PhotoCapacity.hint(photos, options.minutes, lengths)?.let { hint ->
            val s = PhotoCapacity.suggestion(photos, options.minutes, lengths)
            return ComposerStatus(StatusKind.PhotoHint, hint, s?.let { StatusFix(it) })
        }
        return ComposerStatus(StatusKind.Ready, if (balance == null) "$credits credit${if (credits == 1) "" else "s"}" else "$credits credit${if (credits == 1) "" else "s"} · you'll have ${balance - credits} left")
    }
}

/** Where a chosen photo comes from. */
enum class PhotoSource { Phone, Library }

/** Counts and wording for the Add photos sheet's selection bar. One selection across both tabs, at most [PhotoLimits.MAX_PHOTOS] in total with what is already attached. */
object AddPhotosLogic {
    fun total(phone: Int, library: Int) = phone + library
    fun room(phone: Int, library: Int) = maxOf(0, PhotoLimits.MAX_PHOTOS - total(phone, library))
    fun limitReached(phone: Int, library: Int) = total(phone, library) >= PhotoLimits.MAX_PHOTOS

    const val LIMIT_MESSAGE = "You can add up to 100 photos. Remove one to choose another."

    fun title(selected: Int) = if (selected == 0) "Choose photos" else "$selected selected"

    fun subline(phone: Int, library: Int, minutes: Double, lengths: List<Int> = CreateOptions.LENGTHS.map { it.toInt() }): String {
        val n = total(phone, library)
        if (n == 0) return "Choose up to ${PhotoLimits.MAX_PHOTOS} photos"
        val parts = buildList {
            if (phone > 0) add("$phone from this phone")
            if (library > 0) add("$library from My media")
        }.joinToString(", ")
        val fit = PhotoCapacity.capacity(minutes)
        val tail = if (n > PhotoLimits.MAX_PHOTOS * 8 / 10) " $n of ${PhotoLimits.MAX_PHOTOS}." else ""
        val fitText = " About $fit fit in ${PhotoCapacity.minutesText(minutes)}."
        return "$parts.$tail$fitText"
    }

    fun addLabel(selected: Int) = if (selected == 0) "Add" else "Add $selected"

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
        secondsSinceUploaded >= 120 -> "Taking longer than usual"
        secondsSinceUploaded >= 30 -> "Still getting it ready"
        else -> "Getting it ready"
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
        val s = StringBuilder()
        s.append(if (added == 0 && (duplicates > 0 || failed > 0 || noSpace > 0)) "No new photos were added." else "$added photo${if (added == 1) "" else "s"} added.")
        if (duplicates > 0) s.append(" $duplicates ${if (duplicates == 1) "was" else "were"} already there.")
        if (failed > 0) s.append(" $failed need${if (failed == 1) "s" else ""} your attention.")
        if (noSpace > 0) s.append(" $noSpace did not fit in your storage.")
        return s.toString()
    }

    /** "about 4 min" from the average speed so far; null until there is something to measure. */
    fun etaText(bytesLeft: Long, bytesDone: Long, elapsedMillis: Long): String? {
        if (bytesDone <= 0 || elapsedMillis < 3000 || bytesLeft <= 0) return null
        val seconds = bytesLeft.toDouble() / (bytesDone.toDouble() / (elapsedMillis / 1000.0))
        return if (seconds < 60) "less than a minute" else "about ${Math.round(seconds / 60)} min"
    }
}
