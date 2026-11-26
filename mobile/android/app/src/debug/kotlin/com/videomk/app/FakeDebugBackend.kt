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
    private val videos = listOf(
        VideoItem("v1", VideoStatus.Complete, "How bees make honey", 182.0, now.minusSeconds(3600), "https://example.com/v1.mp4", null, null, true, "16:9", "1080p"),
        VideoItem("v2", VideoStatus.Running(VideoStatus.Stage.VoiceAndVisuals), "The history of the lighthouse", null, now.minusSeconds(240), null, null, null, false, "9:16", "1080p"),
        VideoItem("v3", VideoStatus.Failed, "A calm walk through Kyoto", null, now.minusSeconds(86400), null, null, null, false, "16:9", "1080p"),
        VideoItem("v4", VideoStatus.Rejected, null, null, now.minusSeconds(172800), null, null, "This request is outside what videomk can make.", false, "16:9", "1080p"),
        VideoItem("v5", VideoStatus.Complete, "Why is the sky blue?", 61.0, now.minusSeconds(604800), "https://example.com/v5.mp4", null, null, true, "1:1", "720p"),
    )

    /** With the fake presentation switch on, two videos made from a deck are being prepared: one reading the slides, one writing the narration. */
    private val deckVideos = listOf(
        VideoItem("d1", VideoStatus.Running(VideoStatus.Stage.Writing, VideoStatus.DeckStage.Reading), "Annual plan", null, now.minusSeconds(20), null, null, null, false, "16:9", "1080p"),
        VideoItem("d2", VideoStatus.Running(VideoStatus.Stage.Writing, VideoStatus.DeckStage.Writing), "Sales kickoff", null, now.minusSeconds(60), null, null, null, false, "16:9", "1080p"),
    )

    override suspend fun listVideos(): List<VideoItem> = if (deckDemo) deckVideos + videos else videos
    override suspend fun wallet() = WalletInfo(balance = 9, buckets = listOf(WalletBucket("daily", 1, now.plusSeconds(7200)), WalletBucket("signup", 3, now.plusSeconds(86400L * 20)), WalletBucket("paid", 5, null)), nextFreeAt = now.plusSeconds(5400))
    override suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions, media: List<String>, mediaMeta: kotlinx.serialization.json.JsonObject?, libraryMedia: List<String>, brief: kotlinx.serialization.json.JsonObject?, deck: String?) = "v-new"
    override suspend fun uploadPhotos(photos: List<ByteArray>, progress: (Int, Int) -> Unit): List<String> = photos.indices.map { "m$it" }
    override suspend fun playback(videoId: String) = PlaybackInfo("https://example.invalid/$videoId.mp4", "A short story about how bees turn nectar into honey.")
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
