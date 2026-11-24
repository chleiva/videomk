package com.videomk.app.core

sealed class ApiError(final override val message: String) : Exception(message) {
    data object Unauthorized : ApiError("Your session expired. Please sign in again.")
    data class Invalid(val text: String) : ApiError(text)
    data class Quota(val text: String) : ApiError(text)
    data class NotReady(val status: VideoStatus) : ApiError("This video isn't ready yet.")
    /** The video changed since it was loaded, or a render is already running (editor only). */
    data class Conflict(val text: String) : ApiError(text)
    data object Network : ApiError("Network problem. Check your connection and try again.")
    data object Server : ApiError("Something went wrong on our side. Please try again.")
    data class InsufficientCredits(val balance: Int, val needed: Int) :
        ApiError("This video needs $needed credit${if (needed == 1) "" else "s"} and you have $balance.")
}

class AuthException(val kind: Kind) : Exception(kind.name) {
    enum class Kind { SignedOut, Cancelled, Failed }
}
