package com.videomk.app.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import java.time.Duration
import java.time.Instant

/*
 * In-app account deletion (docs/ACCOUNT_DELETION.md). The people-facing wording is in [DeletionText], the flow is [AccountDeletionFlow].
 *
 * Invariants:
 *  - The stored session is never touched until the server has answered 202. Re-authentication runs next to it and only replaces the tokens
 *    when the new sign-in is the same account, so a cancelled, failed or wrong-account re-sign-in leaves the person signed in and nothing deleted.
 *  - The delete request is only ever sent from [AccountDeletionFlow.start], which needs the typed word. A redirect (sign-out, sign-in, Apple) can
 *    only move an already running deletion one step on; with no deletion running every one of them is ignored.
 *  - Tokens, the Apple link and the email are never logged.
 */

/** What the server says about the person's Sign in with Apple grant (the `apple` field of the 202). An unknown or missing value is [Unknown]. */
enum class AppleRevoke {
    NotLinked, RevokeAvailable, RevokeOff, Unknown;

    companion object {
        fun fromWire(s: String?): AppleRevoke = when (s) {
            "not_linked" -> NotLinked
            "revoke_available" -> RevokeAvailable
            "revoke_off" -> RevokeOff
            else -> Unknown
        }
    }
}

sealed interface AccountDeleteResult {
    data class Accepted(val apple: AppleRevoke) : AccountDeleteResult
    /** 401 `reauth_required`: the sign-in is older than 10 minutes. */
    data object ReauthRequired : AccountDeleteResult
    /** 401 without that code: the token itself is not accepted. Handled like [ReauthRequired] (a new sign-in fixes both). */
    data object Unauthorized : AccountDeleteResult
    data object Forbidden : AccountDeleteResult
    /** 400: the confirmation word was not accepted. */
    data object Rejected : AccountDeleteResult
    data object ServerError : AccountDeleteResult
    /** No answer (offline, timeout, connection dropped). The deletion may or may not have started: calling again is safe. */
    data object Offline : AccountDeleteResult
}

interface AccountApi {
    suspend fun deleteAccount(idToken: String, sub: String): AccountDeleteResult
    /** The Apple page to open, or null when the server cannot offer it (never throws for server or network problems). */
    suspend fun appleRevokeUrl(idToken: String, sub: String): String?
}

object AppleRevokeLink {
    /** Only Apple's own https authorize page is ever opened from this link. */
    fun isAcceptable(url: String): Boolean = url.toHttpUrlOrNull()?.let { it.isHttps && it.host == "appleid.apple.com" } == true
}

/** Removes everything this device holds for the person (tokens, caches, files, preferences, databases). Must not throw for a single failing step. */
fun interface LocalWiper { suspend fun wipe() }

interface DeletionSession : AuthorizationProviding {
    fun logoutUrl(): HttpUrl
    fun beginReauth(expectedSub: String): HttpUrl
    val reauthInProgress: Boolean
    suspend fun completeReauth(callback: String): ReauthResult
    fun cancelReauth()
}

enum class ReauthStep { LoggingOut, SigningIn }

enum class DeletionFailure {
    Offline, Server, Forbidden, Rejected, ReauthCancelled, ReauthFailed, WrongAccount, StillStale,
}

sealed interface AppleStep {
    /** Nothing to do (no Apple sign-in on the account, or the server does not know). */
    data object None : AppleStep
    /** The person finishes it by hand in their Apple account settings. */
    data object Manual : AppleStep
    /** The server gave a link to Apple's page; the person can open it now. */
    data class Available(val url: String) : AppleStep
    data object Done : AppleStep
}

sealed interface DeletionState {
    data object Idle : DeletionState
    /** Checking the session, or waiting for the server. */
    data object Working : DeletionState
    /** A browser page is open and the person must sign in again. */
    data class Reauth(val step: ReauthStep) : DeletionState
    /** Nothing was deleted (or it is unknown); the person is still signed in and may retry. */
    data class Failed(val reason: DeletionFailure) : DeletionState
    /** The server accepted. Everything local is gone and the app is signed out. */
    data class Accepted(val apple: AppleStep) : DeletionState
}

object DeletionText {
    const val CONFIRM_WORD = "DELETE"

    val deletes = listOf("Your videos", "Your photos and everything in My media", "Your credits, including any you have left", "Your sign-in")
    const val IRREVERSIBLE = "This can't be undone."
    const val NEXT = "Your data is removed within minutes and your sign-in within about an hour or two. If you want to sign up again with the same email, please wait until then."
    const val REAUTH_NOTE = "To make sure it's you, you may be asked to sign in again first."
    const val DONE_TITLE = "Your account is being deleted"
    const val DONE_BODY = NEXT
    const val SETTINGS_BODY = "Permanently deletes your account, your videos, your photos and My media, your credits and your sign-in. This can't be undone."
    const val APPLE_AVAILABLE = "You signed in with Apple. To finish, confirm with Apple so videomk stops being connected to your Apple ID. This is optional and your account is deleted either way."
    const val APPLE_MANUAL = "To finish, go to appleid.apple.com, sign in, open Sign-In and Security, then Sign in with Apple, choose videomk and select Stop using Apple ID."
    const val APPLE_DONE = "Done: videomk no longer has access through your Apple ID."
    const val WEB_URL = "https://videomk.com/delete-account"

