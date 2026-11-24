package com.videomk.app

import android.content.Intent
import com.videomk.app.core.AuthService

/** Release twin of the debug hooks: does nothing, so no test entry point exists in a release build. */
object DebugHooks {
    val enabled = false
    @Suppress("UNUSED_PARAMETER") fun seed(intent: Intent?, auth: AuthService) {}
    @Suppress("UNUSED_PARAMETER") fun defaultMinutes(intent: Intent?): Double? = null
    @Suppress("UNUSED_PARAMETER") fun photoFiles(intent: Intent?): List<String> = emptyList()
}
