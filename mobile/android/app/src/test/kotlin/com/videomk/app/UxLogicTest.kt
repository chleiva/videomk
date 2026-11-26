package com.videomk.app

import com.videomk.app.core.CreateOptions
import com.videomk.app.core.DayBucket
import com.videomk.app.core.DayGroups
import com.videomk.app.core.LibraryEntry
import com.videomk.app.core.LibraryRow
import com.videomk.app.core.MakingScene
import com.videomk.app.core.MakingSnapshot
import com.videomk.app.core.PendingVideo
import com.videomk.app.core.Txt
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset

class UxLogicTest {
    @Before fun english() { Txt.provider = JvmStringProvider() }

    private val zone: ZoneId = ZoneOffset.UTC
    private val now = Instant.parse("2026-11-26T15:00:00Z")
    private fun v(id: String, at: String?, status: VideoStatus = VideoStatus.Complete) = LibraryEntry.Video(VideoItem(id, status, id, null, at?.let { Instant.parse(it) }))

    @Test fun bucketsAreTodayYesterdayEarlier() {
        assertEquals(DayBucket.Today, DayGroups.bucket(Instant.parse("2026-11-26T00:00:01Z"), now, zone))
        assertEquals(DayBucket.Yesterday, DayGroups.bucket(Instant.parse("2026-11-25T23:59:59Z"), now, zone))
        assertEquals(DayBucket.Earlier, DayGroups.bucket(Instant.parse("2026-11-24T12:00:00Z"), now, zone))
        assertEquals(DayBucket.Earlier, DayGroups.bucket(null, now, zone))
    }

    @Test fun rowsPutLiveFirstWithoutHeaderAndInsertHeadersOnChange() {
        val entries = listOf(
            v("a", "2026-11-26T10:00:00Z"), v("b", "2026-11-26T09:00:00Z"), v("mk", "2026-11-26T14:00:00Z", VideoStatus.Running(VideoStatus.Stage.Writing)),
            v("c", "2026-11-25T10:00:00Z", VideoStatus.Failed), v("d", "2026-11-01T10:00:00Z"),
        )
        val rows = DayGroups.rows(entries, now, zone)
        val shape = rows.map { if (it is LibraryRow.Header) "H:${it.bucket}" else (it as LibraryRow.Item).entry.id }
        assertEquals(listOf("mk", "H:Today", "a", "b", "H:Yesterday", "c", "H:Earlier", "d"), shape)
        assertEquals(rows.size, rows.map { it.key }.toSet().size)   // keys are unique (LazyColumn needs that)
    }

    @Test fun pendingRequestsStayOnTop() {
        val p = LibraryEntry.Pending(PendingVideo(brief = "x", options = CreateOptions()))
        val rows = DayGroups.rows(listOf(v("a", "2026-11-26T10:00:00Z"), p), now, zone)
        assertTrue((rows.first() as LibraryRow.Item).entry is LibraryEntry.Pending)
    }

    @Test fun makingSnapshotIsTheSameValueForCardAndDetail() {
        val a = MakingSnapshot.of("Bees", VideoStatus.Stage.VoiceAndVisuals, 10.0, 0.5)
        val b = MakingSnapshot.of("Bees", VideoStatus.Stage.VoiceAndVisuals, 10.0, 0.5)
        assertEquals(a, b)
        assertEquals(4, a.fills.size)
        assertNull(a.scene); assertTrue(a.thumbnails.isEmpty())   // seams: hidden until the backend reports scenes
        assertTrue(a.spoken().contains("Bees"))
        assertFalse(a.spoken().contains("Scene"))
        assertTrue(a.copy(scene = MakingScene(3, 7)).spoken().contains("Scene 3 of 7"))
    }

    @Test fun makingEtaIsHonestWhenLong() {
        assertTrue(MakingSnapshot.of("t", VideoStatus.Stage.Rendering, 0.0, 3.0).eta!!.contains("min"))
        assertEquals(null, MakingSnapshot.pending("t", "Sending", 0.0).eta)
    }

    @Test fun firstVideoIsThirtySeconds() {
        assertEquals(0.5, com.videomk.app.core.CreateDefaults.FIRST_TIME.minutes, 0.0)
        assertEquals(1, com.videomk.app.core.Lengths.credits(0.5))
    }

    @Test fun fourKIsRecognisedOnlyWhenOffered() {
        assertFalse(CreateOptions().isFourK)
        assertTrue(CreateOptions(resolution = "2160p").isFourK)
    }
}
