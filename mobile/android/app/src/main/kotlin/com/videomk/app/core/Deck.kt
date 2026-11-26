package com.videomk.app.core

import com.videomk.app.R
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okio.BufferedSink
import okio.source
import java.io.File
import java.io.IOException
import java.io.InputStream
import java.util.UUID
import java.util.concurrent.TimeUnit

/**
 * Presentations (PowerPoint and PDF) to video, client side (contract: docs/CREATE_API.md "Making a video from a presentation deck").
 * The feature exists only where `capabilities.deck` is present. Nothing here ever logs a file name or content.
 */
data class DeckCaps(val maxMb: Int, val maxSlides: Int, val formats: List<String>) {
    val maxBytes: Long get() = maxMb.toLong() * 1024L * 1024L

    /** What the system document picker may offer. */
    val mimeTypes: Array<String> get() = formats.mapNotNull { f -> DeckFormat.entries.firstOrNull { it.wire == f }?.mime }.toTypedArray()

    companion object {
        private val KNOWN = DeckFormat.entries.map { it.wire }
        fun fromJson(o: JsonObject): DeckCaps = DeckCaps(
            maxMb = o.int("max_mb")?.takeIf { it > 0 } ?: 50,
            maxSlides = o.int("max_slides")?.takeIf { it > 0 } ?: 60,
            formats = (o.arr("formats")?.mapNotNull { (it as? JsonPrimitive)?.content?.lowercase() }?.filter { it in KNOWN }?.distinct() ?: emptyList()).ifEmpty { KNOWN },
        )
    }
}

enum class DeckFormat(val wire: String, val mime: String) {
    Pptx("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    Pdf("pdf", "application/pdf");

    companion object {
        fun ofExtension(name: String?): DeckFormat? = extension(name)?.let { e -> entries.firstOrNull { it.wire == e } }
        fun ofMime(mime: String?): DeckFormat? = mime?.lowercase()?.let { m -> entries.firstOrNull { it.mime == m } }
        fun extension(name: String?): String? = name?.takeIf { '.' in it }?.substringAfterLast('.')?.lowercase()?.trim()
    }
}

/** What went wrong, in the app's own calm words (the server's `code` is mapped here; its message is only a fallback for a code this app does not know). */
enum class DeckProblem(val titleRes: Int, val bodyRes: Int, val action: DeckAction) {
    TooLarge(R.string.deck_err_too_large_title, R.string.deck_err_too_large_body, DeckAction.PickAgain),
    TooManySlides(R.string.deck_err_too_many_slides_title, R.string.deck_err_too_many_slides_body, DeckAction.PickAgain),
    Encrypted(R.string.deck_err_encrypted_title, R.string.deck_err_encrypted_body, DeckAction.PickAgain),
    Macro(R.string.deck_err_macro_title, R.string.deck_err_macro_body, DeckAction.PickAgain),
    Corrupt(R.string.deck_err_corrupt_title, R.string.deck_err_corrupt_body, DeckAction.PickAgain),
    Unsupported(R.string.deck_err_unsupported_title, R.string.deck_err_unsupported_body, DeckAction.PickAgain),
    Empty(R.string.deck_err_empty_title, R.string.deck_err_empty_body, DeckAction.PickAgain),
    Unsafe(R.string.deck_err_unsafe_title, R.string.deck_err_unsafe_body, DeckAction.PickAgain),
    Timeout(R.string.deck_err_timeout_title, R.string.deck_err_timeout_body, DeckAction.PickAgain),
    ConvertFailed(R.string.deck_err_convert_title, R.string.deck_err_convert_body, DeckAction.PickAgain),
    /** The upload could not run or finish: the temporary copy is still here, so Try again needs no new pick. */
    Offline(R.string.deck_err_network_title, R.string.deck_err_network_body, DeckAction.Retry),
    UploadFailed(R.string.deck_err_upload_title, R.string.deck_err_upload_body, DeckAction.Retry),
    DailyLimit(R.string.deck_err_daily_title, R.string.deck_err_daily_body, DeckAction.None),
    Unavailable(R.string.deck_err_unavailable_title, R.string.deck_err_unavailable_body, DeckAction.None),
    /** We stopped polling after a sensible time; the deck may still finish. */
    Stalled(R.string.deck_err_stalled_title, R.string.deck_err_stalled_body, DeckAction.KeepWaiting),
    Other(R.string.deck_err_other_title, R.string.deck_err_other_body, DeckAction.PickAgain);

