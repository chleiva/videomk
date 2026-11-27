package com.videomk.app

import com.videomk.app.core.*
import org.junit.Assert.*
import org.junit.Test

class ComposerLogicTest {
    private val ok = "A short film about my golden retriever's first summer"
    private fun st(text: String = ok, minutes: Double = 3.0, balance: Int? = 5, photos: Int = 0, listening: Boolean = false, sending: Boolean = false) =
        ComposerLogic.status(text, CreateOptions(minutes), balance, photos, listening, sending)

    @Test fun `empty field shows the price and send is not ready`() {
        val s = st(text = "")
        assertEquals(StatusKind.Idle, s.kind); assertEquals("A 3 minute video costs 3 credits", s.text); assertFalse(s.sendReady); assertNull(s.fix)
    }

    @Test fun `ready shows price and what is left`() {
        val s = st()
        assertEquals(StatusKind.Ready, s.kind); assertEquals("3 credits · you'll have 2 left", s.text); assertTrue(s.sendReady)
        assertEquals("3 credits", st(balance = null).text)
        assertEquals("1 credit · you'll have 0 left", st(minutes = 1.0, balance = 1).text)
    }

    @Test fun `not affordable offers the longest length the balance allows`() {
        val s = st(balance = 1)
        assertEquals(StatusKind.NotAffordable, s.kind); assertEquals("Needs 3 credits, you have 1", s.text); assertFalse(s.sendReady)
        assertEquals(1.0, s.fix!!.minutes!!, 0.0); assertEquals("Use 1 min · ⚡1", s.fix!!.label()); assertEquals("Use 1 minute instead, 1 credit", s.fix!!.description())
        assertEquals(2.0, st(minutes = 5.0, balance = 2).fix!!.minutes!!, 0.0)
        assertEquals(3.0, st(minutes = 8.0, balance = 4).fix!!.minutes!!, 0.0)   // 3 is the longest option that costs at most 4
    }

    @Test fun `one tap on the fix makes the video affordable and ready`() {
        val s = st(balance = 1)
        val fixed = st(minutes = s.fix!!.minutes!!.toDouble(), balance = 1)
        assertEquals(StatusKind.Ready, fixed.kind); assertEquals("1 credit · you'll have 0 left", fixed.text); assertTrue(fixed.sendReady)
    }

    @Test fun `no credits at all offers add credits instead of a length`() {
        val s = st(balance = 0)
        assertEquals(StatusKind.NoCredits, s.kind); assertEquals("You have no credits", s.text); assertTrue(s.fix!!.addCredits); assertEquals("Add credits", s.fix!!.label())
        assertNull(ComposerLogic.affordableLength(0, listOf(1.0, 2.0, 3.0)))
    }

    @Test fun `too short and too long`() {
        val short = st(text = "a trip")
        assertEquals(StatusKind.TooShort, short.kind); assertEquals("Add a few more words (${Brief.MIN_LENGTH - 6} to go)", short.text); assertFalse(short.sendReady)
        val long = st(text = "x".repeat(Brief.MAX_LENGTH + 140))
        assertEquals(StatusKind.TooLong, long.kind); assertTrue(long.text.endsWith("Please shorten it.")); assertFalse(long.sendReady)
    }

    @Test fun `priority is too long, then cost, then too short, then photo hint, then price`() {
        assertEquals(StatusKind.TooLong, st(text = "x".repeat(Brief.MAX_LENGTH + 1), balance = 0).kind)
        assertEquals(StatusKind.NotAffordable, st(balance = 1, photos = 100, minutes = 3.0).kind)
        assertEquals(StatusKind.TooShort, st(text = "short", photos = 100, minutes = 1.0).kind)
        assertEquals(StatusKind.Listening, st(listening = true, balance = 0).kind)
        assertEquals(StatusKind.Sending, st(sending = true).kind)
    }

    @Test fun `too many photos for the length gives a hint with a fix, and send stays ready`() {
        val s = st(minutes = 1.0, balance = 5, photos = 100)
        assertEquals(StatusKind.PhotoHint, s.kind); assertTrue(s.sendReady)
        assertTrue(s.text.startsWith("About 51 of 100 photos fit in 1 minute")); assertEquals(2.0, s.fix!!.minutes!!, 0.0); assertEquals("Use 2 min · ⚡2", s.fix!!.label())
        assertEquals(StatusKind.Ready, st(minutes = 2.0, photos = 100).kind)
        assertEquals(2.0, PhotoCapacity.suggestion(100, 1.0, listOf(1.0, 2.0, 3.0))!!, 0.0); assertNull(PhotoCapacity.suggestion(40, 1.0, listOf(1, 2, 3)))
    }

