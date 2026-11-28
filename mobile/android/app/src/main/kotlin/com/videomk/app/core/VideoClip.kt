package com.videomk.app.core

import com.videomk.app.R
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okio.BufferedSink
import okio.source
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * The person's own short video clips (docs/VIDEO_UPLOAD_2026-11-28.md, clients: docs/VIDEO_UPLOAD_CLIENTS_2026-11-28.md). The feature exists only where
 * `capabilities.video_upload.enabled`. At most the first 5 seconds of a clip are used (the server trims). Nothing here logs a file name, a hash or a token.
 */
data class VideoUploadCaps(
    val enabled: Boolean, val available: Boolean, val paused: Boolean,
    val clipsPerDay: Int, val clipsLeftToday: Int, val clipsPerVideo: Int,
    val maxBytes: Long, val usedSeconds: Int, val formats: List<String>, val apiUrl: String?, val requiresPlan: String?,
) {
    companion object {
        private val DEFAULT_FORMATS = listOf("video/mp4", "video/quicktime", "video/webm")
        fun fromJson(o: JsonObject?): VideoUploadCaps? {
            o ?: return null
            return VideoUploadCaps(
                enabled = o.bool("enabled") ?: false, available = o.bool("available") ?: false, paused = o.bool("paused") ?: false,
                clipsPerDay = o.int("clips_per_day") ?: 0, clipsLeftToday = o.int("clips_left_today") ?: 0, clipsPerVideo = (o.int("clips_per_video") ?: 2).coerceAtLeast(1),
                maxBytes = o.num("max_bytes")?.toLong()?.takeIf { it > 0 } ?: (25L * 1024 * 1024), usedSeconds = o.int("used_seconds")?.takeIf { it > 0 } ?: 5,
                formats = (o.arr("formats")?.mapNotNull { (it as? JsonPrimitive)?.content?.lowercase() } ?: emptyList()).ifEmpty { DEFAULT_FORMATS },
                apiUrl = o.str("api_url")?.takeIf { it.isNotBlank() }, requiresPlan = o.str("requires_plan")?.takeIf { it.isNotBlank() },
            )
        }
    }
    val maxMb: Int get() = (maxBytes / (1024 * 1024)).toInt()
}

/** What the "Add a video" row does. [reason] says why a disabled row is disabled. */
sealed interface VideoEntry {
    data object Hidden : VideoEntry
    data object Enabled : VideoEntry
    data class Disabled(val reason: Reason, val plan: String? = null) : VideoEntry
    enum class Reason { Paused, DailyLimit, RequiresPlan, VideoFull }
}

/** The clip as the server shows it (only what the app uses). */
data class ClipInfo(
    val id: String, val status: String, val useAudio: Boolean, val duration: Double?, val sourceDuration: Double?, val trimmed: Boolean,
    val hasAudio: Boolean, val audioUsed: Boolean, val audioState: String?, val width: Int?, val height: Int?, val code: String?, val message: String?,
) {
    val ready: Boolean get() = status == "ready"
    /** The sound was asked for but the server could not use it (the picture is still used). */
    val soundDropped: Boolean get() = useAudio && !audioUsed && (audioState == "unscreened" || audioState == "unavailable")

    companion object {
        fun fromJson(o: JsonObject): ClipInfo = ClipInfo(
            id = o.str("id") ?: "", status = o.str("status") ?: "", useAudio = o.bool("use_audio") ?: false, duration = o.num("duration"), sourceDuration = o.num("source_duration"),
            trimmed = o.bool("trimmed") ?: false, hasAudio = o.bool("has_audio") ?: false, audioUsed = o.bool("audio_used") ?: false, audioState = o.str("audio_state"),
            width = o.int("width"), height = o.int("height"), code = o.str("code"), message = o.str("message"),
        )
    }
}

/** `POST .../video-uploads`: a slot (201) or an already ready clip (200 duplicate). */
sealed interface ClipSlotAnswer {
    data class Slot(val id: String, val url: String, val fields: Map<String, String>, val clipsLeftToday: Int?) : ClipSlotAnswer
    data class Duplicate(val clip: ClipInfo) : ClipSlotAnswer
}