    companion object {
        /** The server's stable codes (a `failed` deck, or a 400 from the deck calls and generate). */
        fun fromCode(code: String?): DeckProblem = when (code) {
            "deck_too_large" -> TooLarge
            "deck_too_many_slides" -> TooManySlides
            "deck_encrypted" -> Encrypted
            "deck_macro" -> Macro
            "deck_corrupt" -> Corrupt
            "deck_unsupported" -> Unsupported
            "deck_empty" -> Empty
            "deck_unsafe" -> Unsafe
            "deck_convert_timeout" -> Timeout
            "deck_convert_failed" -> ConvertFailed
            "too_many_decks" -> DailyLimit
            "unavailable" -> Unavailable
            else -> Other
        }
    }
}

/** The one button a failure offers (besides Remove). */
enum class DeckAction { PickAgain, Retry, KeepWaiting, None }

data class DeckFailure(val problem: DeckProblem, val serverMessage: String? = null) {
    fun title(): String = Txt.s(problem.titleRes)
    fun body(caps: DeckCaps?): String = when (problem) {
        DeckProblem.TooLarge -> Txt.s(problem.bodyRes, caps?.maxMb ?: 50)
        DeckProblem.TooManySlides -> Txt.s(problem.bodyRes, caps?.maxSlides ?: 60)
        DeckProblem.Other -> serverMessage?.takeIf { it.isNotBlank() } ?: Txt.s(problem.bodyRes)
        else -> Txt.s(problem.bodyRes)
    }
}

/** What the device can tell before anything is uploaded: the format and the size. */
sealed interface DeckCheck {
    data class Ok(val format: DeckFormat) : DeckCheck
    data class Rejected(val problem: DeckProblem) : DeckCheck
}

object DeckRules {
    /** Extensions people have that this feature does not take (the app says "export as .pptx or PDF"). */
    private val EXPORT_FIRST = setOf("ppt", "pptm", "pps", "ppsx", "potx", "potm", "key", "odp", "pages", "doc", "docx")

    /** [sizeBytes] is what the provider says (null when it does not say; the copy then counts for itself). */
    fun check(name: String?, mime: String?, sizeBytes: Long?, caps: DeckCaps): DeckCheck {
        val ext = DeckFormat.extension(name)
        if (ext in EXPORT_FIRST) return DeckCheck.Rejected(DeckProblem.Unsupported)
        val format = DeckFormat.ofExtension(name) ?: DeckFormat.ofMime(mime)   // the first bytes are checked after the copy
        if (format == null || format.wire !in caps.formats) return DeckCheck.Rejected(DeckProblem.Unsupported)
        if (sizeBytes != null) {
            if (sizeBytes <= 0) return DeckCheck.Rejected(DeckProblem.Empty)
            if (sizeBytes > caps.maxBytes) return DeckCheck.Rejected(DeckProblem.TooLarge)
        }
        return DeckCheck.Ok(format)
    }

