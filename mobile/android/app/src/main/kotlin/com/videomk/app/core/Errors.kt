package com.videomk.app.core

import com.videomk.app.R

/** [message] is resolved when it is read (never at construction), so it follows the app language. Text that came from the server is shown as received. */
sealed class ApiError : Exception() {
    abstract override val message: String

    data object Unauthorized : ApiError() { override val message: String get() = Txt.s(R.string.err_session_expired) }
    data class Invalid(val text: String) : ApiError() { override val message: String get() = text }
    data class Quota(val text: String) : ApiError() { override val message: String get() = text }
    data class NotReady(val status: VideoStatus) : ApiError() { override val message: String get() = Txt.s(R.string.err_video_not_ready) }
    /** The video changed since it was loaded, or a render is already running (editor only). */
    data class Conflict(val text: String) : ApiError() { override val message: String get() = text }
    /** My media: nothing at all fits in the remaining storage (HTTP 402 `storage_full`). */
    data class StorageFull(val usedBytes: Long, val limitBytes: Long) : ApiError() { override val message: String get() = Txt.s(R.string.err_storage_full) }
    data object NotFound : ApiError() { override val message: String get() = Txt.s(R.string.err_not_found) }
    /** The safety check stopped the request (HTTP 400 `{status: "blocked"}` or a blocked brief). Nothing was charged. */
    data class Blocked(val text: String) : ApiError() { override val message: String get() = text }
    /** The account is paused after repeated safety stops (HTTP 429 `{status: "paused"}`); [retryAfterSeconds] says when it can try again. */
    data class Paused(val text: String, val retryAfterSeconds: Int?) : ApiError() { override val message: String get() = text }
    /** A presentation call the server refused with one of its stable `code`s (`deck_encrypted`, `too_many_decks`, `missing`...). [text] is the server's localized message. */
    data class Deck(val code: String, val text: String) : ApiError() { override val message: String get() = text }
    data object Network : ApiError() { override val message: String get() = Txt.s(R.string.err_network) }
    data object Server : ApiError() { override val message: String get() = Txt.s(R.string.err_server) }
    data class InsufficientCredits(val balance: Int, val needed: Int) : ApiError() {
        override val message: String get() = Txt.n(R.plurals.err_insufficient_credits, needed, balance)
    }
}

class AuthException(val kind: Kind) : Exception(kind.name) {
    /** [Network]: the auth server could not be reached (as opposed to [Failed], an answer that could not be used). */
    enum class Kind { SignedOut, Cancelled, Failed, AccountLink, Network }
}