/** The calls, behind an interface so tests and the debug build can fake them. */
interface ClipApi {
    suspend fun createSlot(sizeBytes: Long, contentType: String, useAudio: Boolean, sha256: String?): ClipSlotAnswer
    suspend fun analyse(id: String): ClipInfo
    suspend fun status(id: String): ClipInfo
    suspend fun delete(id: String)
}

/** A refusal from the clip API, as its stable `code` says (the server's message is the fallback text for a code this app does not know). */
class ClipRefusal(val http: Int, val code: String?, val text: String?, val canUpgrade: Boolean, val accountPaused: Boolean = false) : Exception()

/** The pure request body of `POST .../video-uploads` (the choice cannot be left empty; the hash is optional). */
object ClipRequests {
    fun createBody(sizeBytes: Long, contentType: String, useAudio: Boolean, sha256: String?): JsonObject = buildJsonObject {
        put("size_bytes", sizeBytes); put("content_type", contentType); put("use_audio", useAudio)
        if (!sha256.isNullOrBlank()) put("sha256", sha256)
    }
    /** `video_assets` of `POST /videos`: ready clips only, in the order shown, never more than the plan's clips per video. */
    fun videoAssets(entries: List<ClipEntry>, perVideo: Int): List<String> = entries.filter { it.phase is ClipPhase.Ready && it.serverId != null }.mapNotNull { it.serverId }.distinct().take(perVideo)
    fun assetsJson(ids: List<String>): JsonArray = JsonArray(ids.map { JsonPrimitive(it) })
}

class ApiClipApi(private val api: ApiClient, private val base: HttpUrl) : ClipApi {
    private val c = api.forBase(base)
    override suspend fun createSlot(sizeBytes: Long, contentType: String, useAudio: Boolean, sha256: String?): ClipSlotAnswer {
        val o = c.clips("POST", listOf("video-uploads"), ClipRequests.createBody(sizeBytes, contentType, useAudio, sha256))
        if (o.bool("duplicate") == true) return ClipSlotAnswer.Duplicate(ClipInfo.fromJson(o.obj("clip") ?: throw ApiError.Server))
        val up = o.obj("upload") ?: throw ApiError.Server
        return ClipSlotAnswer.Slot(
            id = o.requireString("id"), url = up.requireString("url"),
            fields = up.obj("fields")?.mapNotNull { (k, v) -> (v as? JsonPrimitive)?.takeIf { it.isString }?.let { k to it.content } }?.toMap() ?: emptyMap(), clipsLeftToday = o.int("clips_left_today"),
        )
    }
    override suspend fun analyse(id: String): ClipInfo = ClipInfo.fromJson(c.clips("POST", listOf("video-uploads", id, "analyse")).obj("clip") ?: throw ApiError.Server)
    override suspend fun status(id: String): ClipInfo = ClipInfo.fromJson(c.clips("GET", listOf("video-uploads", id)).obj("clip") ?: throw ApiError.Server)
    override suspend fun delete(id: String) { c.clips("DELETE", listOf("video-uploads", id)) }
}

/** Puts the file at the slot. Reports bytes sent. Throws [ApiError.Network] offline, [ApiError.Invalid] when the storage refused it. */
fun interface ClipUploader { suspend fun upload(url: String, fields: Map<String, String>, contentType: String, file: File, progress: (sent: Long, total: Long) -> Unit) }

/** A streaming multipart form for the presigned POST: the slot's fields first (server order), the file last. No Authorization header goes to storage. */
class ClipFormBody(private val fields: Map<String, String>, private val contentType: String, private val file: File, private val onProgress: (Long, Long) -> Unit, private val boundary: String = UUID.randomUUID().toString()) : RequestBody() {
    private val head: ByteArray = buildString {
        val all = if (fields.keys.any { it.equals("Content-Type", true) }) fields else fields + ("Content-Type" to contentType)
        for ((k, v) in all) append("--$boundary\r\nContent-Disposition: form-data; name=\"$k\"\r\n\r\n$v\r\n")
        append("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"clip.${VideoRules.extension(contentType)}\"\r\nContent-Type: $contentType\r\n\r\n")
    }.toByteArray()
    private val tail: ByteArray = "\r\n--$boundary--\r\n".toByteArray()
    override fun contentType() = "multipart/form-data; boundary=$boundary".toMediaType()
    override fun contentLength(): Long = head.size + file.length() + tail.size
    override fun writeTo(sink: BufferedSink) {
        sink.write(head)
        val total = file.length(); var sent = 0L
        onProgress(0, total)
        file.source().use { src ->
            val buf = okio.Buffer()
            while (true) {
                val n = src.read(buf, 64 * 1024L)
                if (n < 0) break
                sink.write(buf, n); sent += n; onProgress(sent, total)
            }
        }
        sink.write(tail)
    }
}

