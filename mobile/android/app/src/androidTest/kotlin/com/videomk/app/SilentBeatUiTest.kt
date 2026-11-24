package com.videomk.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.videomk.app.core.EditorBeat
import com.videomk.app.core.SceneKind
import com.videomk.app.ui.BeatRow
import com.videomk.app.ui.NarrationSupport
import com.videomk.app.ui.VideoMkTheme
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** QA has no silent beat yet, so the real composables are rendered on the emulator with a fixture beat. */
@RunWith(AndroidJUnit4::class)
class SilentBeatUiTest {
    @get:Rule val rule = createComposeRule()

    private val pause = EditorBeat("p", "", SceneKind.Image, silent = true, hold = 4.0)

    @Test fun silentBeatRowShowsTheSilentPauseLabelInsteadOfNarration() {
        rule.setContent { VideoMkTheme { BeatRow(pause, edited = false, error = null, reorder = false, picked = false, canUp = false, canDown = false, onClick = {}, onUp = {}, onDown = {}, onDelete = {}) } }
        rule.onNodeWithTag("silentBeatLabel", useUnmergedTree = true).assertExists()
        rule.onNodeWithText("Silent pause, 4 s").assertIsDisplayed()
    }

    @Test fun aSpokenBeatRowShowsNoSilentLabel() {
        val spoken = EditorBeat("s", "A line of narration with enough words in it.", SceneKind.Title)
        rule.setContent { VideoMkTheme { BeatRow(spoken, false, null, false, false, false, false, {}, {}, {}, {}) } }
        rule.onNodeWithTag("silentBeatLabel", useUnmergedTree = true).assertDoesNotExist()
    }

    @Test fun theSceneEditorExplainsAnEmptyPause() {
        rule.setContent { VideoMkTheme { NarrationSupport(pause, words = 0, minWords = 6, maxWords = 70, error = null) } }
        rule.onNodeWithText("A silent pause: nothing is spoken for 4 seconds and the music carries it. Type words here to give it a voice.").assertIsDisplayed()
    }
}