    fun message(f: DeletionFailure): String = when (f) {
        DeletionFailure.Offline -> "We couldn't reach videomk, so we can't tell if the deletion started. Check your connection and try again. Trying again is safe."
        DeletionFailure.Server -> "Something went wrong on our side and nothing was deleted. Please try again."
        DeletionFailure.Forbidden -> "This request doesn't match the account you are signed in to, so nothing was deleted. Sign out, sign in again and retry."
        DeletionFailure.Rejected -> "The confirmation wasn't accepted, so nothing was deleted. Check the word and try again."
        DeletionFailure.ReauthCancelled -> "You didn't finish signing in again, so nothing was deleted. You are still signed in."
        DeletionFailure.ReauthFailed -> "We couldn't confirm it's you, so nothing was deleted. You are still signed in. Please try again."
        DeletionFailure.WrongAccount -> "You signed in with a different account, so nothing was deleted. Use the account you are deleting."
        DeletionFailure.StillStale -> "We still couldn't confirm a fresh sign-in, so nothing was deleted. Please try again. If it keeps failing, use the steps at videomk.com/delete-account."
    }
}

/**
 * Runs one deletion. States: Idle, Working, Reauth (browser open), Failed, Accepted (see [DeletionState]).
 *
 *  start(typed word) -> token fresh (`auth_time` within [FRESH_SECONDS]) ? send : re-authenticate first
 *  re-authenticate  -> hosted /logout (wait for its redirect) -> normal authorize with prompt=login&max_age=0 -> new token (same `sub`) -> send
 *  send             -> 202: [finish]; 401: re-authenticate once (a second 401 is "still stale"); 403/400/5xx/offline: Failed, nothing lost
 *
 * Browser pages are requested through [requests]; the activity opens them in a Custom Tab and reports back through the on* functions.
 */
