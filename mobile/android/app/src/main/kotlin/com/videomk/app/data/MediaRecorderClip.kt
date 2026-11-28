package com.videomk.app.data

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import com.videomk.app.core.ClipRecorder
import java.io.File

/**
 * The clip for "Better dictation": AAC in an MP4 (m4a) file, mono, 16 kHz, 32 kbps (5 minutes is about 1.2 MB). Every platform call is guarded: a phone that does not allow
 * a second microphone client next to the speech recognizer answers false from [start] (the native engine then carries on alone) and never crashes.
 * Not testable without a microphone; the file and the upload rules around it are tested in `BetterDictationEngine`.
 */
class MediaRecorderClip(context: Context) : ClipRecorder {
    private val appContext = context.applicationContext
    private var recorder: MediaRecorder? = null

    @Suppress("DEPRECATION")
    override fun start(file: File): Boolean {
        stopQuietly()
        val r = try { if (Build.VERSION.SDK_INT >= 31) MediaRecorder(appContext) else MediaRecorder() } catch (e: Throwable) { return false }
        return try {
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioChannels(1)
            r.setAudioSamplingRate(16_000)
            r.setAudioEncodingBitRate(32_000)
            r.setOutputFile(file.absolutePath)
            r.prepare()
            r.start()
            recorder = r
            true
        } catch (e: Throwable) {
            runCatching { r.release() }
            false
        }
    }

    override fun stop(): Boolean {
        val r = recorder ?: return false
        recorder = null
        return try { r.stop(); true } catch (e: Throwable) { false } finally { runCatching { r.release() } }   // stop() throws when nothing was recorded
    }

    override fun abort() { stopQuietly() }

    private fun stopQuietly() { val r = recorder ?: return; recorder = null; runCatching { r.stop() }; runCatching { r.release() } }
}