class HttpClipUploader(private val http: OkHttpClient) : ClipUploader {
    override suspend fun upload(url: String, fields: Map<String, String>, contentType: String, file: File, progress: (Long, Long) -> Unit) {
        val u = url.toHttpUrlOrNull() ?: throw ApiError.Server
        val req = Request.Builder().url(u).post(ClipFormBody(fields, contentType, file, progress)).build()
        try {
            http.newBuilder().writeTimeout(60, TimeUnit.SECONDS).callTimeout(10, TimeUnit.MINUTES).build().newCall(req).await().use { r -> if (r.code !in 200..299) throw ApiError.Invalid("") }
        } catch (e: CancellationException) { throw e } catch (e: ApiError) { throw e } catch (e: IOException) { throw ApiError.Network }
    }
}

/** What went wrong, in the app's own calm words. Nothing here says why a clip was refused. */
enum class VideoProblem(val titleRes: Int, val bodyRes: Int, val retry: Boolean) {
    TooLarge(R.string.vclip_err_large_title, R.string.vclip_err_large_body, false),
    TooLong(R.string.vclip_err_long_title, R.string.vclip_err_long_body, false),
    BadFile(R.string.vclip_err_bad_title, R.string.vclip_err_bad_body, false),
    Rejected(R.string.vclip_err_rejected_title, R.string.vclip_err_rejected_body, false),
    CheckFailed(R.string.vclip_err_check_title, R.string.vclip_err_check_body, true),
    DailyLimit(R.string.vclip_err_daily_title, R.string.vclip_err_daily_body, false),
    Paused(R.string.vclip_err_paused_title, R.string.vclip_err_paused_body, false),
    Plan(R.string.vclip_err_plan_title, R.string.vclip_err_plan_body, false),
    Offline(R.string.vclip_err_network_title, R.string.vclip_err_network_body, true),
    Stalled(R.string.vclip_err_stalled_title, R.string.vclip_err_stalled_body, true),
    Other(R.string.vclip_err_other_title, R.string.vclip_err_other_body, true);

    companion object {
        fun fromCode(http: Int, code: String?): VideoProblem = when (code) {
            "too_big" -> TooLarge
            "bad_request", "unfinished" -> BadFile
            "rejected" -> Rejected
            "check_failed" -> CheckFailed
            "video_upload_quota" -> DailyLimit
            "video_upload_paused" -> Paused
            "video_upload_plan" -> Plan
            else -> when (http) { 413 -> TooLarge; 503 -> Paused; 429 -> DailyLimit; 403 -> Plan; else -> Other }
        }
    }
}

data class ClipFailure(val problem: VideoProblem, val serverMessage: String? = null, val plan: String? = null) {
    fun title(): String = Txt.s(problem.titleRes)
    fun body(caps: VideoUploadCaps?): String = when (problem) {
        VideoProblem.TooLarge -> Txt.s(problem.bodyRes, caps?.maxMb ?: 25)
        // an account-level refusal (a safety pause, a plan paywall) is the server's own sentence
        VideoProblem.Plan, VideoProblem.Other -> serverMessage?.takeIf { it.isNotBlank() } ?: Txt.s(problem.bodyRes)
        else -> Txt.s(problem.bodyRes)
    }
}

sealed interface ClipPhase {
    /** Reading the file's length and tracks (a blink). */
    data object Inspecting : ClipPhase
    /** The sheet is open: the person must choose the sound. */
    data object AskSound : ClipPhase
    /** Copying, trimming on the phone when the file is over the limit, hashing. */
    data object Preparing : ClipPhase
    data class Uploading(val sent: Long, val total: Long) : ClipPhase { val percent: Int get() = if (total <= 0) 0 else (sent * 100 / total).toInt().coerceIn(0, 100) }
    /** "Checking your clip": [slow] after 90 s ("taking longer than usual, we will keep checking"). */
    data class Analysing(val slow: Boolean = false) : ClipPhase
    data object Ready : ClipPhase
    data class Failed(val failure: ClipFailure) : ClipPhase

