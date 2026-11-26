package com.videomk.app

import android.content.res.Configuration
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.getBoundsInRoot
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.dp
import androidx.test.platform.app.InstrumentationRegistry
import com.videomk.app.core.DayBucket
import com.videomk.app.core.MakingScene
import com.videomk.app.core.MakingSnapshot
import com.videomk.app.core.SocialSwitches
import com.videomk.app.core.VideoItem
import com.videomk.app.core.VideoStatus
import com.videomk.app.ui.AppState
import com.videomk.app.ui.DayHeader
import com.videomk.app.ui.FailedRow
import com.videomk.app.ui.MakingCard
import com.videomk.app.ui.MakingLayout
import com.videomk.app.ui.Phase
import com.videomk.app.ui.SignInScreen
import com.videomk.app.ui.VideoMkTheme
import com.videomk.app.ui.VideoRow
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.time.Instant
import java.util.Locale

/**
 * Layout at font scale 2.0 (and 1.0), a narrow 360 dp phone, English and Spanish: nothing is cut at the sides, every button is at least 48 dp high, and a
 * tall page scrolls to its last element. Pure Compose, no server and no account.
 */
class FontScaleLayoutTest {
    @get:Rule val rule = createComposeRule()

    private fun host(fontScale: Float, lang: String, widthDp: Int = 360, content: @Composable () -> Unit) {
        rule.setContent {
            val base = LocalContext.current
            val cfg = Configuration(androidx.compose.ui.platform.LocalConfiguration.current).apply { setLocale(Locale.forLanguageTag(lang)) }
            val ctx = base.createConfigurationContext(cfg)
            CompositionLocalProvider(LocalContext provides ctx, LocalDensity provides Density(LocalDensity.current.density, fontScale)) {
                VideoMkTheme(dark = false) { Column(Modifier.width(widthDp.dp), content = { content() }) }
            }
        }
    }

    private fun assertFits(tag: String, widthDp: Int = 360, minHeightDp: Int = 0) {
        val n = rule.onNodeWithTag(tag).performScrollTo()
        val b = n.getBoundsInRoot()
        assertTrue("$tag left ${b.left}", b.left.value >= -0.5f)
        assertTrue("$tag right ${b.right} > $widthDp", b.right.value <= widthDp + 0.5f)
        val h = (b.bottom - b.top).value
        assertTrue("$tag is $h high, needs $minHeightDp", h + 0.5f >= minHeightDp)
    }


    @Test fun signInAtTwoTimesFitsAndScrolls_english() = signInCase("en", 2f)
    @Test fun signInAtTwoTimesFitsAndScrolls_spanish() = signInCase("es", 2f)
    @Test fun signInAtNormalSize_spanish() = signInCase("es", 1f)

    private fun signInCase(lang: String, scale: Float) {
        rule.setContent {
            val base = LocalContext.current
            val cfg = Configuration(androidx.compose.ui.platform.LocalConfiguration.current).apply { setLocale(Locale.forLanguageTag(lang)) }
            CompositionLocalProvider(LocalContext provides base.createConfigurationContext(cfg), LocalDensity provides Density(LocalDensity.current.density, scale)) {
                VideoMkTheme(dark = false) { androidx.compose.foundation.layout.Box(Modifier.width(360.dp)) { SignInScreen(AppState(phase = Phase.SignedOut), SocialSwitches(google = true, apple = true)) {} } }
            }
        }
        for (tag in listOf("googleButton", "appleButton", "signInButton")) assertFits(tag, minHeightDp = 48)
    }

    private fun feed(lang: String, scale: Float) {
        val ready = VideoItem("v1", VideoStatus.Complete, "Cómo hacen miel las abejas, explicado en treinta segundos para todo el mundo", 182.0, Instant.now())
        val snapshot = MakingSnapshot.of("The history of the lighthouse and the people who kept the lamps burning", VideoStatus.Stage.VoiceAndVisuals, 20.0, 3.0)
        host(scale, lang) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
                DayHeader(DayBucket.Today)
                VideoRow(ready, "hace 1 h", {})
                MakingCard(snapshot.copy(scene = MakingScene(3, 7)), Modifier.testTag("making"))
                MakingCard(snapshot, Modifier.testTag("makingDetail"), MakingLayout.Detail)
                FailedRow("Un paseo tranquilo por Kioto", false, "Algo salió mal al montar el video.", null, "failed", {}, {})
            }
        }
        for (tag in listOf("dayHeader", "videoRow", "making", "makingDetail", "failed", "leavePromise")) assertFits(tag)
        for (tag in listOf("retryButton", "removeButton")) assertFits(tag, minHeightDp = 48)
    }

    @Test fun homeComponentsAtTwoTimes_english() = feed("en", 2f)
    @Test fun homeComponentsAtTwoTimes_spanish() = feed("es", 2f)
    @Test fun homeComponentsAtNormalSize_spanish() = feed("es", 1f)
}
