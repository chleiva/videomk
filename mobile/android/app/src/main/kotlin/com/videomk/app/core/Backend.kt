package com.videomk.app.core

/** What the view models need from the server. The real one wraps [ApiClient]; tests use a fake. */
interface Backend {
    suspend fun listVideos(): List<VideoItem>
    suspend fun wallet(): WalletInfo
    suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions, media: List<String>, mediaMeta: kotlinx.serialization.json.JsonObject? = null, libraryMedia: List<String> = emptyList(), brief: kotlinx.serialization.json.JsonObject? = null, deck: String? = null): String
    suspend fun uploadPhotos(photos: List<ByteArray>, progress: (done: Int, total: Int) -> Unit): List<String>
    suspend fun playback(videoId: String): PlaybackInfo
    suspend fun editorSnapshot(videoId: String): EditorSnapshot
    suspend fun applyEdits(videoId: String, baseRev: Int, ops: List<EditOp>, mode: RenderMode): Int
    /** "Try again" reuses the failed video on the server (all its photos and options); [RetryResult.Unsupported] from an older server. */
    suspend fun retryVideo(videoId: String): RetryResult = RetryResult.Unsupported
    /** Removes a video (finished or not); false when the server cannot. */
    suspend fun deleteVideo(videoId: String): Boolean = false
    /** Stops a video that is being made and gives its credits back. */
    suspend fun cancelVideo(videoId: String): CancelResult = CancelResult.Unsupported
    /** The public showcase. */
    suspend fun gallery(): List<GalleryVideo> = emptyList()
}

/**
 * The production [Backend]. A signed-out session (the refresh token was revoked or expired) is reported through [onSignedOut] and surfaces to
 * the caller as [ApiError.Unauthorized], so every screen handles it the same way.
 */
class ApiBackend(private val api: ApiClient, private val uploader: PhotoUploader, private val onSignedOut: () -> Unit) : Backend {
    private suspend fun <T> guarded(block: suspend () -> T): T = try {
        block()
    } catch (e: AuthException) {
        if (e.kind == AuthException.Kind.SignedOut) { onSignedOut(); throw ApiError.Unauthorized }
        throw if (e.kind == AuthException.Kind.Network) ApiError.Network else ApiError.Server
    }

    override suspend fun listVideos() = guarded { api.listVideos() }
    override suspend fun wallet() = guarded { api.wallet() }
    override suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions, media: List<String>, mediaMeta: kotlinx.serialization.json.JsonObject?, libraryMedia: List<String>, brief: kotlinx.serialization.json.JsonObject?, deck: String?) =
        guarded { api.startGeneration(prompt, clientRequestId, options, media, mediaMeta, libraryMedia, brief, deck) }
    override suspend fun uploadPhotos(photos: List<ByteArray>, progress: (Int, Int) -> Unit) = guarded { uploader.upload(photos, progress) }
    override suspend fun playback(videoId: String) = guarded { api.playback(videoId) }
    override suspend fun editorSnapshot(videoId: String) = guarded { api.editorSnapshot(videoId) }
    override suspend fun applyEdits(videoId: String, baseRev: Int, ops: List<EditOp>, mode: RenderMode) = guarded { api.applyEdits(videoId, baseRev, ops, mode) }
    override suspend fun retryVideo(videoId: String) = guarded { api.retryVideo(videoId) }
    override suspend fun deleteVideo(videoId: String) = guarded { api.deleteVideo(videoId) }
    override suspend fun cancelVideo(videoId: String) = guarded { api.cancelVideo(videoId) }
    override suspend fun gallery() = api.gallery()
}
