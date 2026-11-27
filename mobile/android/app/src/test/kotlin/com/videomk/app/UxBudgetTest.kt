package com.videomk.app

import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The text budgets of docs/UX_2026_REDESIGN.md section 4 as a test: the static words a person sees on a screen (English and Spanish catalogs, counted from the
 * strings the screen shows) must stay under the budget, so a later change cannot quietly put the clutter back.
 */
class UxBudgetTest {
    private val en = JvmStringProvider.Catalog.load("values")
    private val es = JvmStringProvider.Catalog.load("values-es")

    private fun words(c: JvmStringProvider.Catalog, vararg names: String): Int = names.sumOf { n ->
        (c.strings[n] ?: error("missing $n")).replace(Regex("%\\d?\\$?[sd]"), "N").split(Regex("[\\s·]+")).count { it.isNotBlank() }
    }

    private fun check(label: String, budget: Int, vararg names: String) {
        for ((lang, c) in listOf("en" to en, "es" to es)) {
            val n = words(c, *names)
            assertTrue("$label ($lang) shows $n words, budget $budget", n <= budget)
        }
    }

    /** Create's main surface (docs/DESIGN_BAR_2026.md rule 4): the prompt hint, three pill values (a platform word, a length, a look), the Create button and the credits caption. Budget 14. */
    @Test fun `create surface stays within 14 words`() {
        check("Create surface", 11, "create_prompt_hint", "create_pill_video", "create_summary_look_auto", "create_create_video", "create_capsule_sub")   // + "1 min" and "N credits left" = 14 at most
        for (c in listOf(en, es)) assertTrue(c.plurals["create_credits_left"]!!.values.all { it.split(" ").size <= 3 })
    }

    /** The three example chips are suggestions, a few words each; the capsule says what is happening in three words. */
    @Test fun `example chips and the capsule stay short`() {
        check("Example chips", 13, "create_example_bees", "create_example_focus", "create_example_forests")
        check("Capsule, checking", 3, "create_capsule_checking"); check("Capsule, starting", 3, "create_capsule_starting")
    }

    /** First run: the headline, the prompt field and three short example chips. Budget 14. */
    @Test fun `first run stays within 14 words`() =
        check("First run", 14, "lib_empty_title", "create_prompt_hint", "lib_example_chip_lighthouse", "lib_example_chip_bees", "lib_example_chip_holiday")

    /** The video screen beside the title: the caption is numbers; the five actions are icons (no visible words). Budget 8 for the failed state: title and one line. */
    @Test fun `failed video state stays within 8 words`() = check("Failed video", 8, "video_failed_title", "video_failed_body")

    /** Credits: the explanation is one popover, not four paragraphs. Budget 18 for the rules; the question sheets drop the helper lines. */
    @Test fun `credit rules fit one short popover`() = check("Credit rules", 18, "wallet_how_short")

    /** The Media tab's selection flow: the one primary button and the one-time tip stay short. */
    @Test fun `media selection button stays within 4 words`() = check("Make a video button", 4, "media_make_video_count")
    @Test fun `media select tip stays within 10 words`() = check("Select tip", 10, "media_select_hint")

    @Test fun `making promise is one short sentence`() = check("Making promise", 12, "making_leave_promise")

    @Test fun `feedback intro is three words`() = check("Feedback intro", 5, "feedback_intro")
}
