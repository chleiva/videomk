package com.videomk.app

import android.content.Intent
import com.videomk.app.core.AuthService

/** Release twin of the debug hooks: does nothing, so no test entry point exists in a release build. */
object DebugHooks {
    val enabled = false
    @Suppress("UNUSED_PARAMETER") fun seed(intent: Intent?, auth: AuthService) {}
    @Suppress("UNUSED_PARAMETER") fun defaultMinutes(intent: Intent?): Double? = null
    @Suppress("UNUSED_PARAMETER") fun photoFiles(intent: Intent?): List<String> = emptyList()

    @Suppress("UNUSED_PARAMETER") fun fakeMedia(context: android.content.Context): com.videomk.app.core.MediaApi? = null
    @Suppress("UNUSED_PARAMETER") fun balanceOverride(context: android.content.Context): Int? = null
    @Suppress("UNUSED_PARAMETER") fun mediaFiles(intent: Intent?): List<String> = emptyList()
    @Suppress("UNUSED_PARAMETER") fun fakePoster(context: android.content.Context): com.videomk.app.core.SlotPoster? = null
    @Suppress("UNUSED_PARAMETER") fun prompt(intent: Intent?): String? = null
    @Suppress("UNUSED_PARAMETER") fun fakeIntake(context: android.content.Context): com.videomk.app.core.IntakeApi? = null
    @Suppress("UNUSED_PARAMETER") fun manyVideos(context: android.content.Context): Int = 0
    @Suppress("UNUSED_PARAMETER") fun emptyHome(context: android.content.Context): Boolean = false
    @Suppress("UNUSED_PARAMETER") fun social(context: android.content.Context): com.videomk.app.core.SocialSwitches? = null
    @Suppress("UNUSED_PARAMETER") fun fixture(intent: Intent?): (@androidx.compose.runtime.Composable () -> Unit)? = null
}