class AccountDeletionFlow(
    private val session: DeletionSession,
    private val api: AccountApi,
    private val wiper: LocalWiper,
    private val scope: CoroutineScope,
    /** Called once everything local is gone: the app moves to the signed-out phase. */
    private val onWiped: () -> Unit,
    /** The session turned out to be over before anything was sent (refresh token revoked): the app signs out. */
    private val onSessionEnded: () -> Unit,
    private val now: () -> Instant = { Instant.now() },
    private val appleTimeoutMillis: Long = 8_000,
) {
    private val _state = MutableStateFlow<DeletionState>(DeletionState.Idle)
    val state: StateFlow<DeletionState> = _state.asStateFlow()

    private val _requests = MutableSharedFlow<HttpUrl>(extraBufferCapacity = 4)
    /** Pages the activity must open in a Custom Tab. */
    val requests: SharedFlow<HttpUrl> = _requests

    @Volatile private var reauthSub: String? = null

    val isRunning: Boolean get() = _state.value.let { it is DeletionState.Working || it is DeletionState.Reauth }

    /** The only way a deletion starts. Needs the exact confirmation word; ignored while one is running or after it was accepted. */
    fun start(typed: String) {
        if (typed.trim() != DeletionText.CONFIRM_WORD) return
        val cur = _state.value
        if (cur !is DeletionState.Idle && cur !is DeletionState.Failed) return
        if (!_state.compareAndSet(cur, DeletionState.Working)) return
        scope.launch { attempt() }
    }

    /** Leaves a failure behind (the sheet was closed). Never interrupts a running deletion. */
    fun reset() { if (_state.value is DeletionState.Failed) _state.value = DeletionState.Idle }

    /** The person leaves the sign-in step. Nothing was sent; the session is untouched. */
    fun cancel() {
        if (_state.value is DeletionState.Reauth) { session.cancelReauth(); reauthSub = null; _state.value = DeletionState.Failed(DeletionFailure.ReauthCancelled) }
    }

    /** The browser was closed without a redirect. */
    fun onBrowserAbandoned() = cancel()

    /** `com.videomk.app://auth/signout` arrived. Only meaningful while the hosted sign-out page is open. */
    fun onLogoutReturned() {
        val sub = reauthSub ?: return
        if (!_state.compareAndSet(DeletionState.Reauth(ReauthStep.LoggingOut), DeletionState.Reauth(ReauthStep.SigningIn))) return
        _requests.tryEmit(session.beginReauth(sub))
    }

    /** `com.videomk.app://auth/callback?...` arrived while the sign-in step is open (the caller checks [reauthPending] first). */
    fun onReauthCallback(callback: String) {
        if (!_state.compareAndSet(DeletionState.Reauth(ReauthStep.SigningIn), DeletionState.Working)) return
        scope.launch {
            try {
                when (val r = session.completeReauth(callback)) {
                    is ReauthResult.Completed -> send(r.authorization, reauthed = true)
                    is ReauthResult.Retry -> { _state.value = DeletionState.Reauth(ReauthStep.SigningIn); _requests.tryEmit(r.url) }
                    ReauthResult.WrongAccount -> fail(DeletionFailure.WrongAccount)
                    ReauthResult.Cancelled -> fail(DeletionFailure.ReauthCancelled)
                    ReauthResult.Failed -> fail(DeletionFailure.ReauthFailed)
                }
            } catch (e: CancellationException) { throw e } catch (e: Exception) { fail(DeletionFailure.ReauthFailed) }
        }
    }

    val reauthPending: Boolean get() = _state.value == DeletionState.Reauth(ReauthStep.SigningIn) && session.reauthInProgress

    /** The Apple page the server offered, opened from the done screen. */
    fun openApple() {
        val step = (_state.value as? DeletionState.Accepted)?.apple as? AppleStep.Available ?: return
        step.url.toHttpUrlOrNull()?.let { _requests.tryEmit(it) }
    }

    /** `com.videomk.app://auth/apple-revoked?status=...`. Ignored unless a deletion was accepted and the Apple step is waiting. */
    fun onAppleReturn(status: String?) {
        val s = _state.value as? DeletionState.Accepted ?: return
        if (s.apple !is AppleStep.Available) return
        _state.value = DeletionState.Accepted(if (status == "ok") AppleStep.Done else AppleStep.Manual)
    }

    /** The done screen is closed: back to the signed-out screen. */
    fun dismissDone() { if (_state.value is DeletionState.Accepted) _state.value = DeletionState.Idle }

    // steps

    private suspend fun attempt() {
        try {
            val auth = try { session.authorization() } catch (e: AuthException) {
                if (e.kind == AuthException.Kind.SignedOut) { _state.value = DeletionState.Idle; onSessionEnded() } else fail(DeletionFailure.Server)
                return
            }
            if (isStale(auth.idToken)) beginReauth(auth.userId) else send(auth, reauthed = false)
        } catch (e: CancellationException) { throw e } catch (e: Exception) { fail(DeletionFailure.Server) }
    }

    private fun isStale(idToken: String): Boolean {
        val at = Jwt.authTime(idToken) ?: return true
        return Duration.between(at, now()).seconds > FRESH_SECONDS
    }

    private fun beginReauth(sub: String) {
        reauthSub = sub
        _state.value = DeletionState.Reauth(ReauthStep.LoggingOut)
        _requests.tryEmit(session.logoutUrl())
    }

    private suspend fun send(auth: Authorization, reauthed: Boolean) {
        when (val r = api.deleteAccount(auth.idToken, auth.userId)) {
            is AccountDeleteResult.Accepted -> finish(auth, r.apple)
            AccountDeleteResult.ReauthRequired, AccountDeleteResult.Unauthorized -> if (reauthed) fail(DeletionFailure.StillStale) else beginReauth(auth.userId)
            AccountDeleteResult.Forbidden -> fail(DeletionFailure.Forbidden)
            AccountDeleteResult.Rejected -> fail(DeletionFailure.Rejected)
            AccountDeleteResult.ServerError -> fail(DeletionFailure.Server)
            AccountDeleteResult.Offline -> fail(DeletionFailure.Offline)
        }
    }

    private suspend fun finish(auth: Authorization, apple: AppleRevoke) {
        withContext(NonCancellable) {
            // The Apple link needs the token, so it is asked for before the tokens are wiped; it is bounded and never blocks the deletion.
            val step: AppleStep = when (apple) {
                AppleRevoke.NotLinked, AppleRevoke.Unknown -> AppleStep.None
                AppleRevoke.RevokeOff -> AppleStep.Manual
                AppleRevoke.RevokeAvailable -> {
                    val url = try { withTimeoutOrNull(appleTimeoutMillis) { api.appleRevokeUrl(auth.idToken, auth.userId) } } catch (e: Exception) { null }
                    if (url != null && AppleRevokeLink.isAcceptable(url)) AppleStep.Available(url) else AppleStep.Manual
                }
            }
            try { wiper.wipe() } catch (e: Exception) { /* each step of the real wiper is guarded; whatever is left is reported by the owner's tests, not shown to the person */ }
            reauthSub = null
            _state.value = DeletionState.Accepted(step)
            onWiped()
        }
    }

    private fun fail(reason: DeletionFailure) { reauthSub = null; _state.value = DeletionState.Failed(reason) }

    companion object {
        /** The server allows 10 minutes; one minute less leaves room for a slow typist and clock differences. */
        const val FRESH_SECONDS = 540L
    }
}