    /** Counts as not usable and still running (the Create button waits for these). */
    val busy: Boolean get() = this is Inspecting || this is AskSound || this is Preparing || this is Uploading || this is Analysing
}

/**
 * One clip on the Create screen. [useAudio] is null until the person has answered (it cannot be left empty). [thumb] is a JPEG of a local frame (never the signed link).
 * [name] is the file's display name, kept in memory for the sheet only.
 */
data class ClipEntry(
    val id: String, val name: String? = null, val phase: ClipPhase = ClipPhase.Inspecting, val useAudio: Boolean? = null, val hasAudio: Boolean? = null,
    val durationMs: Long? = null, val width: Int? = null, val height: Int? = null, val thumb: ByteArray? = null, val serverId: String? = null, val info: ClipInfo? = null,
    val trimmedOnPhone: Boolean = false,
) {
    val aspect: Float get() { val w = info?.width ?: width; val h = info?.height ?: height; return if (w != null && h != null && w > 0 && h > 0) w.toFloat() / h else 1f }
    val ready: Boolean get() = phase is ClipPhase.Ready
    /** Shows "first 5 s": the file is longer than what is used. */
    val longer: Boolean get() = (durationMs ?: 0) > VideoRules.USED_SECONDS * 1000L + 250
    val soundOn: Boolean get() = if (info != null && ready) info.audioUsed else useAudio == true
}

/** What the device decides before anything is uploaded. */
sealed interface ClipDecision {
    /** Upload the file as it is. */
    data object AsIs : ClipDecision
    /** Over the limit: cut the first seconds on the phone first, then check the size again. */
    data object TrimFirst : ClipDecision
    data class Reject(val problem: VideoProblem) : ClipDecision
}

object VideoRules {
    const val USED_SECONDS = 5
    /** An original this big is not worth even copying (the phone would only fill its cache): said plainly. */
    const val ABSURD_BYTES = 1024L * 1024 * 1024
    /** The server's own limit on length is 600 s. */
    const val ABSURD_MILLIS = 600_000L

    fun extension(contentType: String): String = when (contentType.lowercase()) { "video/quicktime" -> "mov"; "video/webm" -> "webm"; else -> "mp4" }

    fun entry(caps: VideoUploadCaps?, leftToday: Int?, clipsInVideo: Int): VideoEntry {
        caps ?: return VideoEntry.Hidden
        if (!caps.enabled) return VideoEntry.Hidden
        if (caps.paused) return VideoEntry.Disabled(VideoEntry.Reason.Paused)
        if (!caps.available && caps.requiresPlan != null) return VideoEntry.Disabled(VideoEntry.Reason.RequiresPlan, caps.requiresPlan)
        if ((leftToday ?: caps.clipsLeftToday) <= 0 && (caps.clipsPerDay > 0 || !caps.available)) return VideoEntry.Disabled(VideoEntry.Reason.DailyLimit)
        if (!caps.available) return VideoEntry.Disabled(VideoEntry.Reason.Paused)
        if (clipsInVideo >= caps.clipsPerVideo) return VideoEntry.Disabled(VideoEntry.Reason.VideoFull)
        return VideoEntry.Enabled
    }

    /** The type the server takes, or null (the picker's own type, lower-cased; an unknown one is refused before any copy). */
    fun contentType(mime: String?, caps: VideoUploadCaps): String? = mime?.lowercase()?.substringBefore(';')?.trim()?.takeIf { it in caps.formats }

    /** The first check on what the picker said. [size] null when the provider does not say; [durationMs] null when unreadable. */
    fun decide(size: Long?, mime: String?, durationMs: Long?, caps: VideoUploadCaps): ClipDecision {
        if (contentType(mime, caps) == null) return ClipDecision.Reject(VideoProblem.BadFile)
        if (size != null && size <= 0) return ClipDecision.Reject(VideoProblem.BadFile)
        if (durationMs != null && durationMs > ABSURD_MILLIS) return ClipDecision.Reject(VideoProblem.TooLong)
        if (size != null && size > ABSURD_BYTES) return ClipDecision.Reject(VideoProblem.TooLarge)
        if (size != null && size > caps.maxBytes) return ClipDecision.TrimFirst
        return ClipDecision.AsIs
    }

