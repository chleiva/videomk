package com.videomk.app.core

import kotlinx.serialization.json.JsonObject
import java.time.Instant

/** What the user needs to know about a video's state. The server has finer statuses; we only distinguish what changes the UI. */
sealed interface VideoStatus {
    data class Running(val stage: Stage) : VideoStatus
    data object Complete : VideoStatus
    data object Failed : VideoStatus
    data object Rejected : VideoStatus

    enum class Stage(val shortTitle: String, val title: String) {
        Starting("Starting", "Getting started"),
        Writing("Writing the story", "Writing the story"),
        VoiceAndVisuals("Voice and visuals", "Recording the voice and finding visuals"),
        Rendering("Rendering", "Rendering"),
    }

    val isRunning: Boolean get() = this is Running

    companion object {
        fun fromServer(raw: String): VideoStatus = when (raw.uppercase()) {
            "COMPLETE", "PREVIEW_READY" -> Complete
            "FAILED", "EDIT_FAILED", "CANCELLED" -> Failed
            "REJECTED" -> Rejected
            "PLOT_CREATION" -> Running(Stage.Writing)
            "ASSETS_CREATION", "STORYBOARD_CREATION" -> Running(Stage.VoiceAndVisuals)
            "RENDERING" -> Running(Stage.Rendering)
            else -> Running(Stage.Starting)
        }
    }
}

data class VideoItem(
    val id: String,
    val status: VideoStatus,
    val title: String? = null,
    val durationSeconds: Double? = null,
    val createdAt: Instant? = null,
    val videoUrl: String? = null,
    val previewGifUrl: String? = null,
    val rejectReason: String? = null,
    val editable: Boolean = false,
) {
    val displayTitle: String get() = title?.takeIf { it.isNotEmpty() } ?: "Untitled video"

    companion object {
        fun fromJson(o: JsonObject): VideoItem = VideoItem(
            id = o.requireString("video_id"),
            status = VideoStatus.fromServer(o.str("status") ?: ""),
            title = o.str("title"),
            durationSeconds = o.num("duration_s"),
            createdAt = parseInstant(o.str("created_at")),
            videoUrl = o.str("video_url"),
            previewGifUrl = o.str("preview_gif_url"),
            rejectReason = o.str("reject_reason"),
            editable = o.bool("editable") ?: false,
        )
    }
}

data class PlaybackInfo(val url: String, val description: String?)

/** The three looks the video engine offers. */
enum class VideoLook(val wire: String, val title: String) {
    Midnight("midnight", "Midnight"), Paper("paper", "Paper"), Sunrise("sunrise", "Sunrise")
}

/** [captions]: subtitles on the video; the creator decides (on is the server default). */
data class CreateOptions(val minutes: Double = DEFAULT_MINUTES, val look: VideoLook? = null, val captions: Boolean = true) {
    /** 1 credit per started minute, at least 1, at most 12 (matches the server; the server's number is the one that is charged). */
    val credits: Int get() = maxOf(1, minOf(12, Math.ceil(minutes).toInt()))

    companion object {
        val LENGTHS = listOf(1.0, 2.0, 3.0, 5.0, 8.0, 12.0)
        const val DEFAULT_MINUTES = 3.0
    }
}

data class WalletBucket(val kindName: String, val remaining: Int, val expiresAt: Instant? = null) {
    enum class Kind { Daily, Signup, Paid, Refund, Other }

    val kind: Kind get() = when (kindName) {
        "daily" -> Kind.Daily
        "signup" -> Kind.Signup
        "paid" -> Kind.Paid
        "refund" -> Kind.Refund
        else -> Kind.Other
    }

    companion object {
        fun fromJson(o: JsonObject) = WalletBucket(o.requireString("kind"), o.requireInt("remaining"), epochSeconds(o.num("expires_at")))
    }
}

data class WalletInfo(
    val balance: Int,
    val buckets: List<WalletBucket> = emptyList(),
    val nextFreeAt: Instant? = null,
    val dailyCredits: Int = 1,
    val signupCredits: Int = 5,
    /** Test and staff accounts the server never charges. */
    val unlimited: Boolean = false,
) {
    fun canAfford(credits: Int): Boolean = unlimited || balance >= credits

    companion object {
        fun fromJson(o: JsonObject): WalletInfo {
            val rules = o.obj("rules")
            return WalletInfo(
                balance = o.requireInt("balance"),
                buckets = o.arr("buckets")?.mapNotNull { e -> e.asObject()?.let { runCatching { WalletBucket.fromJson(it) }.getOrNull() } } ?: emptyList(),
                nextFreeAt = epochSeconds(o.num("next_daily_at")),
                dailyCredits = rules?.int("daily") ?: 1,
                signupCredits = rules?.int("signup") ?: 5,
                unlimited = o.bool("unlimited") ?: false,
            )
        }
    }
}

object Brief {
    const val MIN_LENGTH = 10
    const val MAX_LENGTH = 2000

    /** Mirrors the server's whitespace collapse so the counter matches what is sent. */
    fun normalized(text: String): String = text.split(Regex("\\s+")).filter { it.isNotEmpty() }.joinToString(" ")
    fun isValid(text: String): Boolean = normalized(text).length in MIN_LENGTH..MAX_LENGTH
}