    /** Null when the first bytes fit the format; else why not (an old binary .ppt is "unsupported", anything else "damaged"). */
    fun sniff(format: DeckFormat, head: ByteArray): DeckProblem? {
        fun starts(vararg b: Int) = head.size >= b.size && b.indices.all { (head[it].toInt() and 0xFF) == b[it] }
        if (format == DeckFormat.Pdf && starts('%'.code, 'P'.code, 'D'.code, 'F'.code)) return null
        if (format == DeckFormat.Pptx && starts('P'.code, 'K'.code)) return null
        return if (starts(0xD0, 0xCF, 0x11, 0xE0)) DeckProblem.Unsupported else DeckProblem.Corrupt
    }
}

/** `POST .../decks` answer: where to put the file. [fields] keep the server's order (the file part comes last). */
data class DeckSlot(val id: String, val format: DeckFormat, val url: String, val fields: Map<String, String>, val maxBytes: Long?)

sealed interface DeckStatus {
    data object Uploading : DeckStatus
    data object Processing : DeckStatus
    data class Ready(val info: DeckReady) : DeckStatus
    data class Failed(val code: String?, val message: String?) : DeckStatus

    companion object {
        fun fromJson(id: String, o: JsonObject): DeckStatus = when (o.str("status")) {
            "uploading" -> Uploading
            "ready" -> {
                val minutes = o.num("suggested_minutes")?.takeIf { it > 0 } ?: 1.0
                Ready(DeckReady(id, o.int("slides") ?: 0, minutes, o.int("suggested_credits")?.takeIf { it > 0 } ?: Lengths.credits(minutes)))
            }
            "failed" -> Failed(o.str("code"), o.str("message"))
            else -> Processing
        }
    }
}

/** A ready presentation: its id for `generate`, what it holds and what the server suggests (length and its price at the default resolution). */
data class DeckReady(val id: String, val slides: Int, val suggestedMinutes: Double, val suggestedCredits: Int)

/** The three calls, behind an interface so tests and the debug build can fake them. */
interface DeckApi {
    suspend fun createSlot(format: DeckFormat, size: Long): DeckSlot
    suspend fun process(id: String)
    suspend fun status(id: String): DeckStatus
}

/** Puts the file at the slot. Reports bytes sent. Throws [ApiError.Network] offline, [ApiError.Invalid] when the storage refused it. */
fun interface DeckUploader { suspend fun upload(slot: DeckSlot, file: File, progress: (sent: Long, total: Long) -> Unit) }

class ApiDeckApi(private val api: ApiClient) : DeckApi {
    override suspend fun createSlot(format: DeckFormat, size: Long): DeckSlot {
        val o = api.deck("POST", body = buildJsonObject { put("format", format.wire); put("size", size) })
        val d = o.obj("deck") ?: throw ApiError.Server
        return DeckSlot(
            id = d.requireString("id"), format = format, url = d.requireString("url"),
            fields = d.obj("fields")?.mapNotNull { (k, v) -> (v as? JsonPrimitive)?.takeIf { it.isString }?.let { k to it.content } }?.toMap() ?: emptyMap(),
            maxBytes = o.num("max_bytes")?.toLong(),
        )
    }

    override suspend fun process(id: String) { api.deck("POST", listOf(id, "process")) }
    override suspend fun status(id: String): DeckStatus = DeckStatus.fromJson(id, api.deck("GET", listOf(id)))
}

/**
 * A streaming multipart form for the presigned POST: the slot's fields first (in the order the server gave them, plus the content type if the server left it out),
 * the file last. The file is read from disk in small pieces, so a 50 MB deck never sits in memory. No Authorization header goes to storage.
 */
class DeckFormBody(private val slot: DeckSlot, private val file: File, private val onProgress: (sent: Long, total: Long) -> Unit, private val boundary: String = UUID.randomUUID().toString()) : RequestBody() {
    private val head: ByteArray = buildString {
        val fields = if (slot.fields.keys.any { it.equals("Content-Type", true) }) slot.fields else slot.fields + ("Content-Type" to slot.format.mime)
        for ((k, v) in fields) append("--$boundary\r\nContent-Disposition: form-data; name=\"$k\"\r\n\r\n$v\r\n")
        append("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"deck.${slot.format.wire}\"\r\nContent-Type: ${slot.format.mime}\r\n\r\n")
    }.toByteArray()
    private val tail: ByteArray = "\r\n--$boundary--\r\n".toByteArray()

