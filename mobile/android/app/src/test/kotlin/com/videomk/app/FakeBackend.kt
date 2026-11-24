package com.videomk.app

import com.videomk.app.core.ApiError
import com.videomk.app.core.Backend
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.EditOp
import com.videomk.app.core.EditorSnapshot
import com.videomk.app.core.PlaybackInfo
import com.videomk.app.core.RenderMode
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
    val startMeta = mutableListOf<kotlinx.serialization.json.JsonObject?>()

    override suspend fun listVideos(): List<VideoItem> { listCalls++; listError?.let { throw it }; return videos }
    override suspend fun wallet(): WalletInfo = wallet
    override suspend fun startGeneration(prompt: String, clientRequestId: String, options: CreateOptions, media: List<String>, mediaMeta: kotlinx.serialization.json.JsonObject?): String {
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
    override suspend fun playback(videoId: String) = PlaybackInfo("https://example.com/$videoId.mp4", null)
    override suspend fun editorSnapshot(videoId: String): EditorSnapshot = if (snapshots.size > 1) snapshots.removeFirst() else snapshots.firstOrNull() ?: throw ApiError.Server
    override suspend fun applyEdits(videoId: String, baseRev: Int, ops: List<EditOp>, mode: RenderMode): Int {
        editCalls += Triple(baseRev, ops, mode)
        editError?.let { throw it }
        return baseRev + 1
    }
}