    // Add photos sheet

    @Test fun `one selection across both tabs with counts and the limit`() {
        assertEquals("Choose up to 100 photos", AddPhotosLogic.subline(0, 0, 3.0)); assertEquals("Choose photos", AddPhotosLogic.title(0)); assertEquals("Add", AddPhotosLogic.addLabel(0))
        assertEquals("7 selected", AddPhotosLogic.title(7)); assertEquals("Add 7", AddPhotosLogic.addLabel(7))
        assertEquals("4 from this phone, 3 from My media. About 153 fit in 3 minutes.", AddPhotosLogic.subline(4, 3, 3.0))
        assertEquals("4 from this phone, 3 from My media. About 51 fit in 1 minute.", AddPhotosLogic.subline(4, 3, 1.0))
        assertEquals("60 from this phone, 33 from My media. 93 of 100. About 51 fit in 1 minute.", AddPhotosLogic.subline(60, 33, 1.0))
        assertEquals(93, AddPhotosLogic.total(60, 33)); assertEquals(7, AddPhotosLogic.room(60, 33)); assertFalse(AddPhotosLogic.limitReached(60, 39)); assertTrue(AddPhotosLogic.limitReached(60, 40)); assertEquals(0, AddPhotosLogic.room(100, 5))
        assertEquals("You can add up to 100 photos. Remove one to choose another.", AddPhotosLogic.LIMIT_MESSAGE)
        assertNull(AddPhotosLogic.badge(0)); assertEquals("100", AddPhotosLogic.badge(100))
    }

    // upload journey

    private fun item(state: UploadState, mediaId: String? = "m") = QueueItem("i", "/f", 100, "h", state = state, mediaId = mediaId)

    @Test fun `tile states follow the queue and the server listing`() {
        assertEquals(TileState.Queued, UploadTiles.state(UploadState.Queued, false, false))
        assertEquals(TileState.Waiting, UploadTiles.state(UploadState.Queued, false, true))
        assertEquals(TileState.Uploading, UploadTiles.state(UploadState.Uploading, false, false))
        assertEquals(TileState.Processing, UploadTiles.state(UploadState.Done, false, false))
        assertEquals(TileState.Done, UploadTiles.state(UploadState.Done, true, false))
        assertEquals(TileState.Failed, UploadTiles.state(UploadState.Failed, false, false))
        assertEquals(TileState.AlreadyThere, UploadTiles.state(UploadState.Duplicate, false, false))
        assertEquals(TileState.Waiting, UploadTiles.state(UploadState.NoSpace, false, false))
        assertEquals("Getting it ready", UploadTiles.processingLabel(5)); assertEquals("Still getting it ready", UploadTiles.processingLabel(30)); assertEquals("Taking longer than usual", UploadTiles.processingLabel(120))
    }

    @Test fun `panel stats and the one summary per batch`() {
        val items = listOf(item(UploadState.Done, "a"), item(UploadState.Done, "b"), item(UploadState.Queued), item(UploadState.Uploading), item(UploadState.Failed), item(UploadState.NoSpace))
        assertEquals(UploadTiles.Stats(added = 1, gettingReady = 1, waiting = 3, needYou = 1), UploadTiles.stats(items, setOf("a")))
        assertEquals("120 photos added. 12 were already there.", UploadTiles.summary(120, 12, 0))
        assertEquals("120 photos added.", UploadTiles.summary(120, 0, 0))
        assertEquals("108 photos added. 5 need your attention.", UploadTiles.summary(108, 0, 5))
        assertEquals("1 photo added. 1 was already there.", UploadTiles.summary(1, 1, 0))
        assertEquals("No new photos were added. 3 were already there.", UploadTiles.summary(0, 3, 0))
        assertEquals("30 photos added. 62 did not fit in your storage.", UploadTiles.summary(30, 0, 0, noSpace = 62))
    }

    @Test fun `eta from the average speed`() {
        assertNull(UploadTiles.etaText(1000, 0, 10_000)); assertNull(UploadTiles.etaText(1000, 100, 1000)); assertNull(UploadTiles.etaText(0, 100, 10_000))
        assertEquals("about 4 min", UploadTiles.etaText(240_000, 10_000, 10_000))
        assertEquals("less than a minute", UploadTiles.etaText(1000, 10_000, 10_000))
    }
}
