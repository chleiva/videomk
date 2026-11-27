package com.videomk.app

import com.videomk.app.core.ApiError
import com.videomk.app.core.Backend
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.EditOp
import com.videomk.app.core.EditorSnapshot
import com.videomk.app.core.PlaybackInfo
import com.videomk.app.core.RenderMode
import com.videomk.app.core.RetryResult
import com.videomk.app.core.VideoItem
import com.videomk.app.core.WalletInfo

class FakeBackend : Backend {
    var videos: List<VideoItem> = emptyList()
    var wallet = WalletInfo(balance = 5)
    var listError: Exception? = null
    var startError: Exception? = null
    var uploadError: Exception? = null
    var startCalls = mutableListOf<Triple<String, String, List<String>>>()   // brief, request id, media
    var listCalls = 0
    var uploadCalls = 0
    var snapshots = ArrayDeque<EditorSnapshot>()
    var editCalls = mutableListOf<Triple<Int, List<EditOp>, RenderMode>>()
    var editError: Exception? = null
    var newVideoId = "new-video"
    var retryResult: RetryResult = RetryResult.Started(photos = null, unusable = 0)
    var retryError: Exception? = null
    val retryCalls = mutableListOf<String>()
    var deleteResult = true
    val deleteCalls = mutableListOf<String>()
    val startBriefs = mutableListOf<kotlinx.serialization.json.JsonObject?>()
    val startLibrary = mutableListOf<List<String>>()
    val startDecks = mutableListOf<String?>()
    val startOptions = mutableListOf<CreateOptions>()
    val startMeta = mutableListOf<kotlinx.serialization.json.JsonObject?>()

    /** When set, the next list call waits on it (a request left hanging by a sleeping phone); it is used once. */
    var listHang: kotlinx.coroutines.CompletableDeferred<Unit>? = null
    override suspend fun listVideos(): List<VideoItem> {
        listCalls++
        listHang?.let { h -> listHang = null; h.await() }
        listError?.let { throw it }; return videos
    }
    override suspend fun wallet(): WalletInfo = wallet
    override suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions, media: List<String>, mediaMeta: kotlinx.serialization.json.JsonObject?, libraryMedia: List<String>, brief: kotlinx.serialization.json.JsonObject?, deck: String?): String {
        startBriefs += brief
        startDecks += deck; startOptions += options
        startLibrary += libraryMedia
        startCalls += Triple(prompt, clientRequestId, media)
        startMeta += mediaMeta
        startError?.let { throw it }
        return newVideoId
    }
    override suspend fun uploadPhotos(photos: List<ByteArray>, progress: (Int, Int) -> Unit): List<String> {
        uploadCalls++
        progress(0, photos.size)
        uploadError?.let { throw it }
        photos.indices.forEach { progress(it + 1, photos.size) }
        return photos.indices.map { "media$it" }
    }
    override suspend fun retryVideo(videoId: String): RetryResult {
        retryCalls += videoId; retryError?.let { throw it }
        if (retryResult is RetryResult.Started || retryResult == RetryResult.AlreadyRunning) videos = videos.map { if (it.id == videoId) it.copy(status = com.videomk.app.core.VideoStatus.Running(com.videomk.app.core.VideoStatus.Stage.Starting)) else it }   // the server list shows the same video making
        return retryResult
    }
    override suspend fun deleteVideo(videoId: String): Boolean { deleteCalls += videoId; return deleteResult }
    override suspend fun playback(videoId: String) = PlaybackInfo("https://example.com/$videoId.mp4", null)
    override suspend fun editorSnapshot(videoId: String): EditorSnapshot = if (snapshots.size > 1) snapshots.removeFirst() else snapshots.firstOrNull() ?: throw ApiError.Server
    override suspend fun applyEdits(videoId: String, baseRev: Int, ops: List<EditOp>, mode: RenderMode): Int {
        editCalls += Triple(baseRev, ops, mode)
        editError?.let { throw it }
        return baseRev + 1
    }
}