    override fun contentType() = "multipart/form-data; boundary=$boundary".toMediaType()
    override fun contentLength(): Long = head.size + file.length() + tail.size

    override fun writeTo(sink: BufferedSink) {
        sink.write(head)
        val total = file.length()
        var sent = 0L
        onProgress(0, total)
        file.source().use { src ->
            val buf = okio.Buffer()
            while (true) {
                val n = src.read(buf, 64 * 1024L)
                if (n < 0) break
                sink.write(buf, n)
                sent += n
                onProgress(sent, total)
            }
        }
        sink.write(tail)
    }
}

class HttpDeckUploader(private val http: OkHttpClient) : DeckUploader {
    override suspend fun upload(slot: DeckSlot, file: File, progress: (Long, Long) -> Unit) {
        val url = slot.url.toHttpUrlOrNull() ?: throw ApiError.Server
        val req = Request.Builder().url(url).post(DeckFormBody(slot, file, progress)).build()
        try {
            http.newBuilder().writeTimeout(60, TimeUnit.SECONDS).callTimeout(15, TimeUnit.MINUTES).build().newCall(req).await().use { r ->
                if (r.code !in 200..299) throw ApiError.Invalid("")
            }
        } catch (e: CancellationException) { throw e } catch (e: ApiError) { throw e } catch (e: IOException) { throw ApiError.Network }
    }
}

/** What the journey shows. [name] is the file's display name (kept in memory for the card only: never logged, never stored). */
sealed interface DeckState {
    data object Idle : DeckState
    data class Copying(val name: String) : DeckState
    data class Uploading(val name: String, val sent: Long, val total: Long) : DeckState {
        val percent: Int get() = if (total <= 0) 0 else (sent * 100 / total).toInt().coerceIn(0, 100)
    }
    data class Processing(val name: String) : DeckState
    data class Ready(val name: String, val info: DeckReady) : DeckState
    data class Failed(val name: String?, val failure: DeckFailure) : DeckState

