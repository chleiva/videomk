package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.delay

/**
 * Debug only: the presentation calls with no server, so every state can be looked at (see DebugHooks.fakeDeck for the modes).
 * ok: upload in about a second, ready after two looks (12 slides, 4 minutes, 4 credits). uploading: stops at 43 percent. processing: never finishes.
 * stalled: the status calls fail until the app gives up. Any server code (deck_encrypted ...) fails the deck after two looks.
 */
class FakeDeckApi(private val mode: () -> String) : DeckApi {
    private var looks = 0

    override suspend fun createSlot(format: DeckFormat, size: Long): DeckSlot {
        looks = 0
        when (val m = mode()) {
            "offline" -> throw ApiError.Network
            "too_many_decks" -> throw ApiError.Deck(m, "")
            "unavailable" -> throw ApiError.Deck(m, "")
        }
        return DeckSlot("fake-deck-1", format, "https://example.invalid/upload", mapOf("key" to "decks/fake"), 50L * 1024 * 1024)
    }

    override suspend fun process(id: String) {}

    override suspend fun status(id: String): DeckStatus {
        val m = mode()
        looks++
        return when {
            m == "processing" -> DeckStatus.Processing
            m == "stalled" -> throw ApiError.Network
            m == "slowready" -> if (looks < 8) DeckStatus.Processing else ready()
            m.startsWith("deck_") -> if (looks < 3) DeckStatus.Processing else DeckStatus.Failed(m, "Server message for $m.")
            else -> if (looks < 3) DeckStatus.Processing else ready()
        }
    }

    private fun ready() = DeckStatus.Ready(DeckReady("fake-deck-1", 12, 4.0, 4))

    companion object {
        fun uploader(mode: () -> String) = DeckUploader { _, file, progress ->
            val total = file.length().coerceAtLeast(1)
            when (mode()) {
                "uploading" -> { progress(total * 43 / 100, total); delay(10 * 60_000) }
                "upload_failed" -> { progress(total / 3, total); delay(600); throw ApiError.Invalid("") }
                "offline_upload" -> { progress(total / 3, total); delay(600); throw ApiError.Network }
                else -> for (i in 1..5) { delay(250); progress(total * i / 5, total) }
            }
        }
    }
}