    /** After the phone's own cut: the copy must fit, else the person is told plainly. */
    fun afterTrim(trimmedBytes: Long?, caps: VideoUploadCaps): VideoProblem? = when { trimmedBytes == null || trimmedBytes <= 0 -> VideoProblem.TooLarge; trimmedBytes > caps.maxBytes -> VideoProblem.TooLarge; else -> null }

    /** The notice in the sheet: the first 5 seconds are used; when the file is longer its length is named too (whole seconds, at least 6). */
    data class Notice(val longerSeconds: Int?) { val longer: Boolean get() = longerSeconds != null }
    fun notice(durationMs: Long?): Notice = Notice(durationMs?.takeIf { it > USED_SECONDS * 1000L + 250 }?.let { ((it + 500) / 1000).toInt().coerceAtLeast(USED_SECONDS + 1) })

    fun sha256(file: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { ins -> val buf = ByteArray(64 * 1024); while (true) { val n = ins.read(buf); if (n < 0) break; md.update(buf, 0, n) } }
        return md.digest().joinToString("") { "%02x".format(it) }
    }

    /** Waits between status calls: 1.5 s, 3 s after 20 s (docs/VIDEO_UPLOAD_CLIENTS section 4). "Taking longer than usual" after 90 s; a last stop after 5 minutes. */
    fun pollIntervalMillis(elapsedMillis: Long): Long = if (elapsedMillis < 20_000) 1_500 else 3_000
    const val SLOW_AFTER_MILLIS = 90_000L
    const val GIVE_UP_MILLIS = 5 * 60_000L
    const val MAX_STATUS_ERRORS = 5

    /** The failure the Create flow shows for an error of the clip calls. */
    fun failureOf(e: Throwable): ClipFailure = when (e) {
        is ClipRefusal -> if (e.accountPaused) ClipFailure(VideoProblem.Other, e.text) else ClipFailure(VideoProblem.fromCode(e.http, e.code), e.text, null)
        is ApiError.Paused -> ClipFailure(VideoProblem.Other, e.text)
        is ApiError.Network -> ClipFailure(VideoProblem.Offline)
        is ApiError.Invalid -> ClipFailure(VideoProblem.Other)
        else -> ClipFailure(VideoProblem.Other)
    }
}

/** What the picker gave: [open] reads it with the one-time grant. [handle] is the platform's own reference (a Uri), used only by [ClipMedia]. */
class VideoPick(val name: String?, val mime: String?, val size: Long?, val handle: Any?, val open: () -> InputStream?)

/** What the phone can say about a clip without copying it. */
data class ClipProbe(val durationMs: Long?, val hasAudio: Boolean?, val width: Int?, val height: Int?, val thumb: ByteArray?)

/** The platform's media tools (probe, cut the first seconds, a poster frame), behind an interface so the journey is tested without a codec. */
interface ClipMedia {
    fun probe(pick: VideoPick): ClipProbe?
    /** Writes the first [seconds] to [dst] (an MP4), without the sound when [keepAudio] is false. False when the phone cannot do it. */
    fun trim(src: File, dst: File, seconds: Double, keepAudio: Boolean): Boolean
    fun thumbnail(file: File): ByteArray?
}

/**
 * All the clips of the video being composed. Lives in the composer's ViewModel. Per clip: probe, [ClipPhase.AskSound] (unless the file has no sound), a private copy,
 * a cut of the first seconds on the phone when the file is over the limit, hash, `POST video-uploads` (a duplicate is ready at once), upload with progress, analyse, poll.
 * The private copy lives until the clip is removed, so a failed upload can be tried again; at the next app start [cleanLeftovers] removes what a killed process left.
 * Calls [onState] with the whole list on every change (always on [scope]'s thread).
 */