    /** A presentation is on the Create screen in any form (it then replaces the photos). */
    val attached: Boolean get() = this !is Idle
}

/** Waits between status calls: quick at first (processing takes 5 to 30 s), a little slower later, never more than 5 s. */
object DeckBackoff {
    fun intervalMillis(attempt: Int): Long = (2000L + 500L * (attempt / 5)).coerceAtMost(5000L)
    const val GIVE_UP_MILLIS = 3 * 60_000L
    const val MAX_STATUS_ERRORS = 5
}

/** The picked file, as the document picker gave it: [open] reads it with the one-time grant (never made persistable). */
class DeckPick(val name: String?, val mime: String?, val size: Long?, val open: () -> InputStream?)

/**
 * The whole journey for one presentation: check, a private temporary copy, request the slot, upload with progress, process, poll. Lives in the composer's
 * ViewModel (a rotation keeps it). The temporary copy is deleted the moment the upload finishes, on Cancel, on Remove, on any failure that needs a new pick,
 * at the next app start and at account deletion. Calls [onState] on every change.
 */
class DeckJourney(
    private val scope: CoroutineScope,
    private val root: File,
    private val onState: (DeckState) -> Unit = {},
    private val wait: suspend (Long) -> Unit = { delay(it) },
    private val nowMillis: () -> Long = System::currentTimeMillis,
    private val io: kotlin.coroutines.CoroutineContext = Dispatchers.IO,
) {
    @Volatile var state: DeckState = DeckState.Idle
        private set
    private var api: DeckApi? = null
    private var uploader: DeckUploader? = null
    private var caps: DeckCaps? = null
    private var job: Job? = null
    private var file: File? = null
    private var format: DeckFormat? = null
    private var deckId: String? = null

    fun attach(api: DeckApi?, uploader: DeckUploader?) { this.api = api; this.uploader = uploader }

    private fun set(s: DeckState) { state = s; onState(s) }

    private fun nameOf(s: DeckState): String? = when (s) {
        is DeckState.Copying -> s.name; is DeckState.Uploading -> s.name; is DeckState.Processing -> s.name; is DeckState.Ready -> s.name; is DeckState.Failed -> s.name; else -> null
    }

    /** Checks the pick, makes the private copy and runs the journey. A previous presentation is dropped first. */
    fun start(pick: DeckPick, caps: DeckCaps) {
        cancel()
        this.caps = caps
        val name = pick.name?.take(120) ?: ""
        when (val c = DeckRules.check(pick.name, pick.mime, pick.size, caps)) {
            is DeckCheck.Rejected -> { set(DeckState.Failed(name, DeckFailure(c.problem))); return }
            is DeckCheck.Ok -> format = c.format
        }
        set(DeckState.Copying(name))
        job = scope.launch {
            val copy = try { withContext(io) { copyPrivately(pick, caps) } } catch (e: CancellationException) { throw e } catch (e: Exception) { null }
            when (copy) {
                is Copy.Done -> { file = copy.file; run(name) }
                is Copy.Bad -> set(DeckState.Failed(name, DeckFailure(copy.problem)))
                null -> set(DeckState.Failed(name, DeckFailure(DeckProblem.Corrupt)))
            }
        }
    }

    private sealed interface Copy {
        class Done(val file: File) : Copy
        class Bad(val problem: DeckProblem) : Copy
    }

    /** Streams the picked file into our own cache folder (small buffer, a hard limit of the allowed size plus one byte, no name kept on disk). */
    private fun copyPrivately(pick: DeckPick, caps: DeckCaps): Copy {
        val input = pick.open() ?: return Copy.Bad(DeckProblem.Corrupt)
        root.mkdirs()
        val out = File(root, UUID.randomUUID().toString() + ".tmp")
        try {
            var total = 0L
            val head = ByteArray(8); var headLen = 0
            input.use { ins -> out.outputStream().use { o ->
                val buf = ByteArray(64 * 1024)
                while (true) {
                    val n = ins.read(buf)
                    if (n < 0) break
                    if (headLen < head.size) { val k = minOf(head.size - headLen, n); System.arraycopy(buf, 0, head, headLen, k); headLen += k }
                    total += n
                    if (total > caps.maxBytes) { out.delete(); return Copy.Bad(DeckProblem.TooLarge) }
                    o.write(buf, 0, n)
                }
            } }
            if (total == 0L) { out.delete(); return Copy.Bad(DeckProblem.Empty) }
            DeckRules.sniff(format!!, head.copyOf(headLen))?.let { out.delete(); return Copy.Bad(it) }
            return Copy.Done(out)
        } catch (e: Exception) { out.delete(); throw e }
    }

    /** Request the slot, upload, delete the copy, process, poll. [name] is only for the card. */
    private suspend fun run(name: String) {
        val a = api; val up = uploader; val f = file; val fmt = format
        if (a == null || up == null || f == null || fmt == null) { dropFile(); set(DeckState.Failed(name, DeckFailure(DeckProblem.Unavailable))); return }
        var uploaded = false
        try {
            val size = f.length()
            set(DeckState.Uploading(name, 0, size))
            val slot = a.createSlot(fmt, size)
            deckId = slot.id
            var lastPercent = -1
            up.upload(slot, f) { sent, total ->
                val p = if (total <= 0) 0 else (sent * 100 / total).toInt()
                if (p != lastPercent) { lastPercent = p; set(DeckState.Uploading(name, sent, total)) }
            }
            dropFile()   // the deck stays on the device only until the upload is done
            uploaded = true
            set(DeckState.Processing(name))
            a.process(slot.id)
            poll(name, slot.id)
        } catch (e: CancellationException) { throw e
        } catch (e: Exception) {
            // after the upload there is no copy left to send again: a lost connection then means "keep waiting" (which asks the server to process again, harmless)
            val failure = failureOf(e).let { if (uploaded && it.problem.action == DeckAction.Retry) DeckFailure(DeckProblem.Stalled) else it }
            if (failure.problem.action != DeckAction.Retry) dropFile()
            set(DeckState.Failed(name, failure))
        }
    }

    private suspend fun poll(name: String, id: String) {
        val a = api ?: return
        val started = nowMillis()
        var attempt = 0; var errors = 0
        while (true) {
            if (nowMillis() - started > DeckBackoff.GIVE_UP_MILLIS) { set(DeckState.Failed(name, DeckFailure(DeckProblem.Stalled))); return }
            wait(DeckBackoff.intervalMillis(attempt++))
            val s = try { a.status(id).also { errors = 0 } } catch (e: CancellationException) { throw e
            } catch (e: ApiError.Deck) { set(DeckState.Failed(name, failureOf(e))); return   // the deck is gone (missing): nothing to wait for
            } catch (e: Exception) { if (++errors >= DeckBackoff.MAX_STATUS_ERRORS) { set(DeckState.Failed(name, DeckFailure(DeckProblem.Stalled))); return }; continue }
            when (s) {
                is DeckStatus.Ready -> { set(DeckState.Ready(name, s.info)); return }
                is DeckStatus.Failed -> { set(DeckState.Failed(name, DeckFailure(DeckProblem.fromCode(s.code), s.message))); return }
                else -> {}
            }
        }
    }

    private fun failureOf(e: Exception): DeckFailure = when (e) {
        is ApiError.Network -> DeckFailure(DeckProblem.Offline)
        is ApiError.Deck -> DeckFailure(DeckProblem.fromCode(e.code), e.text)
        is ApiError.Quota -> DeckFailure(DeckProblem.DailyLimit)
        is ApiError.Invalid -> DeckFailure(DeckProblem.UploadFailed)
        else -> DeckFailure(DeckProblem.Other)
    }

    /** Try again after an upload that did not finish (the temporary copy is still here). */
    fun retry() {
        val s = state as? DeckState.Failed ?: return
        if (s.failure.problem.action != DeckAction.Retry || file?.exists() != true) return
        job?.cancel()
        job = scope.launch { run(s.name ?: "") }
    }

    /** After "taking longer than usual": look again at the same presentation. */
    fun keepWaiting() {
        val s = state as? DeckState.Failed ?: return
        val id = deckId ?: return
        if (s.failure.problem.action != DeckAction.KeepWaiting) return
        job?.cancel()
        set(DeckState.Processing(s.name ?: ""))
        job = scope.launch {
            try { api?.process(id); poll(s.name ?: "", id) } catch (e: CancellationException) { throw e } catch (e: Exception) { set(DeckState.Failed(s.name, failureOf(e))) }
        }
    }

    /** Cancel an upload, remove a ready or failed presentation: everything stops, the copy is deleted, the state is [DeckState.Idle]. */
    fun cancel() {
        job?.cancel(); job = null
        dropFile(); deckId = null; format = null
        if (state !is DeckState.Idle) set(DeckState.Idle)
    }

    /** The ViewModel is gone: stop and delete, no state to report. */
    fun release() { job?.cancel(); job = null; dropFile(); root.deleteRecursively() }

    /** The id and name a Create needs. */
    val ready: DeckReady? get() = (state as? DeckState.Ready)?.info

    private fun dropFile() { file?.let { runCatching { it.delete() } }; file = null }

    /** How many private copies are on disk right now (tests and the wipe check). */
    fun filesOnDisk(): Int = root.listFiles()?.size ?: 0

    companion object {
        /** An app start removes what a killed process left behind. */
        fun cleanLeftovers(root: File) { root.deleteRecursively() }
    }
}
