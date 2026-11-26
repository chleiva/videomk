package com.videomk.app

import androidx.compose.runtime.Composable
import com.videomk.app.core.AppleStep
import com.videomk.app.core.DeletionFailure
import com.videomk.app.core.DeletionState
import com.videomk.app.core.ReauthStep
import com.videomk.app.ui.DeletionDoneScreenForFixture
import com.videomk.app.ui.SettingsScreen

/**
 * Debug only: draws the account deletion screens in a given state, with no server and no session, so they can be photographed.
 * `adb shell am start -n com.videomk.app/.MainActivity --es vmk_debug_fixture <name>`. Nothing here can send a request or delete anything.
 * Names: settings, sheet-form, sheet-typed, sheet-working, sheet-reauth-logout, sheet-reauth-signin, sheet-error-<offline|server|forbidden|rejected|cancelled|reauthfailed|wrong|stale>,
 * done-none, done-apple, done-manual, done-apple-ok.
 */
object DeletionFixture {
    fun content(name: String?): (@Composable () -> Unit)? {
        name ?: return null
        fun sheet(state: DeletionState, typed: String): @Composable () -> Unit = {
            SettingsScreen("me@example.com", onBack = {}, onSignOut = {}, deletion = state, onDeleteAccount = {}, initialSheetOpen = true, initialTyped = typed)
        }
        fun done(apple: AppleStep): @Composable () -> Unit = { DeletionDoneScreenForFixture(apple) }
        val failures = mapOf(
            "offline" to DeletionFailure.Offline, "server" to DeletionFailure.Server, "forbidden" to DeletionFailure.Forbidden, "rejected" to DeletionFailure.Rejected,
            "cancelled" to DeletionFailure.ReauthCancelled, "reauthfailed" to DeletionFailure.ReauthFailed, "wrong" to DeletionFailure.WrongAccount, "stale" to DeletionFailure.StillStale,
        )
        val out: (@Composable () -> Unit)? = when {
            name == "settings" -> { { SettingsScreen("me@example.com", onBack = {}, onSignOut = {}, onDeleteAccount = {}) } }
            name == "sheet-form" -> sheet(DeletionState.Idle, "")
            name == "sheet-typed" -> sheet(DeletionState.Idle, "DELETE")
            name == "sheet-working" -> sheet(DeletionState.Working, "DELETE")
            name == "sheet-reauth-logout" -> sheet(DeletionState.Reauth(ReauthStep.LoggingOut), "DELETE")
            name == "sheet-reauth-signin" -> sheet(DeletionState.Reauth(ReauthStep.SigningIn), "DELETE")
            name.startsWith("sheet-error-") -> failures[name.removePrefix("sheet-error-")]?.let { sheet(DeletionState.Failed(it), "DELETE") }
            name == "done-none" -> done(AppleStep.None)
            name == "done-apple" -> done(AppleStep.Available("https://appleid.apple.com/auth/authorize?fixture=1"))
            name == "done-manual" -> done(AppleStep.Manual)
            name == "done-apple-ok" -> done(AppleStep.Done)
            else -> null
        }
        return out
    }
}
