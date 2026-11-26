package com.videomk.app.ui

import android.os.Build
import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalView
import com.videomk.app.core.DesignTokens

/** The haptic map of docs/UX_REVIEW.md 6.2 item 7: only these moments vibrate. Use [rememberHaptics] in Compose. */
class Haptics(private val view: View) {
    fun play(h: DesignTokens.Haptic) {
        val sdk30 = Build.VERSION.SDK_INT >= 30
        val c = when (h) {
            DesignTokens.Haptic.Send -> HapticFeedbackConstants.CONTEXT_CLICK
            DesignTokens.Haptic.Selection -> HapticFeedbackConstants.CLOCK_TICK
            DesignTokens.Haptic.Warning -> if (sdk30) HapticFeedbackConstants.REJECT else HapticFeedbackConstants.LONG_PRESS
            DesignTokens.Haptic.VideoReady, DesignTokens.Haptic.UploadDone -> if (sdk30) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.LONG_PRESS
        }
        view.performHapticFeedback(c)
    }
}

@Composable
fun rememberHaptics(): Haptics { val v = LocalView.current; return androidx.compose.runtime.remember(v) { Haptics(v) } }
