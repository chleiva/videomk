package com.videomk.app

import com.videomk.app.core.*
import java.time.Instant

/**
 * Debug only: a backend with canned data, so every signed-in screen can be photographed (and the app localized) without a server or a real account.
 * Switched on by the file `files/fake_backend` (and a locally made, unsigned token through `vmk_debug_id_token`, see scripts/l10n-shots.sh).
 * The text below is English on purpose: it stands for what the model or the user wrote, which is never translated.
 */
class FakeDebugBackend(private val deckDemo: Boolean = false) : Backend {
    private val now = Instant.now()
    /** Screenshots: pictures pushed to `files/fake_pics/` (any JPEG, by name) stand in for posters and scene pictures; without them the gradients show. */
    private fun pic(name: String): String? = java.io.File("/data/data/com.videomk.app/files/fake_pics/$name").takeIf { it.exists() }?.let { "file://${it.path}" }
    /** `files/fake_making`: "none" (a server that does not send `making`), "plain" (scenes without pictures), "render" (every scene done); anything else: scenes with pictures. */
    private val makingMode = runCatching { java.io.File("/data/data/com.videomk.app/files/fake_making").readText().trim() }.getOrDefault("")
    private val making: MakingInfo? = when (makingMode) {
        "none" -> null
        "render" -> MakingInfo(9, 9, "Putting the scenes together", "Deep in the forest, every tree is part of one slow breath.", (1..9).map { MakingInfo.Scene(it, true, pic("p%02d.jpg".format(it))) })
        else -> MakingInfo(9, 4, "Adding footage of sunlit canopies", "Sunlight pours through the canopy, and the forest breathes.", (1..9).map { MakingInfo.Scene(it, it <= 4, if (makingMode == "plain" || it > 4) null else pic("p%02d.jpg".format(it))) })
    }
    private val videos = mutableListOf(
        VideoItem("v2", VideoStatus.Running(VideoStatus.Stage.VoiceAndVisuals), "How a forest breathes", null, now.minusSeconds(240), null, null, null, false, "16:9", "1080p", making = making),
        VideoItem("v1", VideoStatus.Complete, "How bees make honey", 182.0, now.minusSeconds(3600), "https://example.com/v1.mp4", pic("s_bees.jpg"), null, true, "16:9", "1080p"),
        VideoItem("v6", VideoStatus.Complete, "3 focus tips", 30.0, now.minusSeconds(7200), "https://example.com/v6.mp4", pic("s_focus.jpg"), null, true, "9:16", "1080p"),
        VideoItem("v7", VideoStatus.Complete, "Why forests matter", 91.0, now.minusSeconds(9000), "https://example.com/v7.mp4", pic("s_forest.jpg"), null, true, "16:9", "1080p"),
        VideoItem("v3", VideoStatus.Failed, "A calm walk through Kyoto", null, now.minusSeconds(86400), null, null, null, false, "16:9", "1080p"),
        VideoItem("v4", VideoStatus.Rejected, null, null, now.minusSeconds(172800), null, null, "This request is outside what VideoMK can make.", false, "16:9", "1080p"),
        VideoItem("v5", VideoStatus.Complete, "Why is the sky blue?", 61.0, now.minusSeconds(604800), "https://example.com/v5.mp4", pic("mountain_lake.jpg"), null, true, "1:1", "720p"),
    )

    /** With the fake presentation switch on, two videos made from a deck are being prepared: one reading the slides, one writing the narration. */
    private val deckVideos = listOf(
        VideoItem("d1", VideoStatus.Running(VideoStatus.Stage.Writing, VideoStatus.DeckStage.Reading), "Annual plan", null, now.minusSeconds(20), null, null, null, false, "16:9", "1080p"),
        VideoItem("d2", VideoStatus.Running(VideoStatus.Stage.Writing, VideoStatus.DeckStage.Writing), "Sales kickoff", null, now.minusSeconds(60), null, null, null, false, "16:9", "1080p"),
    )

