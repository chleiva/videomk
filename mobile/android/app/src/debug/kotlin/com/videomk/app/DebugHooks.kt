package com.videomk.app

import android.content.Intent
import com.videomk.app.core.AuthService
import com.videomk.app.core.Jwt
import com.videomk.app.core.Tokens
import java.time.Instant

/**
 * QA and automation only: this file exists in the debug source set; the release source set has a no-op twin, so none of it is in a release build.
 * Intent extras start the app signed in or signed out, shorten the default video and attach photo files:
 *   vmk_debug_id_token, vmk_debug_refresh_token   start a signed-in session (tokens minted out of band)
 *   vmk_debug_reset=1                              sign out first
 *   vmk_debug_default_minutes=1                    the composer starts at 1 minute
 *   vmk_debug_photo_files=/a.jpg:/b.jpg            attach those files at launch (the system picker can't be driven by every test)
 */
object DebugHooks {
    val enabled = true

    fun seed(intent: Intent?, auth: AuthService) {
        intent ?: return
        if (intent.getStringExtra("vmk_debug_reset") == "1") auth.signOut()
        val id = intent.getStringExtra("vmk_debug_id_token")?.takeIf { it.isNotEmpty() } ?: return
        val exp = Jwt.expiry(id) ?: Instant.now().plusSeconds(3000)
        auth.seed(Tokens(id, "", intent.getStringExtra("vmk_debug_refresh_token")?.takeIf { it.isNotEmpty() }, exp))
    }

    fun defaultMinutes(intent: Intent?): Double? = intent?.getStringExtra("vmk_debug_default_minutes")?.toDoubleOrNull()

    fun photoFiles(intent: Intent?): List<String> =
        intent?.getStringExtra("vmk_debug_photo_files")?.split(":")?.filter { it.isNotBlank() } ?: emptyList()

    /** `vmk_debug_fake_media`: fake My media data (no server) for screenshots. Read from a file flag so it works without an intent at container time. */
    fun fakeMedia(context: android.content.Context): com.videomk.app.core.MediaApi? =
        if (java.io.File(context.filesDir, "fake_media").exists()) FakeMediaApi(full = java.io.File(context.filesDir, "fake_full").exists()) else null

    /** `files/fake_balance` holds a number: the credits the app pretends to have (to look at the "not enough credits" composer). */
    fun balanceOverride(context: android.content.Context): Int? =
        runCatching { java.io.File(context.filesDir, "fake_balance").readText().trim().toInt() }.getOrNull()

    /** `vmk_debug_media_files=/a.png:/b.png` adds those files to the My media upload queue at launch. */
    fun mediaFiles(intent: Intent?): List<String> =
        intent?.getStringExtra("vmk_debug_media_files")?.split(":")?.filter { it.isNotBlank() } ?: emptyList()

    /** With fake media on, uploads take a few seconds and one photo in six is refused, so every tile state can be looked at. */
    fun fakePoster(context: android.content.Context): com.videomk.app.core.SlotPoster? =
        if (java.io.File(context.filesDir, "fake_media").exists()) com.videomk.app.core.SlotPoster { _, fields, _ ->
            kotlinx.coroutines.delay(7000)
            if (fields["key"] == "fail") throw com.videomk.app.core.ApiError.Invalid("Too large. Photos can be up to 25 MB.")
        } else null

    /** `vmk_debug_prompt` fills the composer at launch (and focuses it): typing through adb is slow. */
    fun prompt(intent: Intent?): String? = intent?.getStringExtra("vmk_debug_prompt")?.takeIf { it.isNotBlank() }

    /** `files/fake_intake` holds a mode ("questions", "unsupported", "blocked", "paused", "slow", "ok"): fake capabilities (all formats ready) and a fake request check. */
    fun fakeIntake(context: android.content.Context): com.videomk.app.core.IntakeApi? {
        val f = java.io.File(context.filesDir, "fake_intake")
        return if (f.exists()) FakeIntakeApi { runCatching { f.readText().trim() }.getOrDefault("ok") } else null
    }

    /** `files/fake_many` holds a number N: every video is repeated N times (distinct ids) so the home list is long enough to fling to its bottom. */
    fun manyVideos(context: android.content.Context): Int = runCatching { java.io.File(context.filesDir, "fake_many").readText().trim().toInt() }.getOrDefault(0)

    /** `files/fake_empty_home`: show the home as if there were no videos (the empty state cannot be reached with a QA account that has videos). */
    fun emptyHome(context: android.content.Context): Boolean = java.io.File(context.filesDir, "fake_empty_home").exists()

    /** `files/fake_social` holds "both", "google" or "apple": show those social buttons whatever the build switches say (screenshots; no login is possible without provider credentials). */
    fun social(context: android.content.Context): com.videomk.app.core.SocialSwitches? =
        runCatching { java.io.File(context.filesDir, "fake_social").readText().trim() }.getOrNull()?.let {
            com.videomk.app.core.SocialSwitches(google = it == "both" || it == "google", apple = it == "both" || it == "apple")
        }

    /** `vmk_debug_fixture=<name>`: draw a screen with fake data instead of the app (see DeletionFixture). */
    fun fixture(intent: Intent?): (@androidx.compose.runtime.Composable () -> Unit)? = DeletionFixture.content(intent?.getStringExtra("vmk_debug_fixture"))
}