class ClipController(
    private val scope: CoroutineScope,
    private val root: File,
    private val media: ClipMedia,
    private val onState: (List<ClipEntry>) -> Unit = {},
    private val wait: suspend (Long) -> Unit = { delay(it) },
    private val nowMillis: () -> Long = System::currentTimeMillis,
    private val io: kotlin.coroutines.CoroutineContext = Dispatchers.IO,
) {
    var entries: List<ClipEntry> = emptyList()
        private set
    private var api: ClipApi? = null
    private var uploader: ClipUploader? = null
    var caps: VideoUploadCaps? = null
        private set
    /** Clips the person can still add today (the capabilities' number, counted down as slots are taken). */
    var leftToday: Int? = null
        private set
    private val jobs = HashMap<String, Job>()
    private val picks = HashMap<String, VideoPick>()
    private val files = HashMap<String, File>()
    private val types = HashMap<String, String>()

    fun attach(api: ClipApi?, uploader: ClipUploader?) { this.api = api; this.uploader = uploader }
    fun setCaps(c: VideoUploadCaps?) { caps = c; leftToday = c?.clipsLeftToday }

    private fun update(id: String, f: (ClipEntry) -> ClipEntry) { entries = entries.map { if (it.id == id) f(it) else it }; onState(entries) }
    private fun entry(id: String) = entries.firstOrNull { it.id == id }
    private fun fail(id: String, f: ClipFailure) = update(id) { it.copy(phase = ClipPhase.Failed(f)) }

    val readyIds: List<String> get() = ClipRequests.videoAssets(entries, caps?.clipsPerVideo ?: 2)
    val busy: Boolean get() = entries.any { it.phase.busy }
    val vacancies: Int get() = (caps?.clipsPerVideo ?: 0) - entries.count { it.phase !is ClipPhase.Failed }

    /** A pick: the entry appears at once; the sheet follows when the file has sound. Returns false when the video already holds all its clips. */
    fun add(pick: VideoPick): Boolean {
        val c = caps ?: return false
        if (entries.count { it.phase !is ClipPhase.Failed } >= c.clipsPerVideo) return false
        val id = UUID.randomUUID().toString()
        picks[id] = pick
        entries = entries + ClipEntry(id, name = pick.name?.take(120))
        onState(entries)
        jobs[id] = scope.launch {
            val probe = try { withContext(io) { media.probe(pick) } } catch (e: CancellationException) { throw e } catch (e: Exception) { null }
            val size = pick.size
            update(id) { it.copy(durationMs = probe?.durationMs, hasAudio = probe?.hasAudio, width = probe?.width, height = probe?.height, thumb = probe?.thumb) }
            when (val d = VideoRules.decide(size, pick.mime, probe?.durationMs, c)) {
                is ClipDecision.Reject -> { fail(id, ClipFailure(d.problem)); return@launch }
                else -> {}
            }
            types[id] = VideoRules.contentType(pick.mime, c)!!
            if (probe?.hasAudio == false) { update(id) { it.copy(useAudio = false, phase = ClipPhase.Preparing) }; runPipeline(id) }
            else update(id) { it.copy(phase = ClipPhase.AskSound) }
        }
        return true
    }

    /** The sheet's answer. On an entry that is already ready or failed it changes the sound: the clip is made again with the other choice. */
    fun answer(id: String, keepSound: Boolean) {
        val e = entry(id) ?: return
        when (e.phase) {
            is ClipPhase.AskSound -> {
                val old = e.serverId
                if (old != null && e.info != null && e.soundOn == keepSound) { update(id) { it.copy(phase = ClipPhase.Ready) }; return }   // the same answer: nothing changes
                update(id) { it.copy(useAudio = keepSound, phase = ClipPhase.Preparing, serverId = null, info = null) }
                jobs[id]?.cancel(); jobs[id] = scope.launch { if (old != null) runCatching { api?.delete(old) }; runPipeline(id) }
            }
            is ClipPhase.Failed -> {
                update(id) { it.copy(useAudio = keepSound, phase = ClipPhase.Preparing, serverId = null, info = null) }
                jobs[id]?.cancel(); jobs[id] = scope.launch { runPipeline(id) }
            }
            else -> {}
        }
    }

    /** Reopens the sheet for a clip (tap on its sound mark). */
    fun askAgain(id: String) { val e = entry(id) ?: return; if (e.ready && e.hasAudio != false) update(id) { it.copy(phase = ClipPhase.AskSound) } }
    /** The sheet was closed without an answer on an entry that had one: back to ready. Without an answer the pick is dropped (it cannot be left empty). */
    fun dismissSheet(id: String) { val e = entry(id) ?: return; if (e.phase is ClipPhase.AskSound) { if (e.serverId != null && e.info != null) update(id) { it.copy(phase = ClipPhase.Ready) } else remove(id) } }

    private suspend fun runPipeline(id: String) {
        val c = caps ?: return
        val a = api; val up = uploader
        val pick = picks[id]
        if (a == null || up == null || pick == null) { fail(id, ClipFailure(VideoProblem.Other)); return }
        try {
            val ctype = types[id] ?: VideoRules.contentType(pick.mime, c) ?: run { fail(id, ClipFailure(VideoProblem.BadFile)); return }
            var file = files[id]
            if (file == null || !file.exists()) {
                val prep = withContext(io) { prepare(id, pick, c, ctype) }
                when (prep) {
                    is Prepared.Bad -> { fail(id, ClipFailure(prep.problem)); return }
                    is Prepared.Done -> { file = prep.file; files[id] = file; update(id) { it.copy(thumb = prep.thumb ?: it.thumb, trimmedOnPhone = prep.trimmed) } }
                }
            }
            val sendType = if (entry(id)?.trimmedOnPhone == true) "video/mp4" else ctype
            val f = file!!
            val hash = withContext(io) { VideoRules.sha256(f) }
            val size = f.length()
            update(id) { it.copy(phase = ClipPhase.Uploading(0, size)) }
            val slot = a.createSlot(size, sendType, entry(id)?.useAudio ?: false, hash)
            when (slot) {
                is ClipSlotAnswer.Duplicate -> { finish(id, slot.clip); return }
                is ClipSlotAnswer.Slot -> {
                    slot.clipsLeftToday?.let { leftToday = it } ?: run { leftToday = leftToday?.minus(1)?.coerceAtLeast(0) }
                    update(id) { it.copy(serverId = slot.id) }
                    var last = -1
                    up.upload(slot.url, slot.fields, sendType, f) { sent, total ->
                        val p = if (total <= 0) 0 else (sent * 100 / total).toInt()
                        if (p != last) { last = p; update(id) { e -> if (e.phase is ClipPhase.Uploading) e.copy(phase = ClipPhase.Uploading(sent, total)) else e } }
                    }
                    update(id) { it.copy(phase = ClipPhase.Analysing()) }
                    val first = a.analyse(slot.id)
                    if (!first.ready && first.status != "analysing" && first.status != "pending") { finish(id, first); return }
                    poll(id, slot.id)
                }
            }
        } catch (e: CancellationException) { throw e
        } catch (e: Exception) { fail(id, VideoRules.failureOf(e)) }
    }

    private sealed interface Prepared { class Done(val file: File, val thumb: ByteArray?, val trimmed: Boolean) : Prepared; class Bad(val problem: VideoProblem) : Prepared }

    /** Streams the pick into our own cache folder (hard stop at the absurd size, no name kept on disk), cuts the first seconds when the file is over the limit, takes a poster frame. */
    private fun prepare(id: String, pick: VideoPick, c: VideoUploadCaps, ctype: String): Prepared {
        val input = pick.open() ?: return Prepared.Bad(VideoProblem.BadFile)
        root.mkdirs()
        val raw = File(root, UUID.randomUUID().toString() + ".src")
        try {
            var total = 0L
            input.use { ins -> raw.outputStream().use { o ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = ins.read(buf); if (n < 0) break
                    total += n
                    if (total > VideoRules.ABSURD_BYTES) { raw.delete(); return Prepared.Bad(VideoProblem.TooLarge) }
                    o.write(buf, 0, n)
                }
            } }
            if (total == 0L) { raw.delete(); return Prepared.Bad(VideoProblem.BadFile) }
            val keepAudio = entry(id)?.useAudio == true
            if (VideoRules.decide(total, ctype, null, c) == ClipDecision.TrimFirst) {
                val cut = File(root, UUID.randomUUID().toString() + ".mp4")
                val ok = try { media.trim(raw, cut, c.usedSeconds.toDouble(), keepAudio) } catch (e: Exception) { false }
                raw.delete()
                val problem = VideoRules.afterTrim(if (ok) cut.length() else null, c)
                if (problem != null) { cut.delete(); return Prepared.Bad(problem) }
                return Prepared.Done(cut, media.thumbnail(cut), true)
            }
            return Prepared.Done(raw, media.thumbnail(raw), false)
        } catch (e: Exception) { raw.delete(); throw e }
    }

    private suspend fun poll(id: String, serverId: String) {
        val a = api ?: return
        val started = nowMillis(); var errors = 0
        while (true) {
            val elapsed = nowMillis() - started
            if (elapsed > VideoRules.GIVE_UP_MILLIS) { fail(id, ClipFailure(VideoProblem.Stalled)); return }
            if (elapsed > VideoRules.SLOW_AFTER_MILLIS) update(id) { e -> if ((e.phase as? ClipPhase.Analysing)?.slow == false) e.copy(phase = ClipPhase.Analysing(slow = true)) else e }
            wait(VideoRules.pollIntervalMillis(elapsed))
            val s = try { a.status(serverId).also { errors = 0 } } catch (e: CancellationException) { throw e
            } catch (e: ClipRefusal) { fail(id, VideoRules.failureOf(e)); return
            } catch (e: Exception) { if (++errors >= VideoRules.MAX_STATUS_ERRORS) { fail(id, ClipFailure(VideoProblem.Stalled)); return }; continue }
            if (s.status != "analysing" && s.status != "pending") { finish(id, s); return }
        }
    }

    private fun finish(id: String, clip: ClipInfo) {
        when {
            clip.ready -> update(id) { it.copy(phase = ClipPhase.Ready, serverId = clip.id.ifEmpty { it.serverId }, info = clip) }
            clip.status == "rejected" || clip.code == "rejected" -> fail(id, ClipFailure(VideoProblem.Rejected))
            else -> fail(id, ClipFailure(VideoProblem.CheckFailed, clip.message))
        }
        // the poster is local: the phone's own frame; the signed link is never kept
    }

    /** Try again after a failure that allows it (a fresh upload; it does not count against today's clips when the server could not check). */
    fun retry(id: String) {
        val e = entry(id) ?: return
        val f = (e.phase as? ClipPhase.Failed)?.failure ?: return
        if (!f.problem.retry) return
        val old = e.serverId
        update(id) { it.copy(phase = ClipPhase.Preparing, serverId = null, info = null) }
        jobs[id]?.cancel(); jobs[id] = scope.launch { if (old != null && f.problem == VideoProblem.CheckFailed) runCatching { api?.delete(old) }; runPipeline(id) }
    }

    /** "Keep checking" after a stall: look at the same clip again. */
    fun keepWaiting(id: String) {
        val e = entry(id) ?: return; val sid = e.serverId ?: return
        if ((e.phase as? ClipPhase.Failed)?.failure?.problem != VideoProblem.Stalled) return
        update(id) { it.copy(phase = ClipPhase.Analysing()) }
        jobs[id]?.cancel(); jobs[id] = scope.launch { try { poll(id, sid) } catch (x: CancellationException) { throw x } catch (x: Exception) { fail(id, VideoRules.failureOf(x)) } }
    }

    /** Take a clip out: everything for it stops, its private copy goes, and the server is asked to delete its record (a clip used by a made video keeps its own copy). */
    fun remove(id: String) {
        val e = entry(id)
        jobs.remove(id)?.cancel(); picks.remove(id); types.remove(id)
        files.remove(id)?.let { runCatching { it.delete() } }
        entries = entries.filterNot { it.id == id }; onState(entries)
        val sid = e?.serverId
        if (sid != null) scope.launch(io) { runCatching { api?.delete(sid) } }
    }

    /** After a video was started: the clips belong to it. Local copies go; the server records stay (the video took its own copy). */
    fun clearAfterSend() {
        jobs.values.forEach { it.cancel() }; jobs.clear(); picks.clear(); types.clear()
        files.values.forEach { runCatching { it.delete() } }; files.clear()
        entries = emptyList(); onState(entries)
    }

    /** Discard the draft: stop, delete local copies and the server records of the clips (nothing used them). */
    fun discard() { entries.map { it.id }.forEach { remove(it) } }

    /** The ViewModel is gone: stop and delete the local copies, no state to report. */
    fun release() { jobs.values.forEach { it.cancel() }; jobs.clear(); files.values.forEach { runCatching { it.delete() } }; files.clear(); root.deleteRecursively() }

    fun filesOnDisk(): Int = root.listFiles()?.size ?: 0

    companion object { fun cleanLeftovers(root: File) { root.deleteRecursively() } }
}