    /**
     * `files/fake_finish` (created from outside while the app is in the background: `adb shell run-as com.videomk.app touch files/fake_finish`): the video being made
     * is finished from then on. That is how "it finished while the phone was locked" is checked by hand and in the instrumented test (tracker R124).
     */
    private fun finished(): Boolean = java.io.File("/data/data/com.videomk.app/files/fake_finish").exists()
    override suspend fun listVideos(): List<VideoItem> {
        val list = if (finished()) videos.map { if (it.id == "v2") it.copy(status = VideoStatus.Complete, durationSeconds = 62.0, making = null, editable = true, videoUrl = "https://example.com/v2.mp4", previewGifUrl = pic("s_forest.jpg")) else it } else videos.toList()
        return if (deckDemo) deckVideos + list else list
    }
    /** "Try again" on the canned failed video: the SAME row turns into a making one (as the server does), so the in-place change can be looked at. */
    override suspend fun retryVideo(videoId: String): RetryResult {
        kotlinx.coroutines.delay(1200)
        val i = videos.indexOfFirst { it.id == videoId }
        if (i < 0) return RetryResult.Refused("not_found", "This video is gone.")
        if (videos[i].status is VideoStatus.Running) return RetryResult.AlreadyRunning
        videos[i] = videos[i].copy(status = VideoStatus.Running(VideoStatus.Stage.Writing))
        return RetryResult.Started(45, 0)
    }
    override suspend fun deleteVideo(videoId: String): Boolean { videos.removeAll { it.id == videoId }; return true }
    /** "Cancel video" on the canned making video: it becomes the cancelled card and two credits come back. */
    override suspend fun cancelVideo(videoId: String): CancelResult {
        kotlinx.coroutines.delay(600)
        val i = videos.indexOfFirst { it.id == videoId }
        if (i < 0 || videos[i].status !is VideoStatus.Running) return CancelResult.NotCancellable("This video is already finished.")
        videos[i] = videos[i].copy(status = VideoStatus.Cancelled, making = null, canRetry = true)
        return CancelResult.Cancelled(2)
    }
    /** `files/fake_plan`: "free" (a Free account: 30 s, 1080p, the watermark, two welcome credits), "locked" (Free with nothing to spend and free videos off: Create shows the showcase), "pro". Absent: no plans, as an older server. */
    private val planMode = runCatching { java.io.File("/data/data/com.videomk.app/files/fake_plan").readText().trim() }.getOrDefault("")
    private val tomorrow = java.time.LocalDate.now().plusDays(1).atStartOfDay(java.time.ZoneId.systemDefault()).toInstant()
    override suspend fun wallet() = when (planMode) {
        "free" -> WalletInfo(balance = 2, buckets = listOf(WalletBucket("signup", 2, now.plusSeconds(86400L * 30))), nextFreeAt = null, nextFreeCredits = 0,
            plans = PlanState(PlanInfo("free", "Free", 30, listOf("720p", "1080p"), true, 10), FreeInfo(true, creditsLeft = 2, maxSeconds = 30), "welcome"))
        "locked" -> WalletInfo(balance = 0, nextFreeAt = null, nextFreeCredits = 0,
            plans = PlanState(PlanInfo("free", "Free", 30, listOf("720p", "1080p"), true, 10), FreeInfo(false, "paused", "Free videos are done for today.", 0, 30, true, tomorrow), "welcome"))
        "pro" -> WalletInfo(balance = 27, buckets = listOf(WalletBucket("plan", 27, now.plusSeconds(86400L * 18))), nextFreeAt = null, nextFreeCredits = 0, plans = PlanState(PlanInfo("pro", "Pro", 300, listOf("720p", "1080p"), false, 30), null, "welcome"))
        else -> WalletInfo(balance = 9, buckets = listOf(WalletBucket("daily", 1, now.plusSeconds(7200)), WalletBucket("signup", 3, now.plusSeconds(86400L * 20)), WalletBucket("paid", 5, null)), nextFreeAt = tomorrow)
    }
    override suspend fun gallery() = listOf(
        GalleryVideo("forest", "How a forest breathes", "file:///data/data/com.videomk.app/files/fake_video.mp4", pic("s_forest.jpg"), "16:9", 28.0),
        GalleryVideo("bees", "How bees make honey", "file:///data/data/com.videomk.app/files/fake_video.mp4", pic("s_bees.jpg"), "16:9", 182.0),
        GalleryVideo("focus", "3 focus tips", "file:///data/data/com.videomk.app/files/fake_video.mp4", pic("s_focus.jpg"), "9:16", 30.0),
    )
    override suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions, media: List<String>, mediaMeta: kotlinx.serialization.json.JsonObject?, libraryMedia: List<String>, brief: kotlinx.serialization.json.JsonObject?, deck: String?): String {
        // a Free account asking for more than its plan makes is refused, as the real server does (it never shortens)
        if (planMode == "free" && options.minutes * 60 > 30.5) throw ApiError.Plan("plan_length", "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", "pro", null, 30)
        return "v-new"
    }
    override suspend fun uploadPhotos(photos: List<ByteArray>, progress: (Int, Int) -> Unit): List<String> = photos.indices.map { "m$it" }
    override suspend fun playback(videoId: String): PlaybackInfo {
        // screenshots: a real local file when `files/fake_video.mp4` exists (push one with `adb push` + `run-as`), else an address that never resolves
        val local = java.io.File("/data/data/com.videomk.app/files/fake_video.mp4")
        return PlaybackInfo(if (local.exists()) "file://${local.path}" else "https://example.invalid/$videoId.mp4", "A short story about how bees turn nectar into honey.\n\nVideo by Jane Doe on Pexels (https://www.pexels.com)")
    }
    override suspend fun editorSnapshot(videoId: String) = EditorSnapshot(
        videoId, 3, EditState.fromServer("IDLE"), null, "How bees make honey", true,
        listOf(
            EditorBeat("b1", "Bees visit thousands of flowers every day to collect nectar.", SceneKind.Title, "title", "How bees make honey", "Nectar"),
            EditorBeat("b2", "Back at the hive, the nectar is passed from bee to bee.", SceneKind.Bullets, "bullets", "Passing the nectar"),
            EditorBeat("b3", "", SceneKind.Image, "image", "A honeycomb", null, 3.0, false, true, 3.0),
            EditorBeat("b4", "Fanning wings dries it into honey.", null, "mystery", "", null),
        ),
        EditorLimits(6, 70, 90),
    )
    override suspend fun applyEdits(videoId: String, baseRev: Int, ops: List<EditOp>, mode: RenderMode) = baseRev + 1
}
