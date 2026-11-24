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
}
